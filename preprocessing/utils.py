"""Particularités de forme des CSV : formats de nombres, codes, lignes à interpréter selon leur contexte."""

import numpy as np
import pandas as pd


def en_nombre(serie):
    return pd.to_numeric(serie.str.replace(",", ".", regex=False), errors="coerce")


def propre(x, decimales=None):
    if x is None or np.isnan(x):
        return None
    x = float(x) if decimales is None else round(float(x), decimales)
    return int(x) if x.is_integer() else x


# --- TRAITEMENTS -------------------------------------------------------------
def regrouper_principes_actifs(t, cle):
    # Le CSV a une ligne par principe actif (plus des lignes sans dosage) : une liste par prescription
    pa = t[t["dosage_principe_actif"] != ""].copy()
    pa["unite_min"] = pa["unite_principe_actif"].str.lower()
    pa = pa.drop_duplicates(cle + ["dosage_principe_actif", "unite_min"])
    pa["pa"] = [{"dosage": propre(d), "unite": u}
                for d, u in zip(en_nombre(pa["dosage_principe_actif"]), pa["unite_principe_actif"])]
    return pa.groupby(cle, sort=False)["pa"].agg(list)


def unite_prise(texte):
    return texte.split(" - ", 1)[-1]  # « gel - gélule(s) » -> « gélule(s) »


def texte_posologie(r):
    unite = unite_prise(r.get("unite_prise", ""))
    quantite = r.get("quantite_par_jour", "")
    morceaux = [f"{quantite} {unite} par jour" if quantite else f"{unite} si besoin"]

    m = r.get("moments_prise", "")
    if m == "Specifique":
        morceaux.append("horaires spécifiques")
    elif m:
        morceaux.append(m.replace(".", ", ").lower())

    f = r.get("frequence_jours", "")
    if "/" in f:
        n, d = f.split("/")
        morceaux.append(f"{n} jour(s) sur {d}")
    elif f == "TLJ":
        morceaux.append("tous les jours")
    elif f == "Autre":
        morceaux.append("rythme particulier")
    elif f:
        morceaux.append(f"fréquence {f}")

    return " — ".join(morceaux)


# --- BIO ---------------------------------------------------------------------
def renommer_lignes_contextuelles(b, formule_leucocytaire):
    bloc = ["id_patient", "date_heure_examen"]
    ex = b["examen"]

    # « soit » : avant les Leucocytes du bloc -> réticulocytes, après -> formule leucocytaire (ordre fixe)
    soit = b.loc[ex.isin(["soit", "soit:", "Soit :"]), bloc]
    i_leu = b.index.to_series()[ex == "Leucocytes"].groupby([b["id_patient"], b["date_heure_examen"]]).min()
    soit = soit.join(i_leu.rename("i_leu"), on=bloc)
    avant = soit.index < soit["i_leu"]
    rang = soit[~avant].groupby(bloc).cumcount() % len(formule_leucocytaire)
    b.loc[soit.index[avant], "examen"] = "soit → Réticulocytes"
    b.loc[rang.index, "examen"] = rang.map(lambda i: f"soit → {formule_leucocytaire[i]}")

    # « Soit » : en BAU/mL -> IgG anti-SARS-CoV-2, sinon log10 de la charge virale du bloc
    for i in b.index[ex.isin(["Soit:", "Soit"])]:
        r = b.loc[i]
        if r["unite"] == "BAU/mL":
            b.at[i, "examen"] = "soit → IgG anti-SARS-CoV-2 (BAU/mL)"
            continue
        meme_bloc = b[(b["id_patient"] == r["id_patient"]) & (b["date_heure_examen"] == r["date_heure_examen"])]
        cv = meme_bloc[meme_bloc["examen"].str.startswith("Charge virale")]
        match = cv[(np.log10(cv["valeur_num"].clip(lower=1)) - r["valeur_num"]).abs() < 0.05]
        b.at[i, "examen"] = f"soit → {match['examen'].iloc[0]} (log)" if len(match) else "soit → Charge virale (log)"

    # « Temps du patient/témoin » : Quick si le témoin < 20 s, sinon TCA
    t = b.loc[ex.isin(["Temps du patient", "Temps du témoin"]), bloc + ["examen", "valeur_num"]].copy()
    t["rang"] = t.groupby(bloc + ["examen"]).cumcount()
    temoin = t[t["examen"] == "Temps du témoin"].set_index(bloc + ["rang"])["valeur_num"]
    v = t.join(temoin.rename("temoin"), on=bloc + ["rang"])["temoin"]
    b.loc[t.index, "examen"] = t["examen"] + np.where(v < 20, " → Quick", " → TCA")
    return b
