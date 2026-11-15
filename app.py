"""Interface Streamlit : analyse des patients, base documentaire, règles du système expert et biologie.

Lancement depuis la racine du projet :  streamlit run app.py
Le thème clair est défini dans .streamlit/config.toml.
"""

import html
import json
import os

# Les scripts du projet utilisent des chemins relatifs (input.json, chroma_db...) : on se place à la racine.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import streamlit as st

from expert_system import verifier_regles
from src.analyse import DECISION_VALIDE, analyser, lire_source
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
    charger_bio,
    charger_patients,
    charger_regles,
    charger_resultats,
    sauver_bio,
    sauver_regles,
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
.decision.erreur {{ background: var(--rouge-fond); border-color: var(--rouge); color: var(--rouge); }}
.libelle {{
    font-size: 0.75rem; font-weight: 600; color: var(--texte-3); text-transform: uppercase;
    letter-spacing: 0.07em; margin: 0.8rem 0 0.3rem 0;
}}
.alerte {{
    background: var(--orange-fond); border-left: 3px solid var(--orange); border-radius: 3px;
    padding: 0.4rem 0.7rem; margin-bottom: 0.35rem; font-size: 0.86rem; color: var(--texte);
}}
.profil {{ color: var(--texte); font-weight: 500; }}
.discret {{ color: var(--texte-3); font-size: 0.76rem; margin-top: 0.6rem; }}
</style>
""",
    unsafe_allow_html=True,
)


def titre_section(texte):
    st.markdown(f'<div class="titre-section">{html.escape(texte)}</div>', unsafe_allow_html=True)


def libelle(texte):
    st.markdown(f'<div class="libelle">{html.escape(texte)}</div>', unsafe_allow_html=True)


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


# ---------------------------------------------------------------------------
# Barre latérale : base patients et base documentaire
# ---------------------------------------------------------------------------

patients = charger_patients()

with st.sidebar:
    titre_section("Base patients")
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

def statut(resultat):
    """Renvoie (code, libellé) du statut d'un dossier."""
    if resultat is None:
        return "non_analyse", "Non analysé"
    if "erreur" in resultat:
        return "erreur", "Erreur d'analyse"
    if resultat["decision"] == DECISION_VALIDE:
        return "valide", "Validé"
    return "intervention", "Intervention proposée"


resultats = charger_resultats()
statuts = {d["patient"]["id"]: statut(resultats.get(d["patient"]["id"]))[0] for d in patients}
compte = {code: list(statuts.values()).count(code) for code in ("non_analyse", "erreur", "valide", "intervention")}

