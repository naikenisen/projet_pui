"""Data shared by the views during one run of the script, and session state of the navigation.

Streamlit re-runs app.py from the top after each interaction: AppState is rebuilt at each run from the files,
while st.session_state keeps what must survive between runs (open patient, filter, search, proposed rule).
"""

from dataclasses import dataclass, field

import streamlit as st

from src.front.rendering.opinion import STATUS_LABELS, STATUS_ORDER, status
from src.front.services.analysis import load_results
from src.front.services.data import load_patients
from src.front.services.documents import indexed_documents


@dataclass
class AppState:
    patients: list  # patient records of dataset/
    indexed: dict  # {pdf name: passage count} of the RAG documents
    results: dict = field(default_factory=dict)  # {patient id: analysis result}
    statuses: dict = field(default_factory=dict)  # {patient id: status code}
    counts: dict = field(default_factory=dict)  # {status code: number of records}
    sorted_patients: list = field(default_factory=list)  # records needing an action first

    @property
    def to_analyse(self):
        """Records analysed by “Lancer l'analyse”: never analysed or failed."""
        return [r for r in self.patients if self.statuses[r["patient"]["id"]] in ("not_analysed", "error")]

    def biology_parameters(self):
        """{laboratory parameter: unit} of the loaded records (the LLM must use their exact name in rules)."""
        parameters = {}
        for record in self.patients:
            for key, measure in record["patient"].get("biology", {}).items():
                parameters.setdefault(key, measure.get("unit") or "")
        return parameters


def build_state():
    """Reads the patient records of dataset/, the indexed RAG documents and the inference results."""
    patients = load_patients()
    indexed = indexed_documents()
    results = load_results()
    statuses = {r["patient"]["id"]: status(results.get(r["patient"]["id"]))[0] for r in patients}
    counts = {code: list(statuses.values()).count(code) for code in STATUS_LABELS}
    sorted_patients = sorted(patients, key=lambda r: STATUS_ORDER[statuses[r["patient"]["id"]]])
    return AppState(patients, indexed, results, statuses, counts, sorted_patients)


# ---------------------------------------------------------------------------
# Navigation between the patient list and an open record
# ---------------------------------------------------------------------------

def open_patient_id():
    return st.session_state.get("open_patient")


def open_patient(patient_id):
    st.session_state.open_patient = patient_id


def close_patient():
    st.session_state.open_patient = None
