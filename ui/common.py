# Elements shared by the pages: page frame, patient records, small helpers.

import html
import os

import streamlit as st

from kbs import load_patient

HOSPITAL_NAME = "CHU Dijon Bourgogne"
SOFTWARE_NAME = "Logiciel d'analyse pharmaceutique assistée par IA"
STYLE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.css")
# One JSON file per patient, relative to the project root
PATIENTS_FOLDER = "dataset"


# Must be the first Streamlit call of the script
def configure_page():
    st.set_page_config(page_title=f"{HOSPITAL_NAME} - Analyse pharmaceutique", layout="wide")


def inject_style():
    with open(STYLE_FILE, encoding="utf-8") as file:
        st.markdown(f"<style>\n{file.read()}</style>", unsafe_allow_html=True)


def render_app_bar():
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


def load_patients(folder=PATIENTS_FOLDER):
    if not os.path.isdir(folder):
        return []
    return [load_patient(folder, name[:-5]) for name in sorted(os.listdir(folder)) if name.endswith(".json")]


# Uppercase label above a block
def label(text):
    st.markdown(f'<div class="label">{html.escape(text)}</div>', unsafe_allow_html=True)


def badge(text, css_class):
    return f'<span class="badge {css_class}">{html.escape(text)}</span>'
