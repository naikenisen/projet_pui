"""
Récupération (retrieval) du RAG.

Prend en entrée UN dossier patient de input.json et retourne le texte des passages
les plus pertinents de la base documentaire (ChromaDB indexée par embedding.py),
prêt à être injecté dans le prompt de génération.
"""

import argparse
import json
import os
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from openai import OpenAI

# Même configuration que l'indexation : la requête DOIT utiliser le même modèle d'embedding.
from indexation import CHROMA_DIR, COLLECTION_NAME, EMBEDDING_MODEL

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

N_PAR_REQUETE = 3   # passages récupérés pour chaque requête
MAX_PASSAGES = 8    # passages conservés au total (après dédoublonnage)

# Qwen3-Embedding : les requêtes sont précédées d'une instruction (pas les documents).
INSTRUCTION = (
    "Instruct: Étant donné un traitement et le profil d'un patient, retrouver les passages "
    "de recommandations médicales pertinents pour analyser la prescription\nQuery: "
)


def construire_requetes(dossier: dict) -> list[str]:
    """Construit une requête par traitement, enrichie du terrain du patient."""
    patient = dossier["patient"]
    biologie = patient.get("biologie", {})

    terrain = [f"patient de {patient.get('age')} ans"]
    if "creatinine_serique" in biologie:
        terrain.append(f"DFG {biologie['creatinine_serique']} mL/min/1,73m²")
    if "HbA1c_pourcent" in biologie:
        terrain.append(f"HbA1c {biologie['HbA1c_pourcent']} %")
    terrain = ", ".join(terrain)

    requetes = []
    for t in dossier.get("traitements", []):
        nom = t["dci"] + (f" ({t['specialite']})" if t.get("specialite") else "")
        requetes.append(f"{nom} {t.get('dosage', '')} {t.get('unite', '')}, {t.get('posologie', '')} — {terrain}")
    return requetes


def recuperer_passages(dossier: dict) -> list[dict]:
    """Interroge ChromaDB et retourne les passages pertinents (dédoublonnés, triés par pertinence)."""
    collection = chromadb.PersistentClient(path=str(CHROMA_DIR)).get_collection(COLLECTION_NAME)

    requetes = construire_requetes(dossier)
    if not requetes:
        return []

    reponse = client.embeddings.create(model=EMBEDDING_MODEL, input=[INSTRUCTION + r for r in requetes])
    vecteurs = [d.embedding for d in sorted(reponse.data, key=lambda d: d.index)]

    resultats = collection.query(
        query_embeddings=vecteurs,
        n_results=N_PAR_REQUETE,
        include=["documents", "metadatas", "distances"],
    )

    # Un même passage peut sortir pour plusieurs traitements : on garde sa meilleure distance.
    passages = {}
    for ids, docs, metas, dists in zip(
        resultats["ids"], resultats["documents"], resultats["metadatas"], resultats["distances"]
    ):
        for id_, doc, meta, dist in zip(ids, docs, metas, dists):
            if id_ not in passages or dist < passages[id_]["distance"]:
                passages[id_] = {"texte": doc, "metadata": meta, "distance": dist}

    return sorted(passages.values(), key=lambda p: p["distance"])[:MAX_PASSAGES]


def recuperer_contexte(dossier: dict) -> str:
    """Retourne le texte des passages récupérés, formaté pour être injecté dans un prompt."""
    blocs = []
    for i, p in enumerate(recuperer_passages(dossier), 1):
        meta = p["metadata"]
        reference = f"{meta.get('source', '?')}, page {meta.get('page', '?')}"
        if meta.get("avis"):
            reference += f", Avis n° {meta['avis']}"
        blocs.append(f"[Extrait {i} — {reference}]\n{p['texte']}")
    return "\n\n---\n\n".join(blocs)


def charger_patient(patient_id: str, fichier: Path = Path(__file__).parent / "input.json") -> dict:
    """Retourne le dossier du patient d'identifiant patient_id dans input.json."""
    dossiers = json.loads(fichier.read_text(encoding="utf-8"))
    if isinstance(dossiers, dict):
        dossiers = [dossiers]
    for dossier in dossiers:
        if dossier["patient"].get("id") == patient_id:
            return dossier
    ids = ", ".join(d["patient"].get("id", "?") for d in dossiers)
    raise SystemExit(f"Patient '{patient_id}' introuvable dans {fichier.name}. Patients disponibles : {ids}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Récupère les passages de la base documentaire pour un patient.")
    parser.add_argument("--patient", required=True, help="identifiant du patient (ex : PAT-0001)")
    args = parser.parse_args()

    dossier = charger_patient(args.patient)
    print("Requêtes :")
    for r in construire_requetes(dossier):
        print(f"  - {r}")
    print("\nContexte récupéré :\n")
    print(recuperer_contexte(dossier))
