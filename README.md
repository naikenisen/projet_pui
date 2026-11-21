# AI-assisted pharmaceutical analysis software

Pipeline that analyses hospital prescriptions by combining a Knowledge-Based System (KBS), a retrieval module over
clinical guidelines (RAG) and a large language model (LLM).

## Installation

```bash
pip install -r requirements.txt
```

Create a `.env` file at the project root:

```
OPENROUTER_API_KEY=your_key
```

All commands below are run from the project root.

---

## Backend: analysis pipeline

### Architecture

![Figure 1](paper/figures_en/figure_1.png)

**Figure 1. Overall architecture of the AI-assisted pharmaceutical analysis pipeline.**
Guidelines (PDF) are split into passages and indexed in a vector database (ChromaDB).
For each patient, the orchestration module queries in parallel the retrieval module, which extracts the relevant passages, and the Knowledge-Based System (KBS), which produces deterministic alerts; both outputs are passed to the language model, which gives the final decision.

The indexing must be run before the first analysis (see [Indexing](#indexing)).

### Scripts

| Script | Role |
|---|---|
| `main.py` | Analyses every patient of a folder with the KBS, the RAG and the LLM |
| `indexing.py` | Indexes the guidelines (PDF) in a vector database (ChromaDB) |
| `retrieval.py` | Searches the vector database for the passages useful for a patient |
| `kbs.py` | Knowledge-Based System (KBS): applies the deterministic rules; has the LLM draft a new rule |
| `generation.py` | Analyses a patient with the LLM |

### Full pipeline

```bash
python3 main.py --folder dataset
```

Use `--folder full_dataset` to analyse the full dataset.

Prints for each patient: its identifier, the decision (`PATIENT VALIDATED`, `MONITORING PROPOSED`, `VERIFICATION PROPOSED` or `PHARMACEUTICAL INTERVENTION PROPOSED`), the justification and the sources cited by the model.

### Indexing

Run once, then each time a PDF is added to `src/rag/RAG_Docs/`:

```bash
python3 indexing.py
```

Prints the number of passages indexed per PDF and creates the `src/rag/chroma_db/` folder.

### Retrieval (RAG)

![Figure 2](paper/figures_en/figure_2.png)

**Figure 2. Retrieval of the relevant guideline excerpts for a patient (Retrieval-Augmented Generation).**
Laboratory parameters outside their reference ranges are converted into textual descriptors and added to the patient profile. A query is built for each prescription line (drug label, dosage regimen, patient profile), encoded with Qwen3-Embedding-8B, then submitted to a 3-nearest-neighbour search (cosine distance). The retrieved passages are deduplicated and sorted by distance, and the 8 closest form the context passed to the language model.

```bash
python3 retrieval.py --folder dataset --patient-id 100133744
```

Prints the most relevant passages for the patient, with their PDF and page.

### Knowledge-Based System (KBS)

![Figure 3](paper/figures_en/figure_3.png)

**Figure 3. Operation of the Knowledge-Based System (KBS) made of deterministic rules.**
Patient variables (characteristics, laboratory values, dose of each drug) are extracted from the record. Each rule is triggered if (i) all the drugs it targets are prescribed, (ii) all its mandatory conditions are met and (iii) a minimum number of optional criteria is satisfied. The messages of the triggered rules form the list of alerts passed to the language model.

```bash
python3 kbs.py --folder dataset --patient-id 100133744
```

Prints the detected alerts, or `No alert`.

The rules are in `src/kbs/generic_rules.json` (ANSM Thesaurus, DDI-Predictor) and `src/kbs/personalized_rules.json` (hospital rules). The texts of the generic rules are kept in French, as in the source documents. A rule is triggered if all its fields are satisfied:

| Field | Meaning |
|---|---|
| `drugs` | all these drugs (INN) are prescribed, on different lines: the name is searched in the label of each prescription line, ignoring case and accents. An item can be a list of INNs, any one of which is enough (Thesaurus class) |
| `conditions` | all these conditions are true |
| `any_of` + `minimum` | at least `minimum` of these conditions are true |
| `alert` | message displayed when the rule is triggered |

Only `alert` is required. A condition is written `variable operator value`, for example `age >= 80`, with the operators `>=`, `<=`, `>`, `<`, `==`, `!=`.
The usable variables are the patient fields (`age`, `weight_kg`, `height_cm`, `bmi_kg_m2`, `body_surface_area_m2`), the laboratory values with the exact parameter name (`Créatinine (sang)`, `DFG estimé (CKD-EPI)`...) and, for the drugs named in the rule, the product strength (`dose_apixaban`), the prescribed dose in mg per day (`daily_dose_daptomycine`) and in mg/kg per day (`dose_per_kg_daptomycine`).

To have the LLM draft a personalized rule (it is displayed, then saved after confirmation):

```bash
python3 kbs.py --folder dataset --new-rule "Alert if metformin with an eGFR < 30 mL/min"
```

### Generation (LLM)

![Figure 4](paper/figures_en/figure_4.png)

**Figure 4. Generation of the pharmaceutical opinion by the language model.**
The message submitted to the model (Qwen3.6-35B-A3B, temperature 0, constrained JSON output) combines the patient record (lines numbered L1, L2..., status of each line on the reference date, daily dose computed by the code, abnormal laboratory values flagged, drugs present on several lines with their total dose), the KBS alerts (numbered [A1], [A2]...) and the retrieved guideline excerpts (numbered [R1], [R2]...). The system prompt defines the clinical pharmacist role, the analysis criteria and the ranking of the alerts (contraindications first). The response is a JSON object containing the decision (patient validated, monitoring proposed, verification proposed or pharmaceutical intervention proposed) and 1 to 4 typed points (intervention, verification, monitoring, validation) written as proposals (“We propose…”, “We suggest…”), each with the identifiers of the alerts and excerpts it relies on. Identifiers that match no provided alert or excerpt are ignored. The displayed decision is that of the most severe point; for an intervention, the LLM also gives the lines to modify.

```bash
python3 generation.py --folder dataset --patient-id 100133744
```

Prints the decision and the justification (without KBS alerts or guideline excerpts: use `main.py` for the full pipeline).

---

## Frontend: Streamlit interface

### Usage

```bash
streamlit run app.py
```

The inference folder (`dataset` by default, or `full_dataset`) is chosen in the sidebar.
Analysis results are saved in `src/results/inference_results.json`.

![List of the analysed records: indicators, filters, pharmaceutical opinion, KBS alerts and cited sources](paper/interface_screenshot_1.png)

*Analysis results: for each patient, profile, laboratory values, prescription, pharmaceutical opinion, KBS alerts and clickable sources.*

![Viewing a cited source: the PDF opens directly at the referenced page](paper/interface_screenshot_2.png)

*Viewing a source: clicking a reference opens the PDF at the page cited by the model.*

The interface is in French. In the “Règles du KBS” tab, the pharmacist has the LLM assistant draft a personalized rule from a natural-language request, checks it before saving, and can delete the saved rules. Any other change (generic rules, manual editing of `src/kbs/personalized_rules.json`, laboratory reference ranges in `src/biology/lab_reference_ranges.json`) is made directly in the files, outside the interface.

### Code

`app.py` only assembles the screen. The interface code is in `src/front/`, split by responsibility so that each
area of the screen can be changed without reading the rest. The backend scripts are only called through
`src/front/services/`.

```
app.py                    entry point: page configuration, sidebar, overview, tabs
src/results/
└── inference_results.json  analysis results saved by the interface
src/front/
├── theme.py              page configuration, style injection, application bar
├── state.py              AppState (data shared by the views during one run) and patient navigation
├── assets/
│   ├── style.css         style of the whole interface
│   └── list_height.html  script giving the patient list the remaining screen height
├── services/             data access and backend calls, no Streamlit
│   ├── data.py           patient files, laboratory reference ranges, inference results
│   ├── analysis.py       analysis of one patient (KBS + RAG + LLM) and saving of the result
│   └── documents.py      RAG documents: list, indexing, page rendering
├── rendering/            HTML generation, no Streamlit
│   ├── opinion.py        record status, decision category, sources
│   ├── record.py         patient profile, laboratory and prescription tables
│   ├── alerts.py         KBS alerts and Thesaurus level badges
│   └── rules.py          personalized KBS rule card
├── components/           reusable Streamlit widgets
│   ├── widgets.py        titles, labels, tables, alerts, error messages
│   └── dialogs.py        document viewer and KBS alert dialogs, source links
└── views/                one module per area of the screen
    ├── sidebar.py        patient folder, RAG documents, guideline upload
    ├── overview.py       title, analysis buttons, indicators
    ├── results/          “Résultats d’analyse” tab
    │   ├── tab.py
    │   ├── patient_list.py
    │   ├── patient_record.py
    │   └── opinion.py
    └── rules.py          “Règles du KBS” tab: LLM assistant, proposed rule, rule list with deletion
```

`services/` and `rendering/` do not import Streamlit: they can be tested without running the interface.

---

## Data and other files

| File | Role |
|---|---|
| `dataset/` | Inference folder (80 patients): one JSON file per patient (`<id>.json`), with laboratory values and treatments |
| `full_dataset/` | Full inference folder (1919 patients, not versioned), same format |
| `src/kbs/generic_rules.json` | KBS rules from the ANSM Thesaurus of drug interactions and from DDI-Predictor |
| `src/kbs/personalized_rules.json` | Hospital-specific KBS rules (e.g. apixaban dose, daptomycin 10 mg/kg) |
| `src/kbs/KBS_Docs/` | Reference documents from which the generic KBS rules were extracted (ANSM Thesaurus, DDI-Predictor) |
| `src/rag/RAG_Docs/` | Guidelines (PDF) used by the RAG |
| `src/rag/chroma_db/` | Vector database created by `indexing.py` |
| `src/biology/lab_reference_ranges.json` | Reference ranges of laboratory values, used by `retrieval.py` and `generation.py` |
| `preprocessing/` | Builds the patient JSON files from the anonymised CSV extractions (`preprocessing/original_dataset/`, not versioned) |
| `paper/` | Article, presentation and figures (`paper/figures_en/`) |

### Preprocessing

Rebuilds the patient files from the CSV files of `preprocessing/original_dataset/`:

```bash
python3 preprocessing/preprocessing.py
```

Writes one JSON file per patient to `preprocessing/dataset/`. `python3 preprocessing/analysis.py` prints the number of patients kept at each filtering step.
