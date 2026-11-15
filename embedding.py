"""
Indexation de la base documentaire pour le RAG.

- Parse les PDF de base_documentaire/ en Markdown avec pymupdf4llm (garde titres et tableaux).
- Découpe le texte en passages (chunks) avec chevauchement.
- Calcule les embeddings via l'API OpenRouter (compatible OpenAI).
- Stocke passages + embeddings + métadonnées dans ChromaDB (mode local, sur disque).

Usage :
    python embedding.py            # indexe / réindexe tous les PDF
    python embedding.py --reset    # supprime la collection avant de réindexer
"""

import argparse
import os
import re
from pathlib import Path

import chromadb
import pymupdf4llm
from dotenv import load_dotenv
from openai import OpenAI

# --- Configuration -----------------------------------------------------------

BASE_DIR = Path(__file__).parent
DOCS_DIR = BASE_DIR / "base_documentaire"
CHROMA_DIR = BASE_DIR / "chroma_db"
COLLECTION_NAME = "base_documentaire"

# Modèle multilingue (très bon en français), contexte long, peu coûteux.
# Alternatives sur OpenRouter : "baai/bge-m3", "openai/text-embedding-3-large".
# Attention : la requête (côté recherche) devra utiliser le MÊME modèle.
EMBEDDING_MODEL = "qwen/qwen3-embedding-8b"

CHUNK_SIZE = 1500      # taille cible d'un passage, en caractères
CHUNK_OVERLAP = 200    # chevauchement entre passages consécutifs
BATCH_SIZE = 32        # nombre de passages envoyés par appel d'API

# Repère les "Avis n° X" de la reco SFD pour l'ajouter en métadonnée.
AVIS_RE = re.compile(r"Avis\s*n\s*[°o]?\s*(\d+\s*(?:bis|ter)?)", re.IGNORECASE)
HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)


# --- Parsing & découpage -----------------------------------------------------

def parse_pdf(pdf_path: Path) -> list[dict]:
    """Retourne une liste de pages : {"page": int, "text": str} (texte en Markdown)."""
    pages = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True)
    return [
        {"page": p["metadata"].get("page", i + 1), "text": p["text"]}
        for i, p in enumerate(pages)
    ]


def split_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Découpe en passages de ~size caractères, en coupant de préférence entre paragraphes."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, current = [], ""

    for para in paragraphs:
        # Paragraphe trop long à lui seul (gros tableau...) : on le coupe brutalement.
        while len(para) > size:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(para[:size])
            para = para[size - overlap:]

        if len(current) + len(para) + 2 <= size:
            current = f"{current}\n\n{para}" if current else para
        else:
            chunks.append(current)
            # On reprend la fin du passage précédent pour garder du contexte.
            current = f"{current[-overlap:]}\n\n{para}"

    if current:
        chunks.append(current)
    return chunks


def build_chunks(pdf_path: Path) -> list[dict]:
    """Parse un PDF et retourne ses passages avec leurs métadonnées."""
    chunks = []
    last_heading, last_avis = "", ""

    for page in parse_pdf(pdf_path):
        for i, text in enumerate(split_text(page["text"])):
            # On mémorise le dernier titre / avis rencontré, même sur les pages précédentes.
            headings = HEADING_RE.findall(text)
            if headings:
                last_heading = headings[-1].strip()
            avis = AVIS_RE.findall(text)
            if avis:
                last_avis = re.sub(r"\s+", " ", avis[-1]).strip()

            chunks.append({
                "id": f"{pdf_path.stem}-p{page['page']}-c{i}",
                "text": text,
                "metadata": {
                    "source": pdf_path.name,
                    "page": page["page"],
                    "section": last_heading,
                    "avis": last_avis,
                },
            })
    return chunks


# --- Embeddings --------------------------------------------------------------

def embed(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Calcule les embeddings d'une liste de textes via OpenRouter, par lots."""
    vectors = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        response = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        vectors.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))
        print(f"  embeddings {start + len(batch)}/{len(texts)}")
    return vectors


# --- Main --------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="supprime la collection avant indexation")
    args = parser.parse_args()

    load_dotenv()
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
    )

    chroma = chromadb.PersistentClient(path=str(CHROMA_DIR))
    if args.reset:
        try:
            chroma.delete_collection(COLLECTION_NAME)
            print(f"Collection '{COLLECTION_NAME}' supprimée.")
        except Exception:
            pass

    # embedding_function=None : on fournit nous-mêmes les vecteurs (pas de modèle local Chroma).
    collection = chroma.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=None,
        metadata={"hnsw:space": "cosine", "embedding_model": EMBEDDING_MODEL},
    )

    pdfs = sorted(DOCS_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"Aucun PDF trouvé dans {DOCS_DIR}")
        return

    for pdf in pdfs:
        print(f"\n{pdf.name}")
        chunks = build_chunks(pdf)
        print(f"  {len(chunks)} passages")

        # Réindexation propre : on retire les anciens passages de ce document.
        collection.delete(where={"source": pdf.name})

        collection.add(
            ids=[c["id"] for c in chunks],
            documents=[c["text"] for c in chunks],
            metadatas=[c["metadata"] for c in chunks],
            embeddings=embed(client, [c["text"] for c in chunks]),
        )

    print(f"\nTerminé : {collection.count()} passages dans '{COLLECTION_NAME}' ({CHROMA_DIR}).")


if __name__ == "__main__":
    main()
