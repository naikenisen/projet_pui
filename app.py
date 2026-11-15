"""Interface Streamlit : analyse des patients, base documentaire, règles du système expert et biologie.

Lancement depuis la racine du projet :  streamlit run app.py
"""

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

st.set_page_config(page_title="Analyse d'ordonnances", page_icon="💊", layout="wide")


# ---------------------------------------------------------------------------
# Visionneuse de documents
# ---------------------------------------------------------------------------

@st.dialog("Document", width="large")
def ouvrir_document(nom, page=1):
    chemin = chemin_document(nom)
    if not os.path.exists(chemin):
        st.error(f"« {nom} » est introuvable dans base_documentaire/.")
        return

    total = nombre_pages(chemin)
    st.subheader(nom)
    colonne_page, colonne_telechargement = st.columns([1, 1])
    page = colonne_page.number_input(
        f"Page (sur {total})", min_value=1, max_value=total, value=min(page, total), key=f"page-{nom}-{page}"
    )
    with open(chemin, "rb") as fichier:
        colonne_telechargement.download_button(
            "⬇️ Télécharger le PDF", fichier.read(), file_name=nom, mime="application/pdf"
        )
    st.image(rendre_page(chemin, page))


def bouton_source(source, cle):
    """Affiche un bouton qui ouvre la source si c'est un PDF de la base, sinon un simple texte."""
    document = lire_source(source)
    if document is None:
        st.markdown(f"- {source}")
        return
    nom, page = document
    if st.button(f"📄 {source}", key=cle, help=f"Ouvrir {nom} à la page {page}"):
        ouvrir_document(nom, page)


# ---------------------------------------------------------------------------
# Barre latérale : base patients et base documentaire
# ---------------------------------------------------------------------------

patients = charger_patients()

with st.sidebar:
    st.metric("Patients dans input.json", len(patients))
    st.divider()

    st.header("📚 Base documentaire")
    try:
        indexes = documents_indexes()
    except Exception as erreur:
        indexes = {}
        st.error(f"Lecture de ChromaDB impossible : {erreur}")

    if indexes:
        st.caption("Documents indexés dans ChromaDB (cliquer pour ouvrir)")
        for nom, nb_passages in indexes.items():
            if st.button(f"📄 {nom} · {nb_passages} passages", key=f"doc-{nom}", use_container_width=True):
                ouvrir_document(nom)
    else:
        st.info("Aucun document indexé.")

    non_indexes = [nom for nom in documents_du_dossier() if nom not in indexes]
    if non_indexes:
        st.caption("Présents dans base_documentaire/ mais non indexés")
        for nom in non_indexes:
            colonne_nom, colonne_bouton = st.columns([3, 1])
            colonne_nom.markdown(f"`{nom}`")
            if colonne_bouton.button("Indexer", key=f"indexer-{nom}"):
                with st.spinner(f"Indexation de {nom}..."):
                    nb = indexer_pdf(chemin_document(nom))
                st.toast(f"{nom} : {nb} passages indexés")
                st.rerun()

    with st.form("ajout_document", clear_on_submit=True):
        fichiers = st.file_uploader(
            "Ajouter des PDF à la base", type="pdf", accept_multiple_files=True,
            help="Le fichier est copié dans base_documentaire/ puis indexé dans ChromaDB.",
        )
        envoye = st.form_submit_button("Indexer", use_container_width=True)
    if envoye and fichiers:
        for fichier in fichiers:
            with st.spinner(f"Indexation de {fichier.name}..."):
                try:
                    nb = indexer_pdf(enregistrer_pdf(fichier.name, fichier.getvalue()))
                    st.toast(f"{fichier.name} : {nb} passages indexés")
                except Exception as erreur:
                    st.error(f"{fichier.name} : {erreur}")
        st.rerun()


# ---------------------------------------------------------------------------
# Panneau principal
# ---------------------------------------------------------------------------

st.title("💊 Analyse pharmaceutique des ordonnances")

