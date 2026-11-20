"""Analyse l'ordonnance d'un patient avec le LLM."""

import argparse
import json
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

from expert_system import charger_patient, normaliser

load_dotenv()
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])

MODEL = "qwen/qwen3.6-35b-a3b"
# Mode raisonnement du modèle : avis nettement plus cohérents (exceptions des alertes, sens de la biologie),
# mais environ 40 s par patient au lieu de 10 s. Mettre False pour une analyse rapide.
RAISONNEMENT = True

DECISION_VALIDE = "PATIENT VALIDÉ"
DECISION_SURVEILLANCE = "SURVEILLANCE PROPOSÉE"
DECISION_VERIFICATION = "VÉRIFICATION PROPOSÉE"
DECISION_INTERVENTION = "INTERVENTION PHARMACEUTIQUE PROPOSÉE"

SYSTEM_PROMPT = f"""Tu es un pharmacien clinicien hospitalier français. On te fournit un patient et son ordonnance au format JSON.

Contenu du dossier :
- "jour_reference" est la date à laquelle l'ordonnance est analysée. Une donnée absente n'est pas renseignée.
- Chaque valeur biologique est donnée avec son unité et sa date ; « (basse) » ou « (élevée) » indique qu'elle sort
  des valeurs de référence de l'établissement.
- Chaque ligne de traitement a un identifiant (L1, L2...), un libellé (spécialité, dosage, forme), une posologie,
  des dates, un statut au jour de référence (« en cours », « terminée », « à venir ») et, quand elle est calculable,
  "dose_par_jour_d_administration" (déjà calculée : utilise-la telle quelle, ne refais pas le calcul). Pour une
  posologie « 1 jour sur N », cette dose n'est prise qu'un jour sur N.
- Seules les lignes « en cours » sont actives. Deux lignes dont les dates ne se chevauchent pas se succèdent : ce
  n'est pas un doublon. Une ligne systématique et une ligne « si besoin » du même médicament (ex : morphine) sont
  une pratique courante, pas un doublon.

Ce que tu ne sais PAS : le dossier ne contient ni diagnostic, ni antécédent, ni indication, ni examen clinique.
- N'affirme jamais qu'un médicament n'est pas indiqué, qu'une pathologie est absente ou présente (sauf si la
  biologie le montre), ni qu'un traitement est « inutile ». Ne propose jamais d'arrêter un médicament pour défaut
  d'indication et ne propose pas de vérifier l'indication d'un traitement.
- Ne suppose pas d'information absente (fragilité, espérance de vie, contexte clinique). Chaque proposition doit
  reposer sur un fait du dossier (dose, biologie, âge, poids, dates, association de lignes) ou sur une alerte ou un
  extrait fourni.
- Si un point repose uniquement sur tes connaissances (aucune alerte ni extrait), ne propose d'intervention ni de
  vérification que pour une erreur manifeste (dose au-delà du maximum de l'AMM, contre-indication confirmée par la
  biologie) ou pour le même médicament sur plusieurs lignes. Une posologie dans les plages habituelles, même
  discutable, n'appelle ni intervention ni vérification.

Des alertes du système expert [A1], [A2]... et des extraits de recommandations [R1], [R2]... peuvent être fournis.
Les alertes du Thésaurus ANSM indiquent leur niveau entre parenthèses. Un niveau combiné (ex : « CI - ASDEC - APEC »)
signifie que le niveau dépend des molécules ou des doses : lis la conduite à tenir pour déterminer le niveau qui
s'applique réellement à cette prescription (ex : aspirine à dose antiagrégante + héparine = « à prendre en compte »,
pas « déconseillée »). Hiérarchise ensuite les alertes :
- les CONTRE-INDICATIONS sont prioritaires ;
- les autres alertes (association déconseillée, précaution d'emploi, interaction pharmacocinétique) ne justifient
  une intervention que si, compte tenu des données de ce patient (âge, fonction rénale, biologie, doses), le risque
  est cliniquement crucial. Sinon, elles relèvent au plus d'une surveillance, ou sont simplement acceptables.
Une alerte ne justifie donc jamais à elle seule une intervention.

Cohérence avec le patient (à contrôler pour chaque point) :
- Lis la conduite à tenir de chaque alerte en entier. Si elle prévoit une exception qui s'applique au patient
  (ex : « Sauf s'il existe une hypokaliémie » alors que la kaliémie est basse), l'alerte ne s'applique pas.
- Vérifie le sens de chaque anomalie biologique. Un traitement qui corrige une valeur anormale (ex : potassium
  si kaliémie basse, vitamine D si carence) est justifié par cette valeur : ne t'appuie jamais sur elle pour
  proposer de l'arrêter ou de le réduire.
- Une ligne de 1 ou 2 jours qui chevauche une ligne plus longue du même médicament est souvent une dose de charge.
- Un point ne doit contredire ni la biologie, ni les dates, ni la conduite à tenir des alertes.

Chaque point a un type :
- "intervention" : un problème avéré et cliniquement important impose de modifier la prescription.
- "verification" : à réserver aux cas où (1) si l'hypothèse se confirmait, le problème justifierait une
  intervention et (2) une information absente du dossier est indispensable pour trancher. Exemple typique : le
  même médicament sur plusieurs lignes en cours et systématiques (dosage global volontaire ou oubli d'arrêter une
  ligne ?). Une liste de ces lignes multiples, avec la dose totale, peut t'être fournie. Associer deux dosages
  pour obtenir une dose précise est courant (ex : lévothyroxine 150 + 12,5 µg) : ne propose une vérification que
  si la dose totale est inhabituelle ou dépasse la dose maximale.
- "surveillance" : association ou posologie acceptable mais qui justifie une surveillance clinique ou biologique
  spécifique (ex : kaliémie, INR, ECG, glycémie, fonction rénale).
- "validation" : rien à signaler. Utilisé seul, en un point unique, quand l'ordonnance est validée.

Réponds uniquement avec un objet JSON. Commence par "raisonnement" : en 3 à 6 phrases, les anomalies
biologiques et leur sens, les alertes qui s'appliquent réellement (exceptions comprises), puis les problèmes retenus.
{{"raisonnement": "...", "points": [{{"type": "intervention", "texte": "une proposition courte", "references": ["A1", "R2"],
  "lignes_a_modifier": ["L3"]}}]}}

Règles pour les points :
- 1 à 4 points, un par problème, du plus important au moins important.
- Chaque point tient en une ou deux phrases courtes (40 mots au plus) et commence par « Proposons » ou
  « Suggérons » (ou « Aucune intervention proposée » pour une validation). Ne fais pas de point sur une
  prescription conforme ni sur un élément sans conséquence pratique.
- Exemples de formulation : « Proposons une réduction de l'apixaban à 2,5 mg x 2/j compte tenu de la créatininémie
  à 155 µmol/L et de l'âge (95 ans) », « Suggérons de vérifier auprès du prescripteur si les deux lignes
  d'irbésartan (150 mg et 300 mg/j) sont volontaires », « Proposons une surveillance de la kaliémie... ».
- Cite le médicament en cause et les valeurs du patient qui justifient le point. N'écris aucun identifiant
  d'alerte ou d'extrait (A1, R2) dans "texte" ; tu peux désigner une ligne par son identifiant (L3).
- "references" : uniquement les identifiants des alertes et extraits fournis sur lesquels le point s'appuie
  réellement. N'invente jamais d'identifiant ; liste vide si le point repose sur tes connaissances.
- "lignes_a_modifier" : pour un point "intervention" seulement, les identifiants des lignes dont tu proposes la
  modification ou l'arrêt ; liste vide pour les autres types."""


