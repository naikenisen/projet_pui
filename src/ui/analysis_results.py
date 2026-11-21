"""“Résultats d'analyse” page: indicators and analysis button, patient list, open patient record.

The analysis is done by main.py: the “Lancer l'analyse” button runs `main.py --remaining`, the “Relancer l'analyse”
button of a record calls main.analyse. Results are stored in src/inference_results.json.
Streamlit re-runs the page from the top after each interaction: ResultsState is rebuilt at each run from the files,
while st.session_state keeps what must survive between runs (open patient, filter, search).
"""

import html
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field

import streamlit as st
import streamlit.components.v1 as components

import main
from generation import (
    DECISION_INTERVENTION,
    DECISION_MONITORING,
    DECISION_VALIDATED,
    DECISION_VERIFICATION,
    lab_interpretation,
    read_lab_ranges,
)
from src.ui.RAG_documents import open_document
from src.ui.common import PATIENTS_FOLDER, badge, label, load_patients, read_asset


def render_page():
    state = build_state()
    st.session_state.setdefault("open_patient", None)

    shown = filtered_patients(state)
    if st.session_state.open_patient in state.statuses:
        # Open record: indicators hidden so that the record fits on the screen without scrolling
        _render_record(state, shown)
    else:
        st.session_state.open_patient = None
        _render_overview(state)
        _render_filters(state)
        _render_list(state, shown)


# ---------------------------------------------------------------------------
# Status of a record
# ---------------------------------------------------------------------------

# Category of each decision written by generation.py
CATEGORIES = {DECISION_INTERVENTION: "intervention", DECISION_VERIFICATION: "verification",
              DECISION_MONITORING: "monitoring", DECISION_VALIDATED: "validated"}
# Decision shown in the opinion, by category (the LLM writes it in English, see generation.py)
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
# Records requiring an action are listed first
STATUS_ORDER = {"intervention": 0, "verification": 1, "monitoring": 2, "error": 3, "not_analysed": 4, "validated": 5}
STATUS_COLORS = {"intervention": "#A85A00", "verification": "#6B3FA0", "monitoring": "#0B4F8A",
                 "error": "#B42318", "not_analysed": "#7A8899", "validated": "#1E7A46"}


def category(decision):
    """Category code of a decision: validated, monitoring, verification or intervention.

    An unknown decision is shown as an intervention, so that the record is checked first."""
    return CATEGORIES.get(decision, "intervention")


def status(result):
    """Returns (code, label) of the status of a record."""
    if result is None:
        code = "not_analysed"
    elif "error" in result:
        code = "error"
    else:
        code = category(result["decision"])
    return code, STATUS_LABELS[code]


# ---------------------------------------------------------------------------
# Data of the page
# ---------------------------------------------------------------------------

@dataclass
class ResultsState:
    patients: list  # patient records of dataset/
    results: dict = field(default_factory=dict)  # {patient id: analysis result}
    statuses: dict = field(default_factory=dict)  # {patient id: status code}
    counts: dict = field(default_factory=dict)  # {status code: number of records}
    sorted_patients: list = field(default_factory=list)  # records needing an action first

    @property
    def to_analyse(self):
        """Records analysed by “Lancer l'analyse”: never analysed or failed."""
        return [r for r in self.patients if self.statuses[r["patient"]["id"]] in ("not_analysed", "error")]


def build_state():
    """Reads the patient records of dataset/ and their inference results."""
    patients = load_patients()
    results = main.load_results()
    statuses = {r["patient"]["id"]: status(results.get(r["patient"]["id"]))[0] for r in patients}
    counts = {code: list(statuses.values()).count(code) for code in STATUS_LABELS}
    sorted_patients = sorted(patients, key=lambda r: STATUS_ORDER[statuses[r["patient"]["id"]]])
    return ResultsState(patients, results, statuses, counts, sorted_patients)


def open_patient(patient_id):
    st.session_state.open_patient = patient_id


def close_patient():
    st.session_state.open_patient = None


# ---------------------------------------------------------------------------
# Analysis by main.py
# ---------------------------------------------------------------------------

