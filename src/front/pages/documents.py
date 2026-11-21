"""“Documents du RAG” page: indexed guidelines (viewing), PDFs waiting to be indexed and upload of new guidelines."""

import streamlit as st

from src.front.components.dialogs import open_document
from src.front.components.widgets import label
from src.front.services.documents import document_path, folder_documents, index_pdf, indexed_documents, save_pdf


def render_documents_page():
    st.caption(
        "Référentiels (PDF) dans lesquels le RAG recherche les passages utiles à l'analyse de chaque patient. "
        "Les documents sont enregistrés dans src/rag/RAG_Docs/ et indexés dans la base vectorielle."
    )
    indexed = indexed_documents()
    _indexed(indexed)
    _not_indexed(indexed)
    _add_guideline()


def _indexed(indexed):
    label(f"Référentiels indexés ({len(indexed)})")
    if not indexed:
        st.info("Aucun référentiel indexé.")
    for name, passage_count in indexed.items():
        name_column, button_column = st.columns([5, 1], vertical_alignment="center")
        name_column.markdown(f"**{name}** · {passage_count} passages")
        if button_column.button("Consulter", key=f"doc-{name}", use_container_width=True):
            open_document(name)


def _not_indexed(indexed):
    """PDFs present in src/rag/RAG_Docs/ but not in the vector database."""
    not_indexed = [name for name in folder_documents() if name not in indexed]
    if not not_indexed:
        return
    label(f"En attente d'indexation ({len(not_indexed)})")
    for name in not_indexed:
        name_column, button_column = st.columns([5, 1], vertical_alignment="center")
        name_column.markdown(f"**{name}**")
        if button_column.button("Indexer", key=f"index-{name}", use_container_width=True):
            with st.spinner(f"Indexation de {name} en cours..."):
                count = index_pdf(document_path(name))
            st.toast(f"{name} : {count} passages indexés")
            st.rerun()


def _add_guideline():
    label("Ajouter un référentiel")
    with st.form("add_document", clear_on_submit=True, border=False):
        files = st.file_uploader(
            "Documents PDF", type="pdf", accept_multiple_files=True, label_visibility="collapsed",
            help="Le document est enregistré dans les documents du RAG, puis indexé.",
        )
        submitted = st.form_submit_button("Indexer les documents", type="primary")
    if submitted and files:
        for file in files:
            with st.spinner(f"Indexation de {file.name} en cours..."):
                try:
                    count = index_pdf(save_pdf(file.name, file.getvalue()))
                    st.toast(f"{file.name} : {count} passages indexés")
                except Exception as error:
                    st.error(f"{file.name} : {error}")
        st.rerun()
