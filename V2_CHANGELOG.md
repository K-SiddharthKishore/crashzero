# V2 change inventory

V1 baseline: `d8354ba` on `crashzero-v1-fallback`.
V2 work: `crashzero-v2`.

- `4ae6222`: temporal verifier, source abstraction, evidence and incident storage.
- `b2a37b3`: three-screen UI, preserved V1 UI, synthetic offline fixtures and regressions.
- Final validation/documentation commit follows these checkpoints; use `git log -1 --oneline` for its identifier.

No new Python dependency or model replacement was required. The original app and guide are preserved as `app_v1.py` and `README_V1.md`; the exact original pipeline remains on the fallback branch. Hosted V1 remains read-only. All crash alerts are local simulations.

## Files added or changed since the V1 checkpoint

- `.gitignore`
- `HACKATHON_DEMO.md`
- `LIMITATIONS.md`
- `README.md`
- `README_V1.md`
- `TECHNICAL_NOTES.md`
- `V2_CHANGELOG.md`
- `VALIDATION.md`
- `app.py`
- `app_v1.py`
- `cloud/app.py`
- `config/bytetrack-v2.yaml`
- `config/v2.py`
- `data/simulations/collision.json`
- `data/simulations/collision.mp4`
- `data/simulations/legal_turn.json`
- `data/simulations/legal_turn.mp4`
- `data/simulations/near_miss.json`
- `data/simulations/near_miss.mp4`
- `data/simulations/normal.json`
- `data/simulations/normal.mp4`
- `data/simulations/normal_stop.json`
- `data/simulations/normal_stop.mp4`
- `data/simulations/perspective_overlap.json`
- `data/simulations/perspective_overlap.mp4`
- `data/simulations/single_bike.json`
- `data/simulations/single_bike.mp4`
- `scripts/benchmark_tracking.py`
- `scripts/create_simulations.py`
- `scripts/evaluate_safety.py`
- `src/detector.py`
- `src/incidents/__init__.py`
- `src/incidents/manager.py`
- `src/live.py`
- `src/safety/__init__.py`
- `src/safety/verifier.py`
- `src/trajectory.py`
- `src/video/__init__.py`
- `src/video/simulation.py`
- `src/video/source.py`
- `src/visualization.py`
- `src/zones.py`
- `tests/test_dashboard.py`
- `tests/test_safety.py`
- `tests/test_v1_dashboard.py`
- `tests/test_v2_integration.py`
