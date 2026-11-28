# Anonymises the CSV files of raw_extraction/ into original_dataset/, then builds full_dataset/ (one JSON per patient).

import json
import secrets
from pathlib import Path

import numpy as np
import pandas as pd

from csv_helpers import clean, dosage_regimen_text, group_active_ingredients, intake_unit, rename_contextual_rows, to_number

FOLDER = Path(__file__).resolve().parent
RAW_FOLDER = FOLDER / "raw_extraction"
CSV_FOLDER = FOLDER / "original_dataset"
OUTPUT_FOLDER = FOLDER.parent / "full_dataset"

DICTIONARY = json.loads((FOLDER / "dictionary.json").read_text(encoding="utf-8"))
BIOLOGY_DICTIONARY = json.loads((FOLDER / "biology_dictionary.json").read_text(encoding="utf-8"))

SEX = {"Femme": "F", "Homme": "M"}


# Distinct 9-digit identifiers drawn without a seed: they cannot be linked back to the hospital numbers
def random_identifiers(values):
    identifiers = set()
    while len(identifiers) < len(values):
        identifiers.add(str(secrets.randbelow(900_000_000) + 100_000_000))
    return dict(zip(values, identifiers))


# Replaces the NDA (same identifier in every table) and the prescription numbers
def anonymise_tables():
    tables = {source: pd.read_csv(RAW_FOLDER / cfg["raw_file"], dtype=str, keep_default_na=False)
              for source, cfg in DICTIONARY.items()}
    all_nda = sorted(set().union(*(tables[source][cfg["raw_id"]] for source, cfg in DICTIONARY.items())))
    patient_ids = random_identifiers(all_nda)
    prescription_ids = random_identifiers(sorted(set(tables["treatments"]["N° Prescription"])))
    tables["treatments"]["N° Prescription"] = tables["treatments"]["N° Prescription"].map(prescription_ids)

    CSV_FOLDER.mkdir(exist_ok=True)
    for source, cfg in DICTIONARY.items():
        table = tables[source]
        table[cfg["raw_id"]] = table[cfg["raw_id"]].map(patient_ids)
        table = table.rename(columns={cfg["raw_id"]: "numero_anonyme"})
        table.to_csv(CSV_FOLDER / cfg["file"], index=False)


def read_raw_csv(source):
    return pd.read_csv(CSV_FOLDER / DICTIONARY[source]["file"], dtype=str, keep_default_na=False)


def read_csv(source):
    cfg = DICTIONARY[source]
    df = read_raw_csv(source)
    for col, values in cfg.get("exclude", {}).items():
        df = df[~df[col].isin(values)]
    return df[list(cfg["columns"])].rename(columns=cfg["columns"])


# The rows of a prescription are copies: each column takes its non-empty value
# The copy without active ingredient holds the quantity summed over the copies, so the quantity comes from the others
def load_treatments():
    t = read_csv("treatments")
    lines = t.replace("", np.nan).groupby("prescription_number", sort=False).first().fillna("")

    quantity = to_number(t["quantity_per_day"])
    with_ingredient = quantity.where(t["active_ingredient_dosage"] != "")
    lines["quantity_per_day"] = (with_ingredient.groupby(t["prescription_number"]).min()
                                 .fillna(quantity.groupby(t["prescription_number"]).min()))

    ingredients = group_active_ingredients(t).reindex(lines.index)
    lines["ai"] = ingredients.apply(lambda x: x if isinstance(x, list) else [])
    lines["start"] = pd.to_datetime(lines["start_date"]).dt.normalize()
    lines["end"] = pd.to_datetime(lines["end_date"], errors="coerce").dt.normalize().fillna(lines["start"])
    return lines


def treatment_json(r):
    return {
        "drug_label": r["drug_label"],
        "start_date": r["start"].date().isoformat(),
        "end_date": r["end"].date().isoformat(),
        "intake_unit": intake_unit(r["intake_unit"]),
        "quantity_per_day": clean(r["quantity_per_day"]),
        "day_frequency": r["day_frequency"],
        "intake_times": r["intake_times"],
        "as_needed": r["as_needed"] == "Oui",
        "prescription_comment": " ".join(r["prescription_comment"].split()) or None,
        "active_ingredients": r["ai"],
        "dosage_regimen": dosage_regimen_text(r),
    }


# A test in a minority unit gets a "[unit]" suffix
def load_biology():
    b = read_csv("biology")
    columns = [c for c in b.columns if c not in ("patient_id", "test")]
    b["test"] = b["test"].str.replace(r"\s+", " ", regex=True).str.strip()
    b["numeric_value"] = to_number(b["value"])
    b = rename_contextual_rows(b, BIOLOGY_DICTIONARY["leukocyte_formula"])

    b["name"] = b["test"].map(lambda e: BIOLOGY_DICTIONARY["tests"].get(e, e))
    b["unit"] = b["unit"].map(lambda u: BIOLOGY_DICTIONARY["units"].get(u, u))

    majority = b.groupby("name")["unit"].agg(lambda s: s.value_counts().index[0])
    b["key"] = np.where(b["unit"] == b["name"].map(majority), b["name"], b["name"] + " [" + b["unit"] + "]")

    b["request"] = pd.to_datetime(b["request_date"])
    b["dt"] = pd.to_datetime(b["test_datetime"], format="%Y%m%d%H%M", errors="coerce")
    return b, columns


# Most recent result of each test
def latest_biology(biology):
    b = biology.sort_values(["patient_id", "key", "request", "dt"])
    return b.groupby(["patient_id", "key"], sort=False).tail(1)


def biology_json(r, columns):
    d = {c: r[c] for c in columns}
    d["value"] = clean(r["numeric_value"])
    d["request_date"] = r["request"].isoformat(sep=" ")
    d["test_datetime"] = r["dt"].isoformat(sep=" ") if pd.notna(r["dt"]) else None
    return d


# (numeric clinical values, sex) indexed by patient
def load_clinical():
    clinical = read_csv("clinical").set_index("patient_id")
    sex = clinical.pop("sex").map(SEX)
    return clinical.apply(to_number), sex


# One JSON per patient with ongoing prescriptions: all their lines, their latest lab values and their clinical data
def build_dataset():
    lines = load_treatments()
    biology, biology_columns = load_biology()
    biology = latest_biology(biology)
    clinical, sex = load_clinical()
    rounding = DICTIONARY["clinical"].get("rounding", {})

    treatments = {pid: [treatment_json(r) for _, r in g.iterrows()] for pid, g in lines.groupby("patient_id")}
    biology_by_patient = {pid: {r["key"]: biology_json(r, biology_columns) for _, r in g.iterrows()}
                          for pid, g in biology.groupby("patient_id")}

    dataset = []
    for pid in sorted(treatments):
        c = clinical.loc[pid] if pid in clinical.index else pd.Series(dtype=float)
        dataset.append({
            "patient": {
                "id": pid,
                "sex": sex.get(pid) if pd.notna(sex.get(pid)) else None,
                **{col: clean(c.get(col), rounding.get(col)) for col in clinical.columns},
                "biology": biology_by_patient.get(pid, {}),
            },
            "treatments": treatments[pid],
        })
    return dataset


def main():
    anonymise_tables()
    dataset = build_dataset()
    OUTPUT_FOLDER.mkdir(exist_ok=True)
    for old in OUTPUT_FOLDER.glob("*.json"):
        old.unlink()
    for entry in dataset:
        with open(OUTPUT_FOLDER / f"{entry['patient']['id']}.json", "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
    print(f"{len(dataset)} patients écrits dans {OUTPUT_FOLDER.name}/")


if __name__ == "__main__":
    main()