resultats = charger_resultats()
analyses = [resultats[d["patient"]["id"]] for d in patients if d["patient"]["id"] in resultats]
colonnes = st.columns(4)
colonnes[0].metric("Patients", len(patients))
colonnes[1].metric("Analysés", len(analyses))
colonnes[2].metric("Validés", sum(r.get("decision") == DECISION_VALIDE for r in analyses))
colonnes[3].metric("Interventions", sum("decision" in r and r["decision"] != DECISION_VALIDE for r in analyses))

if st.button("▶️ Analyser tous les patients", type="primary", disabled=not patients):
    barre = st.progress(0.0, text="Analyse en cours...")
    for numero, dossier in enumerate(patients, start=1):
        identifiant = dossier["patient"]["id"]
        barre.progress((numero - 1) / len(patients), text=f"Analyse de {identifiant} ({numero}/{len(patients)})")
        resultats[identifiant] = analyser(dossier)
        sauver_resultats(resultats)  # sauvegarde au fil de l'eau
    barre.empty()
    st.rerun()

onglet_resultats, onglet_regles, onglet_bio = st.tabs(
    ["📋 Résultats", "⚙️ Règles du système expert", "🧪 Biologie anormale"]
)


# --- Onglet résultats -------------------------------------------------------

def afficher_patient(dossier, resultat):
    patient = dossier["patient"]
    identifiant = patient["id"]

    colonne_patient, colonne_resultat = st.columns([2, 3])

    with colonne_patient:
        st.markdown(
            f"**{patient.get('age', '?')} ans · {patient.get('sexe', '?')} · "
            f"{patient.get('poids_kg', '?')} kg · {patient.get('taille_cm', '?')} cm**"
        )
        biologie = patient.get("biologie", {})
        if biologie:
            st.markdown("Biologie : " + " · ".join(f"`{cle}` = {valeur}" for cle, valeur in biologie.items()))
        # Tout en texte : la colonne dosage mélange nombres et chaînes ("200/6")
        tableau = pd.DataFrame(dossier["traitements"]).fillna("").astype(str)
        st.dataframe(tableau, hide_index=True, use_container_width=True)
        if st.button("🔄 Analyser ce patient", key=f"analyser-{identifiant}"):
            with st.spinner(f"Analyse de {identifiant}..."):
                resultats[identifiant] = analyser(dossier)
                sauver_resultats(resultats)
            st.rerun()

    with colonne_resultat:
        if resultat is None:
            st.info("Patient pas encore analysé.")
            return
        if "erreur" in resultat:
            st.error(f"Échec de l'analyse ({resultat['date']}) : {resultat['erreur']}")
            return

        if resultat["decision"] == DECISION_VALIDE:
            st.success(f"**{resultat['decision']}**")
        else:
            st.warning(f"**{resultat['decision']}**")
        st.write(resultat["justification"])

        if resultat.get("alertes"):
            st.markdown("**Alertes du système expert**")
            for alerte in resultat["alertes"]:
                st.markdown(f"- ⚠️ {alerte}")

        st.markdown("**Sources**")
        if resultat.get("sources"):
            for numero, source in enumerate(resultat["sources"]):
                bouton_source(source, cle=f"source-{identifiant}-{numero}")
        else:
            st.caption("Aucune source citée : décision fondée sur les connaissances du modèle.")
        st.caption(f"Analysé le {resultat['date']}")


with onglet_resultats:
    if not patients:
        st.info("Aucun patient dans input.json.")
    for dossier in patients:
        identifiant = dossier["patient"]["id"]
        resultat = resultats.get(identifiant)
        if resultat is None:
            icone, etat = "⚪", "non analysé"
        elif "erreur" in resultat:
            icone, etat = "❌", "erreur"
        elif resultat["decision"] == DECISION_VALIDE:
            icone, etat = "✅", resultat["decision"]
        else:
            icone, etat = "⚠️", resultat["decision"]
        with st.expander(f"{icone} **{identifiant}** — {etat}"):
            afficher_patient(dossier, resultat)


# --- Onglet règles ----------------------------------------------------------

def lignes(texte):
    return [ligne.strip() for ligne in texte.replace(",", "\n").splitlines() if ligne.strip()]


