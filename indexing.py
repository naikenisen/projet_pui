"""Splits the PDFs of src/rag/RAG_Docs/ into passages, computes their embeddings and stores them in ChromaDB."""

import os

import chromadb
import pymupdf4llm
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])

RAG_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "rag")
PDF_FOLDER = os.path.join(RAG_FOLDER, "RAG_Docs")
CHROMA_DIR = os.path.join(RAG_FOLDER, "chroma_db")
COLLECTION_NAME = "rag_docs"
EMBEDDING_MODEL = "qwen/qwen3-embedding-8b"

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


def compute_embeddings(texts):
    vectors = []
    for start in range(0, len(texts), 32):
        response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts[start:start + 32])
        for element in response.data:
            vectors.append(element.embedding)
    return vectors


def get_collection():
    chroma = chromadb.PersistentClient(path=CHROMA_DIR)
    return chroma.get_or_create_collection(COLLECTION_NAME, embedding_function=None, metadata={"hnsw:space": "cosine"})


def index_pdf(pdf_path):
    """Replaces the passages of the PDF in ChromaDB (old ones are deleted). Returns the number of passages."""
    passages = extract_passages(pdf_path)
    texts = [p["text"] for p in passages]
    embeddings = compute_embeddings(texts)

    collection = get_collection()
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
    for file_name in sorted(os.listdir(PDF_FOLDER)):
        if file_name.endswith(".pdf"):
            count = index_pdf(os.path.join(PDF_FOLDER, file_name))
            print(f"{file_name}: {count} passages indexed")
