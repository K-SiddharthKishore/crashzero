"""Image-space prototype thresholds; scores are evidence strength, not probabilities."""
from dataclasses import dataclass, field

@dataclass(frozen=True)
class SafetyConfig:
    detection_confidence: float = .10
    minimum_confidence: float = .30
    minimum_age: float = .6
    motion_window: float = .30
    moving_speed: float = 18.0  # px/s at a maximum 960 px frame width
    stopped_speed: float = 8.0
    deceleration_fraction: float = .65
    heading_degrees: float = 65.0
    observation_gap: float = .5
    verification_seconds: float = 2.0
    stop_seconds: float = .8
    cooldown_seconds: float = 12.0
    spatial_dedup_pixels: float = 100.0
    proximity_scale: float = 1.6
    likely_score: float = .72
    before_seconds: float = 5.0
    after_seconds: float = 5.0
    buffer_fps: float = 10.0
    max_candidates: int = 32
    weights: dict = field(default_factory=lambda: {
        'trajectory_convergence': .15, 'proximity': .10,
        'deceleration_anomaly': .20, 'heading_anomaly': .10,
        'simultaneous_motion_change': .15, 'post_event_stop': .20,
        'temporal_persistence': .10})

SAFETY = SafetyConfig()
