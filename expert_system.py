"""Système expert : règles déterministes appliquées à un patient, et rédaction de nouvelles règles par le LLM.

Les règles sont réparties dans deux fichiers :
- regles_generiques.json : Thésaurus ANSM des interactions médicamenteuses et ratios d'AUC de DDI-Predictor
  (documents_systeme_expert/), non modifiées depuis l'interface ;
- regles_personnalisees.json : règles propres à l'établissement (ex : dose d'apixaban, daptomycine 10 mg/kg),
  écrites à la main ou rédigées par le LLM à la demande d'un pharmacien.
Dans "medicaments", chaque élément est soit un nom (« ramipril »), soit une liste de noms équivalents
(les membres d'une classe du Thésaurus, ex : tous les anticoagulants oraux).
"""

import argparse
import functools
import json
import operator
import os
import re
import unicodedata

FICHIER_REGLES_GENERIQUES = "regles_generiques.json"
FICHIER_REGLES_PERSONNALISEES = "regles_personnalisees.json"

OPERATEURS = {">=": operator.ge, "<=": operator.le, "!=": operator.ne, "==": operator.eq, ">": operator.gt, "<": operator.lt}
CHAMPS_PATIENT = ("age", "poids_kg", "taille_cm", "imc_kg_m2", "surface_corporelle_m2")

# Conversion en mg de l'unité de prise et de l'unité du dosage des principes actifs
UNITES_PRISE_EN_MG = {"milligramme(s)": 1, "gramme(s)": 1000, "microgramme(s)": 0.001}
UNITES_DOSAGE_EN_MG = {"mg": 1, "g": 1000, "ug": 0.001}


# ---------------------------------------------------------------------------
# Lecture et écriture des règles
# ---------------------------------------------------------------------------

def lire_regles(chemin):
    if not os.path.exists(chemin):
        return []
    with open(chemin, encoding="utf-8") as fichier:
        return json.load(fichier)


def charger_regles_generiques():
    return lire_regles(FICHIER_REGLES_GENERIQUES)


def charger_regles_personnalisees():
    return lire_regles(FICHIER_REGLES_PERSONNALISEES)


def charger_regles():
    """Toutes les règles : personnalisées d'abord (leurs alertes apparaissent en tête), puis génériques."""
    return charger_regles_personnalisees() + charger_regles_generiques()


def erreur_condition(condition):
    """Renvoie un message d'erreur si la condition n'est pas lisible par condition_vraie, sinon None."""
    for symbole in OPERATEURS:  # même ordre de recherche que condition_vraie
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
    for medicament in regle.get("medicaments", []) if isinstance(regle.get("medicaments", []), list) else []:
        noms = [medicament] if isinstance(medicament, str) else medicament
        if not isinstance(noms, list) or not noms or not all(isinstance(n, str) and n.strip() for n in noms):
            erreurs.append("chaque médicament doit être un nom ou une liste de noms")
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


def sauver_regles_personnalisees(regles):
    """Enregistre les règles personnalisées si elles sont toutes valides. Renvoie la liste des erreurs (vide si OK)."""
    if not isinstance(regles, list):
        return ["le fichier doit contenir une liste de règles"]
    erreurs = []
    for numero, regle in enumerate(regles, start=1):
        erreurs += [f"Règle {numero} : {e}" for e in erreurs_regle(regle)]
    if not erreurs:
        with open(FICHIER_REGLES_PERSONNALISEES, "w", encoding="utf-8") as fichier:
            json.dump(regles, fichier, ensure_ascii=False, indent=2)
            fichier.write("\n")
    return erreurs


def ajouter_regle_personnalisee(regle):
    return sauver_regles_personnalisees(charger_regles_personnalisees() + [regle])


# ---------------------------------------------------------------------------
# Application des règles à un patient
# ---------------------------------------------------------------------------

def normaliser(texte):
    """Minuscules sans accents, pour comparer « Paracétamol » et « PARACETAMOL »."""
    texte = unicodedata.normalize("NFD", str(texte).lower())
    return "".join(c for c in texte if not unicodedata.combining(c))


@functools.lru_cache(maxsize=None)
def motif(nom):
    """Expression régulière qui cherche le nom en mot entier."""
    return re.compile(r"\b" + re.escape(normaliser(nom)) + r"\b")