def run_main():
    """Runs `main.py --remaining` on dataset/; yields the id of each analysed patient.

    `main.py --all` (re-analysis of all the patients) is run by hand, not from the interface."""
    script = os.path.abspath(main.__file__)
    command = [sys.executable, "-u", script, "--remaining", "--folder", PATIENTS_FOLDER]
    other_lines = []
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                          cwd=os.path.dirname(script)) as process:
        for line in process.stdout:
            if line.startswith("Patient "):
                yield line.split()[1]
            else:
                other_lines.append(line.rstrip())
    if process.returncode:
        raise RuntimeError("\n".join(other_lines[-5:]) or f"main.py exited with code {process.returncode}")


def analyse_and_save(results, record):
    """Analyses one record again (main.analyse), stores the result in results and saves the results file."""
    results[record["patient"]["id"]] = main.analyse(record)
    main.save_results(results)


# ---------------------------------------------------------------------------
# Top of the page: title, analysis button and indicator strip
# ---------------------------------------------------------------------------

def _render_overview(state):
    title_column, action_column = st.columns([3, 1], vertical_alignment="center")
    title_column.markdown(
        '<p class="page-title">Analyse des prescriptions</p>'
        '<p class="page-subtitle">Knowledge-Based System (KBS), référentiels et modèle de langage</p>',
        unsafe_allow_html=True,
    )
    run = action_column.button(
        f"Lancer l'analyse ({len(state.to_analyse)} dossiers)" if state.to_analyse
        else "Tous les patients ont été analysés",
        type="primary",
        disabled=not state.to_analyse,
        use_container_width=True,
        help="Analyse uniquement les dossiers non analysés ou en erreur",
    )
    _indicators(state)

    if run:
        _run_analysis(state)


def _indicators(state):
    counts = state.counts
    st.markdown(
        f"""
    <div class="indicators">
      <div class="indicator"><div class="value">{len(state.patients)}</div><div class="name">Dossiers</div></div>
      <div class="indicator"><div class="value">{len(state.patients) - counts["not_analysed"]}</div><div class="name">Analysés</div></div>
      <div class="indicator orange"><div class="value">{counts["intervention"]}</div><div class="name">Interventions</div></div>
      <div class="indicator purple"><div class="value">{counts["verification"]}</div><div class="name">Vérifications</div></div>
      <div class="indicator blue"><div class="value">{counts["monitoring"]}</div><div class="name">Surveillances</div></div>
      <div class="indicator green"><div class="value">{counts["validated"]}</div><div class="name">Validés</div></div>
      <div class="indicator red"><div class="value">{counts["error"]}</div><div class="name">Erreurs</div></div>
      <div class="indicator"><div class="value">{counts["not_analysed"]}</div><div class="name">Non analysés</div></div>
    </div>
    """,
        unsafe_allow_html=True,
    )


def _run_analysis(state):
    """Runs main.py --remaining with a progress bar; main.py saves each result as it goes."""
    total = len(state.to_analyse)
    bar = st.progress(0.0, text="Analyse en cours...")
    try:
        for number, patient_id in enumerate(run_main(), start=1):
            bar.progress(min(number / total, 1.0), text=f"Dossier {patient_id} analysé ({number}/{total})")
    except Exception as error:
        bar.empty()
        st.error(f"Échec de main.py : {error}")
        return
    bar.empty()
    st.rerun()


# ---------------------------------------------------------------------------
# Patient list: status filters, search, one clickable row per patient
# ---------------------------------------------------------------------------

# Filter code: (label, status codes shown; None = all)
FILTERS = {
    "all": ("Tous", None),
    "intervention": ("Interventions", {"intervention"}),
    "verification": ("Vérifications", {"verification"}),
    "monitoring": ("Surveillances", {"monitoring"}),
    "validated": ("Validés", {"validated"}),
    "others": ("Non analysés / erreurs", {"not_analysed", "error"}),
}

# The height of the header (titles and filters on one or two lines) depends on the screen width: this script
# (in an invisible frame) gives the list all the remaining height, so that the page itself does not scroll.
# Without it, the height is the one from the CSS (.st-key-patient-list).
LIST_HEIGHT_SCRIPT = read_asset("list_height.html")


