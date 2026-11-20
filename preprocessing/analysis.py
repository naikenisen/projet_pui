"""Combien de patients le filtre 1 va-t-il extraire (= nombre de patients dans dataset.json) ?

Utilise exactement les mêmes fonctions et la même graine que preprocessing.py.
"""

import pandas as pd

from preprocessing import (
    GRAINE, STATUTS_EXCLUS, bio_avant_jour, charger_bio, charger_clinique,
    charger_traitements, choisir_jours, lire_csv, prescriptions_du_jour,
)

brut = lire_csv("ANONYMISED_TRAITEMENTS.csv")
print("=== TRAITEMENTS bruts")
print(f"lignes CSV                      : {len(brut)}")
print(f"patients                        : {brut['id_patient'].nunique()}")
print("lignes par statut               :", brut["statut"].replace("", "(vide)").value_counts().to_dict())

toutes = charger_traitements(statuts_exclus=set())
lignes = charger_traitements()
print(f"\n=== Prescriptions regroupées (1 ligne CSV par principe actif -> 1 prescription)")
print(f"prescriptions, tous statuts     : {len(toutes)}  ({toutes['id_patient'].nunique()} patients)")
print(f"sans statuts {sorted(STATUTS_EXCLUS)}      : {len(lignes)}  ({lignes['id_patient'].nunique()} patients)")

jours = choisir_jours(lignes)
presc = prescriptions_du_jour(lignes, jours)
n_presc = presc.groupby("id_patient").size()

print(f"\n=== FILTRE 1 (graine = {GRAINE})")
print(f">>> PATIENTS DANS LE JSON       : {len(jours)}")
print(f"perdus car seulement annulé/supprimé : {brut['id_patient'].nunique() - len(jours)}")
print(f"prescriptions concomitantes / patient : médiane {n_presc.median():.0f}, "
      f"min {n_presc.min()}, max {n_presc.max()}, total {n_presc.sum()}")
print("jours de référence par année    :", jours.dt.year.value_counts().sort_index().to_dict())

clin = charger_clinique()
avec_clin = jours.index.isin(clin.index)
print(f"\n=== Données associées aux {len(jours)} patients")
print(f"avec données CLINIQUE           : {avec_clin.sum()}")
print(f"  dont poids connu              : {clin.reindex(jours.index)['poids_kg'].notna().sum()}")
print(f"  dont taille connue            : {clin.reindex(jours.index)['taille_cm'].notna().sum()}")

bio = bio_avant_jour(charger_bio(), jours)
n_bio = bio.groupby("id_patient").size().reindex(jours.index, fill_value=0)
print(f"FILTRE 2 - avec >= 1 résultat bio avant le jour : {(n_bio > 0).sum()}")
print(f"  examens / patient (si > 0)    : médiane {n_bio[n_bio > 0].median():.0f}, max {n_bio.max()}")
print(f"  sans aucune bio avant le jour : {(n_bio == 0).sum()}")
print(f"avec CLINIQUE + bio + traitements : {(avec_clin & (n_bio > 0).to_numpy()).sum()}")
