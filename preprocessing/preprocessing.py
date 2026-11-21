"""Builds dataset/: one <patient_id>.json file per patient, from the CSV files of original_dataset/.

1. TREATMENTS: a day on which the patient has at least one active prescription is drawn at random,
   and the prescriptions active on that day are kept.
2. BIOLOGY: for each test, the most recent result strictly before that day.
3. CLINICAL: all the columns of dictionary.json, as numbers.

Files, columns, filters and rounding: dictionary.json.
Laboratory labels and units: biology_dictionary.json.
CSV shape specifics: csv_helpers.py.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from csv_helpers import (clean, dosage_regimen_text, group_active_ingredients, intake_unit,
                         rename_contextual_rows, to_number)

FOLDER = Path(__file__).resolve().parent
CSV_FOLDER = FOLDER / "original_dataset"
OUTPUT_FOLDER = FOLDER / "dataset"

SEED = 42
INCLUDE_SAME_DAY_BIOLOGY = False

DICTIONARY = json.loads((FOLDER / "dictionary.json").read_text(encoding="utf-8"))
BIOLOGY_DICTIONARY = json.loads((FOLDER / "biology_dictionary.json").read_text(encoding="utf-8"))

ACTIVE_INGREDIENT = ["active_ingredient_dosage", "active_ingredient_unit"]


def read_raw_csv(source):
    return pd.read_csv(CSV_FOLDER / DICTIONARY[source]["file"], dtype=str, keep_default_na=False)


def read_csv(source):
    cfg = DICTIONARY[source]
    df = read_raw_csv(source)
    for col, values in cfg.get("exclude", {}).items():
        df = df[~df[col].isin(values)]
    return df[list(cfg["columns"])].rename(columns=cfg["columns"])


# --- TREATMENTS ----------------------------------------------------------------
def load_treatments():
    t = read_csv("treatments")
    key = [c for c in t.columns if c not in ACTIVE_INGREDIENT]

    lines = t.drop_duplicates(key)[key].join(group_active_ingredients(t, key), on=key)
    lines["ai"] = lines["ai"].apply(lambda x: x if isinstance(x, list) else [])
    lines["start"] = pd.to_datetime(lines["start_date"]).dt.normalize()
    lines["end"] = pd.to_datetime(lines["end_date"], errors="coerce").dt.normalize()
    lines["end"] = lines["end"].fillna(lines["start"])  # no end date: active on the first day
    return lines.reset_index(drop=True), [c for c in key if c != "patient_id"]


def choose_days(lines):
    days = lines[["patient_id", "start", "end"]].copy()
    days["day"] = [pd.date_range(s, e, freq="D") for s, e in zip(days["start"], days["end"])]
    days = days.explode("day").drop_duplicates(["patient_id", "day"])
    rng = np.random.default_rng(SEED)
    choice = {pid: grp.iloc[rng.integers(len(grp))]
              for pid, grp in days.sort_values(["patient_id", "day"]).groupby("patient_id")["day"]}
    return pd.Series(choice, name="reference_date")


def prescriptions_of_the_day(lines, days):
    presc = lines.join(days, on="patient_id")
    return presc[(presc["start"] <= presc["reference_date"]) & (presc["reference_date"] <= presc["end"])]


def treatment_json(r, columns):
    d = {c: r[c] for c in columns}
    d["active_ingredients"] = r["ai"]
    d["dosage_regimen"] = dosage_regimen_text(r)
    d["start_date"] = r["start"].date().isoformat()
    d["end_date"] = r["end"].date().isoformat()
    if "intake_unit" in d:
        d["intake_unit"] = intake_unit(d["intake_unit"])
    if "quantity_per_day" in d:
        d["quantity_per_day"] = clean(pd.to_numeric(d["quantity_per_day"].replace(",", "."), errors="coerce"))
    if "as_needed" in d:
        d["as_needed"] = d["as_needed"] == "Oui"
    return d


# --- BIOLOGY ---------------------------------------------------------------------
def load_biology():
    b = read_csv("biology")
    columns = [c for c in b.columns if c not in ("patient_id", "test")]
    b["test"] = b["test"].str.replace(r"\s+", " ", regex=True).str.strip()
    b["numeric_value"] = to_number(b["value"])
    b = rename_contextual_rows(b, BIOLOGY_DICTIONARY["leukocyte_formula"])

    b["name"] = b["test"].map(lambda e: BIOLOGY_DICTIONARY["tests"].get(e, e))
    b["unit"] = b["unit"].map(lambda u: BIOLOGY_DICTIONARY["units"].get(u, u))

    # Same test in several units: the majority unit keeps the name, the others get “[unit]”
    majority = b.groupby("name")["unit"].agg(lambda s: s.value_counts().index[0])
    b["key"] = np.where(b["unit"] == b["name"].map(majority), b["name"], b["name"] + " [" + b["unit"] + "]")

    b["request"] = pd.to_datetime(b["request_date"])
    b["dt"] = pd.to_datetime(b["test_datetime"], format="%Y%m%d%H%M", errors="coerce")
    return b, columns


def biology_before_day(biology, days):
    b = biology.join(days, on="patient_id", how="inner")
    limit = b["reference_date"] + pd.Timedelta(days=1 if INCLUDE_SAME_DAY_BIOLOGY else 0)
    b = b[b["request"] < limit].sort_values(["patient_id", "key", "request", "dt"])
    return b.groupby(["patient_id", "key"], sort=False).tail(1)


def biology_json(r, columns):
    d = {c: r[c] for c in columns}
    d["value"] = clean(r["numeric_value"])
    d["request_date"] = r["request"].isoformat(sep=" ")
    d["test_datetime"] = r["dt"].isoformat(sep=" ") if pd.notna(r["dt"]) else None
    return d


def load_clinical():
    return read_csv("clinical").set_index("patient_id").apply(to_number)


# --- Assembly ----------------------------------------------------------------------
def build_dataset():
    lines, treatment_columns = load_treatments()
    days = choose_days(lines)

    presc = prescriptions_of_the_day(lines, days)
    biology, biology_columns = load_biology()
    biology = biology_before_day(biology, days)
    clinical = load_clinical()
    rounding = DICTIONARY["clinical"].get("rounding", {})

    treatments = {pid: [treatment_json(r, treatment_columns) for _, r in g.iterrows()]
                  for pid, g in presc.groupby("patient_id")}
    biology_by_patient = {pid: {r["key"]: biology_json(r, biology_columns) for _, r in g.iterrows()}
                          for pid, g in biology.groupby("patient_id")}

    dataset = []
    for pid in sorted(days.index):
        c = clinical.loc[pid] if pid in clinical.index else pd.Series(dtype=float)
        dataset.append({
            "patient": {
                "id": pid,
                "reference_date": days[pid].date().isoformat(),
                **{col: clean(c.get(col), rounding.get(col)) for col in clinical.columns},
                "biology": biology_by_patient.get(pid, {}),
            },
            "treatments": treatments.get(pid, []),
        })
    return dataset


def main():
    dataset = build_dataset()
    OUTPUT_FOLDER.mkdir(exist_ok=True)
    for old in OUTPUT_FOLDER.glob("*.json"):
        old.unlink()
    for entry in dataset:
        with open(OUTPUT_FOLDER / f"{entry['patient']['id']}.json", "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
    print(f"{len(dataset)} patients written to {OUTPUT_FOLDER.name}/")


if __name__ == "__main__":
    main()