st.markdown(
    f"""
<div class="barre-app">
  <div class="marque">
    <span class="etablissement">{html.escape(NOM_ETABLISSEMENT)}</span>
    <span class="separateur"></span>
    <span class="logiciel">{html.escape(NOM_LOGICIEL)}</span>
  </div>
  <div class="contexte">
    <span><b>{len(patients)}</b> dossiers</span>
    <span><b>{len(indexes)}</b> référentiels indexés</span>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

colonne_titre, colonne_action = st.columns([3, 1], vertical_alignment="center")
colonne_titre.markdown(
    '<p class="titre-page">Analyse des prescriptions</p>'
    '<p class="sous-titre-page">Système expert, recommandations de référence et modèle de langage</p>',
    unsafe_allow_html=True,
)
lancer = colonne_action.button(
    "Lancer l'analyse de tous les patients", type="primary", disabled=not patients, use_container_width=True
)

st.markdown(
    f"""
<div class="indicateurs">
  <div class="indicateur"><div class="valeur">{len(patients)}</div><div class="nom">Dossiers</div></div>
  <div class="indicateur"><div class="valeur">{len(patients) - compte["non_analyse"]}</div><div class="nom">Analysés</div></div>
  <div class="indicateur orange"><div class="valeur">{compte["intervention"]}</div><div class="nom">Interventions proposées</div></div>
  <div class="indicateur vert"><div class="valeur">{compte["valide"]}</div><div class="nom">Validés</div></div>
  <div class="indicateur rouge"><div class="valeur">{compte["erreur"]}</div><div class="nom">Erreurs</div></div>
  <div class="indicateur"><div class="valeur">{compte["non_analyse"]}</div><div class="nom">Non analysés</div></div>
</div>
""",
    unsafe_allow_html=True,
)

if lancer:
    barre = st.progress(0.0, text="Analyse en cours...")
    for numero, dossier in enumerate(patients, start=1):
        identifiant = dossier["patient"]["id"]
        barre.progress((numero - 1) / len(patients), text=f"Analyse du dossier {identifiant} ({numero}/{len(patients)})")
        resultats[identifiant] = analyser(dossier)
        sauver_resultats(resultats)  # sauvegarde au fil de l'eau
    barre.empty()
    st.rerun()

onglet_resultats, onglet_regles, onglet_bio = st.tabs(
    ["Résultats d'analyse", "Règles du système expert", "Valeurs biologiques de référence"]
)


# --- Onglet résultats -------------------------------------------------------

def afficher_patient(dossier, resultat):
    patient = dossier["patient"]
    identifiant = patient["id"]

    colonne_patient, colonne_resultat = st.columns([2, 3], gap="large")

    with colonne_patient:
        libelle("Profil patient")
        st.markdown(
            f'<div class="profil">{patient.get("age", "?")} ans · {patient.get("sexe", "?")} · '
            f'{patient.get("poids_kg", "?")} kg · {patient.get("taille_cm", "?")} cm</div>',
            unsafe_allow_html=True,
        )
        biologie = patient.get("biologie", {})
        if biologie:
            libelle("Biologie")
            st.markdown(" · ".join(f"`{cle}` {valeur}" for cle, valeur in biologie.items()))
        libelle("Prescription")
        # Tout en texte : la colonne dosage mélange nombres et chaînes ("200/6")
        tableau = pd.DataFrame(dossier["traitements"]).fillna("").astype(str)
        st.dataframe(tableau, hide_index=True, use_container_width=True)
        if st.button("Relancer l'analyse de ce patient", key=f"analyser-{identifiant}"):
            with st.spinner(f"Analyse du dossier {identifiant} en cours..."):
                resultats[identifiant] = analyser(dossier)
                sauver_resultats(resultats)
            st.rerun()

    with colonne_resultat:
        libelle("Avis pharmaceutique")
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

        classe = "valide" if resultat["decision"] == DECISION_VALIDE else "intervention"
        st.markdown(
            f'<div class="decision {classe}">{html.escape(resultat["decision"])}</div>', unsafe_allow_html=True
        )
        st.write(resultat["justification"])

        if resultat.get("alertes"):
            libelle("Alertes du système expert")
            for alerte in resultat["alertes"]:
                st.markdown(f'<div class="alerte">{html.escape(alerte)}</div>', unsafe_allow_html=True)

        libelle("Sources")
        if resultat.get("sources"):
            for numero, source in enumerate(resultat["sources"]):
                bouton_source(source, cle=f"source-{identifiant}-{numero}")
        else:
            st.caption("Aucune source citée : avis fondé sur les connaissances générales du modèle.")
        st.markdown(f'<div class="discret">Analyse réalisée le {resultat["date"]}</div>', unsafe_allow_html=True)


with onglet_resultats:
    filtres = {
        "Tous": None,
        f"Interventions ({compte['intervention']})": {"intervention"},
        f"Validés ({compte['valide']})": {"valide"},
        f"Non analysés / erreurs ({compte['non_analyse'] + compte['erreur']})": {"non_analyse", "erreur"},
    }
    colonne_filtre, colonne_recherche = st.columns([3, 1], vertical_alignment="bottom")
    filtre = colonne_filtre.radio("Filtrer", list(filtres), horizontal=True, label_visibility="collapsed")
    recherche = colonne_recherche.text_input(
        "Rechercher", placeholder="Identifiant ou DCI", label_visibility="collapsed"
    ).strip().lower()

    # Les dossiers nécessitant une action apparaissent en premier
    ordre = {"intervention": 0, "erreur": 1, "non_analyse": 2, "valide": 3}
    couleurs = {"intervention": "orange", "erreur": "red", "non_analyse": "gray", "valide": "green"}
    affiches = [
        d for d in sorted(patients, key=lambda d: ordre[statuts[d["patient"]["id"]]])
        if (filtres[filtre] is None or statuts[d["patient"]["id"]] in filtres[filtre])
        and (
            not recherche
            or recherche in d["patient"]["id"].lower()
            or any(recherche in str(t.get("dci", "")).lower() for t in d["traitements"])
        )
    ]

    if not affiches:
        st.caption("Aucun dossier ne correspond à la sélection.")
    for dossier in affiches:
        patient = dossier["patient"]
        identifiant = patient["id"]
        code, etat = statut(resultats.get(identifiant))
        nb_alertes = len(resultats.get(identifiant, {}).get("alertes", []))
        resume = (
            f"{patient.get('age', '?')} ans · {patient.get('sexe', '?')} · "
            f"{len(dossier['traitements'])} lignes de traitement"
        )
        if nb_alertes:
            resume += f" · {nb_alertes} alerte(s)"
        with st.expander(f"**{identifiant}**  ·  :{couleurs[code]}[{etat}]  ·  :gray[{resume}]"):
            afficher_patient(dossier, resultats.get(identifiant))


# --- Onglet règles ----------------------------------------------------------

def lignes(texte):
    return [ligne.strip() for ligne in texte.replace(",", "\n").splitlines() if ligne.strip()]


with onglet_regles:
    regles = charger_regles()
    st.caption(
        "Une règle se déclenche lorsque l'ensemble de ses critères est vérifié. Une condition s'écrit "
        "`donnee operateur valeur` (opérateurs `>=` `<=` `>` `<` `==` `!=`). Données disponibles : "
        "caractéristiques du patient (`age`, `poids_kg`...), biologie (`creatinine_serique`...) et dose "
        "de chaque médicament prescrit (`dose_apixaban`...)."
    )

    libelle(f"Règles actives ({len(regles)})")
    for numero, regle in enumerate(regles):
        with st.container(border=True):
            colonne_texte, colonne_supprimer = st.columns([6, 1], vertical_alignment="center")
            colonne_texte.markdown(f"**{numero + 1}.** {regle.get('alerte', '')}")
            details = []
            if regle.get("medicaments"):
                details.append("Médicaments : " + ", ".join(f"`{m}`" for m in regle["medicaments"]))
            if regle.get("conditions"):
                details.append("Conditions requises : " + ", ".join(f"`{c}`" for c in regle["conditions"]))
            if regle.get("parmi"):
                details.append(
                    f"Au moins {regle.get('minimum', 0)} critère(s) parmi : "
                    + ", ".join(f"`{c}`" for c in regle["parmi"])
                )
            if details:
                colonne_texte.caption("  \n".join(details))
            if colonne_supprimer.button("Supprimer", key=f"supprimer-regle-{numero}", use_container_width=True):
                sauver_regles(regles[:numero] + regles[numero + 1:])
                st.rerun()

    libelle("Nouvelle règle")
    with st.form("ajout_regle", clear_on_submit=False):
        alerte = st.text_area(
            "Message d'alerte (obligatoire)",
            placeholder="Ex. : Metformine contre-indiquée en cas d'insuffisance rénale sévère",
        )
        colonne_a, colonne_b = st.columns(2)
        medicaments = colonne_a.text_area(
            "Médicaments concernés (DCI, un par ligne)", placeholder="metformine",
            help="La règle ne s'applique que si tous ces médicaments sont prescrits.",
        )
        conditions = colonne_b.text_area(
            "Conditions requises (une par ligne)", placeholder="creatinine_serique >= 200"
        )
        parmi = colonne_a.text_area("Critères au choix (un par ligne)", placeholder="age >= 80")
        minimum = colonne_b.number_input("Nombre minimal de critères au choix vérifiés", min_value=0, value=0)
        ajouter = st.form_submit_button("Enregistrer la règle", type="primary")

    if ajouter:
        nouvelle = {"alerte": alerte.strip()}
        if lignes(medicaments):
            nouvelle["medicaments"] = lignes(medicaments)
        if lignes(conditions):
            nouvelle["conditions"] = lignes(conditions)
        if lignes(parmi):
            nouvelle["parmi"] = lignes(parmi)
            nouvelle["minimum"] = int(minimum)
        erreurs = sauver_regles(regles + [nouvelle])
        if erreurs:
            for erreur in erreurs:
                st.error(erreur)
        else:
            st.success("Règle enregistrée.")
            st.rerun()

    with st.expander("Édition avancée du fichier regles_expert.json"):
        texte = st.text_area(
            "Contenu JSON", json.dumps(regles, ensure_ascii=False, indent=2), height=350, key="json_regles"
        )
        if st.button("Enregistrer les modifications"):
            try:
                erreurs = sauver_regles(json.loads(texte))
            except json.JSONDecodeError as erreur:
                erreurs = [f"JSON invalide : {erreur}"]
            if erreurs:
                for erreur in erreurs:
                    st.error(erreur)
            else:
                st.success("Règles enregistrées.")
                st.rerun()

    libelle("Vérification des règles sur un dossier")
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
                st.markdown(f'<div class="alerte">{html.escape(alerte)}</div>', unsafe_allow_html=True)
        elif alertes is not None:
            st.success("Aucune alerte pour ce dossier.")


# --- Onglet biologie --------------------------------------------------------

with onglet_bio:
    st.caption(
        "Intervalles de référence utilisés pour signaler une biologie anormale lors de la recherche documentaire. "
        "La clé doit correspondre exactement au nom du paramètre dans la biologie des patients."
    )
    cles_patients = sorted({cle for d in patients for cle in d["patient"].get("biologie", {})})
    if cles_patients:
        st.caption("Paramètres présents dans la base patients : " + ", ".join(f"`{c}`" for c in cles_patients))

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
