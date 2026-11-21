"""Mise en forme HTML des résultats, des alertes et des règles, sans dépendance à Streamlit ni au LLM.

Utilisé par app.py (interface Streamlit) pour afficher les cartes, alertes et tableaux.
"""

import html
import re

from expert_system import OPERATEURS, normaliser

# ---------------------------------------------------------------------------
# Décisions et sources du LLM
# ---------------------------------------------------------------------------

# Catégorie de chaque décision, reconnue par un mot-clé (tolère les petites variantes de libellé du LLM).
# Les plus graves sont cherchées en premier.
CATEGORIES = (("intervention", "intervention"), ("verif", "verification"), ("surveill", "surveillance"), ("valid", "valide"))


def categorie(decision):
    """Code de la catégorie d'une décision : valide, surveillance, verification ou intervention (par défaut)."""
    texte = normaliser(decision)
    for mot_cle, code in CATEGORIES:
        if mot_cle in texte:
            return code
    return "intervention"


# Reconnaît par exemple "reco_sfd.pdf, page 12", "reco_sfd.pdf p. 12" ou "reco_sfd.pdf"
MOTIF_SOURCE = re.compile(r"([^,;\[\]()]+?\.pdf)\s*(?:[,\-–:]?\s*(?:pages?|p\.?)\s*(\d+))?", re.IGNORECASE)


def lire_source(source):
    """Renvoie (nom_pdf, page) si la source désigne un PDF, sinon None. page vaut 1 si elle n'est pas précisée."""
    trouve = MOTIF_SOURCE.search(str(source))
    if not trouve:
        return None
    return trouve.group(1).strip(), int(trouve.group(2) or 1)


LIBELLES_STATUT = {
    "intervention": "Intervention proposée",
    "verification": "Vérification proposée",
    "surveillance": "Surveillance proposée",
    "valide": "Validé",
    "erreur": "Erreur d'analyse",
    "non_analyse": "Non analysé",
}
# Les dossiers nécessitant une action apparaissent en premier
ORDRE_STATUTS = {"intervention": 0, "verification": 1, "surveillance": 2, "erreur": 3, "non_analyse": 4, "valide": 5}
COULEURS_STATUTS = {"intervention": "#A85A00", "verification": "#6B3FA0", "surveillance": "#0B4F8A",
                    "erreur": "#B42318", "non_analyse": "#7A8899", "valide": "#1E7A46"}


def statut(resultat):
    """Renvoie (code, libellé) du statut d'un dossier."""
    if resultat is None:
        code = "non_analyse"
    elif "erreur" in resultat:
        code = "erreur"
    else:
        code = categorie(resultat["decision"])
    return code, LIBELLES_STATUT[code]


def type_deduit(texte, categorie_decision):
    """Type d'un point d'une analyse antérieure aux points typés, d'après sa formulation et la décision."""
    debut = normaliser(texte)[:60]
    if "verifi" in debut:
        return "verification"
    if "surveill" in debut:
        return "surveillance"
    return "validation" if categorie_decision == "valide" else categorie_decision


# ---------------------------------------------------------------------------
# Dossier patient : profil, biologie, prescription
# ---------------------------------------------------------------------------

def profil_patient(patient):
    """Résumé lisible des caractéristiques du patient (les champs non renseignés sont omis)."""
    morceaux = []
    if patient.get("age") is not None:
        morceaux.append(f"{patient['age']} ans")
    for cle, unite in (("poids_kg", "kg"), ("taille_cm", "cm"), ("imc_kg_m2", "kg/m² (IMC)"), ("surface_corporelle_m2", "m² (SC)")):
        if patient.get(cle) is not None:
            morceaux.append(f"{patient[cle]} {unite}")
    return " · ".join(morceaux) or "Âge, poids et taille non renseignés"


def interpretation(nom, valeur, normes):
    norme = normes.get(nom)
    if norme is None or not isinstance(valeur, (int, float)):
        return ""
    if valeur < norme["min"]:
        return "Basse"
    if valeur > norme["max"]:
        return "Élevée"
    return "Normale"


