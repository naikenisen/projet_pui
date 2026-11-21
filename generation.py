"""Analyses a patient's prescription with the LLM."""

import argparse
import json
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

from kbs import load_patient, normalize

load_dotenv()
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])

MODEL = "qwen/qwen3.6-35b-a3b"
# Model reasoning mode: much more consistent opinions (alert exceptions, direction of laboratory abnormalities),
# but about 40 s per patient instead of 10 s. Set to False for a fast analysis.
REASONING = True

DECISION_VALIDATED = "PATIENT VALIDATED"
DECISION_MONITORING = "MONITORING PROPOSED"
DECISION_VERIFICATION = "VERIFICATION PROPOSED"
DECISION_INTERVENTION = "PHARMACEUTICAL INTERVENTION PROPOSED"

SYSTEM_PROMPT = """You are a French hospital clinical pharmacist. You are given a patient and their prescription in JSON format.
The record comes from a French hospital: drug labels, laboratory parameter names, alerts and guideline excerpts are
in French. Write your answer in English.

Record content:
- "reference_date" is the date on which the prescription is analysed. Missing data is not available.
- Each laboratory value is given with its unit and date; “(low)” or “(high)” means that it is outside the
  hospital's reference range.
- Each treatment line has an identifier (L1, L2...), a label (product, strength, form), a dosage regimen,
  dates, a status on the reference date (“ongoing”, “ended”, “upcoming”) and, when it can be computed,
  "dose_per_administration_day" (already computed: use it as is, do not redo the computation). For a
  “1 day(s) out of N” regimen, this dose is only taken one day out of N.
- Only “ongoing” lines are active. Two lines whose dates do not overlap follow one another: this is not a
  duplicate. A scheduled line and an “as needed” line of the same drug (e.g. morphine) are a common practice,
  not a duplicate.

What you do NOT know: the record contains no diagnosis, medical history, indication or clinical examination.
- Never state that a drug is not indicated, that a condition is absent or present (unless the laboratory values
  show it), or that a treatment is “unnecessary”. Never propose stopping a drug for lack of indication and do not
  propose checking the indication of a treatment.
- Do not assume missing information (frailty, life expectancy, clinical context). Each proposal must rely on a
  fact from the record (dose, laboratory value, age, weight, dates, combination of lines) or on a provided alert
  or excerpt.
- If a point relies only on your own knowledge (no alert or excerpt), only propose an intervention or a
  verification for an obvious error (dose above the marketing authorisation maximum, contraindication confirmed by
  laboratory values) or for the same drug on several lines. A dosage within the usual ranges, even debatable,
  calls for neither intervention nor verification.

Knowledge-Based System (KBS) alerts [A1], [A2]... and guideline excerpts [R1], [R2]... may be provided.
Alerts from the ANSM Thesaurus give their level in parentheses: CI or CONTRE-INDICATION = contraindication,
ASDEC or Association DECONSEILLEE = combination not recommended, PE or Précaution d'emploi = precaution for use,
APEC or A prendre en compte = to be taken into account. A combined level (e.g. “CI - ASDEC - APEC”) means that the
level depends on the molecules or doses: read the recommended action (“Conduite à tenir”) to determine the level
that really applies to this prescription (e.g. aspirin at antiplatelet dose + heparin = “to be taken into
account”, not “not recommended”). Then rank the alerts:
- CONTRAINDICATIONS take priority;
- the other alerts (combination not recommended, precaution for use, pharmacokinetic interaction) only justify
  an intervention if, given this patient's data (age, renal function, laboratory values, doses), the risk is
  clinically critical. Otherwise, they call at most for monitoring, or are simply acceptable.
An alert therefore never justifies an intervention on its own.

Consistency with the patient (check for each point):
- Read the recommended action of each alert in full. If it provides an exception that applies to the patient
  (e.g. “Sauf s'il existe une hypokaliémie” while potassium is low), the alert does not apply.
- Check the direction of each laboratory abnormality. A treatment that corrects an abnormal value (e.g.
  potassium if potassium is low, vitamin D if deficient) is justified by this value: never use it to propose
  stopping or reducing it.
- A 1- or 2-day line overlapping a longer line of the same drug is often a loading dose.
- A point must contradict neither the laboratory values, nor the dates, nor the recommended action of the alerts.

Each point has a type:
- "intervention": a confirmed and clinically important problem requires changing the prescription.
- "verification": reserved for cases where (1) if the hypothesis were confirmed, the problem would justify an
  intervention and (2) information missing from the record is essential to decide. Typical example: the same
  drug on several ongoing scheduled lines (deliberate total dose or forgotten line?). A list of these multiple
  lines, with the total dose, may be provided. Combining two strengths to obtain a precise dose is common (e.g.
  levothyroxine 150 + 12.5 µg): only propose a verification if the total dose is unusual or exceeds the maximum
  dose.
- "monitoring": acceptable combination or dosage that nevertheless justifies specific clinical or laboratory
  monitoring (e.g. potassium, INR, ECG, blood glucose, renal function).
- "validation": nothing to report. Used alone, as a single point, when the prescription is validated.

Reply only with a JSON object. Start with "reasoning": in 3 to 6 sentences, the laboratory abnormalities and
their direction, the alerts that really apply (exceptions included), then the problems retained.
{"reasoning": "...", "points": [{"type": "intervention", "text": "a short proposal", "references": ["A1", "R2"],
  "lines_to_modify": ["L3"]}]}

Rules for the points:
- 1 to 4 points, one per problem, from the most to the least important.
- Each point is one or two short sentences (40 words at most) and starts with “We propose” or “We suggest”
  (or “No intervention proposed” for a validation). Do not make a point about a compliant prescription or about
  an item with no practical consequence.
- Example wordings: “We propose reducing apixaban to 2.5 mg twice daily given the serum creatinine of
  155 µmol/L and the age (95 years)”, “We suggest checking with the prescriber whether the two irbesartan lines
  (150 mg and 300 mg/day) are deliberate”, “We propose monitoring potassium...”.
- Name the drug involved and the patient values that justify the point. Do not write any alert or excerpt
  identifier (A1, R2) in "text"; you may refer to a line by its identifier (L3).
- "references": only the identifiers of the provided alerts and excerpts on which the point really relies.
  Never invent an identifier; empty list if the point relies on your own knowledge.
- "lines_to_modify": for an "intervention" point only, the identifiers of the lines you propose to modify or
  stop; empty list for the other types."""


