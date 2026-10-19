from dataclasses import dataclass
from pathlib import Path
import numpy as np

from src.calibration import RoadCalibration
from src.digital_twin import DigitalTwin
from src.intelligence_store import IntelligenceStore


@dataclass
class Track:
    id: int
    cls: str
    road_position: list
    road_velocity: list = None


def calibration():
    return RoadCalibration({"image_points": [[0,0],[100,0],[100,100],[0,100]],
                            "road_points": [[0,0],[1,0],[1,1],[0,1]]})


def test_digital_twin_uses_observed_calibrated_positions():
    twin = DigitalTwin(calibration())
    observed = twin.update({7: Track(7, "car", [.2,.3], [1,0])}, 1.0)
    assert observed[0]["id"] == 7 and observed[0]["position"] == [.2,.3]
    image = twin.render(observed)
    assert image.shape == (640,640,3)
    # A later inference result appends an actual trail rather than scripted motion.
    later = twin.update({7: Track(7, "car", [.4,.3], [1,0])}, 1.1)
    assert later[0]["trail"] == [[.2,.3],[.4,.3]]


def test_uncalibrated_twin_does_not_invent_positions():
    twin = DigitalTwin(RoadCalibration({}))
    assert twin.update({1: Track(1, "car", None)}, 0) == []
    assert twin.render([]).mean() < 250  # deliberate unavailable-state annotation


def test_persisted_events_create_real_hotspots_after_restart(tmp_path):
    store = IntelligenceStore(tmp_path)
    event = {"analysis_id": "run", "timestamp": 4.0, "state": "NEAR MISS", "track_ids": [1,2]}
    assert store.save(event, "CAM-1", [.3,.6])
    assert not store.save(event, "CAM-1", [.3,.6])  # same event ID is deduplicated
    restored = IntelligenceStore(tmp_path).hotspots("CAM-1")
    assert len(restored) == 1
    assert restored[0]["count"] == 1 and restored[0]["map_position"] == [.3,.6]
