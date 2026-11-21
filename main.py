"""Analyses every patient of a folder of JSON files with the LLM, helped by the RAG and the KBS.

Run from the project root:  python3 main.py --folder dataset
"""

import argparse
import json
import os

from generation import analyse_patient
from kbs import check_rules
from retrieval import retrieve_context

parser = argparse.ArgumentParser()
parser.add_argument("--folder", required=True, help="folder containing the patient JSON files")
args = parser.parse_args()

for file_name in sorted(os.listdir(args.folder)):
    if not file_name.endswith(".json"):
        continue
    with open(os.path.join(args.folder, file_name), encoding="utf-8") as file:
        record = json.load(file)

    passages = retrieve_context(record)
    alerts = check_rules(record)
    result = analyse_patient(record, passages, alerts)

    print(record["patient"]["id"])
    print(result["decision"])
    print(result["justification"])
    print("Sources:", ", ".join(result.get("sources", [])) or "none")
    print()
