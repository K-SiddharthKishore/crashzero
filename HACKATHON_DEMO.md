# CrashZero V2 — presentation runbook

## Prepare offline

```bash
cd /Users/siddharth/Documents/crashzero
.venv/bin/python -m pytest -q
PORT=8502 ./run.sh
```

Open http://127.0.0.1:8502. Ensure `models/yolo11n.pt`, real videos in `data/demo/`, and synthetic videos/JSON in `data/simulations/` exist. If synthetic assets need regeneration: `.venv/bin/python scripts/create_simulations.py` (offline). Keep CPU selected for the validated path.

## Three-minute demo

1. Live Analysis is the homepage. Explain: “Before, during and after a dangerous event.”
2. Select **Demo → Traffic** and **Start analysis**. This runs the real local YOLO11n + ByteTrack pipeline. Show anonymous IDs, smoothed trails and dashed projections. Numbers are image-space estimates.
3. Wait for completion (about 16 seconds of source video) or select Stop. There should be no likely accident incident in this smoke-tested normal-traffic clip. Candidate checks may resolve to normal interaction.
4. For a deterministic near-miss workflow, select **Near Miss · SYNTHETIC TEST** and Start. Say explicitly: “This is a scripted engineering fixture; the detector is bypassed.” Watch the pair conflict and subsequent separation. Then open Conflict Zones and choose Current analysis. Expand the zone to show actual recorded conflict coordinates/timestamps and the near-miss status.
5. Return to Live Analysis. Select **Collision · SYNTHETIC TEST** and Start. The event occurs around source second 5. The UI shows possible accident / verifying, then likely collision around second 7–8. This is a test of verification and response plumbing, not real accident accuracy.
6. Let the 12-second fixture finish so the five-second post-event window is saved.
7. Open Incidents. Expand the latest record. Show BEFORE / EVENT / AFTER images, anonymous IDs, source offset, unconfigured demo location, individual evidence signals and **DEMO ALERT CREATED**.
8. Play the event clip. Explain that the score is a heuristic evidence score, not a probability or measured accuracy.
9. Optional: replay **Single Bike · SYNTHETIC TEST**. Explain the required combination of heading anomaly, deceleration, persistence and post-event stop; zig-zag alone cannot confirm an accident.
10. For an actual registered webcam, select Live Camera after granting macOS permission. Configure location explicitly. Never claim video-derived GPS or a real emergency dispatch.

## Useful wording

“CrashZero watches traffic before, during and after dangerous events — identifying conflict zones, detecting likely accidents and preserving the information needed for faster response.”

“Real traffic detection uses YOLO11n and ByteTrack. Accident verification is an explainable temporal heuristic. The deterministic crash examples are synthetic fixtures, not a trained accident classifier.”

## Fallbacks

- **Webcam denied:** use Demo → Traffic. Grant Camera permission to Terminal/Codex in macOS settings later; no internet is required for local demos.
- **Model/inference trouble:** use CPU; check the local weights. Synthetic fixtures still exercise the verifier/evidence workflow without model loading, and are labeled accordingly.
- **Slow hardware:** use the short 12-second synthetic fixtures and the preserved V1 saved Conflict Zones analysis. Preview-only video is clearly labeled, never described as fresh inference.
- **Stream disconnected:** Stop, fix the network/local environment URL, then restart; use local demo immediately during presentation.
- **V2 UI trouble:** `.venv/bin/python -m streamlit run app_v1.py --server.address 127.0.0.1 --server.port 8503` retains the original interface. For the exact old code, stop servers, preserve any working changes, `git switch crashzero-v1-fallback`, then `PORT=8503 ./run.sh`.
- **Evidence still capturing:** wait until source completion, then reopen Incidents. If stopped early, the record explicitly marks a partial post-event window.

Do not call an unresolved conflict a crash. Do not claim labeled crash accuracy, calibrated physical speed, or real emergency integration.
