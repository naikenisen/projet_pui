"""“Laboratory reference ranges” tab: parameters present in the records and editable reference ranges."""

import pandas as pd
import streamlit as st

from src.front.components.widgets import show_errors
from src.front.services.data import load_lab_ranges, save_lab_ranges


def render_biology_tab(state):
    st.caption(
        "Reference ranges used to flag abnormal laboratory values for the LLM and the guideline search. "
        "The key must exactly match the parameter name in the patients' laboratory values."
    )
    _parameters_present(state)
    _ranges_editor()


def _parameters_present(state):
    """Laboratory parameters of the loaded records, with their unit and the number of patients."""
    parameters = {}
    for record in state.patients:
        for key, measure in record["patient"].get("biology", {}).items():
            parameters.setdefault(key, {"Key": key, "Unit": measure.get("unit") or "", "Number of patients": 0})
            parameters[key]["Number of patients"] += 1
    if parameters:
        with st.expander(f"Parameters present in the folder “{state.folder}” ({len(parameters)})"):
            st.dataframe(
                pd.DataFrame(parameters.values()).sort_values("Number of patients", ascending=False),
                hide_index=True, use_container_width=True,
            )


def _ranges_editor():
    ranges_table = pd.DataFrame(
        [{"key": key, **reference} for key, reference in load_lab_ranges().items()],
        columns=["key", "label", "unit", "min", "max"],
    )
    edited = st.data_editor(
        ranges_table,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        column_config={
            "key": st.column_config.TextColumn("Key", required=True),
            "label": st.column_config.TextColumn("Label"),
            "unit": st.column_config.TextColumn("Unit"),
            "min": st.column_config.NumberColumn("Lower bound", required=True),
            "max": st.column_config.NumberColumn("Upper bound", required=True),
        },
        key="ranges_editor",
    )
    if st.button("Save the reference ranges", type="primary"):
        edited = edited.dropna(how="all")
        rows = edited.astype(object).where(edited.notna(), None).to_dict("records")
        if show_errors(save_lab_ranges(rows)):
            st.success("Reference ranges saved.")
