# CrashZero V2 — implementation facts

## V1 inspection and protection

Repository inspected before changes: Streamlit `app.py`, `assets/style.css`, Python modules in `src/`, configuration, requirements/lock file, tests, local model/data assets and persisted demo outputs. V1 had an eight-page UI, NYC historical crash analysis and injury-context model, batch traffic video processing, trajectory prediction, conflict episodes and spatial heatmaps. There was no accident classifier or live-camera capture abstraction.

V1's 25 tests passed. The server launched on 8502 because 8501 was occupied. A real inference smoke processed 36 frames / three seconds, produced 25 track IDs, no near misses, and approximately 13.27 processed FPS on CPU. This ID count is not the count of independently verified vehicles. Current user edits were checkpointed at `d8354ba`; fallback branch `crashzero-v1-fallback` was created before implementation. No model weights, stream passwords, captured camera recordings or API credentials were committed.

## Detector and tracker

- Exact detector: local `models/yolo11n.pt`, Ultralytics **YOLO11n**, COCO classes 0/1/2/3/5/7: person, bicycle, car, motorcycle, bus, truck.
- Library: **ultralytics 8.4.163**, existing environment; inference image size 640, processed video width at most 960.
- Exact tracker: Ultralytics **ByteTrack** through persistent `model.track`, not DeepSORT or BoT-SORT. Each analysis owns a fresh detector/tracker instance.
- V1 used bundled `bytetrack.yaml`, detector confidence .20. V2 uses local `config/bytetrack-v2.yaml`: high .25, low .10, new-track .35, lost-track buffer 45, association match .8, fused scores enabled; detector confidence .10 permits second-pass weak detections.
- Candidate analysis requires detection confidence ≥.30 and an established trajectory. Stronger new-track confidence discourages noisy IDs; longer lost-track retention supports brief occlusion. These changes can also suppress small/weak actors and prolong an incorrect identity, so they are not an unconditional accuracy improvement.
- `scripts/benchmark_tracking.py` compares equal decoded frames, CPU after model warmup, V1 vs V2 settings. It records short-track counts and observations per ID, not labeled ID switches, MOTA or IDF1. See `outputs/tracking_benchmark.json` after running it. Frame annotations are saved for visual inspection.

## Trajectories

Bottom-center is the image-space road-contact proxy. Per-ID timestamped raw observations are retained for 1.2 seconds (bounded to 120 observations). A two-dimensional least-squares line estimates velocity and current position; residuals produce a fit-stability indicator. At least five observations and .4 seconds are needed for V1 conflict readiness; V2 candidate motion analysis requires .6 seconds. A gap above .5 seconds resets motion readiness; old tracks expire after two seconds. Implausible jumps reset trajectory history rather than becoming impact evidence. Displayed trails use fitted positions; raw histories remain available in the model. Boxes still come from the tracker and can jitter.

Long-window velocity is appropriate for convergence but can hide a sudden stop. The verifier separately uses a .30-second endpoint-displacement velocity, compares heading against a .4-second-old velocity, and detects a ≥65% speed drop from a recent decaying peak above 18 px/s. Below 8 px/s counts as stationary. A heading change of ≥65 degrees requires moving-speed evidence. All units are image pixels/seconds at the processing scale; none are real-world speed or distance.

## V1 conflict and near-miss logic

For every stable ready pair, compute relative position and velocity; project the time of closest approach in a 2.5-second horizon. Only approaching pairs with sufficiently close predicted separation enter the interaction score. Factors include projected time/separation, convergence, stability/confidence, and vulnerable road-user class. High score begins at 61, critical at 81.

`EventManager` deduplicates high-risk pair episodes. A prototype near miss requires observed separation and clearance sustained for .5 seconds. Overlapping image boxes yield `overlap / review`, not a confirmed collision or near miss. Lost tracks and unfinished episodes stay unresolved. Cooldown is three seconds for V1 conflict episodes.

## V2 candidate and temporal verification

