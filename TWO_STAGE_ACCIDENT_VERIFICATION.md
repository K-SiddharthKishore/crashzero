# CrashZero automatic accident verification

## Use

Set `OPENAI_API_KEY` in the local `.env`, then run `./run.sh`. In **TEST**, upload one or more videos and select **Start monitoring**. In **Accident Detection**, upload a video or choose a local/network camera and select **Start monitoring**. Monitoring continues through the recording or until the live source is stopped. Stage 1 detects and groups suspicious events; each new candidate is automatically verified by OpenAI. No verification button or API approval checkbox is needed.

The main screen shows **GREEN — NO ALERT** until a candidate is classified `LIKELY_ACCIDENT`, then **RED — ALERT**. `UNCERTAIN`, API errors, and exhausted budget retain a neutral system-status indicator and do not claim the event was ruled out. Automatic verification never submits an emergency call. With explicit local opt-in (`M2_TEST_ALERT_CALLS_ENABLED=true`), a verified TEST alert queues one demo request per uploaded video to the approved non-emergency test number. The Android app always requires a tap to open the dialer for these requests.

## Detection and evidence

TEST uses the existing 16-frame temporal checkpoint, scanning complete recordings and grouping adjacent suspicion scores. Module 2 uses its existing YOLO/ByteTrack motion signals and persistent temporal scores for both recordings and live sources. Box overlap alone does not create an event. The Stage 1 thresholds remain configurable through `SUSPICION_THRESHOLD`, `HIGH_CONFIDENCE_THRESHOLD`, and `SUSPICION_COOLDOWN_SECONDS`. Stage 1 is experimental and camera dependent.

Every candidate saves exactly two JPEG evidence frames: the suspected event and one approximately one second later. For a temporal score, the first frame uses the onset of its grouped four-second suspicion episode. For a tracked convergence signal, capture waits until the estimated encounter time (bounded to 0.4–1.5 seconds after the initial signal), rather than using a pre-impact frame. Images are capped at 1024 pixels wide with JPEG quality 75. Short recordings may use the final available frame; the limitation is stored. TEST keeps its evaluation history and Module 2 keeps its incident history, screenshots, and uploaded-video clips. These records and human review functions remain in SQLite even though the main screen is simplified.

The two images go in one OpenAI Responses request. The structured classification is `LIKELY_ACCIDENT`, `NO_ACCIDENT_EVIDENCE`, or `UNCERTAIN`, with supporting details stored internally. Strong visible crash aftermath can support `LIKELY_ACCIDENT` even when impact is not shown; ordinary close traffic and isolated roadside objects are insufficient. The actual classification and reason are also written to `outputs/verification_audit.jsonl`. The default model is controlled by `OPENAI_VISION_MODEL`. Requests have a 30-second timeout and zero SDK retries. Failed events are not retried automatically.

## Spending controls

`OPENAI_SESSION_BUDGET_USD` defaults to **$0.50**, below the user's $5 prepaid credit. A shared durable reservation database under `outputs/openai_budget.sqlite3` applies the cap across TEST and Module 2 and includes in-flight requests. The reservation uses `OPENAI_BUDGET_RESERVE_INPUT_TOKENS` (default 100,000) and the bounded output-token maximum; actual token usage replaces it when returned. `OPENAI_MAX_REQUESTS_PER_VIDEO` defaults to 3. One grouped incident is requested once; cached verified results for the same source, event timestamp, model, and prompt policy are reused without a paid request, including after the budget is exhausted. Changing the prompt does not reuse an older classification. Usage and failures remain in the local databases. Check OpenAI billing for the definitive charge.

## Limits

Two frames can miss contact between them. `UNCERTAIN` is an expected safe result when evidence is insufficient. Stage 2 cannot detect an accident that Stage 1 never selects. Tests use mocked API responses; no paid integration call is part of the automated test suite.
