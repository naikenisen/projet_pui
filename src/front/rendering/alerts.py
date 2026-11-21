"""HTML of the KBS alerts and badges of the ANSM Thesaurus levels (no Streamlit)."""

import html
import re

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
LEVELS = {"CI": "Contre-indication", "ASDEC": "Association déconseillée", "PE": "Précaution d'emploi",
          "APEC": "À prendre en compte"}
# Full level names as written in the Thesaurus (French)
FULL_LEVELS = {"CONTRE-INDICATION": "CI", "Association DECONSEILLEE": "ASDEC", "Précaution d'emploi": "PE",
               "A prendre en compte": "APEC"}
PHARMACOKINETIC = "Pharmacocinétique"
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
        content += f'<div class="complement"><b>Conduite à tenir :</b><br>{format_text(management)}</div>'
    if prescription:
        content += f'<div class="prescription">Prescription : {html.escape(prescription.rstrip("]"))}</div>'
    return f'<div class="alert">{content}</div>'
