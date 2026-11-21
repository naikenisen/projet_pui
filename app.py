"""Streamlit interface: patient analysis, RAG documents, KBS rules and laboratory reference ranges.

Run from the project root:  streamlit run app.py
The light theme is defined in .streamlit/config.toml.
"""

import html
import json
import math
import os

# The default inference folder (dataset) is relative to the project root.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.front.analysis import analyse
from src.front.data import (
    PATIENTS_FOLDER,
    load_lab_ranges,
    load_patients,
    load_results,
    save_lab_ranges,
    save_results,
)
from src.front.display import (
    LEVELS,
    PHARMACOKINETIC,
    STATUS_COLORS,
    STATUS_LABELS,
    STATUS_ORDER,
    category,
    generic_rule_card,
    html_alert,
    html_table,
    inferred_type,
    level_codes,
    lines_to_modify,
    patient_profile,
    personalized_rule_card,
    prescription_table,
    read_source,
    biology_table,
    status,
)
from src.front.documents import (
    document_path,
    folder_documents,
    index_pdf,
    indexed_documents,
    page_count,
    render_page,
    save_pdf,
)
from kbs import (
    PERSONALIZED_RULES_FILE,
    add_personalized_rule,
    apply_rules,
    check_rules,
    load_generic_rules,
    load_personalized_rules,
    normalize,
    propose_rule,
    save_personalized_rules,
    unknown_variables,
)

HOSPITAL_NAME = "CHU Dijon Bourgogne"
SOFTWARE_NAME = "AI-assisted pharmaceutical analysis software"

st.set_page_config(page_title=f"{HOSPITAL_NAME} - Pharmaceutical analysis", layout="wide")


# ---------------------------------------------------------------------------
# Style: fixed application bar, dense business-software interface
# ---------------------------------------------------------------------------

BAR_HEIGHT = 52  # px

st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {{
    --blue: #0B4F8A; --blue-dark: #08355C; --blue-light: #E8F0F8;
    --text: #1A2433; --text-2: #4A5A6E; --text-3: #7A8899;
    --border: #D9E0E8; --background: #F3F5F8; --surface: #FFFFFF;
    --green: #1E7A46; --green-bg: #E9F5EE; --orange: #A85A00; --orange-bg: #FFF3E3;
    --red: #B42318; --red-bg: #FDECEB;
    --purple: #6B3FA0; --purple-bg: #F2ECFA; --blue-bg: #E8F0F8;
}}
html, body, [class*="css"], .stMarkdown, button, input, textarea, select {{
    font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif;
}}
html {{ font-size: 15.5px; }}
#MainMenu, footer, [data-testid="stDecoration"], [data-testid="stStatusWidget"] {{ display: none; }}

/* Fixed application bar at the top */
.app-bar {{
    position: fixed; top: 0; left: 0; right: 0; height: {BAR_HEIGHT}px; z-index: 1000001;
    background: var(--blue-dark); color: #FFFFFF; display: flex; align-items: center;
    justify-content: space-between; padding: 0 1.25rem; font-size: 0.98rem;
    border-bottom: 1px solid #052440;
}}
.app-bar .brand {{ display: flex; align-items: center; gap: 0.75rem; }}
.app-bar .hospital {{ font-weight: 700; letter-spacing: 0.02em; }}
.app-bar .separator {{ width: 1px; height: 22px; background: rgba(255,255,255,0.35); }}
.app-bar .software {{ color: rgba(255,255,255,0.85); font-weight: 400; }}
.app-bar .context {{ font-size: 0.85rem; color: rgba(255,255,255,0.75); display: flex; gap: 1.25rem; }}
.app-bar .context b {{ color: #FFFFFF; font-weight: 600; }}
[data-testid="stHeader"] {{ top: {BAR_HEIGHT}px; background: transparent; height: 2.5rem; }}
[data-testid="stSidebar"] {{ top: {BAR_HEIGHT}px; height: calc(100vh - {BAR_HEIGHT}px); }}
.block-container {{ padding-top: calc({BAR_HEIGHT}px + 1.5rem); padding-bottom: 2rem; max-width: 1500px; }}

/* Sidebar */
[data-testid="stSidebar"] {{ background: var(--surface); border-right: 1px solid var(--border); }}
[data-testid="stSidebar"] .stButton > button {{ justify-content: flex-start; text-align: left; }}
.section-title {{
    font-size: 0.75rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--text-3); margin: 1rem 0 0.4rem 0; padding-bottom: 0.3rem; border-bottom: 1px solid var(--border);
}}

/* Page header and indicator strip */
.page-title {{ font-size: 1.15rem; font-weight: 600; color: var(--text); margin: 0; }}
.page-subtitle {{ font-size: 0.82rem; color: var(--text-3); margin: 0.1rem 0 0 0; }}
.indicators {{
    display: flex; background: var(--surface); border: 1px solid var(--border); border-radius: 4px;
    margin: 0.9rem 0 0.6rem 0;
}}
.indicator {{ flex: 1; padding: 0.6rem 1rem; border-right: 1px solid var(--border); }}
.indicator:last-child {{ border-right: none; }}
.indicator .value {{ font-size: 1.35rem; font-weight: 600; color: var(--text); line-height: 1.2; }}
.indicator .name {{ font-size: 0.76rem; color: var(--text-3); text-transform: uppercase; letter-spacing: 0.05em; }}
.indicator.green .value {{ color: var(--green); }}
.indicator.orange .value {{ color: var(--orange); }}
.indicator.red .value {{ color: var(--red); }}
.indicator.purple .value {{ color: var(--purple); }}
.indicator.blue .value {{ color: var(--blue); }}
[data-testid="stMetric"] {{ padding: 0; }}
[data-testid="stMetricLabel"] p {{ color: var(--text-3); font-size: 0.75rem; }}
[data-testid="stMetricValue"] {{ font-size: 1.4rem; font-weight: 600; }}

/* Components: plain corners, thin borders */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {{
    border-radius: 4px; font-weight: 500; font-size: 0.85rem; min-height: 2.1rem; padding: 0.2rem 0.8rem;
}}
.stButton > button[kind="primary"], [data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"] {{
    background: var(--blue); border-color: var(--blue);
}}
.stTextInput input, .stNumberInput input, .stTextArea textarea, [data-baseweb="select"] > div {{ border-radius: 4px; }}
[data-testid="stExpander"] details {{
    background: var(--surface); border: 1px solid var(--border); border-radius: 4px;
}}
[data-testid="stExpander"] summary {{ padding: 0.55rem 0.9rem; font-size: 0.9rem; }}
[data-testid="stExpander"] summary:hover {{ background: var(--blue-light); }}
[data-testid="stExpander"] {{ margin-bottom: -0.6rem; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: 4px; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 0; border-bottom: 1px solid var(--border); }}
.stTabs [data-baseweb="tab"] {{ padding: 0.55rem 1.1rem; font-weight: 500; font-size: 0.88rem; }}
.stTabs [aria-selected="true"] {{ color: var(--blue); }}
[data-testid="stDataFrame"] {{ border: 1px solid var(--border); border-radius: 4px; }}

