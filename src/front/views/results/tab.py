"""“Analysis results” tab: list of the patients, or the open patient record."""

import streamlit as st

from src.front.state import open_patient_id
from src.front.views.results.patient_list import filtered_patients, render_filters, render_list
from src.front.views.results.patient_record import render_record


def render_results_tab(state):
    # Widgets that are not displayed lose their value: keep the filter and the search when a patient is open
    for key in ("filter", "search"):
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]
    st.session_state.setdefault("open_patient", None)

    shown = filtered_patients(state)
    if open_patient_id() in state.statuses:
        render_record(state, shown)
    else:
        st.session_state.open_patient = None
        render_filters(state)
        render_list(state, shown)
