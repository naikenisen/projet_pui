"""Analyse tous les patients de input.json avec le LLM, aidé du RAG et du système expert."""

import json

from expert_system import verifier_regles
from generation import analyser_patient
from recuperation import recuperer_contexte

with open("input.json", encoding="utf-8") as fichier:
    patients = json.load(fichier)

for dossier in patients:
    contexte = recuperer_contexte(dossier)
    alertes = verifier_regles(dossier)
    resultat = analyser_patient(dossier, contexte, alertes)

    print(dossier["patient"]["id"])
    print(resultat["decision"])
    print(resultat["justification"])
    print("Sources :", ", ".join(resultat.get("sources", [])) or "aucune")
    print()