/* Record content */
.decision {{
    border-radius: 3px; padding: 0.55rem 0.8rem; font-weight: 600; font-size: 0.88rem;
    border-left: 3px solid; margin-bottom: 0.6rem; letter-spacing: 0.01em;
}}
.decision.validated {{ background: var(--green-bg); border-color: var(--green); color: var(--green); }}
.decision.intervention {{ background: var(--orange-bg); border-color: var(--orange); color: var(--orange); }}
.decision.verification {{ background: var(--purple-bg); border-color: var(--purple); color: var(--purple); }}
.decision.monitoring {{ background: var(--blue-bg); border-color: var(--blue); color: var(--blue); }}
.decision.error {{ background: var(--red-bg); border-color: var(--red); color: var(--red); }}
.label {{
    font-size: 0.75rem; font-weight: 600; color: var(--text-3); text-transform: uppercase;
    letter-spacing: 0.07em; margin: 0.8rem 0 0.3rem 0;
}}
.alert {{
    background: var(--orange-bg); border-left: 3px solid var(--orange); border-radius: 3px;
    padding: 0.4rem 0.7rem; margin-bottom: 0.35rem; font-size: 0.86rem; color: var(--text);
}}
.alert .alert-header {{ display: flex; align-items: center; flex-wrap: wrap; gap: 0.35rem; margin-bottom: 0.2rem; }}
.alert .complement {{ margin-top: 0.25rem; }}
.alert .prescription {{ margin-top: 0.25rem; font-size: 0.78rem; color: var(--text-2); }}

