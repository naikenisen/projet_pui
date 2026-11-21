"""“Règles du KBS” page: personalized rules drafted by the LLM assistant, review before saving, list with deletion.

The generic rules (src/kbs/generic_rules.json) are not shown: they are applied during the analysis only.
Personalized rules are edited by hand in src/kbs/personalized_rules.json, outside the interface.
"""

import html

import streamlit as st

from kbs import (
    OPERATORS,
    add_personalized_rule,
    apply_rules,
    biology_parameters,
    load_personalized_rules,
    propose_rule,
    save_personalized_rules,
    unknown_variables,
)
from src.ui.common import badge, label, load_patients


def render_page():
    st.caption(
        "Une règle personnalisée du Knowledge-Based System (KBS) se déclenche lorsque l'ensemble de ses critères "
        "est vérifié. Elle est rédigée par l'assistant à partir d'une demande en langage naturel, puis vérifiée "
        "avant enregistrement. Les règles génériques (Thésaurus ANSM, DDI-Predictor) sont aussi appliquées lors "
        "de l'analyse."
    )
    patients = load_patients()
    parameters = biology_parameters(patients)
    _assistant(parameters)
    _proposed_rule(patients, parameters)
    _rule_list(load_personalized_rules(), parameters)


# ---------------------------------------------------------------------------
# Rule drafted by the LLM: request, then review before saving
# ---------------------------------------------------------------------------

def _assistant(biology_parameters):
    """Natural-language request; the rule proposed by the LLM is kept in st.session_state["proposed_rule"]."""
    label("Ajouter une règle avec l'assistant")
    with st.form("rule_request", border=False):
        request = st.text_area(
            "Demande", label_visibility="collapsed", height=90,
            placeholder="Ex. : Alerter si la metformine est prescrite avec un DFG inférieur à 30 mL/min : "
                        "contre-indication, arrêter la metformine.",
        )
        propose = st.form_submit_button("Proposer une règle", type="primary")
    if propose and request.strip():
        with st.spinner("Rédaction de la règle par le modèle..."):
            try:
                st.session_state["proposed_rule"] = propose_rule(request.strip(), biology_parameters)
            except Exception as error:
                st.session_state.pop("proposed_rule", None)
                st.error(f"Le modèle n'a pas pu rédiger de règle : {error}")


def _proposed_rule(patients, biology_parameters):
    """Card, warnings and number of records that would trigger it, then Save / Cancel."""
    proposed = st.session_state.get("proposed_rule")
    if not proposed:
        return
    label("Règle proposée : à vérifier avant enregistrement")
    st.markdown(rule_card(proposed, biology_parameters), unsafe_allow_html=True)
    for name in unknown_variables(proposed, biology_parameters):
        st.warning(f"La donnée « {name} » n'existe pas dans les dossiers : cette condition sera toujours fausse.")
    triggers = sum(1 for r in patients if apply_rules(r, [proposed]))
    st.caption(f"Se déclencherait pour {triggers} dossier(s) sur {len(patients)}.")
    with st.expander("JSON de la règle"):
        st.json(proposed)
    save_column, cancel_column, _ = st.columns([1, 1, 3])
    if save_column.button("Enregistrer la règle", type="primary", use_container_width=True):
        errors = add_personalized_rule(proposed)
        for error in errors:
            st.error(error)
        if not errors:
            del st.session_state["proposed_rule"]
            st.toast("Règle personnalisée enregistrée.")
            st.rerun()
    if cancel_column.button("Annuler", use_container_width=True):
        del st.session_state["proposed_rule"]
        st.rerun()


# ---------------------------------------------------------------------------
# Saved rules
# ---------------------------------------------------------------------------

def _rule_list(rules, biology_parameters):
    label(f"Règles personnalisées ({len(rules)})")
    if not rules:
        st.caption("Aucune règle personnalisée.")
    for number, rule in enumerate(rules):
        text_column, delete_column = st.columns([7, 1])
        text_column.markdown(rule_card(rule, biology_parameters), unsafe_allow_html=True)
        if delete_column.button("Supprimer", key=f"delete-rule-{number}", use_container_width=True):
            save_personalized_rules(rules[:number] + rules[number + 1:])
            st.rerun()


# ---------------------------------------------------------------------------
# Rule card: alert message, then triggering criteria in plain language
# ---------------------------------------------------------------------------

SYMBOLS = {">=": "≥", "<=": "≤", "!=": "≠", "==": "=", ">": ">", "<": "<"}
PATIENT_DATA = {"age": ("âge", "ans"), "weight_kg": ("poids", "kg"), "height_cm": ("taille", "cm"),
                "bmi_kg_m2": ("IMC", "kg/m²"), "body_surface_area_m2": ("surface corporelle", "m²")}


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
        threshold = f"{float(threshold):g}"
    except ValueError:
        pass
    return f"{variable} {SYMBOLS[symbol]} {threshold} {unit}".strip()


def rule_card(rule, units):
    """HTML card of a personalized rule. units: {laboratory parameter: unit}."""
    drugs = rule.get("drugs", [])
    names = [d if isinstance(d, str) else " ou ".join(d) for d in drugs]
    title = " + ".join(n[:1].upper() + n[1:] for n in names) or "Tous les patients"
    origin = "Rédigée par l'assistant" if rule.get("request") else "Règle personnalisée"

    criteria = []
    if names:
        criteria.append(" et ".join(names) + (" prescrits (sur des lignes distinctes)" if len(names) > 1 else " prescrit"))
    criteria += [condition_sentence(c, units) for c in rule.get("conditions", [])]
    items = "".join(f"<li>{html.escape(c)}</li>" for c in criteria)
    if rule.get("any_of"):
        choices = "".join(f"<li>{html.escape(condition_sentence(c, units))}</li>" for c in rule["any_of"])
        items += f"<li>au moins {rule.get('minimum', 0)} critère(s) parmi :<ul>{choices}</ul></li>"

    content = (
        f'<div class="header">{badge(origin, "custom")}<span class="title">{html.escape(title)}</span></div>'
        f'<div class="block"><span class="field-label">Alerte :</span> {html.escape(rule.get("alert", ""))}</div>'
        f'<div class="block"><span class="field-label">Se déclenche si :</span><ul>{items}</ul></div>'
    )
    if rule.get("request"):
        content += f'<div class="footer">Demande du pharmacien : « {html.escape(rule["request"])} »</div>'
    return f'<div class="rule custom">{content}</div>'
