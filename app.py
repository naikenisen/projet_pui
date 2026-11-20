"""Interface Streamlit : analyse des patients, base documentaire, règles du système expert et biologie.

Lancement depuis la racine du projet :  streamlit run app.py
Le thème clair est défini dans .streamlit/config.toml.
"""

import html
import json
import math
import os

# Les scripts du projet utilisent des chemins relatifs (input.json, chroma_db...) : on se place à la racine.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from expert_system import (
    ajouter_regle_personnalisee,
    appliquer_regles,
    charger_regles_generiques,
    charger_regles_personnalisees,
    normaliser,
    proposer_regle,
    sauver_regles_personnalisees,
    variables_inconnues,
    verifier_regles,
)
from src.affichage import (
    COULEURS_STATUTS,
    LIBELLES_STATUT,
    NIVEAUX,
    ORDRE_STATUTS,
    carte_regle_generique,
    carte_regle_personnalisee,
    categorie,
    codes_niveau,
    html_alerte,
    html_tableau,
    lignes_a_modifier,
    lire_source,
    profil_patient,
    statut,
    tableau_biologie,
    tableau_prescription,
    type_deduit,
)
from src.analyse import analyser
from src.documents import (
    chemin_document,
    documents_du_dossier,
    documents_indexes,
    enregistrer_pdf,
    indexer_pdf,
    nombre_pages,
    rendre_page,
)
from src.donnees import (
    DOSSIER_PATIENTS,
    charger_bio,
    charger_patients,
    charger_resultats,
    sauver_bio,
    sauver_resultats,
)

NOM_ETABLISSEMENT = "CHU Dijon Bourgogne"
NOM_LOGICIEL = "Logiciel d'analyse pharmaceutique assistée par IA"

st.set_page_config(page_title=f"{NOM_ETABLISSEMENT} - Analyse pharmaceutique", layout="wide")


# ---------------------------------------------------------------------------
# Style : barre d'application fixe, interface dense de type logiciel métier
# ---------------------------------------------------------------------------

HAUTEUR_BARRE = 52  # px

st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {{
    --bleu: #0B4F8A; --bleu-fonce: #08355C; --bleu-clair: #E8F0F8;
    --texte: #1A2433; --texte-2: #4A5A6E; --texte-3: #7A8899;
    --bordure: #D9E0E8; --fond: #F3F5F8; --surface: #FFFFFF;
    --vert: #1E7A46; --vert-fond: #E9F5EE; --orange: #A85A00; --orange-fond: #FFF3E3;
    --rouge: #B42318; --rouge-fond: #FDECEB;
    --violet: #6B3FA0; --violet-fond: #F2ECFA; --bleu-fond: #E8F0F8;
}}
html, body, [class*="css"], .stMarkdown, button, input, textarea, select {{
    font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif;
}}
html {{ font-size: 15.5px; }}
#MainMenu, footer, [data-testid="stDecoration"], [data-testid="stStatusWidget"] {{ display: none; }}

/* Barre d'application fixe en haut */
.barre-app {{
    position: fixed; top: 0; left: 0; right: 0; height: {HAUTEUR_BARRE}px; z-index: 1000001;
    background: var(--bleu-fonce); color: #FFFFFF; display: flex; align-items: center;
    justify-content: space-between; padding: 0 1.25rem; font-size: 0.98rem;
    border-bottom: 1px solid #052440;
}}
.barre-app .marque {{ display: flex; align-items: center; gap: 0.75rem; }}
.barre-app .etablissement {{ font-weight: 700; letter-spacing: 0.02em; }}
.barre-app .separateur {{ width: 1px; height: 22px; background: rgba(255,255,255,0.35); }}
.barre-app .logiciel {{ color: rgba(255,255,255,0.85); font-weight: 400; }}
.barre-app .contexte {{ font-size: 0.85rem; color: rgba(255,255,255,0.75); display: flex; gap: 1.25rem; }}
.barre-app .contexte b {{ color: #FFFFFF; font-weight: 600; }}
[data-testid="stHeader"] {{ top: {HAUTEUR_BARRE}px; background: transparent; height: 2.5rem; }}
[data-testid="stSidebar"] {{ top: {HAUTEUR_BARRE}px; height: calc(100vh - {HAUTEUR_BARRE}px); }}
.block-container {{ padding-top: calc({HAUTEUR_BARRE}px + 1.5rem); padding-bottom: 2rem; max-width: 1500px; }}

/* Barre latérale */
[data-testid="stSidebar"] {{ background: var(--surface); border-right: 1px solid var(--bordure); }}
[data-testid="stSidebar"] .stButton > button {{ justify-content: flex-start; text-align: left; }}
.titre-section {{
    font-size: 0.75rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--texte-3); margin: 1rem 0 0.4rem 0; padding-bottom: 0.3rem; border-bottom: 1px solid var(--bordure);
}}

/* En-tête de page et bandeau d'indicateurs */
.titre-page {{ font-size: 1.15rem; font-weight: 600; color: var(--texte); margin: 0; }}
.sous-titre-page {{ font-size: 0.82rem; color: var(--texte-3); margin: 0.1rem 0 0 0; }}
.indicateurs {{
    display: flex; background: var(--surface); border: 1px solid var(--bordure); border-radius: 4px;
    margin: 0.9rem 0 0.6rem 0;
}}
.indicateur {{ flex: 1; padding: 0.6rem 1rem; border-right: 1px solid var(--bordure); }}
.indicateur:last-child {{ border-right: none; }}
.indicateur .valeur {{ font-size: 1.35rem; font-weight: 600; color: var(--texte); line-height: 1.2; }}
.indicateur .nom {{ font-size: 0.76rem; color: var(--texte-3); text-transform: uppercase; letter-spacing: 0.05em; }}
.indicateur.vert .valeur {{ color: var(--vert); }}
.indicateur.orange .valeur {{ color: var(--orange); }}
.indicateur.rouge .valeur {{ color: var(--rouge); }}
.indicateur.violet .valeur {{ color: var(--violet); }}
.indicateur.bleu .valeur {{ color: var(--bleu); }}
[data-testid="stMetric"] {{ padding: 0; }}
[data-testid="stMetricLabel"] p {{ color: var(--texte-3); font-size: 0.75rem; }}
[data-testid="stMetricValue"] {{ font-size: 1.4rem; font-weight: 600; }}

/* Composants : angles sobres, bordures fines */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {{
    border-radius: 4px; font-weight: 500; font-size: 0.85rem; min-height: 2.1rem; padding: 0.2rem 0.8rem;
}}
.stButton > button[kind="primary"], [data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"] {{
    background: var(--bleu); border-color: var(--bleu);
}}
.stTextInput input, .stNumberInput input, .stTextArea textarea, [data-baseweb="select"] > div {{ border-radius: 4px; }}
[data-testid="stExpander"] details {{
    background: var(--surface); border: 1px solid var(--bordure); border-radius: 4px;
}}
[data-testid="stExpander"] summary {{ padding: 0.55rem 0.9rem; font-size: 0.9rem; }}
[data-testid="stExpander"] summary:hover {{ background: var(--bleu-clair); }}
[data-testid="stExpander"] {{ margin-bottom: -0.6rem; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: 4px; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 0; border-bottom: 1px solid var(--bordure); }}
.stTabs [data-baseweb="tab"] {{ padding: 0.55rem 1.1rem; font-weight: 500; font-size: 0.88rem; }}
.stTabs [aria-selected="true"] {{ color: var(--bleu); }}
[data-testid="stDataFrame"] {{ border: 1px solid var(--bordure); border-radius: 4px; }}

