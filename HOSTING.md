# CrashZero hosting status

The current two-module application is prepared for Streamlit Community Cloud and pushed to the public GitHub repository `K-SiddharthKishore/crashzero`, branch `crashzero-v2`. Deployment entry point: `cloud/v2/app.py`; Python version: 3.12. The cloud build uses its adjacent `cloud/v2/requirements.txt` and the root `packages.txt`.

The public deployment is live at **https://crashzero-v2-siddharth.streamlit.app/**. On 2026-10-22, the two-button chooser, both module screens, and the real Highway demo's completed analysis → Danger Spots transition were verified on the hosted site. Cloud management still requires the account holder to sign in at https://share.streamlit.io/.

Deployment settings:

- Repository: `K-SiddharthKishore/crashzero`
- Branch: `crashzero-v2`
- Main file: `cloud/v2/app.py`
- Python: `3.12`

The hosted build runs on CPU, downloads YOLO weights on first analysis, and keeps both modules' files and records separate per browser session. They live on temporary host storage. The local trained temporal checkpoint is not in this public branch; Accident Response uses its experimental motion baseline. Real calls are forced off in the hosted entry point. Live Highway analysis completed successfully on shared-host CPU; performance will vary with load and video length.

Official guides: [deploy an app](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy), [app dependencies](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies).