# ---------------------------------------------------------------------------
# Préparation du dossier : ce qui peut être calculé l'est par le code, pas par le LLM
# ---------------------------------------------------------------------------

FICHIER_NORMES_BIO = "bio_anormale.json"

# Unités de prise qui sont déjà une quantité de principe actif
UNITES_QUANTITE = {"milligramme(s)": (1, "mg"), "gramme(s)": (1000, "mg"), "microgramme(s)": (1, "µg"),
                   "unité(s) internationale(s)": (1, "UI"), "unité(s) internationale(s) anti-Xa": (1, "UI anti-Xa")}
# Formes unitaires dont le dosage du principe actif est la quantité par unité (pas une concentration)
FORMES_UNITAIRES = ("comprimé", "gélule", "sachet", "ampoule", "seringue", "capsule", "suppositoire", "stylo", "film")
UNITES_DOSAGE = {"mg": (1, "mg"), "g": (1000, "mg"), "ug": (1, "µg"), "iu": (1, "UI"), "axa_iu": (1, "UI anti-Xa"), "u": (1, "U")}


def nombre(valeur):
    return f"{valeur:g}".replace(".", ",") if valeur < 1e6 else f"{valeur:.0f}"


def dose_par_jour(traitement):
    """Dose de principe actif par jour d'administration : (3000, "mg"), ou None si elle n'est pas calculable."""
    quantite = traitement.get("quantite_par_jour")
    if not isinstance(quantite, (int, float)) or quantite <= 0:
        return None
    unite = traitement.get("unite_prise") or ""
    if unite in UNITES_QUANTITE:
        facteur, symbole = UNITES_QUANTITE[unite]
        return quantite * facteur, symbole
    principes = traitement.get("principes_actifs") or []
    if (any(unite.startswith(forme) for forme in FORMES_UNITAIRES) and len(principes) == 1
            and principes[0].get("unite") in UNITES_DOSAGE and isinstance(principes[0].get("dosage"), (int, float))):
        facteur, symbole = UNITES_DOSAGE[principes[0]["unite"]]
        return quantite * principes[0]["dosage"] * facteur, symbole
    return None


