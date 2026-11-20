"""Analyse d'un patient (RAG + système expert + LLM) et lecture des sources citées par le LLM."""

import re
from datetime import datetime

from expert_system import normaliser, verifier_regles
from generation import analyser_patient
from recuperation import recuperer_contexte

# Catégorie de chaque décision, reconnue par un mot-clé (tolère les petites variantes de libellé du LLM).
# Les plus graves sont cherchées en premier.
CATEGORIES = (("intervention", "intervention"), ("verif", "verification"), ("surveill", "surveillance"), ("valid", "valide"))


def categorie(decision):
    """Code de la catégorie d'une décision : valide, surveillance, verification ou intervention (par défaut)."""
    texte = normaliser(decision)
    for mot_cle, code in CATEGORIES:
        if mot_cle in texte:
            return code
    return "intervention"

# Reconnaît par exemple "reco_sfd.pdf, page 12", "reco_sfd.pdf p. 12" ou "reco_sfd.pdf"
MOTIF_SOURCE = re.compile(r"([^,;\[\]()]+?\.pdf)\s*(?:[,\-–:]?\s*(?:pages?|p\.?)\s*(\d+))?", re.IGNORECASE)


def analyser(dossier):
    """Même enchaînement que main.py, pour un seul patient. Ne lève pas d'exception."""
    try:
        alertes = verifier_regles(dossier)
        passages = recuperer_contexte(dossier)
        resultat = analyser_patient(dossier, passages, alertes)
        return {
            "decision": resultat["decision"],
            "points": resultat["points"],
            "justification": resultat["justification"],
            "sources": resultat["sources"],
            "alertes": alertes,
            "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
        }
    except Exception as erreur:
        return {"erreur": f"{type(erreur).__name__} : {erreur}", "date": datetime.now().strftime("%d/%m/%Y %H:%M")}


def lire_source(source):
    """Renvoie (nom_pdf, page) si la source désigne un PDF, sinon None. page vaut 1 si elle n'est pas précisée."""
    trouve = MOTIF_SOURCE.search(str(source))
    if not trouve:
        return None
    return trouve.group(1).strip(), int(trouve.group(2) or 1)
