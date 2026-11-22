# Système à base de connaissances (KBS) sur le moteur d'inférence CLIPS : le dossier patient est traduit en faits,
# les règles des fichiers .clp produisent les alertes ; le LLM peut rédiger de nouvelles règles.

import argparse
import functools
import json
import os
import re
import tempfile
import unicodedata

import clips

KBS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ressources", "kbs")
# Modèle des faits, calculs de dose et règle générique d'interaction
BASE_FILE = os.path.join(KBS_FOLDER, "base.clp")
# Interactions du Thésaurus ANSM et de DDI-Predictor, non modifiables depuis l'interface
GENERIC_RULES_FILE = os.path.join(KBS_FOLDER, "generic_rules.clp")
# Règles propres à l'hôpital, écrites à la main ou par le LLM : un bloc par règle, séparé par une ligne vide
PERSONALIZED_RULES_FILE = os.path.join(KBS_FOLDER, "personalized_rules.clp")

PATIENT_FIELDS = ("age", "weight_kg", "height_cm", "bmi_kg_m2", "body_surface_area_m2")
REQUEST_PREFIX = "; Demande du pharmacien : "
# Fonctions CLIPS refusées dans les règles personnalisées : accès aux fichiers et au système
FORBIDDEN_FUNCTIONS = ("system", "open", "remove", "rename", "load", "batch", "save", "bsave", "bload", "eval", "build", "exit")


def read_file(path):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as file:
        return file.read()


# Minuscules sans accents : « Paracétamol » == « PARACETAMOL »
def normalize(text):
    text = unicodedata.normalize("NFD", str(text).lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# Toutes les suites de mots du libellé : une règle trouve ainsi « apixaban » dans « APIXABAN 5 MG (ELIQUIS), CPR »
def word_sequences(label):
    label = normalize(label)
    words = list(re.finditer(r"\w+", label))
    return {label[first.start():last.end()] for i, first in enumerate(words) for last in words[i:]}


# Traduit le dossier patient en faits (modèle décrit dans base.clp)
def assert_patient(env, record):
    data = env.find_template("data")
    patient = record["patient"]
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
            quantity=quantity if is_number(quantity) else 0,
            unit=treatment.get("intake_unit") or "",
            ingredients=len(ingredients),
        )
        for number, ingredient in enumerate(ingredients, start=1):
            if is_number(ingredient.get("dosage")):
                env.find_template("ingredient").assert_fact(
                    line=line, number=number, dosage=ingredient["dosage"], unit=ingredient.get("unit") or ""
                )
        for words in word_sequences(treatment["drug_label"]):
            env.find_template("prescribed").assert_fact(line=line, drug=words)


# Environnement CLIPS avec base.clp puis les règles données en texte
# CLIPS ne charge que des fichiers : le texte passe par un fichier temporaire
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


# Gardé en mémoire car generic_rules.clp est long à charger ; vidé quand les règles personnalisées changent
@functools.lru_cache(maxsize=None)
def kbs_environment():
    env = create_environment(read_file(PERSONALIZED_RULES_FILE))
    env.load(GENERIC_RULES_FILE)
    return env


# Alertes du dossier, une seule par message, suivies des libellés des lignes concernées
def apply_rules(record, env):
    env.reset()
    assert_patient(env, record)
    env.run()

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


def rule_names(rule):
    return re.findall(r"\(defrule\s+([^\s()]+)", rule)


# Sans ligne vide, pour qu'une règle reste un seul bloc du fichier
def compact(rule):
    return "\n".join(line.rstrip() for line in rule.strip().splitlines() if line.strip())


def load_personalized_rules():
    return [block.strip() for block in read_file(PERSONALIZED_RULES_FILE).split("\n\n") if block.strip()]


# Liste vide si la règle (texte CLIPS) est sûre et se charge dans CLIPS
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


# N'enregistre que si toutes les règles sont valides ; renvoie la liste des erreurs
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


# {paramètre biologique: unité} des dossiers, dont le LLM doit reprendre le nom exact
def biology_parameters(records):
    parameters = {}
    for record in records:
        for name, measure in record["patient"]["biology"].items():
            parameters.setdefault(name, measure.get("unit") or "")
    return parameters


# Données (data (name "...")) absentes des dossiers : les conditions sur elles seront toujours fausses
def unknown_data(rule, biology_parameters):
    names = re.findall(r'\(data\s+\(name\s+"([^"]+)"\)', rule)
    return sorted(set(names) - set(PATIENT_FIELDS) - set(biology_parameters))


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


# Traduit la demande en règle CLIPS validée, sans l'enregistrer ; ValueError si impossible
# Import local de generation, qui importe lui-même ce module
def propose_rule(request, biology_parameters):
    from generation import MODEL, client

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

    rule = REQUEST_PREFIX + " ".join(request.split()) + "\n" + compact(str(response.get("clips", "")))
    errors = rule_errors(rule)
    if errors:
        raise ValueError("invalid proposed rule: " + " ; ".join(errors))
    return rule


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
        records = [load_patient(args.folder, name[:-5]) for name in sorted(os.listdir(args.folder)) if name.endswith(".json")]
        parameters = biology_parameters(records)
        rule = propose_rule(args.new_rule, parameters)
        print(rule)
        for name in unknown_data(rule, parameters):
            print(f"Warning: the data “{name}” does not exist, the conditions on it will always be false.")
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
