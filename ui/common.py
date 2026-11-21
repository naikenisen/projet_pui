"""What the three pages share: page frame (configuration, style, application bar), patient records, small helpers."""

import html
import os

import streamlit as st

from kbs import load_patient

HOSPITAL_NAME = "CHU Dijon Bourgogne"
SOFTWARE_NAME = "Logiciel d'analyse pharmaceutique assistée par IA"
STYLE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.css")
PATIENTS_FOLDER = "dataset"  # patient records of the interface (one JSON file per patient), relative to the root


# ---------------------------------------------------------------------------
# Page frame
# ---------------------------------------------------------------------------

def configure_page():
    """Must be the first Streamlit call of the script."""
    st.set_page_config(page_title=f"{HOSPITAL_NAME} - Analyse pharmaceutique", layout="wide")


def inject_style():
    """Style of the whole interface (ui/style.css). The light theme is in .streamlit/config.toml."""
    with open(STYLE_FILE, encoding="utf-8") as file:
        st.markdown(f"<style>\n{file.read()}</style>", unsafe_allow_html=True)


def render_app_bar():
    """Dark bar fixed at the top of every page: hospital and software name."""
    st.markdown(
        f"""
<div class="app-bar">
  <div class="brand">
    <span class="hospital">{html.escape(HOSPITAL_NAME)}</span>
    <span class="separator"></span>
    <span class="software">{html.escape(SOFTWARE_NAME)}</span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Patient records and small helpers
# ---------------------------------------------------------------------------

def load_patients(folder=PATIENTS_FOLDER):
    """Patient records of the folder (one JSON file per patient), sorted by file name."""
    if not os.path.isdir(folder):
        return []
    return [load_patient(folder, name[:-5]) for name in sorted(os.listdir(folder)) if name.endswith(".json")]


def label(text):
    """Uppercase label above a block of the page."""
    st.markdown(f'<div class="label">{html.escape(text)}</div>', unsafe_allow_html=True)


def badge(text, css_class):
    return f'<span class="badge {css_class}">{html.escape(text)}</span>'
