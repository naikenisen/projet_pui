"""Small reusable Streamlit widgets (titles, labels, HTML tables, alerts)."""

import html

import streamlit as st

from src.front.rendering.alerts import html_alert
from src.front.rendering.record import html_table


def section_title(text):
    """Uppercase title of a sidebar section."""
    st.markdown(f'<div class="section-title">{html.escape(text)}</div>', unsafe_allow_html=True)


def label(text):
    """Uppercase label above a block of the page."""
    st.markdown(f'<div class="label">{html.escape(text)}</div>', unsafe_allow_html=True)


def table(columns, rows, row_classes=(), short_columns=()):
    st.markdown(html_table(columns, rows, row_classes, short_columns), unsafe_allow_html=True)


def show_alert(alert):
    st.markdown(html_alert(alert), unsafe_allow_html=True)


def show_errors(errors):
    """Shows each error message; returns True if there was none."""
    for error in errors:
        st.error(error)
    return not errors
