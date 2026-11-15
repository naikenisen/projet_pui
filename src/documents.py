"""Base documentaire : liste des PDF indexés dans ChromaDB, indexation d'un PDF et rendu d'une page."""

import os

import chromadb
import pymupdf

from indexation import (
    CHROMA_DIR,
    COLLECTION_NAME,
    DOSSIER_PDF,
    calculer_embeddings,
    extraire_passages,
)


def _collection(creer=False):
    chroma = chromadb.PersistentClient(path=CHROMA_DIR)
    if creer:
        # Mêmes paramètres que indexation.py
        return chroma.get_or_create_collection(
            COLLECTION_NAME, embedding_function=None, metadata={"hnsw:space": "cosine"}
        )
    try:
        return chroma.get_collection(COLLECTION_NAME, embedding_function=None)
    except Exception:
        return None


def documents_indexes():
    """Renvoie {nom_pdf: nombre_de_passages} pour les documents présents dans ChromaDB."""
    collection = _collection()
    if collection is None:
        return {}
    compte = {}
    for meta in collection.get(include=["metadatas"])["metadatas"]:
        compte[meta["source"]] = compte.get(meta["source"], 0) + 1
    return dict(sorted(compte.items()))


def documents_du_dossier():
    if not os.path.isdir(DOSSIER_PDF):
        return []
    return sorted(f for f in os.listdir(DOSSIER_PDF) if f.lower().endswith(".pdf"))


def chemin_document(nom):
    # basename : empêche de sortir du dossier avec un nom du type "../../fichier.pdf"
    return os.path.join(DOSSIER_PDF, os.path.basename(nom))


def enregistrer_pdf(nom, contenu):
    os.makedirs(DOSSIER_PDF, exist_ok=True)
    chemin = chemin_document(nom)
    with open(chemin, "wb") as fichier:
        fichier.write(contenu)
    return chemin


def indexer_pdf(chemin):
    """Indexe un PDF (en remplaçant ses anciens passages s'il était déjà indexé). Renvoie le nombre de passages."""
    nom = os.path.basename(chemin)
    passages = extraire_passages(chemin)
    textes = [p["texte"] for p in passages]
    collection = _collection(creer=True)
    collection.delete(where={"source": nom})
    if passages:
        collection.upsert(
            ids=[p["id"] for p in passages],
            documents=textes,
            metadatas=[{"source": p["source"], "page": p["page"]} for p in passages],
            embeddings=calculer_embeddings(textes),
        )
    return len(passages)


def nombre_pages(chemin):
    with pymupdf.open(chemin) as document:
        return document.page_count


def rendre_page(chemin, page, dpi=110):
    """Renvoie l'image PNG (bytes) de la page demandée (numérotée à partir de 1)."""
    with pymupdf.open(chemin) as document:
        page = min(max(page, 1), document.page_count)
        return document[page - 1].get_pixmap(dpi=dpi).tobytes("png")