/* KBS rules */
.rule {{
    background: var(--surface); border: 1px solid var(--border); border-left: 4px solid var(--blue);
    border-radius: 4px; padding: 0.65rem 0.9rem; margin-bottom: 0.5rem; font-size: 0.86rem; color: var(--text);
}}
.rule.ci {{ border-left-color: var(--red); }}
.rule.asdec {{ border-left-color: var(--orange); }}
.rule.pe {{ border-left-color: #C9A100; }}
.rule.apec {{ border-left-color: #9AA6B2; }}
.rule.custom {{ border-left-color: var(--green); }}
.rule .header {{ display: flex; align-items: center; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.4rem; }}
.rule .title {{ font-weight: 600; font-size: 0.93rem; margin-right: 0.2rem; }}
.rule .block {{ margin: 0.3rem 0; line-height: 1.45; }}
.rule .field-label {{ font-weight: 600; color: var(--text-2); }}
.rule ul {{ margin: 0.15rem 0 0 0; padding-left: 1.2rem; }}
.rule li {{ margin: 0.05rem 0; }}
.rule details {{ margin-top: 0.35rem; }}
.rule summary {{ cursor: pointer; color: var(--text-3); font-size: 0.8rem; }}
.rule .footer {{ margin-top: 0.35rem; font-size: 0.75rem; color: var(--text-3); }}
.badge {{
    font-size: 0.68rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em;
    padding: 0.1rem 0.45rem; border-radius: 3px; white-space: nowrap;
}}
.badge.ci {{ background: var(--red-bg); color: var(--red); }}
.badge.asdec {{ background: var(--orange-bg); color: var(--orange); }}
.badge.pe {{ background: #FFF7D6; color: #7A5B00; }}
.badge.apec {{ background: #EEF1F4; color: var(--text-2); }}
.badge.pk {{ background: var(--blue-light); color: var(--blue); }}
.badge.custom {{ background: var(--green-bg); color: var(--green); }}
.chip {{
    display: inline-block; background: var(--background); border: 1px solid var(--border); border-radius: 3px;
    padding: 0 0.35rem; margin: 0.1rem 0.2rem 0.1rem 0; font-size: 0.8rem;
}}
.profile {{ color: var(--text); font-weight: 500; }}
.muted {{ color: var(--text-3); font-size: 0.76rem; margin-top: 0.6rem; }}

/* Pharmaceutical opinion: each point is a frame containing the proposal then its sources.
   The frames are st.container(key="frame-<type>-..."): Streamlit gives them the class st-key-<key>. */
[class*="st-key-frame-"] {{
    border: 1px solid var(--border); border-left: 3px solid var(--border); border-radius: 4px;
    background: var(--surface); padding: 0.5rem 0.75rem; margin: 0.35rem 0; gap: 0.35rem;
}}
[class*="st-key-frame-intervention"] {{ border: 1.5px solid var(--orange); background: var(--orange-bg); }}
[class*="st-key-frame-verification"] {{ border-left-color: var(--purple); }}
[class*="st-key-frame-monitoring"] {{ border-left-color: var(--blue); }}
[class*="st-key-frame-validation"] {{ border-left-color: var(--green); }}
/* Streamlit gives markdown blocks a negative bottom margin: without this fix, the sources overlap the text */
[class*="st-key-frame-"] [data-testid="stMarkdownContainer"] {{ margin-bottom: 0 !important; }}
[class*="st-key-frame-"] [data-testid="stMarkdownContainer"] p {{ margin: 0 !important; }}
.point {{ font-size: 0.9rem; color: var(--text); line-height: 1.45; }}
p.point.intervention, .point.intervention {{ font-weight: 700 !important; }}
/* Open record: areas whose height is computed from the screen, each scrolls on its own (the page does not).
   Available height ≈ 100vh minus application bar, tabs, navigation bar and labels. */
div.st-key-zone-biology, div.st-key-zone-prescription, div.st-key-zone-opinion {{
    overflow-y: auto !important; overflow-x: hidden !important; flex: none !important;
}}
div.st-key-zone-biology {{ height: calc(100vh - 390px) !important; min-height: 220px; }}
div.st-key-zone-prescription {{ height: calc((100vh - 360px) * 0.5) !important; min-height: 160px; }}
div.st-key-zone-opinion {{ height: calc((100vh - 360px) * 0.5) !important; min-height: 180px; }}
.st-key-zone-opinion > div {{ margin-bottom: 0.5rem; }}
.data-table th {{ position: sticky; top: 0; z-index: 1; }}

/* Patient list: aligned columns (grid), each row covered by an invisible button.
   The list scrolls on its own in a screen-high area (the page does not); the column header stays visible. */
div.st-key-patient-list {{ border: 1px solid var(--border); border-radius: 4px; background: var(--surface);
    margin-top: 0.4rem; overflow-y: auto !important; overflow-x: hidden !important; flex: none !important;
    max-height: calc(100vh - 400px) !important; min-height: 200px; }}
.st-key-patient-list > div:first-child {{ position: sticky; top: 0; z-index: 3; }}
.st-key-adjust-list {{ display: none; }}
.st-key-patient-list [data-testid="stMarkdownContainer"] {{ margin-bottom: 0 !important; }}
.patient-row {{
    display: grid; grid-template-columns: 9rem 13rem 6rem 10rem 6rem 1fr; align-items: center;
    padding: 0.5rem 0.9rem; border-bottom: 1px solid var(--border); font-size: 0.87rem; color: var(--text);
}}
.patient-row.header-row {{ background: var(--background); color: var(--text-3); font-size: 0.74rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.05em; padding: 0.4rem 0.9rem; }}
.patient-row .status {{ font-weight: 600; }}
.status.intervention {{ color: var(--orange); }} .status.verification {{ color: var(--purple); }}
.status.monitoring {{ color: var(--blue); }} .status.validated {{ color: var(--green); }}
.status.error {{ color: var(--red); }} .status.not_analysed {{ color: var(--text-3); }}
[class*="st-key-row-"] {{ position: relative; }}
[class*="st-key-row-"]:hover {{ background: var(--blue-light); cursor: pointer; }}
[class*="st-key-open-"] {{ position: absolute; inset: 0; z-index: 2; }}
[class*="st-key-open-"] .stButton, [class*="st-key-open-"] button {{
    width: 100%; height: 100%; opacity: 0; cursor: pointer;
}}
.sources-title {{ font-size: 0.74rem; font-weight: 600; color: var(--text-3); text-transform: uppercase;
    letter-spacing: 0.05em; }}
/* Source links: pastel blue text on a very light blue background */
.stButton > button[kind="tertiary"] {{
    min-height: 1.4rem; padding: 0.05rem 0.5rem; background: #F0F6FD; border: 1px solid #C6DDF5; border-radius: 10px;
}}
.stButton > button[kind="tertiary"], .stButton > button[kind="tertiary"] p {{
    color: #5B9BD5; font-size: 0.78rem; font-weight: 500;
}}
.stButton > button[kind="tertiary"]:hover {{ background: #E2EEFB; border-color: #9EC3EA; }}
.stButton > button[kind="tertiary"]:hover p {{ color: #3E7FC1; }}
.llm-source {{
    display: inline-block; font-size: 0.78rem; color: var(--text-2); background: #EEF1F4;
    border: 1px solid var(--border); border-radius: 10px; padding: 0.05rem 0.5rem;
}}

/* Laboratory and prescription tables: all text visible, no horizontal scrolling */
.data-table {{ width: 100%; border-collapse: collapse; font-size: 0.8rem; background: var(--surface);
    border: 1px solid var(--border); table-layout: auto; }}
.data-table th {{ text-align: left; font-weight: 600; color: var(--text-2); background: var(--background);
    padding: 0.3rem 0.45rem; border-bottom: 1px solid var(--border); }}
.data-table td {{ padding: 0.28rem 0.45rem; border-bottom: 1px solid var(--border); vertical-align: top;
    white-space: normal; overflow-wrap: anywhere; }}
.data-table td.short {{ white-space: nowrap; }}
.data-table tr.abnormal td {{ color: var(--red); background: var(--red-bg); font-weight: 500; }}
</style>
""",
    unsafe_allow_html=True,
)


def section_title(text):
    st.markdown(f'<div class="section-title">{html.escape(text)}</div>', unsafe_allow_html=True)


def label(text):
    st.markdown(f'<div class="label">{html.escape(text)}</div>', unsafe_allow_html=True)


def show_alert(alert):
    st.markdown(html_alert(alert), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Document viewer
# ---------------------------------------------------------------------------

@st.dialog("Document viewer", width="large")
def open_document(name, page=1):
    path = document_path(name)
    if not os.path.exists(path):
        st.error(f"The document “{name}” cannot be found in the RAG documents.")
        return

    total = page_count(path)
    st.markdown(f"**{name}**")
    page_column, download_column = st.columns([1, 1], vertical_alignment="bottom")
    page = page_column.number_input(
        f"Page (of {total})", min_value=1, max_value=total, value=min(page, total), key=f"page-{name}-{page}"
    )
    with open(path, "rb") as file:
        download_column.download_button(
            "Download PDF", file.read(), file_name=name, mime="application/pdf",
            use_container_width=True,
        )
    st.image(render_page(path, page))


def source_button(source, key):
    """Shows a button that opens the source if it is a PDF of the RAG documents, otherwise plain text."""
    document = read_source(source)
    if document is None:
        st.markdown(f"- {source}")
        return
    name, page = document
    if st.button(source, key=key, help=f"Open {name} at page {page}"):
        open_document(name, page)


@st.dialog("KBS alert", width="large")
def open_alert(alert):
    show_alert(alert)


def alert_link(alert, key):
    """“KBS alert” link: hovering shows the alert, clicking opens it in detail."""
    if st.button("KBS alert", key=key, type="tertiary", help=alert):
        open_alert(alert)


def show_point(point, key, decision_category=""):
    """One proposal of the pharmaceutical opinion in a frame, with its sources at the bottom of the same frame.

    Intervention: bold text, orange frame. KBS alerts are only visible through these links (no separate list).
    """
    type_ = point.get("type") or inferred_type(point["text"], decision_category)
    with st.container(key=f"frame-{type_}-{key}"):
        st.markdown(f'<p class="point {type_}">{html.escape(point["text"])}</p>', unsafe_allow_html=True)
        with st.container(horizontal=True, gap="small", vertical_alignment="center"):
            st.markdown('<span class="sources-title">Sources</span>', unsafe_allow_html=True)
            if not point["sources"]:
                st.markdown('<span class="llm-source">model knowledge only: no alert or guideline</span>',
                            unsafe_allow_html=True)
            show_source_links(point["sources"], key)


def show_source_links(sources, key):
    for number, source in enumerate(sources):
        if source["type"] == "alert":
            alert_link(source["text"], key=f"{key}-{number}")
        elif st.button(f"{source['source']}, p. {source['page']}", key=f"{key}-{number}", type="tertiary",
                       help=f"Open {source['source']} at page {source['page']}"):
            open_document(source["source"], source["page"])


# ---------------------------------------------------------------------------
# Sidebar: patient base and RAG documents
# ---------------------------------------------------------------------------

with st.sidebar:
    section_title("Patient base")
    folder = st.text_input(
        "Inference folder", value=PATIENTS_FOLDER, key="patients_folder",
        help="Folder containing one JSON file per patient (path relative to the project root, or absolute).",
    ).strip()
    if os.path.isdir(folder):
        try:
            patients = load_patients(folder)
        except Exception as error:
            patients = []
            st.error(f"Unable to read the patient records: {error}")
    else:
        patients = []
        st.error(f"The folder “{folder}” does not exist.")
    st.metric("Patient records", len(patients))

    section_title("RAG documents")
    try:
        indexed = indexed_documents()
    except Exception as error:
        indexed = {}
        st.error(f"Unable to read the vector database: {error}")

    if indexed:
        st.caption("Indexed guidelines. Click to view.")
        for name, passage_count in indexed.items():
            if st.button(f"{name}  ·  {passage_count} passages", key=f"doc-{name}", use_container_width=True):
                open_document(name)
    else:
        st.info("No indexed guideline.")

    not_indexed = [name for name in folder_documents() if name not in indexed]
    if not_indexed:
        st.caption("Documents waiting to be indexed")
        for name in not_indexed:
            name_column, button_column = st.columns([3, 2], vertical_alignment="center")
            name_column.markdown(f"`{name}`")
            if button_column.button("Index", key=f"index-{name}", use_container_width=True):
                with st.spinner(f"Indexing {name}..."):
                    count = index_pdf(document_path(name))
                st.toast(f"{name}: {count} passages indexed")
                st.rerun()

    section_title("Add a guideline")
    with st.form("add_document", clear_on_submit=True, border=False):
        files = st.file_uploader(
            "PDF documents", type="pdf", accept_multiple_files=True, label_visibility="collapsed",
            help="The document is saved in the RAG documents, then indexed.",
        )
        submitted = st.form_submit_button("Index the documents", use_container_width=True)
    if submitted and files:
        for file in files:
            with st.spinner(f"Indexing {file.name}..."):
                try:
                    count = index_pdf(save_pdf(file.name, file.getvalue()))
                    st.toast(f"{file.name}: {count} passages indexed")
                except Exception as error:
                    st.error(f"{file.name}: {error}")
        st.rerun()


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

results = load_results()
statuses = {r["patient"]["id"]: status(results.get(r["patient"]["id"]))[0] for r in patients}
counts = {code: list(statuses.values()).count(code) for code in STATUS_LABELS}
# Records analysed by “Run the analysis”: never analysed or failed
to_analyse = [r for r in patients if statuses[r["patient"]["id"]] in ("not_analysed", "error")]

st.markdown(
    f"""
<div class="app-bar">
  <div class="brand">
    <span class="hospital">{html.escape(HOSPITAL_NAME)}</span>
    <span class="separator"></span>
    <span class="software">{html.escape(SOFTWARE_NAME)}</span>
  </div>
  <div class="context">
    <span>Folder <b>{html.escape(folder)}</b></span>
    <span><b>{len(patients)}</b> records</span>
    <span><b>{len(indexed)}</b> indexed guidelines</span>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# Open record: header and indicators hidden so that the record fits on the screen without scrolling
record_view = bool(st.session_state.get("open_patient"))
run = rerun_all = False
if not record_view:
    title_column, action_column, rerun_column = st.columns([2, 1, 1], vertical_alignment="center")
    title_column.markdown(
        '<p class="page-title">Prescription analysis</p>'
        '<p class="page-subtitle">Knowledge-Based System (KBS), reference guidelines and language model</p>',
        unsafe_allow_html=True,
    )
    run = action_column.button(
        f"Run the analysis ({len(to_analyse)} records)",
        type="primary",
        disabled=not to_analyse,
        use_container_width=True,
        help="Analyses only the records not yet analysed or in error",
    )
    rerun_all = rerun_column.button(
        "Re-run the analysis of all patients",
        disabled=not patients,
        use_container_width=True,
        help="Analyses all the records again, including those already analysed",
    )

    st.markdown(
        f"""
    <div class="indicators">
      <div class="indicator"><div class="value">{len(patients)}</div><div class="name">Records</div></div>
      <div class="indicator"><div class="value">{len(patients) - counts["not_analysed"]}</div><div class="name">Analysed</div></div>
      <div class="indicator orange"><div class="value">{counts["intervention"]}</div><div class="name">Interventions</div></div>
      <div class="indicator purple"><div class="value">{counts["verification"]}</div><div class="name">Verifications</div></div>
      <div class="indicator blue"><div class="value">{counts["monitoring"]}</div><div class="name">Monitoring</div></div>
      <div class="indicator green"><div class="value">{counts["validated"]}</div><div class="name">Validated</div></div>
      <div class="indicator red"><div class="value">{counts["error"]}</div><div class="name">Errors</div></div>
      <div class="indicator"><div class="value">{counts["not_analysed"]}</div><div class="name">Not analysed</div></div>
    </div>
    """,
        unsafe_allow_html=True,
    )

if run or rerun_all:
    selection = patients if rerun_all else to_analyse
    bar = st.progress(0.0, text="Analysis in progress...")
    for number, record in enumerate(selection, start=1):
        patient_id = record["patient"]["id"]
        bar.progress((number - 1) / len(selection), text=f"Analysing record {patient_id} ({number}/{len(selection)})")
        results[patient_id] = analyse(record)
        save_results(results)  # saved as we go
    bar.empty()
    st.rerun()

results_tab, rules_tab, biology_tab = st.tabs(
    ["Analysis results", "KBS rules", "Laboratory reference ranges"]
)


# --- Results tab --------------------------------------------------------------

def table(columns, rows, row_classes=(), short_columns=()):
    st.markdown(html_table(columns, rows, row_classes, short_columns), unsafe_allow_html=True)


def show_patient(record, result, ranges):
    """Laboratory values on the left; prescription at the top right, pharmaceutical opinion below.

    Each area has a height computed from the screen height (CSS .st-key-zone-*) and scrolls on its own: the page
    does not scroll, the pharmacist moves from one record to the next without scrolling. No horizontal scrolling.
    """
    patient = record["patient"]
    patient_id = patient["id"]
    treatments = record["treatments"]

    patient_column, result_column = st.columns([2, 3], gap="medium")

    with patient_column:
        label("Patient profile")
        st.markdown(f'<div class="profile">{html.escape(patient_profile(patient))}</div>', unsafe_allow_html=True)
        if patient.get("reference_date"):
            st.caption(f"Reference date: {patient['reference_date']}")
        biology = patient.get("biology", {})
        if biology:
            label(f"Laboratory values ({len(biology)} parameters)")
            biology_rows, biology_classes = biology_table(biology, ranges)
            with st.container(key="zone-biology", border=False):
                table(["Parameter", "Value", "Interpretation", "Date"], biology_rows, row_classes=biology_classes)

    with result_column:
        # Lines the LLM proposes to modify (“intervention” points): in red
        to_modify = lines_to_modify(result)
        legend = " · in red: change proposed" if to_modify else ""
        label(f"Prescription ({len(treatments)} lines){legend}")
        with st.container(key="zone-prescription", border=False):
            prescription_rows, prescription_classes = prescription_table(treatments, to_modify)
            table(["No.", "Drug", "Dosage regimen", "Start", "End"], prescription_rows,
                  row_classes=prescription_classes, short_columns=("No.", "Start", "End"))
        label("Pharmaceutical opinion")
        with st.container(key="zone-opinion", border=False):
            show_opinion(result, patient_id)


def show_opinion(result, patient_id):
    """Decision and points of the pharmaceutical opinion."""
    if result is None:
        st.info("Record not analysed.")
        return
    if "error" in result:
        st.markdown(
            f'<div class="decision error">Analysis failed ({result["date"]})</div>',
            unsafe_allow_html=True,
        )
        st.code(result["error"], language=None)
        return

    css_class = category(result["decision"])
    st.markdown(
        f'<div class="decision {css_class}">{html.escape(result["decision"])}</div>', unsafe_allow_html=True
    )
    if "points" in result:
        for number, point in enumerate(result["points"]):
            show_point(point, key=f"point-{patient_id}-{number}", decision_category=css_class)
    else:  # analysis made before points were introduced: justification in one paragraph
        st.write(result["justification"])
        for number, source in enumerate(result.get("sources", [])):
            if read_source(source):
                source_button(source, key=f"source-{patient_id}-{number}")
        with st.container(horizontal=True, gap="small"):
            for number, alert in enumerate(result.get("alerts", [])):
                alert_link(alert, key=f"alert-{patient_id}-{number}")
    st.markdown(f'<div class="muted">Analysed on {result["date"]}</div>', unsafe_allow_html=True)


# Widgets that are not displayed lose their value: keep the filter and the search when a patient is open
for key in ("filter", "search"):
    if key in st.session_state:
        st.session_state[key] = st.session_state[key]
st.session_state.setdefault("open_patient", None)

FILTERS = {
    "all": ("All", None),
    "intervention": ("Interventions", {"intervention"}),
    "verification": ("Verifications", {"verification"}),
    "monitoring": ("Monitoring", {"monitoring"}),
    "validated": ("Validated", {"validated"}),
    "others": ("Not analysed / errors", {"not_analysed", "error"}),
}


def filter_label(code):
    name, codes = FILTERS[code]
    return name if codes is None else f"{name} ({sum(counts[c] for c in codes)})"


def open_patient(patient_id):
    st.session_state.open_patient = patient_id


def close_patient():
    st.session_state.open_patient = None


def show_list(shown):
    """Patient list, one clickable row per patient, in a scrolling area (CSS .st-key-patient-list)."""
    if not shown:
        st.caption("No record matches the selection.")
        return

    with st.container(key="patient-list", gap=None):
        st.markdown(
            '<div class="patient-row header-row"><span>Patient</span><span>Status</span><span>Age</span>'
            '<span>Treatment lines</span><span>Alerts</span><span>Analysed on</span></div>',
            unsafe_allow_html=True,
        )
        for record in shown:
            patient = record["patient"]
            patient_id = patient["id"]
            result = results.get(patient_id) or {}
            code, state = status(results.get(patient_id))
            cells = [
                f"<b>{html.escape(patient_id)}</b>",
                f'<span class="status {code}">{html.escape(state)}</span>',
                f"{patient['age']} years" if patient.get("age") is not None else "—",
                str(len(record["treatments"])),
                str(len(result.get("alerts", []))) if result.get("alerts") else "—",
                html.escape(result.get("date", "")) or "—",
            ]
            # HTML row (aligned columns) covered by an invisible button that opens the record
            with st.container(key=f"row-{patient_id}", gap=None):
                st.markdown('<div class="patient-row">' + "".join(f"<span>{c}</span>" for c in cells) + "</div>",
                            unsafe_allow_html=True)
                st.button(f"Open record {patient_id}", key=f"open-{patient_id}", on_click=open_patient,
                          args=(patient_id,), use_container_width=True)

    st.caption(f"{len(shown)} record{'s' if len(shown) > 1 else ''} shown")
    with st.container(key="adjust-list"):
        components.html(LIST_HEIGHT_SCRIPT, height=0)


# The height of the header (titles and filters on one or two lines) depends on the screen width: this script
# (in an invisible frame) gives the list all the remaining height, so that the page itself does not scroll.
# Without it, the height is the one from the CSS (.st-key-patient-list).
LIST_HEIGHT_SCRIPT = """
<script>
const page = window.parent.document;
function adjust() {
    const list = page.querySelector(".st-key-patient-list");
    const main = page.querySelector('[data-testid="stMain"]');
    if (!list || !main) return;
    const top = list.getBoundingClientRect().top + main.scrollTop;
    const bottom = 75;  // “N records shown” caption and bottom margin of the page
    const height = Math.max(200, window.parent.innerHeight - top - bottom);
    if (list.style.maxHeight !== height + "px") list.style.setProperty("max-height", height + "px", "important");
}
adjust();
setInterval(adjust, 250);
</script>
"""


def show_open_record(shown):
    """Full-width record, with a way back to the list and navigation to the previous or next patient."""
    patient_id = st.session_state.open_patient
    records = shown if any(r["patient"]["id"] == patient_id for r in shown) else sorted_patients
    position = next(i for i, r in enumerate(records) if r["patient"]["id"] == patient_id)
    record = records[position]
    code, state = status(results.get(patient_id))

    back_column, title_column, rerun_column, previous_column, position_column, next_column = st.columns(
        [1.3, 3, 1.6, 1, 0.7, 1], vertical_alignment="center"
    )
    back_column.button("← Patient list", on_click=close_patient, use_container_width=True)
    title_column.markdown(
        f'<span class="page-title">Patient {html.escape(patient_id)}</span> &nbsp; '
        f'<span style="color: {STATUS_COLORS[code]}; font-weight: 600">{html.escape(state)}</span>',
        unsafe_allow_html=True,
    )
    if rerun_column.button("Re-run the analysis", key=f"analyse-{patient_id}", use_container_width=True,
                           help="Analyses this patient again"):
        with st.spinner(f"Analysing record {patient_id}..."):
            results[patient_id] = analyse(record)
            save_results(results)
        st.rerun()
    if position > 0:
        previous_column.button("‹ Previous", on_click=open_patient, args=(records[position - 1]["patient"]["id"],),
                               use_container_width=True)
    position_column.markdown(f'<div class="muted" style="text-align:center; margin:0">{position + 1} / {len(records)}</div>',
                             unsafe_allow_html=True)
    if position < len(records) - 1:
        next_column.button("Next ›", on_click=open_patient, args=(records[position + 1]["patient"]["id"],),
                           use_container_width=True)
    show_patient(record, results.get(patient_id), load_lab_ranges())


sorted_patients = sorted(patients, key=lambda r: STATUS_ORDER[statuses[r["patient"]["id"]]])

with results_tab:
    selected_filter = st.session_state.get("filter", "all")
    search = st.session_state.get("search", "").strip().lower()
    shown = [
        r for r in sorted_patients
        if (FILTERS[selected_filter][1] is None or statuses[r["patient"]["id"]] in FILTERS[selected_filter][1])
        and (
            not search
            or search in r["patient"]["id"].lower()
            or any(search in str(t.get("drug_label", "")).lower() for t in r["treatments"])
        )
    ]

    if st.session_state.open_patient in statuses:
        show_open_record(shown)
    else:
        st.session_state.open_patient = None
        filter_column, search_column = st.columns([3, 1], vertical_alignment="bottom")
        filter_column.radio("Filter", list(FILTERS), format_func=filter_label, horizontal=True,
                            label_visibility="collapsed", key="filter")
        search_column.text_input("Search", placeholder="Identifier or drug",
                                 label_visibility="collapsed", key="search")
        show_list(shown)


# --- Rules tab ------------------------------------------------------------------

def lines(text, commas=False):
    """One value per line (and per comma if commas=True: laboratory names may contain commas)."""
    if commas:
        text = text.replace(",", "\n")
    return [line.strip() for line in text.splitlines() if line.strip()]


RULES_PER_PAGE = 25

# Laboratory parameters of the loaded records, with their unit: the LLM must use their exact name
biology_parameters = {}
for r in patients:
    for key, measure in r["patient"].get("biology", {}).items():
        biology_parameters.setdefault(key, measure.get("unit") or "")

with rules_tab:
    personalized_rules = load_personalized_rules()
    generic_rules = load_generic_rules()
    st.caption(
        "A rule of the Knowledge-Based System (KBS) is triggered when all its criteria are met. **Generic rules** "
        "come from the ANSM Thesaurus of drug interactions and from DDI-Predictor; **personalized rules** are "
        "specific to the hospital and can be drafted by the assistant from a natural-language request."
    )
    personalized_tab, generic_tab, test_tab = st.tabs([
        f"Personalized rules ({len(personalized_rules)})",
        f"Generic rules ({len(generic_rules)})",
        "Check on a record",
    ])

    with personalized_tab:
        label("Add a rule with the assistant")
        with st.form("rule_request", border=False):
            request = st.text_area(
                "Request", label_visibility="collapsed", height=90,
                placeholder="E.g.: Alert if metformin is prescribed with an eGFR below 30 mL/min: "
                            "contraindication, stop metformin.",
            )
            propose = st.form_submit_button("Propose a rule", type="primary")
        if propose and request.strip():
            with st.spinner("The model is drafting the rule..."):
                try:
                    st.session_state["proposed_rule"] = propose_rule(request.strip(), biology_parameters)
                except Exception as error:
                    st.session_state.pop("proposed_rule", None)
                    st.error(f"The model could not draft a rule: {error}")

        proposed = st.session_state.get("proposed_rule")
        if proposed:
            label("Proposed rule: check before saving")
            st.markdown(personalized_rule_card(proposed, biology_parameters), unsafe_allow_html=True)
            for name in unknown_variables(proposed, biology_parameters):
                st.warning(f"The variable “{name}” does not exist in the records: this condition will always be false.")
            triggers = sum(1 for r in patients if apply_rules(r, [proposed]))
            st.caption(f"Would be triggered for {triggers} record(s) out of {len(patients)} in the folder “{folder}”.")
            with st.expander("Rule JSON"):
                st.json(proposed)
            save_column, cancel_column, _ = st.columns([1, 1, 3])
            if save_column.button("Save the rule", type="primary", use_container_width=True):
                errors = add_personalized_rule(proposed)
                if errors:
                    for error in errors:
                        st.error(error)
                else:
                    del st.session_state["proposed_rule"]
                    st.toast("Personalized rule saved.")
                    st.rerun()
            if cancel_column.button("Cancel", use_container_width=True):
                del st.session_state["proposed_rule"]
                st.rerun()

        label(f"Personalized rules ({len(personalized_rules)})")
        if not personalized_rules:
            st.caption("No personalized rule.")
        for number, rule in enumerate(personalized_rules):
            text_column, delete_column = st.columns([7, 1])
            text_column.markdown(personalized_rule_card(rule, biology_parameters), unsafe_allow_html=True)
            if delete_column.button("Delete", key=f"delete-rule-{number}", use_container_width=True):
                save_personalized_rules(personalized_rules[:number] + personalized_rules[number + 1:])
                st.rerun()

        with st.expander("Manual rule entry"):
            st.caption(
                "A condition is written `variable operator value` (operators `>=` `<=` `>` `<` `==` `!=`). Available "
                "variables: patient characteristics (`age`, `weight_kg`, `height_cm`, `bmi_kg_m2`, "
                "`body_surface_area_m2`), laboratory values with the exact parameter name (`Créatinine (sang)`, "
                "`DFG estimé (CKD-EPI)`...) and, for the drugs named in the rule, the product strength "
                "(`dose_apixaban`), the dose in mg per day (`daily_dose_daptomycine`) and in mg/kg per day "
                "(`dose_per_kg_daptomycine`). A drug is considered prescribed if its name appears in the label of a "
                "prescription line (ignoring case and accents)."
            )
            with st.form("add_rule", clear_on_submit=False, border=False):
                alert = st.text_area(
                    "Alert message (required)",
                    placeholder="E.g.: Metformin contraindicated in severe renal failure",
                )
                column_a, column_b = st.columns(2)
                drugs = column_a.text_area(
                    "Drugs involved (INN, one per line)", placeholder="apixaban",
                    help="The rule only applies if all these drugs are prescribed.",
                )
                conditions = column_b.text_area(
                    "Required conditions (one per line)", placeholder="DFG estimé (CKD-EPI) < 30"
                )
                any_of = column_a.text_area("Optional criteria (one per line)", placeholder="age >= 80")
                minimum = column_b.number_input("Minimum number of optional criteria met", min_value=0, value=0)
                add = st.form_submit_button("Save the rule", type="primary")

            if add:
                new_rule = {"alert": alert.strip()}
                if lines(drugs, commas=True):
                    new_rule["drugs"] = lines(drugs, commas=True)
                if lines(conditions):
                    new_rule["conditions"] = lines(conditions)
                if lines(any_of):
                    new_rule["any_of"] = lines(any_of)
                    new_rule["minimum"] = int(minimum)
                errors = add_personalized_rule(new_rule)
                if errors:
                    for error in errors:
                        st.error(error)
                else:
                    st.success("Rule saved.")
                    st.rerun()

        with st.expander(f"Advanced editing of {os.path.relpath(PERSONALIZED_RULES_FILE)}"):
            text = st.text_area(
                "JSON content", json.dumps(personalized_rules, ensure_ascii=False, indent=2), height=350,
                key="rules_json",
            )
            if st.button("Save changes"):
                try:
                    errors = save_personalized_rules(json.loads(text))
                except json.JSONDecodeError as error:
                    errors = [f"Invalid JSON: {error}"]
                if errors:
                    for error in errors:
                        st.error(error)
                else:
                    st.success("Rules saved.")
                    st.rerun()

    with generic_tab:
        st.caption(
            "Rules extracted from the reference documents of src/kbs/KBS_Docs/ (src/kbs/generic_rules.json), read-only. "
            "A Thesaurus class (e.g. oral anticoagulants) is searched through the list of its INNs."
        )
        rule_search_column, level_column, source_column = st.columns([3, 3, 2], vertical_alignment="bottom")
        rule_search = normalize(rule_search_column.text_input(
            "Search", placeholder="INN, class or keyword (e.g. apixaban, hyperkaliémie)", key="rule_search"
        ).strip())
        chosen_levels = level_column.multiselect(
            "Level", list(LEVELS.values()) + [PHARMACOKINETIC], placeholder="All levels"
        )
        chosen_source = source_column.selectbox("Source", ["All", "ANSM Thesaurus", "DDI-Predictor"])

        def level_selected(rule):
            if not chosen_levels:
                return True
            labels = [LEVELS[c] for c in level_codes(rule)] or [PHARMACOKINETIC]
            return any(l in chosen_levels for l in labels)

        filtered = [
            r for r in generic_rules
            if (chosen_source == "All" or r.get("source", "").startswith(chosen_source))
            and level_selected(r)
            and (
                not rule_search
                or rule_search in normalize(r["alert"])
                or rule_search in json.dumps(r.get("drugs", []), ensure_ascii=False)
            )
        ]
        rule_page_count = max(1, math.ceil(len(filtered) / RULES_PER_PAGE))
        rule_page_column, rule_info_column = st.columns([1, 4], vertical_alignment="bottom")
        rule_page = rule_page_column.number_input(
            f"Page (of {rule_page_count})", min_value=1, max_value=rule_page_count, value=1, key="rules_page"
        )
        rule_start = (rule_page - 1) * RULES_PER_PAGE
        if filtered:
            rule_info_column.caption(
                f"Rules {rule_start + 1} to {min(rule_start + RULES_PER_PAGE, len(filtered))} of {len(filtered)}"
            )
        else:
            rule_info_column.caption("No rule matches the search.")
        st.markdown(
            "".join(generic_rule_card(r) for r in filtered[rule_start:rule_start + RULES_PER_PAGE]),
            unsafe_allow_html=True,
        )

    with test_tab:
        if patients:
            choice = st.selectbox("Patient", [r["patient"]["id"] for r in patients], key="rules_test")
            record = next(r for r in patients if r["patient"]["id"] == choice)
            try:
                alerts = check_rules(record)
            except Exception as error:
                alerts = None
                st.error(f"Error in the rules: {error}")
            if alerts:
                for alert in alerts:
                    show_alert(alert)
            elif alerts is not None:
                st.success("No alert for this record.")
        else:
            st.caption("No patient record loaded.")


# --- Laboratory tab ---------------------------------------------------------------

with biology_tab:
    st.caption(
        "Reference ranges used to flag abnormal laboratory values for the LLM and the guideline search. "
        "The key must exactly match the parameter name in the patients' laboratory values."
    )
    parameters = {}
    for r in patients:
        for key, measure in r["patient"].get("biology", {}).items():
            parameters.setdefault(key, {"Key": key, "Unit": measure.get("unit") or "", "Number of patients": 0})
            parameters[key]["Number of patients"] += 1
    if parameters:
        with st.expander(f"Parameters present in the folder “{folder}” ({len(parameters)})"):
            st.dataframe(
                pd.DataFrame(parameters.values()).sort_values("Number of patients", ascending=False),
                hide_index=True, use_container_width=True,
            )

    ranges_table = pd.DataFrame(
        [{"key": key, **reference} for key, reference in load_lab_ranges().items()],
        columns=["key", "label", "unit", "min", "max"],
    )
    edited = st.data_editor(
        ranges_table,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        column_config={
            "key": st.column_config.TextColumn("Key", required=True),
            "label": st.column_config.TextColumn("Label"),
            "unit": st.column_config.TextColumn("Unit"),
            "min": st.column_config.NumberColumn("Lower bound", required=True),
            "max": st.column_config.NumberColumn("Upper bound", required=True),
        },
        key="ranges_editor",
    )
    if st.button("Save the reference ranges", type="primary"):
        edited = edited.dropna(how="all")
        rows = edited.astype(object).where(edited.notna(), None).to_dict("records")
        errors = save_lab_ranges(rows)
        if errors:
            for error in errors:
                st.error(error)
        else:
            st.success("Reference ranges saved.")
