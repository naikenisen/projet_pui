"""HTML formatting of results, alerts and rules, with no dependency on Streamlit or on the LLM.

Used by app.py (Streamlit interface) to display cards, alerts and tables.
"""

import html
import re

from kbs import OPERATORS, normalize

# ---------------------------------------------------------------------------
# LLM decisions and sources
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Patient record: profile, laboratory values, prescription
# ---------------------------------------------------------------------------

def patient_profile(patient):
    """Readable summary of the patient characteristics (missing fields are omitted)."""
    parts = []
    if patient.get("age") is not None:
        parts.append(f"{patient['age']} years")
    for key, unit in (("weight_kg", "kg"), ("height_cm", "cm"), ("bmi_kg_m2", "kg/m² (BMI)"),
                      ("body_surface_area_m2", "m² (BSA)")):
        if patient.get(key) is not None:
            parts.append(f"{patient[key]} {unit}")
    return " · ".join(parts) or "Age, weight and height not available"


def interpretation(name, value, ranges):
    reference = ranges.get(name)
    if reference is None or not isinstance(value, (int, float)):
        return ""
    if value < reference["min"]:
        return "Low"
    if value > reference["max"]:
        return "High"
    return "Normal"


def biology_table(biology, ranges):
    """(rows, classes) of the laboratory table: abnormal values first, in red."""
    measures = sorted(
        ((name, measure, interpretation(name, measure.get("value"), ranges)) for name, measure in biology.items()),
        key=lambda m: {"Low": 0, "High": 0, "Normal": 1, "": 2}[m[2]],
    )
    rows = [[name, f"{measure.get('value', '')} {measure.get('unit') or ''}".strip(), state,
             (measure.get("test_datetime") or "")[:16]] for name, measure, state in measures]
    classes = ["abnormal" if state in ("Low", "High") else "" for _, _, state in measures]
    return rows, classes


def lines_to_modify(result):
    """Numbers of the prescription lines the LLM proposes to modify (“intervention” points)."""
    return {n for point in (result or {}).get("points", []) for n in point.get("lines_to_modify", [])}


def prescription_table(treatments, to_modify):
    """(rows, classes) of the prescription table: lines to modify in red."""
    rows = [[f"L{number}", t.get("drug_label", ""), t.get("dosage_regimen", ""), t.get("start_date") or "",
             t.get("end_date") or ""] for number, t in enumerate(treatments, start=1)]
    classes = ["abnormal" if number in to_modify else "" for number in range(1, len(treatments) + 1)]
    return rows, classes


def html_table(columns, rows, row_classes=(), short_columns=()):
    """HTML table that fits the width (line wrapping, no scrolling).

    row_classes: CSS class of each row ("abnormal" to colour it red).
    short_columns: columns that must never wrap (identifier, value, dates).
    """
    header = "".join(f"<th>{html.escape(c)}</th>" for c in columns)
    body = ""
    for number, row in enumerate(rows):
        css_class = row_classes[number] if number < len(row_classes) else ""
        cells = "".join(
            f'<td class="short">{html.escape(str(v))}</td>' if c in short_columns else f"<td>{html.escape(str(v))}</td>"
            for c, v in zip(columns, row)
        )
        body += f'<tr class="{css_class}">{cells}</tr>'
    return f'<table class="data-table"><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>'


# ---------------------------------------------------------------------------
# KBS alerts
# ---------------------------------------------------------------------------

def format_text(text):
    """Thesaurus text (in French) as HTML: a line break per level (“Contre-indication avec :”) and per dash."""
    text = html.escape(text, quote=False)
    text = re.sub(
        r"\s*\b(Contre-indication|Association déconseillée|Précaution d'emploi|A prendre en compte)( avec)?\s*:",
        r"<br><b>\1\2 :</b>", text,
    )
    text = re.sub(r"\s+-\s+(?=\S)", "<br>• ", text)
    return text.removeprefix("<br>")


