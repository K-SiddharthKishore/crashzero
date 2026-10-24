"""Temporary read-only preview of JPEGs used by verified OpenAI requests."""
from pathlib import Path

import streamlit as st


SHOW_DEBUG_EVIDENCE = True
CLASSIFICATIONS = {'LIKELY_ACCIDENT', 'NO_ACCIDENT_EVIDENCE', 'UNCERTAIN'}


def preview_items(records, submitted_evidence):
    """Read original JPEG bytes; never substitute a newly extracted frame."""
    items = []
    for record in records:
        if not record or record.get('status') != 'VERIFIED' or record.get('classification') not in CLASSIFICATIONS:
            continue
        identity = record.get('event_id') or record.get('incident_id')
        cached = record.get('attempt_count', 0) == 0
        original = submitted_evidence(identity)
        pair = None
        if original:
            paths = original.get('evidence_paths') or []
            timestamps = original.get('frame_timestamps') or []
            if len(paths) == len(timestamps) == 2:
                try:
                    pair = [(Path(path).read_bytes(), float(timestamp))
                            for path, timestamp in zip(paths, timestamps)]
                    if not all(data.startswith(b'\xff\xd8') for data, _ in pair):
                        pair = None
                except (OSError, TypeError, ValueError):
                    pair = None
        items.append({'classification': record['classification'],
                      'cached': cached, 'pair': pair})
    return items


def render_evidence_preview(records, submitted_evidence):
    if not SHOW_DEBUG_EVIDENCE:
        return
    st.subheader('Evidence Frames Analysed')
    items = preview_items(records, submitted_evidence)
    if not items:
        if any(row and row.get('status') == 'PROCESSING' for row in records):
            st.caption('Stage 2 processing; evidence frames will appear when verification completes.')
        elif any(row and row.get('status') == 'VERIFICATION_FAILED' and
                 row.get('attempt_count', 0) > 0 for row in records):
            st.caption('Stage 2 result unavailable; submitted evidence frames could not be verified.')
        else:
            st.write('No evidence frames submitted for verification')
        return
    for number, item in enumerate(items, 1):
        with st.expander(f"Event {number} — Stage 2 Result: {item['classification']}",
                         expanded=len(items) == 1):
            if item['cached']:
                st.caption('Cached verification · original evidence frames')
            if item['pair'] is None:
                st.caption('Original submitted JPEGs are unavailable.')
                continue
            left, right = st.columns(2)
            for column, title, (jpeg, timestamp) in zip(
                (left, right),
                ('Frame 1 — Suspected Accident Moment',
                 'Frame 2 — Approximately 1 Second Later'), item['pair']):
                with column:
                    st.markdown(f'**{title}**')
                    st.image(jpeg, width='stretch')
                    st.caption(f'Original video timestamp: {timestamp:.2f} s')
