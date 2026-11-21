"""Status of a patient record and reading of the LLM decision (no Streamlit)."""

import re

from kbs import normalize

# Category of each decision, recognised by a keyword (tolerates small variations in the LLM wording).
# The most severe ones are searched first.
CATEGORIES = (("intervention", "intervention"), ("verif", "verification"), ("monitor", "monitoring"),
              ("valid", "validated"))


def category(decision):
    """Category code of a decision: validated, monitoring, verification or intervention (default)."""
    text = normalize(decision)
    for keyword, code in CATEGORIES:
        if keyword in text:
            return code
    return "intervention"


# Recognises for instance "reco_sfd.pdf, page 12", "reco_sfd.pdf p. 12" or "reco_sfd.pdf"
SOURCE_PATTERN = re.compile(r"([^,;\[\]()]+?\.pdf)\s*(?:[,\-–:]?\s*(?:pages?|p\.?)\s*(\d+))?", re.IGNORECASE)


def read_source(source):
    """Returns (pdf_name, page) if the source refers to a PDF, otherwise None. page is 1 if not given."""
    found = SOURCE_PATTERN.search(str(source))
    if not found:
        return None
    return found.group(1).strip(), int(found.group(2) or 1)


STATUS_LABELS = {
    "intervention": "Intervention proposed",
    "verification": "Verification proposed",
    "monitoring": "Monitoring proposed",
    "validated": "Validated",
    "error": "Analysis error",
    "not_analysed": "Not analysed",
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


def inferred_type(text, decision_category):
    """Type of a point from an analysis made before typed points, from its wording and the decision."""
    start = normalize(text)[:60]
    if "verif" in start:
        return "verification"
    if "monitor" in start:
        return "monitoring"
    return "validation" if decision_category == "validated" else decision_category
