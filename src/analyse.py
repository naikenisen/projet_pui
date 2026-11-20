"""Analyse d'un patient (RAG + système expert + LLM)."""

from datetime import datetime

from expert_system import verifier_regles
from generation import analyser_patient
from recuperation import recuperer_contexte


def analyser(dossier):
    """Même enchaînement que main.py, pour un seul patient. Ne lève pas d'exception."""
    try:
        alertes = verifier_regles(dossier)
        passages = recuperer_contexte(dossier)
        resultat = analyser_patient(dossier, passages, alertes)
        return {
            "decision": resultat["decision"],
            "points": resultat["points"],
            "raisonnement": resultat["raisonnement"],
            "justification": resultat["justification"],
            "sources": resultat["sources"],
            "alertes": alertes,
            "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
        }
    except Exception as erreur:
        return {"erreur": f"{type(erreur).__name__} : {erreur}", "date": datetime.now().strftime("%d/%m/%Y %H:%M")}

