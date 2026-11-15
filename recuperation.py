"""Cherche dans ChromaDB les passages de la base documentaire utiles pour analyser un patient."""

import argparse
import json
import os

import chromadb
from dotenv import load_dotenv
from openai import OpenAI

from indexation import CHROMA_DIR, COLLECTION_NAME, EMBEDDING_MODEL

load_dotenv()
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])

NOMBRE_PAR_REQUETE = 3
NOMBRE_MAX_PASSAGES = 8

# Préfixe recommandé par Qwen3-Embedding pour les requêtes (les documents n'en ont pas).
INSTRUCTION = "Instruct: Retrouver les recommandations médicales utiles pour analyser cette prescription\nQuery: "


def construire_requetes(dossier):
    patient = dossier["patient"]
    terrain = (
        f"patient de {patient['age']} ans, {patient['poids_kg']} kg, "
        f"créatinine {patient['biologie']['creatinine_serique']} µmol/L"
    )

    requetes = []
    for traitement in dossier["traitements"]:
        requetes.append(
            f"{traitement['dci']} {traitement['dosage']} {traitement['unite']}, {traitement['posologie']}, {terrain}"
        )
    return requetes


def recuperer_contexte(dossier):
    requetes = construire_requetes(dossier)
    reponse = client.embeddings.create(model=EMBEDDING_MODEL, input=[INSTRUCTION + r for r in requetes])
    vecteurs = [element.embedding for element in reponse.data]

    collection = chromadb.PersistentClient(path=CHROMA_DIR).get_collection(COLLECTION_NAME, embedding_function=None)
    resultats = collection.query(query_embeddings=vecteurs, n_results=NOMBRE_PAR_REQUETE)

    # Un même passage peut être trouvé par plusieurs requêtes : on ne le garde qu'une fois.
    passages = {}
    for i in range(len(requetes)):
        for id_passage, texte, meta, distance in zip(
            resultats["ids"][i], resultats["documents"][i], resultats["metadatas"][i], resultats["distances"][i]
        ):
            if id_passage not in passages or distance < passages[id_passage]["distance"]:
                passages[id_passage] = {"texte": texte, "source": meta["source"], "page": meta["page"], "distance": distance}

    meilleurs = sorted(passages.values(), key=lambda p: p["distance"])[:NOMBRE_MAX_PASSAGES]

    contexte = ""
    for p in meilleurs:
        contexte += f"[{p['source']}, page {p['page']}]\n{p['texte']}\n\n"
    return contexte


def charger_patient(patient_id):
    with open("input.json", encoding="utf-8") as fichier:
        patients = json.load(fichier)
    for dossier in patients:
        if dossier["patient"]["id"] == patient_id:
            return dossier
    raise SystemExit(f"Patient introuvable : {patient_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--idpatient", required=True)
    args = parser.parse_args()

    print(recuperer_contexte(charger_patient(args.idpatient)))
