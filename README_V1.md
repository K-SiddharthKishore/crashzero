# CRASHZERO
### Predict Risk Before Impact

> We don't want a crash to be the first data point telling us that an intersection is dangerous.

CrashZero is a local, offline-capable road-safety prototype for an Apple Silicon Mac. It brings together **past crash evidence**, **present traffic trajectories**, and **context-dependent injury estimates**. It helps demonstrate how dangerous interactions can motivate investigation before a crash history accumulates.

## Start the demo

From this project directory:

```bash
./run.sh
```

Open **http://localhost:8501**. Stop with Ctrl+C. Run the same command to restart. The installed Python 3.12 virtual environment, model weights, dataset, demo footage and preprocessed results are already local. No login or internet is needed for the default demo. The optional street basemap needs internet; the default geographic plot does not.

1. **Overview**: camera evidence and separate NYC context.
2. **Live CCTV**: cached playback immediately; click **Analyze video** to run fresh YOLO inference.
3. **Near Misses**: inspect resolved candidates, overlap/review and unresolved episodes.
4. **Risk Hotspots**: camera-space conflict density and interaction types.
5. **Historical Analysis / City Risk**: filter authentic NYC crash data.
6. **Future Prediction**: choose borough, day and vehicle context, inspect timeline and model evaluation.

Backup: open `outputs/demo_processed.mp4` in any video player. `outputs/demo/analytics.json`, `events.csv`, `tracks.csv`, `preview.jpg` and `heatmap.jpg` contain the matching cached analysis. No warnings or events are inserted into the video manually.

## Features and architecture

```text
Local MP4/MOV/AVI → YOLO11n → ByteTrack → bounded trajectory history
  → least-squares velocity (pixels/second) → 2.5-second motion projection
  → simultaneous closest approach → risk index → deduplicated episodes
  → H.264 annotated video + heatmap + CSV + JSON + SQLite

NYC police-reported crashes → cleaning + geospatial validation → patterns
  → temporal train/test split → Random Forest conditional-injury model
  → hourly scenario estimates → transparent available-source fusion
```

Eight Streamlit views provide interactive geographic plots, severity and time filters, historical charts, conditional-injury timelines, local uploads, cached and fresh inference, exports, explanations, event records and camera-space hotspots. Dark styling is local; no external font dependency. Empty histories, empty filtered results, videos with no detections, missing source components and invalid videos have explicit states.

## AI / ML and measurement

**YOLO11n** is a pretrained Ultralytics COCO detector. Retained classes are person, bicycle, car, motorcycle, bus and truck. **ByteTrack** associates boxes into anonymous per-session IDs. Classes and IDs may fragment or switch; unique IDs are not a reliable physical traffic census.

Bottom-center observations are fitted against **source video timestamps**, using up to 1.2 seconds / 40 observations. Five observations and at least 0.4 seconds are required before forecasting. Tracks reset after a gap >0.5 seconds and stale histories are removed. Linear velocity yields a 2.5-second projection. Solid lines are observed trails; cyan dashed lines are projections. No km/h, metre or calibrated speed is reported.

For each converging pair, let relative position be `r` and relative velocity `v`. Closest-approach time is `clip(-r·v / |v|², 0, 2.5)`, with separation `|r+v*t|`. This is the continuous-time minimum of the constant-velocity model, not infinite-line intersection. Parallel, separating, distant, poorly fitted and minimally converging pairs are excluded. The time displayed is **estimated time to minimum image-space separation**, not certified TTC.

Combined image footprint = sum of `max(7 px, .42 × min(box width, box height))`.

```text
proximity = clip(1 - minimum separation / (1.4 × combined footprint), 0, 1)
urgency = clip(1 - time to closest approach / 2.5, 0, 1)
convergence = clip(approach speed / combined footprint, 0, 1)
confidence = minimum trajectory stability × capped minimum detector confidence
pair score = round(100 × (.40 proximity + .30 urgency + .20 convergence
                         + .10 vulnerable-user flag) × (.55 + .45 confidence))
```

All scores are deterministic heuristic indices, **not calibrated crash probabilities**. Thresholds are centralized in `config/settings.py`: 0–30 LOW, 31–60 MODERATE, 61–80 HIGH, 81–100 CRITICAL. The live clip index is the 90th percentile of frame maximum pair scores; the peak and final-frame scores are shown separately.

**Near-miss logic:** an episode starts at score ≥61. Its peak, minimum predicted separation time, classes and location are retained. It becomes a **prototype near miss** only after both tracks visibly separate beyond 1.5 combined footprints for ≥0.5 seconds without any observed bounding-box overlap during the episode. Overlap produces **overlap / review**, not a crash declaration. Lost tracks and the end of a clip are **unresolved**. A 3-second pair cooldown prevents repeated counts. This conservative test cannot rule out unseen physical contact. Video is a source for human review, not near-miss ground truth.

The heatmap places **one point per high-risk episode** at its peak-risk location and applies a 25-pixel Gaussian blur. It does not count every frame as an independent conflict. Projected locations outside the image remain in event exports but are excluded from the heatmap.

## Historical dataset

**REAL PUBLIC DATA · Prototype / demonstration dataset**

- Dataset: NYPD Motor Vehicle Collisions — Crashes, NYC Open Data.
- Geography: **New York City, USA. Not Bengaluru.**
- Period: full 2024 calendar year, queried on 2026-09-25.
- Records: **91,316** unique crashes; **83,692** coordinates within the configured NYC extent.
- Fields: ID, date, time, borough, coordinates, injury/fatality counts, pedestrian/cyclist injuries, vehicle types, contributing factor, street.
- Source: https://data.cityofnewyork.us/Public-Safety/Motor-Vehicle-Collisions-Crashes/h9gi-nx95
- API and exact query: `data/historical/source.json`.
- Official API documentation: https://dev.socrata.com/foundry/data.cityofnewyork.us/h9gi-nx95
- Access terms: https://opendata.cityofnewyork.us/overview/#termsofuse

