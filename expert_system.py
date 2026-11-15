"""Règles déterministes appliquées à un patient."""

import argparse
import json


def verifier_apixaban(dossier):
    patient = dossier["patient"]

    criteres_remplis = []
    if patient["age"] >= 80:
        criteres_remplis.append("âge ≥ 80 ans")
    if patient["poids_kg"] <= 60:
        criteres_remplis.append("poids ≤ 60 kg")
    if patient["biologie"]["creatinine_serique"] >= 133:
        criteres_remplis.append("créatinine ≥ 133 µmol/L")

    alertes = []
    for traitement in dossier["traitements"]:
        if traitement["dci"] == "apixaban" and len(criteres_remplis) >= 2 and traitement["dosage"] != 2.5:
            alertes.append(
                f"Apixaban {traitement['dosage']} mg : la dose recommandée est 2,5 mg deux fois par jour "
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

    alertes = verifier_apixaban(charger_patient(args.idpatient))
    if alertes:
        for alerte in alertes:
            print(alerte)
    else:
        print("Aucune alerte")
