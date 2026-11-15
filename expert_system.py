"""
Système expert : règles déterministes appliquées à UN dossier patient de input.json.

Règle implémentée :
- Apixaban : la dose recommandée est de 2,5 mg deux fois par jour chez les patients présentant
  au moins deux des caractéristiques suivantes : âge ≥ 80 ans, poids ≤ 60 kg,
  créatinine sérique ≥ 133 µmol/L.
"""

import argparse
import json
from pathlib import Path

APIXABAN_DOSE_REDUITE_MG = 2.5
APIXABAN_DOSE_STANDARD_MG = 5

SEUIL_AGE_ANS = 80
SEUIL_POIDS_KG = 60
SEUIL_CREATININE_UMOL_L = 133


def criteres_apixaban(patient: dict) -> tuple[list[str], list[str]]:
    """Retourne (critères remplis, données manquantes) pour la réduction de dose d'apixaban."""
    age = patient.get("age")
    poids = patient.get("poids_kg")
    creatinine = patient.get("biologie", {}).get("creatinine_serique")

    remplis, manquants = [], []

    if age is None:
        manquants.append("âge")
    elif age >= SEUIL_AGE_ANS:
        remplis.append(f"âge {age} ans ≥ {SEUIL_AGE_ANS} ans")

    if poids is None:
        manquants.append("poids")
    elif poids <= SEUIL_POIDS_KG:
        remplis.append(f"poids {poids} kg ≤ {SEUIL_POIDS_KG} kg")

    if creatinine is None:
        manquants.append("créatinine sérique")
    elif creatinine >= SEUIL_CREATININE_UMOL_L:
        remplis.append(f"créatinine {creatinine} µmol/L ≥ {SEUIL_CREATININE_UMOL_L} µmol/L")

    return remplis, manquants


def verifier_apixaban(dossier: dict) -> list[dict]:
    """
    Vérifie la dose d'apixaban d'un patient.
    Retourne une liste d'alertes (vide si pas d'apixaban ou si la dose est conforme).
    """
    patient = dossier["patient"]
    alertes = []

    for t in dossier.get("traitements", []):
        if "apixaban" not in t.get("dci", "").lower():
            continue

        dose = t.get("dosage")
        remplis, manquants = criteres_apixaban(patient)
        reduction_requise = len(remplis) >= 2

        if reduction_requise and dose != APIXABAN_DOSE_REDUITE_MG:
            alertes.append({
                "medicament": "apixaban",
                "type": "surdosage",
                "message": (
                    f"Apixaban {dose} mg prescrit alors que le patient présente {len(remplis)} critères "
                    f"de réduction de dose ({', '.join(remplis)}) : la dose recommandée est de "
                    f"{APIXABAN_DOSE_REDUITE_MG} mg deux fois par jour."
                ),
            })
        elif not reduction_requise and manquants and len(remplis) + len(manquants) >= 2:
            alertes.append({
                "medicament": "apixaban",
                "type": "donnees_manquantes",
                "message": (
                    f"Impossible de conclure sur la dose d'apixaban ({dose} mg) : "
                    f"données manquantes ({', '.join(manquants)}). "
                    f"Critère(s) déjà rempli(s) : {', '.join(remplis) or 'aucun'}."
                ),
            })

    return alertes


def charger_patient(patient_id: str, fichier: Path = Path(__file__).parent / "input.json") -> dict:
    """Retourne le dossier du patient d'identifiant patient_id dans input.json."""
    dossiers = json.loads(fichier.read_text(encoding="utf-8"))
    if isinstance(dossiers, dict):
        dossiers = [dossiers]
    for dossier in dossiers:
        if dossier["patient"].get("id") == patient_id:
            return dossier
    ids = ", ".join(d["patient"].get("id", "?") for d in dossiers)
    raise SystemExit(f"Patient '{patient_id}' introuvable dans {fichier.name}. Patients disponibles : {ids}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Applique les règles du système expert à un patient.")
    parser.add_argument("--patient", required=True, help="identifiant du patient (ex : PAT-0001)")
    args = parser.parse_args()

    alertes = verifier_apixaban(charger_patient(args.patient))
    if not alertes:
        print("Aucune alerte.")
    for a in alertes:
        print(f"[{a['type']}] {a['message']}")
