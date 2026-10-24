from datetime import datetime
from pathlib import Path
import hashlib
import json

import streamlit as st

from .analyzer import TestVideoAnalyzer
from .config import TestLabConfig
from .storage import TestHistory


def _timecode(seconds):
    if seconds is None:
        return '—'
    minutes, value = divmod(float(seconds), 60)
    return f'{int(minutes):02d}:{value:05.2f}'


def _save_upload(config, uploaded):
    content = uploaded.getvalue()
    digest = hashlib.sha256(content).hexdigest()
    suffix = Path(uploaded.name).suffix.lower()
    path = config.uploads_dir / f'{digest[:20]}{suffix}'
    if not path.exists():
        path.write_bytes(content)
    return path


def _review_buttons(history, row, prefix):
    st.caption('After watching the video, verify whether the prediction itself was correct.')
    correct, wrong, unsure = st.columns(3)
    if correct.button('Correct Prediction', key=f'{prefix}_correct', use_container_width=True):
        history.review(row['test_id'], 'CORRECT')
        st.rerun()
    if wrong.button('Wrong Prediction', key=f'{prefix}_wrong', use_container_width=True):
        history.review(row['test_id'], 'WRONG')
        st.rerun()
    if unsure.button('Not Sure', key=f'{prefix}_unsure', use_container_width=True):
        history.review(row['test_id'], 'NOT_SURE')
        st.rerun()
    if row.get('review'):
        st.caption('Review: ' + row['review'].replace('_', ' ').title())


def _result_card(history, row, show_video=True):
    if row['result'] == 'Accident Detected':
        st.error('Accident Detected')
    elif row['result'] == 'No Accident Detected':
        st.success('No Accident Detected')
    else:
        st.warning('Uncertain')
    timestamp, score, windows = st.columns(3)
    timestamp.metric('Suspected timestamp', _timecode(row['event_timestamp']))
    score.metric('Confidence score', '—' if row['model_score'] is None else f"{row['model_score']:.3f}")
    windows.metric('Temporal windows', row['windows_analyzed'])
    st.caption('Confidence is the model’s raw sigmoid score, not a calibrated real-world accident probability. '
               f"Decision threshold: {row['threshold']:.3f}.")
    st.write(row['decision_basis'])
    if show_video and Path(row['source_path']).exists():
        st.video(row['source_path'])
    images = [path for path in row['evidence_paths'] if Path(path).exists()]
    if images:
        st.caption('Before · suspected event · after')
        columns = st.columns(len(images))
        for column, image in zip(columns, images):
            column.image(image, caption=Path(image).stem.split('_', 1)[-1])
    _review_buttons(history, row, 'review_' + row['test_id'])


def _incorrect_review(history, rows):
    wrong = [row for row in rows if row['review'] == 'WRONG']
    st.subheader('Incorrect predictions')
    st.caption('These stay in the TEST library. They are never added to training automatically.')
    if not wrong:
        st.info('No predictions have been marked wrong yet.')
        return
    for row in wrong:
        with st.expander(f"{row['source_name']} · predicted {row['result']}"):
            if Path(row['source_path']).exists():
                st.video(row['source_path'])
            current = row.get('actual_outcome') or 'NOT_SURE'
            options = ['ACCIDENT', 'NO_ACCIDENT', 'NOT_SURE']
            actual = st.selectbox('Actual outcome', options, index=options.index(current),
                                  key='actual_' + row['test_id'])
            timestamp = st.number_input('Actual accident timestamp (seconds)', min_value=0.0,
                                        max_value=max(0.0, float(row['duration_seconds'])),
                                        value=float(row.get('actual_timestamp') or 0.0), step=0.1,
                                        disabled=actual != 'ACCIDENT', key='actual_time_' + row['test_id'])
            note = st.text_area('Reviewer note', value=row.get('reviewer_note') or '',
                                key='note_' + row['test_id'])
            approved = st.checkbox('Approve this verified label as a future training candidate',
                                   value=row['approved_for_training'],
                                   disabled=actual == 'NOT_SURE', key='approve_' + row['test_id'])
            if st.button('Save verified label', key='save_label_' + row['test_id']):
                history.review(row['test_id'], 'WRONG', actual,
                               timestamp if actual == 'ACCIDENT' else None, note, approved)
                st.rerun()

    manifest = history.training_manifest()
    st.download_button('Download approved training-candidate manifest',
                       json.dumps(manifest, indent=2), 'crashzero_verified_training_candidates.json',
                       'application/json', disabled=not manifest)
    st.caption('Downloading a manifest does not retrain or modify the deployed model.')


