"""Analyse l'ordonnance d'un patient avec le LLM."""

import argparse
import json
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

from expert_system import charger_patient

load_dotenv()
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])

MODEL = "qwen/qwen3.6-35b-a3b"

DECISION_VALIDE = "PATIENT VALIDÉ"
DECISION_SURVEILLANCE = "SURVEILLANCE PROPOSÉE"
DECISION_VERIFICATION = "VÉRIFICATION PROPOSÉE"
DECISION_INTERVENTION = "INTERVENTION PHARMACEUTIQUE PROPOSÉE"

SYSTEM_PROMPT = f"""Tu es un pharmacien clinicien hospitalier français. On te fournit un patient et son ordonnance au format JSON.
"jour_reference" est la date à laquelle l'ordonnance est analysée. Une donnée absente du patient n'est pas renseignée.
Chaque valeur biologique est donnée avec son unité et la date de l'examen. Chaque traitement est donné avec son libellé
(spécialité, dosage, forme), sa posologie et ses dates de début et de fin.
Analyse l'ordonnance en tenant compte du terrain du patient (âge, poids, biologie), des posologies,
des contre-indications, des interactions et des recommandations françaises.

Des alertes du système expert [A1], [A2]... et des extraits de recommandations [R1], [R2]... peuvent être fournis.
Les alertes du Thésaurus ANSM indiquent leur niveau entre parenthèses. Un niveau combiné (ex : « CI - ASDEC - APEC »)
signifie que le niveau dépend des molécules ou des doses : lis la conduite à tenir pour déterminer le niveau qui
s'applique réellement à cette prescription (ex : aspirine à dose antiagrégante + héparine = « à prendre en compte »,
pas « déconseillée »). Hiérarchise ensuite les alertes :
- les CONTRE-INDICATIONS sont prioritaires ;
- les autres alertes (association déconseillée, précaution d'emploi, interaction pharmacocinétique) ne justifient
  une intervention que si, compte tenu du contexte de ce patient (âge, fonction rénale, biologie, doses), le risque
  est cliniquement crucial. Sinon, elles relèvent au plus d'une surveillance, ou sont simplement acceptables.
Une alerte ne justifie donc jamais à elle seule une intervention : juge sa pertinence pour ce patient.

Choisis UNE décision parmi les quatre suivantes, de la plus grave à la moins grave :
- "{DECISION_INTERVENTION}" : un problème avéré et cliniquement important impose de modifier la prescription
  (contre-indication, posologie inadaptée au terrain ou à la biologie, association à risque crucial pour ce
  patient, médicament indiqué manquant, etc.).
- "{DECISION_VERIFICATION}" : à réserver aux cas où les deux conditions suivantes sont réunies : (1) si
  l'hypothèse se confirmait, le problème justifierait une intervention ; (2) une information absente du dossier est
  indispensable pour trancher. Exemple typique : deux lignes du même médicament ou de la même classe (dosage global
  volontaire ou oubli d'arrêter une ligne ?). Ne propose PAS de vérification pour une indication non documentée
  d'un traitement courant, un bilan de routine, une interaction mineure ou une donnée manquante qui ne changerait
  pas la conduite à tenir : dans ces cas, choisis la surveillance ou la validation.
- "{DECISION_SURVEILLANCE}" : pas de problème majeur ; l'association ou la posologie est acceptable (interaction
  tolérée, précaution d'emploi, association dont le bénéfice justifie l'emploi) mais une surveillance clinique ou
  biologique spécifique est utile (ex : kaliémie, INR, ECG, glycémie, fonction rénale).
- "{DECISION_VALIDE}" : aucun problème notable ni surveillance particulière au-delà du suivi habituel.

Réponds uniquement avec un objet JSON :
{{"decision": "<une des quatre décisions, recopiée à l'identique>",
 "points": [{{"texte": "une proposition courte", "references": ["A1", "R2"]}}]}}

Règles pour les points :
- 1 à 4 points, un par problème, du plus important au moins important. Pour un patient validé, un seul point.
- Chaque point tient en une ou deux phrases courtes (40 mots au plus) et commence par « Proposons » ou
  « Suggérons ». Ne fais pas de point sur une prescription conforme (ex : statine à dose adaptée) ni sur un
  élément sans conséquence pratique.
- Formule des propositions, jamais des affirmations ni des ordres : « Proposons une réduction de l'apixaban à
  2,5 mg x 2/j compte tenu de la créatininémie à 155 µmol/L et de l'âge (95 ans) », « Suggérons de vérifier auprès
  du prescripteur si... », « Proposons une surveillance de la kaliémie... ».
- Chaque point cite le médicament en cause et les valeurs du patient qui le justifient ; pour une vérification,
  ce qu'il faut vérifier et la conduite à tenir selon la réponse ; pour une surveillance, le paramètre à surveiller.
- N'écris aucune référence dans "texte". Dans "references", mets uniquement les identifiants ([A1], [R2]...) des
  alertes et extraits fournis ci-dessous sur lesquels le point s'appuie réellement, sans les crochets.
  N'invente jamais d'identifiant : si aucune alerte ni aucun extrait n'est fourni, ou si le point repose sur tes
  connaissances, laisse la liste vide."""