def tableau_biologie(biologie, normes):
    """(lignes, classes) du tableau de biologie : valeurs anormales en premier, colorées en rouge."""
    mesures = sorted(
        ((nom, mesure, interpretation(nom, mesure.get("valeur"), normes)) for nom, mesure in biologie.items()),
        key=lambda m: {"Basse": 0, "Élevée": 0, "Normale": 1, "": 2}[m[2]],
    )
    lignes = [[nom, f"{mesure.get('valeur', '')} {mesure.get('unite') or ''}".strip(), etat,
               (mesure.get("date_heure_examen") or "")[:16]] for nom, mesure, etat in mesures]
    classes = ["anormal" if etat in ("Basse", "Élevée") else "" for _, _, etat in mesures]
    return lignes, classes


def lignes_a_modifier(resultat):
    """Numéros des lignes de prescription dont le LLM propose la modification (points « intervention »)."""
    return {n for point in (resultat or {}).get("points", []) for n in point.get("lignes_a_modifier", [])}


def tableau_prescription(traitements, a_modifier):
    """(lignes, classes) du tableau de prescription : lignes à modifier en rouge."""
    lignes = [[f"L{numero}", t.get("libelle_medicament", ""), t.get("posologie", ""), t.get("date_debut") or "",
               t.get("date_fin") or ""] for numero, t in enumerate(traitements, start=1)]
    classes = ["anormal" if numero in a_modifier else "" for numero in range(1, len(traitements) + 1)]
    return lignes, classes


def html_tableau(colonnes, lignes, classes_lignes=(), colonnes_courtes=()):
    """Tableau HTML qui s'adapte à la largeur (retour à la ligne, pas de défilement).

    classes_lignes : classe CSS de chaque ligne ("anormal" pour la colorer en rouge).
    colonnes_courtes : colonnes à ne jamais couper (identifiant, valeur, dates).
    """
    entete = "".join(f"<th>{html.escape(c)}</th>" for c in colonnes)
    corps = ""
    for numero, ligne in enumerate(lignes):
        classe = classes_lignes[numero] if numero < len(classes_lignes) else ""
        cellules = "".join(
            f'<td class="court">{html.escape(str(v))}</td>' if c in colonnes_courtes else f"<td>{html.escape(str(v))}</td>"
            for c, v in zip(colonnes, ligne)
        )
        corps += f'<tr class="{classe}">{cellules}</tr>'
    return f'<table class="tableau"><thead><tr>{entete}</tr></thead><tbody>{corps}</tbody></table>'


# ---------------------------------------------------------------------------
# Alertes du système expert
# ---------------------------------------------------------------------------

def mettre_en_forme(texte):
    """Texte du Thésaurus en HTML : un retour à la ligne par niveau (« Contre-indication avec : ») et par tiret."""
    texte = html.escape(texte, quote=False)
    texte = re.sub(
        r"\s*\b(Contre-indication|Association déconseillée|Précaution d'emploi|A prendre en compte)( avec)?\s*:",
        r"<br><b>\1\2 :</b>", texte,
    )
    texte = re.sub(r"\s+-\s+(?=\S)", "<br>• ", texte)
    return texte.removeprefix("<br>")


# Niveaux du Thésaurus ANSM : code, libellé affiché, du plus grave au moins grave
NIVEAUX = {"CI": "Contre-indication", "ASDEC": "Association déconseillée", "PE": "Précaution d'emploi",
           "APEC": "À prendre en compte"}
NIVEAUX_COMPLETS = {"CONTRE-INDICATION": "CI", "Association DECONSEILLEE": "ASDEC", "Précaution d'emploi": "PE",
                    "A prendre en compte": "APEC"}