# ---------------------------------------------------------------------------
# Record preparation: whatever can be computed is computed by the code, not by the LLM
# ---------------------------------------------------------------------------

LAB_RANGES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "biology", "lab_reference_ranges.json")

# Intake units that are already an amount of active ingredient (values as found in the data)
QUANTITY_UNITS = {"milligramme(s)": (1, "mg"), "gramme(s)": (1000, "mg"), "microgramme(s)": (1, "µg"),
                  "unité(s) internationale(s)": (1, "IU"), "unité(s) internationale(s) anti-Xa": (1, "anti-Xa IU")}
# Unit dosage forms whose active ingredient dosage is the amount per unit (not a concentration)
UNIT_FORMS = ("comprimé", "gélule", "sachet", "ampoule", "seringue", "capsule", "suppositoire", "stylo", "film")
DOSAGE_UNITS = {"mg": (1, "mg"), "g": (1000, "mg"), "ug": (1, "µg"), "iu": (1, "IU"), "axa_iu": (1, "anti-Xa IU"), "u": (1, "U")}


def number(value):
    return f"{value:g}" if value < 1e6 else f"{value:.0f}"


def dose_per_day(treatment):
    """Active ingredient dose per administration day: (3000, "mg"), or None if it cannot be computed."""
    quantity = treatment.get("quantity_per_day")
    if not isinstance(quantity, (int, float)) or quantity <= 0:
        return None
    unit = treatment.get("intake_unit") or ""
    if unit in QUANTITY_UNITS:
        factor, symbol = QUANTITY_UNITS[unit]
        return quantity * factor, symbol
    ingredients = treatment.get("active_ingredients") or []
    if (any(unit.startswith(form) for form in UNIT_FORMS) and len(ingredients) == 1
            and ingredients[0].get("unit") in DOSAGE_UNITS and isinstance(ingredients[0].get("dosage"), (int, float))):
        factor, symbol = DOSAGE_UNITS[ingredients[0]["unit"]]
        return quantity * ingredients[0]["dosage"] * factor, symbol
    return None


def line_status(treatment, reference_date):
    """“ongoing”, “ended” or “upcoming” on the reference date (dates in YYYY-MM-DD format)."""
    if not reference_date:
        return "ongoing"
    start, end = (treatment.get("start_date") or "")[:10], (treatment.get("end_date") or "")[:10]
    if start and start > reference_date:
        return "upcoming"
    if end and end < reference_date:
        return "ended"
    return "ongoing"


