"""Analyse l'ordonnance d'un patient avec le LLM."""

import argparse
import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])

MODEL = "qwen/qwen3.6-35b-a3b"

SYSTEM_PROMPT = """Tu es un pharmacien clinicien hospitalier français. On te fournit un patient et son ordonnance au format JSON.
Analyse l'ordonnance en tenant compte du terrain du patient (âge, poids, biologie), des posologies,
des contre-indications, des interactions et des recommandations françaises.

Réponds uniquement avec un objet JSON :
{"decision": "PATIENT VALIDÉ" ou "INTERVENTION PHARMACEUTIQUE PROPOSÉE", "justification": "un paragraphe court de 3 à 5 phrases"}

En cas d'intervention, la justification cite le ou les médicaments en cause, le problème et l'adaptation proposée."""


def analyser_patient(dossier):
    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(dossier, ensure_ascii=False)},
        ],
        max_tokens=1024,
        temperature=0,
        response_format={"type": "json_object"},
        extra_body={"reasoning": {"enabled": False}},
    )
    reponse = completion.choices[0].message.content

    # Garde uniquement le JSON, au cas où le modèle ajoute du texte autour.
    reponse = reponse[reponse.find("{"):reponse.rfind("}") + 1]
    return json.loads(reponse)


def charger_patient(patient_id):
    with open("input.json", encoding="utf-8") as fichier:
        patients = json.load(fichier)
    for dossier in patients:
        if dossier["patient"]["id"] == patient_id:
            return dossier
    raise SystemExit(f"Patient introuvable : {patient_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--patient", required=True)
    args = parser.parse_args()

    resultat = analyser_patient(charger_patient(args.patient))
    print(resultat["decision"])
    print(resultat["justification"])
