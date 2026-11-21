"""Top of the page: title, analysis buttons and indicator strip. Hidden when a patient record is open."""

import streamlit as st

from src.front.services.analysis import analyse_and_save
from src.front.state import open_patient_id


def render_overview(state):
    # Open record: header and indicators hidden so that the record fits on the screen without scrolling
    if open_patient_id():
        return

    title_column, action_column, rerun_column = st.columns([2, 1, 1], vertical_alignment="center")
    title_column.markdown(
        '<p class="page-title">Prescription analysis</p>'
        '<p class="page-subtitle">Knowledge-Based System (KBS), reference guidelines and language model</p>',
        unsafe_allow_html=True,
    )
    run = action_column.button(
        f"Run the analysis ({len(state.to_analyse)} records)",
        type="primary",
        disabled=not state.to_analyse,
        use_container_width=True,
        help="Analyses only the records not yet analysed or in error",
    )
    rerun_all = rerun_column.button(
        "Re-run the analysis of all patients",
        disabled=not state.patients,
        use_container_width=True,
        help="Analyses all the records again, including those already analysed",
    )
    _indicators(state)

    if run or rerun_all:
        _run_analysis(state, state.patients if rerun_all else state.to_analyse)


def _indicators(state):
    counts = state.counts
    st.markdown(
        f"""
    <div class="indicators">
      <div class="indicator"><div class="value">{len(state.patients)}</div><div class="name">Records</div></div>
      <div class="indicator"><div class="value">{len(state.patients) - counts["not_analysed"]}</div><div class="name">Analysed</div></div>
      <div class="indicator orange"><div class="value">{counts["intervention"]}</div><div class="name">Interventions</div></div>
      <div class="indicator purple"><div class="value">{counts["verification"]}</div><div class="name">Verifications</div></div>
      <div class="indicator blue"><div class="value">{counts["monitoring"]}</div><div class="name">Monitoring</div></div>
      <div class="indicator green"><div class="value">{counts["validated"]}</div><div class="name">Validated</div></div>
      <div class="indicator red"><div class="value">{counts["error"]}</div><div class="name">Errors</div></div>
      <div class="indicator"><div class="value">{counts["not_analysed"]}</div><div class="name">Not analysed</div></div>
    </div>
    """,
        unsafe_allow_html=True,
    )


def _run_analysis(state, selection):
    """Analyses the selected records one by one with a progress bar; results are saved as we go."""
    bar = st.progress(0.0, text="Analysis in progress...")
    for number, record in enumerate(selection, start=1):
        patient_id = record["patient"]["id"]
        bar.progress((number - 1) / len(selection), text=f"Analysing record {patient_id} ({number}/{len(selection)})")
        analyse_and_save(state.results, record)
    bar.empty()
    st.rerun()
