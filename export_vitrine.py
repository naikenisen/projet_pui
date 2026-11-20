"""Exporte l'application en vitrine HTML statique, consultable sans Python, sans installation et sans internet.

Génère un dossier (par défaut vitrine/) et son archive zip :
    vitrine/
    ├── index.html        <- à ouvrir par double-clic (Chrome, Edge, Firefox, Safari)
    ├── LISEZ-MOI.txt
    └── documents/        <- les PDF de la base documentaire

La vitrine reprend l'interface Streamlit (liste des patients, dossier, avis pharmaceutique, sources, règles du système
expert, valeurs biologiques de référence) à partir des résultats déjà calculés dans resultats.json. Les actions qui
demandent le LLM ou la base vectorielle (lancer une analyse, indexer un document, rédiger une règle) sont désactivées.

Lancement depuis la racine du projet, après les analyses :
    python3 export_vitrine.py
    python3 export_vitrine.py --dossier dataset --sortie vitrine --masquer-identifiants

Par défaut, les images des PDF sont recompressées pour que l'archive puisse être envoyée par mail
(environ 15 Mo au lieu de 34 Mo) ; --pdf-originaux copie les PDF tels quels.
"""

import argparse
import html
import json
import os
import shutil
from datetime import datetime

import pymupdf

from expert_system import charger_regles_generiques, charger_regles_personnalisees, normaliser, verifier_regles
from indexation import DOSSIER_PDF
from src.affichage import (
    LIBELLES_STATUT,
    NIVEAUX,
    ORDRE_STATUTS,
    carte_regle_generique,
    carte_regle_personnalisee,
    categorie,
    codes_niveau,
    html_alerte,
    html_tableau,
    lignes_a_modifier,
    lire_source,
    profil_patient,
    statut,
    tableau_biologie,
    tableau_prescription,
    type_deduit,
)
from src.donnees import DOSSIER_PATIENTS, charger_bio, charger_patients, charger_resultats

NOM_ETABLISSEMENT = "CHU Dijon Bourgogne"
NOM_LOGICIEL = "Logiciel d'analyse pharmaceutique assistée par IA"
MODELE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "vitrine_modele.html")
MARQUEUR_DONNEES = "/*__DONNEES__*/null"


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

def copier_pdf(source, destination, compresser):
    """Copie le PDF ; avec compresser, réduit ses images (la page reste lisible) et garde le plus petit des deux."""
    shutil.copyfile(source, destination)
    if not compresser:
        return
    try:
        with pymupdf.open(source) as document:
            document.rewrite_images(dpi_threshold=120, dpi_target=100, quality=60)
            document.save(destination + ".tmp", garbage=4, deflate=True)
        if os.path.getsize(destination + ".tmp") < os.path.getsize(destination):
            os.replace(destination + ".tmp", destination)
    except Exception as erreur:  # PDF que PyMuPDF ne sait pas réécrire : on garde l'original
        print(f"  {os.path.basename(source)} : compression impossible ({erreur}), copie de l'original")
    finally:
        if os.path.exists(destination + ".tmp"):
            os.remove(destination + ".tmp")