def filtered_patients(state):
    """Records matching the selected filter and the search (identifier or drug), records needing action first."""
    selected_filter = st.session_state.get("filter", "all")
    search = st.session_state.get("search", "").strip().lower()
    return [
        r for r in state.sorted_patients
        if (FILTERS[selected_filter][1] is None or state.statuses[r["patient"]["id"]] in FILTERS[selected_filter][1])
        and (
            not search
            or search in r["patient"]["id"].lower()
            or any(search in str(t.get("drug_label", "")).lower() for t in r["treatments"])
        )
    ]


def _render_filters(state):
    def filter_label(code):
        name, codes = FILTERS[code]
        return name if codes is None else f"{name} ({sum(state.counts[c] for c in codes)})"

    filter_column, search_column = st.columns([3, 1], vertical_alignment="bottom")
    filter_column.radio("Filtre", list(FILTERS), format_func=filter_label, horizontal=True,
                        label_visibility="collapsed", key="filter")
    search_column.text_input("Recherche", placeholder="Identifiant ou médicament",
                             label_visibility="collapsed", key="search")


def _render_list(state, shown):
    """Patient list, one clickable row per patient, in a scrolling area (CSS .st-key-patient-list)."""
    if not shown:
        st.caption("Aucun dossier ne correspond à la sélection.")
        return

    with st.container(key="patient-list", gap=None):
        st.markdown(
            '<div class="patient-row header-row"><span>Patient</span><span>Statut</span><span>Âge</span>'
            '<span>Lignes de traitement</span><span>Alertes</span><span>Analysé le</span></div>',
            unsafe_allow_html=True,
        )
        for record in shown:
            _patient_row(state, record)

    st.caption(f"{len(shown)} dossier{'s' if len(shown) > 1 else ''} affiché{'s' if len(shown) > 1 else ''}")
    with st.container(key="adjust-list"):
        components.html(LIST_HEIGHT_SCRIPT, height=0)


def _patient_row(state, record):
    patient = record["patient"]
    patient_id = patient["id"]
    result = state.results.get(patient_id) or {}
    code, state_label = status(state.results.get(patient_id))
    cells = [
        f"<b>{html.escape(patient_id)}</b>",
        f'<span class="status {code}">{html.escape(state_label)}</span>',
        f"{patient['age']} ans" if patient.get("age") is not None else "—",
        str(len(record["treatments"])),
        str(len(result.get("alerts", []))) if result.get("alerts") else "—",
        html.escape(result.get("date", "")) or "—",
    ]
    # HTML row (aligned columns) covered by an invisible button that opens the record
    with st.container(key=f"row-{patient_id}", gap=None):
        st.markdown('<div class="patient-row">' + "".join(f"<span>{c}</span>" for c in cells) + "</div>",
                    unsafe_allow_html=True)
        st.button(f"Ouvrir le dossier {patient_id}", key=f"open-{patient_id}", on_click=open_patient,
                  args=(patient_id,), use_container_width=True)


# ---------------------------------------------------------------------------
# Open record: navigation bar, laboratory values, prescription and pharmaceutical opinion
# ---------------------------------------------------------------------------

def _render_record(state, shown):
    """Full-width record, with a way back to the list and navigation to the previous or next patient."""
    patient_id = st.session_state.open_patient
    records = shown if any(r["patient"]["id"] == patient_id for r in shown) else state.sorted_patients
    position = next(i for i, r in enumerate(records) if r["patient"]["id"] == patient_id)
    _navigation_bar(state, records, position)
    _patient_record(records[position], state.results.get(patient_id), read_lab_ranges())


