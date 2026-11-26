# Plots the ROC and precision-recall curves of the LLM intervention probability against the manual IP labels in figure_1.png.

import json
from pathlib import Path

import matplotlib.pyplot as plt
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score, roc_curve

PROJECT_DIR = Path(__file__).resolve().parent.parent


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# Patients labelled "ip" whose inference has an intervention probability
def get_scores_and_labels(inference_results: dict, label_results: dict) -> tuple[list[float], list[int]]:
    scores, labels = [], []
    for patient_id, label in label_results.items():
        probability = inference_results.get(patient_id, {}).get("intervention_probability")
        if probability is None or label.get("ip") not in ("Oui", "Non"):
            continue
        scores.append(probability)
        labels.append(int(label["ip"] == "Oui"))
    return scores, labels


def plot_curves(scores: list[float], labels: list[int], output_path: Path):
    figure, (roc_axis, pr_axis) = plt.subplots(1, 2, figsize=(10, 5))

    false_positive_rate, true_positive_rate, _ = roc_curve(labels, scores)
    roc_axis.plot(false_positive_rate, true_positive_rate, label=f"AUC-ROC = {roc_auc_score(labels, scores):.2f}")
    roc_axis.plot([0, 1], [0, 1], linestyle="--", color="grey")
    roc_axis.set_xlabel("False positive rate")
    roc_axis.set_ylabel("True positive rate")
    roc_axis.set_title("ROC curve")
    roc_axis.legend(loc="lower right")

    precision, recall, _ = precision_recall_curve(labels, scores)
    # Precision of a random model = proportion of IP patients
    prevalence = sum(labels) / len(labels)
    pr_axis.plot(recall, precision, label=f"AUC-PR = {average_precision_score(labels, scores):.2f}")
    pr_axis.axhline(prevalence, linestyle="--", color="grey")
    pr_axis.set_ylim(0, 1.05)
    pr_axis.set_xlabel("Recall")
    pr_axis.set_ylabel("Precision")
    pr_axis.set_title("Precision-recall curve")
    pr_axis.legend(loc="lower left")

    figure.suptitle(f"Pharmaceutical intervention detection (n = {len(labels)} patients)")
    figure.tight_layout()
    figure.savefig(output_path, dpi=300)


if __name__ == "__main__":
    inference_results = load_json(PROJECT_DIR / "inference_results.json")
    label_results = load_json(PROJECT_DIR / "label_results.json")
    scores, labels = get_scores_and_labels(inference_results, label_results)
    plot_curves(scores, labels, PROJECT_DIR / "paper" / "figure_1.png")
