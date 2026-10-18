"""V3 incident archive tests use synthetic frames only."""
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np

from config.v2 import SAFETY
from src.incidents.manager import EvidenceBuffer, IncidentStore
from src.video.source import Camera
from src.video_processor import probe


def _event(timestamp, state="LIKELY_ACCIDENT"):
    return {"timestamp": timestamp, "state": state, "track_ids": [4, 9],
            "road_users": ["car", "car"], "evidence_score": .82,
            "evidence_signals": {"trajectory_convergence": True, "post_event_stop": True}}


def _capture(tmp_path, timestamps, event_time=11.0, analysis_id="run-a"):
    cfg = replace(SAFETY, buffer_fps=10.0, incident_blob_max_bytes=8 * 1024 * 1024)
    store = IncidentStore(tmp_path / "incidents", config=cfg)
    buffer = EvidenceBuffer(Camera(), store, config=cfg, analysis_id=analysis_id, source_kind="SYNTHETIC TEST")
    frame = np.full((80, 120, 3), 100, np.uint8)
    for t in timestamps:
        frame[:, :, 0] = int(t * 10) % 255
        buffer.add(t, frame, {"tracks": []})
        if abs(t - event_time) < .001:
            buffer.trigger(_event(event_time))
    buffer.close()
    return store, buffer


def test_ten_second_context_is_blob_backed_and_playable(tmp_path):
    store, _ = _capture(tmp_path, [round(i * .2, 2) for i in range(111)])
    record = store.list()[0]
    assert record["clip_start"] <= 1.2
    assert record["clip_end"] >= 21.0
    assert not record["pre_event_truncated"] and not record["post_event_truncated"]
    clip = store.get_clip(record["incident_id"])
    assert clip and b"ftyp" in clip[:32]
    replay = tmp_path / "replay.mp4"; replay.write_bytes(clip)
    assert probe(replay)["frames"] >= 95
    screenshot = store.get_screenshot(record["incident_id"])
    assert screenshot and cv2.imdecode(np.frombuffer(screenshot, np.uint8), cv2.IMREAD_COLOR) is not None


def test_variable_timestamps_are_preserved_in_metadata(tmp_path):
    times = [0, .11, .42, .61, 1.05, 1.23, 2.0, 3.7, 5.3, 7.2, 9.4, 11.0,
             11.13, 12.8, 14.1, 16.9, 18.0, 20.6, 21.2]
    store, _ = _capture(tmp_path, times)
    record = store.list()[0]
    # Only the requested pre/post window is retained, with each original
    # variable source timestamp represented exactly.
    assert record["frame_timestamps"] == [t for t in times if t >= 1.0]


def test_disconnect_creates_explicit_partial_clip(tmp_path):
    store, _ = _capture(tmp_path, [round(i * .2, 2) for i in range(56)])
    record = store.list()[0]
    assert record["post_event_truncated"]
    assert store.get_clip(record["incident_id"])


def test_clip_and_screenshot_survive_store_restart(tmp_path):
    store, _ = _capture(tmp_path, [round(i * .2, 2) for i in range(111)])
    incident_id = store.list()[0]["incident_id"]
    restarted = IncidentStore(tmp_path / "incidents")
    assert restarted.get_clip(incident_id)
    assert restarted.get_screenshot(incident_id)


def test_same_run_duplicate_is_suppressed_but_replay_is_not(tmp_path):
    cfg = replace(SAFETY, incident_blob_max_bytes=8 * 1024 * 1024)
    store = IncidentStore(tmp_path / "incidents", config=cfg)
    frame = np.zeros((40, 60, 3), np.uint8)
    first = EvidenceBuffer(Camera(), store, config=cfg, analysis_id="same")
    for t in np.arange(0, 12.1, .2):
        first.add(float(t), frame)
    assert first.trigger(_event(11)) is not None
    assert first.trigger(_event(11.1)) is None
    first.close()
    replay = EvidenceBuffer(Camera(), store, config=cfg, analysis_id="replayed")
    for t in np.arange(0, 12.1, .2):
        replay.add(float(t), frame)
    assert replay.trigger(_event(11)) is not None
    replay.close()
    assert len(store.list()) == 2


def test_independent_incidents_are_not_merged(tmp_path):
    cfg = replace(SAFETY, before_seconds=1.0, after_seconds=1.0, incident_blob_max_bytes=8 * 1024 * 1024)
    store = IncidentStore(tmp_path / "incidents", config=cfg)
    frame = np.zeros((40, 60, 3), np.uint8)
    buffer = EvidenceBuffer(Camera(), store, config=cfg, analysis_id="one-run")
    for t in np.arange(0, 30, .2):
        buffer.add(float(t), frame)
        if abs(t - 3) < .01: buffer.trigger(_event(3))
        if abs(t - 20) < .01: buffer.trigger(_event(20))
    buffer.close()
    assert len(store.list()) == 2


def test_database_failure_does_not_crash_monitoring(tmp_path, monkeypatch):
    cfg = replace(SAFETY, incident_blob_max_bytes=8 * 1024 * 1024)
    store = IncidentStore(tmp_path / "incidents", config=cfg)
    buffer = EvidenceBuffer(Camera(), store, config=cfg, analysis_id="failure")
    frame = np.zeros((40, 60, 3), np.uint8)
    for t in np.arange(0, 12, .2):
        buffer.add(float(t), frame)
    def fail(*args, **kwargs):
        raise OSError("disk unavailable")
    monkeypatch.setattr(store, "save", fail)
    assert buffer.trigger(_event(11)) is None
    assert "not saved" in buffer.last_error
    buffer.close()


def test_no_full_source_is_persisted(tmp_path):
    store, _ = _capture(tmp_path, [round(i * .2, 2) for i in range(111)])
    record = store.list()[0]
    assert len(store.get_clip(record["incident_id"])) <= SAFETY.incident_blob_max_bytes
    assert record["clip_end"] - record["clip_start"] <= 21.1