A short search found Bengaluru aggregate/FIR and collision-warning resources, but no quickly verified, directly usable accident table with the required date/time/location provenance. This build prioritizes the official NYC source over unverified India records. Missing coordinates are excluded only from maps, not silently removed from all analysis. The dataset can change on subsequent retrievals.

No traffic exposure denominators or non-crash controls exist. Counts are **concentrations of reported incidents**, not danger per trip. Weather, lighting, surface and junction fields are unavailable. No conditions are synthesized. The map's density index is `100 × log(1+cell count)/log(1+maximum cell count)` on 0.01-degree cells. Borough historical index is count divided by the largest borough count ×100. Neither is an exposure-adjusted risk rate.

## Predictive model

A lightweight Random Forest predicts **any injury/fatality given a reported crash** from borough, hour, weekday and primary vehicle type. Injury counts, severity and post-crash contributing factors are not inputs. Jan–Sep 2024 is training (68,546 rows); Oct–Dec is a held-out temporal test (22,770). Fixed seed 42, 100 trees, max depth 10, minimum leaf 40. Stored model: `models/injury_model.joblib`; evaluation: `models/model_metrics.json`.

Measured ROC AUC **0.6028**; Brier score **0.2356**, versus prevalence-only baseline **0.2482** (lower is better). These are modest results, not evidence of precise accident prediction. No independent camera, city or prospective validation has been performed. No probability calibration is claimed. Timeline categories apply to the conditional-injury index, not likelihood of a crash happening at that hour. Context counts and observed injury share are descriptive explanations, not causal attribution. Rare/unseen combinations have weak support.

## Fusion and emerging hotspots

Default source weights: historical .25, predictive .30, live .45. Missing inputs are excluded and remaining weights renormalized. Zero weights produce an unavailable index rather than division by zero. Future Prediction exposes weight controls. The index mixes different signals for prioritization; it is not a probability.

**The footage's geography is unverified, so its live score is never silently fused with NYC history.** Camera Overview uses live only; NYC Overview uses historical + predictive context. The fusion engine supports all three when valid co-located data exists. Emerging logic requires verified local historical index ≤30, ≥3 distinct conflict episodes and increasing high-pair density between clip halves. With unknown historical coverage, only a **live conflict cluster** may be reported. No fabricated geographic emerging-hotspot marker is displayed.

## Installation / recreation

Already installed on this Mac. For a clean Python 3.12 machine:

```bash
./setup.sh
.venv/bin/python scripts/process_demo.py
./run.sh
```

Setup requires internet for packages, public data and weights. `requirements.txt` pins direct dependencies; `requirements-lock.txt` records the tested Mac environment. The setup script does not change unrelated projects or install system packages. FFmpeg encoding uses the binary bundled by imageio-ffmpeg. CPU is the verified default; optional MPS is available in the interface. Inference is resolution-limited to 960 pixels and model input 640, with bounded processing duration and trajectories.

To train again, remove only `models/injury_model.joblib` and open Future Prediction, or call `src.prediction.train(load_history())` locally. Do not load untrusted joblib/PT files.

## Testing

```bash
.venv/bin/python -m pytest -q
```

Analytic synthetic fixtures test simultaneous vs asynchronous crossing, parallel motion, source-time velocity, track gaps, near-miss deduplication, observed-overlap rejection, lost tracks, thresholds, missing-source fusion and emerging criteria. These test fixtures are **never presented as observed events**. Integration tests cover invalid/empty videos, no detections, playable output, CSV/JSON exports, real data and deterministic model inference. Streamlit AppTest exercises all eight views and map variants. Browser checks cover actual rendering, upload and playback. See `FINAL_STATUS.md` for the final verification record.

## Privacy

No face recognition, identity inference or plate reading is implemented. Uploads, tracks, events and outputs stay on this Mac unless you deliberately deploy or share them. Raw footage may itself contain identifiable people or plates. Delete specific `outputs/sessions` folders to remove uploads; `outputs/events.sqlite` stores per-session event JSON. The app does not contact external inference APIs. Optional map tiles contact CARTO. Streamlit usage collection is disabled.

## Limits / future scope

Constant velocity does not anticipate turns, braking or evasive behavior. Uncalibrated perspective can create false conflicts, particularly across depth-separated lanes; moving cameras violate the motion assumptions. The detector may miss small aerial road users and double-detect riders as people plus motorcycles. No frame-level annotations establish precision/recall. Clip-level 90th percentile can understate rare peaks, which are shown separately. Uploaded files are capped at 200 MB and analysis at 120 seconds. Audio is removed. MOV/AVI support depends on their codecs. The app is intended for one local user, not concurrent city operations.

Future architecture only: camera calibration; ground-plane trajectories; lane/road geometry; traffic exposure and signal phases; weather and traffic APIs; real CCTV ingestion; edge deployment; multi-camera fusion; spatio-temporal GNNs; trajectory Transformers; continual learning with independently labeled evaluation. None of those are claimed implemented.

## Licenses

Application code is supplied under AGPL-3.0-or-later to align with the Ultralytics dependency; see `LICENSE` and the upstream https://www.ultralytics.com/license. Commercial/closed-source distribution needs a separate license assessment. Footage has its own Pexels license; data has NYC Open Data terms. `data/demo/source.json` and `DATA_SOURCES.md` preserve attribution and download provenance. No person or source endorses this project.

## Disclaimer

“CrashZero is a hackathon research prototype. Its risk estimates are not certified collision predictions and should not be used as a standalone traffic-control or safety system.”
