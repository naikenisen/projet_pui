# "Documents du RAG" page: indexed guidelines, indexing, PDF upload and viewer.

import os

import pymupdf
import streamlit as st

from indexing import PDF_FOLDER, get_collection, index_pdf
from ui.common import label


def render_page():
    indexed = indexed_documents()
    _indexed(indexed)
    _not_indexed(indexed)
    _add_guideline()


# {PDF name: number of passages} of the documents stored in ChromaDB
def indexed_documents():
    counts = {}
    for meta in get_collection(backend=st.session_state.backend).get(include=["metadatas"])["metadatas"]:
        counts[meta["source"]] = counts.get(meta["source"], 0) + 1
    return dict(sorted(counts.items()))


def folder_documents():
    if not os.path.isdir(PDF_FOLDER):
        return []
    return sorted(f for f in os.listdir(PDF_FOLDER) if f.lower().endswith(".pdf"))


# basename prevents leaving the folder with a name like "../../file.pdf"
def document_path(name):
    return os.path.join(PDF_FOLDER, os.path.basename(name))


def save_pdf(name, content):
    os.makedirs(PDF_FOLDER, exist_ok=True)
    path = document_path(name)
    with open(path, "wb") as file:
        file.write(content)
    return path


def page_count(path):
    with pymupdf.open(path) as document:
        return document.page_count


# PNG image of the requested page, numbered from 1
def page_image(path, page, dpi=110):
    with pymupdf.open(path) as document:
        page = min(max(page, 1), document.page_count)
        return document[page - 1].get_pixmap(dpi=dpi).tobytes("png")


@st.dialog("Consultation du document", width="large")
def open_document(name, page=1):
    path = document_path(name)
    if not os.path.exists(path):
        st.error(f"Le document « {name} » est introuvable dans les documents du RAG.")
        return

    total = page_count(path)
    st.markdown(f"**{name}**")
    page_column, download_column = st.columns([1, 1], vertical_alignment="bottom")
    page = page_column.number_input(
        f"Page (sur {total})", min_value=1, max_value=total, value=min(page, total), key=f"page-{name}-{page}"
    )
    with open(path, "rb") as file:
        download_column.download_button(
            "Télécharger le PDF", file.read(), file_name=name, mime="application/pdf",
            use_container_width=True,
        )
    st.image(page_image(path, page))


def _indexed(indexed):
    label(f"Référentiels indexés ({len(indexed)})")
    if not indexed:
        st.info("Aucun référentiel indexé.")
    for name, passage_count in indexed.items():
        name_column, button_column = st.columns([5, 1], vertical_alignment="center")
        name_column.markdown(f"**{name}** · {passage_count} passages")
        if button_column.button("Consulter", key=f"doc-{name}", use_container_width=True):
            open_document(name)


# PDFs in the folder but missing from the vector database
def _not_indexed(indexed):
    not_indexed = [name for name in folder_documents() if name not in indexed]
    if not not_indexed:
        return
    label(f"En attente d'indexation ({len(not_indexed)})")
    for name in not_indexed:
        name_column, button_column = st.columns([5, 1], vertical_alignment="center")
        name_column.markdown(f"**{name}**")
        if button_column.button("Indexer", key=f"index-{name}", use_container_width=True):
            with st.spinner(f"Indexation de {name} en cours..."):
                count = index_pdf(document_path(name), backend=st.session_state.backend)
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
                    count = index_pdf(save_pdf(file.name, file.getvalue()), backend=st.session_state.backend)
                    st.toast(f"{file.name} : {count} passages indexés")
                except Exception as error:
                    st.error(f"{file.name} : {error}")
        st.rerun()
