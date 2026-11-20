"""Construit dataset/ : un fichier <id_patient>.json par patient.

1. TRAITEMENTS : on tire au hasard un jour où le patient a au moins une
   prescription active, et on garde les prescriptions actives ce jour-là.
2. BIO : pour chaque examen, le résultat le plus récent strictement avant ce jour.
3. CLINIQUE : toutes les colonnes de dictionnaire.json, en nombres.

Fichiers, colonnes, filtres et arrondis : dictionnaire.json.
Libellés et unités de biologie : dictionnaire_biologies.json.
Particularités de forme des CSV : utils.py.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from utils import (en_nombre, propre, regrouper_principes_actifs, renommer_lignes_contextuelles,
                   texte_posologie, unite_prise)

DOSSIER = Path(__file__).resolve().parent
DOSSIER_SORTIE = DOSSIER / "dataset"

GRAINE = 42
INCLURE_BIO_DU_JOUR = False

DICO = json.loads((DOSSIER / "dictionnaire.json").read_text(encoding="utf-8"))
DICO_BIO = json.loads((DOSSIER / "dictionnaire_biologies.json").read_text(encoding="utf-8"))

PRINCIPE_ACTIF = ["dosage_principe_actif", "unite_principe_actif"]


def lire_csv(source):
    cfg = DICO[source]
    df = pd.read_csv(DOSSIER / cfg["fichier"], dtype=str, keep_default_na=False)
    for col, valeurs in cfg.get("exclure", {}).items():
        df = df[~df[col].isin(valeurs)]
    return df[list(cfg["colonnes"])].rename(columns=cfg["colonnes"])


# --- TRAITEMENTS -------------------------------------------------------------
def charger_traitements():
    t = lire_csv("traitements")
    cle = [c for c in t.columns if c not in PRINCIPE_ACTIF]

    lignes = t.drop_duplicates(cle)[cle].join(regrouper_principes_actifs(t, cle), on=cle)
    lignes["pa"] = lignes["pa"].apply(lambda x: x if isinstance(x, list) else [])
    lignes["debut"] = pd.to_datetime(lignes["date_debut"]).dt.normalize()
    lignes["fin"] = pd.to_datetime(lignes["date_fin"], errors="coerce").dt.normalize()
    lignes["fin"] = lignes["fin"].fillna(lignes["debut"])  # sans date de fin : active le 1er jour
    return lignes.reset_index(drop=True), [c for c in cle if c != "id_patient"]


def choisir_jours(lignes):
    jours = lignes[["id_patient", "debut", "fin"]].copy()
    jours["jour"] = [pd.date_range(d, f, freq="D") for d, f in zip(jours["debut"], jours["fin"])]
    jours = jours.explode("jour").drop_duplicates(["id_patient", "jour"])
    rng = np.random.default_rng(GRAINE)
    choix = {pid: grp.iloc[rng.integers(len(grp))]
             for pid, grp in jours.sort_values(["id_patient", "jour"]).groupby("id_patient")["jour"]}
    return pd.Series(choix, name="jour_reference")


def traitement_json(r, colonnes):
    d = {c: r[c] for c in colonnes}
    d["principes_actifs"] = r["pa"]
    d["posologie"] = texte_posologie(r)
    d["date_debut"] = r["debut"].date().isoformat()
    d["date_fin"] = r["fin"].date().isoformat()
    if "unite_prise" in d:
        d["unite_prise"] = unite_prise(d["unite_prise"])
    if "quantite_par_jour" in d:
        d["quantite_par_jour"] = propre(pd.to_numeric(d["quantite_par_jour"].replace(",", "."), errors="coerce"))
    if "si_besoin" in d:
        d["si_besoin"] = d["si_besoin"] == "Oui"
    return d


# --- BIO ---------------------------------------------------------------------
def charger_bio():
    b = lire_csv("biologie")
    colonnes = [c for c in b.columns if c not in ("id_patient", "examen")]
    b["examen"] = b["examen"].str.replace(r"\s+", " ", regex=True).str.strip()
    b["valeur_num"] = en_nombre(b["valeur"])
    b = renommer_lignes_contextuelles(b, DICO_BIO["formule_leucocytaire"])

    b["nom"] = b["examen"].map(lambda e: DICO_BIO["examens"].get(e, e))
    b["unite"] = b["unite"].map(lambda u: DICO_BIO["unites"].get(u, u))

    # Même examen dans plusieurs unités : l'unité majoritaire garde le nom, les autres ont « [unité] »
    majoritaire = b.groupby("nom")["unite"].agg(lambda s: s.value_counts().index[0])
    b["cle"] = np.where(b["unite"] == b["nom"].map(majoritaire), b["nom"], b["nom"] + " [" + b["unite"] + "]")

    b["demande"] = pd.to_datetime(b["date_demande"])
    b["dh"] = pd.to_datetime(b["date_heure_examen"], format="%Y%m%d%H%M", errors="coerce")
    return b, colonnes


def bio_avant_jour(bio, jours):
    b = bio.join(jours, on="id_patient", how="inner")
    limite = b["jour_reference"] + pd.Timedelta(days=1 if INCLURE_BIO_DU_JOUR else 0)
    b = b[b["demande"] < limite].sort_values(["id_patient", "cle", "demande", "dh"])
    return b.groupby(["id_patient", "cle"], sort=False).tail(1)


def bio_json(r, colonnes):
    d = {c: r[c] for c in colonnes}
    d["valeur"] = propre(r["valeur_num"])
    d["date_demande"] = r["demande"].isoformat(sep=" ")
    d["date_heure_examen"] = r["dh"].isoformat(sep=" ") if pd.notna(r["dh"]) else None
    return d


# --- Assemblage --------------------------------------------------------------
def construire_dataset():
    lignes, colonnes_traitements = charger_traitements()
    jours = choisir_jours(lignes)

    presc = lignes.join(jours, on="id_patient")
    presc = presc[(presc["debut"] <= presc["jour_reference"]) & (presc["jour_reference"] <= presc["fin"])]
    bio, colonnes_bio = charger_bio()
    bio = bio_avant_jour(bio, jours)
    clin = lire_csv("clinique").set_index("id_patient").apply(en_nombre)
    arrondi = DICO["clinique"].get("arrondi", {})

    traitements = {pid: [traitement_json(r, colonnes_traitements) for _, r in g.iterrows()]
                   for pid, g in presc.groupby("id_patient")}
    biologie = {pid: {r["cle"]: bio_json(r, colonnes_bio) for _, r in g.iterrows()}
                for pid, g in bio.groupby("id_patient")}

    dataset = []
    for pid in sorted(jours.index):
        c = clin.loc[pid] if pid in clin.index else pd.Series(dtype=float)
        dataset.append({
            "patient": {
                "id": pid,
                "jour_reference": jours[pid].date().isoformat(),
                **{col: propre(c.get(col), arrondi.get(col)) for col in clin.columns},
                "biologie": biologie.get(pid, {}),
            },
            "traitements": traitements.get(pid, []),
        })
    return dataset


def main():
    dataset = construire_dataset()
    DOSSIER_SORTIE.mkdir(exist_ok=True)
    for ancien in DOSSIER_SORTIE.glob("*.json"):
        ancien.unlink()
    for entree in dataset:
        with open(DOSSIER_SORTIE / f"{entree['patient']['id']}.json", "w", encoding="utf-8") as f:
            json.dump(entree, f, ensure_ascii=False, indent=2)
    print(f"{len(dataset)} patients écrits dans {DOSSIER_SORTIE.name}/")


if __name__ == "__main__":
    main()
