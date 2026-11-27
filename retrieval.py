# Searches ChromaDB for the guideline passages useful to analyse a patient.

import argparse
import json

from generation import LAB_RANGES_FILE, summarize_record
from indexing import get_collection
from inference import InferenceBackend, add_inference_arguments, backend_from_args
from kbs import load_patient

RESULTS_PER_QUERY = 3
MAX_PASSAGES = 8
# Extra passages found from the LLM context, added after the main ones
MAX_LLM_PASSAGES = 4

# Prefix recommended by Qwen3-Embedding, for queries only
INSTRUCTION = "Instruct: Retrieve the medical guidelines useful to analyse this prescription\nQuery: "

LLM_CONTEXT_PROMPT = """You are a French hospital clinical pharmacist. You are given a patient and their prescription in JSON format.
Write up to 8 short and simple context sentences to search the guidelines: the likely indication of the notable
treatments, specific populations, drug combinations to check. Describe the situation, do not judge the prescription.
The guidelines are in French and English: write each sentence in French, then the same sentence in English on the
next line. One sentence per line, without numbering or bullet points.
Example for a woman treated with silodosine:
Silodosine chez la femme : traitement facilitant le désondage.
Silodosin in women: treatment to help urinary catheter removal.
"""

RENAL_TESTS = {
    "DFG estimé (CKD-EPI)": "eGFR CKD-EPI",
    "Clairance de la créatinine (Cockcroft)": "Cockcroft creatinine clearance",
    "Créatinine (sang)": "creatinine",
}


# Renal values always added to the query when present
def renal_function(patient):
    values = []
    for name, label in RENAL_TESTS.items():
        measure = patient["biology"].get(name)
        if measure and measure.get("value") is not None:
            values.append(f"{label} {measure['value']} {measure.get('unit', '')}".strip())
    return values


def abnormal_biology(patient):
    with open(LAB_RANGES_FILE, encoding="utf-8") as file:
        ranges = json.load(file)

    abnormalities = []
    for name, measure in patient["biology"].items():
        if name in RENAL_TESTS or name not in ranges or not isinstance(measure.get("value"), (int, float)):
            continue
        reference = ranges[name]
        value = measure["value"]
        unit = measure.get("unit") or reference["unit"]
        if value < reference["min"]:
            abnormalities.append(f"low {reference['label']} ({value} {unit})")
        elif value > reference["max"]:
            abnormalities.append(f"high {reference['label']} ({value} {unit})")
    return abnormalities


# One query per treatment line, completed with the patient profile, the renal function and the lab abnormalities
def build_queries(record):
    patient = record["patient"]
    profile = []
    if patient.get("age") is not None:
        profile.append(f"patient aged {patient['age']} years")
    if patient.get("weight_kg") is not None:
        profile.append(f"{patient['weight_kg']} kg")
    profile += renal_function(patient)
    profile += abnormal_biology(patient)

    queries = []
    for treatment in record["treatments"]:
        query = f"{treatment['drug_label']}, {treatment['dosage_regimen']}"
        if profile:
            query += ", " + ", ".join(profile)
        if query not in queries:
            queries.append(query)
    return queries


# Short context sentences written by the LLM from the patient record, used as extra queries
def llm_context(record, backend: InferenceBackend | None = None):
    backend = backend if backend is not None else InferenceBackend()
    text = backend.generate(
        LLM_CONTEXT_PROMPT, json.dumps(summarize_record(record), ensure_ascii=False),
        max_tokens=1000,
    )
    return [line.strip(" -•*") for line in text.splitlines() if line.strip(" -•*")]


# Passages closest to the queries, without duplicates, sorted by distance
def search(queries, backend: InferenceBackend | None = None):
    if not queries:
        return []
    backend = backend if backend is not None else InferenceBackend()
    collection = get_collection(backend=backend)
    vectors = backend.embed([INSTRUCTION + q for q in queries])

    results = collection.query(query_embeddings=vectors, n_results=RESULTS_PER_QUERY)

    passages = {}
    for i in range(len(queries)):
        for passage_id, text, meta, distance in zip(
            results["ids"][i], results["documents"][i], results["metadatas"][i], results["distances"][i]
        ):
            if passage_id not in passages or distance < passages[passage_id]["distance"]:
                passages[passage_id] = {"text": text, "source": meta["source"], "page": meta["page"], "distance": distance}
    return sorted(passages.values(), key=lambda p: p["distance"])


# Passages from the code queries first, then the new passages found from the LLM context
def retrieve_context(record, backend: InferenceBackend | None = None):
    backend = backend if backend is not None else InferenceBackend()
    passages = search(build_queries(record), backend=backend)[:MAX_PASSAGES]
    known_texts = [p["text"] for p in passages]
    llm_passages = [
        p for p in search(llm_context(record, backend=backend), backend=backend) if p["text"] not in known_texts
    ]
    return passages + llm_passages[:MAX_LLM_PASSAGES]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    add_inference_arguments(parser)
    parser.add_argument("--folder", required=True, help="folder containing the patient JSON files")
    parser.add_argument("--patient-id", required=True, help="patient number (JSON file name without .json)")
    args = parser.parse_args()

    for p in retrieve_context(load_patient(args.folder, args.patient_id), backend=backend_from_args(args)):
        print(f"[{p['source']}, page {p['page']}]\n{p['text']}\n")
