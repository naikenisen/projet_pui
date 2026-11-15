"""Analyse tous les patients de input.json avec le LLM."""

import json

from generation import analyser_patient

with open("input.json", encoding="utf-8") as fichier:
    patients = json.load(fichier)

for dossier in patients:
    resultat = analyser_patient(dossier)
    print(dossier["patient"]["id"])
    print(resultat["decision"])
    print(resultat["justification"])
    print()