Stage 1:

- Pair: recent high-risk convergence within 1.5 seconds, current proximity relative to estimated footprints, and at least one abrupt speed or heading change.
- Single vehicle: heading anomaly plus deceleration close in time. Pedestrians are excluded from the single-vehicle detector. No detector supplies vehicle orientation, rollover or physical contact evidence.

Stage 2 observes at least two seconds after the candidate. A likely pair collision requires **all** of: both actors decelerating near the candidate time, observed convergence/proximity, at least one sustained .8-second stop, at least five verification observations, ≥85% temporal coverage, and no observation gap above .5 seconds. A likely single event requires deceleration, heading anomaly and sustained stop under the same continuity gates. Missing tracks are uncertainty, never a post-event stop.

Pair weights: convergence .15, proximity .10, deceleration .20, heading .10, simultaneous change .15, post-stop .20, persistence .10. Single weights: deceleration .30, heading .20, post-stop .30, persistence .20. The threshold is .72 **and** the required gates; a score alone cannot confirm an event. These weights prioritize observed motion changes and aftermath. They are unvalidated prototype defaults, not learned probabilities. Configurable values live in `config/v2.py`.

States: monitoring → possible accident / verifying → likely collision, likely single-vehicle accident, near miss, normal interaction, or uncertain. Candidates unfinished at source end become uncertain. Near-miss results from this verifier are explanatory; counted V1 near-miss episodes still require V1's observed-clearance test. Only likely states create incidents. Deduplication covers overlapping track IDs or a nearby image-space location for 12 seconds within a session; replaying a file creates a new analysis session and may create a new record.

## Evidence and alerts

JPEG frames are sampled at up to 10 FPS and kept for five seconds plus the verification window and one-second margin. Event screenshots are the buffered frame nearest the candidate time. Five additional seconds are collected after that time. Variable input timings are resampled to constant-rate video before H.264 export via the installed imageio-ffmpeg binary. A separate one-worker encoding executor keeps ffmpeg off the inference loop. Images, before/after frames, clip paths and partial/failure status are persisted in `outputs/incidents/incidents.sqlite`.

Records include anonymous tracks/classes, camera metadata, source offset, observed capture clock for live sources, creation timestamp, evidence signals/score, verification state, screenshot/clip paths and simulated alert status. An uploaded recording's original filming date is unknown and is not fabricated. `DemoAlertService` only constructs a local alert record; no network request, ambulance/police call, or webhook delivery exists.

## Live input and performance

`VideoFileSource`, `WebcamSource`, `StreamSource` use OpenCV. Live sources have a dedicated capture thread and a one-item latest-frame queue so inference discards stale input rather than building a growing backlog. Files are sampled near 12 FPS and played on their source clock; processing slows if inference cannot keep up. The worker and UI communicate through locked snapshots. UI polling is .5 seconds; evidence export has its own executor. Source wall-clock/source-frame timestamps, not inference duration, drive motion calculations.

Device camera permission was denied on this machine during testing. IP camera support is implemented with bounded FFmpeg connection/read timeouts but has not been validated against a physical RTSP camera. Stream URLs come only from `CRASHZERO_STREAM_URL` and are excluded from saved camera metadata and UI error strings. Errors are brief messages; recovery is restart after fixing the source.

## Conflict Zones

Preserves V1 Gaussian-smoothed conflict density over the camera image. V2 additionally groups deduplicated conflict coordinates in 120px square bins. Three or more events marks a repeated high-risk bin; lower counts are moderate evidence. Expand a zone for timestamps, pair types, scores, coordinates and status. This is image-space conflict concentration, not a geographic accident rate. Sessions stay separate; no fabricated trend is shown.

## Scope deliberately deferred

No temporal neural accident classifier, model retraining, homography/calibration editor, lane/corridor model, orientation/spin detector, appearance re-identification, real emergency integration, face recognition or plate identification. The V1 historical prediction model remains a separate historical injury-context model; it is not an accident video classifier.
