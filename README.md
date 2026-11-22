# AI-assisted pharmaceutical analysis software

Pipeline that analyses hospital prescriptions by combining a Knowledge-Based System (KBS), a retrieval module over
clinical guidelines (RAG) and a large language model (LLM).

**Online demo:** https://projetpui.streamlit.app/

To run locally, a  `.env` file at the project root including you API key for OpenRouter is required :
```
OPENROUTER_API_KEY=your_key
```

---

## BACKEND

### Figure 1. Overall architecture

![Figure 1](paper/figures_en/figure_1.png)

| Script | Role |
|---|---|
| `indexing.py` | Indexes the guidelines (PDF) in a vector database (ChromaDB) |
| `retrieval.py` | Searches the vector database for the passages useful for a patient |
| `kbs.py` | Knowledge-Based System (KBS): applies the deterministic rules for a patient|
| `generation.py` | Analyses a patient with the LLM along with retrieved passages and KBS results |
| `main.py` | Launch retrieval then KBS then generation|


### Run the pipeline from a terminal

```bash
python3 main.py --remaining   # launch the analysis of patients without a result
python3 main.py --all         # launch the analysis of all patients (the results file is overwritten)
```

Patients are in the folder `dataset` and each result is saved in `inference_results.json`

To add a document from `ressources/rag/RAG_Docs/` to the vector database, run :

```bash
python3 indexing.py
```

### Run individual part of the pipeline from a terminal
Prints the most relevant passages for the patient, with their PDF and page.
```bash
python3 retrieval.py --folder dataset --patient-id 100133744
```

Prints the detected alerts, or `No alert`.
```bash
python3 kbs.py --folder dataset --patient-id 100133744
```

Prints the decision and the justification (without KBS alerts and RAG)
```bash
python3 generation.py --folder dataset --patient-id 100133744
```

## Details of the pipeline

### Figure 2. (RAG)

![Figure 2](paper/figures_en/figure_2.png)

### Figure 3. Knowledge-Based System (KBS)

![Figure 3](paper/figures_en/figure_3.png)

### Figure 4. Generation (LLM)

![Figure 4](paper/figures_en/figure_4.png)

---

## Frontend: Streamlit interface

### Usage

```bash
streamlit run app.py
```

The interface always works on the patients of `dataset/`; `full_dataset/` is analysed from the command line only (`python3 main.py --remaining --folder full_dataset`).
The “Lancer l'analyse” button runs `main.py --remaining` (patients without a result); results are read from `inference_results.json`. Re-analysing all the patients (`main.py --all`) is done from the command line only.

![List of the analysed records: indicators, filters, pharmaceutical opinion, KBS alerts and cited sources](paper/interface_screenshot_1.png)

*Analysis results: for each patient, profile, laboratory values, prescription, pharmaceutical opinion, KBS alerts and clickable sources.*

![Viewing a cited source: the PDF opens directly at the referenced page](paper/interface_screenshot_2.png)

*Viewing a source: clicking a reference opens the PDF at the page cited by the model.*

The interface is in French and has three pages. On the “Résultats d'analyse” page, the indicators and the “Lancer l'analyse” button are above the patient list. On the “Règles du KBS” page, the pharmacist has the LLM assistant draft a personalized rule from a natural-language request, checks it before saving, and can delete the saved rules. The “Documents du RAG” page lists the indexed guidelines (click to view), indexes the PDFs added to `ressources/rag/RAG_Docs/` and uploads new ones. Any other change (generic rules, manual editing of `ressources/kbs/personalized_rules.json`, laboratory reference ranges in `ressources/lab_reference_ranges.json`) is made directly in the files, outside the interface.

### Code

`app.py` holds what is common to every page (configuration, style, application bar) and declares the pages with
`st.navigation`. The interface code is in `ui/`, with one `page_*.py` module per page of the application (the
patient record opened from the list included): each page loads its own data and calls the backend scripts of the
project root for any processing (analysis, rules, indexing).

```
app.py                         entry point: page configuration, application bar, list of the pages
inference_results.json         analysis results saved by main.py
ui/
├── page_analysis_results.py   “Résultats d'analyse” page: indicators, “Lancer l'analyse” (main.py --remaining),
│                              patient list
├── page_patient_result.py     record opened from the list: laboratory values, prescription, pharmaceutical
│                              opinion and KBS alerts
├── page_kbs_rules.py          “Règles du KBS” page: LLM assistant (kbs.propose_rule), proposed rule, rule list
├── page_rag_documents.py      “Documents du RAG” page: indexed guidelines, indexing (indexing.index_pdf), upload;
│                              PDF viewer also opened from the sources of the opinion
├── common.py                  shared by the pages: page frame, patient records of dataset/, small helpers
└── style.css                  style of the whole interface
```
To have the LLM draft a personalized rule (it is displayed, then saved after confirmation):

```bash
python3 kbs.py --folder dataset --new-rule "Alert if metformin with an eGFR < 30 mL/min"
```
---

## Data and other files

| File | Role |
|---|---|
| `dataset/` | Inference folder (80 patients): one JSON file per patient (`<id>.json`), with laboratory values and treatments |
| `full_dataset/` | Full inference folder (1919 patients, not versioned), same format |
| `ressources/kbs/generic_rules.json` | KBS rules from the ANSM Thesaurus of drug interactions and from DDI-Predictor |
| `ressources/kbs/personalized_rules.json` | Hospital-specific KBS rules (e.g. apixaban dose, daptomycin 10 mg/kg) |
| `ressources/kbs/KBS_Docs/` | Reference documents from which the generic KBS rules were extracted (ANSM Thesaurus, DDI-Predictor) |
| `ressources/rag/RAG_Docs/` | Guidelines (PDF) used by the RAG |
| `ressources/rag/chroma_db/` | Vector database created by `indexing.py` |
| `ressources/lab_reference_ranges.json` | Reference ranges of laboratory values, used by `retrieval.py` and `generation.py` |
| `preprocessing/` | Builds the patient JSON files from the anonymised CSV extractions (`preprocessing/original_dataset/`, not versioned) |
| `paper/` | Article, presentation and figures (`paper/figures_en/`) |

### Preprocessing

Rebuilds the patient files from the CSV files of `preprocessing/original_dataset/`:

```bash
python3 preprocessing/preprocessing.py
```

Writes one JSON file per patient to `preprocessing/dataset/`. `python3 preprocessing/analysis.py` prints the number of patients kept at each filtering step.





