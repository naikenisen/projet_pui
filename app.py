"""Streamlit interface: patient analysis, RAG documents and personalized KBS rules.

Run from the project root:  streamlit run app.py

This file only assembles the screen; the code of the interface is in src/front/ (see src/front/__init__.py).
Streamlit re-runs this script from the top after each interaction.
"""

import os

# The default inference folder (dataset) is relative to the project root.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

from src.front import theme
from src.front.state import build_state
from src.front.views.overview import render_overview
from src.front.views.results.tab import render_results_tab
from src.front.views.rules import render_rules_tab
from src.front.views.sidebar import render_sidebar

theme.configure_page()
theme.inject_style()

folder, patients, indexed = render_sidebar()
state = build_state(folder, patients, indexed)

theme.render_app_bar(state)
render_overview(state)

results_tab, rules_tab = st.tabs(["Résultats d'analyse", "Règles du KBS"])
with results_tab:
    render_results_tab(state)
with rules_tab:
    render_rules_tab(state)
