# CrashZero — hackathon notes

## 15-second pitch

“We don't want a crash to be the first data point telling us an intersection is dangerous. CrashZero combines historical crash patterns with live trajectory conflicts to surface road-safety concerns before more crashes accumulate.”

## 30-second pitch

“Traditional blackspot analysis starts with crashes that already happened. CrashZero adds a leading signal: dangerous interactions in traffic video. Our local AI detects and tracks road users, projects their movement, and finds pairs approaching the same image-space region at the same time. We combine that idea with real historical crash analysis and an evaluated injury-context model, while clearly separating what we observed, what we estimated and what we cannot yet know.”

## 60-second pitch

“Past data tells us where crashes were recorded. But new intersections or changing traffic patterns may be dangerous before a crash history exists. CrashZero explores earlier warning signals. A lightweight YOLO model detects road users, ByteTrack maintains anonymous IDs, and a short motion history projects paths 2.5 seconds ahead. We look at simultaneous closest approach, not just crossing lines. A transparent score produces reviewable interaction episodes, and we only label prototype near misses after observing separation. A heatmap shows where those episodes cluster in the camera image. Alongside that, 91,316 authentic NYC crash records support historical patterns and a modest Random Forest model of injury severity context. We never claim to predict a specific accident, and we never merge an unverified camera with unrelated history. The complete demo runs locally, with cached video and analytics for unreliable hackathon Wi-Fi.”

## Problem, solution and innovation

- **Problem:** crash-based prioritization is reactive, and sparse crash records can hide emerging concerns.
- **Solution:** put historical evidence alongside measurable trajectory interactions and conditional injury context.
- **Innovation:** the product separates evidence streams, deduplicates risky episodes, requires observed resolution for a prototype near miss, and shows why a score exists.
- **Value:** a transportation analyst can review candidate sites and video moments for further investigation. This is not automatic traffic control.

## Technical architecture

Python 3.12 / Streamlit / OpenCV / Ultralytics YOLO11n / ByteTrack / NumPy / scikit-learn Random Forest / Plotly / optional PyDeck / SQLite / H.264 via FFmpeg. The system runs entirely locally once dependencies, weights, footage and data are downloaded.

Past: real CSV → cleaning → geospatial checks → patterns → temporal model evaluation.

Present: video → detections → track IDs → smoothed motion → synchronous closest approach → risk → episode state machine → exports.

Future: selected context → deterministic conditional-injury timeline → available-source weighted index.

## Demo sequence / three minutes

1. Open `http://localhost:8501`. Lead with the core sentence on Overview.
2. Open **Live CCTV**. Show **cached** annotated playback first; explicitly say it was processed by the same local engine.
3. Point out IDs, solid observed trails and dashed projected trajectories. Show peak risk and live clip index as different summaries.
4. Run a **fresh analysis** of the demo. CPU is the tested default. Do not imply that file processing is a connected city CCTV feed.
5. Open **Near Misses**. Explain confirmed-by-rule candidates versus overlap/review and unresolved episodes. A zero count is valid; never describe every alert as a real near miss.
6. Open **Risk Hotspots**. Highlight repeated conflict locations and actual class-pair counts. Explain image coordinates.
7. Open **Historical Analysis**, change a filter, then **City Risk**. State clearly: NYC 2024 public data, not Bengaluru.
8. Open **Future Prediction**. Change weekday/vehicle context and show model evaluation. Say “conditional injury context,” not “crash tomorrow.”
9. Show fusion weights and the missing-data behavior. Explain why NYC history and this demo camera are not fused.
10. Close: “Past tells us what happened. Vision measures interactions now. Predictive models help prioritize the conditions worth investigating next.”

## Offline fallback

If the browser or inference fails, open `outputs/demo_processed.mp4`. Use `outputs/demo/preview.jpg`, `heatmap.jpg` and `analytics.json`. The UI's **Load offline demo analytics** button restores the cached session. Restart with `./run.sh`. If port 8501 is already serving CrashZero, use that app; otherwise stop the previous process before restarting.

## Dataset explanation

NYPD Motor Vehicle Collisions — Crashes, NYC Open Data, full 2024. There are 91,316 unique records and 83,692 usable coordinates under the NYC bounds check. Records describe police-reported crashes; missing reports and traffic exposure prevent absolute crash-probability estimation. The dataset has date/time, borough, vehicle types and injury/fatality counts. It lacks weather, lighting, road surface and junction geometry. Source query and provenance are bundled.

The model learns any injury/fatality **given a reported crash**. Jan–Sep is training, Oct–Dec is holdout. AUC 0.6028 is modest. Brier score 0.2356 beats a 0.2482 prevalence baseline, but neither metric validates crash-occurrence forecasting or transfer to India.

## Likely judge questions — honest answers

