"""Reading of the patient files and of the laboratory reference ranges.

Inference results are read and written by main.py, KBS rules by kbs.py (src/kbs/)."""

import json
import os

from generation import LAB_RANGES_FILE

PATIENTS_FOLDER = "dataset"  # patient records of the interface (one JSON file per patient), relative to the root


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def patient_files(folder):
    if not os.path.isdir(folder):
        return []
    return sorted(name for name in os.listdir(folder) if name.endswith(".json"))


def load_patients(folder=PATIENTS_FOLDER):
    """Returns the list of patient records (one JSON file per patient) contained in the folder."""
    return [read_json(os.path.join(folder, name)) for name in patient_files(folder)]


def load_lab_ranges():
    return read_json(LAB_RANGES_FILE, {})
