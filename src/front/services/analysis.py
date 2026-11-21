"""Analysis of the patients through main.py (KBS + RAG + LLM), results in src/results/inference_results.json."""

import os
import subprocess
import sys

import main

MAIN_SCRIPT = os.path.abspath(main.__file__)
load_results = main.load_results


def run_main(folder, all_patients):
    """Runs `main.py --all` or `main.py --remaining` on the folder; yields the id of each analysed patient."""
    command = [sys.executable, "-u", MAIN_SCRIPT, "--all" if all_patients else "--remaining", "--folder", folder]
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
