"""Analyse tous les patients d'un dossier de fichiers JSON avec le LLM, aidé du RAG et du système expert."""

import argparse
import json
import os

from expert_system import verifier_regles
from generation import analyser_patient
from recuperation import recuperer_contexte

parser = argparse.ArgumentParser()
parser.add_argument("--dossier", required=True, help="dossier contenant les fichiers JSON des patients")
args = parser.parse_args()

for nom_fichier in sorted(os.listdir(args.dossier)):
    if not nom_fichier.endswith(".json"):
        continue
    with open(os.path.join(args.dossier, nom_fichier), encoding="utf-8") as fichier:
        dossier = json.load(fichier)

    passages = recuperer_contexte(dossier)
    alertes = verifier_regles(dossier)
    resultat = analyser_patient(dossier, passages, alertes)

    print(dossier["patient"]["id"])
    print(resultat["decision"])
    print(resultat["justification"])
    print("Sources :", ", ".join(resultat.get("sources", [])) or "aucune")
    print()
