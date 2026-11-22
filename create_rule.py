# Drafts a personalized CLIPS rule with the LLM from a pharmacist request, checks it and saves it in personalized_rules.clp.

import argparse
import json
import os
import re

import clips

from generation import MODEL, client
from kbs import BASE_FILE, PERSONALIZED_RULES_FILE, create_environment, kbs_environment, load_patient, read_file

# CLIPS functions forbidden in personalized rules: file and system access
FORBIDDEN_FUNCTIONS = ("system", "open", "remove", "rename", "load", "batch", "save", "bsave", "bload", "eval", "build", "exit")


def rule_names(rule):
    return re.findall(r"\(defrule\s+([^\s()]+)", rule)


# Without empty lines, so a rule stays a single block of the file
def compact(rule):
    return "\n".join(line.rstrip() for line in rule.strip().splitlines() if line.strip())


def load_personalized_rules():
    return [block.strip() for block in read_file(PERSONALIZED_RULES_FILE).split("\n\n") if block.strip()]


# Empty list if the rule (CLIPS text) is safe and loads in CLIPS
def rule_errors(rule):
    if not rule_names(rule):
        return ["the rule must contain at least one defrule"]
    forbidden = re.findall(r"\((" + "|".join(FORBIDDEN_FUNCTIONS) + r")[\s)*]", rule)
    if forbidden:
        return [f"forbidden CLIPS function: {forbidden[0]}"]
    taken = set(rule_names(rule)) & set(rule_names(read_file(BASE_FILE)))
    if taken:
        return ["names already used in base.clp: " + ", ".join(sorted(taken))]
    try:
        create_environment(rule)
    except clips.CLIPSError as error:
        return [str(error)]
    return []


# Saves only if all the rules are valid; returns the list of errors
def save_personalized_rules(rules):
    errors = []
    names = []
    for number, rule in enumerate(rules, start=1):
        errors += [f"Rule {number}: {e}" for e in rule_errors(rule)]
        names += rule_names(rule)
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        errors.append("names used by several rules: " + ", ".join(duplicates))
    if not errors:
        with open(PERSONALIZED_RULES_FILE, "w", encoding="utf-8") as file:
            file.write("\n\n".join(compact(rule) for rule in rules) + "\n")
        kbs_environment.cache_clear()
    return errors


def add_personalized_rule(rule):
    return save_personalized_rules(load_personalized_rules() + [rule])


# {lab parameter: unit} of the records; the LLM must reuse their exact names
def biology_parameters(records):
    parameters = {}
    for record in records:
        for name, measure in record["patient"]["biology"].items():
            parameters.setdefault(name, measure.get("unit") or "")
    return parameters


RULE_PROMPT = """You are a hospital clinical pharmacist and a CLIPS expert. A pharmacist asks you to add a rule to the
Knowledge-Based System (KBS) that analyses prescriptions. Translate the request into CLIPS code.
Reply only with a JSON object: {{"clips": "<CLIPS code>"}}, or {{"error": "short explanation"}} if the request
cannot be expressed with the facts below.

Facts created from the patient file:
- (data (name <string>) (value <number>)): numeric patient data, only present when known. Names:
  "age" (years), "weight_kg", "height_cm", "bmi_kg_m2", "body_surface_area_m2", and the laboratory values,
  with their exact name and unit (convert the threshold to this unit):
{biology}
- (treatment (line <n>) (label <string>) (quantity <quantity per day>) (unit <intake unit>) (ingredients <count>)):
  one prescription line; ingredients is the number of active ingredients.
- (ingredient (line <n>) (number <n>) (dosage <number>) (unit <string>)): active ingredient of a line,
  e.g. dosage 5 and unit "mg" for "APIXABAN 5 MG".
- (prescribed (line <n>) (drug <string>)): drug cited on a line, as a lowercase French INN without accents
  (e.g. "apixaban", "paracetamol"). Equivalent drugs: (prescribed (line ?l) (drug "ibuprofene" | "ketoprofene")).
Facts deduced by the KBS:
- (daily-dose (line <n>) (mg <number>)): prescribed dose in mg per administration day.
- (dose-per-kg (line <n>) (mg <number>)): prescribed dose in mg/kg per administration day.

Raise an alert with (assert (alert (message "<problem and recommended action, in French>") (lines <line variables>))).
Two drugs must be on distinct lines: (prescribed (line ?l1) (drug "a")) (prescribed (line ?l2&~?l1) (drug "b")).
Compare numbers with a test, e.g. (data (name "age") (value ?v&:(>= ?v 80))).

Format: first line "; <short title in French>", then one or more defrule whose names share a prefix specific
to this rule. No empty line, no deftemplate, no deffunction; intermediate results are ordered facts,
e.g. (assert (apixaban-criterion age)).

Examples:
; Apixaban : dose réduite si au moins 2 critères parmi âge, poids et créatinine
(defrule apixaban-criterion-age
  (data (name "age") (value ?v&:(>= ?v 80)))
  =>
  (assert (apixaban-criterion age)))
(defrule apixaban-criterion-weight
  (data (name "weight_kg") (value ?v&:(<= ?v 60)))
  =>
  (assert (apixaban-criterion weight)))
(defrule apixaban-criterion-creatinine
  (data (name "Créatinine (sang)") (value ?v&:(>= ?v 133)))
  =>
  (assert (apixaban-criterion creatinine)))
(defrule apixaban-dose
  (prescribed (line ?l) (drug "apixaban"))
  (ingredient (line ?l) (dosage ?d&:(<> ?d 2.5)))
  (apixaban-criterion ?c1)
  (apixaban-criterion ?c2&~?c1)
  =>
  (assert (alert (message "Apixaban : la dose recommandée est 2,5 mg deux fois par jour") (lines ?l))))

; Daptomycine : posologie inférieure à 10 mg/kg/jour
(defrule daptomycine-dose
  (prescribed (line ?l) (drug "daptomycine"))
  (dose-per-kg (line ?l) (mg ?mg&:(< ?mg 10)))
  =>
  (assert (alert (message "Daptomycine : la posologie recommandée est de 10 mg/kg/jour") (lines ?l))))"""


# Translates the request into a validated CLIPS rule, without saving it; ValueError if impossible
def propose_rule(request, biology_parameters):
    biology = "\n".join(f"  {name} ({unit})" for name, unit in sorted(biology_parameters.items()))
    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": RULE_PROMPT.format(biology=biology)},
            {"role": "user", "content": request},
        ],
        max_tokens=2048,
        temperature=0,
        response_format={"type": "json_object"},
        extra_body={"reasoning": {"enabled": False}},
    )
    response = completion.choices[0].message.content
    response = json.loads(response[response.find("{"):response.rfind("}") + 1])
    if "error" in response:
        raise ValueError(response["error"])

    rule = compact(str(response.get("clips", "")))
    errors = rule_errors(rule)
    if errors:
        raise ValueError("invalid proposed rule: " + " ; ".join(errors))
    return rule


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True, help="folder containing the patient JSON files")
    parser.add_argument("--request", required=True, help="natural-language request: the LLM drafts a personalized rule")
    args = parser.parse_args()

    records = [load_patient(args.folder, name[:-5]) for name in sorted(os.listdir(args.folder)) if name.endswith(".json")]
    rule = propose_rule(args.request, biology_parameters(records))
    print(rule)
    if input(f"Save this rule to {os.path.relpath(PERSONALIZED_RULES_FILE)}? [y/N] ").strip().lower() == "y":
        errors = add_personalized_rule(rule)
        print("\n".join(errors) if errors else "Rule saved.")
