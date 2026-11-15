"""Règles déterministes, définies dans regles_expert.json, appliquées à un patient."""

import argparse
import json
import operator

OPERATEURS = {">=": operator.ge, "<=": operator.le, "!=": operator.ne, "==": operator.eq, ">": operator.gt, "<": operator.lt}


def lire_valeurs(dossier):
    patient = dossier["patient"]
    valeurs = {**patient, **patient["biologie"]}
    for traitement in dossier["traitements"]:
        valeurs["dose_" + traitement["dci"]] = traitement["dosage"]
    return valeurs


def condition_vraie(condition, valeurs):
    for symbole, comparer in OPERATEURS.items():
        if symbole in condition:
            nom, seuil = condition.split(symbole)
            valeur = valeurs.get(nom.strip())
            return valeur is not None and comparer(valeur, float(seuil))
    raise ValueError(f"Condition invalide : {condition}")


def regle_declenchee(regle, valeurs, medicaments):
    for medicament in regle.get("medicaments", []):
        if medicament not in medicaments:
            return False

    for condition in regle.get("conditions", []):
        if not condition_vraie(condition, valeurs):
            return False

    nombre_vraies = 0
    for condition in regle.get("parmi", []):
        if condition_vraie(condition, valeurs):
            nombre_vraies += 1
    return nombre_vraies >= regle.get("minimum", 0)


def verifier_regles(dossier):
    with open("regles_expert.json", encoding="utf-8") as fichier:
        regles = json.load(fichier)

    valeurs = lire_valeurs(dossier)
    medicaments = [traitement["dci"] for traitement in dossier["traitements"]]

    alertes = []
    for regle in regles:
        if regle_declenchee(regle, valeurs, medicaments):
            alertes.append(regle["alerte"])
    return alertes


def charger_patient(patient_id):
    with open("input.json", encoding="utf-8") as fichier:
        patients = json.load(fichier)
    for dossier in patients:
        if dossier["patient"]["id"] == patient_id:
            return dossier
    raise SystemExit(f"Patient introuvable : {patient_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--idpatient", required=True)
    args = parser.parse_args()

    alertes = verifier_regles(charger_patient(args.idpatient))
    if alertes:
        for alerte in alertes:
            print(alerte)
    else:
        print("Aucune alerte")
