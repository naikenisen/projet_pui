"""HTML card of a personalized KBS rule, with its conditions in plain language (no Streamlit)."""

import html

from kbs import OPERATORS
from src.front.rendering.alerts import badge

SYMBOLS = {">=": "≥", "<=": "≤", "!=": "≠", "==": "=", ">": ">", "<": "<"}
PATIENT_DATA = {"age": ("âge", "ans"), "weight_kg": ("poids", "kg"), "height_cm": ("taille", "cm"),
                "bmi_kg_m2": ("IMC", "kg/m²"), "body_surface_area_m2": ("surface corporelle", "m²")}


def readable_number(value):
    return f"{float(value):g}"


def condition_sentence(condition, units):
    """“dose_per_kg_daptomycine < 10” -> “dose de daptomycine < 10 mg/kg/j”."""
    for symbol in OPERATORS:  # same search order as kbs.condition_true
        if symbol in condition:
            name, threshold = (part.strip() for part in condition.split(symbol, 1))
            break
    else:
        return condition
    if name in PATIENT_DATA:
        variable, unit = PATIENT_DATA[name]
    elif name.startswith("daily_dose_"):
        variable, unit = f"dose de {name[len('daily_dose_'):]}", "mg/j"
    elif name.startswith("dose_per_kg_"):
        variable, unit = f"dose de {name[len('dose_per_kg_'):]}", "mg/kg/j"
    elif name.startswith("dose_"):
        variable, unit = f"dosage de {name[len('dose_'):]}", ""
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
    names = [d if isinstance(d, str) else " ou ".join(d) for d in drugs]
    title = " + ".join(n[:1].upper() + n[1:] for n in names) or "Tous les patients"
    origin = "Rédigée par l'assistant" if rule.get("request") else "Règle personnalisée"

    criteria = []
    if names:
        criteria.append(" et ".join(names) + (" prescrits" if len(names) > 1 else " prescrit") + (" (sur des lignes distinctes)" if len(names) > 1 else ""))
    criteria += [condition_sentence(c, units) for c in rule.get("conditions", [])]
    if rule.get("any_of"):
        choices = "".join(f"<li>{html.escape(condition_sentence(c, units))}</li>" for c in rule["any_of"])
        any_of_criteria = f"au moins {rule.get('minimum', 0)} critère(s) parmi :<ul>{choices}</ul>"
    else:
        any_of_criteria = ""
    items = "".join(f"<li>{html.escape(c)}</li>" for c in criteria)
    if any_of_criteria:
        items += f"<li>{any_of_criteria}</li>"

    content = (
        f'<div class="header">{badge(origin, "custom")}<span class="title">{html.escape(title)}</span></div>'
        f'<div class="block"><span class="field-label">Alerte :</span> {html.escape(rule.get("alert", ""))}</div>'
        f'<div class="block"><span class="field-label">Se déclenche si :</span><ul>{items}</ul></div>'
    )
    if rule.get("request"):
        content += f'<div class="footer">Demande du pharmacien : « {html.escape(rule["request"])} »</div>'
    return f'<div class="rule custom">{content}</div>'

