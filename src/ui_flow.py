"""Read-only visual steps using Streamlit's bundled Material Symbols icons."""
import streamlit as st


def render_flow(labels, current=0, completed=()):
    columns = st.columns([1, .12, 1, .12, 1])
    icons = ['upload_file', 'manage_search', 'flag']
    for index, label in enumerate(labels):
        with columns[index * 2]:
            st.badge(f'{index + 1} · {label}',
                     icon=f':material/{"check_circle" if index in completed else icons[index]}:',
                     color='green' if index in completed else 'blue' if index == current else 'gray')
        if index < 2:
            columns[index * 2 + 1].markdown('→')