def _navigation_bar(state, records, position):
    record = records[position]
    patient_id = record["patient"]["id"]
    code, state_label = status(state.results.get(patient_id))

    back_column, title_column, rerun_column, previous_column, position_column, next_column = st.columns(
        [1.3, 3, 1.6, 1, 0.7, 1], vertical_alignment="center"
    )
    back_column.button("← Liste des patients", on_click=close_patient, use_container_width=True)
    title_column.markdown(
        f'<span class="page-title">Patient {html.escape(patient_id)}</span> &nbsp; '
        f'<span style="color: {STATUS_COLORS[code]}; font-weight: 600">{html.escape(state_label)}</span>',
        unsafe_allow_html=True,
    )
    if rerun_column.button("Relancer l'analyse", key=f"analyse-{patient_id}", use_container_width=True,
                           help="Analyse à nouveau ce patient"):
        with st.spinner(f"Analyse du dossier {patient_id} en cours..."):
            analyse_and_save(state.results, record)
        st.rerun()
    if position > 0:
        previous_column.button("‹ Précédent", on_click=open_patient, args=(records[position - 1]["patient"]["id"],),
                               use_container_width=True)
    position_column.markdown(f'<div class="muted" style="text-align:center; margin:0">{position + 1} / {len(records)}</div>',
                             unsafe_allow_html=True)
    if position < len(records) - 1:
        next_column.button("Suivant ›", on_click=open_patient, args=(records[position + 1]["patient"]["id"],),
                           use_container_width=True)


def _patient_record(record, result, ranges):
    """Laboratory values on the left; prescription at the top right, pharmaceutical opinion below.

    Each area has a height computed from the screen height (CSS .st-key-zone-*) and scrolls on its own: the page
    does not scroll, the pharmacist moves from one record to the next without scrolling. No horizontal scrolling.
    """
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
        # Lines the LLM proposes to modify (“intervention” points): in red
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


# Interpretation of a laboratory value, as displayed
LOW, HIGH, NORMAL = "Bas", "Élevé", "Normal"


def patient_profile(patient):
    """Readable summary of the patient characteristics (missing fields are omitted)."""
    parts = []
    if patient.get("age") is not None:
        parts.append(f"{patient['age']} ans")
    for key, unit in (("weight_kg", "kg"), ("height_cm", "cm"), ("bmi_kg_m2", "kg/m² (IMC)"),
                      ("body_surface_area_m2", "m² (SC)")):
        if patient.get(key) is not None:
            parts.append(f"{patient[key]} {unit}")
    return " · ".join(parts) or "Âge, poids et taille non disponibles"


def interpretation(name, value, ranges):
    """Same interpretation as the one sent to the LLM (generation.lab_interpretation); "" without reference range."""
    if name not in ranges or not isinstance(value, (int, float)):
        return ""
    return {"low": LOW, "high": HIGH}.get(lab_interpretation(name, value, ranges), NORMAL)


def biology_table(biology, ranges):
    """(rows, classes) of the laboratory table: abnormal values first, in red."""
    measures = sorted(
        ((name, measure, interpretation(name, measure.get("value"), ranges)) for name, measure in biology.items()),
        key=lambda m: {LOW: 0, HIGH: 0, NORMAL: 1, "": 2}[m[2]],
    )
    rows = [[name, f"{measure.get('value', '')} {measure.get('unit') or ''}".strip(), state,
             (measure.get("test_datetime") or "")[:16]] for name, measure, state in measures]
    classes = ["abnormal" if state in (LOW, HIGH) else "" for _, _, state in measures]
    return rows, classes


def lines_to_modify(result):
    """Numbers of the prescription lines the LLM proposes to modify (“intervention” points)."""
    return {n for point in (result or {}).get("points", []) for n in point.get("lines_to_modify", [])}


def prescription_table(treatments, to_modify):
    """(rows, classes) of the prescription table: lines to modify in red."""
    rows = [[f"L{number}", t.get("drug_label", ""), t.get("dosage_regimen", ""), t.get("start_date") or "",
             t.get("end_date") or ""] for number, t in enumerate(treatments, start=1)]
    classes = ["abnormal" if number in to_modify else "" for number in range(1, len(treatments) + 1)]
    return rows, classes


def _table(columns, rows, row_classes=(), short_columns=()):
    """HTML table that fits the width (line wrapping, no scrolling).

    row_classes: CSS class of each row ("abnormal" to colour it red).
    short_columns: columns that must never wrap (identifier, value, dates).
    """
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


# ---------------------------------------------------------------------------
# Pharmaceutical opinion: decision, then one frame per point with its sources
# ---------------------------------------------------------------------------

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
    else:  # analysis made before points were introduced: justification in one paragraph
        _legacy_opinion(result, patient_id)
    st.markdown(f'<div class="muted">Analysé le {result["date"]}</div>', unsafe_allow_html=True)