# « Interaction A + B (niveau) : ... » (Thésaurus) et « Interaction pharmacocinétique A + B : ... » (DDI-Predictor)
_CODE = "(?:CI|ASDEC|PE|APEC)"
MOTIF_ALERTE_THESAURUS = re.compile(
    rf"^Interaction (.+?) \(({_CODE}(?: - {_CODE})*|{'|'.join(map(re.escape, NIVEAUX_COMPLETS))})\) : (.*)$", re.DOTALL
)
MOTIF_ALERTE_DDI = re.compile(r"^Interaction pharmacocinétique (.+?) : (.*)$", re.DOTALL)


def codes_niveau(regle):
    """« CI - ASDEC - APEC » -> ["CI", "ASDEC", "APEC"] ; [] pour une règle sans niveau (DDI-Predictor, personnalisée)."""
    niveau = regle.get("niveau") or ""
    if niveau in NIVEAUX_COMPLETS:
        return [NIVEAUX_COMPLETS[niveau]]
    return [code.strip() for code in niveau.split("-") if code.strip() in NIVEAUX]


def badge(texte, classe):
    return f'<span class="badge {classe}">{html.escape(texte)}</span>'


def html_alerte(alerte):
    """Alerte du système expert : niveau et titre, message, conduite à tenir et lignes de prescription."""
    alerte, _, prescription = alerte.partition(" [Prescription : ")
    entete = ""
    if trouve := MOTIF_ALERTE_THESAURUS.match(alerte):
        titre, niveau, alerte = trouve.groups()
        entete = "".join(badge(NIVEAUX[c], c.lower()) for c in codes_niveau({"niveau": niveau}))
        entete += f" <b>{html.escape(titre)}</b>"
    elif trouve := MOTIF_ALERTE_DDI.match(alerte):
        titre, alerte = trouve.groups()
        entete = f'{badge("Pharmacocinétique", "pk")} <b>{html.escape(titre)}</b>'
    message, _, conduite = alerte.partition(" Conduite à tenir : ")
    contenu = f'<div class="entete-alerte">{entete}</div>' if entete else ""
    contenu += mettre_en_forme(message)
    if conduite:
        contenu += f'<div class="complement"><b>Conduite à tenir :</b><br>{mettre_en_forme(conduite)}</div>'
    if prescription:
        contenu += f'<div class="prescription">Prescription : {html.escape(prescription.rstrip("]"))}</div>'
    return f'<div class="alerte">{contenu}</div>'


# ---------------------------------------------------------------------------
# Règles du système expert
# ---------------------------------------------------------------------------

SYMBOLES = {">=": "≥", "<=": "≤", "!=": "≠", "==": "=", ">": ">", "<": "<"}
DONNEES_PATIENT = {"age": ("âge", "ans"), "poids_kg": ("poids", "kg"), "taille_cm": ("taille", "cm"),
                   "imc_kg_m2": ("IMC", "kg/m²"), "surface_corporelle_m2": ("surface corporelle", "m²")}


def nombre_lisible(valeur):
    return f"{float(valeur):g}".replace(".", ",")


def de(nom):
    """« de daptomycine », « d'apixaban »."""
    return f"d'{nom}" if nom[:1].lower() in "aeiouyhéè" else f"de {nom}"


def phrase_condition(condition, unites):
    """« dose_kg_daptomycine < 10 » -> « dose de daptomycine < 10 mg/kg/jour »."""
    for symbole in OPERATEURS:  # même ordre de recherche que expert_system.condition_vraie
        if symbole in condition:
            nom, seuil = (morceau.strip() for morceau in condition.split(symbole, 1))
            break
    else:
        return condition
    if nom in DONNEES_PATIENT:
        donnee, unite = DONNEES_PATIENT[nom]
    elif nom.startswith("dose_jour_"):
        donnee, unite = f"dose {de(nom[10:])}", "mg/jour"
    elif nom.startswith("dose_kg_"):
        donnee, unite = f"dose {de(nom[8:])}", "mg/kg/jour"
    elif nom.startswith("dose_"):
        donnee, unite = f"dosage {de(nom[5:])}", ""
    else:
        donnee, unite = nom, unites.get(nom, "")
    try:
        seuil = nombre_lisible(seuil)
    except ValueError:
        pass
    return f"{donnee} {SYMBOLES[symbole]} {seuil} {unite}".strip()


