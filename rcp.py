# Finds the ANSM RCP (summary of product characteristics) of each ongoing drug and extracts its dosage and contraindications sections.

import argparse
import functools
import os
import re

from kbs import line_details, load_patient, normalize

RCP_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ressources", "rag", "RCP", "markdown")
# 4.2 Posologie et mode d'administration, 4.3 Contre-indications
SECTIONS = ("4.2", "4.3")
# Only the dosage is sent to the LLM
LLM_SECTIONS = ("4.2",)


def words(text):
    return re.findall(r"[a-z0-9]+", normalize(text))


# Words of each file name without its CIS code: "62782120_irbesartan_arrow_150_mg_comprime.md"
@functools.lru_cache(maxsize=None)
def rcp_index():
    if not os.path.isdir(RCP_FOLDER):
        return []
    return [(set(words(name.split("_", 1)[1][:-3])), name) for name in os.listdir(RCP_FOLDER) if name.endswith(".md")]


# "IRBESARTAN 150 MG (LABO ARROW), CPR" -> "62782120_irbesartan_arrow_150_mg_comprime.md"
def find_rcp(label):
    label = re.sub(r"^\[[^]]*\]", "", label)
    drug = re.split(r"[\d,(]", label, maxsplit=1)[0]
    # First word of each active ingredient: the salt ("METFORMINE CHLORHYDRATE") is not in the file names
    ingredients = {words(part)[0] for part in drug.split("+") if words(part)}
    found = re.search(r"\(([^)]*)\)", label)
    brand = set(words(found.group(1))) if found else set()
    # "(LABO ARROW)" names a laboratory, not a brand: it only separates the candidates
    is_laboratory = "labo" in brand
    numbers = set(re.findall(r"\d+", label.split(",")[0]))

    candidates = [(tokens, name) for tokens, name in rcp_index()
                  if (ingredients and ingredients <= tokens) or (brand and not is_laboratory and brand <= tokens)]
    if not candidates:
        return None
    label_words = set(words(drug)) | brand | numbers
    # The brand names the exact product (KARDEGIC 75 mg, not an aspirin 500 mg): it comes first
    has_brand = lambda tokens: bool(brand) and not is_laboratory and brand <= tokens
    return max(candidates, key=lambda c: (has_brand(c[0]), len(label_words & c[0]), -len(c[1])))[1]


# (denomination, markdown text of the sections 4.2 and 4.3) of an RCP file
def read_sections(file_name, sections=SECTIONS):
    # basename prevents leaving the folder with a name like "../../file.md"
    with open(os.path.join(RCP_FOLDER, os.path.basename(file_name)), encoding="utf-8") as file:
        text = file.read()
    denomination = re.search(r'^denomination: "?(.*?)"?$', text, re.M)
    parts = []
    for number in sections:
        # From the "### 4.2." heading to the next numbered heading
        found = re.search(rf"^#+ *{re.escape(number)}\.?([^\n]*)\n(.*?)(?=^#+ *\d+\.\d|\Z)", text, re.S | re.M)
        if found:
            parts.append(f"### {number}.{found.group(1)}\n{found.group(2).strip()}")
    return (denomination.group(1) if denomination else file_name), "\n\n".join(parts)


# One excerpt per RCP of the ongoing lines: {"source": file name, "name": denomination, "text": dosage section}
def rcp_excerpts(record):
    file_names = []
    for treatment, details in zip(record["treatments"], line_details(record)):
        file_name = find_rcp(treatment["drug_label"]) if details.get("status") == "ongoing" else None
        if file_name and file_name not in file_names:
            file_names.append(file_name)
    excerpts = []
    for file_name in file_names:
        name, text = read_sections(file_name, LLM_SECTIONS)
        if text:
            excerpts.append({"source": file_name, "name": name, "text": text})
    return excerpts


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True, help="folder containing the patient JSON files")
    parser.add_argument("--patient-id", required=True, help="patient number (JSON file name without .json)")
    args = parser.parse_args()

    record = load_patient(args.folder, args.patient_id)
    for treatment in record["treatments"]:
        print(f"{treatment['drug_label']} -> {find_rcp(treatment['drug_label'])}")
