"""Knowledge-Based System (KBS): deterministic rules applied to a patient, and rule drafting by the LLM.

Rules are split across two files:
- src/kbs/generic_rules.json: ANSM Thesaurus of drug interactions and DDI-Predictor AUC ratios (src/kbs/KBS_Docs/),
  not editable from the interface;
- src/kbs/personalized_rules.json: hospital-specific rules (e.g. apixaban dose, daptomycin 10 mg/kg),
  written by hand or drafted by the LLM at a pharmacist's request.
In "drugs", each item is either a name ("ramipril") or a list of equivalent names
(the members of a Thesaurus class, e.g. all oral anticoagulants).
"""

import argparse
import functools
import json
import operator
import os
import re
import unicodedata

KBS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "kbs")
GENERIC_RULES_FILE = os.path.join(KBS_FOLDER, "generic_rules.json")
PERSONALIZED_RULES_FILE = os.path.join(KBS_FOLDER, "personalized_rules.json")

OPERATORS = {">=": operator.ge, "<=": operator.le, "!=": operator.ne, "==": operator.eq, ">": operator.gt, "<": operator.lt}
PATIENT_FIELDS = ("age", "weight_kg", "height_cm", "bmi_kg_m2", "body_surface_area_m2")

# Conversion to mg of the intake unit and of the active ingredient dosage unit (values as found in the data)
INTAKE_UNITS_TO_MG = {"milligramme(s)": 1, "gramme(s)": 1000, "microgramme(s)": 0.001}
DOSAGE_UNITS_TO_MG = {"mg": 1, "g": 1000, "ug": 0.001}


# ---------------------------------------------------------------------------
# Reading and writing rules
# ---------------------------------------------------------------------------

