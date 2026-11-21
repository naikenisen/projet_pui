"""Streamlit interface (entry point: app.py at the project root).

- services/: data access and calls to the backend (no Streamlit);
- rendering/: HTML generation (no Streamlit);
- components/: reusable Streamlit widgets and dialogs;
- views/: one module per area of the screen (sidebar, overview, tabs);
- assets/: CSS and JavaScript injected in the page;
- state.py: data shared by the views during one run of the script;
- theme.py: page configuration, style and application bar.
"""
