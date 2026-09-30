# Deploy V2 on Streamlit Community Cloud

Choose the destination GitHub repository, branch `crashzero-v2`, main file `cloud/v2/app.py`, and Python **3.12** in Advanced settings.

This starts the actual three-screen V2 application. `cloud/app.py` is the separate legacy V1 preview.

- Uses CPU-only PyTorch wheels. Root `packages.txt` supplies Linux libraries required by Ultralytics' OpenCV dependency.
- Downloads official YOLO11n weights on the first real-video analysis. Synthetic fixtures do not require this download.
- Supports uploaded recordings, included demos and live RTSP/RTSPS streams using a reachable public IP. Select Live Camera → IP / CCTV stream and enter the full stream URL. Hostnames, private/reserved IP addresses and HTTP streams are rejected in hosted mode. The remote server cannot access the visitor's local webcam or LAN camera; run the local app on the camera network for these sources.
- Stream addresses are masked in the UI and held in the browser session's server memory, not saved to incident metadata. Configure a distinct camera ID/name/location; changing the stream also creates a distinct source identity for incident filtering. Open/read timeouts prevent indefinite connection waits, and a lost connection is shown in the live status. No physical IP camera has been validated without a supplied reachable endpoint.
- Stores uploaded media, newly generated zones and incidents separately for each browser session. These files are temporary host storage, not durable backups. Reloading into a new session may lose access; save desired clips before leaving.
- Shared-host inference performance and dependency installation must be validated after deployment. Local tests do not establish cloud performance. The original Mac environment and dependency pins are unchanged.
- Alerts remain simulated; no emergency service or external webhook is contacted.

The GitHub account used by Streamlit must have admin access to the destination repository. Complete sign-in in your browser; do not paste passwords or tokens into chat.
