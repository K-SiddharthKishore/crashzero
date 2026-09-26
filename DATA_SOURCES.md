# Data provenance / third-party notices

All bundled demonstration footage is **REAL VIDEO**. All event labels and scores are **algorithmic prototype estimates**, not human annotations. No footage is represented as Bengaluru. No historical records are synthetic. Synthetic trajectories exist only in clearly labeled unit tests.

## Historical data

NYPD / NYC Open Data, Motor Vehicle Collisions — Crashes, dataset `h9gi-nx95`, 2024 calendar year. Retrieved 2026-09-25 using the complete query in `data/historical/source.json`. 91,316 distinct collision IDs. 83,692 rows pass the NYC coordinate check. No location/time/injury records have been fabricated.

- Dataset: https://data.cityofnewyork.us/Public-Safety/Motor-Vehicle-Collisions-Crashes/h9gi-nx95
- API: https://dev.socrata.com/foundry/data.cityofnewyork.us/h9gi-nx95
- Terms: https://opendata.cityofnewyork.us/overview/#termsofuse

## Primary demo

**Busy City Intersection with Traffic and Pedestrians**, Richard L, Pexels, video 33049294.

- Page: https://www.pexels.com/video/busy-city-intersection-with-traffic-and-pedestrians-33049294/
- Source tags include Singapore. Exact camera location has not been verified and is not linked to NYC.
- Media: https://videos.pexels.com/video-files/33049294/14086047_3840_2160_25fps.mp4
- Local input: `data/demo/traffic.mp4`; source resolution reduced to 960×540, 12 FPS, audio removed, speed unchanged.
- License: https://www.pexels.com/license/
- Cached analysis: `outputs/demo/`, plus `outputs/demo_processed.mp4`.

## Additional offline demo clips

**Cars On Highway**, Pixabay via Pexels, video 854671.

- Page: https://www.pexels.com/video/cars-on-highway-854671/
- Media: https://videos.pexels.com/video-files/854671/854671-hd_1920_1080_25fps.mp4
- Local: `data/demo/highway.mp4`, first 35 seconds, 960×540 at 12 FPS.
- Geography unverified. License: Pexels.

**Mixed urban traffic**, Pexels video 27783817. The download URL is also referenced in Ultralytics' official MNN example.

- Page: https://www.pexels.com/video/27783817/
- Media: https://videos.pexels.com/video-files/27783817/12223745_1920_1080_24fps.mp4
- Referencing example: https://www.ultralytics.com/blog/seamlessly-deploy-ultralytics-yolo11-using-the-mnn-integration
- Local: `data/demo/mixed_traffic.mp4`, 960×540 at 12 FPS; no audio.
- Geography and creator attribution not independently verified. License: Pexels.
- Contains motorcycles, cars, buses and people; low-angle occlusion makes many conflicts ambiguous.

Pexels permits downloading, modifying and using its videos under its license. Do not imply endorsement by depicted people, creators or brands. These are incorporated demonstration clips, not a stock-media resale library.

## Model provenance

Ultralytics YOLO11n, official pretrained COCO checkpoint:
https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt

License: AGPL-3.0 / Ultralytics enterprise options, see https://www.ultralytics.com/license . ByteTrack is used through the Ultralytics implementation; official integration: https://docs.ultralytics.com/modes/track/ . Model artifacts are local and excluded from Git; fetch script downloads the official checkpoint.

A data/artifact SHA-256 manifest is stored in `data/manifest.json`. The README documents the trained model's split, features and evaluation. Its joblib artifact is generated from the public CSV and excluded from Git.
