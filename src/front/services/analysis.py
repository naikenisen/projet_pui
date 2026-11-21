"""Analysis of one patient (RAG + KBS + LLM)."""

from datetime import datetime

from generation import analyse_patient
from kbs import check_rules
from retrieval import retrieve_context
from src.front.services.data import save_results


def analyse(record):
    """Same sequence as main.py, for a single patient. Never raises an exception: errors are stored in the result."""
    try:
        alerts = check_rules(record)
        passages = retrieve_context(record)
        result = analyse_patient(record, passages, alerts)
        return {
            "decision": result["decision"],
            "points": result["points"],
            "reasoning": result["reasoning"],
            "justification": result["justification"],
            "sources": result["sources"],
            "alerts": alerts,
            "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
        }
    except Exception as error:
        return {"error": f"{type(error).__name__}: {error}", "date": datetime.now().strftime("%d/%m/%Y %H:%M")}


def analyse_and_save(results, record):
    """Analyses the record, stores the result in results and saves the results file at once."""
    results[record["patient"]["id"]] = analyse(record)
    save_results(results)