def read_rules(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def load_generic_rules():
    return read_rules(GENERIC_RULES_FILE)


def load_personalized_rules():
    return read_rules(PERSONALIZED_RULES_FILE)


def load_rules():
    """All rules: personalized first (their alerts are listed first), then generic."""
    return load_personalized_rules() + load_generic_rules()


def condition_error(condition):
    """Returns an error message if the condition cannot be read by condition_true, otherwise None."""
    for symbol in OPERATORS:  # same search order as condition_true
        if symbol in condition:
            parts = condition.split(symbol)
            if len(parts) != 2 or not parts[0].strip():
                return f"“{condition}”: write `variable {symbol} value`"
            try:
                float(parts[1])
            except ValueError:
                return f"“{condition}”: the value “{parts[1].strip()}” is not a number"
            return None
    return f"“{condition}”: no operator among {', '.join(OPERATORS)}"


def rule_errors(rule):
    if not isinstance(rule, dict):
        return ["a rule must be a JSON object"]
    errors = []
    if not str(rule.get("alert", "")).strip():
        errors.append("the `alert` field is required")
    for field in ("drugs", "conditions", "any_of"):
        if not isinstance(rule.get(field, []), list):
            errors.append(f"`{field}` must be a list")
    for drug in rule.get("drugs", []) if isinstance(rule.get("drugs", []), list) else []:
        names = [drug] if isinstance(drug, str) else drug
        if not isinstance(names, list) or not names or not all(isinstance(n, str) and n.strip() for n in names):
            errors.append("each drug must be a name or a list of names")
    for condition in rule.get("conditions", []) + rule.get("any_of", []):
        message = condition_error(str(condition))
        if message:
            errors.append(message)
    minimum = rule.get("minimum", 0)
    if not isinstance(minimum, int) or minimum < 0:
        errors.append("`minimum` must be a positive integer")
    elif minimum > len(rule.get("any_of", [])):
        errors.append("`minimum` is greater than the number of conditions in `any_of`")
    return errors


def save_personalized_rules(rules):
    """Saves the personalized rules if they are all valid. Returns the list of errors (empty if OK)."""
    if not isinstance(rules, list):
        return ["the file must contain a list of rules"]
    errors = []
    for number, rule in enumerate(rules, start=1):
        errors += [f"Rule {number}: {e}" for e in rule_errors(rule)]
    if not errors:
        with open(PERSONALIZED_RULES_FILE, "w", encoding="utf-8") as file:
            json.dump(rules, file, ensure_ascii=False, indent=2)
            file.write("\n")
    return errors


def add_personalized_rule(rule):
    return save_personalized_rules(load_personalized_rules() + [rule])


# ---------------------------------------------------------------------------
# Applying the rules to a patient
# ---------------------------------------------------------------------------

def normalize(text):
    """Lowercase without accents, so that “Paracétamol” and “PARACETAMOL” compare equal."""
    text = unicodedata.normalize("NFD", str(text).lower())
    return "".join(c for c in text if not unicodedata.combining(c))


@functools.lru_cache(maxsize=None)
def pattern(name):
    """Regular expression that searches for the name as a whole word."""
    return re.compile(r"\b" + re.escape(normalize(name)) + r"\b")


class Prescription:
    """Treatment lines of the patient, with memoized searches (one rule per interaction pair)."""

    def __init__(self, treatments):
        self.treatments = treatments
        self.labels = [normalize(t["drug_label"]) for t in treatments]
        self.cache = {}

    def lines(self, drug):
        """Indices of the lines whose label contains the drug (or one of the names if it is a list)."""
        names = [drug] if isinstance(drug, str) else drug
        found = set()
        for name in names:
            if name not in self.cache:
                self.cache[name] = {i for i, label in enumerate(self.labels) if pattern(name).search(label)}
            found |= self.cache[name]
        return found


def match_lines(line_sets, taken=()):
    """Picks a different line for each drug of the rule, or returns None if this is impossible.

    Two distinct lines are required: a fixed-dose combination (e.g. PERINDOPRIL+AMLODIPINE on a single
    line) does not trigger an interaction, and a drug does not interact with itself in
    “ORAL ANTICOAGULANTS + OTHER ORAL ANTICOAGULANTS”.
    """
    if not line_sets:
        return list(taken)
    for line in sorted(line_sets[0]):
        if line not in taken:
            result = match_lines(line_sets[1:], taken + (line,))
            if result is not None:
                return result
    return None


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def daily_dose_mg(treatment):
    """Dose in mg per administration day (quantity per day × dosage), or None if it cannot be computed."""
    quantity = treatment.get("quantity_per_day")
    if not is_number(quantity) or quantity <= 0:
        return None
    unit = treatment.get("intake_unit")
    if unit in INTAKE_UNITS_TO_MG:  # “700 milligramme(s) per day”
        return quantity * INTAKE_UNITS_TO_MG[unit]
    ingredients = treatment["active_ingredients"]  # “2 flacon(s) per day” of a 350 mg vial
    if len(ingredients) == 1 and ingredients[0].get("unit") in DOSAGE_UNITS_TO_MG and is_number(ingredients[0].get("dosage")):
        return quantity * ingredients[0]["dosage"] * DOSAGE_UNITS_TO_MG[ingredients[0]["unit"]]
    return None


def read_variables(record, rules, prescription):
    """Variables usable in conditions: patient fields, laboratory values and doses of the drugs in the rules.

    For each drug named alone in a rule with conditions:
    - dose_<drug>: dosage of the active ingredient (if there is only one, otherwise we cannot tell which);
    - daily_dose_<drug>: prescribed dose in mg per administration day;
    - dose_per_kg_<drug>: prescribed dose in mg/kg per administration day (if the weight is known).
    """
    patient = record["patient"]
    variables = {key: value for key, value in patient.items() if is_number(value)}
    for name, measure in patient["biology"].items():
        if is_number(measure.get("value")):
            variables[name] = measure["value"]

    for rule in rules:
        if not rule.get("conditions") and not rule.get("any_of"):
            continue
        for drug in rule.get("drugs", []):
            if not isinstance(drug, str):
                continue
            lines = prescription.lines(drug)
            if not lines:
                continue
            treatment = prescription.treatments[min(lines)]
            if len(treatment["active_ingredients"]) == 1:
                variables["dose_" + drug] = treatment["active_ingredients"][0]["dosage"]
            daily_dose = daily_dose_mg(treatment)
            if daily_dose is not None:
                variables["daily_dose_" + drug] = daily_dose
                if is_number(patient.get("weight_kg")) and patient["weight_kg"] > 0:
                    variables["dose_per_kg_" + drug] = daily_dose / patient["weight_kg"]
    return variables


def condition_true(condition, variables):
    for symbol, compare in OPERATORS.items():
        if symbol in condition:
            name, threshold = condition.split(symbol)
            value = variables.get(name.strip())
            return value is not None and compare(value, float(threshold))
    raise ValueError(f"Invalid condition: {condition}")


def rule_triggered(rule, variables, prescription):
    """Returns the prescription lines involved if the rule is triggered, otherwise None."""
    line_sets = [prescription.lines(drug) for drug in rule.get("drugs", [])]
    lines = match_lines(line_sets)
    if lines is None:
        return None

    for condition in rule.get("conditions", []):
        if not condition_true(condition, variables):
            return None

    true_count = sum(1 for condition in rule.get("any_of", []) if condition_true(condition, variables))
    return lines if true_count >= rule.get("minimum", 0) else None


def apply_rules(record, rules):
    prescription = Prescription(record["treatments"])
    variables = read_variables(record, rules, prescription)

    alerts = []
    for rule in rules:
        lines = rule_triggered(rule, variables, prescription)
        if lines is None:
            continue
        alert = rule["alert"]
        if lines:
            labels = " ; ".join(prescription.treatments[i]["drug_label"] for i in lines)
            alert += f" [Prescription: {labels}]"
        if alert not in alerts:
            alerts.append(alert)
    return alerts


def check_rules(record):
    """KBS alerts of all the rules (personalized and generic) for a patient."""
    return apply_rules(record, load_rules())


# ---------------------------------------------------------------------------
# Drafting of a personalized rule by the LLM, at a pharmacist's request
# ---------------------------------------------------------------------------

RULE_PROMPT = """You are a hospital clinical pharmacist. A pharmacist asks you to add a rule to the Knowledge-Based
System (KBS) that analyses prescriptions. Translate the request into a JSON rule. Reply only with a JSON object.

Rule format (only "alert" is required):
- "drugs": list of drugs that must ALL be prescribed, as lowercase French INNs (e.g. "apixaban", "paracetamol").
  An item can be a list of equivalent INNs, any one of which is enough (e.g. ["ibuprofene", "ketoprofene"]).
  The name is searched as a whole word in the prescription label (e.g. “APIXABAN 5 MG (ELIQUIS), CPR”),
  ignoring case and accents.
- "conditions": list of conditions that must ALL be true.
- "any_of" and "minimum": at least "minimum" conditions from the "any_of" list must be true.
- "alert": message shown to the pharmacist when the rule is triggered: problem and recommended action.

A condition is written exactly "variable operator number", with a single operator among >=, <=, >, <, ==, !=,
without unit or computation (e.g. "age >= 80", "DFG estimé (CKD-EPI) < 30"). Available variables:
- patient: age (years), weight_kg, height_cm, bmi_kg_m2, body_surface_area_m2;
- laboratory values, with the exact parameter name and its unit (convert the threshold to this unit):
{biology}
- for each drug named alone (not in a list) in "drugs":
  dose_<inn> = dosage of the prescribed product (e.g. dose_apixaban == 5 for APIXABAN 5 MG),
  daily_dose_<inn> = prescribed dose in mg per administration day,
  dose_per_kg_<inn> = prescribed dose in mg/kg per administration day.

Examples:
{{"drugs": ["apixaban"], "conditions": ["dose_apixaban != 2.5"], "any_of": ["age >= 80", "weight_kg <= 60", "Créatinine (sang) >= 133"], "minimum": 2, "alert": "Apixaban: the recommended dose is 2.5 mg twice daily (at least 2 criteria among age ≥ 80 years, weight ≤ 60 kg, creatinine ≥ 133 µmol/L)"}}
{{"drugs": ["daptomycine"], "conditions": ["dose_per_kg_daptomycine < 10"], "alert": "Daptomycin: the recommended dosage is now 10 mg/kg/day, the prescribed dose is lower"}}

If the request cannot be expressed with this format, reply {{"error": "short explanation"}}."""


def unknown_variables(rule, biology_parameters):
    """Condition variables that match no known data: the rule would never be triggered."""
    known = set(PATIENT_FIELDS) | set(biology_parameters)
    for drug in rule.get("drugs", []):
        if isinstance(drug, str):
            known |= {f"dose_{drug}", f"daily_dose_{drug}", f"dose_per_kg_{drug}"}
    unknown = []
    for condition in rule.get("conditions", []) + rule.get("any_of", []):
        for symbol in OPERATORS:
            if symbol in condition:
                name = condition.split(symbol)[0].strip()
                if name not in known and name not in unknown:
                    unknown.append(name)
                break
    return unknown


def propose_rule(request, biology_parameters):
    """Asks the LLM (the same one used to analyse patients) to translate the request into a rule.

    biology_parameters: {exact parameter name: unit}. Returns the validated rule, without saving it.
    Raises ValueError if the LLM cannot draft a valid rule.
    """
    from generation import MODEL, client  # imported here: generation imports this module

    biology = "\n".join(f"  {name} ({unit})" for name, unit in sorted(biology_parameters.items()))
    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": RULE_PROMPT.format(biology=biology)},
            {"role": "user", "content": request},
        ],
        max_tokens=1024,
        temperature=0,
        response_format={"type": "json_object"},
        extra_body={"reasoning": {"enabled": False}},
    )
    response = completion.choices[0].message.content
    response = json.loads(response[response.find("{"):response.rfind("}") + 1])
    if "error" in response:
        raise ValueError(response["error"])

    rule = {field: response[field] for field in ("drugs", "conditions", "any_of", "minimum", "alert")
            if response.get(field) not in (None, "", [])}
    if "any_of" not in rule:
        rule.pop("minimum", None)
    if isinstance(rule.get("drugs"), list):  # names are searched in lowercase without accents
        rule["drugs"] = [
            d.strip().lower() if isinstance(d, str)
            else [n.strip().lower() if isinstance(n, str) else n for n in d] if isinstance(d, list)
            else d
            for d in rule["drugs"]
        ]
    rule["source"] = "Written by the LLM at a pharmacist's request"
    rule["request"] = request

    errors = rule_errors(rule)
    if errors:
        raise ValueError("invalid proposed rule: " + " ; ".join(errors))
    return rule


