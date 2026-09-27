# CrashZero V2

**Predict Risk Before Impact**

CrashZero watches traffic before, during and after dangerous events — identifying conflict zones, detecting likely accidents and preserving the information needed for faster response.

A local hackathon prototype with exactly three primary screens: **Live Analysis**, **Conflict Zones**, and **Incidents**. No real emergency service is contacted. Evidence scores are configurable heuristics, not calibrated probabilities.

## Run on this Mac

```bash
cd /Users/siddharth/Documents/crashzero
./run.sh
```

Open http://127.0.0.1:8501. If occupied (as it was during development):

```bash
PORT=8502 ./run.sh
```

The existing `.venv` uses Python 3.12.13. No environment replacement or new dependency installation was required. CPU is the tested default; MPS is optional and has not been benchmarked.

For a fresh environment, use the existing `./setup.sh` and pinned `requirements.txt`. Models and real demo assets must be fetched once before offline use:

```bash
.venv/bin/python scripts/fetch_model.py
.venv/bin/python scripts/fetch_demo.py
.venv/bin/python scripts/create_simulations.py
```

Model path: `models/yolo11n.pt`. The local real traffic videos and generated synthetic fixtures work offline once present. Synthetic scenario videos and their scripted detection fixtures are included in V2; regenerating them is optional.

## Use

- **Demo:** select a local real traffic video and Start analysis to run YOLO11n/ByteTrack. Preview alone does not run inference. For a deterministic incident workflow demonstration, choose **Collision · SYNTHETIC TEST** or **Single Bike · SYNTHETIC TEST**. These explicitly bypass detection using scripted tracks, and must not be represented as real crash detection performance.
- **Upload video:** upload MP4/MOV/AVI/MKV, then Start analysis. Files remain local in ignored `outputs/sessions/uploads/`.
- **Webcam:** select Live Camera → Device webcam → device index (usually 0). This is the camera attached to the Python server, not a remote browser's camera.
- **IP/CCTV:** set `CRASHZERO_STREAM_URL` locally, restart the app, then Live Camera → IP / CCTV stream. OpenCV FFmpeg supports RTSP/HTTP where the local backend and camera codec permit it. Never commit credential-bearing URLs.
- **Camera metadata:** configure ID/name/registered location in the gear expander, or set `CRASHZERO_CAMERA_ID`, `CRASHZERO_CAMERA_NAME`, and `CRASHZERO_CAMERA_LOCATION` before launching. Demo/upload sources are explicitly unlocated. GPS is never inferred from images.
- **Stop:** stops processing and finalizes any evidence already being captured. Start becomes available again after finalization.

On this Mac, the hardware probe returned **not authorized to capture video**. In **System Settings → Privacy & Security → Camera**, enable the application launching Python (Terminal or Codex), restart it, and retry. If no permission entry appears, launch `./run.sh` from Terminal and select Device webcam to trigger the system request. Webcam frame capture remains unverified until permission is granted.

## Before / during / after

**Before:** V1 detection, tracking, least-squares motion, closest-approach conflict analysis, deduplicated conflict episodes, and observed-separation near misses remain in use. Conflict Zones bins actual conflict coordinates and displays density on the source camera image. Sessions are separate so different cameras are not merged accidentally. Trends are marked unavailable without comparable observation windows.

**During:** the new `CrashVerifier` collects multiple temporal signals. A pair candidate requires recent convergence, close ground-contact estimates and a motion anomaly. A single-vehicle candidate requires both deceleration and heading change. It then observes about two more seconds; a likely pair collision requires simultaneous deceleration, continued observation and a sustained stop. Overlap alone, zig-zag alone, and disappearing tracks never confirm an accident. Inconclusive candidates become uncertain or normal/near-miss interactions.

**After:** a JPEG rolling buffer retains pre-event frames while temporal verification runs. Likely events create a SQLite incident and simulated internal alert, save an event image, and collect five seconds of post-event footage. An independent encoder writes a browser-playable H.264 clip. Partial windows and encoding failures are explicitly recorded. File offsets and analysis creation times are kept separate; file footage is not given fabricated capture timestamps.

