"""RAG documents: list of the PDFs indexed in ChromaDB, upload of a PDF and rendering of a page.

The indexing itself is done by indexing.py (index_pdf)."""

import os

import pymupdf

from indexing import PDF_FOLDER, get_collection, index_pdf  # noqa: F401 (index_pdf is used by the pages)


def indexed_documents():
    """Returns {pdf_name: passage_count} for the documents present in ChromaDB."""
    counts = {}
    for meta in get_collection().get(include=["metadatas"])["metadatas"]:
        counts[meta["source"]] = counts.get(meta["source"], 0) + 1
    return dict(sorted(counts.items()))


def folder_documents():
    if not os.path.isdir(PDF_FOLDER):
        return []
    return sorted(f for f in os.listdir(PDF_FOLDER) if f.lower().endswith(".pdf"))


def document_path(name):
    # basename: prevents leaving the folder with a name such as "../../file.pdf"
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


def render_page(path, page, dpi=110):
    """Returns the PNG image (bytes) of the requested page (numbered from 1)."""
    with pymupdf.open(path) as document:
        page = min(max(page, 1), document.page_count)
        return document[page - 1].get_pixmap(dpi=dpi).tobytes("png")
