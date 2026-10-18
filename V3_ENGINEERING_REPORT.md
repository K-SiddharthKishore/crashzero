# CrashZero V3 engineering report
## Implemented archive
The live worker retains JPEG-compressed annotated frames in a bounded in-memory ring. A temporally verified candidate starts a single capture for its analysis run, preserving ten seconds before the event and collecting ten seconds after it. Encoding occurs on a background executor, so detector and tracker work continue. The final browser-playable MP4 uses H.264 when available and MP4V otherwise. Source timestamps are retained in frame_timestamps; the MP4 is sampled for reliable browser playback.

Each record has a daily ID such as CZ-20261018-001. The candidate is written with CAPTURING AFTER EVENT; only the final transaction adds video BLOB bytes and changes the status to EVIDENCE SAVED. Interrupted streams save available footage and set partial-window fields. Restart recovery marks stale in-progress captures interrupted.
## SQLite schema
incidents contains id, created_at, JSON payload, analysis_id, event_type, verification_status, event_time, video clip BLOB plus MIME/size, screenshot BLOB plus MIME/size, and expires_at. Indexed analysis and filter fields support source scope, date, type, and status filtering. The BLOB limit is 30 MiB by default and configurable in SafetyConfig.

Candidate de-duplication applies only inside one analysis ID and cooldown window, so adjacent frames do not create repeated records while a replayed test video can produce a fresh test incident.
## Running and tests
    .venv/bin/python -m streamlit run app.py
    .venv/bin/python -m pytest -q

The V3 archive tests cover ten-second pre/post context, MP4 replay, BLOB persistence across restart, variable timestamps, partial disconnects, same-run deduplication, independent incidents, database failure handling, and bounded clip duration. Existing temporal verifier tests cover normal overtaking, traffic queues, camera motion, stationary road users, and insufficient temporal coverage.
## Measured results and limits
The existing synthetic benchmark measured CPU processing at 19.92, 23.18, and 28.22 FPS across traffic, highway, and mixed-traffic fixtures; MPS measured 27.54, 36.21, and 40.23 FPS. These are processing measurements, not accident-detection accuracy.

No deployment-camera or labelled-dataset accuracy is claimed. CADP and similar datasets must be evaluated separately from deployment CCTV, and false accident alerts per video-hour remains a first-class evaluation metric alongside precision, recall, F1, confusion matrices, and detection delay. This local prototype never calls emergency services; public/cloud operation remains mock-only and REAL_CALLS_ENABLED defaults to false.
