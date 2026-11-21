"""Page configuration, style sheet and fixed application bar."""

import html
import os

import streamlit as st

HOSPITAL_NAME = "CHU Dijon Bourgogne"
SOFTWARE_NAME = "Logiciel d'analyse pharmaceutique assistée par IA"

ASSETS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def read_asset(name):
    with open(os.path.join(ASSETS_FOLDER, name), encoding="utf-8") as file:
        return file.read()


def configure_page():
    """Must be the first Streamlit call of the script."""
    st.set_page_config(page_title=f"{HOSPITAL_NAME} - Analyse pharmaceutique", layout="wide")


def inject_style():
    """Style of the whole interface (assets/style.css). The light theme is in .streamlit/config.toml."""
    st.markdown(f"<style>\n{read_asset('style.css')}</style>", unsafe_allow_html=True)


def render_app_bar(state):
    """Dark bar fixed at the top of the page: hospital, software, number of records and indexed guidelines."""
    st.markdown(
        f"""
<div class="app-bar">
  <div class="brand">
    <span class="hospital">{html.escape(HOSPITAL_NAME)}</span>
    <span class="separator"></span>
    <span class="software">{html.escape(SOFTWARE_NAME)}</span>
  </div>
  <div class="context">
    <span><b>{len(state.patients)}</b> dossiers</span>
    <span><b>{len(state.indexed)}</b> référentiels indexés</span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
