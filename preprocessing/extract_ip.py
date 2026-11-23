# Extracts the pharmaceutical interventions (IP) written by the pharmacists from ANONYMISED_TRAITEMENTS.csv into ip.json.

import json
import re
from pathlib import Path

import pandas as pd

FOLDER = Path(__file__).resolve().parent
TREATMENTS_CSV = FOLDER / "original_dataset" / "ANONYMISED_TRAITEMENTS.csv"
OUTPUT_FILE = FOLDER / "ip.json"

# "25/10/2024 17:25 PERRET Valentin : text" -> date, pharmacist, text
LINE_PATTERN = re.compile(r"^(\d\d/\d\d/\d{4} \d\d:\d\d) (.+?) : (.*)$")


# One comment -> {"date", "text", "problem", "resolution"}
def parse_comment(comment):
    intervention = {"date": None, "text": "", "problem": None, "resolution": None}
    for line in comment.splitlines():
        found = LINE_PATTERN.match(line.strip())
        if not found:
            intervention["text"] += " " + line.strip()
            continue
        date, _, content = found.groups()
        intervention["date"] = intervention["date"] or date
        if content.startswith("Problème :"):
            intervention["problem"] = content.removeprefix("Problème :").strip()
        elif content.startswith("Résolution :"):
            intervention["resolution"] = content.removeprefix("Résolution :").strip()
        else:
            intervention["text"] += " " + content
    intervention["text"] = intervention["text"].strip()
    return intervention


def extract_interventions():
    treatments = pd.read_csv(TREATMENTS_CSV, dtype=str, keep_default_na=False)
    treatments = treatments[treatments["Commentaire Médecin"].str.strip() != ""]
    # The CSV has one row per active ingredient: the same comment is repeated
    treatments = treatments.drop_duplicates(["numero_anonyme", "Libellé Médicament Prescrit", "Commentaire Médecin"])

    interventions = []
    for _, row in treatments.iterrows():
        interventions.append({
            "patient_id": row["numero_anonyme"],
            "drug_label": row["Libellé Médicament Prescrit"],
            **parse_comment(row["Commentaire Médecin"]),
        })
    return interventions


if __name__ == "__main__":
    interventions = extract_interventions()
    OUTPUT_FILE.write_text(json.dumps(interventions, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(interventions)} interventions written to {OUTPUT_FILE.name}")
