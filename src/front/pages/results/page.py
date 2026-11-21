"""“Résultats d'analyse” page: indicators and analysis button, then the patient list, or the open patient record."""

import streamlit as st

from src.front.pages.results.overview import render_overview
from src.front.pages.results.patient_list import filtered_patients, render_filters, render_list
from src.front.pages.results.patient_record import render_record
from src.front.pages.results.state import build_state, open_patient_id


def render_results_page():
    state = build_state()
    st.session_state.setdefault("open_patient", None)

    shown = filtered_patients(state)
    if open_patient_id() in state.statuses:
        # Open record: indicators hidden so that the record fits on the screen without scrolling
        render_record(state, shown)
    else:
        st.session_state.open_patient = None
        render_overview(state)
        render_filters(state)
        render_list(state, shown)