def exporter_documents(dossier_sortie, compresser):
    """Copie les PDF de la base documentaire. Renvoie [{nom, pages, taille_ko}]."""
    dossier_documents = os.path.join(dossier_sortie, "documents")
    os.makedirs(dossier_documents, exist_ok=True)
    documents = []
    noms = sorted(f for f in os.listdir(DOSSIER_PDF) if f.lower().endswith(".pdf")) if os.path.isdir(DOSSIER_PDF) else []
    for nom in noms:
        destination = os.path.join(dossier_documents, nom)
        copier_pdf(os.path.join(DOSSIER_PDF, nom), destination, compresser)
        with pymupdf.open(destination) as document:
            pages = document.page_count
        documents.append({"nom": nom, "pages": pages, "taille_ko": os.path.getsize(destination) // 1024})
        print(f"  {nom} : {pages} pages, {documents[-1]['taille_ko']} Ko")
    return documents


# ---------------------------------------------------------------------------
# Avis pharmaceutique (même rendu que afficher_avis dans app.py, liens en boutons HTML)
# ---------------------------------------------------------------------------

class Alertes:
    """Alertes du système expert citées dans les avis, numérotées une seule fois (data-alerte="numéro")."""

    def __init__(self):
        self.liste = []
        self.numeros = {}

    def numero(self, alerte):
        if alerte not in self.numeros:
            self.numeros[alerte] = len(self.liste)
            self.liste.append(html_alerte(alerte))
        return self.numeros[alerte]


def lien_alerte(alerte, alertes):
    return (f'<button class="lien-source" data-alerte="{alertes.numero(alerte)}" '
            f'title="{html.escape(alerte)}">Alerte experte</button>')


def lien_document(nom, page, texte=None):
    texte = texte or f"{nom}, p. {page}"
    return (f'<button class="lien-source" data-doc="{html.escape(nom)}" data-page="{page}" '
            f'title="Ouvrir {html.escape(nom)} à la page {page}">{html.escape(texte)}</button>')


def html_point(point, categorie_decision, alertes):
    type_ = point.get("type") or type_deduit(point["texte"], categorie_decision)
    if point["sources"]:
        liens = "".join(
            lien_alerte(source["texte"], alertes) if source["type"] == "alerte"
            else lien_document(source["source"], source["page"])
            for source in point["sources"]
        )
    else:
        liens = ('<span class="source-llm">connaissances du modèle uniquement : ni alerte ni recommandation</span>')
    return (f'<div class="cadre {type_}"><p class="point {type_}">{html.escape(point["texte"])}</p>'
            f'<div class="sources"><span class="titre-sources">Sources</span>{liens}</div></div>')


def html_avis(resultat, alertes):
    if resultat is None:
        return '<div class="info">Dossier non analysé.</div>'
    if "erreur" in resultat:
        return (f'<div class="decision erreur">Échec de l\'analyse ({html.escape(resultat["date"])})</div>'
                f'<pre class="code">{html.escape(resultat["erreur"])}</pre>')

    classe = categorie(resultat["decision"])
    contenu = f'<div class="decision {classe}">{html.escape(resultat["decision"])}</div>'
    if "points" in resultat:
        contenu += "".join(html_point(point, classe, alertes) for point in resultat["points"])
    else:  # analyse faite avant le passage aux points : justification en un paragraphe
        contenu += f'<p class="justification">{html.escape(resultat["justification"])}</p>'
        liens = [lien_document(*document, texte=source) for source in resultat.get("sources", [])
                 if (document := lire_source(source))]
        liens += [lien_alerte(alerte, alertes) for alerte in resultat.get("alertes", [])]
        if liens:
            contenu += f'<div class="sources">{"".join(liens)}</div>'
    return contenu + f'<div class="discret">Analyse réalisée le {html.escape(resultat["date"])}</div>'


# ---------------------------------------------------------------------------
# Données de la vitrine
# ---------------------------------------------------------------------------

def donnees_patients(patients, resultats, normes, masquer, alertes):
    """Un dictionnaire par patient, dans l'ordre de la liste de l'application (dossiers à traiter en premier)."""
    # Identifiant affiché : celui du dossier, ou « Patient 01 »... dans l'ordre des fichiers
    affiches = {d["patient"]["id"]: f"Patient {numero:02d}" if masquer else d["patient"]["id"]
                for numero, d in enumerate(patients, start=1)}
    statuts = {d["patient"]["id"]: statut(resultats.get(d["patient"]["id"]))[0] for d in patients}
    tries = sorted(patients, key=lambda d: ORDRE_STATUTS[statuts[d["patient"]["id"]]])

    lignes = []
    for dossier in tries:
        patient = dossier["patient"]
        resultat = resultats.get(patient["id"])
        code, etat = statut(resultat)
        traitements = dossier["traitements"]
        biologie = patient.get("biologie", {})
        a_modifier = lignes_a_modifier(resultat)

        lignes_bio, classes_bio = tableau_biologie(biologie, normes)
        lignes_presc, classes_presc = tableau_prescription(traitements, a_modifier)
        try:
            alertes_actuelles = verifier_regles(dossier)
        except Exception as erreur:
            print(f"  {patient['id']} : règles non appliquées ({erreur})")
            alertes_actuelles = []

        identifiant = affiches[patient["id"]]
        lignes.append({
            "id": identifiant,
            "code": code,
            "etat": etat,
            "age": f"{patient['age']} ans" if patient.get("age") is not None else "—",
            "nb_lignes": len(traitements),
            "nb_alertes": len((resultat or {}).get("alertes", [])),
            "date": (resultat or {}).get("date", ""),
            "recherche": normaliser(" ".join([identifiant] + [str(t.get("libelle_medicament", "")) for t in traitements])),
            "profil": profil_patient(patient),
            "jour_reference": patient.get("jour_reference") or "",
            "nb_bio": len(biologie),
            "bio": html_tableau(["Paramètre", "Valeur", "Interprétation", "Date"], lignes_bio, classes_bio)
                   if biologie else "",
            "a_modifier": bool(a_modifier),
            "prescription": html_tableau(["N°", "Médicament", "Posologie", "Début", "Fin"], lignes_presc, classes_presc,
                                         colonnes_courtes=("N°", "Début", "Fin")),
            "avis": html_avis(resultat, alertes),
            "alertes_regles": "".join(html_alerte(a) for a in alertes_actuelles),
        })
    return lignes


def donnees_regles(unites):
    generiques = []
    for regle in charger_regles_generiques():
        generiques.append({
            "html": carte_regle_generique(regle),
            "recherche": normaliser(regle["alerte"]) + " " + json.dumps(regle.get("medicaments", []), ensure_ascii=False),
            "niveaux": [NIVEAUX[c] for c in codes_niveau(regle)] or ["Pharmacocinétique"],
            "source": regle.get("source", ""),
        })
    return {
        "personnalisees": [carte_regle_personnalisee(r, unites) for r in charger_regles_personnalisees()],
        "generiques": generiques,
        "niveaux": list(NIVEAUX.values()) + ["Pharmacocinétique"],
    }


def donnees_biologie(patients, normes):
    references = html_tableau(
        ["Clé", "Libellé", "Unité", "Borne inférieure", "Borne supérieure"],
        [[cle, n.get("libelle", ""), n.get("unite", ""), f"{n['min']:g}", f"{n['max']:g}"] for cle, n in normes.items()],
        colonnes_courtes=("Unité", "Borne inférieure", "Borne supérieure"),
    )
    parametres = {}
    for d in patients:
        for cle, mesure in d["patient"].get("biologie", {}).items():
            parametres.setdefault(cle, [cle, mesure.get("unite") or "", 0])
            parametres[cle][2] += 1
    lignes = sorted(parametres.values(), key=lambda p: -p[2])
    presents = html_tableau(["Clé", "Unité", "Nombre de patients"], lignes, colonnes_courtes=("Nombre de patients",))
    return {"references": references, "presents": presents, "nb_presents": len(lignes)}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

LISEZ_MOI = """{logiciel} - {etablissement}
Version de démonstration exportée le {date}

POUR CONSULTER : double-cliquer sur le fichier « index.html ».
Il s'ouvre dans le navigateur internet (Chrome, Edge, Firefox ou Safari). Aucune installation ni connexion internet
n'est nécessaire. Si le fichier a été reçu dans un zip, il faut d'abord extraire tout le dossier (clic droit >
« Extraire tout ») : sinon les documents PDF ne s'ouvrent pas.

Contenu :
- {nb_patients} dossiers patients analysés, avec la biologie, la prescription et l'avis pharmaceutique proposé ;
- les recommandations de la base documentaire (dossier « documents »), qui s'ouvrent à la page citée ;
- les règles du système expert et les valeurs biologiques de référence.

Il s'agit d'une vitrine : les résultats sont ceux déjà calculés, les boutons d'analyse et d'ajout de documents
sont désactivés.
"""


def exporter(repertoire, sortie, compresser, masquer):
    patients = charger_patients(repertoire)
    if not patients:
        raise SystemExit(f"Aucun dossier patient dans « {repertoire} ».")
    resultats = charger_resultats()
    normes = charger_bio()

    if os.path.isdir(sortie):
        # Ne remplace qu'une vitrine précédente : protège d'un --sortie qui désignerait un autre dossier
        if os.listdir(sortie) and not os.path.exists(os.path.join(sortie, "index.html")):
            raise SystemExit(f"« {sortie} » existe et n'est pas une vitrine : choisir un autre --sortie.")
        shutil.rmtree(sortie)
    os.makedirs(sortie)

    print(f"Documents ({'images recompressées' if compresser else 'originaux'}) :")
    documents = exporter_documents(sortie, compresser)

    print(f"Patients : {len(patients)} dossiers de « {repertoire} »")
    alertes = Alertes()
    lignes = donnees_patients(patients, resultats, normes, masquer, alertes)
    compte = {code: sum(p["code"] == code for p in lignes) for code in LIBELLES_STATUT}
    unites = {cle: m.get("unite") or "" for d in patients for cle, m in d["patient"].get("biologie", {}).items()}

    date = datetime.now().strftime("%d/%m/%Y à %H:%M")
    donnees = {
        "etablissement": NOM_ETABLISSEMENT,
        "logiciel": NOM_LOGICIEL,
        "repertoire": os.path.basename(os.path.normpath(repertoire)),
        "date_export": date,
        "documents": documents,
        "patients": lignes,
        "compte": compte,
        "alertes": alertes.liste,
        "regles": donnees_regles(unites),
        "biologie": donnees_biologie(patients, normes),
    }

    with open(MODELE, encoding="utf-8") as fichier:
        modele = fichier.read()
    # « </ » et « <!-- » échappés : un texte des données ne peut pas fermer ni perturber la balise <script>
    json_donnees = json.dumps(donnees, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\u0021--")
    titre = html.escape(f"{NOM_ETABLISSEMENT} - Analyse pharmaceutique (démonstration)")
    page = modele.replace("__TITRE__", titre).replace(MARQUEUR_DONNEES, json_donnees)
    with open(os.path.join(sortie, "index.html"), "w", encoding="utf-8") as fichier:
        fichier.write(page)
    with open(os.path.join(sortie, "LISEZ-MOI.txt"), "w", encoding="utf-8") as fichier:
        fichier.write(LISEZ_MOI.format(logiciel=NOM_LOGICIEL, etablissement=NOM_ETABLISSEMENT, date=date,
                                       nb_patients=len(lignes)))

    archive = shutil.make_archive(sortie, "zip", root_dir=os.path.dirname(os.path.abspath(sortie)),
                                  base_dir=os.path.basename(os.path.abspath(sortie)))
    print(f"\nVitrine : {os.path.join(sortie, 'index.html')} ({os.path.getsize(os.path.join(sortie, 'index.html')) // 1024} Ko)")
    print(f"Archive : {archive} ({os.path.getsize(archive) / 1e6:.1f} Mo)")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))  # chemins relatifs du projet (resultats.json, base_documentaire...)
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dossier", default=DOSSIER_PATIENTS, help="dossier des patients à exporter (défaut : %(default)s)")
    parser.add_argument("--sortie", default="vitrine", help="dossier de la vitrine, remplacé s'il existe (défaut : %(default)s)")
    parser.add_argument("--pdf-originaux", action="store_true", help="copier les PDF sans recompresser leurs images")
    parser.add_argument("--masquer-identifiants", action="store_true",
                        help="remplacer les identifiants des patients par « Patient 01 », « Patient 02 »...")
    args = parser.parse_args()
    exporter(args.dossier, args.sortie, compresser=not args.pdf_originaux, masquer=args.masquer_identifiants)
