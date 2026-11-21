"""Patient records shown by the interface.

Inference results are read and written by main.py, KBS rules by kbs.py, laboratory reference ranges by generation.py."""

import os

from kbs import load_patient

PATIENTS_FOLDER = "dataset"  # patient records of the interface (one JSON file per patient), relative to the root


def load_patients(folder=PATIENTS_FOLDER):
    """Patient records of the folder (one JSON file per patient), sorted by file name."""
    if not os.path.isdir(folder):
        return []
    return [load_patient(folder, name[:-5]) for name in sorted(os.listdir(folder)) if name.endswith(".json")]
