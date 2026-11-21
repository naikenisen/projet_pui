"""Open patient record: navigation bar, laboratory values, prescription and pharmaceutical opinion."""

import html

import streamlit as st

from src.front.components.widgets import label, table
from src.front.rendering.opinion import STATUS_COLORS, status
from src.front.rendering.record import biology_table, lines_to_modify, patient_profile, prescription_table
from src.front.services.analysis import analyse_and_save
from src.front.services.data import load_lab_ranges
from src.front.state import close_patient, open_patient, open_patient_id
from src.front.views.results.opinion import render_opinion


def render_record(state, shown):
    """Full-width record, with a way back to the list and navigation to the previous or next patient."""
    patient_id = open_patient_id()
    records = shown if any(r["patient"]["id"] == patient_id for r in shown) else state.sorted_patients
    position = next(i for i, r in enumerate(records) if r["patient"]["id"] == patient_id)
    record = records[position]
    _navigation_bar(state, records, position)
    _patient_record(record, state.results.get(patient_id), load_lab_ranges())


def _navigation_bar(state, records, position):
    record = records[position]
    patient_id = record["patient"]["id"]
    code, state_label = status(state.results.get(patient_id))

    back_column, title_column, rerun_column, previous_column, position_column, next_column = st.columns(
        [1.3, 3, 1.6, 1, 0.7, 1], vertical_alignment="center"
    )
    back_column.button("← Liste des patients", on_click=close_patient, use_container_width=True)
    title_column.markdown(
        f'<span class="page-title">Patient {html.escape(patient_id)}</span> &nbsp; '
        f'<span style="color: {STATUS_COLORS[code]}; font-weight: 600">{html.escape(state_label)}</span>',
        unsafe_allow_html=True,
    )
    if rerun_column.button("Relancer l'analyse", key=f"analyse-{patient_id}", use_container_width=True,
                           help="Analyse à nouveau ce patient"):
        with st.spinner(f"Analyse du dossier {patient_id} en cours..."):
            analyse_and_save(state.results, record)
        st.rerun()
    if position > 0:
        previous_column.button("‹ Précédent", on_click=open_patient, args=(records[position - 1]["patient"]["id"],),
                               use_container_width=True)
    position_column.markdown(f'<div class="muted" style="text-align:center; margin:0">{position + 1} / {len(records)}</div>',
                             unsafe_allow_html=True)
    if position < len(records) - 1:
        next_column.button("Suivant ›", on_click=open_patient, args=(records[position + 1]["patient"]["id"],),
                           use_container_width=True)


def _patient_record(record, result, ranges):
    """Laboratory values on the left; prescription at the top right, pharmaceutical opinion below.

    Each area has a height computed from the screen height (CSS .st-key-zone-*) and scrolls on its own: the page
    does not scroll, the pharmacist moves from one record to the next without scrolling. No horizontal scrolling.
    """
    patient = record["patient"]
    treatments = record["treatments"]

    patient_column, result_column = st.columns([2, 3], gap="medium")

    with patient_column:
        label("Profil patient")
        st.markdown(f'<div class="profile">{html.escape(patient_profile(patient))}</div>', unsafe_allow_html=True)
        if patient.get("reference_date"):
            st.caption(f"Jour de référence : {patient['reference_date']}")
        biology = patient.get("biology", {})
        if biology:
            label(f"Biologie ({len(biology)} paramètres)")
            biology_rows, biology_classes = biology_table(biology, ranges)
            with st.container(key="zone-biology", border=False):
                table(["Paramètre", "Valeur", "Interprétation", "Date"], biology_rows, row_classes=biology_classes)

    with result_column:
        # Lines the LLM proposes to modify (“intervention” points): in red
        to_modify = lines_to_modify(result)
        legend = " · en rouge : modification proposée" if to_modify else ""
        label(f"Prescription ({len(treatments)} lignes){legend}")
        with st.container(key="zone-prescription", border=False):
            prescription_rows, prescription_classes = prescription_table(treatments, to_modify)
            table(["N°", "Médicament", "Posologie", "Début", "Fin"], prescription_rows,
                  row_classes=prescription_classes, short_columns=("N°", "Début", "Fin"))
        label("Avis pharmaceutique")
        with st.container(key="zone-opinion", border=False):
            render_opinion(result, patient["id"])
