"""RAG documents: list of the PDFs indexed in ChromaDB, indexing of a PDF and rendering of a page."""

import os

import chromadb
import pymupdf

from indexing import (
    CHROMA_DIR,
    COLLECTION_NAME,
    PDF_FOLDER,
    compute_embeddings,
    extract_passages,
)


def _collection(create=False):
    chroma = chromadb.PersistentClient(path=CHROMA_DIR)
    if create:
        # Same parameters as indexing.py
        return chroma.get_or_create_collection(
            COLLECTION_NAME, embedding_function=None, metadata={"hnsw:space": "cosine"}
        )
    try:
        return chroma.get_collection(COLLECTION_NAME, embedding_function=None)
    except Exception:
        return None


def indexed_documents():
    """Returns {pdf_name: passage_count} for the documents present in ChromaDB."""
    collection = _collection()
    if collection is None:
        return {}
    counts = {}
    for meta in collection.get(include=["metadatas"])["metadatas"]:
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


def index_pdf(path):
    """Indexes a PDF (replacing its previous passages if it was already indexed). Returns the passage count."""
    name = os.path.basename(path)
    passages = extract_passages(path)
    texts = [p["text"] for p in passages]
    collection = _collection(create=True)
    collection.delete(where={"source": name})
    if passages:
        collection.upsert(
            ids=[p["id"] for p in passages],
            documents=texts,
            metadatas=[{"source": p["source"], "page": p["page"]} for p in passages],
            embeddings=compute_embeddings(texts),
        )
    return len(passages)


def page_count(path):
    with pymupdf.open(path) as document:
        return document.page_count


def render_page(path, page, dpi=110):
    """Returns the PNG image (bytes) of the requested page (numbered from 1)."""
    with pymupdf.open(path) as document:
        page = min(max(page, 1), document.page_count)
        return document[page - 1].get_pixmap(dpi=dpi).tobytes("png")
