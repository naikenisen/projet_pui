# Recherche dans ChromaDB les passages des référentiels utiles à l'analyse d'un patient.

import argparse
import json
import os

import chromadb
from dotenv import load_dotenv
from openai import OpenAI

from generation import LAB_RANGES_FILE
from indexing import CHROMA_DIR, COLLECTION_NAME, EMBEDDING_MODEL
from kbs import load_patient

load_dotenv()
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])

RESULTS_PER_QUERY = 3
MAX_PASSAGES = 8

# Préfixe recommandé par Qwen3-Embedding pour les requêtes uniquement
INSTRUCTION = "Instruct: Retrieve the medical guidelines useful to analyse this prescription\nQuery: "


def abnormal_biology(patient):
    with open(LAB_RANGES_FILE, encoding="utf-8") as file:
        ranges = json.load(file)

    abnormalities = []
    for name, measure in patient["biology"].items():
        if name not in ranges or not isinstance(measure.get("value"), (int, float)):
            continue
        reference = ranges[name]
        value = measure["value"]
        unit = measure.get("unit") or reference["unit"]
        if value < reference["min"]:
            abnormalities.append(f"low {reference['label']} ({value} {unit})")
        elif value > reference["max"]:
            abnormalities.append(f"high {reference['label']} ({value} {unit})")
    return abnormalities


# Une requête par ligne de traitement, complétée du profil patient et des anomalies biologiques
def build_queries(record):
    patient = record["patient"]
    profile = []
    if patient.get("age") is not None:
        profile.append(f"patient aged {patient['age']} years")
    if patient.get("weight_kg") is not None:
        profile.append(f"{patient['weight_kg']} kg")
    profile += abnormal_biology(patient)

    queries = []
    for treatment in record["treatments"]:
        query = f"{treatment['drug_label']}, {treatment['dosage_regimen']}"
        if profile:
            query += ", " + ", ".join(profile)
        if query not in queries:
            queries.append(query)
    return queries


# Passages les plus proches de la prescription, sans doublons, triés par distance
def retrieve_context(record):
    queries = build_queries(record)
    if not queries:
        return []
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=[INSTRUCTION + q for q in queries])
    vectors = [element.embedding for element in response.data]

    collection = chromadb.PersistentClient(path=CHROMA_DIR).get_collection(COLLECTION_NAME, embedding_function=None)
    results = collection.query(query_embeddings=vectors, n_results=RESULTS_PER_QUERY)

    passages = {}
    for i in range(len(queries)):
        for passage_id, text, meta, distance in zip(
            results["ids"][i], results["documents"][i], results["metadatas"][i], results["distances"][i]
        ):
            if passage_id not in passages or distance < passages[passage_id]["distance"]:
                passages[passage_id] = {"text": text, "source": meta["source"], "page": meta["page"], "distance": distance}

    return sorted(passages.values(), key=lambda p: p["distance"])[:MAX_PASSAGES]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True, help="folder containing the patient JSON files")
    parser.add_argument("--patient-id", required=True, help="patient number (JSON file name without .json)")
    args = parser.parse_args()

    for p in retrieve_context(load_patient(args.folder, args.patient_id)):
        print(f"[{p['source']}, page {p['page']}]\n{p['text']}\n")