class Prescription:
    """Lignes de traitement du patient, avec mémorisation des recherches (une règle par paire d'interaction)."""

    def __init__(self, traitements):
        self.traitements = traitements
        self.libelles = [normaliser(t["libelle_medicament"]) for t in traitements]
        self.cache = {}

    def lignes(self, medicament):
        """Numéros des lignes dont le libellé contient le médicament (ou l'un des noms si c'est une liste)."""
        noms = [medicament] if isinstance(medicament, str) else medicament
        trouvees = set()
        for nom in noms:
            if nom not in self.cache:
                self.cache[nom] = {i for i, libelle in enumerate(self.libelles) if motif(nom).search(libelle)}
            trouvees |= self.cache[nom]
        return trouvees


def associer(ensembles, prises=()):
    """Choisit une ligne différente pour chaque médicament de la règle, ou renvoie None si c'est impossible.

    Deux lignes distinctes sont exigées : une association fixe (ex : PERINDOPRIL+AMLODIPINE sur une seule
    ligne) ne déclenche pas d'interaction, et un médicament ne s'associe pas avec lui-même dans
    « ANTICOAGULANTS ORAUX + AUTRES ANTICOAGULANTS ORAUX ».
    """
    if not ensembles:
        return list(prises)
    for ligne in sorted(ensembles[0]):
        if ligne not in prises:
            resultat = associer(ensembles[1:], prises + (ligne,))
            if resultat is not None:
                return resultat
    return None


def est_nombre(valeur):
    return isinstance(valeur, (int, float)) and not isinstance(valeur, bool)


def dose_journaliere_mg(traitement):
    """Dose en mg par jour d'administration (quantité par jour × dosage), ou None si on ne peut pas la calculer."""
    quantite = traitement.get("quantite_par_jour")
    if not est_nombre(quantite) or quantite <= 0:
        return None
    unite = traitement.get("unite_prise")
    if unite in UNITES_PRISE_EN_MG:  # « 700 milligramme(s) par jour »
        return quantite * UNITES_PRISE_EN_MG[unite]
    principes = traitement["principes_actifs"]  # « 2 flacon(s) par jour » d'un flacon dosé à 350 mg
    if len(principes) == 1 and principes[0].get("unite") in UNITES_DOSAGE_EN_MG and est_nombre(principes[0].get("dosage")):
        return quantite * principes[0]["dosage"] * UNITES_DOSAGE_EN_MG[principes[0]["unite"]]
    return None


def lire_valeurs(dossier, regles, prescription):
    """Données utilisables dans les conditions : champs du patient, biologie et doses des médicaments des règles.

    Pour chaque médicament cité seul dans une règle à conditions :
    - dose_<médicament> : dosage du principe actif (s'il n'y en a qu'un, sinon on ne sait pas lequel) ;
    - dose_jour_<médicament> : dose prescrite en mg par jour d'administration ;
    - dose_kg_<médicament> : dose prescrite en mg/kg par jour d'administration (si le poids est connu).
    """
    patient = dossier["patient"]
    valeurs = {cle: valeur for cle, valeur in patient.items() if est_nombre(valeur)}
    for nom, mesure in patient["biologie"].items():
        if est_nombre(mesure.get("valeur")):
            valeurs[nom] = mesure["valeur"]

    for regle in regles:
        if not regle.get("conditions") and not regle.get("parmi"):
            continue
        for medicament in regle.get("medicaments", []):
            if not isinstance(medicament, str):
                continue
            lignes = prescription.lignes(medicament)
            if not lignes:
                continue
            traitement = prescription.traitements[min(lignes)]
            if len(traitement["principes_actifs"]) == 1:
                valeurs["dose_" + medicament] = traitement["principes_actifs"][0]["dosage"]
            dose_jour = dose_journaliere_mg(traitement)
            if dose_jour is not None:
                valeurs["dose_jour_" + medicament] = dose_jour
                if est_nombre(patient.get("poids_kg")) and patient["poids_kg"] > 0:
                    valeurs["dose_kg_" + medicament] = dose_jour / patient["poids_kg"]
    return valeurs


def condition_vraie(condition, valeurs):
    for symbole, comparer in OPERATEURS.items():
        if symbole in condition:
            nom, seuil = condition.split(symbole)
            valeur = valeurs.get(nom.strip())
            return valeur is not None and comparer(valeur, float(seuil))
    raise ValueError(f"Condition invalide : {condition}")


