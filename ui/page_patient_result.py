# Dossier d'un patient ouvert depuis la liste, et statut des dossiers.

import html
import re

import streamlit as st

from generation import (
    DECISION_INTERVENTION,
    DECISION_MONITORING,
    DECISION_VALIDATED,
    DECISION_VERIFICATION,
    lab_interpretation,
    read_lab_ranges,
)
from ui.common import badge, label
from ui.page_rag_documents import open_document


# records : liste parcourue par les boutons précédent / suivant
def render_page(records, results):
    patient_id = st.session_state.open_patient
    position = next(i for i, r in enumerate(records) if r["patient"]["id"] == patient_id)
    _navigation_bar(records, position, results.get(patient_id))
    _patient_record(records[position], results.get(patient_id), read_lab_ranges())


def open_patient(patient_id):
    st.session_state.open_patient = patient_id


def close_patient():
    st.session_state.open_patient = None


# Catégorie de chaque décision écrite par generation.py
CATEGORIES = {DECISION_INTERVENTION: "intervention", DECISION_VERIFICATION: "verification",
              DECISION_MONITORING: "monitoring", DECISION_VALIDATED: "validated"}
# Décision affichée dans l'avis, par catégorie
DECISION_LABELS = {
    "intervention": "INTERVENTION PHARMACEUTIQUE PROPOSÉE",
    "verification": "VÉRIFICATION PROPOSÉE",
    "monitoring": "SURVEILLANCE PROPOSÉE",
    "validated": "PATIENT VALIDÉ",
}
STATUS_LABELS = {
    "intervention": "Intervention proposée",
    "verification": "Vérification proposée",
    "monitoring": "Surveillance proposée",
    "validated": "Validé",
    "error": "Erreur d'analyse",
    "not_analysed": "Non analysé",
}


# Une décision inconnue est traitée comme une intervention, pour être vérifiée en premier
def category(decision):
    return CATEGORIES.get(decision, "intervention")


# (code, libellé) du statut d'un dossier
def status(result):
    if result is None:
        code = "not_analysed"
    elif "error" in result:
        code = "error"
    else:
        code = category(result["decision"])
    return code, STATUS_LABELS[code]


def _navigation_bar(records, position, result):
    patient_id = records[position]["patient"]["id"]
    code, state_label = status(result)

    back_column, title_column, previous_column, position_column, next_column = st.columns(
        [1.3, 4.6, 1, 0.7, 1], vertical_alignment="center"
    )
    back_column.button("← Liste des patients", on_click=close_patient, use_container_width=True)
    title_column.markdown(
        f'<span class="page-title">Patient {html.escape(patient_id)}</span> &nbsp; '
        f'<span class="status {code}">{html.escape(state_label)}</span>',
        unsafe_allow_html=True,
    )
    if position > 0:
        previous_column.button("‹ Précédent", on_click=open_patient, args=(records[position - 1]["patient"]["id"],),
                               use_container_width=True)
    position_column.markdown(f'<div class="muted" style="text-align:center; margin:0">{position + 1} / {len(records)}</div>',
                             unsafe_allow_html=True)
    if position < len(records) - 1:
        next_column.button("Suivant ›", on_click=open_patient, args=(records[position + 1]["patient"]["id"],),
                           use_container_width=True)


# Biologie à gauche, prescription et avis à droite ; chaque zone défile seule (CSS .st-key-zone-*)
def _patient_record(record, result, ranges):
    patient = record["patient"]
    treatments = record["treatments"]

    patient_column, result_column = st.columns([2, 3], gap="medium")

    with patient_column:
        label("Profil patient")
        st.markdown(f'<div class="profile">{html.escape(patient_profile(patient))}</div>', unsafe_allow_html=True)
        if patient.get("reference_date"):
            st.caption(f"Jour de référence : {patient['reference_date']}")
        biology = patient.get("biology", {})
        if biology:
            label(f"Biologie ({len(biology)} paramètres)")
            biology_rows, biology_classes = biology_table(biology, ranges)
            with st.container(key="zone-biology", border=False):
                _table(["Paramètre", "Valeur", "Interprétation", "Date"], biology_rows, row_classes=biology_classes)

    with result_column:
        to_modify = lines_to_modify(result)
        legend = " · en rouge : modification proposée" if to_modify else ""
        label(f"Prescription ({len(treatments)} lignes){legend}")
        with st.container(key="zone-prescription", border=False):
            prescription_rows, prescription_classes = prescription_table(treatments, to_modify)
            _table(["N°", "Médicament", "Posologie", "Début", "Fin"], prescription_rows,
                   row_classes=prescription_classes, short_columns=("N°", "Début", "Fin"))
        label("Avis pharmaceutique")
        with st.container(key="zone-opinion", border=False):
            _render_opinion(result, patient["id"])


