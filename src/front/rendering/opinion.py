"""Status of a patient record and reading of the LLM decision (no Streamlit)."""

import re

from generation import DECISION_INTERVENTION, DECISION_MONITORING, DECISION_VALIDATED, DECISION_VERIFICATION

# Category of each decision written by generation.py
CATEGORIES = {DECISION_INTERVENTION: "intervention", DECISION_VERIFICATION: "verification",
              DECISION_MONITORING: "monitoring", DECISION_VALIDATED: "validated"}


def category(decision):
    """Category code of a decision: validated, monitoring, verification or intervention.

    An unknown decision is shown as an intervention, so that the record is checked first."""
    return CATEGORIES.get(decision, "intervention")


# Recognises for instance "reco_sfd.pdf, page 12", "reco_sfd.pdf p. 12" or "reco_sfd.pdf"
SOURCE_PATTERN = re.compile(r"([^,;\[\]()]+?\.pdf)\s*(?:[,\-–:]?\s*(?:pages?|p\.?)\s*(\d+))?", re.IGNORECASE)


def read_source(source):
    """Returns (pdf_name, page) if the source refers to a PDF, otherwise None. page is 1 if not given."""
    found = SOURCE_PATTERN.search(str(source))
    if not found:
        return None
    return found.group(1).strip(), int(found.group(2) or 1)


STATUS_LABELS = {
    "intervention": "Intervention proposée",
    "verification": "Vérification proposée",
    "monitoring": "Surveillance proposée",
    "validated": "Validé",
    "error": "Erreur d'analyse",
    "not_analysed": "Non analysé",
}
# Decision shown in the opinion, by category (the LLM writes it in English, see generation.py)
DECISION_LABELS = {
    "intervention": "INTERVENTION PHARMACEUTIQUE PROPOSÉE",
    "verification": "VÉRIFICATION PROPOSÉE",
    "monitoring": "SURVEILLANCE PROPOSÉE",
    "validated": "PATIENT VALIDÉ",
}
# Records requiring an action are listed first
STATUS_ORDER = {"intervention": 0, "verification": 1, "monitoring": 2, "error": 3, "not_analysed": 4, "validated": 5}
STATUS_COLORS = {"intervention": "#A85A00", "verification": "#6B3FA0", "monitoring": "#0B4F8A",
                 "error": "#B42318", "not_analysed": "#7A8899", "validated": "#1E7A46"}


def status(result):
    """Returns (code, label) of the status of a record."""
    if result is None:
        code = "not_analysed"
    elif "error" in result:
        code = "error"
    else:
        code = category(result["decision"])
    return code, STATUS_LABELS[code]
