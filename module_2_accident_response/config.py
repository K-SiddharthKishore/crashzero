"""Configuration owned exclusively by the Accident Response module."""
from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Module2Config:
    root: Path
    db_path: Path
    evidence_dir: Path
    model_path: Path
    temporal_model_path: Path
    pre_event_seconds: float = 10.0
    post_event_seconds: float = 10.0
    likely_threshold: float = 0.72
    minimum_track_observations: int = 6
    suspicion_threshold: float = 0.45
    high_confidence_threshold: float = 0.72

    @classmethod
    def load(cls, root=None, data_dir=None):
        project=Path(root or Path(__file__).resolve().parents[1])
        data=Path(data_dir) if data_dir is not None else Path(os.getenv('CRASHZERO_MODULE2_DATA_DIR',project/'outputs/module2_accident_response'))
        data.mkdir(parents=True,exist_ok=True)
        evidence=data/'evidence'; evidence.mkdir(exist_ok=True)
        return cls(project,data/'module2.sqlite3',evidence,project/'models/yolo11n.pt',
                   project/'models/crash_temporal.pt',
                   suspicion_threshold=float(os.getenv('SUSPICION_THRESHOLD', '0.45')),
                   high_confidence_threshold=float(os.getenv('HIGH_CONFIDENCE_THRESHOLD', '0.72')))