# Interprétation affichée d'une valeur biologique
LOW, HIGH, NORMAL = "Bas", "Élevé", "Normal"


def patient_profile(patient):
    parts = []
    if patient.get("age") is not None:
        parts.append(f"{patient['age']} ans")
    for key, unit in (("weight_kg", "kg"), ("height_cm", "cm"), ("bmi_kg_m2", "kg/m² (IMC)"),
                      ("body_surface_area_m2", "m² (SC)")):
        if patient.get(key) is not None:
            parts.append(f"{patient[key]} {unit}")
    return " · ".join(parts) or "Âge, poids et taille non disponibles"


# Même interprétation que celle envoyée au LLM ; "" sans valeurs de référence
def interpretation(name, value, ranges):
    if name not in ranges or not isinstance(value, (int, float)):
        return ""
    return {"low": LOW, "high": HIGH}.get(lab_interpretation(name, value, ranges), NORMAL)


# (lignes, classes) du tableau de biologie : valeurs anormales en premier, en rouge
def biology_table(biology, ranges):
    measures = sorted(
        ((name, measure, interpretation(name, measure.get("value"), ranges)) for name, measure in biology.items()),
        key=lambda m: {LOW: 0, HIGH: 0, NORMAL: 1, "": 2}[m[2]],
    )
    rows = [[name, f"{measure.get('value', '')} {measure.get('unit') or ''}".strip(), state,
             (measure.get("test_datetime") or "")[:16]] for name, measure, state in measures]
    classes = ["abnormal" if state in (LOW, HIGH) else "" for _, _, state in measures]
    return rows, classes


# Numéros des lignes que le LLM propose de modifier
def lines_to_modify(result):
    return {n for point in (result or {}).get("points", []) for n in point.get("lines_to_modify", [])}


# (lignes, classes) du tableau de prescription : lignes à modifier en rouge
def prescription_table(treatments, to_modify):
    rows = [[f"L{number}", t.get("drug_label", ""), t.get("dosage_regimen", ""), t.get("start_date") or "",
             t.get("end_date") or ""] for number, t in enumerate(treatments, start=1)]
    classes = ["abnormal" if number in to_modify else "" for number in range(1, len(treatments) + 1)]
    return rows, classes


# Tableau HTML ajusté à la largeur ; short_columns : colonnes sans retour à la ligne
def _table(columns, rows, row_classes=(), short_columns=()):
    header = "".join(f"<th>{html.escape(c)}</th>" for c in columns)
    body = ""
    for number, row in enumerate(rows):
        css_class = row_classes[number] if number < len(row_classes) else ""
        cells = "".join(
            f'<td class="short">{html.escape(str(v))}</td>' if c in short_columns else f"<td>{html.escape(str(v))}</td>"
            for c, v in zip(columns, row)
        )
        body += f'<tr class="{css_class}">{cells}</tr>'
    st.markdown(f'<table class="data-table"><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>',
                unsafe_allow_html=True)


def _render_opinion(result, patient_id):
    if result is None:
        st.info("Dossier non analysé.")
        return
    if "error" in result:
        st.markdown(
            f'<div class="decision error">Échec de l’analyse ({result["date"]})</div>',
            unsafe_allow_html=True,
        )
        st.code(result["error"], language=None)
        return

    css_class = category(result["decision"])
    st.markdown(
        f'<div class="decision {css_class}">{html.escape(DECISION_LABELS[css_class])}</div>', unsafe_allow_html=True
    )
    if "points" in result:
        for number, point in enumerate(result["points"]):
            _point(point, key=f"point-{patient_id}-{number}")
    else:
        _legacy_opinion(result, patient_id)
    st.markdown(f'<div class="muted">Analysé le {result["date"]}</div>', unsafe_allow_html=True)


# Proposition de l'avis dans un cadre (CSS st-key-frame-<type>), avec ses sources en bas
def _point(point, key):
    type_ = point["type"]
    with st.container(key=f"frame-{type_}-{key}"):
        st.markdown(f'<p class="point {type_}">{html.escape(point["text"])}</p>', unsafe_allow_html=True)
        with st.container(horizontal=True, gap="small", vertical_alignment="center"):
            st.markdown('<span class="sources-title">Sources</span>', unsafe_allow_html=True)
            if not point["sources"]:
                st.markdown('<span class="llm-source">connaissances du modèle uniquement : aucune alerte ni référentiel</span>',
                            unsafe_allow_html=True)
            for number, source in enumerate(point["sources"]):
                if source["type"] == "alert":
                    _alert_link(source["text"], key=f"{key}-{number}")
                elif st.button(f"{source['source']}, p. {source['page']}", key=f"{key}-{number}", type="tertiary",
                               help=f"Ouvrir {source['source']} à la page {source['page']}"):
                    open_document(source["source"], source["page"])