# ANSM Thesaurus levels: code, displayed label, from most to least severe
LEVELS = {"CI": "Contraindication", "ASDEC": "Not recommended", "PE": "Precaution for use",
          "APEC": "To be taken into account"}
# Full level names as written in the Thesaurus (French)
FULL_LEVELS = {"CONTRE-INDICATION": "CI", "Association DECONSEILLEE": "ASDEC", "Précaution d'emploi": "PE",
               "A prendre en compte": "APEC"}
PHARMACOKINETIC = "Pharmacokinetic"
# “Interaction A + B (level) : ...” (Thesaurus) and “Interaction pharmacocinétique A + B : ...” (DDI-Predictor),
# as written in src/kbs/generic_rules.json
_CODE = "(?:CI|ASDEC|PE|APEC)"
THESAURUS_ALERT_PATTERN = re.compile(
    rf"^Interaction (.+?) \(({_CODE}(?: - {_CODE})*|{'|'.join(map(re.escape, FULL_LEVELS))})\) : (.*)$", re.DOTALL
)
DDI_ALERT_PATTERN = re.compile(r"^Interaction pharmacocinétique (.+?) : (.*)$", re.DOTALL)


def level_codes(rule):
    """“CI - ASDEC - APEC” -> ["CI", "ASDEC", "APEC"]; [] for a rule without level (DDI-Predictor, personalized)."""
    level = rule.get("level") or ""
    if level in FULL_LEVELS:
        return [FULL_LEVELS[level]]
    return [code.strip() for code in level.split("-") if code.strip() in LEVELS]


def badge(text, css_class):
    return f'<span class="badge {css_class}">{html.escape(text)}</span>'


def html_alert(alert):
    """KBS alert: level and title, message, recommended action and prescription lines."""
    alert, _, prescription = alert.partition(" [Prescription: ")
    header = ""
    if found := THESAURUS_ALERT_PATTERN.match(alert):
        title, level, alert = found.groups()
        header = "".join(badge(LEVELS[c], c.lower()) for c in level_codes({"level": level}))
        header += f" <b>{html.escape(title)}</b>"
    elif found := DDI_ALERT_PATTERN.match(alert):
        title, alert = found.groups()
        header = f'{badge(PHARMACOKINETIC, "pk")} <b>{html.escape(title)}</b>'
    message, _, management = alert.partition(" Conduite à tenir : ")
    content = f'<div class="alert-header">{header}</div>' if header else ""
    content += format_text(message)
    if management:
        content += f'<div class="complement"><b>Recommended action:</b><br>{format_text(management)}</div>'
    if prescription:
        content += f'<div class="prescription">Prescription: {html.escape(prescription.rstrip("]"))}</div>'
    return f'<div class="alert">{content}</div>'


# ---------------------------------------------------------------------------
# KBS rules
# ---------------------------------------------------------------------------

SYMBOLS = {">=": "≥", "<=": "≤", "!=": "≠", "==": "=", ">": ">", "<": "<"}
PATIENT_DATA = {"age": ("age", "years"), "weight_kg": ("weight", "kg"), "height_cm": ("height", "cm"),
                "bmi_kg_m2": ("BMI", "kg/m²"), "body_surface_area_m2": ("body surface area", "m²")}


def readable_number(value):
    return f"{float(value):g}"


def condition_sentence(condition, units):
    """“dose_per_kg_daptomycine < 10” -> “dose of daptomycine < 10 mg/kg/day”."""
    for symbol in OPERATORS:  # same search order as kbs.condition_true
        if symbol in condition:
            name, threshold = (part.strip() for part in condition.split(symbol, 1))
            break
    else:
        return condition
    if name in PATIENT_DATA:
        variable, unit = PATIENT_DATA[name]
    elif name.startswith("daily_dose_"):
        variable, unit = f"dose of {name[len('daily_dose_'):]}", "mg/day"
    elif name.startswith("dose_per_kg_"):
        variable, unit = f"dose of {name[len('dose_per_kg_'):]}", "mg/kg/day"
    elif name.startswith("dose_"):
        variable, unit = f"strength of {name[len('dose_'):]}", ""
    else:
        variable, unit = name, units.get(name, "")
    try:
        threshold = readable_number(threshold)
    except ValueError:
        pass
    return f"{variable} {SYMBOLS[symbol]} {threshold} {unit}".strip()