def regle_declenchee(regle, valeurs, prescription):
    """Renvoie les lignes de prescription concernées si la règle se déclenche, sinon None."""
    ensembles = [prescription.lignes(medicament) for medicament in regle.get("medicaments", [])]
    lignes = associer(ensembles)
    if lignes is None:
        return None

    for condition in regle.get("conditions", []):
        if not condition_vraie(condition, valeurs):
            return None

    nombre_vraies = 0
    for condition in regle.get("parmi", []):
        if condition_vraie(condition, valeurs):
            nombre_vraies += 1
    return lignes if nombre_vraies >= regle.get("minimum", 0) else None


def appliquer_regles(dossier, regles):
    prescription = Prescription(dossier["traitements"])
    valeurs = lire_valeurs(dossier, regles, prescription)

    alertes = []
    for regle in regles:
        lignes = regle_declenchee(regle, valeurs, prescription)
        if lignes is None:
            continue
        alerte = regle["alerte"]
        if lignes:
            libelles = " ; ".join(prescription.traitements[i]["libelle_medicament"] for i in lignes)
            alerte += f" [Prescription : {libelles}]"
        if alerte not in alertes:
            alertes.append(alerte)
    return alertes


def verifier_regles(dossier):
    """Alertes de toutes les règles (personnalisées et génériques) pour un patient."""
    return appliquer_regles(dossier, charger_regles())


# ---------------------------------------------------------------------------
# Rédaction d'une règle personnalisée par le LLM, à la demande d'un pharmacien
# ---------------------------------------------------------------------------

PROMPT_REGLE = """Tu es pharmacien clinicien hospitalier. Un pharmacien te demande d'ajouter une règle au système expert
qui analyse les prescriptions. Traduis sa demande en une règle JSON. Réponds uniquement avec un objet JSON.

Format d'une règle (seul "alerte" est obligatoire) :
- "medicaments" : liste des médicaments qui doivent TOUS être prescrits, en DCI française en minuscules (ex : "apixaban").
  Un élément peut être une liste de DCI équivalentes, dont une seule suffit (ex : ["ibuprofene", "ketoprofene"]).
  Le nom est cherché comme mot entier dans le libellé de la prescription (ex : « APIXABAN 5 MG (ELIQUIS), CPR »),
  sans tenir compte des majuscules et des accents.
- "conditions" : liste de conditions qui doivent TOUTES être vraies.
- "parmi" et "minimum" : au moins "minimum" conditions de la liste "parmi" doivent être vraies.
- "alerte" : message en français affiché au pharmacien quand la règle se déclenche : problème et conduite à tenir.

Une condition s'écrit exactement "donnee operateur nombre", avec un seul opérateur parmi >=, <=, >, <, ==, !=,
sans unité ni calcul (ex : "age >= 80", "DFG estimé (CKD-EPI) < 30"). Données disponibles :
- patient : age (ans), poids_kg, taille_cm, imc_kg_m2, surface_corporelle_m2 ;
- biologie, avec le nom exact du paramètre et son unité (convertis le seuil dans cette unité) :
{biologie}
- pour chaque médicament cité seul (pas dans une liste) dans "medicaments" :
  dose_<dci> = dosage de la spécialité prescrite (ex : dose_apixaban == 5 pour APIXABAN 5 MG),
  dose_jour_<dci> = dose prescrite en mg par jour d'administration,
  dose_kg_<dci> = dose prescrite en mg/kg par jour d'administration.

Exemples :
{{"medicaments": ["apixaban"], "conditions": ["dose_apixaban != 2.5"], "parmi": ["age >= 80", "poids_kg <= 60", "Créatinine (sang) >= 133"], "minimum": 2, "alerte": "Apixaban : la dose recommandée est 2,5 mg deux fois par jour (au moins 2 critères parmi âge ≥ 80 ans, poids ≤ 60 kg, créatinine ≥ 133 µmol/L)"}}
{{"medicaments": ["daptomycine"], "conditions": ["dose_kg_daptomycine < 10"], "alerte": "Daptomycine : la posologie recommandée est désormais de 10 mg/kg/jour, la dose prescrite est inférieure"}}

Si la demande ne peut pas s'exprimer avec ce format, réponds {{"erreur": "explication courte"}}."""


