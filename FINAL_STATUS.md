# CRASHZERO STATUS

Local URL: http://localhost:8501
Public URL: Not deployed — awaiting GitHub sign-in and Streamlit authorization.
Run command: `./run.sh` from this directory.

## Working features

- Eight styled Streamlit views, local upload and fresh YOLO11n / ByteTrack processing.
- Anonymous IDs, observed trails, 2.5-second projected paths and simultaneous closest-approach scoring.
- Deduplicated interaction episodes; conservative near-miss resolution; unresolved/review states.
- Playable H.264 output, image-space heatmap, event CSV, track CSV, analytics JSON and SQLite records.
- Three offline traffic clips and cached primary demo.
- 91,316 official NYC 2024 crash records; historical filters, charts and geographic plots.
- Temporally evaluated Random Forest injury-context model and hourly scenario timeline.
- Transparent missing-source fusion; unrelated camera and NYC history are not combined.
- Saved local session restoration, source attribution, README and 22 judge questions.

## Verification

25 automated tests passed. All eight pages passed a clean-start smoke test after stopping the server and restarting with `./run.sh`. Fresh demo inference also passed after restart. Browser upload, fresh processing and annotated video playback were verified. Real YOLO detected 16 objects on the first city frame and zero on a black frame. Package dependency checks passed.

Primary cached demo: 15.83 seconds, 190 frames at 12 sampled FPS; 63 temporary track IDs, 16 high-risk episodes, peak score 75, clip index 64.1. Approximately 23 inference FPS on CPU in the measured run; throughput varies. **Zero prototype near misses and zero critical episodes** qualified in this clip. These counts have not been inflated.

## Demo steps

1. Run `./run.sh` and open the local URL.
2. Open Live CCTV and play the cached video. Click Analyze video for fresh inference.
3. Inspect Near Misses and Risk Hotspots; explain review/unresolved states.
4. Show Historical Analysis, City Risk and Future Prediction. Identify NYC geography and the conditional-injury target.

## Datasets

NYPD Motor Vehicle Collisions — Crashes, NYC Open Data, full 2024. Real public data, demonstration use, not Bengaluru. Primary video: Richard L / Pexels, “Busy City Intersection with Traffic and Pedestrians,” tagged Singapore; exact camera location unverified. Additional Pexels clips demonstrate highway traffic and motorcycles. See DATA_SOURCES.md and data/manifest.json.

## Known limitations

Image-space conflicts are unvalidated and can arise from perspective, occlusion, camera motion or tracking errors. No metric speed, collision confirmation, connected city CCTV feed or prospective crash forecast is claimed. The injury model's temporal AUC is 0.6028. Unknown local history prevents confirmed emerging geographic hotspots. Optional street tiles need internet; the default geographic plot works offline. MPS is optional; CPU is the verified inference path.

## Backup demo

`outputs/demo_processed.mp4`; matching `outputs/demo/analytics.json`, `events.csv`, `tracks.csv`, `preview.jpg` and `heatmap.jpg`.

## Hosting

Streamlit Community Cloud was investigated only after local verification. Its prepared entrypoint is `cloud/app.py` with lightweight adjacent requirements; hosted mode disables uploads and new inference. The deployment retry on 2026-09-26 reached GitHub's sign-in page for Streamlit. User authentication/OAuth is required. No public URL exists yet. See HOSTING.md.

## Important files

`app.py`, `run.sh`, `README.md`, `HACKATHON_NOTES.md`, `DATA_SOURCES.md`, `HOSTING.md`, `config/settings.py`, `src/`, `tests/`, `models/model_metrics.json`, `cloud/app.py`.

CrashZero is a hackathon research prototype. Its risk estimates are not certified collision predictions and should not be used as a standalone traffic-control or safety system.
