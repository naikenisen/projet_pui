# "Règles du KBS" page: personalized CLIPS rules drafted by the LLM, checked and listed.

import html
import re

import streamlit as st

from create_rule import (
    add_personalized_rule,
    biology_parameters,
    load_personalized_rules,
    propose_rule,
    rule_names,
    save_personalized_rules,
)
from kbs import apply_rules, create_environment
from ui.common import badge, label, load_patients

# Alert text: (message "...") in the CLIPS code
ALERT_MESSAGE = re.compile(r'\(message\s+"((?:[^"\\]|\\.)*)"')


def render_page():
    patients = load_patients()
    parameters = biology_parameters(patients)
    _assistant(parameters)
    _proposed_rule(patients)
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
                st.session_state["proposed_rule"] = propose_rule(request.strip(), biology_parameters, backend=st.session_state.backend)
            except Exception as error:
                st.session_state.pop("proposed_rule", None)
                st.error(f"Le modèle n'a pas pu rédiger de règle : {error}")


# Card, warnings and number of triggered records, then Save / Cancel
def _proposed_rule(patients):
    proposed = st.session_state.get("proposed_rule")
    if not proposed:
        return
    label("Règle proposée : à vérifier avant enregistrement")
    show_rule(proposed)
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


# Title: first comment of the rule, else name of the first defrule
def rule_title(rule):
    for line in rule.splitlines():
        if line.startswith(";"):
            return line.lstrip("; ")
    names = rule_names(rule)
    return names[0] if names else "Règle"


# HTML card of a rule: title and alerts
def rule_card(rule):
    alerts = "".join(f"<li>{html.escape(message)}</li>" for message in ALERT_MESSAGE.findall(rule))
    content = (
        f'<div class="header">{badge("Règle personnalisée", "custom")}'
        f'<span class="title">{html.escape(rule_title(rule))}</span></div>'
        f'<div class="block"><span class="field-label">Alerte :</span><ul>{alerts}</ul></div>'
    )
    return f'<div class="rule custom">{content}</div>'