def statut_ligne(traitement, jour_reference):
    """« en cours », « terminée » ou « à venir » au jour de référence (dates au format AAAA-MM-JJ)."""
    if not jour_reference:
        return "en cours"
    debut, fin = (traitement.get("date_debut") or "")[:10], (traitement.get("date_fin") or "")[:10]
    if debut and debut > jour_reference:
        return "à venir"
    if fin and fin < jour_reference:
        return "terminée"
    return "en cours"


def nom_medicament(libelle):
    """« IRBESARTAN 150 MG (LABO ARROW), CPR » -> « IRBESARTAN » : le nom avant le dosage ou la forme."""
    return re.split(r"[\d,(]", libelle, maxsplit=1)[0].strip().upper()


def lire_normes_bio():
    if not os.path.exists(FICHIER_NORMES_BIO):
        return {}
    with open(FICHIER_NORMES_BIO, encoding="utf-8") as fichier:
        return json.load(fichier)


def interpretation_bio(nom, valeur, normes):
    """« basse », « élevée » ou "" selon les valeurs de référence de bio_anormale.json."""
    norme = normes.get(nom)
    if norme is None or not isinstance(valeur, (int, float)) or isinstance(valeur, bool):
        return ""
    if valeur < norme["min"]:
        return "basse"
    if valeur > norme["max"]:
        return "élevée"
    return ""


def resumer_dossier(dossier):
    """Version du dossier envoyée au LLM : champs vides retirés, biologie interprétée, lignes numérotées L1, L2...
    avec leur statut au jour de référence et la dose par jour d'administration calculée."""
    patient = dossier["patient"]
    resume = {cle: valeur for cle, valeur in patient.items() if cle != "biologie" and valeur is not None}
    normes = lire_normes_bio()
    resume["biologie"] = {}
    for nom, mesure in patient["biologie"].items():
        texte = f"{mesure['valeur']} {mesure.get('unite') or ''}".strip()
        if interpretation := interpretation_bio(nom, mesure.get("valeur"), normes):
            texte += f" ({interpretation})"
        resume["biologie"][nom] = f"{texte} le {mesure.get('date_heure_examen') or '?'}"

    traitements = []
    for numero, traitement in enumerate(dossier["traitements"], start=1):
        ligne = {"id": f"L{numero}"}
        ligne |= {cle: traitement[cle] for cle in ("libelle_medicament", "posologie", "date_debut", "date_fin")
                  if traitement.get(cle)}
        ligne["statut"] = statut_ligne(traitement, patient.get("jour_reference"))
        if traitement.get("si_besoin"):
            ligne["si_besoin"] = True
        elif dose := dose_par_jour(traitement):
            ligne["dose_par_jour_d_administration"] = f"{nombre(dose[0])} {dose[1]}"
        traitements.append(ligne)
    return {"patient": resume, "traitements": traitements}


def lignes_multiples(dossier):
    """Médicaments prescrits sur plusieurs lignes en cours et systématiques (hors « si besoin ») :
    dosage global volontaire ou oubli d'arrêter une ligne. Renvoie une phrase par médicament, avec la dose
    totale quand elle est calculable : « IRBESARTAN : L11 (150 mg) + L19 (300 mg) = 450 mg par jour »."""
    jour = dossier["patient"].get("jour_reference")
    groupes = {}
    for numero, traitement in enumerate(dossier["traitements"], start=1):
        if traitement.get("si_besoin") or statut_ligne(traitement, jour) != "en cours":
            continue
        groupes.setdefault(nom_medicament(traitement["libelle_medicament"]), []).append((numero, dose_par_jour(traitement)))
    phrases = []
    for nom, lignes in groupes.items():
        if not nom or len(lignes) < 2:
            continue
        doses = [dose for _, dose in lignes]
        if all(doses) and len({symbole for _, symbole in doses}) == 1:
            detail = " + ".join(f"L{numero} ({nombre(dose[0])} {dose[1]})" for numero, dose in lignes)
            detail += f" = {nombre(sum(d[0] for d in doses))} {doses[0][1]} par jour"
        else:
            detail = " + ".join(f"L{numero}" for numero, _ in lignes)
        phrases.append(f"{nom} : {detail}")
    return phrases


