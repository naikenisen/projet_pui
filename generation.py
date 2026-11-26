# Analyses a patient's prescription with the LLM.

import argparse
import json
import os
import re

from inference import InferenceBackend, add_inference_arguments, backend_from_args
from kbs import line_details, load_patient, normalize

# Reasoning: much more consistent opinions, but ~40 s per patient instead of 10 s
REASONING = True

DECISION_VALIDATED = "PATIENT VALIDATED"
DECISION_MONITORING = "MONITORING PROPOSED"
DECISION_VERIFICATION = "VERIFICATION PROPOSED"
DECISION_INTERVENTION = "PHARMACEUTICAL INTERVENTION PROPOSED"

SYSTEM_PROMPT = """You are a French hospital clinical pharmacist. You are given a patient and their prescription in JSON format.
The record comes from a French hospital: drug labels, laboratory parameter names, alerts and guideline excerpts are
in French. Write "reasoning" and the "text" of the points in French; keep the JSON keys and the "type" values in
English.

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
  laboratory values). A dosage within the usual ranges, even debatable, calls for neither intervention nor
  verification.

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
Alerts starting with “Patient à risque” are statistical: they flag a situation in which the hospital pharmacists
often make an intervention (e.g. oral anticoagulant). They report no problem. Examine the drugs involved more
carefully, but never make a point only because of such an alert: if nothing is wrong, validate the prescription.

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
  intervention and (2) information missing from the record is essential to decide.
  The same drug on several ongoing lines is not a problem in itself: it is usually deliberate, to obtain a
  specific dosage (e.g. levothyroxine 150 + 12.5 µg). Judge the total dose: only propose a verification if it is
  unusual or exceeds the maximum dose.
- "monitoring": acceptable combination or dosage that nevertheless justifies specific clinical or laboratory
  monitoring (e.g. potassium, INR, ECG, blood glucose, renal function).
- "validation": nothing to report. Used alone, as a single point, when the prescription is validated.

Reply only with a JSON object. Start with "reasoning": in 3 to 6 sentences, the laboratory abnormalities and
their direction, the alerts that really apply (exceptions included), then the problems retained.
{"reasoning": "...", "points": [{"type": "intervention", "text": "a short proposal", "references": ["A1", "R2"],
  "lines_to_modify": ["L3"]}]}

Rules for the points:
- 1 to 4 points, one per problem, from the most to the least important.
- Each point is one or two short sentences (40 words at most) and starts with “Nous proposons” or “Nous
  suggérons” (or “Pas d'intervention proposée” for a validation). Do not make a point about a compliant prescription or about
  an item with no practical consequence.
- Example wordings: “Nous proposons de réduire l'apixaban à 2,5 mg deux fois par jour compte tenu de la
  créatinine à 155 µmol/L et de l'âge (95 ans)”, “Nous suggérons de vérifier avec le prescripteur la dose totale
  d'irbésartan de 450 mg/jour (L11 + L19), supérieure à la dose maximale”, “Nous proposons de surveiller la
  kaliémie...”.
- Name the drug involved and the patient values that justify the point. Do not write any alert or excerpt
  identifier (A1, R2) in "text"; you may refer to a line by its identifier (L3).
- "references": only the identifiers of the provided alerts and excerpts on which the point really relies.
  Never invent an identifier; empty list if the point relies on your own knowledge.
- "lines_to_modify": for an "intervention" point only, the identifiers of the lines you propose to modify or
  stop; empty list for the other types."""


LAB_RANGES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ressources", "lab_reference_ranges.json")


# Number without useless zeros or scientific notation
def number(value):
    return f"{value:g}" if value < 1e6 else f"{value:.0f}"


def read_lab_ranges():
    if not os.path.exists(LAB_RANGES_FILE):
        return {}
    with open(LAB_RANGES_FILE, encoding="utf-8") as file:
        return json.load(file)


def lab_interpretation(name, value, ranges):
    reference = ranges.get(name)
    if reference is None or not isinstance(value, (int, float)) or isinstance(value, bool):
        return ""
    if value < reference["min"]:
        return "low"
    if value > reference["max"]:
        return "high"
    return ""


# Record sent to the LLM: empty fields removed, lab values interpreted, lines L1, L2... with the status and dose
# deduced by the KBS
def summarize_record(record):
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
    for number_, (treatment, details) in enumerate(zip(record["treatments"], line_details(record)), start=1):
        line = {"id": f"L{number_}"}
        line |= {key: treatment[key] for key in ("drug_label", "dosage_regimen", "start_date", "end_date")
                 if treatment.get(key)}
        line["status"] = details["status"]
        if treatment.get("as_needed"):
            line["as_needed"] = True
        elif "dose" in details:
            amount, unit = details["dose"]
            line["dose_per_administration_day"] = f"{number(amount)} {unit}"
        treatments.append(line)
    return {"patient": summary, "treatments": treatments}


# A1, R2... identifiers copied into the text despite the prompt (L3 identifiers are kept)
REFERENCE_IN_TEXT_PATTERN = re.compile(r"\s*(?:\([^()]*\b[AR]\d+\b[^()]*\)|\[[AR]\d+(?:\s*,\s*[AR]\d+)*\])")


# From most to least severe
POINT_TYPES = ("intervention", "verification", "monitoring", "validation")
DECISION_BY_TYPE = {"intervention": DECISION_INTERVENTION, "verification": DECISION_VERIFICATION,
                    "monitoring": DECISION_MONITORING, "validation": DECISION_VALIDATED}


# Accepts variants ("Verification", "PI"...); "verification" if unknown
def point_type(value):
    text = normalize(value).strip()
    if text in ("pi", "ip") or "interv" in text:
        return "intervention"
    for keyword, code in (("verif", "verification"), ("monitor", "monitoring"), ("surveil", "monitoring"),
                          ("valid", "validation")):
        if keyword in text:
            return code
    return "verification"


# Replaces the identifiers cited by the LLM with the matching alerts, excerpts and lines; unknown ones are ignored
def read_response(response, alerts, passages, line_count):
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


# The decision is the one of the most severe point, to stay consistent with the points
def analyse_patient(record, passages=(), alerts=(), backend: InferenceBackend | None = None):
    backend = backend if backend is not None else InferenceBackend()
    alerts, passages = list(alerts), list(passages)
    message = json.dumps(summarize_record(record), ensure_ascii=False, indent=1)
    if alerts:
        message += "\n\nKBS alerts:\n" + "\n".join(f"[A{i}] {alert}" for i, alert in enumerate(alerts, start=1))
    if passages:
        message += "\n\nGuideline excerpts:\n" + "\n\n".join(
            f"[R{i}] ({p['source']}, page {p['page']})\n{p['text']}" for i, p in enumerate(passages, start=1)
        )

    response = backend.generate(
        SYSTEM_PROMPT, message,
        max_tokens=12000 if REASONING else 2500,
        reasoning=REASONING,
        json_mode=True,
    )

    response = json.loads(response[response.find("{"):response.rfind("}") + 1])
    points = read_response(response, alerts, passages, len(record["treatments"]))
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
    add_inference_arguments(parser)
    parser.add_argument("--folder", required=True, help="folder containing the patient JSON files")
    parser.add_argument("--patient-id", required=True, help="patient number (JSON file name without .json)")
    args = parser.parse_args()

    result = analyse_patient(load_patient(args.folder, args.patient_id), backend=backend_from_args(args))
    print(result["decision"])
    print(result["justification"])
