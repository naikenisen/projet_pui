# AI-assisted pharmaceutical analysis software

## Installation

```bash
pip install -r requirements.txt
```

Create a `.env` file at the project root:

```
OPENROUTER_API_KEY=your_key
```

All commands below are run from the project root.

## Files

| File | Role |
|---|---|
| `dataset/` | Inference folder (80 patients), loaded by default in the interface: one JSON file per patient (`<id>.json`), with laboratory values and treatments |
| `full_dataset/` | Full inference folder (1919 patients, not versioned), same format |
| `app.py` | Streamlit interface (analysis, RAG documents, KBS rules, laboratory reference ranges) |
| `main.py` | Analyses every patient with the LLM, the RAG and the KBS |
| `generation.py` | Analyses a patient with the LLM |
| `kbs.py` | Knowledge-Based System (KBS): applies the deterministic rules; has the LLM draft a new rule |
| `indexing.py` | Indexes the PDFs of `src/rag/RAG_Docs/` in ChromaDB |
| `retrieval.py` | Searches ChromaDB for the passages useful for a patient |
| `src/front/` | Modules of the Streamlit interface (JSON files, documents, analysis, HTML formatting) |
| `src/front/inference_results.json` | Analysis results saved by the interface |
| `src/kbs/generic_rules.json` | KBS rules from the ANSM Thesaurus of drug interactions and from DDI-Predictor |
| `src/kbs/personalized_rules.json` | Hospital-specific KBS rules (e.g. apixaban dose, daptomycin 10 mg/kg) |
| `src/kbs/KBS_Docs/` | Reference documents from which the generic KBS rules were extracted (ANSM Thesaurus, DDI-Predictor) |
| `src/rag/RAG_Docs/` | Guidelines (PDF) used by the RAG |
| `src/rag/chroma_db/` | Vector database created by `indexing.py` |
| `src/biology/lab_reference_ranges.json` | Reference ranges of laboratory values, used by `retrieval.py`, `generation.py` and the interface |
| `preprocessing/` | Builds the patient JSON files from the anonymised CSV extractions (`preprocessing/original_dataset/`, not versioned) |
| `paper/` | Article, presentation and figures (`paper/figures_en/`) |

## Links between the scripts

```
src/rag/RAG_Docs/ --> indexing.py --> src/rag/chroma_db/

                  retrieval.py   (guideline passages)
                /              \
dataset/ --> main.py              --> generation.py --> LLM decision
                \              /
                  kbs.py         (KBS alerts)
```

For each patient, `main.py` gets the useful passages from `retrieval.py` and the alerts from `kbs.py`, then passes them to `generation.py`, which gives the final decision.
`retrieval.py` uses the `src/rag/chroma_db/` database created by `indexing.py`: run the indexing before the analysis.

## Methodology

![Figure 1](paper/figures_en/figure_1.png)

**Figure 1. Overall architecture of the AI-assisted pharmaceutical analysis pipeline.**
Guidelines (PDF) are split into passages and indexed in a vector database (ChromaDB).
For each patient, the orchestration module queries in parallel the retrieval module, which extracts the relevant passages, and the Knowledge-Based System (KBS), which produces deterministic alerts; both outputs are passed to the language model, which gives the final decision.

![Figure 2](paper/figures_en/figure_2.png)

**Figure 2. Retrieval of the relevant guideline excerpts for a patient (Retrieval-Augmented Generation).**
Laboratory parameters outside their reference ranges are converted into textual descriptors and added to the patient profile. A query is built for each prescription line (drug label, dosage regimen, patient profile), encoded with Qwen3-Embedding-8B, then submitted to a 3-nearest-neighbour search (cosine distance). The retrieved passages are deduplicated and sorted by distance, and the 8 closest form the context passed to the language model.

![Figure 3](paper/figures_en/figure_3.png)

**Figure 3. Operation of the Knowledge-Based System (KBS) made of deterministic rules.**
Patient variables (characteristics, laboratory values, dose of each drug) are extracted from the record. Each rule is triggered if (i) all the drugs it targets are prescribed, (ii) all its mandatory conditions are met and (iii) a minimum number of optional criteria is satisfied. The messages of the triggered rules form the list of alerts passed to the language model.

![Figure 4](paper/figures_en/figure_4.png)

**Figure 4. Generation of the pharmaceutical opinion by the language model.**
The message submitted to the model (Qwen3.6-35B-A3B, temperature 0, constrained JSON output) combines the patient record (lines numbered L1, L2..., status of each line on the reference date, daily dose computed by the code, abnormal laboratory values flagged, drugs present on several lines with their total dose), the KBS alerts (numbered [A1], [A2]...) and the retrieved guideline excerpts (numbered [R1], [R2]...). The system prompt defines the clinical pharmacist role, the analysis criteria and the ranking of the alerts (contraindications first). The response is a JSON object containing the decision (patient validated, monitoring proposed, verification proposed or pharmaceutical intervention proposed) and 1 to 4 typed points (intervention, verification, monitoring, validation) written as proposals (“We propose…”, “We suggest…”), each with the identifiers of the alerts and excerpts it relies on. Identifiers that match no provided alert or excerpt are ignored. The displayed decision is that of the most severe point; for an intervention, the LLM also gives the lines to modify, shown in red in the prescription.

## Usage

**Web interface**

```bash
streamlit run app.py
```

The inference folder (`dataset` by default, or `full_dataset`) is chosen in the sidebar.

Analysis results are saved in `src/front/inference_results.json`.

![List of the analysed records: indicators, filters, pharmaceutical opinion, KBS alerts and cited sources](paper/interface_screenshot_1.png)

*Analysis results: for each patient, profile, laboratory values, prescription, pharmaceutical opinion, KBS alerts and clickable sources.*

![Viewing a cited source: the PDF opens directly at the referenced page](paper/interface_screenshot_2.png)

*Viewing a source: clicking a reference opens the PDF at the page cited by the model.*

**All patients**

```bash
python3 main.py --folder dataset
```

Use `--folder full_dataset` to analyse the full dataset.

Prints for each patient: its identifier, the decision (`PATIENT VALIDATED`, `MONITORING PROPOSED`, `VERIFICATION PROPOSED` or `PHARMACEUTICAL INTERVENTION PROPOSED`), the justification and the sources cited by the model.

**One patient with the LLM**

```bash
python3 generation.py --folder dataset --patient-id 100133744
```

Prints the decision and the justification.

**Knowledge-Based System (KBS)**

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

In the interface, the “KBS rules” tab separates the personalized rules (added by the assistant or by hand, deletion) from the generic rules (viewing and search).

**Indexing** (run once, then each time a PDF is added)

```bash
python3 indexing.py
```

Prints the number of passages indexed per PDF and creates the `src/rag/chroma_db/` folder.

**Retrieval**

```bash
python3 retrieval.py --folder dataset --patient-id 100133744
```

Prints the most relevant passages for the patient, with their PDF and page.

**Preprocessing** (rebuilds the patient files from the CSV files of `preprocessing/original_dataset/`)

```bash
python3 preprocessing/preprocessing.py
```

Writes one JSON file per patient to `preprocessing/dataset/`. `python3 preprocessing/analysis.py` prints the number of patients kept at each filtering step.