def resumer_dossier(dossier):
    """Version allégée du dossier envoyée au LLM : champs vides retirés, une ligne de texte par valeur biologique."""
    patient = dossier["patient"]
    resume = {cle: valeur for cle, valeur in patient.items() if cle != "biologie" and valeur is not None}
    resume["biologie"] = {
        nom: f"{mesure['valeur']} {mesure.get('unite') or ''} le {mesure.get('date_heure_examen') or '?'}".replace("  ", " ")
        for nom, mesure in patient["biologie"].items()
    }
    traitements = [
        {cle: traitement[cle] for cle in ("libelle_medicament", "posologie", "date_debut", "date_fin") if traitement.get(cle)}
        for traitement in dossier["traitements"]
    ]
    return {"patient": resume, "traitements": traitements}


# Identifiant recopié dans le texte malgré la consigne : « (A1, A2) », « (alerte A1 niveau ...) », « [R2] »
MOTIF_REFERENCE_DANS_TEXTE = re.compile(r"\s*(?:\([^()]*\b[AR]\d+\b[^()]*\)|\[[AR]\d+(?:\s*,\s*[AR]\d+)*\])")


def lire_reponse(reponse, alertes, passages):
    """Remplace les identifiants cités par le LLM par les alertes et extraits correspondants.

    Les identifiants inconnus sont ignorés : le LLM ne peut pas citer une source qu'on ne lui a pas donnée.
    """
    references = {f"A{i}": {"type": "alerte", "texte": alerte} for i, alerte in enumerate(alertes, start=1)}
    references |= {
        f"R{i}": {"type": "document", "source": p["source"], "page": p["page"]} for i, p in enumerate(passages, start=1)
    }
    points = []
    for point in reponse.get("points") or []:
        if not isinstance(point, dict) or not str(point.get("texte", "")).strip():
            continue
        sources = []
        for identifiant in point.get("references") or []:
            source = references.get(str(identifiant).strip(" []").upper())
            if source and source not in sources:
                sources.append(source)
        texte = MOTIF_REFERENCE_DANS_TEXTE.sub("", str(point["texte"])).strip()
        points.append({"texte": texte, "sources": sources})
    return points


def libelle_source(source):
    if source["type"] == "alerte":
        return "système expert : " + source["texte"]
    return f"{source['source']}, page {source['page']}"


def analyser_patient(dossier, passages=(), alertes=()):
    """passages : extraits renvoyés par recuperation.recuperer_contexte ; alertes : alertes du système expert.

    Renvoie {"decision", "points": [{"texte", "sources"}], "justification", "sources"} ; "justification" et "sources"
    reprennent les points à plat pour un affichage simple (main.py).
    """
    alertes, passages = list(alertes), list(passages)
    message = json.dumps(resumer_dossier(dossier), ensure_ascii=False, indent=1)
    if alertes:
        message += "\n\nAlertes du système expert :\n" + "\n".join(
            f"[A{i}] {alerte}" for i, alerte in enumerate(alertes, start=1)
        )
    if passages:
        message += "\n\nExtraits des recommandations :\n" + "\n\n".join(
            f"[R{i}] ({p['source']}, page {p['page']})\n{p['texte']}" for i, p in enumerate(passages, start=1)
        )

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
    reponse = json.loads(reponse[reponse.find("{"):reponse.rfind("}") + 1])
    points = lire_reponse(reponse, alertes, passages)
    sources = []
    for point in points:
        for source in point["sources"]:
            if libelle_source(source) not in sources:
                sources.append(libelle_source(source))
    return {
        "decision": reponse.get("decision", "?"),
        "points": points,
        "justification": "\n".join("- " + point["texte"] for point in points),
        "sources": sources,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dossier", required=True, help="dossier contenant les fichiers JSON des patients")
    parser.add_argument("--idpatient", required=True, help="numéro du patient (nom du fichier JSON sans .json)")
    args = parser.parse_args()

    resultat = analyser_patient(charger_patient(args.dossier, args.idpatient))
    print(resultat["decision"])
    print(resultat["justification"])
