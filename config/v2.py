"""Image-space prototype thresholds; scores are evidence strength, not probabilities."""
from dataclasses import dataclass, field
import os

def _env_int(name, default):
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default

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
    heading_window: float = .4
    peak_speed_decay: float = .96
    convergence_memory: float = 1.5
    recent_motion_seconds: float = .7
    event_deceleration_seconds: float = .8
    event_heading_seconds: float = 1.0
    minimum_coverage: float = .85
    minimum_verification_observations: int = 5
    minimum_display_observations: int = 3
    observation_gap: float = .5
    verification_seconds: float = 2.0
    stop_seconds: float = .8
    cooldown_seconds: float = 12.0
    spatial_dedup_pixels: float = 100.0
    proximity_scale: float = 1.6
    likely_score: float = .72
    # Event evidence is intentionally bounded: retain a short context window,
    # never the source stream.  Values can be overridden for a deployment by
    # constructing SafetyConfig, which also keeps synthetic tests fast.
    before_seconds: float = 10.0
    after_seconds: float = 10.0
    buffer_fps: float = 10.0
    incident_blob_max_bytes: int = field(default_factory=lambda: _env_int('INCIDENT_BLOB_MAX_BYTES', 30 * 1024 * 1024))
    # -1 keeps evidence until an operator configures a retention policy.
    incident_retention_days: int = field(default_factory=lambda: _env_int('INCIDENT_RETENTION_DAYS', -1))
    incident_max_records: int = field(default_factory=lambda: _env_int('INCIDENT_MAX_RECORDS', 1000))
    max_candidates: int = 32
    weights: dict = field(default_factory=lambda: {
        'trajectory_convergence': .15, 'proximity': .10,
        'deceleration_anomaly': .20, 'heading_anomaly': .10,
        'simultaneous_motion_change': .15, 'post_event_stop': .20,
        'temporal_persistence': .10})

SAFETY = SafetyConfig()
