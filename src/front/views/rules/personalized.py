"""Personalized rules: drafting by the LLM assistant, list with deletion, manual entry and JSON editing."""

import json
import os

import streamlit as st

from kbs import (
    PERSONALIZED_RULES_FILE,
    add_personalized_rule,
    apply_rules,
    propose_rule,
    save_personalized_rules,
    unknown_variables,
)
from src.front.components.widgets import label, show_errors
from src.front.rendering.rules import personalized_rule_card


def render(state, rules):
    biology_parameters = state.biology_parameters()
    _assistant(biology_parameters)
    _proposed_rule(state, biology_parameters)
    _rule_list(rules, biology_parameters)
    _manual_entry()
    _json_editor(rules)


# ---------------------------------------------------------------------------
# Rule drafted by the LLM: request, then review before saving
# ---------------------------------------------------------------------------

def _assistant(biology_parameters):
    """Natural-language request; the rule proposed by the LLM is kept in st.session_state["proposed_rule"]."""
    label("Add a rule with the assistant")
    with st.form("rule_request", border=False):
        request = st.text_area(
            "Request", label_visibility="collapsed", height=90,
            placeholder="E.g.: Alert if metformin is prescribed with an eGFR below 30 mL/min: "
                        "contraindication, stop metformin.",
        )
        propose = st.form_submit_button("Propose a rule", type="primary")
    if propose and request.strip():
        with st.spinner("The model is drafting the rule..."):
            try:
                st.session_state["proposed_rule"] = propose_rule(request.strip(), biology_parameters)
            except Exception as error:
                st.session_state.pop("proposed_rule", None)
                st.error(f"The model could not draft a rule: {error}")


def _proposed_rule(state, biology_parameters):
    """Card, warnings and number of records that would trigger it, then Save / Cancel."""
    proposed = st.session_state.get("proposed_rule")
    if not proposed:
        return
    label("Proposed rule: check before saving")
    st.markdown(personalized_rule_card(proposed, biology_parameters), unsafe_allow_html=True)
    for name in unknown_variables(proposed, biology_parameters):
        st.warning(f"The variable “{name}” does not exist in the records: this condition will always be false.")
    triggers = sum(1 for r in state.patients if apply_rules(r, [proposed]))
    st.caption(f"Would be triggered for {triggers} record(s) out of {len(state.patients)} in the folder “{state.folder}”.")
    with st.expander("Rule JSON"):
        st.json(proposed)
    save_column, cancel_column, _ = st.columns([1, 1, 3])
    if save_column.button("Save the rule", type="primary", use_container_width=True):
        if show_errors(add_personalized_rule(proposed)):
            del st.session_state["proposed_rule"]
            st.toast("Personalized rule saved.")
            st.rerun()
    if cancel_column.button("Cancel", use_container_width=True):
        del st.session_state["proposed_rule"]
        st.rerun()


# ---------------------------------------------------------------------------
# Saved rules
# ---------------------------------------------------------------------------

def _rule_list(rules, biology_parameters):
    label(f"Personalized rules ({len(rules)})")
    if not rules:
        st.caption("No personalized rule.")
    for number, rule in enumerate(rules):
        text_column, delete_column = st.columns([7, 1])
        text_column.markdown(personalized_rule_card(rule, biology_parameters), unsafe_allow_html=True)
        if delete_column.button("Delete", key=f"delete-rule-{number}", use_container_width=True):
            save_personalized_rules(rules[:number] + rules[number + 1:])
            st.rerun()


def _lines(text, commas=False):
    """One value per line (and per comma if commas=True: laboratory names may contain commas)."""
    if commas:
        text = text.replace(",", "\n")
    return [line.strip() for line in text.splitlines() if line.strip()]


def _manual_entry():
    with st.expander("Manual rule entry"):
        st.caption(
            "A condition is written `variable operator value` (operators `>=` `<=` `>` `<` `==` `!=`). Available "
            "variables: patient characteristics (`age`, `weight_kg`, `height_cm`, `bmi_kg_m2`, "
            "`body_surface_area_m2`), laboratory values with the exact parameter name (`Créatinine (sang)`, "
            "`DFG estimé (CKD-EPI)`...) and, for the drugs named in the rule, the product strength "
            "(`dose_apixaban`), the dose in mg per day (`daily_dose_daptomycine`) and in mg/kg per day "
            "(`dose_per_kg_daptomycine`). A drug is considered prescribed if its name appears in the label of a "
            "prescription line (ignoring case and accents)."
        )
        with st.form("add_rule", clear_on_submit=False, border=False):
            alert = st.text_area(
                "Alert message (required)",
                placeholder="E.g.: Metformin contraindicated in severe renal failure",
            )
            column_a, column_b = st.columns(2)
            drugs = column_a.text_area(
                "Drugs involved (INN, one per line)", placeholder="apixaban",
                help="The rule only applies if all these drugs are prescribed.",
            )
            conditions = column_b.text_area(
                "Required conditions (one per line)", placeholder="DFG estimé (CKD-EPI) < 30"
            )
            any_of = column_a.text_area("Optional criteria (one per line)", placeholder="age >= 80")
            minimum = column_b.number_input("Minimum number of optional criteria met", min_value=0, value=0)
            add = st.form_submit_button("Save the rule", type="primary")

        if add:
            new_rule = {"alert": alert.strip()}
            if _lines(drugs, commas=True):
                new_rule["drugs"] = _lines(drugs, commas=True)
            if _lines(conditions):
                new_rule["conditions"] = _lines(conditions)
            if _lines(any_of):
                new_rule["any_of"] = _lines(any_of)
                new_rule["minimum"] = int(minimum)
            if show_errors(add_personalized_rule(new_rule)):
                st.success("Rule saved.")
                st.rerun()


def _json_editor(rules):
    with st.expander(f"Advanced editing of {os.path.relpath(PERSONALIZED_RULES_FILE)}"):
        text = st.text_area(
            "JSON content", json.dumps(rules, ensure_ascii=False, indent=2), height=350,
            key="rules_json",
        )
        if st.button("Save changes"):
            try:
                errors = save_personalized_rules(json.loads(text))
            except json.JSONDecodeError as error:
                errors = [f"Invalid JSON: {error}"]
            if show_errors(errors):
                st.success("Rules saved.")
                st.rerun()
