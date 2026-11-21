"""Dialogs (document viewer, KBS alert) and the buttons that open them."""

import os

import streamlit as st

from src.front.components.widgets import show_alert
from src.front.rendering.opinion import read_source
from src.front.services.documents import document_path, page_count, render_page


@st.dialog("Document viewer", width="large")
def open_document(name, page=1):
    path = document_path(name)
    if not os.path.exists(path):
        st.error(f"The document “{name}” cannot be found in the RAG documents.")
        return

    total = page_count(path)
    st.markdown(f"**{name}**")
    page_column, download_column = st.columns([1, 1], vertical_alignment="bottom")
    page = page_column.number_input(
        f"Page (of {total})", min_value=1, max_value=total, value=min(page, total), key=f"page-{name}-{page}"
    )
    with open(path, "rb") as file:
        download_column.download_button(
            "Download PDF", file.read(), file_name=name, mime="application/pdf",
            use_container_width=True,
        )
    st.image(render_page(path, page))


@st.dialog("KBS alert", width="large")
def open_alert(alert):
    show_alert(alert)


def source_button(source, key):
    """Shows a button that opens the source if it is a PDF of the RAG documents, otherwise plain text."""
    document = read_source(source)
    if document is None:
        st.markdown(f"- {source}")
        return
    name, page = document
    if st.button(source, key=key, help=f"Open {name} at page {page}"):
        open_document(name, page)


def alert_link(alert, key):
    """“KBS alert” link: hovering shows the alert, clicking opens it in detail."""
    if st.button("KBS alert", key=key, type="tertiary", help=alert):
        open_alert(alert)


def source_links(sources, key):
    """Links to the sources of a point of the opinion: KBS alerts and PDF pages."""
    for number, source in enumerate(sources):
        if source["type"] == "alert":
            alert_link(source["text"], key=f"{key}-{number}")
        elif st.button(f"{source['source']}, p. {source['page']}", key=f"{key}-{number}", type="tertiary",
                       help=f"Open {source['source']} at page {source['page']}"):
            open_document(source["source"], source["page"])
