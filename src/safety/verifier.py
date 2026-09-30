"""Conservative temporal heuristics. Neither overlap nor disappearance proves a crash."""
from collections import deque
import itertools
import math
import numpy as np
from config.v2 import SAFETY

class AccidentStateMachine:
    allowed = {'MONITORING': {'CANDIDATE'}, 'CANDIDATE': {'VERIFYING', 'UNCERTAIN'},
               'VERIFYING': {'NORMAL', 'NEAR_MISS', 'UNCERTAIN', 'LIKELY_ACCIDENT'}}

    @classmethod
    def transition(cls, event, state, timestamp):
        previous = event.get('phase', 'MONITORING')
        if state not in cls.allowed.get(previous, set()):
            raise ValueError(f'Invalid accident transition: {previous} -> {state}')
        event['phase'] = state
        event.setdefault('state_history', []).append({'state':state, 'timestamp':timestamp})


class CrashVerifier:
    def __init__(self, config=SAFETY):
        self.cfg = config
        self.motion = {}
        self.candidates = {}
        self.cooldowns = []
        self.results = deque(maxlen=100)
        self.recent_pairs = {}

    def _features(self, tr, t):
        c = self.cfg
        s = self.motion.setdefault(tr.id, {'samples': deque(), 'velocity': None,
            'last': t, 'stop_since': None, 'decel_at': -100., 'turn_at': -100., 'peak_speed': 0., 'velocities': deque(), 'launched_at': -100., 'stationary_observations': 0})
        if t-s['last'] > c.observation_gap:
            s['samples'].clear(); s['velocity'] = None; s['stop_since'] = None
            s['decel_at'] = s['turn_at'] = -100.; s['peak_speed'] = 0.; s['velocities'].clear()
        s['last'] = t
        # Short-window endpoint displacement detects changes hidden by long trend fits.
        x1,y1,x2,y2 = tr.box
        s['samples'].append((t, np.array([(x1+x2)/2, y2])))
        while len(s['samples']) > 2 and t-s['samples'][1][0] >= c.motion_window:
            s['samples'].popleft()
        dt = t-s['samples'][0][0]
        v = (s['samples'][-1][1]-s['samples'][0][1])/dt if dt >= c.motion_window*.8 else None
        if v is not None:
            speed = float(np.linalg.norm(v)); old = s['velocity']
            if speed < c.stopped_speed: s['stationary_observations'] += 1
            elif speed >= c.moving_speed and s['stationary_observations'] >= 3:
                s['launched_at'] = t
                s['stationary_observations'] = 0
            if old is not None:
                while len(s['velocities'])>1 and t-s['velocities'][1][0] >= c.heading_window:
                    s['velocities'].popleft()
                turn_reference = s['velocities'][0][1] if s['velocities'] else old
                prev = float(np.linalg.norm(turn_reference))
                # Compare with a recent peak to capture deceleration spread over frames.
                if s['peak_speed'] >= c.moving_speed and speed < s['peak_speed']*(1-c.deceleration_fraction):
                    if s.get('decelerating', False) is False: s['decel_at'] = t
                    s['decelerating'] = True
                else: s['decelerating'] = False
                if min(prev,speed) >= c.moving_speed:
                    angle = math.degrees(math.acos(float(np.clip(turn_reference@v/(prev*speed),-1,1))))
                    if angle >= c.heading_degrees: s['turn_at'] = t
            s['peak_speed'] = max(speed, s['peak_speed']*c.peak_speed_decay)
            s['velocity'] = v; s['velocities'].append((t,v.copy()))
            if speed < c.stopped_speed:
                if s['stop_since'] is None: s['stop_since'] = t
            else: s['stop_since'] = None
        return s

    def update(self, tracks, interactions, t, camera_motion=None):
        c = self.cfg
        eligible = {i:tr for i,tr in tracks.items() if tr.ready and tr.confidence >= c.minimum_confidence
                    and len(tr.history)>1 and t-tr.history[0][0] >= c.minimum_age}
        camera_safe = camera_motion is None or (camera_motion.get('available') and not camera_motion.get('moving'))
        features = {i:self._features(tr,t) for i,tr in eligible.items()}
        for pair in interactions:
            if pair['risk'] >= 61: self.recent_pairs[tuple(pair['ids'])] = (t,pair)
        self.recent_pairs = {k:v for k,v in self.recent_pairs.items() if t-v[0] <= c.convergence_memory}
        self.cooldowns = [r for r in self.cooldowns if t-r['until'] < 0]
        self.motion = {i:s for i,s in self.motion.items() if t-s['last'] < 3}
        proposals = []
        for ids,(seen,pair) in self.recent_pairs.items():
            if not all(i in eligible for i in ids): continue
            a,b = (eligible[i] for i in ids)
            close = np.linalg.norm(a.position-b.position) < (a.radius+b.radius)*c.proximity_scale
            # Must have observed convergence AND motion change AND proximity.
            changes = [t-features[i]['decel_at'] <= c.recent_motion_seconds or t-features[i]['turn_at'] <= c.recent_motion_seconds for i in ids]
            if close and any(changes): proposals.append((ids, pair, False))
        paired_ids = {i for ids,_,_ in proposals for i in ids}
        for i,s in features.items():
            # A normal stop or a legal turn alone cannot trigger a single-vehicle candidate.
            if eligible[i].cls!='person' and i not in paired_ids and t-s['decel_at'] <= c.recent_motion_seconds and t-s['turn_at'] <= c.event_heading_seconds:
                tr = eligible[i]
                proposals.append(((i,), {'x':float(tr.position[0]),'y':float(tr.position[1])}, True))
        for ids,pair,single in proposals:
            point = np.array([pair['x'],pair['y']])
            if ids in self.candidates or any(set(ids)&set(k) for k in self.candidates): continue
            if any(set(ids)&set(r['ids']) or np.linalg.norm(point-r['point'])<c.spatial_dedup_pixels for r in self.cooldowns): continue
            if len(self.candidates) >= c.max_candidates: continue
            evidence = {k:0. for k in c.weights}
            evidence.update(trajectory_convergence=0. if single else 1., proximity=0. if single else 1.)
            self.candidates[ids] = {'track_ids':list(ids), 'road_users':[eligible[i].cls for i in ids],
                'timestamp':t, 'x':float(point[0]),'y':float(point[1]), 'single':single,
                'evidence_signals':evidence, 'observations':0, 'missing':False, 'state':'POSSIBLE ACCIDENT',
                'last_observed':t, 'observed_seconds':0., 'camera_motion_safe':bool(camera_safe),
                'minimum_tracking_confidence':min(eligible[i].confidence for i in ids),
                'calibration_status':'calibrated' if all(eligible[i].road_position is not None for i in ids) else 'image-space',
                'state_history':[{'state':'MONITORING','timestamp':t}]}
            AccidentStateMachine.transition(self.candidates[ids], 'CANDIDATE', t)
        completed = []
        for ids,event in list(self.candidates.items()):
            if t == event['timestamp']: continue
            if event['phase'] == 'CANDIDATE': AccidentStateMachine.transition(event, 'VERIFYING', t)
            event['camera_motion_safe'] = event['camera_motion_safe'] and bool(camera_safe)
            e = event['evidence_signals']; present = all(i in features for i in ids)
            if present:
                event['observations'] += 1
                gap = t-event['last_observed']
                if gap <= c.observation_gap: event['observed_seconds'] += gap
                else: event['missing'] = True
                event['last_observed'] = t
                decels = [abs(features[i]['decel_at']-event['timestamp']) <= c.event_deceleration_seconds for i in ids]
                turns = [abs(features[i]['turn_at']-event['timestamp']) <= c.event_heading_seconds for i in ids]
                e['deceleration_anomaly'] = max(e['deceleration_anomaly'],float(any(decels)))
                e['heading_anomaly'] = max(e['heading_anomaly'],float(any(turns)))
                launched = [abs(features[i]['launched_at']-event['timestamp']) <= c.event_deceleration_seconds for i in ids]
                supported_impact = len(ids)>1 and (all(decels) or any(decels) and any(launched))
                e['stationary_target_displacement'] = max(e.get('stationary_target_displacement',0.),float(any(launched) and any(decels)))
                e['simultaneous_motion_change'] = max(e['simultaneous_motion_change'],float(supported_impact))
                stops = [features[i]['stop_since'] is not None and t-features[i]['stop_since'] >= c.stop_seconds for i in ids]
                e['post_event_stop'] = float(any(stops))
                e['temporal_persistence'] = min(1.,event['observed_seconds']/c.verification_seconds)
            elif t-event['last_observed'] > c.observation_gap:
                event['missing'] = True
            event['state'] = 'VERIFYING'
            if t-event['timestamp'] < c.verification_seconds: continue
            # Correlated trajectory features cannot accumulate unlimited confidence.
            # Each semantic group contributes at most one point, with mandatory gates.
            interaction = bool(e['trajectory_convergence'] and e['proximity'])
            impact = bool(e['deceleration_anomaly'] and (e['heading_anomaly'] if event['single'] else e['simultaneous_motion_change']))
            aftermath = bool(e['post_event_stop'])
            groups = {'INTERACTION':interaction, 'IMPACT':impact, 'AFTERMATH':aftermath}
            required = ['IMPACT','AFTERMATH'] if event['single'] else list(groups)
            score = sum(bool(groups[k]) for k in required)/len(required)
            coverage = (present and not event['missing'] and e['temporal_persistence'] >= c.minimum_coverage
                        and event['observations'] >= c.minimum_verification_observations)
            strong = coverage and event['camera_motion_safe'] and all(groups[k] for k in required)
            state = ('LIKELY SINGLE-VEHICLE ACCIDENT' if event['single'] else 'LIKELY COLLISION') if strong else 'UNCERTAIN'
            if coverage and event['camera_motion_safe'] and not aftermath:
                state = 'NEAR MISS' if not event['single'] else 'NORMAL INTERACTION'
            phase = 'LIKELY_ACCIDENT' if strong else 'NEAR_MISS' if state=='NEAR MISS' else 'NORMAL' if state=='NORMAL INTERACTION' else 'UNCERTAIN'
            AccidentStateMachine.transition(event, phase, t)
            event.update(state=state, evidence_score=round(score,3), evidence_groups=groups,
                         temporal_coverage=bool(coverage), verified_at=t)
            completed.append(dict(event)); self.results.append(dict(event)); del self.candidates[ids]
            self.cooldowns.append({'ids':ids,'point':np.array([event['x'],event['y']]),'until':t+c.cooldown_seconds})
        return completed

    def flush(self, t):
        for event in self.candidates.values():
            AccidentStateMachine.transition(event, 'UNCERTAIN', t)
            event.update(state='UNCERTAIN', verified_at=t, evidence_score=0., reason='Source ended before verification completed')
            self.results.append(dict(event))
        self.candidates.clear()
