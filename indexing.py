# Splits the RAG PDFs into passages, computes their embeddings and stores them in ChromaDB.

import argparse
import os
import re

import chromadb
import pymupdf4llm

from inference import EMBEDDING_MODEL, InferenceBackend, add_inference_arguments, backend_from_args

RAG_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ressources", "rag")
PDF_FOLDER = os.path.join(RAG_FOLDER, "RAG_Docs")
CHROMA_DIR = os.path.join(RAG_FOLDER, "chroma_db")
COLLECTION_NAME = "rag_docs"

# In characters
PASSAGE_SIZE = 1500
OVERLAP = 200


def split(text):
    passages = []
    start = 0
    while start < len(text):
        passages.append(text[start:start + PASSAGE_SIZE])
        start += PASSAGE_SIZE - OVERLAP
    return passages


def extract_passages(pdf_path):
    pdf_name = os.path.basename(pdf_path)
    pages = pymupdf4llm.to_markdown(pdf_path, page_chunks=True, use_ocr=False)

    passages = []
    for page_number, page in enumerate(pages, start=1):
        for passage_number, text in enumerate(split(page["text"])):
            passages.append({
                "id": f"{pdf_name}-page{page_number}-{passage_number}",
                "text": text,
                "source": pdf_name,
                "page": page_number,
            })
    return passages


def compute_embeddings(texts, backend: InferenceBackend | None = None):
    backend = backend if backend is not None else InferenceBackend()
    vectors = []
    for start in range(0, len(texts), 32):
        vectors.extend(backend.embed(texts[start:start + 32]))
    return vectors


def get_collection(backend: InferenceBackend | None = None):
    backend = backend if backend is not None else InferenceBackend()
    chroma = chromadb.PersistentClient(path=CHROMA_DIR)
    return chroma.get_or_create_collection(COLLECTION_NAME, embedding_function=None, metadata={"hnsw:space": "cosine"})


# Replaces the PDF passages in ChromaDB and returns their count
def index_pdf(pdf_path, backend: InferenceBackend | None = None):
    passages = extract_passages(pdf_path)
    texts = [p["text"] for p in passages]
    embeddings = compute_embeddings(texts, backend=backend)

    collection = get_collection(backend=backend)
    collection.delete(where={"source": os.path.basename(pdf_path)})
    if passages:
        collection.upsert(
            ids=[p["id"] for p in passages],
            documents=texts,
            metadatas=[{"source": p["source"], "page": p["page"]} for p in passages],
            embeddings=embeddings,
        )
    return len(passages)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    add_inference_arguments(parser)
    args = parser.parse_args()
    backend = backend_from_args(args)
    for file_name in sorted(os.listdir(PDF_FOLDER)):
        if file_name.endswith(".pdf"):
            count = index_pdf(os.path.join(PDF_FOLDER, file_name), backend=backend)
            print(f"{file_name}: {count} passages indexed")
