"""Check on a record: alerts of all the KBS rules for a chosen patient."""

import streamlit as st

from kbs import check_rules
from src.front.components.widgets import show_alert


def render(state):
    if not state.patients:
        st.caption("No patient record loaded.")
        return
    choice = st.selectbox("Patient", [r["patient"]["id"] for r in state.patients], key="rules_test")
    record = next(r for r in state.patients if r["patient"]["id"] == choice)
    try:
        alerts = check_rules(record)
    except Exception as error:
        alerts = None
        st.error(f"Error in the rules: {error}")
    if alerts:
        for alert in alerts:
            show_alert(alert)
    elif alerts is not None:
        st.success("No alert for this record.")