**1. How can you predict accidents?**
We do not claim to predict the exact occurrence of a specific crash. CrashZero estimates elevated road-safety indicators using historical patterns, contextual conditions and live trajectory conflicts. The implemented ML target is injury given a reported crash; the live branch estimates future image-space proximity.

**2. Is this actually AI?**
Yes. A pretrained YOLO neural detector identifies road-user classes, and a trained Random Forest estimates injury context. Tracking, motion projection, scoring and fusion are explicit deterministic algorithms. We do not label every component deep learning.

**3. Did you train YOLO?**
No. We use the lightweight pretrained YOLO11n COCO weights. This saves time and compute. Domain adaptation and camera-specific evaluation are future work.

**4. Why not a Transformer or GNN?**
There is no validated trajectory training corpus for this camera, and the deadline favors inspectable, reliable short-horizon motion. A learned predictor can replace the projection method later while preserving the downstream interface.

**5. What does 80/100 mean?**
An uncalibrated priority index produced by a documented weighted formula. It does not mean an 80% probability of collision. Proximity, time, convergence, vulnerability and trajectory confidence contribute.

**6. Do crossing lines imply a collision?**
No. We evaluate simultaneous positions under constant velocity and find the continuous-time closest approach. Paths that cross at different times need not produce a warning; the tests include that case.

**7. Is the displayed time real TTC?**
It is seconds to minimum projected image-space separation, using source video FPS. Without camera calibration, object dimensions, lane geometry and behavior modeling, it is not validated metric TTC.

**8. How do you identify a near miss?**
A high-risk episode must be followed by observed separation for at least 0.5 seconds and no observed bounding-box overlap during that episode. We call it a prototype candidate, not a confirmed near miss. Track loss and clip endings stay unresolved.

**9. Is a bounding-box overlap a crash?**
No. Objects in different lanes or at different depths can overlap in the image. Those episodes are marked for review, never declared collisions.

**10. Are these Bengaluru crashes?**
No. This prototype uses official NYC 2024 crash records. A short search did not yield a quickly verified local dataset suitable for the entire pipeline. The labels explicitly identify geography and limitations.

**11. How accurate is the prediction model?**
The held-out AUC is 0.6028 for binary injury classification, with Brier 0.2356 versus baseline 0.2482. This is modest signal, not strong accident prediction. There is no independent live-conflict accuracy claim because we have not obtained labeled ground truth.

**12. Why not combine all three scores on the home page?**
The demonstration camera is not matched to NYC history. Mixing them would imply evidence we do not have. Missing components are excluded and weights renormalized. The engine can combine all three once geographic and temporal compatibility is established.

**13. What makes an emerging hotspot?**
Verified low historical index, repeated high-risk interactions and rising interaction density. If historical coverage is unknown, we only report a live cluster. Unknown history never counts as zero accidents.

**14. Does high accident count mean high danger?**
Not necessarily. More traffic can mean more crashes. We lack exposure denominators and present counts as concentration. Production work needs traffic volume, pedestrian activity and road geometry.

**15. What about privacy?**
No facial identity, face recognition or plate reading. IDs are temporary, and processing stays local. Original footage can still contain identifiable people; responsible retention and deletion remain necessary.

**16. Does it work offline?**
Yes, after one-time setup. Model weights, data, footage, annotated playback and analytics are local. The default geographic plot works without tiles. Only the optional online street map needs a connection.

**17. Can it run on inexpensive hardware?**
The current model is a nano detector with bounded resolution/history and frame sampling. CPU inference is measured on the Mac, not assumed. Edge-device performance still needs benchmarking.

**18. How does it scale to a city?**
Move per-camera detection/tracking to edge workers; send anonymous events and health metrics to a central store; calibrate cameras and join events to verified locations. Use validation, monitoring and human review before operational decisions.

**19. What produces false positives?**
Perspective, camera movement, occlusion, turns, detection jitter, track-ID switches and riders detected as people plus motorcycles. Short-horizon linear projection cannot know intent. The UI names these limitations.

**20. Why are some counts zero?**
The clip may contain no qualifying event, the detector may miss road users, or the conservative event logic may leave an episode unresolved. We display the observed output rather than injecting warnings for presentation.

**21. What data would improve the project next?**
Calibrated fixed-camera footage with labeled conflicts, genuine local crash records, traffic exposure, signal phases, weather, lane geometry and independent validation across cameras and seasons.

**22. Can this control signals or warn drivers today?**
No. It is a hackathon research prototype for analysis and review. Certification, robust real-time engineering, validation and operational governance are outside this build.

## Roadmap, not implemented tonight

Spatio-temporal GNN; trajectory Transformer; calibrated ground-plane geometry; multi-camera fusion; weather/traffic APIs; authorized CCTV integration; edge deployment; signal phases; city-scale event stores; exposure-adjusted rates; continual learning and prospective evaluation.

## Closing disclaimer

CrashZero is a hackathon research prototype. Its risk estimates are not certified collision predictions and should not be used as a standalone traffic-control or safety system.
