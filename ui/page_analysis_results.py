"""“Résultats d'analyse” page: indicators and analysis button, patient list.

Clicking a patient opens its record (page_patient_result.py) in place of the list.
The analysis is done by main.py: the “Lancer l'analyse” button runs `main.py --remaining`.
Results are stored in inference_results.json (project root).
Streamlit re-runs the page from the top after each interaction: ResultsState is rebuilt at each run from the files,
while st.session_state keeps what must survive between runs (open patient, filter, search).
"""

import html
import os
import subprocess
import sys
from dataclasses import dataclass, field

import streamlit as st

import main
from ui import page_patient_result
from ui.common import PATIENTS_FOLDER, load_patients
from ui.page_patient_result import STATUS_LABELS, open_patient, status


def render_page():
    state = build_state()
    st.session_state.setdefault("open_patient", None)

    shown = filtered_patients(state)
    patient_id = st.session_state.open_patient
    if patient_id in state.statuses:
        # Open record: indicators hidden so that the record fits on the screen without scrolling.
        # Previous/next go through the filtered list, or through all the records if the patient is not in it.
        records = shown if any(r["patient"]["id"] == patient_id for r in shown) else state.sorted_patients
        page_patient_result.render_page(records, state.results)
    else:
        st.session_state.open_patient = None
        _render_overview(state)
        _render_filters(state)
        _render_list(state, shown)


# Records requiring an action are listed first
STATUS_ORDER = {"intervention": 0, "verification": 1, "monitoring": 2, "error": 3, "not_analysed": 4, "validated": 5}


# ---------------------------------------------------------------------------
# Data of the page
# ---------------------------------------------------------------------------

@dataclass
class ResultsState:
    patients: list  # patient records of dataset/
    results: dict = field(default_factory=dict)  # {patient id: analysis result}
    statuses: dict = field(default_factory=dict)  # {patient id: status code}
    counts: dict = field(default_factory=dict)  # {status code: number of records}
    sorted_patients: list = field(default_factory=list)  # records needing an action first

    @property
    def to_analyse(self):
        """Records analysed by “Lancer l'analyse”: never analysed or failed."""
        return [r for r in self.patients if self.statuses[r["patient"]["id"]] in ("not_analysed", "error")]


def build_state():
    """Reads the patient records of dataset/ and their inference results."""
    patients = load_patients()
    results = main.load_results()
    statuses = {r["patient"]["id"]: status(results.get(r["patient"]["id"]))[0] for r in patients}
    counts = {code: list(statuses.values()).count(code) for code in STATUS_LABELS}
    sorted_patients = sorted(patients, key=lambda r: STATUS_ORDER[statuses[r["patient"]["id"]]])
    return ResultsState(patients, results, statuses, counts, sorted_patients)


# ---------------------------------------------------------------------------
# Analysis by main.py
# ---------------------------------------------------------------------------

def run_main():
    """Runs `main.py --remaining` on dataset/; yields the id of each analysed patient.

    `main.py --all` (re-analysis of all the patients) is run by hand, not from the interface."""
    script = os.path.abspath(main.__file__)
    command = [sys.executable, "-u", script, "--remaining", "--folder", PATIENTS_FOLDER]
    other_lines = []
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                          cwd=os.path.dirname(script)) as process:
        for line in process.stdout:
            if line.startswith("Patient "):
                yield line.split()[1]
            else:
                other_lines.append(line.rstrip())
    if process.returncode:
        raise RuntimeError("\n".join(other_lines[-5:]) or f"main.py exited with code {process.returncode}")


# ---------------------------------------------------------------------------
# Top of the page: title, analysis button and indicator strip
# ---------------------------------------------------------------------------

def _render_overview(state):
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


# ---------------------------------------------------------------------------
# Patient list: status filters, search, one clickable row per patient
# ---------------------------------------------------------------------------

# Filter code: (label, status codes shown; None = all)
FILTERS = {
    "all": ("Tous", None),
    "intervention": ("Interventions", {"intervention"}),
    "verification": ("Vérifications", {"verification"}),
    "monitoring": ("Surveillances", {"monitoring"}),
    "validated": ("Validés", {"validated"}),
    "others": ("Non analysés / erreurs", {"not_analysed", "error"}),
}


def filtered_patients(state):
    """Records matching the selected filter and the search (identifier or drug), records needing action first."""
    selected_filter = st.session_state.get("filter", "all")
    search = st.session_state.get("search", "").strip().lower()
    return [
        r for r in state.sorted_patients
        if (FILTERS[selected_filter][1] is None or state.statuses[r["patient"]["id"]] in FILTERS[selected_filter][1])
        and (
            not search
            or search in r["patient"]["id"].lower()
            or any(search in str(t.get("drug_label", "")).lower() for t in r["treatments"])
        )
    ]


def _render_filters(state):
    def filter_label(code):
        name, codes = FILTERS[code]
        return name if codes is None else f"{name} ({sum(state.counts[c] for c in codes)})"

    filter_column, search_column = st.columns([3, 1], vertical_alignment="bottom")
    filter_column.radio("Filtre", list(FILTERS), format_func=filter_label, horizontal=True,
                        label_visibility="collapsed", key="filter")
    search_column.text_input("Recherche", placeholder="Identifiant ou médicament",
                             label_visibility="collapsed", key="search")


def _render_list(state, shown):
    """Patient list, one clickable row per patient, in a scrolling area (CSS .st-key-patient-list)."""
    if not shown:
        st.caption("Aucun dossier ne correspond à la sélection.")
        return

    with st.container(key="patient-list", gap=None):
        st.markdown(
            '<div class="patient-row header-row"><span>Patient</span><span>Statut</span><span>Âge</span>'
            '<span>Lignes de traitement</span><span>Alertes</span><span>Analysé le</span></div>',
            unsafe_allow_html=True,
        )
        for record in shown:
            _patient_row(state, record)


def _patient_row(state, record):
    patient = record["patient"]
    patient_id = patient["id"]
    result = state.results.get(patient_id) or {}
    code, state_label = status(state.results.get(patient_id))
    cells = [
        f"<b>{html.escape(patient_id)}</b>",
        f'<span class="status {code}">{html.escape(state_label)}</span>',
        f"{patient['age']} ans" if patient.get("age") is not None else "—",
        str(len(record["treatments"])),
        str(len(result.get("alerts", []))) if result.get("alerts") else "—",
        html.escape(result.get("date", "")) or "—",
    ]
    # HTML row (aligned columns) covered by an invisible button that opens the record
    with st.container(key=f"row-{patient_id}", gap=None):
        st.markdown('<div class="patient-row">' + "".join(f"<span>{c}</span>" for c in cells) + "</div>",
                    unsafe_allow_html=True)
        st.button(f"Ouvrir le dossier {patient_id}", key=f"open-{patient_id}", on_click=open_patient,
                  args=(patient_id,), use_container_width=True)