def drug_name(label):
    """“IRBESARTAN 150 MG (LABO ARROW), CPR” -> “IRBESARTAN”: the name before the strength or the form."""
    return re.split(r"[\d,(]", label, maxsplit=1)[0].strip().upper()


def read_lab_ranges():
    if not os.path.exists(LAB_RANGES_FILE):
        return {}
    with open(LAB_RANGES_FILE, encoding="utf-8") as file:
        return json.load(file)


def lab_interpretation(name, value, ranges):
    """“low”, “high” or "" according to the reference ranges of src/biology/lab_reference_ranges.json."""
    reference = ranges.get(name)
    if reference is None or not isinstance(value, (int, float)) or isinstance(value, bool):
        return ""
    if value < reference["min"]:
        return "low"
    if value > reference["max"]:
        return "high"
    return ""


def summarize_record(record):
    """Version of the record sent to the LLM: empty fields removed, laboratory values interpreted, lines numbered
    L1, L2... with their status on the reference date and the computed dose per administration day."""
    patient = record["patient"]
    summary = {key: value for key, value in patient.items() if key != "biology" and value is not None}
    ranges = read_lab_ranges()
    summary["biology"] = {}
    for name, measure in patient["biology"].items():
        text = f"{measure['value']} {measure.get('unit') or ''}".strip()
        if interpretation := lab_interpretation(name, measure.get("value"), ranges):
            text += f" ({interpretation})"
        summary["biology"][name] = f"{text} on {measure.get('test_datetime') or '?'}"

    treatments = []
    for number_, treatment in enumerate(record["treatments"], start=1):
        line = {"id": f"L{number_}"}
        line |= {key: treatment[key] for key in ("drug_label", "dosage_regimen", "start_date", "end_date")
                 if treatment.get(key)}
        line["status"] = line_status(treatment, patient.get("reference_date"))
        if treatment.get("as_needed"):
            line["as_needed"] = True
        elif dose := dose_per_day(treatment):
            line["dose_per_administration_day"] = f"{number(dose[0])} {dose[1]}"
        treatments.append(line)
    return {"patient": summary, "treatments": treatments}


def multiple_lines(record):
    """Drugs prescribed on several ongoing scheduled lines (excluding “as needed”): deliberate total dose or
    forgotten line. Returns one sentence per drug, with the total dose when it can be computed:
    “IRBESARTAN: L11 (150 mg) + L19 (300 mg) = 450 mg per day”."""
    reference_date = record["patient"].get("reference_date")
    groups = {}
    for number_, treatment in enumerate(record["treatments"], start=1):
        if treatment.get("as_needed") or line_status(treatment, reference_date) != "ongoing":
            continue
        groups.setdefault(drug_name(treatment["drug_label"]), []).append((number_, dose_per_day(treatment)))
    sentences = []
    for name, lines in groups.items():
        if not name or len(lines) < 2:
            continue
        doses = [dose for _, dose in lines]
        if all(doses) and len({symbol for _, symbol in doses}) == 1:
            detail = " + ".join(f"L{n} ({number(dose[0])} {dose[1]})" for n, dose in lines)
            detail += f" = {number(sum(d[0] for d in doses))} {doses[0][1]} per day"
        else:
            detail = " + ".join(f"L{n}" for n, _ in lines)
        sentences.append(f"{name}: {detail}")
    return sentences


# Identifier copied into the text despite the instruction: “(A1, A2)”, “(alert A1 level ...)”, “[R2]” (line numbers
# such as L3 are kept: they are shown in the prescription table)
REFERENCE_IN_TEXT_PATTERN = re.compile(r"\s*(?:\([^()]*\b[AR]\d+\b[^()]*\)|\[[AR]\d+(?:\s*,\s*[AR]\d+)*\])")


POINT_TYPES = ("intervention", "verification", "monitoring", "validation")  # from most to least severe
DECISION_BY_TYPE = {"intervention": DECISION_INTERVENTION, "verification": DECISION_VERIFICATION,
                    "monitoring": DECISION_MONITORING, "validation": DECISION_VALIDATED}


