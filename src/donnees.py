"""Lecture, écriture et validation des fichiers JSON du projet (patients, règles, biologie, résultats)."""

import json
import os

from expert_system import OPERATEURS

FICHIER_PATIENTS = "input.json"
FICHIER_REGLES = "regles_expert.json"
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


def charger_patients():
    return lire_json(FICHIER_PATIENTS, [])


def charger_regles():
    return lire_json(FICHIER_REGLES, [])


def charger_bio():
    return lire_json(FICHIER_BIO, {})


def charger_resultats():
    return lire_json(FICHIER_RESULTATS, {})


def sauver_resultats(resultats):
    ecrire_json(FICHIER_RESULTATS, resultats)


def erreur_condition(condition):
    """Renvoie un message d'erreur si la condition n'est pas lisible par expert_system.py, sinon None."""
    for symbole in OPERATEURS:  # même ordre de recherche que expert_system.condition_vraie
        if symbole in condition:
            morceaux = condition.split(symbole)
            if len(morceaux) != 2 or not morceaux[0].strip():
                return f"« {condition} » : écrire `donnee {symbole} valeur`"
            try:
                float(morceaux[1])
            except ValueError:
                return f"« {condition} » : la valeur « {morceaux[1].strip()} » n'est pas un nombre"
            return None
    return f"« {condition} » : aucun opérateur parmi {', '.join(OPERATEURS)}"


def erreurs_regle(regle):
    if not isinstance(regle, dict):
        return ["une règle doit être un objet JSON"]
    erreurs = []
    if not str(regle.get("alerte", "")).strip():
        erreurs.append("le champ `alerte` est obligatoire")
    for champ in ("medicaments", "conditions", "parmi"):
        if not isinstance(regle.get(champ, []), list):
            erreurs.append(f"`{champ}` doit être une liste")
    for condition in regle.get("conditions", []) + regle.get("parmi", []):
        message = erreur_condition(str(condition))
        if message:
            erreurs.append(message)
    minimum = regle.get("minimum", 0)
    if not isinstance(minimum, int) or minimum < 0:
        erreurs.append("`minimum` doit être un entier positif")
    elif minimum > len(regle.get("parmi", [])):
        erreurs.append("`minimum` est plus grand que le nombre de conditions dans `parmi`")
    return erreurs


def sauver_regles(regles):
    """Enregistre les règles si elles sont toutes valides. Renvoie la liste des erreurs (vide si OK)."""
    if not isinstance(regles, list):
        return ["le fichier doit contenir une liste de règles"]
    erreurs = []
    for numero, regle in enumerate(regles, start=1):
        erreurs += [f"Règle {numero} : {e}" for e in erreurs_regle(regle)]
    if not erreurs:
        ecrire_json(FICHIER_REGLES, regles)
    return erreurs


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
