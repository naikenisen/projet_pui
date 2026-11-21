"""HTML of the patient record: profile, laboratory table, prescription table (no Streamlit)."""

import html

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
    reference = ranges.get(name)
    if reference is None or not isinstance(value, (int, float)):
        return ""
    if value < reference["min"]:
        return LOW
    if value > reference["max"]:
        return HIGH
    return NORMAL


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


def html_table(columns, rows, row_classes=(), short_columns=()):
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
    return f'<table class="data-table"><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>'
