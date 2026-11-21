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
        '<p class="page-title">Analyse des prescriptions</p>'
        '<p class="page-subtitle">Knowledge-Based System (KBS), référentiels et modèle de langage</p>',
        unsafe_allow_html=True,
    )
    run = action_column.button(
        f"Lancer l'analyse ({len(state.to_analyse)} dossiers)",
        type="primary",
        disabled=not state.to_analyse,
        use_container_width=True,
        help="Analyse uniquement les dossiers non analysés ou en erreur",
    )
    rerun_all = rerun_column.button(
        "Relancer l'analyse de tous les patients",
        disabled=not state.patients,
        use_container_width=True,
        help="Analyse à nouveau tous les dossiers, y compris ceux déjà analysés",
    )
    _indicators(state)

    if run or rerun_all:
        _run_analysis(state, state.patients if rerun_all else state.to_analyse)


def _indicators(state):
    counts = state.counts
    st.markdown(
        f"""
    <div class="indicators">
      <div class="indicator"><div class="value">{len(state.patients)}</div><div class="name">Dossiers</div></div>
      <div class="indicator"><div class="value">{len(state.patients) - counts["not_analysed"]}</div><div class="name">Analysés</div></div>
      <div class="indicator orange"><div class="value">{counts["intervention"]}</div><div class="name">Interventions</div></div>
      <div class="indicator purple"><div class="value">{counts["verification"]}</div><div class="name">Vérifications</div></div>
      <div class="indicator blue"><div class="value">{counts["monitoring"]}</div><div class="name">Surveillances</div></div>
      <div class="indicator green"><div class="value">{counts["validated"]}</div><div class="name">Validés</div></div>
      <div class="indicator red"><div class="value">{counts["error"]}</div><div class="name">Erreurs</div></div>
      <div class="indicator"><div class="value">{counts["not_analysed"]}</div><div class="name">Non analysés</div></div>
    </div>
    """,
        unsafe_allow_html=True,
    )


def _run_analysis(state, selection):
    """Analyses the selected records one by one with a progress bar; results are saved as we go."""
    bar = st.progress(0.0, text="Analyse en cours...")
    for number, record in enumerate(selection, start=1):
        patient_id = record["patient"]["id"]
        bar.progress((number - 1) / len(selection), text=f"Analyse du dossier {patient_id} ({number}/{len(selection)})")
        analyse_and_save(state.results, record)
    bar.empty()
    st.rerun()