# ---------------------------------------------------------------------------

def load_patient(folder, patient_id):
    path = os.path.join(folder, f"{patient_id}.json")
    if not os.path.exists(path):
        raise SystemExit(f"Patient not found: {path}")
    with open(path, encoding="utf-8") as file:
        return json.load(file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True, help="folder containing the patient JSON files")
    parser.add_argument("--patient-id", help="patient number (JSON file name without .json)")
    parser.add_argument("--new-rule", help="natural-language request: the LLM drafts a personalized rule")
    args = parser.parse_args()

    if args.new_rule:
        parameters = {}
        for file_name in sorted(os.listdir(args.folder)):
            if file_name.endswith(".json"):
                for name, measure in load_patient(args.folder, file_name[:-5])["patient"]["biology"].items():
                    parameters.setdefault(name, measure.get("unit") or "")
        rule = propose_rule(args.new_rule, parameters)
        print(json.dumps(rule, ensure_ascii=False, indent=2))
        for name in unknown_variables(rule, parameters):
            print(f"Warning: the variable “{name}” does not exist, the condition will always be false.")
        if input(f"Save this rule to {os.path.relpath(PERSONALIZED_RULES_FILE)}? [y/N] ").strip().lower() == "y":
            errors = add_personalized_rule(rule)
            print("\n".join(errors) if errors else "Rule saved.")
    elif args.patient_id:
        alerts = check_rules(load_patient(args.folder, args.patient_id))
        if alerts:
            for alert in alerts:
                print(alert)
        else:
            print("No alert")
    else:
        parser.error("specify --patient-id or --new-rule")
