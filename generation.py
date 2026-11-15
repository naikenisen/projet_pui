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
Si des alertes du système expert ou des extraits de recommandations sont fournis, appuie-toi dessus en priorité.

Réponds uniquement avec un objet JSON :
{"decision": "PATIENT VALIDÉ" ou "INTERVENTION PHARMACEUTIQUE PROPOSÉE", "justification": "un paragraphe court de 3 à 5 phrases", "sources": ["..."]}

En cas d'intervention, la justification cite le ou les médicaments en cause, le problème et l'adaptation proposée.
Dans "sources", liste les références des extraits utilisés (ex : "reco_sfd.pdf, page 12") et ajoute "système expert" si tu t'appuies sur une de ses alertes.
Laisse la liste vide si ta décision repose uniquement sur tes connaissances."""


def analyser_patient(dossier, contexte="", alertes=None):
    message = json.dumps(dossier, ensure_ascii=False)
    if alertes:
        message += "\n\nAlertes du système expert :\n" + "\n".join(alertes)
    if contexte:
        message += "\n\nExtraits des recommandations :\n" + contexte

    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message},
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
    parser.add_argument("--idpatient", required=True)
    args = parser.parse_args()

    resultat = analyser_patient(charger_patient(args.idpatient))
    print(resultat["decision"])
    print(resultat["justification"])