# Identifiant recopié dans le texte malgré la consigne : « (A1, A2) », « (alerte A1 niveau ...) », « [R2] » (les numéros de ligne L3 restent : ils sont affichés dans le tableau de prescription)
MOTIF_REFERENCE_DANS_TEXTE = re.compile(r"\s*(?:\([^()]*\b[AR]\d+\b[^()]*\)|\[[AR]\d+(?:\s*,\s*[AR]\d+)*\])")


TYPES_POINT = ("intervention", "verification", "surveillance", "validation")  # du plus grave au moins grave
DECISION_PAR_TYPE = {"intervention": DECISION_INTERVENTION, "verification": DECISION_VERIFICATION,
                     "surveillance": DECISION_SURVEILLANCE, "validation": DECISION_VALIDE}


def type_point(valeur):
    """Type d'un point, tolérant aux variantes (« Vérification », « IP »...) ; "verification" s'il est inconnu."""
    texte = normaliser(valeur).strip()
    if texte == "ip" or "interv" in texte:
        return "intervention"
    for mot_cle, code in (("verif", "verification"), ("surveil", "surveillance"), ("valid", "validation")):
        if mot_cle in texte:
            return code
    return "verification"


def lire_reponse(reponse, alertes, passages, nb_lignes):
    """Remplace les identifiants cités par le LLM par les alertes, extraits et lignes correspondants.

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
        type_ = type_point(point.get("type", ""))
        lignes = []
        if type_ == "intervention":
            for identifiant in point.get("lignes_a_modifier") or []:
                trouve = re.fullmatch(r"L(\d+)", str(identifiant).strip(" []").upper())
                if trouve and 1 <= int(trouve.group(1)) <= nb_lignes and int(trouve.group(1)) not in lignes:
                    lignes.append(int(trouve.group(1)))
        texte = MOTIF_REFERENCE_DANS_TEXTE.sub("", str(point["texte"])).strip()
        points.append({"type": type_, "texte": texte, "sources": sources, "lignes_a_modifier": lignes})
    return points


def libelle_source(source):
    if source["type"] == "alerte":
        return "système expert : " + source["texte"]
    return f"{source['source']}, page {source['page']}"


def analyser_patient(dossier, passages=(), alertes=()):
    """passages : extraits renvoyés par recuperation.recuperer_contexte ; alertes : alertes du système expert.

    Renvoie {"decision", "points": [{"type", "texte", "sources", "lignes_a_modifier"}], "justification", "sources"}.
    La décision est celle du point le plus grave, pour qu'elle soit toujours cohérente avec les points.
    "justification" et "sources" reprennent les points à plat pour un affichage simple (main.py).
    """
    alertes, passages = list(alertes), list(passages)
    message = json.dumps(resumer_dossier(dossier), ensure_ascii=False, indent=1)
    if multiples := lignes_multiples(dossier):
        message += "\n\nMême médicament sur plusieurs lignes en cours et systématiques :\n" + "\n".join(
            f"- {phrase}" for phrase in multiples
        )
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
        max_tokens=12000 if RAISONNEMENT else 2500,  # le raisonnement consomme des jetons
        temperature=0,
        response_format={"type": "json_object"},
        extra_body={"reasoning": {"enabled": RAISONNEMENT}},
    )
    reponse = completion.choices[0].message.content

    # Garde uniquement le JSON, au cas où le modèle ajoute du texte autour.
    reponse = json.loads(reponse[reponse.find("{"):reponse.rfind("}") + 1])
    points = lire_reponse(reponse, alertes, passages, len(dossier["traitements"]))
    # Un point « validation » n'a de sens que seul
    if any(point["type"] != "validation" for point in points):
        points = [point for point in points if point["type"] != "validation"]
    plus_grave = min((TYPES_POINT.index(point["type"]) for point in points), default=TYPES_POINT.index("validation"))

    sources = []
    for point in points:
        for source in point["sources"]:
            if libelle_source(source) not in sources:
                sources.append(libelle_source(source))
    return {
        "decision": DECISION_PAR_TYPE[TYPES_POINT[plus_grave]],
        "points": points,
        "raisonnement": str(reponse.get("raisonnement", "")).strip(),
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
