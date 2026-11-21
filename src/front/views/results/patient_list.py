"""Patient list: status filters, search, and one clickable row per patient."""

import html

import streamlit as st
import streamlit.components.v1 as components

from src.front.rendering.opinion import status
from src.front.state import open_patient
from src.front.theme import read_asset

# Filter code: (label, status codes shown; None = all)
FILTERS = {
    "all": ("All", None),
    "intervention": ("Interventions", {"intervention"}),
    "verification": ("Verifications", {"verification"}),
    "monitoring": ("Monitoring", {"monitoring"}),
    "validated": ("Validated", {"validated"}),
    "others": ("Not analysed / errors", {"not_analysed", "error"}),
}

# The height of the header (titles and filters on one or two lines) depends on the screen width: this script
# (in an invisible frame) gives the list all the remaining height, so that the page itself does not scroll.
# Without it, the height is the one from the CSS (.st-key-patient-list).
LIST_HEIGHT_SCRIPT = read_asset("list_height.html")


def filtered_patients(state):
    """Records matching the selected filter and the search (identifier or drug), records needing action first."""
    selected_filter = st.session_state.get("filter", "all")
    search = st.session_state.get("search", "").strip().lower()
    return [
        r for r in state.sorted_patients
        if (FILTERS[selected_filter][1] is None or state.statuses[r["patient"]["id"]] in FILTERS[selected_filter][1])
        and (
            not search
            or search in r["patient"]["id"].lower()
            or any(search in str(t.get("drug_label", "")).lower() for t in r["treatments"])
        )
    ]


def render_filters(state):
    def filter_label(code):
        name, codes = FILTERS[code]
        return name if codes is None else f"{name} ({sum(state.counts[c] for c in codes)})"

    filter_column, search_column = st.columns([3, 1], vertical_alignment="bottom")
    filter_column.radio("Filter", list(FILTERS), format_func=filter_label, horizontal=True,
                        label_visibility="collapsed", key="filter")
    search_column.text_input("Search", placeholder="Identifier or drug",
                             label_visibility="collapsed", key="search")


def render_list(state, shown):
    """Patient list, one clickable row per patient, in a scrolling area (CSS .st-key-patient-list)."""
    if not shown:
        st.caption("No record matches the selection.")
        return

    with st.container(key="patient-list", gap=None):
        st.markdown(
            '<div class="patient-row header-row"><span>Patient</span><span>Status</span><span>Age</span>'
            '<span>Treatment lines</span><span>Alerts</span><span>Analysed on</span></div>',
            unsafe_allow_html=True,
        )
        for record in shown:
            _patient_row(state, record)

    st.caption(f"{len(shown)} record{'s' if len(shown) > 1 else ''} shown")
    with st.container(key="adjust-list"):
        components.html(LIST_HEIGHT_SCRIPT, height=0)


def _patient_row(state, record):
    patient = record["patient"]
    patient_id = patient["id"]
    result = state.results.get(patient_id) or {}
    code, state_label = status(state.results.get(patient_id))
    cells = [
        f"<b>{html.escape(patient_id)}</b>",
        f'<span class="status {code}">{html.escape(state_label)}</span>',
        f"{patient['age']} years" if patient.get("age") is not None else "—",
        str(len(record["treatments"])),
        str(len(result.get("alerts", []))) if result.get("alerts") else "—",
        html.escape(result.get("date", "")) or "—",
    ]
    # HTML row (aligned columns) covered by an invisible button that opens the record
    with st.container(key=f"row-{patient_id}", gap=None):
        st.markdown('<div class="patient-row">' + "".join(f"<span>{c}</span>" for c in cells) + "</div>",
                    unsafe_allow_html=True)
        st.button(f"Open record {patient_id}", key=f"open-{patient_id}", on_click=open_patient,
                  args=(patient_id,), use_container_width=True)
