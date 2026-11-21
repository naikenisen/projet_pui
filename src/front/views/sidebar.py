"""Sidebar: choice of the patient folder, RAG documents (viewing, indexing) and upload of new guidelines."""

import os

import streamlit as st

from src.front.components.dialogs import open_document
from src.front.components.widgets import section_title
from src.front.services.data import PATIENTS_FOLDER, load_patients
from src.front.services.documents import document_path, folder_documents, index_pdf, indexed_documents, save_pdf


def render_sidebar():
    """Returns (folder, patients, indexed): the chosen folder, its records and the indexed documents."""
    with st.sidebar:
        folder, patients = _patient_base()
        indexed = _rag_documents()
        _add_guideline()
    return folder, patients, indexed


def _patient_base():
    section_title("Base patients")
    folder = st.text_input(
        "Dossier d'inférence", value=PATIENTS_FOLDER, key="patients_folder",
        help="Dossier contenant un fichier JSON par patient (chemin relatif à la racine du projet ou absolu).",
    ).strip()
    if os.path.isdir(folder):
        try:
            patients = load_patients(folder)
        except Exception as error:
            patients = []
            st.error(f"Lecture des dossiers patients impossible : {error}")
    else:
        patients = []
        st.error(f"Le dossier « {folder} » n'existe pas.")
    st.metric("Dossiers patients", len(patients))
    return folder, patients


def _rag_documents():
    """Indexed documents (click to view) and documents of the folder waiting to be indexed."""
    section_title("Documents du RAG")
    try:
        indexed = indexed_documents()
    except Exception as error:
        indexed = {}
        st.error(f"Lecture de la base vectorielle impossible : {error}")

    if indexed:
        st.caption("Référentiels indexés. Cliquer pour consulter.")
        for name, passage_count in indexed.items():
            if st.button(f"{name}  ·  {passage_count} passages", key=f"doc-{name}", use_container_width=True):
                open_document(name)
    else:
        st.info("Aucun référentiel indexé.")

    not_indexed = [name for name in folder_documents() if name not in indexed]
    if not_indexed:
        st.caption("Documents en attente d'indexation")
        for name in not_indexed:
            name_column, button_column = st.columns([3, 2], vertical_alignment="center")
            name_column.markdown(f"`{name}`")
            if button_column.button("Indexer", key=f"index-{name}", use_container_width=True):
                with st.spinner(f"Indexation de {name} en cours..."):
                    count = index_pdf(document_path(name))
                st.toast(f"{name} : {count} passages indexés")
                st.rerun()
    return indexed


def _add_guideline():
    section_title("Ajouter un référentiel")
    with st.form("add_document", clear_on_submit=True, border=False):
        files = st.file_uploader(
            "Documents PDF", type="pdf", accept_multiple_files=True, label_visibility="collapsed",
            help="Le document est enregistré dans les documents du RAG, puis indexé.",
        )
        submitted = st.form_submit_button("Indexer les documents", use_container_width=True)
    if submitted and files:
        for file in files:
            with st.spinner(f"Indexation de {file.name} en cours..."):
                try:
                    count = index_pdf(save_pdf(file.name, file.getvalue()))
                    st.toast(f"{file.name} : {count} passages indexés")
                except Exception as error:
                    st.error(f"{file.name} : {error}")
        st.rerun()