def render_test_lab(data_dir=None):
    config = TestLabConfig.load(data_dir=data_dir)
    history = TestHistory(config.db_path)
    st.title('TEST · Accident Detection')
    st.caption('Offline model evaluation only · no alerts, phone calls, or emergency actions')

    metrics = history.metrics()
    columns = st.columns(4)
    columns[0].metric('Videos analysed', metrics['total'])
    columns[1].metric('Detected accidents', metrics['accidents'])
    columns[2].metric('Uncertain results', metrics['uncertain'])
    columns[3].metric('Verified accuracy', '—' if metrics['accuracy'] is None else f"{metrics['accuracy']:.1%}",
                      help='Correct / (correct + wrong). Not Sure and unreviewed videos are excluded.')
    st.caption(f"Accuracy currently uses {metrics['verified']} explicitly reviewed prediction(s).")

    st.markdown('<div class="cz-section-label">UPLOAD AND ANALYSE</div>', unsafe_allow_html=True)
    uploads = st.file_uploader('Traffic videos', type=['mp4', 'mov', 'avi', 'mkv'],
                               accept_multiple_files=True, key='test_lab_uploads')
    if uploads:
        st.caption(f'{len(uploads)} video(s) ready. The entire duration of each file will be scanned.')
        if st.button('Analyse all videos', type='primary'):
            overall = st.progress(0.0)
            status = st.empty()
            analyzer = TestVideoAnalyzer(config)
            completed = []
            try:
                for index, upload in enumerate(uploads):
                    status.write(f'Analysing {upload.name} ({index + 1}/{len(uploads)})')
                    path = _save_upload(config, upload)
                    def update(value, offset=index):
                        overall.progress((offset + value) / len(uploads))
                    row = analyzer.analyze(path, upload.name, update)
                    history.save(row)
                    completed.append(row['test_id'])
                st.session_state['test_latest_ids'] = completed
                status.success(f'Analysis complete for {len(completed)} video(s).')
                st.rerun()
            except Exception as exc:
                status.error('Analysis could not complete: ' + str(exc))

    latest_ids = st.session_state.get('test_latest_ids', [])
    latest = [history.get(identity) for identity in latest_ids]
    latest = [row for row in latest if row]
    if latest:
        st.markdown('<div class="cz-section-label">LATEST RESULTS</div>', unsafe_allow_html=True)
        for row in latest:
            with st.container(border=True):
                st.subheader(row['source_name'])
                _result_card(history, row)

    st.markdown('<div class="cz-section-label">TEST HISTORY</div>', unsafe_allow_html=True)
    rows = history.all()
    if not rows:
        st.info('No TEST videos have been analysed yet.')
    for row in rows:
        created = datetime.fromtimestamp(row['created_at']).strftime('%Y-%m-%d %H:%M')
        label = f"{row['source_name']} · {row['result']} · {created}"
        with st.expander(label):
            _result_card(history, row)

    st.markdown('<div class="cz-section-label">MODEL IMPROVEMENT QUEUE</div>', unsafe_allow_html=True)
    _incorrect_review(history, rows)
    with st.expander('Known model limitations and retraining guardrails'):
        st.write('The current model has strong validation precision but misses many accidents and produces '
                 'too many false alarms on limited held-out normal footage. Likely causes include incident-heavy '
                 'training data, too few diverse normal-driving negatives, low input resolution, domain shift, '
                 'and a four-second full-frame classifier that lacks explicit object interaction features.')
        st.write('TEST uploads remain evaluation data. Only a human-labelled item explicitly approved above '
                 'appears in the downloadable training-candidate manifest. The deployed checkpoint is never '
                 'changed by this screen.')

