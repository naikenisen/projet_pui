# Analyses the patients of a folder (KBS, RAG, LLM) and saves the results in inference_results.json.

import argparse
import json
import multiprocessing
import os
from datetime import datetime

from generation import analyse_patient
from kbs import check_rules
from retrieval import retrieve_context

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inference_results.json")
# Parallel analyses with --multithreads
WORKERS = 8


def load_results():
    if not os.path.exists(RESULTS_FILE):
        return {}
    with open(RESULTS_FILE, encoding="utf-8") as file:
        return json.load(file)


def save_results(results):
    with open(RESULTS_FILE, "w", encoding="utf-8") as file:
        json.dump(results, file, ensure_ascii=False, indent=2)


# Full analysis of one patient; on failure, the error is saved instead of a result
def analyse(record):
    date = datetime.now().strftime("%d/%m/%Y %H:%M")
    try:
        alerts = check_rules(record)
        passages = retrieve_context(record)
        result = analyse_patient(record, passages, alerts)
    except Exception as error:
        return {"error": f"{type(error).__name__}: {error}", "date": date}
    return {**result, "alerts": alerts, "date": date}


# The workers return the patient ID with the result, since they finish in any order
def analyse_with_id(record):
    return record["patient"]["id"], analyse(record)


def read_record(path):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", default="dataset", help="folder containing the patient JSON files")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--remaining", action="store_true", help="only the patients without a result")
    mode.add_argument("--all", action="store_true", help="all the patients; the results file is overwritten")
    parser.add_argument("--multithreads", action="store_true", help=f"analyses {WORKERS} patients at a time")
    args = parser.parse_args()

    results = {} if args.all else load_results()
    records = [read_record(os.path.join(args.folder, name)) for name in sorted(os.listdir(args.folder))]
    records = [record for record in records
               if record["patient"]["id"] not in results or "error" in results[record["patient"]["id"]]]

    # --multithreads: processes, not threads, because the cached CLIPS environment cannot be shared.
    # Only this process writes the results file.
    pool = multiprocessing.Pool(WORKERS) if args.multithreads else None
    analysed = pool.imap_unordered(analyse_with_id, records) if pool else map(analyse_with_id, records)
    for patient_id, result in analysed:
        results[patient_id] = result
        save_results(results)
        print(f"Patient {patient_id} analysed and result saved in inference_results.json")
    if pool:
        pool.close()
