"""Cherche dans ChromaDB les passages de la base documentaire utiles pour analyser un patient."""

import argparse
import json
import os

import chromadb
from dotenv import load_dotenv
from openai import OpenAI

from expert_system import charger_patient
from indexation import CHROMA_DIR, COLLECTION_NAME, EMBEDDING_MODEL

load_dotenv()
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])

NOMBRE_PAR_REQUETE = 3
NOMBRE_MAX_PASSAGES = 8

# Préfixe recommandé par Qwen3-Embedding pour les requêtes (les documents n'en ont pas).
INSTRUCTION = "Instruct: Retrouver les recommandations médicales utiles pour analyser cette prescription\nQuery: "


def bio_anormales(patient):
    with open("bio_anormale.json", encoding="utf-8") as fichier:
        normes = json.load(fichier)

    anomalies = []
    for nom, mesure in patient["biologie"].items():
        if nom not in normes or not isinstance(mesure.get("valeur"), (int, float)):
            continue
        norme = normes[nom]
        valeur = mesure["valeur"]
        unite = mesure.get("unite") or norme["unite"]
        if valeur < norme["min"]:
            anomalies.append(f"{norme['libelle']} basse ({valeur} {unite})")
        elif valeur > norme["max"]:
            anomalies.append(f"{norme['libelle']} élevée ({valeur} {unite})")
    return anomalies


def construire_requetes(dossier):
    patient = dossier["patient"]
    terrain = []
    if patient.get("age") is not None:
        terrain.append(f"patient de {patient['age']} ans")
    if patient.get("poids_kg") is not None:
        terrain.append(f"{patient['poids_kg']} kg")
    terrain += bio_anormales(patient)

    requetes = []
    for traitement in dossier["traitements"]:
        requete = f"{traitement['libelle_medicament']}, {traitement['posologie']}"
        if terrain:
            requete += ", " + ", ".join(terrain)
        if requete not in requetes:  # une même ligne peut être prescrite plusieurs fois
            requetes.append(requete)
    return requetes


def recuperer_contexte(dossier):
    """Passages les plus proches de la prescription : liste de {"texte", "source", "page", "distance"}."""
    requetes = construire_requetes(dossier)
    if not requetes:
        return []
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

    return sorted(passages.values(), key=lambda p: p["distance"])[:NOMBRE_MAX_PASSAGES]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dossier", required=True, help="dossier contenant les fichiers JSON des patients")
    parser.add_argument("--idpatient", required=True, help="numéro du patient (nom du fichier JSON sans .json)")
    args = parser.parse_args()

    for p in recuperer_contexte(charger_patient(args.dossier, args.idpatient)):
        print(f"[{p['source']}, page {p['page']}]\n{p['texte']}\n")