/* Contenu des dossiers */
.decision {{
    border-radius: 3px; padding: 0.55rem 0.8rem; font-weight: 600; font-size: 0.88rem;
    border-left: 3px solid; margin-bottom: 0.6rem; letter-spacing: 0.01em;
}}
.decision.valide {{ background: var(--vert-fond); border-color: var(--vert); color: var(--vert); }}
.decision.intervention {{ background: var(--orange-fond); border-color: var(--orange); color: var(--orange); }}
.decision.verification {{ background: var(--violet-fond); border-color: var(--violet); color: var(--violet); }}
.decision.surveillance {{ background: var(--bleu-fond); border-color: var(--bleu); color: var(--bleu); }}
.decision.erreur {{ background: var(--rouge-fond); border-color: var(--rouge); color: var(--rouge); }}
.libelle {{
    font-size: 0.75rem; font-weight: 600; color: var(--texte-3); text-transform: uppercase;
    letter-spacing: 0.07em; margin: 0.8rem 0 0.3rem 0;
}}
.alerte {{
    background: var(--orange-fond); border-left: 3px solid var(--orange); border-radius: 3px;
    padding: 0.4rem 0.7rem; margin-bottom: 0.35rem; font-size: 0.86rem; color: var(--texte);
}}
.alerte .entete-alerte {{ display: flex; align-items: center; flex-wrap: wrap; gap: 0.35rem; margin-bottom: 0.2rem; }}
.alerte .complement {{ margin-top: 0.25rem; }}
.alerte .prescription {{ margin-top: 0.25rem; font-size: 0.78rem; color: var(--texte-2); }}