# Reconnaît « reco_sfd.pdf, page 12 », « reco_sfd.pdf p. 12 » ou « reco_sfd.pdf »
SOURCE_PATTERN = re.compile(r"([^,;\[\]()]+?\.pdf)\s*(?:[,\-–:]?\s*(?:pages?|p\.?)\s*(\d+))?", re.IGNORECASE)


# Avis des analyses antérieures aux points typés : justification, sources PDF en texte, alertes KBS
def _legacy_opinion(result, patient_id):
    st.write(result["justification"])
    for number, source in enumerate(result.get("sources", [])):
        if found := SOURCE_PATTERN.search(str(source)):
            name, page = found.group(1).strip(), int(found.group(2) or 1)
            if st.button(source, key=f"source-{patient_id}-{number}", help=f"Ouvrir {name} à la page {page}"):
                open_document(name, page)
    with st.container(horizontal=True, gap="small"):
        for number, alert in enumerate(result.get("alerts", [])):
            _alert_link(alert, key=f"alert-{patient_id}-{number}")


@st.dialog("Alerte du KBS", width="large")
def _open_alert(alert):
    st.markdown(html_alert(alert), unsafe_allow_html=True)


# Le survol affiche l'alerte, le clic l'ouvre en détail
def _alert_link(alert, key):
    if st.button("Alerte KBS", key=key, type="tertiary", help=alert):
        _open_alert(alert)


# Niveaux du Thésaurus ANSM, du plus au moins grave
LEVELS = {"CI": "Contre-indication", "ASDEC": "Association déconseillée", "PE": "Précaution d'emploi",
          "APEC": "À prendre en compte"}
# Noms complets des niveaux tels qu'écrits dans le Thésaurus
FULL_LEVELS = {"CONTRE-INDICATION": "CI", "Association DECONSEILLEE": "ASDEC", "Précaution d'emploi": "PE",
               "A prendre en compte": "APEC"}
PHARMACOKINETIC = "Pharmacocinétique"
# « Interaction A + B (niveau) : ... » (Thésaurus) et « Interaction pharmacocinétique A + B : ... » (DDI-Predictor)
_CODE = "(?:CI|ASDEC|PE|APEC)"
THESAURUS_ALERT_PATTERN = re.compile(
    rf"^Interaction (.+?) \(({_CODE}(?: - {_CODE})*|{'|'.join(map(re.escape, FULL_LEVELS))})\) : (.*)$", re.DOTALL
)
DDI_ALERT_PATTERN = re.compile(r"^Interaction pharmacocinétique (.+?) : (.*)$", re.DOTALL)


# Texte du Thésaurus en HTML : un retour à la ligne par niveau et par tiret
def format_text(text):
    text = html.escape(text, quote=False)
    text = re.sub(
        r"\s*\b(Contre-indication|Association déconseillée|Précaution d'emploi|A prendre en compte)( avec)?\s*:",
        r"<br><b>\1\2 :</b>", text,
    )
    text = re.sub(r"\s+-\s+(?=\S)", "<br>• ", text)
    return text.removeprefix("<br>")


# « CI - ASDEC - APEC » -> ["CI", "ASDEC", "APEC"] ; noms complets -> leur code
def level_codes(level):
    if level in FULL_LEVELS:
        return [FULL_LEVELS[level]]
    return [code.strip() for code in level.split("-") if code.strip() in LEVELS]


# Alerte KBS en HTML : niveau et titre, message, conduite à tenir et lignes de prescription
def html_alert(alert):
    alert, _, prescription = alert.partition(" [Prescription: ")
    header = ""
    if found := THESAURUS_ALERT_PATTERN.match(alert):
        title, level, alert = found.groups()
        header = "".join(badge(LEVELS[c], c.lower()) for c in level_codes(level))
        header += f" <b>{html.escape(title)}</b>"
    elif found := DDI_ALERT_PATTERN.match(alert):
        title, alert = found.groups()
        header = f'{badge(PHARMACOKINETIC, "pk")} <b>{html.escape(title)}</b>'
    message, _, management = alert.partition(" Conduite à tenir : ")
    content = f'<div class="alert-header">{header}</div>' if header else ""
    content += format_text(message)
    if management:
        content += f'<div class="complement"><b>Conduite à tenir :</b><br>{format_text(management)}</div>'
    if prescription:
        content += f'<div class="prescription">Prescription : {html.escape(prescription.rstrip("]"))}</div>'
    return f'<div class="alert">{content}</div>'
