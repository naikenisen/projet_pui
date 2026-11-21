"""Top of the “Résultats d'analyse” page: title, analysis button and indicator strip."""

import streamlit as st

from src.front.services.analysis import run_main


def render_overview(state):
    title_column, action_column = st.columns([3, 1], vertical_alignment="center")
    title_column.markdown(
        '<p class="page-title">Analyse des prescriptions</p>'
        '<p class="page-subtitle">Knowledge-Based System (KBS), référentiels et modèle de langage</p>',
        unsafe_allow_html=True,
    )
    run = action_column.button(
        f"Lancer l'analyse ({len(state.to_analyse)} dossiers)" if state.to_analyse
        else "Tous les patients ont été analysés",
        type="primary",
        disabled=not state.to_analyse,
        use_container_width=True,
        help="Analyse uniquement les dossiers non analysés ou en erreur",
    )
    _indicators(state)

    if run:
        _run_analysis(state)


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


def _run_analysis(state):
    """Runs main.py --remaining with a progress bar; main.py saves each result as it goes."""
    total = len(state.to_analyse)
    bar = st.progress(0.0, text="Analyse en cours...")
    try:
        for number, patient_id in enumerate(run_main(), start=1):
            bar.progress(min(number / total, 1.0), text=f"Dossier {patient_id} analysé ({number}/{total})")
    except Exception as error:
        bar.empty()
        st.error(f"Échec de main.py : {error}")
        return
    bar.empty()
    st.rerun()