def variables_inconnues(regle, parametres_biologie):
    """Données des conditions qui ne correspondent à aucune donnée connue : la règle ne se déclencherait jamais."""
    connues = set(CHAMPS_PATIENT) | set(parametres_biologie)
    for medicament in regle.get("medicaments", []):
        if isinstance(medicament, str):
            connues |= {f"dose_{medicament}", f"dose_jour_{medicament}", f"dose_kg_{medicament}"}
    inconnues = []
    for condition in regle.get("conditions", []) + regle.get("parmi", []):
        for symbole in OPERATEURS:
            if symbole in condition:
                nom = condition.split(symbole)[0].strip()
                if nom not in connues and nom not in inconnues:
                    inconnues.append(nom)
                break
    return inconnues


def proposer_regle(demande, parametres_biologie):
    """Demande au LLM (le même que pour l'analyse des patients) de traduire la demande en règle.

    parametres_biologie : {nom exact du paramètre: unité}. Renvoie la règle validée, sans l'enregistrer.
    Lève ValueError si le LLM ne peut pas rédiger de règle valide.
    """
    from generation import MODEL, client  # import ici : generation importe ce module

    biologie = "\n".join(f"  {nom} ({unite})" for nom, unite in sorted(parametres_biologie.items()))
    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": PROMPT_REGLE.format(biologie=biologie)},
            {"role": "user", "content": demande},
        ],
        max_tokens=1024,
        temperature=0,
        response_format={"type": "json_object"},
        extra_body={"reasoning": {"enabled": False}},
    )
    reponse = completion.choices[0].message.content
    reponse = json.loads(reponse[reponse.find("{"):reponse.rfind("}") + 1])
    if "erreur" in reponse:
        raise ValueError(reponse["erreur"])

    regle = {champ: reponse[champ] for champ in ("medicaments", "conditions", "parmi", "minimum", "alerte")
             if reponse.get(champ) not in (None, "", [])}
    if "parmi" not in regle:
        regle.pop("minimum", None)
    if isinstance(regle.get("medicaments"), list):  # les noms sont cherchés en minuscules sans accents
        regle["medicaments"] = [
            m.strip().lower() if isinstance(m, str)
            else [n.strip().lower() if isinstance(n, str) else n for n in m] if isinstance(m, list)
            else m
            for m in regle["medicaments"]
        ]
    regle["source"] = "Rédigée par le LLM à la demande d'un pharmacien"
    regle["demande"] = demande

    erreurs = erreurs_regle(regle)
    if erreurs:
        raise ValueError("règle proposée invalide : " + " ; ".join(erreurs))
    return regle


# ---------------------------------------------------------------------------

def charger_patient(repertoire, patient_id):
    chemin = os.path.join(repertoire, f"{patient_id}.json")
    if not os.path.exists(chemin):
        raise SystemExit(f"Patient introuvable : {chemin}")
    with open(chemin, encoding="utf-8") as fichier:
        return json.load(fichier)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dossier", required=True, help="dossier contenant les fichiers JSON des patients")
    parser.add_argument("--idpatient", help="numéro du patient (nom du fichier JSON sans .json)")
    parser.add_argument("--nouvelle-regle", help="demande en langage naturel : le LLM rédige une règle personnalisée")
    args = parser.parse_args()

    if args.nouvelle_regle:
        parametres = {}
        for nom_fichier in sorted(os.listdir(args.dossier)):
            if nom_fichier.endswith(".json"):
                for nom, mesure in charger_patient(args.dossier, nom_fichier[:-5])["patient"]["biologie"].items():
                    parametres.setdefault(nom, mesure.get("unite") or "")
        regle = proposer_regle(args.nouvelle_regle, parametres)
        print(json.dumps(regle, ensure_ascii=False, indent=2))
        for nom in variables_inconnues(regle, parametres):
            print(f"Attention : la donnée « {nom} » n'existe pas, la condition sera toujours fausse.")
        if input("Enregistrer cette règle dans regles_personnalisees.json ? [o/N] ").strip().lower() == "o":
            erreurs = ajouter_regle_personnalisee(regle)
            print("\n".join(erreurs) if erreurs else "Règle enregistrée.")
    elif args.idpatient:
        alertes = verifier_regles(charger_patient(args.dossier, args.idpatient))
        if alertes:
            for alerte in alertes:
                print(alerte)
        else:
            print("Aucune alerte")
    else:
        parser.error("préciser --idpatient ou --nouvelle-regle")
