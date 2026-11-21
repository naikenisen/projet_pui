"""HTML cards of the KBS rules, with their conditions in plain language (no Streamlit)."""

import html

from kbs import OPERATORS
from src.front.rendering.alerts import LEVELS, PHARMACOKINETIC, badge, format_text, level_codes

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
