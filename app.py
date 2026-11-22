# Point d'entrée de l'interface Streamlit : streamlit run app.py

import os

# Le dossier patients est relatif à la racine du projet
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

from ui import common, page_analysis_results, page_kbs_rules, page_rag_documents

common.configure_page()
common.inject_style()
common.render_app_bar()

# Conserve le filtre et la recherche de la liste patients lors d'un changement de page
for key in ("filter", "search"):
    if key in st.session_state:
        st.session_state[key] = st.session_state[key]

page = st.navigation(
    [
        st.Page(page_analysis_results.render_page, title="Résultats d'analyse", default=True),
        st.Page(page_kbs_rules.render_page, title="Règles du KBS", url_path="regles"),
        st.Page(page_rag_documents.render_page, title="Documents du RAG", url_path="documents"),
    ],
    position="top",
)
page.run()
