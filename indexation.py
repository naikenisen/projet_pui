"""Découpe les PDF de base_documentaire/ en passages, calcule leurs embeddings et les stocke dans ChromaDB."""

import os

import chromadb
import pymupdf4llm
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])

DOSSIER_PDF = "base_documentaire"
CHROMA_DIR = "chroma_db"
COLLECTION_NAME = "base_documentaire"
EMBEDDING_MODEL = "qwen/qwen3-embedding-8b"

TAILLE_PASSAGE = 1500
CHEVAUCHEMENT = 200


def decouper(texte):
    passages = []
    debut = 0
    while debut < len(texte):
        passages.append(texte[debut:debut + TAILLE_PASSAGE])
        debut += TAILLE_PASSAGE - CHEVAUCHEMENT
    return passages


def extraire_passages(chemin_pdf):
    nom_pdf = os.path.basename(chemin_pdf)
    pages = pymupdf4llm.to_markdown(chemin_pdf, page_chunks=True, use_ocr=False)

    passages = []
    for numero_page, page in enumerate(pages, start=1):
        for numero_passage, texte in enumerate(decouper(page["text"])):
            passages.append({
                "id": f"{nom_pdf}-page{numero_page}-{numero_passage}",
                "texte": texte,
                "source": nom_pdf,
                "page": numero_page,
            })
    return passages


def calculer_embeddings(textes):
    vecteurs = []
    for debut in range(0, len(textes), 32):
        reponse = client.embeddings.create(model=EMBEDDING_MODEL, input=textes[debut:debut + 32])
        for element in reponse.data:
            vecteurs.append(element.embedding)
    return vecteurs


if __name__ == "__main__":
    chroma = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = chroma.get_or_create_collection(
        COLLECTION_NAME,
        embedding_function=None,
        metadata={"hnsw:space": "cosine"},
    )

    for nom_fichier in sorted(os.listdir(DOSSIER_PDF)):
        if not nom_fichier.endswith(".pdf"):
            continue

        passages = extraire_passages(os.path.join(DOSSIER_PDF, nom_fichier))
        textes = [p["texte"] for p in passages]

        collection.upsert(
            ids=[p["id"] for p in passages],
            documents=textes,
            metadatas=[{"source": p["source"], "page": p["page"]} for p in passages],
            embeddings=calculer_embeddings(textes),
        )
        print(f"{nom_fichier} : {len(passages)} passages indexés")
