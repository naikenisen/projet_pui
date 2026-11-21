"""Analysis of the patients through main.py (KBS + RAG + LLM), results in src/results/inference_results.json."""

import os
import subprocess
import sys

import main
from src.front.services.data import PATIENTS_FOLDER

MAIN_SCRIPT = os.path.abspath(main.__file__)
load_results = main.load_results


def run_main():
    """Runs `main.py --remaining` on dataset/; yields the id of each analysed patient.

    `main.py --all` (re-analysis of all the patients) is run by hand, not from the interface."""
    command = [sys.executable, "-u", MAIN_SCRIPT, "--remaining", "--folder", PATIENTS_FOLDER]
    other_lines = []
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                          cwd=os.path.dirname(MAIN_SCRIPT)) as process:
        for line in process.stdout:
            if line.startswith("Patient "):
                yield line.split()[1]
            else:
                other_lines.append(line.rstrip())
    if process.returncode:
        raise RuntimeError("\n".join(other_lines[-5:]) or f"main.py exited with code {process.returncode}")


def analyse_and_save(results, record):
    """Analyses one record again (main.analyse), stores the result in results and saves the results file."""
    results[record["patient"]["id"]] = main.analyse(record)
    main.save_results(results)
