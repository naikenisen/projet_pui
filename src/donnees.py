"""Lecture, écriture et validation des fichiers JSON du projet (patients, biologie, résultats).

Les règles du système expert sont gérées par expert_system.py."""

import json
import os

DOSSIER_PATIENTS = "dataset_test"  # dossier par défaut : un fichier JSON par patient
FICHIER_BIO = "bio_anormale.json"
FICHIER_RESULTATS = "resultats.json"


def lire_json(chemin, defaut=None):
    if not os.path.exists(chemin):
        return defaut
    with open(chemin, encoding="utf-8") as fichier:
        return json.load(fichier)


def ecrire_json(chemin, donnees):
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(donnees, fichier, ensure_ascii=False, indent=2)
        fichier.write("\n")


def fichiers_patients(repertoire):
    if not os.path.isdir(repertoire):
        return []
    return sorted(nom for nom in os.listdir(repertoire) if nom.endswith(".json"))


def charger_patients(repertoire=DOSSIER_PATIENTS):
    """Renvoie la liste des dossiers patients (un fichier JSON par patient) contenus dans le répertoire."""
    return [lire_json(os.path.join(repertoire, nom)) for nom in fichiers_patients(repertoire)]


def charger_bio():
    return lire_json(FICHIER_BIO, {})


def charger_resultats():
    return lire_json(FICHIER_RESULTATS, {})


def sauver_resultats(resultats):
    ecrire_json(FICHIER_RESULTATS, resultats)


def sauver_bio(lignes):
    """lignes : liste de dicts {cle, libelle, unite, min, max}. Renvoie la liste des erreurs (vide si OK)."""
    normes = {}
    erreurs = []
    for numero, ligne in enumerate(lignes, start=1):
        cle = str(ligne.get("cle") or "").strip()
        if not cle:
            erreurs.append(f"Ligne {numero} : la clé est obligatoire")
            continue
        if cle in normes:
            erreurs.append(f"Ligne {numero} : la clé « {cle} » est en double")
            continue
        try:
            minimum, maximum = float(ligne["min"]), float(ligne["max"])
        except (TypeError, ValueError, KeyError):
            erreurs.append(f"Ligne {numero} ({cle}) : min et max doivent être des nombres")
            continue
        if minimum > maximum:
            erreurs.append(f"Ligne {numero} ({cle}) : min est plus grand que max")
            continue
        normes[cle] = {
            "libelle": str(ligne.get("libelle") or cle).strip(),
            "unite": str(ligne.get("unite") or "").strip(),
            "min": minimum,
            "max": maximum,
        }
    if not erreurs:
        ecrire_json(FICHIER_BIO, normes)
    return erreurs