def _point(point, key):
    """One proposal of the pharmaceutical opinion in a frame, with its sources at the bottom of the same frame.

    Intervention: bold text, orange frame. KBS alerts are only visible through these links (no separate list).
    The frames are st.container(key="frame-<type>-..."), styled by the CSS classes st-key-frame-<type>.
    """
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


# Recognises for instance "reco_sfd.pdf, page 12", "reco_sfd.pdf p. 12" or "reco_sfd.pdf"
SOURCE_PATTERN = re.compile(r"([^,;\[\]()]+?\.pdf)\s*(?:[,\-–:]?\s*(?:pages?|p\.?)\s*(\d+))?", re.IGNORECASE)


def _legacy_opinion(result, patient_id):
    """Opinion of an analysis made before typed points: justification, PDF sources as text, KBS alerts."""
    st.write(result["justification"])
    for number, source in enumerate(result.get("sources", [])):
        if found := SOURCE_PATTERN.search(str(source)):
            name, page = found.group(1).strip(), int(found.group(2) or 1)
            if st.button(source, key=f"source-{patient_id}-{number}", help=f"Ouvrir {name} à la page {page}"):
                open_document(name, page)
    with st.container(horizontal=True, gap="small"):
        for number, alert in enumerate(result.get("alerts", [])):
            _alert_link(alert, key=f"alert-{patient_id}-{number}")


# ---------------------------------------------------------------------------
# KBS alerts: link, dialog and HTML (badges of the ANSM Thesaurus levels)
# ---------------------------------------------------------------------------

@st.dialog("Alerte du KBS", width="large")
def _open_alert(alert):
    st.markdown(html_alert(alert), unsafe_allow_html=True)


def _alert_link(alert, key):
    """“Alerte KBS” link: hovering shows the alert, clicking opens it in detail."""
    if st.button("Alerte KBS", key=key, type="tertiary", help=alert):
        _open_alert(alert)


# ANSM Thesaurus levels: code, displayed label, from most to least severe
LEVELS = {"CI": "Contre-indication", "ASDEC": "Association déconseillée", "PE": "Précaution d'emploi",
          "APEC": "À prendre en compte"}
# Full level names as written in the Thesaurus (French)
FULL_LEVELS = {"CONTRE-INDICATION": "CI", "Association DECONSEILLEE": "ASDEC", "Précaution d'emploi": "PE",
               "A prendre en compte": "APEC"}
PHARMACOKINETIC = "Pharmacocinétique"
# “Interaction A + B (level) : ...” (Thesaurus) and “Interaction pharmacocinétique A + B : ...” (DDI-Predictor),
# as written in src/kbs/generic_rules.json
_CODE = "(?:CI|ASDEC|PE|APEC)"
THESAURUS_ALERT_PATTERN = re.compile(
    rf"^Interaction (.+?) \(({_CODE}(?: - {_CODE})*|{'|'.join(map(re.escape, FULL_LEVELS))})\) : (.*)$", re.DOTALL
)
DDI_ALERT_PATTERN = re.compile(r"^Interaction pharmacocinétique (.+?) : (.*)$", re.DOTALL)


def format_text(text):
    """Thesaurus text (in French) as HTML: a line break per level (“Contre-indication avec :”) and per dash."""
    text = html.escape(text, quote=False)
    text = re.sub(
        r"\s*\b(Contre-indication|Association déconseillée|Précaution d'emploi|A prendre en compte)( avec)?\s*:",
        r"<br><b>\1\2 :</b>", text,
    )
    text = re.sub(r"\s+-\s+(?=\S)", "<br>• ", text)
    return text.removeprefix("<br>")


def level_codes(level):
    """“CI - ASDEC - APEC” -> ["CI", "ASDEC", "APEC"]; full Thesaurus names -> their code."""
    if level in FULL_LEVELS:
        return [FULL_LEVELS[level]]
    return [code.strip() for code in level.split("-") if code.strip() in LEVELS]


def html_alert(alert):
    """KBS alert: level and title, message, recommended action and prescription lines."""
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
