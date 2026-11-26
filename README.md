# AI-assisted pharmaceutical analysis software

Pipeline that analyses hospital prescriptions by combining a Knowledge-Based System (KBS), a retrieval module over
clinical guidelines (RAG) and a large language model (LLM).

**Online demo:** https://projetpui.streamlit.app/

To run locally, a  `.env` file at the project root including you API key for OpenRouter is required :
```
OPENROUTER_API_KEY=your_key
```

## BACKEND

### Overall architecture

![Figure 1](paper/figures_en/figure_1.png)

| Script | Role |
|---|---|
| `indexing.py` | Indexes the guidelines (PDF) in a vector database (ChromaDB) |
| `retrieval.py` | Searches the vector database for the passages useful for a patient |
| `kbs.py` | Knowledge-Based System (KBS): turns a patient into facts and runs the CLIPS rules on them |
| `create_rule.py` | Drafts a personalized CLIPS rule with the LLM from a pharmacist request, checks it and saves it |
| `generation.py` | Analyses a patient with the LLM along with retrieved passages and KBS results |
| `main.py` | Launch retrieval then KBS then generation|


### Run from a terminal

Patients are read from `dataset/`; results are saved in `inference_results.json`.

```bash
# FRun the full pipeline on the dataset
python3 main.py --remaining   # analyse patients without a result
python3 main.py --all         # analyse all patients (overwrites results)
python3 main.py --all --multithreads   # same, 8 patients analysed in parallel (also works with --remaining)
python3 indexing.py           # index new docs from ressources/rag/RAG_Docs/ to the vectorial database

# Run inference on one individual patient
python3 retrieval.py  --folder dataset --patient-id 100133744   # retreive relevant passages
python3 kbs.py        --folder dataset --patient-id 100133744   # detected alerts
python3 generation.py --folder dataset --patient-id 100133744   # decision + justification (no KBS/RAG)
```
To have the LLM draft a personalized rule (it is displayed, then saved after confirmation):

```bash
python3 create_rule.py --folder dataset --request "Alert if metformin with an eGFR < 30 mL/min"
```

### Details of the pipeline

- 📄 [Figure 2 – RAG](paper/figures_en/figure_2.pdf)
- 📄 [Figure 3 – Knowledge-Based System (KBS)](paper/figures_en/figure_3.pdf)
- 📄 [Figure 4 – Generation (LLM)](paper/figures_en/figure_4.pdf)


## FRONTEND

```
# The frontend code is organized in pages, one script for each pages of the app

app.py                         entry point
inference_results.json         analysis results saved by main.py
ui/
├── page_analysis_results.py   Page named “Résultats d'analyse”
├── page_patient_result.py     Page shown when you click on a patient
├── page_kbs_rules.py          Page named “Règles du KBS”
├── page_rag_documents.py      Page named “Documents du RAG”
├── common.py                  code shared by the pages
└── style.css                  style of the whole interface
```

## DATA AND OTHER FILES

```
dataset/                         80 patients, one JSON per patient (<id>.json): lab values and treatments
full_dataset/                    1919 patients (not versioned), same format
ressources/
├── kbs/
│   ├── base.clp                 CLIPS fact model, unit conversions, dose calculations, generic interaction rule
│   ├── generic_rules.clp        drug interactions from the ANSM Thesaurus and DDI-Predictor (CLIPS facts)
│   ├── personalized_rules.clp   hospital-specific CLIPS rules, written by create_rule.py (e.g. apixaban dose)
│   └── KBS_Docs/                source documents of the generic rules (ANSM Thesaurus, DDI-Predictor)
├── rag/
│   ├── RAG_Docs/                guidelines (PDF) used by the RAG
│   └── chroma_db/               vector database created by indexing.py
└── lab_reference_ranges.json    lab reference ranges, used by retrieval.py and generation.py
preprocessing/                   builds patient JSONs from the anonymised CSV extractions
                                 (preprocessing/original_dataset/, not versioned)
paper/                           article, presentation and figures (paper/figures_en/)
```




