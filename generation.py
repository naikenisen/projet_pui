import json
import os
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

# Loads OPENROUTER_API_KEY from the .env file (which is git-ignored).
load_dotenv()

# OpenRouter is OpenAI-compatible: same SDK, just a different base_url.
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

MODEL = "qwen/qwen3.6-35b-a3b"
INPUT_FILE = Path(__file__).parent / "input.json"

VALIDE = "PATIENT VALIDÉ"
INTERVENTION = "INTERVENTION PHARMACEUTIQUE PROPOSÉE"

SYSTEM_PROMPT = f"""Tu es un pharmacien clinicien hospitalier français chargé de l'analyse pharmaceutique des prescriptions.
On te fournit un patient (âge, sexe, poids, taille, biologie) et son ordonnance au format JSON.

Analyse l'ordonnance en tenant compte du terrain du patient : âge, fonction rénale (DFG), biologie,
posologies, contre-indications, interactions, médicaments inappropriés chez le sujet âgé,
et conformité aux recommandations françaises (HAS, SFD, ANSM...).

Réponds UNIQUEMENT avec un objet JSON de la forme :
{{
  "decision": "{VALIDE}" ou "{INTERVENTION}",
  "justification": "un paragraphe court (3 à 5 phrases)"
}}

- "{VALIDE}" : aucune adaptation nécessaire ; la justification explique brièvement pourquoi l'ordonnance est conforme.
- "{INTERVENTION}" : au moins une adaptation est nécessaire ; la justification cite le ou les médicaments en cause,
  le problème (en lien avec les données du patient) et l'adaptation proposée.
"""


def analyser_patient(dossier: dict) -> dict:
    """Envoie un dossier patient au modèle et retourne {"decision", "justification"}."""
    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(dossier, ensure_ascii=False, indent=2)},
        ],
        max_tokens=1024,
        temperature=0,
        response_format={"type": "json_object"},
        extra_body={"reasoning": {"enabled": False}},
    )

    content = completion.choices[0].message.content or ""
    try:
        # Certains modèles entourent le JSON de ```json ... ``` : on isole l'objet.
        return json.loads(content[content.find("{"): content.rfind("}") + 1])
    except json.JSONDecodeError:
        return {"decision": "ERREUR (réponse non JSON)", "justification": content}


def main():
    dossiers = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    if isinstance(dossiers, dict):  # accepte aussi un fichier avec un seul patient
        dossiers = [dossiers]

    for dossier in dossiers:
        patient = dossier["patient"]
        resultat = analyser_patient(dossier)

        print("=" * 80)
        print(f"Patient {patient.get('id', '?')} — {patient.get('age')} ans, {patient.get('sexe')}")
        print(f"\n>>> {resultat.get('decision', '?')}\n")
        print(resultat.get("justification", ""))
    print("=" * 80)


if __name__ == "__main__":
    main()
