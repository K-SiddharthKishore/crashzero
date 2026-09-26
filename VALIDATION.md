# Validation record — 2026-09-26

## Baseline

- V1 tests before edits: **25 passed**.
- Existing server successfully launched on 127.0.0.1:8502; 8501 was already occupied.
- Fresh real-video V1 smoke: three seconds / 36 analyzed frames, 25 tracked IDs, zero near misses, ~13.27 processed FPS on CPU. Counts are algorithm output, not labeled vehicle truth.
- V1 checkpoint `d8354ba`, branch `crashzero-v1-fallback`.

## V2 automated coverage

Final suite: **45 passed**. Includes the retained V1 dashboard/core/integration tests, all three V2 screens, and a populated incident detail rendered from an end-to-end generated record.

Tests cover normal motion, overlapping boxes without collision, different-time trajectory crossings, observed-separation near misses, legal turns, normal stops, multi-vehicle stop collision fixture, single-bike turn/deceleration/stop fixture, track disappearance, impossible jumps, temporal delay, deduplication, corrupt files, empty detections, SQLite persistence, before/event/after screenshots, H.264 decoding, complete and truncated evidence windows, stopping/releasing a file source, stream scheme validation, and the bounded latest-frame queue with a mocked device.

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/evaluate_safety.py
```

Synthetic scenario evaluation (12 seconds at 12 FPS each, scripted detections bypass YOLO):

| Scenario | Likely accident records | Prototype near misses |
|---|---:|---:|
| Normal | 0 | 0 |
| Perspective overlap | 0 | 0 |
| Near miss with avoidance | 0 | 1 |
| Collision | 1 | 0 |
| Legal turn | 0 | 0 |
| Normal stop | 0 | 0 |
| Single-bike abnormal turn and stop | 1 | 0 |

Within these **synthetic fixtures only**: 2 positive scenarios detected, 0 false-positive scenarios, 0 missed positive scenarios. This is an engineering regression result, **not real-world accuracy**. There is no labeled accident-video evaluation set.

## Real video smoke

The real `traffic.mp4` source completed through the V2 worker to source timestamp 15.75s. There were **zero likely-accident incidents**. Motion candidates resolved to normal interactions after verification. Observed throughput in that run was about **17.1 processed FPS** (unpaced CPU run including analysis and rendering). This short clip is not a collision validation dataset.

## ByteTrack comparison

Same first eight seconds of `traffic.mp4`, 96 frames at the application analysis rate, CPU after model warmup:

| Diagnostic | V1 settings | V2 settings |
|---|---:|---:|
| Unique track IDs | 41 | 31 |
| IDs with fewer than 3 observations | 7 | 3 |
| Median observations per ID | 16 | 24 |
| Measured tracker/detector throughput | 31.65 FPS | 27.55 FPS |

Fewer short tracks is encouraging, but fewer IDs can also mean missed weak actors. No labeled identity comparison exists; no ID-switch, IDF1, MOTA or tracking-accuracy improvement is claimed. Throughput is a single-run diagnostic, sensitive to warmup and machine load. V1/V2 annotated frame outputs were inspected. Reproduce with `scripts/benchmark_tracking.py`; output goes to `outputs/tracking_benchmark.json` and tracking preview images.

## Browser checks

- Opened the actual running Streamlit app and exercised source selection / Start / automatic completion.
- Ran the synthetic collision fixture through the UI and saw a likely collision.
- Opened persisted incident review with three images, evidence signals, source label, location-not-configured text and simulated alert status.
- Browser media element reported **10.1s duration, readyState 4, no decode error** for the saved clip.
- Opened Conflict Zones and verified the saved session and zone detail entry.
- Fixed an incident camera-name schema mismatch discovered during browser review and added a populated-incident UI regression.

## Hardware and scope gaps

- Webcam probe: OpenCV reported **not authorized to capture video**. No webcam-frame success claim. macOS permission is required from the user.
- No physical RTSP camera available; actual stream connectivity/latency is unverified.
- PyTorch 2.14.0 reports MPS available, but V2 validation used CPU; MPS is not benchmarked.
- OpenCV 5.0.0, Streamlit 1.64.0, Ultralytics 8.4.163, Python 3.12.13.
- No trained temporal crash classifier, road-plane calibration or real emergency integration.
