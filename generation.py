import argparse
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
    parser = argparse.ArgumentParser(description="Analyse pharmaceutique d'un patient par le LLM.")
    parser.add_argument("--patient", required=True, help="identifiant du patient (ex : PAT-0001)")
    args = parser.parse_args()

    resultat = analyser_patient(charger_patient(args.patient))
    print(f">>> {resultat.get('decision', '?')}\n")
    print(resultat.get("justification", ""))
