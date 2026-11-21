"""Streamlit interface (entry point: app.py at the project root), one module per page of the application.

- page_analysis_results.py: “Résultats d'analyse” page (indicators, analysis button, patient list);
- page_patient_result.py: record opened by clicking a patient of the list (laboratory values, prescription,
  pharmaceutical opinion, KBS alerts);
- page_kbs_rules.py: “Règles du KBS” page (rules drafted by the LLM assistant, list, deletion);
- page_rag_documents.py: “Documents du RAG” page (indexed guidelines, indexing, upload) and PDF viewer;
- common.py: what the three pages share (page frame, patient records, small helpers);
- style.css: style of the whole interface, injected in every page.

The backend logic stays in the scripts at the project root (main.py, kbs.py, generation.py, indexing.py).
"""
