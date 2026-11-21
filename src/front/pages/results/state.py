"""Data of the “Résultats d'analyse” page, and navigation between the patient list and an open record.

Streamlit re-runs the page from the top after each interaction: ResultsState is rebuilt at each run from the
files, while st.session_state keeps what must survive between runs (open patient, filter, search).
"""

from dataclasses import dataclass, field

import streamlit as st

from src.front.rendering.opinion import STATUS_LABELS, STATUS_ORDER, status
from src.front.services.analysis import load_results
from src.front.services.data import load_patients


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
    results = load_results()
    statuses = {r["patient"]["id"]: status(results.get(r["patient"]["id"]))[0] for r in patients}
    counts = {code: list(statuses.values()).count(code) for code in STATUS_LABELS}
    sorted_patients = sorted(patients, key=lambda r: STATUS_ORDER[statuses[r["patient"]["id"]]])
    return ResultsState(patients, results, statuses, counts, sorted_patients)


# ---------------------------------------------------------------------------
# Navigation between the patient list and an open record
# ---------------------------------------------------------------------------

def open_patient_id():
    return st.session_state.get("open_patient")


def open_patient(patient_id):
    st.session_state.open_patient = patient_id


def close_patient():
    st.session_state.open_patient = None
