# Analyses the patients of a folder (KBS, RAG, LLM) and saves the results in inference_results.json.

import argparse
import json
import os
from datetime import datetime

from generation import analyse_patient
from inference import InferenceBackend, add_inference_arguments, backend_from_args
from kbs import check_rules
from retrieval import retrieve_context

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inference_results.json")


def load_results():
    if not os.path.exists(RESULTS_FILE):
        return {}
    with open(RESULTS_FILE, encoding="utf-8") as file:
        return json.load(file)


def save_results(results):
    with open(RESULTS_FILE, "w", encoding="utf-8") as file:
        json.dump(results, file, ensure_ascii=False, indent=2)


# Full analysis of one patient; on failure, the error is saved instead of a result
def analyse(record, backend: InferenceBackend | None = None):
    backend = backend if backend is not None else InferenceBackend()
    date = datetime.now().strftime("%d/%m/%Y %H:%M")
    try:
        alerts = check_rules(record)
        passages = retrieve_context(record, backend=backend)
        result = analyse_patient(record, passages, alerts, backend=backend)
    except Exception as error:
        return {"error": f"{type(error).__name__}: {error}", "date": date}
    return {**result, "alerts": alerts, "date": date}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    add_inference_arguments(parser)
    parser.add_argument("--folder", default="dataset", help="folder containing the patient JSON files")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--remaining", action="store_true", help="only the patients without a result")
    mode.add_argument("--all", action="store_true", help="all the patients; the results file is overwritten")
    args = parser.parse_args()
    backend = backend_from_args(args)

    results = {} if args.all else load_results()
    for file_name in sorted(os.listdir(args.folder)):
        with open(os.path.join(args.folder, file_name), encoding="utf-8") as file:
            record = json.load(file)
        patient_id = record["patient"]["id"]
        if patient_id in results and "error" not in results[patient_id]:
            continue
        results[patient_id] = analyse(record, backend=backend)
        save_results(results)
        print(f"Patient {patient_id} analysed and result saved in inference_results.json")
