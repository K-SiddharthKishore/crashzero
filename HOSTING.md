# CrashZero hosting status

The current two-module application is prepared for Streamlit Community Cloud and pushed to the public GitHub repository `K-SiddharthKishore/crashzero`, branch `crashzero-v2`. Deployment entry point: `cloud/v2/app.py`; Python version: 3.12. The cloud build uses its adjacent `cloud/v2/requirements.txt` and the root `packages.txt`.

As checked on 2026-10-22, https://share.streamlit.io/ opens a sign-in screen that requires the account holder to accept Streamlit's terms. No authenticated Community Cloud session is available here, so **no public Streamlit app has been created or verified**. After signing in, choose **Create app → Yup, I have an app**, then enter:

- Repository: `K-SiddharthKishore/crashzero`
- Branch: `crashzero-v2`
- Main file: `cloud/v2/app.py`
- Python: `3.12`

The hosted build runs on CPU, downloads YOLO weights on first analysis, and keeps both modules' files and records separate per browser session. They live on temporary host storage. The local trained temporal checkpoint is not in this public branch; Accident Response uses its experimental motion baseline. Real calls are forced off in the hosted entry point. Shared-host build and processing speed still need live validation.

Official guides: [deploy an app](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy), [app dependencies](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies).
