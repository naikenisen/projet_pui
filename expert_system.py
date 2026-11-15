"""Règles déterministes, définies dans regles_expert.json, appliquées à un patient."""

import argparse
import json
import operator

OPERATEURS = {">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt}


def verifier_regles(dossier):
    with open("regles_expert.json", encoding="utf-8") as fichier:
        regles = json.load(fichier)

    # Données du patient et de sa biologie réunies dans un seul dictionnaire.
    patient = dossier["patient"]
    valeurs = {**patient, **patient["biologie"]}

    alertes = []
    for regle in regles:
        criteres_remplis = []
        for critere in regle["criteres"]:
            comparer = OPERATEURS[critere["operateur"]]
            if comparer(valeurs[critere["donnee"]], critere["seuil"]):
                criteres_remplis.append(critere["libelle"])

        if len(criteres_remplis) < regle["nombre_criteres_minimum"]:
            continue

        for traitement in dossier["traitements"]:
            if traitement["dci"] == regle["medicament"] and traitement["dosage"] != regle["dose_recommandee"]:
                alertes.append(
                    f"{traitement['dci']} {traitement['dosage']} {traitement['unite']} : {regle['message']} "
                    f"({', '.join(criteres_remplis)})"
                )
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
