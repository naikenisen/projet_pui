"""“KBS rules” tab: three sub-tabs (personalized rules, generic rules, check on a record)."""

import streamlit as st

from kbs import load_generic_rules, load_personalized_rules
from src.front.views.rules import check, generic, personalized


def render_rules_tab(state):
    personalized_rules = load_personalized_rules()
    generic_rules = load_generic_rules()
    st.caption(
        "A rule of the Knowledge-Based System (KBS) is triggered when all its criteria are met. **Generic rules** "
        "come from the ANSM Thesaurus of drug interactions and from DDI-Predictor; **personalized rules** are "
        "specific to the hospital and can be drafted by the assistant from a natural-language request."
    )
    personalized_tab, generic_tab, check_tab = st.tabs([
        f"Personalized rules ({len(personalized_rules)})",
        f"Generic rules ({len(generic_rules)})",
        "Check on a record",
    ])
    with personalized_tab:
        personalized.render(state, personalized_rules)
    with generic_tab:
        generic.render(generic_rules)
    with check_tab:
        check.render(state)
