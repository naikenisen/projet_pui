"""Streamlit interface: patient analysis, personalized KBS rules and RAG documents.

Run from the project root:  streamlit run app.py

This file holds what is common to every page (configuration, style, application bar) and declares the pages;
the code of each page is in ui/ (see ui/__init__.py).
Streamlit re-runs this script, then the selected page, from the top after each interaction.
"""

import os

# The patient folder (dataset) is relative to the project root.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

from ui import KBS_rules, RAG_documents, analysis_results, common

common.configure_page()
common.inject_style()
common.render_app_bar()

# A widget loses its value when its page is not shown: keep the filter and the search of the patient list
for key in ("filter", "search"):
    if key in st.session_state:
        st.session_state[key] = st.session_state[key]

page = st.navigation(
    [
        st.Page(analysis_results.render_page, title="Résultats d'analyse", default=True),  # served at the root URL
        st.Page(KBS_rules.render_page, title="Règles du KBS", url_path="regles"),
        st.Page(RAG_documents.render_page, title="Documents du RAG", url_path="documents"),
    ],
    position="top",
)
page.run()
