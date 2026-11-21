"""“KBS rules” tab: personalized rules drafted by the LLM assistant, review before saving, list with deletion.

The generic rules (src/kbs/generic_rules.json) are not shown: they are applied during the analysis only.
Personalized rules are edited by hand in src/kbs/personalized_rules.json, outside the interface.
"""

import streamlit as st

from kbs import (
    add_personalized_rule,
    apply_rules,
    load_personalized_rules,
    propose_rule,
    save_personalized_rules,
    unknown_variables,
)
from src.front.components.widgets import label, show_errors
from src.front.rendering.rules import personalized_rule_card


def render_rules_tab(state):
    st.caption(
        "Une règle personnalisée du Knowledge-Based System (KBS) se déclenche lorsque l'ensemble de ses critères "
        "est vérifié. Elle est rédigée par l'assistant à partir d'une demande en langage naturel, puis vérifiée "
        "avant enregistrement. Les règles génériques (Thésaurus ANSM, DDI-Predictor) sont aussi appliquées lors "
        "de l'analyse."
    )
    biology_parameters = state.biology_parameters()
    _assistant(biology_parameters)
    _proposed_rule(state, biology_parameters)
    _rule_list(load_personalized_rules(), biology_parameters)


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


def _proposed_rule(state, biology_parameters):
    """Card, warnings and number of records that would trigger it, then Save / Cancel."""
    proposed = st.session_state.get("proposed_rule")
    if not proposed:
        return
    label("Règle proposée : à vérifier avant enregistrement")
    st.markdown(personalized_rule_card(proposed, biology_parameters), unsafe_allow_html=True)
    for name in unknown_variables(proposed, biology_parameters):
        st.warning(f"La donnée « {name} » n'existe pas dans les dossiers : cette condition sera toujours fausse.")
    triggers = sum(1 for r in state.patients if apply_rules(r, [proposed]))
    st.caption(f"Se déclencherait pour {triggers} dossier(s) sur {len(state.patients)} du dossier « {state.folder} ».")
    with st.expander("JSON de la règle"):
        st.json(proposed)
    save_column, cancel_column, _ = st.columns([1, 1, 3])
    if save_column.button("Enregistrer la règle", type="primary", use_container_width=True):
        if show_errors(add_personalized_rule(proposed)):
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
        text_column.markdown(personalized_rule_card(rule, biology_parameters), unsafe_allow_html=True)
        if delete_column.button("Supprimer", key=f"delete-rule-{number}", use_container_width=True):
            save_personalized_rules(rules[:number] + rules[number + 1:])
            st.rerun()
