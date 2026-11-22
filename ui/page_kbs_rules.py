# "Règles du KBS" page: personalized CLIPS rules drafted by the LLM, checked and listed.

import html
import re

import streamlit as st

from kbs import (
    REQUEST_PREFIX,
    add_personalized_rule,
    apply_rules,
    biology_parameters,
    create_environment,
    load_personalized_rules,
    propose_rule,
    rule_names,
    save_personalized_rules,
    unknown_data,
)
from ui.common import badge, label, load_patients

# Alert text: (message "...") in the CLIPS code
ALERT_MESSAGE = re.compile(r'\(message\s+"((?:[^"\\]|\\.)*)"')


def render_page():
    patients = load_patients()
    parameters = biology_parameters(patients)
    _assistant(parameters)
    _proposed_rule(patients, parameters)
    _rule_list(load_personalized_rules())


# The rule proposed by the LLM is kept in st.session_state["proposed_rule"]
def _assistant(biology_parameters):
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


# Card, warnings and number of triggered records, then Save / Cancel
def _proposed_rule(patients, biology_parameters):
    proposed = st.session_state.get("proposed_rule")
    if not proposed:
        return
    label("Règle proposée : à vérifier avant enregistrement")
    show_rule(proposed)
    for name in unknown_data(proposed, biology_parameters):
        st.warning(f"La donnée « {name} » n'existe pas dans les dossiers : les conditions sur elle seront toujours fausses.")
    env = create_environment(proposed)
    triggers = sum(1 for record in patients if apply_rules(record, env))
    st.caption(f"Se déclencherait pour {triggers} dossier(s) sur {len(patients)}.")
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


def _rule_list(rules):
    label(f"Règles personnalisées ({len(rules)})")
    if not rules:
        st.caption("Aucune règle personnalisée.")
    for number, rule in enumerate(rules):
        text_column, delete_column = st.columns([7, 1])
        with text_column:
            show_rule(rule)
        if delete_column.button("Supprimer", key=f"delete-rule-{number}", use_container_width=True):
            errors = save_personalized_rules(rules[:number] + rules[number + 1:])
            for error in errors:
                st.error(error)
            if not errors:
                st.rerun()


def show_rule(rule):
    st.markdown(rule_card(rule), unsafe_allow_html=True)
    with st.expander("Code CLIPS"):
        st.code(rule, language="lisp")


# Title: first comment of the rule (except the pharmacist request), else name of the first defrule
def rule_title(rule):
    for line in rule.splitlines():
        if line.startswith(";") and not line.startswith(REQUEST_PREFIX):
            return line.lstrip("; ")
    names = rule_names(rule)
    return names[0] if names else "Règle"


# HTML card of a rule: title, alerts and pharmacist request
def rule_card(rule):
    request = next((line[len(REQUEST_PREFIX):] for line in rule.splitlines() if line.startswith(REQUEST_PREFIX)), "")
    origin = "Rédigée par l'assistant" if request else "Règle personnalisée"
    alerts = "".join(f"<li>{html.escape(message)}</li>" for message in ALERT_MESSAGE.findall(rule))

    content = (
        f'<div class="header">{badge(origin, "custom")}<span class="title">{html.escape(rule_title(rule))}</span></div>'
        f'<div class="block"><span class="field-label">Alerte :</span><ul>{alerts}</ul></div>'
    )
    if request:
        content += f'<div class="footer">Demande du pharmacien : « {html.escape(request)} »</div>'
    return f'<div class="rule custom">{content}</div>'