def point_type(value):
    """Type of a point, tolerant to variants (“Verification”, “PI”...); "verification" if unknown."""
    text = normalize(value).strip()
    if text in ("pi", "ip") or "interv" in text:
        return "intervention"
    for keyword, code in (("verif", "verification"), ("monitor", "monitoring"), ("surveil", "monitoring"),
                          ("valid", "validation")):
        if keyword in text:
            return code
    return "verification"


def read_response(response, alerts, passages, line_count):
    """Replaces the identifiers cited by the LLM with the corresponding alerts, excerpts and lines.

    Unknown identifiers are ignored: the LLM cannot cite a source it was not given.
    """
    references = {f"A{i}": {"type": "alert", "text": alert} for i, alert in enumerate(alerts, start=1)}
    references |= {
        f"R{i}": {"type": "document", "source": p["source"], "page": p["page"]} for i, p in enumerate(passages, start=1)
    }
    points = []
    for point in response.get("points") or []:
        if not isinstance(point, dict) or not str(point.get("text", "")).strip():
            continue
        sources = []
        for identifier in point.get("references") or []:
            source = references.get(str(identifier).strip(" []").upper())
            if source and source not in sources:
                sources.append(source)
        type_ = point_type(point.get("type", ""))
        lines = []
        if type_ == "intervention":
            for identifier in point.get("lines_to_modify") or []:
                found = re.fullmatch(r"L(\d+)", str(identifier).strip(" []").upper())
                if found and 1 <= int(found.group(1)) <= line_count and int(found.group(1)) not in lines:
                    lines.append(int(found.group(1)))
        text = REFERENCE_IN_TEXT_PATTERN.sub("", str(point["text"])).strip()
        points.append({"type": type_, "text": text, "sources": sources, "lines_to_modify": lines})
    return points


def source_label(source):
    if source["type"] == "alert":
        return "KBS: " + source["text"]
    return f"{source['source']}, page {source['page']}"


def analyse_patient(record, passages=(), alerts=()):
    """passages: excerpts returned by retrieval.retrieve_context; alerts: KBS alerts.

    Returns {"decision", "points": [{"type", "text", "sources", "lines_to_modify"}], "reasoning", "justification",
    "sources"}. The decision is that of the most severe point, so that it is always consistent with the points.
    "justification" and "sources" list the points flat, for a simple display (main.py).
    """
    alerts, passages = list(alerts), list(passages)
    message = json.dumps(summarize_record(record), ensure_ascii=False, indent=1)
    if multiples := multiple_lines(record):
        message += "\n\nSame drug on several ongoing scheduled lines:\n" + "\n".join(
            f"- {sentence}" for sentence in multiples
        )
    if alerts:
        message += "\n\nKBS alerts:\n" + "\n".join(f"[A{i}] {alert}" for i, alert in enumerate(alerts, start=1))
    if passages:
        message += "\n\nGuideline excerpts:\n" + "\n\n".join(
            f"[R{i}] ({p['source']}, page {p['page']})\n{p['text']}" for i, p in enumerate(passages, start=1)
        )

    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
        max_tokens=12000 if REASONING else 2500,  # reasoning consumes tokens
        temperature=0,
        response_format={"type": "json_object"},
        extra_body={"reasoning": {"enabled": REASONING}},
    )
    response = completion.choices[0].message.content

    # Keep only the JSON, in case the model adds text around it.
    response = json.loads(response[response.find("{"):response.rfind("}") + 1])
    points = read_response(response, alerts, passages, len(record["treatments"]))
    # A "validation" point only makes sense on its own
    if any(point["type"] != "validation" for point in points):
        points = [point for point in points if point["type"] != "validation"]
    most_severe = min((POINT_TYPES.index(point["type"]) for point in points), default=POINT_TYPES.index("validation"))

    sources = []
    for point in points:
        for source in point["sources"]:
            if source_label(source) not in sources:
                sources.append(source_label(source))
    return {
        "decision": DECISION_BY_TYPE[POINT_TYPES[most_severe]],
        "points": points,
        "reasoning": str(response.get("reasoning", "")).strip(),
        "justification": "\n".join("- " + point["text"] for point in points),
        "sources": sources,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True, help="folder containing the patient JSON files")
    parser.add_argument("--patient-id", required=True, help="patient number (JSON file name without .json)")
    args = parser.parse_args()

    result = analyse_patient(load_patient(args.folder, args.patient_id))
    print(result["decision"])
    print(result["justification"])