with onglet_regles:
    regles = charger_regles()
    st.caption(
        "Une règle se déclenche si tous ses champs sont vérifiés. Une condition s'écrit `donnee operateur valeur` "
        "(opérateurs `>=` `<=` `>` `<` `==` `!=`). Données utilisables : champs du patient (`age`, `poids_kg`...), "
        "de sa biologie (`creatinine_serique`...) et dose de chaque médicament (`dose_apixaban`...)."
    )

    st.subheader(f"Règles actuelles ({len(regles)})")
    for numero, regle in enumerate(regles):
        with st.container(border=True):
            colonne_texte, colonne_supprimer = st.columns([6, 1])
            colonne_texte.markdown(f"**{numero + 1}.** {regle.get('alerte', '')}")
            details = []
            if regle.get("medicaments"):
                details.append("Médicaments : " + ", ".join(f"`{m}`" for m in regle["medicaments"]))
            if regle.get("conditions"):
                details.append("Toutes : " + ", ".join(f"`{c}`" for c in regle["conditions"]))
            if regle.get("parmi"):
                details.append(
                    f"Au moins {regle.get('minimum', 0)} parmi : " + ", ".join(f"`{c}`" for c in regle["parmi"])
                )
            if details:
                colonne_texte.caption("  \n".join(details))
            if colonne_supprimer.button("🗑️ Supprimer", key=f"supprimer-regle-{numero}"):
                sauver_regles(regles[:numero] + regles[numero + 1:])
                st.rerun()

    st.subheader("Ajouter une règle")
    with st.form("ajout_regle", clear_on_submit=False):
        alerte = st.text_area("Message d'alerte *", placeholder="Ex : Metformine contre-indiquée si DFG < 30")
        colonne_a, colonne_b = st.columns(2)
        medicaments = colonne_a.text_area(
            "Médicaments (DCI, un par ligne)", placeholder="metformine",
            help="La règle ne s'applique que si tous ces médicaments sont prescrits.",
        )
        conditions = colonne_b.text_area(
            "Conditions toutes obligatoires (une par ligne)", placeholder="creatinine_serique >= 200"
        )
        parmi = colonne_a.text_area("Conditions « au moins N parmi » (une par ligne)", placeholder="age >= 80")
        minimum = colonne_b.number_input("N (minimum de conditions « parmi » vraies)", min_value=0, value=0)
        ajouter = st.form_submit_button("Ajouter la règle", type="primary")

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
            st.success("Règle ajoutée.")
            st.rerun()

    with st.expander("✏️ Modifier directement regles_expert.json"):
        texte = st.text_area(
            "Contenu JSON", json.dumps(regles, ensure_ascii=False, indent=2), height=350, key="json_regles"
        )
        if st.button("Enregistrer le JSON"):
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

    st.subheader("Tester les règles sur un patient")
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
                st.warning(alerte)
        elif alertes is not None:
            st.success("Aucune alerte")


# --- Onglet biologie --------------------------------------------------------

with onglet_bio:
    st.caption(
        "Valeurs normales utilisées par recuperation.py pour signaler une biologie anormale dans la recherche. "
        "La clé doit correspondre au nom de la donnée dans la biologie des patients."
    )
    cles_patients = sorted({cle for d in patients for cle in d["patient"].get("biologie", {})})
    if cles_patients:
        st.caption("Clés présentes dans input.json : " + ", ".join(f"`{c}`" for c in cles_patients))

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
            "min": st.column_config.NumberColumn("Min", required=True),
            "max": st.column_config.NumberColumn("Max", required=True),
        },
        key="editeur_bio",
    )
    if st.button("💾 Enregistrer les valeurs normales", type="primary"):
        modifie = modifie.dropna(how="all")
        lignes_bio = modifie.astype(object).where(modifie.notna(), None).to_dict("records")
        erreurs = sauver_bio(lignes_bio)
        if erreurs:
            for erreur in erreurs:
                st.error(erreur)
        else:
            st.success("bio_anormale.json mis à jour.")