def carte_regle_personnalisee(regle, unites):
    """Carte HTML : message d'alerte puis critères de déclenchement en langage courant."""
    medicaments = regle.get("medicaments", [])
    noms = [m if isinstance(m, str) else " ou ".join(m) for m in medicaments]
    titre = " + ".join(n[:1].upper() + n[1:] for n in noms) or "Tous les patients"
    origine = "Rédigée par l'assistant" if regle.get("demande") else "Règle personnalisée"

    criteres = []
    if noms:
        criteres.append(" et ".join(noms) + (" prescrits" if len(noms) > 1 else " prescrit")
                        + (" (sur des lignes différentes)" if len(noms) > 1 else ""))
    criteres += [phrase_condition(c, unites) for c in regle.get("conditions", [])]
    if regle.get("parmi"):
        choix = "".join(f"<li>{html.escape(phrase_condition(c, unites))}</li>" for c in regle["parmi"])
        criteres_parmi = f"au moins {regle.get('minimum', 0)} critère(s) parmi :<ul>{choix}</ul>"
    else:
        criteres_parmi = ""
    liste = "".join(f"<li>{html.escape(c)}</li>" for c in criteres)
    if criteres_parmi:
        liste += f"<li>{criteres_parmi}</li>"

    contenu = (
        f'<div class="entete">{badge(origine, "perso")}<span class="titre">{html.escape(titre)}</span></div>'
        f'<div class="bloc"><span class="etiquette">Alerte :</span> {html.escape(regle.get("alerte", ""))}</div>'
        f'<div class="bloc"><span class="etiquette">Se déclenche si :</span><ul>{liste}</ul></div>'
    )
    if regle.get("demande"):
        contenu += f'<div class="pied">Demande du pharmacien : « {html.escape(regle["demande"])} »</div>'
    return f'<div class="regle perso">{contenu}</div>'


def carte_regle_generique(regle):
    """Carte HTML : niveau, couple de médicaments, risque, conduite à tenir et DCI recherchées."""
    codes = codes_niveau(regle)
    if codes:
        badges = "".join(badge(NIVEAUX[c], c.lower()) for c in codes)
        classe = codes[0].lower()  # le plus grave donne la couleur de la carte
    else:
        badges, classe = badge("Pharmacocinétique", "pk"), ""
    titre = regle.get("titre") or " + ".join(m if isinstance(m, str) else "classe" for m in regle.get("medicaments", []))

    if "risque" in regle:
        contenu = f'<div class="bloc"><span class="etiquette">Risque :</span> {mettre_en_forme(regle["risque"])}</div>'
        if regle.get("conduite"):
            contenu += (f'<div class="bloc"><span class="etiquette">Conduite à tenir :</span><br>'
                        f'{mettre_en_forme(regle["conduite"])}</div>')
    else:
        contenu = f'<div class="bloc">{mettre_en_forme(regle["alerte"])}</div>'

    # DCI cherchées dans les libellés, utile surtout pour les classes du Thésaurus
    parties = titre.split(" + ")
    medicaments = regle.get("medicaments", [])
    if any(not isinstance(m, str) for m in medicaments):
        lignes_dci = ""
        for numero, medicament in enumerate(medicaments):
            nom = parties[numero] if len(parties) == len(medicaments) else f"Médicament {numero + 1}"
            dci = [medicament] if isinstance(medicament, str) else medicament
            puces = "".join(f'<span class="puce">{html.escape(d)}</span>' for d in dci)
            lignes_dci += f'<div class="bloc"><span class="etiquette">{html.escape(nom)} :</span> {puces}</div>'
        contenu += f"<details><summary>DCI recherchées dans la prescription</summary>{lignes_dci}</details>"

    return (f'<div class="regle {classe}"><div class="entete">{badges}'
            f'<span class="titre">{html.escape(titre)}</span></div>{contenu}'
            f'<div class="pied">{html.escape(regle.get("source", ""))}</div></div>')
