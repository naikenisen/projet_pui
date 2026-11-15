import json
from pathlib import Path

from generation import analyser_patient

INPUT_FILE = Path(__file__).parent / "input.json"


def main():
    dossiers = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    if isinstance(dossiers, dict):  # accepte aussi un fichier avec un seul patient
        dossiers = [dossiers]

    for dossier in dossiers:
        patient = dossier["patient"]
        resultat = analyser_patient(dossier)

        print("=" * 80)
        print(f"Patient {patient.get('id', '?')} — {patient.get('age')} ans, {patient.get('sexe')}")
        print(f"\n>>> {resultat.get('decision', '?')}\n")
        print(resultat.get("justification", ""))
    print("=" * 80)


if __name__ == "__main__":
    main()
