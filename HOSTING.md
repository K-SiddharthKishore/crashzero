# Hosting status

Local build was completed, stopped and restarted with `./run.sh` before hosting was investigated.

## Selected option: Streamlit Community Cloud

As checked on 2026-09-25, the official documentation describes free deployment from GitHub. Browser access to https://share.streamlit.io reached **Sign in**. No authenticated session was available. Signing in accepts terms and needs user interaction; no account was created and no public app is claimed.

- Official deployment guide: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
- Free Community Cloud: https://docs.streamlit.io/deploy/streamlit-community-cloud
- Dependency organization: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization

Prepared entry point: **`cloud/app.py`**. Select Python **3.12**. Its adjacent `cloud/requirements.txt` omits Torch, YOLO and OpenCV. The hosted view serves historical analytics, maps, the injury-context model and the preprocessed video. Live uploads and new inference are disabled and labeled. The local `./run.sh` continues to provide full processing.

The model trains from the included public CSV on first cloud access because local joblib artifacts are excluded from Git. This is lightweight (100 bounded trees); actual cloud memory and startup performance remain unverified. The cached video is included. The entire project needs to be placed in a GitHub repository authorized by the user before deployment can continue.

## Alternative investigated

Hugging Face's current official Spaces overview says new compute-backed Docker/Gradio Spaces require a paid plan, even though CPU Basic compute has no hourly cost. It is therefore not assumed to be an unconditional free option. Streamlit there uses the Docker SDK.

- https://huggingface.co/docs/hub/spaces-overview
- https://huggingface.co/docs/hub/spaces-sdks-streamlit

No paid resource was provisioned. No existing local functionality was removed for hosting.
