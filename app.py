"""Streamlit interface: patient analysis, personalized KBS rules and RAG documents.

Run from the project root:  streamlit run app.py

This file holds what is common to every page (configuration, style, application bar) and declares the pages;
the code of each page is in src/front/pages/ (see src/front/__init__.py).
Streamlit re-runs this script, then the selected page, from the top after each interaction.
"""

import os

# The patient folder (dataset) is relative to the project root.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

from src.front import theme
from src.front.pages.documents import render_documents_page
from src.front.pages.results.page import render_results_page
from src.front.pages.rules import render_rules_page

theme.configure_page()
theme.inject_style()
theme.render_app_bar()

# A widget loses its value when its page is not shown: keep the filter and the search of the patient list
for key in ("filter", "search"):
    if key in st.session_state:
        st.session_state[key] = st.session_state[key]

page = st.navigation(
    [
        st.Page(render_results_page, title="Résultats d'analyse", default=True),  # served at the root URL
        st.Page(render_rules_page, title="Règles du KBS", url_path="regles"),
        st.Page(render_documents_page, title="Documents du RAG", url_path="documents"),
    ],
    position="top",
)
page.run()
