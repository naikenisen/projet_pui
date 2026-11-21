"""Shape specifics of the CSV files: number formats, codes, rows to interpret from their context."""

import numpy as np
import pandas as pd


def to_number(series):
    return pd.to_numeric(series.str.replace(",", ".", regex=False), errors="coerce")


def clean(x, decimals=None):
    if x is None or np.isnan(x):
        return None
    x = float(x) if decimals is None else round(float(x), decimals)
    return int(x) if x.is_integer() else x


# --- TREATMENTS ----------------------------------------------------------------
def group_active_ingredients(t, key):
    # The CSV has one row per active ingredient (plus rows without dosage): one list per prescription
    ai = t[t["active_ingredient_dosage"] != ""].copy()
    ai["unit_lower"] = ai["active_ingredient_unit"].str.lower()
    ai = ai.drop_duplicates(key + ["active_ingredient_dosage", "unit_lower"])
    ai["ai"] = [{"dosage": clean(d), "unit": u}
                for d, u in zip(to_number(ai["active_ingredient_dosage"]), ai["active_ingredient_unit"])]
    return ai.groupby(key, sort=False)["ai"].agg(list)


def intake_unit(text):
    return text.split(" - ", 1)[-1]  # « gel - gélule(s) » -> « gélule(s) »


def dosage_regimen_text(r):
    """Readable dosage regimen, e.g. “2 comprimé(s) per day — matin, soir — every day”.

    The units and intake times come from the CSV (in French) and are kept as is."""
    unit = intake_unit(r.get("intake_unit", ""))
    quantity = r.get("quantity_per_day", "")
    try:
        quantity = f"{float(quantity.replace(',', '.')):g}" if quantity else ""
    except ValueError:
        pass  # not a number: kept as written
    parts = [f"{quantity} {unit} per day" if quantity else f"{unit} as needed"]

    m = r.get("intake_times", "")
    if m == "Specifique":
        parts.append("specific times")
    elif m:
        parts.append(m.replace(".", ", ").lower())

    f = r.get("day_frequency", "")
    if "/" in f:
        n, d = f.split("/")
        parts.append(f"{n} day(s) out of {d}")
    elif f == "TLJ":
        parts.append("every day")
    elif f == "Autre":
        parts.append("irregular schedule")
    elif f:
        parts.append(f"frequency {f}")

    return " — ".join(parts)


# --- BIOLOGY ---------------------------------------------------------------------
def rename_contextual_rows(b, leukocyte_formula):
    block = ["patient_id", "test_datetime"]
    test = b["test"]

    # « soit »: before the block's Leucocytes -> reticulocytes, after -> leukocyte formula (fixed order)
    soit = b.loc[test.isin(["soit", "soit:", "Soit :"]), block]
    i_leu = b.index.to_series()[test == "Leucocytes"].groupby([b["patient_id"], b["test_datetime"]]).min()
    soit = soit.join(i_leu.rename("i_leu"), on=block)
    before = soit.index < soit["i_leu"]
    rank = soit[~before].groupby(block).cumcount() % len(leukocyte_formula)
    b.loc[soit.index[before], "test"] = "soit → Réticulocytes"
    b.loc[rank.index, "test"] = rank.map(lambda i: f"soit → {leukocyte_formula[i]}")

    # « Soit »: in BAU/mL -> anti-SARS-CoV-2 IgG, otherwise log10 of the block's viral load
    for i in b.index[test.isin(["Soit:", "Soit"])]:
        r = b.loc[i]
        if r["unit"] == "BAU/mL":
            b.at[i, "test"] = "soit → IgG anti-SARS-CoV-2 (BAU/mL)"
            continue
        same_block = b[(b["patient_id"] == r["patient_id"]) & (b["test_datetime"] == r["test_datetime"])]
        vl = same_block[same_block["test"].str.startswith("Charge virale")]
        match = vl[(np.log10(vl["numeric_value"].clip(lower=1)) - r["numeric_value"]).abs() < 0.05]
        b.at[i, "test"] = f"soit → {match['test'].iloc[0]} (log)" if len(match) else "soit → Charge virale (log)"

    # « Temps du patient/témoin » (patient/control time): Quick if the control is < 20 s, otherwise aPTT (TCA)
    t = b.loc[test.isin(["Temps du patient", "Temps du témoin"]), block + ["test", "numeric_value"]].copy()
    t["rank"] = t.groupby(block + ["test"]).cumcount()
    control = t[t["test"] == "Temps du témoin"].set_index(block + ["rank"])["numeric_value"]
    v = t.join(control.rename("control"), on=block + ["rank"])["control"]
    b.loc[t.index, "test"] = t["test"] + np.where(v < 20, " → Quick", " → TCA")
    return b