def personalized_rule_card(rule, units):
    """HTML card: alert message then triggering criteria in plain language."""
    drugs = rule.get("drugs", [])
    names = [d if isinstance(d, str) else " or ".join(d) for d in drugs]
    title = " + ".join(n[:1].upper() + n[1:] for n in names) or "All patients"
    origin = "Drafted by the assistant" if rule.get("request") else "Personalized rule"

    criteria = []
    if names:
        criteria.append(" and ".join(names) + " prescribed" + (" (on different lines)" if len(names) > 1 else ""))
    criteria += [condition_sentence(c, units) for c in rule.get("conditions", [])]
    if rule.get("any_of"):
        choices = "".join(f"<li>{html.escape(condition_sentence(c, units))}</li>" for c in rule["any_of"])
        any_of_criteria = f"at least {rule.get('minimum', 0)} criterion/criteria among:<ul>{choices}</ul>"
    else:
        any_of_criteria = ""
    items = "".join(f"<li>{html.escape(c)}</li>" for c in criteria)
    if any_of_criteria:
        items += f"<li>{any_of_criteria}</li>"

    content = (
        f'<div class="header">{badge(origin, "custom")}<span class="title">{html.escape(title)}</span></div>'
        f'<div class="block"><span class="field-label">Alert:</span> {html.escape(rule.get("alert", ""))}</div>'
        f'<div class="block"><span class="field-label">Triggered if:</span><ul>{items}</ul></div>'
    )
    if rule.get("request"):
        content += f'<div class="footer">Pharmacist request: “{html.escape(rule["request"])}”</div>'
    return f'<div class="rule custom">{content}</div>'


def generic_rule_card(rule):
    """HTML card: level, drug pair, risk, recommended action and INNs searched for."""
    codes = level_codes(rule)
    if codes:
        badges = "".join(badge(LEVELS[c], c.lower()) for c in codes)
        css_class = codes[0].lower()  # the most severe gives the card colour
    else:
        badges, css_class = badge(PHARMACOKINETIC, "pk"), ""
    title = rule.get("title") or " + ".join(d if isinstance(d, str) else "class" for d in rule.get("drugs", []))

    if "risk" in rule:
        content = f'<div class="block"><span class="field-label">Risk:</span> {format_text(rule["risk"])}</div>'
        if rule.get("management"):
            content += (f'<div class="block"><span class="field-label">Recommended action:</span><br>'
                        f'{format_text(rule["management"])}</div>')
    else:
        content = f'<div class="block">{format_text(rule["alert"])}</div>'

    # INNs searched for in the labels, mostly useful for Thesaurus classes
    parts = title.split(" + ")
    drugs = rule.get("drugs", [])
    if any(not isinstance(d, str) for d in drugs):
        inn_rows = ""
        for number, drug in enumerate(drugs):
            name = parts[number] if len(parts) == len(drugs) else f"Drug {number + 1}"
            inns = [drug] if isinstance(drug, str) else drug
            chips = "".join(f'<span class="chip">{html.escape(d)}</span>' for d in inns)
            inn_rows += f'<div class="block"><span class="field-label">{html.escape(name)}:</span> {chips}</div>'
        content += f"<details><summary>INNs searched for in the prescription</summary>{inn_rows}</details>"

    return (f'<div class="rule {css_class}"><div class="header">{badges}'
            f'<span class="title">{html.escape(title)}</span></div>{content}'
            f'<div class="footer">{html.escape(rule.get("source", ""))}</div></div>')
