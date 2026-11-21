"""Reading, writing and validation of the project's JSON files (patients, laboratory ranges, inference results).

KBS rules are handled by kbs.py (src/kbs/)."""

import json
import os

from generation import LAB_RANGES_FILE

PATIENTS_FOLDER = "dataset"  # default folder: one JSON file per patient
SRC_FOLDER = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESULTS_FILE = os.path.join(SRC_FOLDER, "results", "inference_results.json")


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def patient_files(folder):
    if not os.path.isdir(folder):
        return []
    return sorted(name for name in os.listdir(folder) if name.endswith(".json"))


def load_patients(folder=PATIENTS_FOLDER):
    """Returns the list of patient records (one JSON file per patient) contained in the folder."""
    return [read_json(os.path.join(folder, name)) for name in patient_files(folder)]


def load_lab_ranges():
    return read_json(LAB_RANGES_FILE, {})


def load_results():
    return read_json(RESULTS_FILE, {})


def save_results(results):
    write_json(RESULTS_FILE, results)


def save_lab_ranges(rows):
    """rows: list of dicts {key, label, unit, min, max}. Returns the list of errors (empty if OK)."""
    ranges = {}
    errors = []
    for number, row in enumerate(rows, start=1):
        key = str(row.get("key") or "").strip()
        if not key:
            errors.append(f"Row {number}: the key is required")
            continue
        if key in ranges:
            errors.append(f"Row {number}: the key “{key}” is duplicated")
            continue
        try:
            minimum, maximum = float(row["min"]), float(row["max"])
        except (TypeError, ValueError, KeyError):
            errors.append(f"Row {number} ({key}): min and max must be numbers")
            continue
        if minimum > maximum:
            errors.append(f"Row {number} ({key}): min is greater than max")
            continue
        ranges[key] = {
            "label": str(row.get("label") or key).strip(),
            "unit": str(row.get("unit") or "").strip(),
            "min": minimum,
            "max": maximum,
        }
    if not errors:
        write_json(LAB_RANGES_FILE, ranges)
    return errors
