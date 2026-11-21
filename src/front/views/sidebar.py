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
    section_title("Patient base")
    folder = st.text_input(
        "Inference folder", value=PATIENTS_FOLDER, key="patients_folder",
        help="Folder containing one JSON file per patient (path relative to the project root, or absolute).",
    ).strip()
    if os.path.isdir(folder):
        try:
            patients = load_patients(folder)
        except Exception as error:
            patients = []
            st.error(f"Unable to read the patient records: {error}")
    else:
        patients = []
        st.error(f"The folder “{folder}” does not exist.")
    st.metric("Patient records", len(patients))
    return folder, patients


def _rag_documents():
    """Indexed documents (click to view) and documents of the folder waiting to be indexed."""
    section_title("RAG documents")
    try:
        indexed = indexed_documents()
    except Exception as error:
        indexed = {}
        st.error(f"Unable to read the vector database: {error}")

    if indexed:
        st.caption("Indexed guidelines. Click to view.")
        for name, passage_count in indexed.items():
            if st.button(f"{name}  ·  {passage_count} passages", key=f"doc-{name}", use_container_width=True):
                open_document(name)
    else:
        st.info("No indexed guideline.")

    not_indexed = [name for name in folder_documents() if name not in indexed]
    if not_indexed:
        st.caption("Documents waiting to be indexed")
        for name in not_indexed:
            name_column, button_column = st.columns([3, 2], vertical_alignment="center")
            name_column.markdown(f"`{name}`")
            if button_column.button("Index", key=f"index-{name}", use_container_width=True):
                with st.spinner(f"Indexing {name}..."):
                    count = index_pdf(document_path(name))
                st.toast(f"{name}: {count} passages indexed")
                st.rerun()
    return indexed


def _add_guideline():
    section_title("Add a guideline")
    with st.form("add_document", clear_on_submit=True, border=False):
        files = st.file_uploader(
            "PDF documents", type="pdf", accept_multiple_files=True, label_visibility="collapsed",
            help="The document is saved in the RAG documents, then indexed.",
        )
        submitted = st.form_submit_button("Index the documents", use_container_width=True)
    if submitted and files:
        for file in files:
            with st.spinner(f"Indexing {file.name}..."):
                try:
                    count = index_pdf(save_pdf(file.name, file.getvalue()))
                    st.toast(f"{file.name}: {count} passages indexed")
                except Exception as error:
                    st.error(f"{file.name}: {error}")
        st.rerun()
