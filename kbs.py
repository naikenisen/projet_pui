# Knowledge-Based System (KBS) on the CLIPS inference engine: the patient record becomes facts and the rules of the .clp files raise the alerts.

import argparse
import functools
import json
import os
import re
import tempfile
import unicodedata

import clips

KBS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ressources", "kbs")
# Generic rule
BASE_FILE = os.path.join(KBS_FOLDER, "base.clp")
# ANSM Thesaurus and DDI-Predictor interactions
GENERIC_RULES_FILE = os.path.join(KBS_FOLDER, "generic_rules.clp")
# Hospital-specific rules, written by the LLM
PERSONALIZED_RULES_FILE = os.path.join(KBS_FOLDER, "personalized_rules.clp")
# Situations in which the pharmacists often make an IP ("Patient à risque" alerts)
STATISTICAL_RULES_FILE = os.path.join(KBS_FOLDER, "statistical_rules.clp")


def read_file(path):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as file:
        return file.read()


# Lowercase without accents: "Paracétamol" == "PARACETAMOL"
def normalize(text):
    text = unicodedata.normalize("NFD", str(text).lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# All word sequences of the label, so a rule finds "apixaban" in "APIXABAN 5 MG (ELIQUIS), CPR"
def word_sequences(label):
    label = normalize(label)
    words = list(re.finditer(r"\w+", label))
    return {label[first.start():last.end()] for i, first in enumerate(words) for last in words[i:]}


# "IRBESARTAN 150 MG (LABO ARROW), CPR" -> "IRBESARTAN"
def drug_name(label):
    return re.split(r"[\d,(]", label, maxsplit=1)[0].strip().upper()


# Translates the patient record into facts (templates described in base.clp)
def assert_patient(env, record):
    data = env.find_template("data")
    patient = record["patient"]
    if patient.get("reference_date"):
        env.find_template("reference-date").assert_fact(date=patient["reference_date"][:10])
    for name, value in patient.items():
        if is_number(value):
            data.assert_fact(name=name, value=value)
    for name, measure in patient["biology"].items():
        if is_number(measure.get("value")):
            data.assert_fact(name=name, value=measure["value"])

    for line, treatment in enumerate(record["treatments"]):
        quantity = treatment.get("quantity_per_day")
        ingredients = treatment["active_ingredients"]
        env.find_template("treatment").assert_fact(
            line=line,
            label=treatment["drug_label"],
            name=drug_name(treatment["drug_label"]),
            quantity=quantity if is_number(quantity) else 0,
            unit=treatment.get("intake_unit") or "",
            ingredients=len(ingredients),
            start=(treatment.get("start_date") or "")[:10],
            end=(treatment.get("end_date") or "")[:10],
            as_needed=bool(treatment.get("as_needed")),
        )
        for number, ingredient in enumerate(ingredients, start=1):
            if is_number(ingredient.get("dosage")):
                env.find_template("ingredient").assert_fact(
                    line=line, number=number, dosage=ingredient["dosage"], unit=ingredient.get("unit") or ""
                )
        for words in word_sequences(treatment["drug_label"]):
            env.find_template("prescribed").assert_fact(line=line, drug=words)


# CLIPS environment with base.clp, then the rules given as text
# CLIPS only loads files, so the text goes through a temporary file
def create_environment(rules=""):
    env = clips.Environment()
    env.load(BASE_FILE)
    if rules:
        with tempfile.NamedTemporaryFile("w", suffix=".clp", encoding="utf-8", delete=False) as file:
            file.write(rules)
        try:
            env.load(file.name)
        finally:
            os.remove(file.name)
    return env


# base.clp alone is enough to deduce the status and dose of the lines
@functools.lru_cache(maxsize=None)
def base_environment():
    return create_environment()


# Cached because generic_rules.clp is slow to load; cleared when the personalized rules change
@functools.lru_cache(maxsize=None)
def kbs_environment():
    env = create_environment(read_file(PERSONALIZED_RULES_FILE))
    env.load(GENERIC_RULES_FILE)
    env.load(STATISTICAL_RULES_FILE)
    return env


def run_rules(env, record):
    env.reset()
    assert_patient(env, record)
    env.run()


# Alerts of the record, one per message, followed by the labels of the lines involved
def apply_rules(record, env):
    run_rules(env, record)

    labels = [treatment["drug_label"] for treatment in record["treatments"]]
    alerts = {}
    for fact in env.facts():
        if fact.template.name != "alert":
            continue
        message = str(fact["message"])
        if message not in alerts:
            lines = " ; ".join(labels[line] for line in fact["lines"])
            alerts[message] = f"{message} [Prescription: {lines}]" if lines else message
    return list(alerts.values())


def check_rules(record):
    return apply_rules(record, kbs_environment())


# Status and dose per administration day of each line, deduced by base.clp
# e.g. [{"status": "ongoing", "dose": (3000, "mg")}, {"status": "ended"}]
def line_details(record):
    env = base_environment()
    run_rules(env, record)

    details = [{} for _ in record["treatments"]]
    for fact in env.facts():
        if fact.template.name == "line-status":
            details[fact["line"]]["status"] = str(fact["status"])
        elif fact.template.name == "line-dose":
            details[fact["line"]]["dose"] = (fact["amount"], str(fact["unit"]))
    return details


def load_patient(folder, patient_id):
    path = os.path.join(folder, f"{patient_id}.json")
    if not os.path.exists(path):
        raise SystemExit(f"Patient not found: {path}")
    with open(path, encoding="utf-8") as file:
        return json.load(file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True, help="folder containing the patient JSON files")
    parser.add_argument("--patient-id", required=True, help="patient number (JSON file name without .json)")
    args = parser.parse_args()

    alerts = check_rules(load_patient(args.folder, args.patient_id))
    if alerts:
        for alert in alerts:
            print(alert)
    else:
        print("No alert")
