"""Pharmaceutical opinion of a record: decision, then one frame per point with its sources."""

import html

import streamlit as st

from src.front.components.dialogs import alert_link, source_button, source_links
from src.front.rendering.opinion import DECISION_LABELS, category, read_source


def render_opinion(result, patient_id):
    """Decision and points of the pharmaceutical opinion."""
    if result is None:
        st.info("Dossier non analysé.")
        return
    if "error" in result:
        st.markdown(
            f'<div class="decision error">Échec de l’analyse ({result["date"]})</div>',
            unsafe_allow_html=True,
        )
        st.code(result["error"], language=None)
        return

    css_class = category(result["decision"])
    st.markdown(
        f'<div class="decision {css_class}">{html.escape(DECISION_LABELS[css_class])}</div>', unsafe_allow_html=True
    )
    if "points" in result:
        for number, point in enumerate(result["points"]):
            _point(point, key=f"point-{patient_id}-{number}")
    else:  # analysis made before points were introduced: justification in one paragraph
        _legacy_opinion(result, patient_id)
    st.markdown(f'<div class="muted">Analysé le {result["date"]}</div>', unsafe_allow_html=True)


def _point(point, key):
    """One proposal of the pharmaceutical opinion in a frame, with its sources at the bottom of the same frame.

    Intervention: bold text, orange frame. KBS alerts are only visible through these links (no separate list).
    The frames are st.container(key="frame-<type>-..."), styled by the CSS classes st-key-frame-<type>.
    """
    type_ = point["type"]
    with st.container(key=f"frame-{type_}-{key}"):
        st.markdown(f'<p class="point {type_}">{html.escape(point["text"])}</p>', unsafe_allow_html=True)
        with st.container(horizontal=True, gap="small", vertical_alignment="center"):
            st.markdown('<span class="sources-title">Sources</span>', unsafe_allow_html=True)
            if not point["sources"]:
                st.markdown('<span class="llm-source">connaissances du modèle uniquement : aucune alerte ni référentiel</span>',
                            unsafe_allow_html=True)
            source_links(point["sources"], key)


def _legacy_opinion(result, patient_id):
    st.write(result["justification"])
    for number, source in enumerate(result.get("sources", [])):
        if read_source(source):
            source_button(source, key=f"source-{patient_id}-{number}")
    with st.container(horizontal=True, gap="small"):
        for number, alert in enumerate(result.get("alerts", [])):
            alert_link(alert, key=f"alert-{patient_id}-{number}")