/* Règles du système expert */
.regle {{
    background: var(--surface); border: 1px solid var(--bordure); border-left: 4px solid var(--bleu);
    border-radius: 4px; padding: 0.65rem 0.9rem; margin-bottom: 0.5rem; font-size: 0.86rem; color: var(--texte);
}}
.regle.ci {{ border-left-color: var(--rouge); }}
.regle.asdec {{ border-left-color: var(--orange); }}
.regle.pe {{ border-left-color: #C9A100; }}
.regle.apec {{ border-left-color: #9AA6B2; }}
.regle.perso {{ border-left-color: var(--vert); }}
.regle .entete {{ display: flex; align-items: center; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.4rem; }}
.regle .titre {{ font-weight: 600; font-size: 0.93rem; margin-right: 0.2rem; }}
.regle .bloc {{ margin: 0.3rem 0; line-height: 1.45; }}
.regle .etiquette {{ font-weight: 600; color: var(--texte-2); }}
.regle ul {{ margin: 0.15rem 0 0 0; padding-left: 1.2rem; }}
.regle li {{ margin: 0.05rem 0; }}
.regle details {{ margin-top: 0.35rem; }}
.regle summary {{ cursor: pointer; color: var(--texte-3); font-size: 0.8rem; }}
.regle .pied {{ margin-top: 0.35rem; font-size: 0.75rem; color: var(--texte-3); }}
.badge {{
    font-size: 0.68rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em;
    padding: 0.1rem 0.45rem; border-radius: 3px; white-space: nowrap;
}}
.badge.ci {{ background: var(--rouge-fond); color: var(--rouge); }}
.badge.asdec {{ background: var(--orange-fond); color: var(--orange); }}
.badge.pe {{ background: #FFF7D6; color: #7A5B00; }}
.badge.apec {{ background: #EEF1F4; color: var(--texte-2); }}
.badge.pk {{ background: var(--bleu-clair); color: var(--bleu); }}
.badge.perso {{ background: var(--vert-fond); color: var(--vert); }}
.puce {{
    display: inline-block; background: var(--fond); border: 1px solid var(--bordure); border-radius: 3px;
    padding: 0 0.35rem; margin: 0.1rem 0.2rem 0.1rem 0; font-size: 0.8rem;
}}
.profil {{ color: var(--texte); font-weight: 500; }}
.discret {{ color: var(--texte-3); font-size: 0.76rem; margin-top: 0.6rem; }}

/* Avis pharmaceutique : chaque point est un cadre contenant la proposition puis ses sources.
   Les cadres sont des st.container(key="cadre-<type>-...") : Streamlit leur donne la classe st-key-<key>. */
[class*="st-key-cadre-"] {{
    border: 1px solid var(--bordure); border-left: 3px solid var(--bordure); border-radius: 4px;
    background: var(--surface); padding: 0.5rem 0.75rem; margin: 0.35rem 0; gap: 0.35rem;
}}
[class*="st-key-cadre-intervention"] {{ border: 1.5px solid var(--orange); background: var(--orange-fond); }}
[class*="st-key-cadre-verification"] {{ border-left-color: var(--violet); }}
[class*="st-key-cadre-surveillance"] {{ border-left-color: var(--bleu); }}
[class*="st-key-cadre-validation"] {{ border-left-color: var(--vert); }}
/* Streamlit donne une marge basse négative aux blocs markdown : sans correction, les sources remontent sur le texte */
[class*="st-key-cadre-"] [data-testid="stMarkdownContainer"] {{ margin-bottom: 0 !important; }}
[class*="st-key-cadre-"] [data-testid="stMarkdownContainer"] p {{ margin: 0 !important; }}
.point {{ font-size: 0.9rem; color: var(--texte); line-height: 1.45; }}
p.point.intervention, .point.intervention {{ font-weight: 700 !important; }}
/* Dossier ouvert : zones à hauteur calculée sur l'écran, chacune défile seule (la page ne défile pas).
   Hauteur disponible ≈ 100vh moins barre d'application, onglets, barre de navigation et libellés. */
div.st-key-zone-bio, div.st-key-zone-prescription, div.st-key-zone-avis {{
    overflow-y: auto !important; overflow-x: hidden !important; flex: none !important;
}}
div.st-key-zone-bio {{ height: calc(100vh - 390px) !important; min-height: 220px; }}
div.st-key-zone-prescription {{ height: calc((100vh - 360px) * 0.5) !important; min-height: 160px; }}
div.st-key-zone-avis {{ height: calc((100vh - 360px) * 0.5) !important; min-height: 180px; }}
.st-key-zone-avis > div {{ margin-bottom: 0.5rem; }}
.tableau th {{ position: sticky; top: 0; z-index: 1; }}

/* Liste des patients : colonnes alignées (grille), chaque ligne recouverte d'un bouton invisible.
   La liste défile seule dans une zone à hauteur d'écran (la page ne défile pas) ; l'en-tête de colonnes reste visible. */
div.st-key-liste-patients {{ border: 1px solid var(--bordure); border-radius: 4px; background: var(--surface);
    margin-top: 0.4rem; overflow-y: auto !important; overflow-x: hidden !important; flex: none !important;
    max-height: calc(100vh - 400px) !important; min-height: 200px; }}
.st-key-liste-patients > div:first-child {{ position: sticky; top: 0; z-index: 3; }}
.st-key-ajuster-liste {{ display: none; }}
.st-key-liste-patients [data-testid="stMarkdownContainer"] {{ margin-bottom: 0 !important; }}
.ligne-patient {{
    display: grid; grid-template-columns: 9rem 13rem 6rem 10rem 6rem 1fr; align-items: center;
    padding: 0.5rem 0.9rem; border-bottom: 1px solid var(--bordure); font-size: 0.87rem; color: var(--texte);
}}
.ligne-patient.entete {{ background: var(--fond); color: var(--texte-3); font-size: 0.74rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.05em; padding: 0.4rem 0.9rem; }}
.ligne-patient .statut {{ font-weight: 600; }}
.statut.intervention {{ color: var(--orange); }} .statut.verification {{ color: var(--violet); }}
.statut.surveillance {{ color: var(--bleu); }} .statut.valide {{ color: var(--vert); }}
.statut.erreur {{ color: var(--rouge); }} .statut.non_analyse {{ color: var(--texte-3); }}
[class*="st-key-ligne-"] {{ position: relative; }}
[class*="st-key-ligne-"]:hover {{ background: var(--bleu-clair); cursor: pointer; }}
[class*="st-key-ouvrir-"] {{ position: absolute; inset: 0; z-index: 2; }}
[class*="st-key-ouvrir-"] .stButton, [class*="st-key-ouvrir-"] button {{
    width: 100%; height: 100%; opacity: 0; cursor: pointer;
}}
.titre-sources {{ font-size: 0.74rem; font-weight: 600; color: var(--texte-3); text-transform: uppercase;
    letter-spacing: 0.05em; }}
/* Liens de sources : texte bleu pastel sur fond bleu très clair */
.stButton > button[kind="tertiary"] {{
    min-height: 1.4rem; padding: 0.05rem 0.5rem; background: #F0F6FD; border: 1px solid #C6DDF5; border-radius: 10px;
}}
.stButton > button[kind="tertiary"], .stButton > button[kind="tertiary"] p {{
    color: #5B9BD5; font-size: 0.78rem; font-weight: 500;
}}
.stButton > button[kind="tertiary"]:hover {{ background: #E2EEFB; border-color: #9EC3EA; }}
.stButton > button[kind="tertiary"]:hover p {{ color: #3E7FC1; }}
.source-llm {{
    display: inline-block; font-size: 0.78rem; color: var(--texte-2); background: #EEF1F4;
    border: 1px solid var(--bordure); border-radius: 10px; padding: 0.05rem 0.5rem;
}}

/* Tableaux de la biologie et de la prescription : tout le texte visible, sans défilement horizontal */
.tableau {{ width: 100%; border-collapse: collapse; font-size: 0.8rem; background: var(--surface);
    border: 1px solid var(--bordure); table-layout: auto; }}
.tableau th {{ text-align: left; font-weight: 600; color: var(--texte-2); background: var(--fond);
    padding: 0.3rem 0.45rem; border-bottom: 1px solid var(--bordure); }}
.tableau td {{ padding: 0.28rem 0.45rem; border-bottom: 1px solid var(--bordure); vertical-align: top;
    white-space: normal; overflow-wrap: anywhere; }}
.tableau td.court {{ white-space: nowrap; }}
.tableau tr.anormal td {{ color: var(--rouge); background: var(--rouge-fond); font-weight: 500; }}
</style>
""",
    unsafe_allow_html=True,
)


def titre_section(texte):
    st.markdown(f'<div class="titre-section">{html.escape(texte)}</div>', unsafe_allow_html=True)


def libelle(texte):
    st.markdown(f'<div class="libelle">{html.escape(texte)}</div>', unsafe_allow_html=True)


def afficher_alerte(alerte):
    st.markdown(html_alerte(alerte), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Visionneuse de documents
# ---------------------------------------------------------------------------

@st.dialog("Consultation du document", width="large")
def ouvrir_document(nom, page=1):
    chemin = chemin_document(nom)
    if not os.path.exists(chemin):
        st.error(f"Le document « {nom} » est introuvable dans la base documentaire.")
        return

    total = nombre_pages(chemin)
    st.markdown(f"**{nom}**")
    colonne_page, colonne_telechargement = st.columns([1, 1], vertical_alignment="bottom")
    page = colonne_page.number_input(
        f"Page (sur {total})", min_value=1, max_value=total, value=min(page, total), key=f"page-{nom}-{page}"
    )
    with open(chemin, "rb") as fichier:
        colonne_telechargement.download_button(
            "Télécharger le PDF", fichier.read(), file_name=nom, mime="application/pdf",
            use_container_width=True,
        )
    st.image(rendre_page(chemin, page))


def bouton_source(source, cle):
    """Affiche un bouton qui ouvre la source si c'est un PDF de la base, sinon un simple texte."""
    document = lire_source(source)
    if document is None:
        st.markdown(f"- {source}")
        return
    nom, page = document
    if st.button(source, key=cle, help=f"Ouvrir {nom} à la page {page}"):
        ouvrir_document(nom, page)


@st.dialog("Alerte du système expert", width="large")
def ouvrir_alerte(alerte):
    afficher_alerte(alerte)


def lien_alerte(alerte, cle):
    """Lien « Alerte experte » : le survol affiche l'alerte, le clic l'ouvre en détail."""
    if st.button("Alerte experte", key=cle, type="tertiary", help=alerte):
        ouvrir_alerte(alerte)


def afficher_point(point, cle, categorie_decision=""):
    """Une proposition de l'avis pharmaceutique dans un cadre, avec ses sources en bas du même cadre.

    Intervention : texte en gras, cadre orange. Les alertes du système expert ne sont visibles qu'à travers
    ces liens (pas de liste séparée).
    """
    type_ = point.get("type") or type_deduit(point["texte"], categorie_decision)
    with st.container(key=f"cadre-{type_}-{cle}"):
        st.markdown(f'<p class="point {type_}">{html.escape(point["texte"])}</p>', unsafe_allow_html=True)
        with st.container(horizontal=True, gap="small", vertical_alignment="center"):
            st.markdown('<span class="titre-sources">Sources</span>', unsafe_allow_html=True)
            if not point["sources"]:
                st.markdown('<span class="source-llm">connaissances du modèle uniquement : ni alerte ni '
                            'recommandation</span>', unsafe_allow_html=True)
            afficher_liens_sources(point["sources"], cle)


def afficher_liens_sources(sources, cle):
    for numero, source in enumerate(sources):
        if source["type"] == "alerte":
            lien_alerte(source["texte"], cle=f"{cle}-{numero}")
        elif st.button(f"{source['source']}, p. {source['page']}", key=f"{cle}-{numero}", type="tertiary",
                       help=f"Ouvrir {source['source']} à la page {source['page']}"):
            ouvrir_document(source["source"], source["page"])


# ---------------------------------------------------------------------------
# Barre latérale : base patients et base documentaire
# ---------------------------------------------------------------------------

with st.sidebar:
    titre_section("Base patients")
    repertoire = st.text_input(
        "Dossier d'inférence", value=DOSSIER_PATIENTS, key="repertoire_patients",
        help="Dossier contenant un fichier JSON par patient (chemin relatif à la racine du projet ou absolu).",
    ).strip()
    if os.path.isdir(repertoire):
        try:
            patients = charger_patients(repertoire)
        except Exception as erreur:
            patients = []
            st.error(f"Lecture des dossiers patients impossible : {erreur}")
    else:
        patients = []
        st.error(f"Le dossier « {repertoire} » n'existe pas.")
    st.metric("Dossiers patients", len(patients))

    titre_section("Base documentaire")
    try:
        indexes = documents_indexes()
    except Exception as erreur:
        indexes = {}
        st.error(f"Lecture de la base vectorielle impossible : {erreur}")

    if indexes:
        st.caption("Référentiels indexés. Cliquer pour consulter.")
        for nom, nb_passages in indexes.items():
            if st.button(f"{nom}  ·  {nb_passages} passages", key=f"doc-{nom}", use_container_width=True):
                ouvrir_document(nom)
    else:
        st.info("Aucun référentiel indexé.")

    non_indexes = [nom for nom in documents_du_dossier() if nom not in indexes]
    if non_indexes:
        st.caption("Documents en attente d'indexation")
        for nom in non_indexes:
            colonne_nom, colonne_bouton = st.columns([3, 2], vertical_alignment="center")
            colonne_nom.markdown(f"`{nom}`")
            if colonne_bouton.button("Indexer", key=f"indexer-{nom}", use_container_width=True):
                with st.spinner(f"Indexation de {nom} en cours..."):
                    nb = indexer_pdf(chemin_document(nom))
                st.toast(f"{nom} : {nb} passages indexés")
                st.rerun()

    titre_section("Ajouter un référentiel")
    with st.form("ajout_document", clear_on_submit=True, border=False):
        fichiers = st.file_uploader(
            "Documents PDF", type="pdf", accept_multiple_files=True, label_visibility="collapsed",
            help="Le document est enregistré dans la base documentaire puis indexé.",
        )
        envoye = st.form_submit_button("Indexer les documents", use_container_width=True)
    if envoye and fichiers:
        for fichier in fichiers:
            with st.spinner(f"Indexation de {fichier.name} en cours..."):
                try:
                    nb = indexer_pdf(enregistrer_pdf(fichier.name, fichier.getvalue()))
                    st.toast(f"{fichier.name} : {nb} passages indexés")
                except Exception as erreur:
                    st.error(f"{fichier.name} : {erreur}")
        st.rerun()


# ---------------------------------------------------------------------------
# Panneau principal
# ---------------------------------------------------------------------------

resultats = charger_resultats()
statuts = {d["patient"]["id"]: statut(resultats.get(d["patient"]["id"]))[0] for d in patients}
compte = {code: list(statuts.values()).count(code) for code in LIBELLES_STATUT}
# Dossiers à analyser par « Lancer l'analyse » : jamais analysés ou en échec
a_analyser = [d for d in patients if statuts[d["patient"]["id"]] in ("non_analyse", "erreur")]

st.markdown(
    f"""
<div class="barre-app">
  <div class="marque">
    <span class="etablissement">{html.escape(NOM_ETABLISSEMENT)}</span>
    <span class="separateur"></span>
    <span class="logiciel">{html.escape(NOM_LOGICIEL)}</span>
  </div>
  <div class="contexte">
    <span>Dossier <b>{html.escape(repertoire)}</b></span>
    <span><b>{len(patients)}</b> dossiers</span>
    <span><b>{len(indexes)}</b> référentiels indexés</span>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# Dossier ouvert : en-tête et indicateurs masqués pour que le dossier tienne dans l'écran sans défilement
vue_dossier = bool(st.session_state.get("patient_ouvert"))
lancer = relancer = False
if not vue_dossier:
    colonne_titre, colonne_action, colonne_relance = st.columns([2, 1, 1], vertical_alignment="center")
    colonne_titre.markdown(
        '<p class="titre-page">Analyse des prescriptions</p>'
        '<p class="sous-titre-page">Système expert, recommandations de référence et modèle de langage</p>',
        unsafe_allow_html=True,
    )
    lancer = colonne_action.button(
        f"Lancer l'analyse ({len(a_analyser)} dossiers)",
        type="primary",
        disabled=not a_analyser,
        use_container_width=True,
        help="Analyse uniquement les dossiers non analysés ou en erreur",
    )
    relancer = colonne_relance.button(
        "Relancer l'analyse de tous les patients",
        disabled=not patients,
        use_container_width=True,
        help="Analyse à nouveau tous les dossiers, y compris ceux déjà analysés",
    )
    
    st.markdown(
        f"""
    <div class="indicateurs">
      <div class="indicateur"><div class="valeur">{len(patients)}</div><div class="nom">Dossiers</div></div>
      <div class="indicateur"><div class="valeur">{len(patients) - compte["non_analyse"]}</div><div class="nom">Analysés</div></div>
      <div class="indicateur orange"><div class="valeur">{compte["intervention"]}</div><div class="nom">Interventions</div></div>
      <div class="indicateur violet"><div class="valeur">{compte["verification"]}</div><div class="nom">Vérifications</div></div>
      <div class="indicateur bleu"><div class="valeur">{compte["surveillance"]}</div><div class="nom">Surveillances</div></div>
      <div class="indicateur vert"><div class="valeur">{compte["valide"]}</div><div class="nom">Validés</div></div>
      <div class="indicateur rouge"><div class="valeur">{compte["erreur"]}</div><div class="nom">Erreurs</div></div>
      <div class="indicateur"><div class="valeur">{compte["non_analyse"]}</div><div class="nom">Non analysés</div></div>
    </div>
    """,
        unsafe_allow_html=True,
    )

if lancer or relancer:
    selection = patients if relancer else a_analyser
    barre = st.progress(0.0, text="Analyse en cours...")
    for numero, dossier in enumerate(selection, start=1):
        identifiant = dossier["patient"]["id"]
        barre.progress((numero - 1) / len(selection), text=f"Analyse du dossier {identifiant} ({numero}/{len(selection)})")
        resultats[identifiant] = analyser(dossier)
        sauver_resultats(resultats)  # sauvegarde au fil de l'eau
    barre.empty()
    st.rerun()

onglet_resultats, onglet_regles, onglet_bio = st.tabs(
    ["Résultats d'analyse", "Règles du système expert", "Valeurs biologiques de référence"]
)


# --- Onglet résultats -------------------------------------------------------

def tableau_html(colonnes, lignes, classes_lignes=(), colonnes_courtes=()):
    st.markdown(html_tableau(colonnes, lignes, classes_lignes, colonnes_courtes), unsafe_allow_html=True)


def afficher_patient(dossier, resultat, normes):
    """Biologie à gauche ; prescription en haut à droite, avis pharmaceutique en dessous.

    Chaque zone a une hauteur calculée sur celle de l'écran (CSS .st-key-zone-*) et défile seule : la page ne
    défile pas, le pharmacien passe d'un dossier à l'autre sans faire défiler. Aucun défilement horizontal.
    """
    patient = dossier["patient"]
    identifiant = patient["id"]
    traitements = dossier["traitements"]

    colonne_patient, colonne_resultat = st.columns([2, 3], gap="medium")

    with colonne_patient:
        libelle("Profil patient")
        st.markdown(f'<div class="profil">{html.escape(profil_patient(patient))}</div>', unsafe_allow_html=True)
        if patient.get("jour_reference"):
            st.caption(f"Jour de référence : {patient['jour_reference']}")
        biologie = patient.get("biologie", {})
        if biologie:
            libelle(f"Biologie ({len(biologie)} paramètres)")
            lignes_bio, classes_bio = tableau_biologie(biologie, normes)
            with st.container(key="zone-bio", border=False):
                tableau_html(["Paramètre", "Valeur", "Interprétation", "Date"], lignes_bio, classes_lignes=classes_bio)

    with colonne_resultat:
        # Lignes dont le LLM propose la modification (points « intervention ») : en rouge
        a_modifier = lignes_a_modifier(resultat)
        legende = " · en rouge : modification proposée" if a_modifier else ""
        libelle(f"Prescription ({len(traitements)} lignes){legende}")
        with st.container(key="zone-prescription", border=False):
            lignes_presc, classes_presc = tableau_prescription(traitements, a_modifier)
            tableau_html(["N°", "Médicament", "Posologie", "Début", "Fin"], lignes_presc, classes_lignes=classes_presc,
                         colonnes_courtes=("N°", "Début", "Fin"))
        libelle("Avis pharmaceutique")
        with st.container(key="zone-avis", border=False):
            afficher_avis(resultat, identifiant)


def afficher_avis(resultat, identifiant):
    """Décision et points de l'avis pharmaceutique."""
    if resultat is None:
        st.info("Dossier non analysé.")
        return
    if "erreur" in resultat:
        st.markdown(
            f'<div class="decision erreur">Échec de l\'analyse ({resultat["date"]})</div>',
            unsafe_allow_html=True,
        )
        st.code(resultat["erreur"], language=None)
        return

    classe = categorie(resultat["decision"])
    st.markdown(
        f'<div class="decision {classe}">{html.escape(resultat["decision"])}</div>', unsafe_allow_html=True
    )
    if "points" in resultat:
        for numero, point in enumerate(resultat["points"]):
            afficher_point(point, cle=f"point-{identifiant}-{numero}", categorie_decision=classe)
    else:  # analyse faite avant le passage aux points : justification en un paragraphe
        st.write(resultat["justification"])
        for numero, source in enumerate(resultat.get("sources", [])):
            if lire_source(source):
                bouton_source(source, cle=f"source-{identifiant}-{numero}")
        with st.container(horizontal=True, gap="small"):
            for numero, alerte in enumerate(resultat.get("alertes", [])):
                lien_alerte(alerte, cle=f"alerte-{identifiant}-{numero}")
    st.markdown(f'<div class="discret">Analyse réalisée le {resultat["date"]}</div>', unsafe_allow_html=True)


# Les widgets non affichés perdent leur valeur : on conserve le filtre et la recherche quand un patient est ouvert
for cle in ("filtre", "recherche"):
    if cle in st.session_state:
        st.session_state[cle] = st.session_state[cle]
st.session_state.setdefault("patient_ouvert", None)

FILTRES = {
    "tous": ("Tous", None),
    "intervention": ("Interventions", {"intervention"}),
    "verification": ("Vérifications", {"verification"}),
    "surveillance": ("Surveillances", {"surveillance"}),
    "valide": ("Validés", {"valide"}),
    "autres": ("Non analysés / erreurs", {"non_analyse", "erreur"}),
}


def libelle_filtre(code):
    nom, codes = FILTRES[code]
    return nom if codes is None else f"{nom} ({sum(compte[c] for c in codes)})"


def ouvrir_patient(identifiant):
    st.session_state.patient_ouvert = identifiant


def fermer_patient():
    st.session_state.patient_ouvert = None


def afficher_liste(affiches):
    """Liste des patients, une ligne cliquable par patient, dans une zone qui défile (CSS .st-key-liste-patients)."""
    if not affiches:
        st.caption("Aucun dossier ne correspond à la sélection.")
        return

    with st.container(key="liste-patients", gap=None):
        st.markdown(
            '<div class="ligne-patient entete"><span>Patient</span><span>Statut</span><span>Âge</span>'
            '<span>Lignes de traitement</span><span>Alertes</span><span>Analysé le</span></div>',
            unsafe_allow_html=True,
        )
        for dossier in affiches:
            patient = dossier["patient"]
            identifiant = patient["id"]
            resultat = resultats.get(identifiant) or {}
            code, etat = statut(resultats.get(identifiant))
            cellules = [
                f"<b>{html.escape(identifiant)}</b>",
                f'<span class="statut {code}">{html.escape(etat)}</span>',
                f"{patient['age']} ans" if patient.get("age") is not None else "—",
                str(len(dossier["traitements"])),
                str(len(resultat.get("alertes", []))) if resultat.get("alertes") else "—",
                html.escape(resultat.get("date", "")) or "—",
            ]
            # Ligne en HTML (colonnes alignées) recouverte d'un bouton invisible qui ouvre le dossier
            with st.container(key=f"ligne-{identifiant}", gap=None):
                st.markdown('<div class="ligne-patient">' + "".join(f"<span>{c}</span>" for c in cellules) + "</div>",
                            unsafe_allow_html=True)
                st.button(f"Ouvrir le dossier {identifiant}", key=f"ouvrir-{identifiant}", on_click=ouvrir_patient,
                          args=(identifiant,), use_container_width=True)

    st.caption(f"{len(affiches)} dossier{'s' if len(affiches) > 1 else ''} affiché{'s' if len(affiches) > 1 else ''}")
    with st.container(key="ajuster-liste"):
        components.html(SCRIPT_HAUTEUR_LISTE, height=0)


# La hauteur de l'en-tête (titres et filtres sur une ou deux lignes) dépend de la largeur de l'écran : ce script
# (dans un cadre invisible) donne à la liste toute la hauteur restante, pour que la page elle-même ne défile pas.
# Sans lui, la hauteur reste celle du CSS (.st-key-liste-patients).
SCRIPT_HAUTEUR_LISTE = """
<script>
const page = window.parent.document;
function ajuster() {
    const liste = page.querySelector(".st-key-liste-patients");
    const principal = page.querySelector('[data-testid="stMain"]');
    if (!liste || !principal) return;
    const haut = liste.getBoundingClientRect().top + principal.scrollTop;
    const bas = 75;  // légende « N dossiers affichés » et marge basse de la page
    const hauteur = Math.max(200, window.parent.innerHeight - haut - bas);
    if (liste.style.maxHeight !== hauteur + "px") liste.style.setProperty("max-height", hauteur + "px", "important");
}
ajuster();
setInterval(ajuster, 250);
</script>
"""


def afficher_dossier_ouvert(affiches):
    """Dossier en pleine largeur, avec retour à la liste et navigation vers le patient précédent ou suivant."""
    identifiant = st.session_state.patient_ouvert
    liste = affiches if any(d["patient"]["id"] == identifiant for d in affiches) else patients_tries
    position = next(i for i, d in enumerate(liste) if d["patient"]["id"] == identifiant)
    dossier = liste[position]
    code, etat = statut(resultats.get(identifiant))

    colonne_retour, colonne_titre, colonne_relance, colonne_precedent, colonne_position, colonne_suivant = st.columns(
        [1.3, 3, 1.6, 1, 0.7, 1], vertical_alignment="center"
    )
    colonne_retour.button("← Liste des patients", on_click=fermer_patient, use_container_width=True)
    colonne_titre.markdown(
        f'<span class="titre-page">Patient {html.escape(identifiant)}</span> &nbsp; '
        f'<span style="color: {COULEURS_STATUTS[code]}; font-weight: 600">{html.escape(etat)}</span>',
        unsafe_allow_html=True,
    )
    if colonne_relance.button("Relancer l'analyse", key=f"analyser-{identifiant}", use_container_width=True,
                              help="Analyse à nouveau ce patient"):
        with st.spinner(f"Analyse du dossier {identifiant} en cours..."):
            resultats[identifiant] = analyser(dossier)
            sauver_resultats(resultats)
        st.rerun()
    if position > 0:
        colonne_precedent.button("‹ Précédent", on_click=ouvrir_patient, args=(liste[position - 1]["patient"]["id"],),
                                 use_container_width=True)
    colonne_position.markdown(f'<div class="discret" style="text-align:center; margin:0">{position + 1} / {len(liste)}</div>',
                              unsafe_allow_html=True)
    if position < len(liste) - 1:
        colonne_suivant.button("Suivant ›", on_click=ouvrir_patient, args=(liste[position + 1]["patient"]["id"],),
                               use_container_width=True)
    afficher_patient(dossier, resultats.get(identifiant), charger_bio())


patients_tries = sorted(patients, key=lambda d: ORDRE_STATUTS[statuts[d["patient"]["id"]]])

with onglet_resultats:
    filtre = st.session_state.get("filtre", "tous")
    recherche = st.session_state.get("recherche", "").strip().lower()
    affiches = [
        d for d in patients_tries
        if (FILTRES[filtre][1] is None or statuts[d["patient"]["id"]] in FILTRES[filtre][1])
        and (
            not recherche
            or recherche in d["patient"]["id"].lower()
            or any(recherche in str(t.get("libelle_medicament", "")).lower() for t in d["traitements"])
        )
    ]

    if st.session_state.patient_ouvert in statuts:
        afficher_dossier_ouvert(affiches)
    else:
        st.session_state.patient_ouvert = None
        colonne_filtre, colonne_recherche = st.columns([3, 1], vertical_alignment="bottom")
        colonne_filtre.radio("Filtrer", list(FILTRES), format_func=libelle_filtre, horizontal=True,
                             label_visibility="collapsed", key="filtre")
        colonne_recherche.text_input("Rechercher", placeholder="Identifiant ou médicament",
                                     label_visibility="collapsed", key="recherche")
        afficher_liste(affiches)


# --- Onglet règles ----------------------------------------------------------

def lignes(texte, virgules=False):
    """Une valeur par ligne (et par virgule si virgules=True : les noms de biologie peuvent contenir des virgules)."""
    if virgules:
        texte = texte.replace(",", "\n")
    return [ligne.strip() for ligne in texte.splitlines() if ligne.strip()]


REGLES_PAR_PAGE = 25

# Paramètres biologiques des dossiers chargés, avec leur unité : le LLM doit utiliser leur nom exact
parametres_biologie = {}
for d in patients:
    for cle, mesure in d["patient"].get("biologie", {}).items():
        parametres_biologie.setdefault(cle, mesure.get("unite") or "")

with onglet_regles:
    regles_personnalisees = charger_regles_personnalisees()
    regles_generiques = charger_regles_generiques()
    st.caption(
        "Une règle se déclenche lorsque l'ensemble de ses critères est vérifié. Les **règles génériques** sont issues "
        "du Thésaurus ANSM des interactions médicamenteuses et de DDI-Predictor ; les **règles personnalisées** sont "
        "propres à l'établissement et peuvent être rédigées par l'assistant à partir d'une demande en langage naturel."
    )
    onglet_perso, onglet_generiques, onglet_test = st.tabs([
        f"Règles personnalisées ({len(regles_personnalisees)})",
        f"Règles génériques ({len(regles_generiques)})",
        "Vérification sur un dossier",
    ])

    with onglet_perso:
        libelle("Ajouter une règle avec l'assistant")
        with st.form("demande_regle", border=False):
            demande = st.text_area(
                "Demande", label_visibility="collapsed", height=90,
                placeholder="Ex. : Alerter si la metformine est prescrite avec un DFG inférieur à 30 mL/min : "
                            "contre-indication, arrêter la metformine.",
            )
            proposer = st.form_submit_button("Proposer une règle", type="primary")
        if proposer and demande.strip():
            with st.spinner("Rédaction de la règle par le modèle..."):
                try:
                    st.session_state["regle_proposee"] = proposer_regle(demande.strip(), parametres_biologie)
                except Exception as erreur:
                    st.session_state.pop("regle_proposee", None)
                    st.error(f"Le modèle n'a pas pu rédiger de règle : {erreur}")

        proposee = st.session_state.get("regle_proposee")
        if proposee:
            libelle("Règle proposée : à vérifier avant enregistrement")
            st.markdown(carte_regle_personnalisee(proposee, parametres_biologie), unsafe_allow_html=True)
            for nom in variables_inconnues(proposee, parametres_biologie):
                st.warning(f"La donnée « {nom} » n'existe pas dans les dossiers : cette condition sera toujours fausse.")
            declenchements = sum(1 for d in patients if appliquer_regles(d, [proposee]))
            st.caption(f"Se déclencherait pour {declenchements} dossier(s) sur {len(patients)} du dossier « {repertoire} ».")
            with st.expander("JSON de la règle"):
                st.json(proposee)
            colonne_enregistrer, colonne_annuler, _ = st.columns([1, 1, 3])
            if colonne_enregistrer.button("Enregistrer la règle", type="primary", use_container_width=True):
                erreurs = ajouter_regle_personnalisee(proposee)
                if erreurs:
                    for erreur in erreurs:
                        st.error(erreur)
                else:
                    del st.session_state["regle_proposee"]
                    st.toast("Règle personnalisée enregistrée.")
                    st.rerun()
            if colonne_annuler.button("Annuler", use_container_width=True):
                del st.session_state["regle_proposee"]
                st.rerun()

        libelle(f"Règles personnalisées ({len(regles_personnalisees)})")
        if not regles_personnalisees:
            st.caption("Aucune règle personnalisée.")
        for numero, regle in enumerate(regles_personnalisees):
            colonne_texte, colonne_supprimer = st.columns([7, 1])
            colonne_texte.markdown(carte_regle_personnalisee(regle, parametres_biologie), unsafe_allow_html=True)
            if colonne_supprimer.button("Supprimer", key=f"supprimer-regle-{numero}", use_container_width=True):
                sauver_regles_personnalisees(regles_personnalisees[:numero] + regles_personnalisees[numero + 1:])
                st.rerun()

        with st.expander("Saisie manuelle d'une règle"):
            st.caption(
                "Une condition s'écrit `donnee operateur valeur` (opérateurs `>=` `<=` `>` `<` `==` `!=`). Données "
                "disponibles : caractéristiques du patient (`age`, `poids_kg`, `taille_cm`, `imc_kg_m2`, "
                "`surface_corporelle_m2`), biologie avec le nom exact du paramètre (`Créatinine (sang)`, "
                "`DFG estimé (CKD-EPI)`...) et, pour les médicaments cités dans la règle, dosage de la spécialité "
                "(`dose_apixaban`), dose en mg par jour (`dose_jour_daptomycine`) et en mg/kg par jour "
                "(`dose_kg_daptomycine`). Un médicament est considéré comme prescrit si son nom figure dans le "
                "libellé d'une ligne de prescription (sans tenir compte des majuscules et des accents)."
            )
            with st.form("ajout_regle", clear_on_submit=False, border=False):
                alerte = st.text_area(
                    "Message d'alerte (obligatoire)",
                    placeholder="Ex. : Metformine contre-indiquée en cas d'insuffisance rénale sévère",
                )
                colonne_a, colonne_b = st.columns(2)
                medicaments = colonne_a.text_area(
                    "Médicaments concernés (DCI, un par ligne)", placeholder="apixaban",
                    help="La règle ne s'applique que si tous ces médicaments sont prescrits.",
                )
                conditions = colonne_b.text_area(
                    "Conditions requises (une par ligne)", placeholder="DFG estimé (CKD-EPI) < 30"
                )
                parmi = colonne_a.text_area("Critères au choix (un par ligne)", placeholder="age >= 80")
                minimum = colonne_b.number_input("Nombre minimal de critères au choix vérifiés", min_value=0, value=0)
                ajouter = st.form_submit_button("Enregistrer la règle", type="primary")

            if ajouter:
                nouvelle = {"alerte": alerte.strip()}
                if lignes(medicaments, virgules=True):
                    nouvelle["medicaments"] = lignes(medicaments, virgules=True)
                if lignes(conditions):
                    nouvelle["conditions"] = lignes(conditions)
                if lignes(parmi):
                    nouvelle["parmi"] = lignes(parmi)
                    nouvelle["minimum"] = int(minimum)
                erreurs = ajouter_regle_personnalisee(nouvelle)
                if erreurs:
                    for erreur in erreurs:
                        st.error(erreur)
                else:
                    st.success("Règle enregistrée.")
                    st.rerun()

        with st.expander("Édition avancée du fichier regles_personnalisees.json"):
            texte = st.text_area(
                "Contenu JSON", json.dumps(regles_personnalisees, ensure_ascii=False, indent=2), height=350,
                key="json_regles",
            )
            if st.button("Enregistrer les modifications"):
                try:
                    erreurs = sauver_regles_personnalisees(json.loads(texte))
                except json.JSONDecodeError as erreur:
                    erreurs = [f"JSON invalide : {erreur}"]
                if erreurs:
                    for erreur in erreurs:
                        st.error(erreur)
                else:
                    st.success("Règles enregistrées.")
                    st.rerun()

    with onglet_generiques:
        st.caption(
            "Règles extraites des documents de référence (fichier regles_generiques.json), en lecture seule. "
            "Une classe du Thésaurus (ex : anticoagulants oraux) est recherchée via la liste de ses DCI."
        )
        colonne_recherche_regle, colonne_niveau, colonne_source = st.columns([3, 3, 2], vertical_alignment="bottom")
        recherche_regle = normaliser(colonne_recherche_regle.text_input(
            "Rechercher", placeholder="DCI, classe ou mot-clé (ex : apixaban, hyperkaliémie)", key="recherche_regle"
        ).strip())
        niveaux_choisis = colonne_niveau.multiselect(
            "Niveau", list(NIVEAUX.values()) + ["Pharmacocinétique"], placeholder="Tous les niveaux"
        )
        source_choisie = colonne_source.selectbox("Source", ["Toutes", "Thésaurus ANSM", "DDI-Predictor"])

        def niveau_retenu(regle):
            if not niveaux_choisis:
                return True
            libelles = [NIVEAUX[c] for c in codes_niveau(regle)] or ["Pharmacocinétique"]
            return any(l in niveaux_choisis for l in libelles)

        filtrees = [
            r for r in regles_generiques
            if (source_choisie == "Toutes" or r.get("source", "").startswith(source_choisie))
            and niveau_retenu(r)
            and (
                not recherche_regle
                or recherche_regle in normaliser(r["alerte"])
                or recherche_regle in json.dumps(r.get("medicaments", []), ensure_ascii=False)
            )
        ]
        nb_pages_regles = max(1, math.ceil(len(filtrees) / REGLES_PAR_PAGE))
        colonne_page_regle, colonne_info_regle = st.columns([1, 4], vertical_alignment="bottom")
        page_regle = colonne_page_regle.number_input(
            f"Page (sur {nb_pages_regles})", min_value=1, max_value=nb_pages_regles, value=1, key="page_regles"
        )
        debut_regle = (page_regle - 1) * REGLES_PAR_PAGE
        if filtrees:
            colonne_info_regle.caption(
                f"Règles {debut_regle + 1} à {min(debut_regle + REGLES_PAR_PAGE, len(filtrees))} sur {len(filtrees)}"
            )
        else:
            colonne_info_regle.caption("Aucune règle ne correspond à la recherche.")
        st.markdown(
            "".join(carte_regle_generique(r) for r in filtrees[debut_regle:debut_regle + REGLES_PAR_PAGE]),
            unsafe_allow_html=True,
        )

    with onglet_test:
        if patients:
            choix = st.selectbox("Patient", [d["patient"]["id"] for d in patients], key="test_regles")
            dossier = next(d for d in patients if d["patient"]["id"] == choix)
            try:
                alertes = verifier_regles(dossier)
            except Exception as erreur:
                alertes = None
                st.error(f"Erreur dans les règles : {erreur}")
            if alertes:
                for alerte in alertes:
                    afficher_alerte(alerte)
            elif alertes is not None:
                st.success("Aucune alerte pour ce dossier.")
        else:
            st.caption("Aucun dossier patient chargé.")


# --- Onglet biologie --------------------------------------------------------

with onglet_bio:
    st.caption(
        "Intervalles de référence utilisés pour signaler une biologie anormale lors de la recherche documentaire. "
        "La clé doit correspondre exactement au nom du paramètre dans la biologie des patients."
    )
    parametres = {}
    for d in patients:
        for cle, mesure in d["patient"].get("biologie", {}).items():
            parametres.setdefault(cle, {"Clé": cle, "Unité": mesure.get("unite") or "", "Nombre de patients": 0})
            parametres[cle]["Nombre de patients"] += 1
    if parametres:
        with st.expander(f"Paramètres présents dans le dossier « {repertoire} » ({len(parametres)})"):
            st.dataframe(
                pd.DataFrame(parametres.values()).sort_values("Nombre de patients", ascending=False),
                hide_index=True, use_container_width=True,
            )

    tableau_bio = pd.DataFrame(
        [{"cle": cle, **norme} for cle, norme in charger_bio().items()],
        columns=["cle", "libelle", "unite", "min", "max"],
    )
    modifie = st.data_editor(
        tableau_bio,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        column_config={
            "cle": st.column_config.TextColumn("Clé", required=True),
            "libelle": st.column_config.TextColumn("Libellé"),
            "unite": st.column_config.TextColumn("Unité"),
            "min": st.column_config.NumberColumn("Borne inférieure", required=True),
            "max": st.column_config.NumberColumn("Borne supérieure", required=True),
        },
        key="editeur_bio",
    )
    if st.button("Enregistrer les valeurs de référence", type="primary"):
        modifie = modifie.dropna(how="all")
        lignes_bio = modifie.astype(object).where(modifie.notna(), None).to_dict("records")
        erreurs = sauver_bio(lignes_bio)
        if erreurs:
            for erreur in erreurs:
                st.error(erreur)
        else:
            st.success("Valeurs de référence enregistrées.")
