"""Explainable, high-recall candidates from temporal model windows."""
import os


def suspicion_threshold(original):
    value = float(os.getenv('SUSPICION_THRESHOLD', '0.45'))
    return max(0.0, min(float(original), value))


def group_candidates(scores, original_threshold, threshold, cooldown=3.0,
                     verification_threshold=None):
    """Group adjacent score crossings without bridging a quiet interval.

    Temporal windows are sampled once per second. A three-second cooldown may
    suppress nearby duplicate events, but must not merge an early false alarm
    with a later impact and then choose the early frame for both.
    """
    ordered = sorted((s for s in scores if s['score'] >= threshold),
                     key=lambda s: s['timestamp'])
    groups = []
    for item in ordered:
        if groups and item['timestamp'] - groups[-1]['last_timestamp'] <= min(cooldown, 1.5):
            group = groups[-1]
            group['last_timestamp'] = item['timestamp']
            if item['score'] > group['score']:
                group['peak_timestamp'], group['score'] = item['timestamp'], item['score']
            group['windows'].append(item)
        else:
            groups.append({'timestamp': item['timestamp'], 'peak_timestamp': item['timestamp'],
                           'last_timestamp': item['timestamp'],
                           'score': item['score'], 'original_detected': False, 'windows': [item],
                           'reason': 'Temporal accident prediction crossed the suspicion threshold'})
    for group in groups:
        crossings = [s for s in group.pop('windows') if s['score'] >= original_threshold
                     and (verification_threshold is None or
                          s.get('verification_score', 0) >= verification_threshold)]
        group['original_detected'] = any(
            second['timestamp'] - first['timestamp'] <= 2.01
            for first, second in zip(crossings, crossings[1:]))
    return groups
