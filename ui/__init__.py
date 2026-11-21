"""Streamlit interface (entry point: app.py at the project root), one module per page of the application.

- analysis_results.py: “Résultats d'analyse” page (indicators, patient list, record, pharmaceutical opinion);
- KBS_rules.py: “Règles du KBS” page (rules drafted by the LLM assistant, list, deletion);
- RAG_documents.py: “Documents du RAG” page (indexed guidelines, indexing, upload) and PDF viewer;
- common.py: what the three pages share (page frame, patient records, small helpers);
- assets/: CSS and JavaScript injected in the page.

The backend logic stays in the scripts at the project root (main.py, kbs.py, generation.py, indexing.py).
"""