## Architecture

```text
OpenCV file / webcam / stream
  → bounded latest-frame capture queue for live inputs
  → background worker: YOLO11n → ByteTrack → trajectory store
  → V1 conflict + near-miss manager / V2 temporal crash verifier
  → snapshot → Streamlit Live Analysis / Conflict Zones
  → JPEG ring → evidence encoder → SQLite incidents → DemoAlertService
```

- `app.py`: minimal V2 UI; `app_v1.py`: retained V1 interface.
- `src/detector.py`, `src/trajectory.py`, `src/motion.py`: shared vision pipeline.
- `src/conflicts.py`, `src/events.py`, `src/visualization.py`: preserved V1 conflict logic and overlays.
- `src/safety/verifier.py`: temporal candidate/verification state machine.
- `src/video/source.py`, `src/live.py`: source abstraction and worker.
- `src/incidents/manager.py`: evidence buffer, asynchronous clip export, SQLite and demo alerts.
- `src/zones.py`: conflict-coordinate bins.
- `config/settings.py`: preserved V1 motion/conflict settings.
- `config/v2.py`, `config/bytetrack-v2.yaml`: V2 thresholds/weights and tracking configuration.

## Storage and troubleshooting

Incidents and media: `outputs/incidents/`; session zones: `outputs/live/`; legacy analysis: `outputs/demo/` and `outputs/sessions/`. All new captured evidence and local configuration are Git-ignored. No automatic evidence deletion or external upload occurs. Disk usage should be checked before a long capture session.

Missing model: run the model fetch script once online. Invalid files, model/tracker failures and camera disconnects become short UI messages. The CPU option is the fallback for device/inference issues. After a disconnected stream, check connectivity and restart analysis. Nothing attempts to guess stream credentials or precise camera location.

If clip encoding fails, images and the incident survive with a failure status. If the source ends early, before/after windows are labeled partial. A browser disconnect stops an abandoned worker after about 120 seconds without UI polling.

## V1 preservation and rollback

The initial application had eight navigation pages, historical NYC crash analysis, a trained historical injury-context model, offline YOLO11n/ByteTrack video processing, trajectory conflicts, CSV/SQLite exports and heatmaps. These modules were retained. V2 removes historical/forecast pages from primary navigation; the original interface is available through:

```bash
.venv/bin/python -m streamlit run app_v1.py --server.address 127.0.0.1 --server.port 8503
```

That interface shares current vision modules. For the exact pre-upgrade application, stop V2 and switch to the checkpoint branch (first preserve any new working edits):

```bash
git switch crashzero-v1-fallback
PORT=8503 ./run.sh
```

Checkpoint: `d8354ba` (`checkpoint: CrashZero V1 before V2 upgrade`). V2 branch: `crashzero-v2`. Local model/video assets remain present when switching branches. The original guide is [README_V1.md](README_V1.md).

## Validation and demo

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/benchmark_tracking.py
```

See [HACKATHON_DEMO.md](HACKATHON_DEMO.md) for the presentation sequence, [TECHNICAL_NOTES.md](TECHNICAL_NOTES.md) for exact algorithms, and [LIMITATIONS.md](LIMITATIONS.md) for honest scope. No real-world collision accuracy percentage is claimed. This is not a validated emergency detection system.

Detailed measured results and remaining validation gaps: [VALIDATION.md](VALIDATION.md). The existing hosted entry point `cloud/app.py` remains a read-only V1 demo via `app_v1.py`; V2 camera/evidence workflows run locally.

For **V2 Community Cloud deployment**, use `cloud/v2/app.py` (Python 3.12), not the legacy `cloud/app.py`. This hosted mode supports uploads/demos, CPU inference, first-use model download and separate temporary storage for each browser session. See [cloud/v2/README.md](cloud/v2/README.md). Physical device cameras remain local-only; actual cloud build/performance still require deployment validation.
