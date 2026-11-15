# Analyse pharmaceutique d'ordonnances

## Installation

```bash
pip install -r requierments.txt
```

Créer un fichier `.env` à la racine du projet :

```
OPENROUTER_API_KEY=votre_cle
```

Toutes les commandes se lancent depuis la racine du projet.

## Fichiers

| Fichier | Rôle |
|---|---|
| `input.json` | Liste des patients et de leurs traitements |
| `main.py` | Analyse tous les patients avec le LLM, le RAG et le système expert |
| `generation.py` | Analyse un patient avec le LLM |
| `expert_system.py` | Applique les règles déterministes de `regles_expert.json` |
| `regles_expert.json` | Règles du système expert (ex : dose d'apixaban) |
| `indexation.py` | Indexe les PDF de `base_documentaire/` dans ChromaDB |
| `recuperation.py` | Cherche dans ChromaDB les passages utiles pour un patient |
| `bio_anormale.json` | Valeurs normales de la biologie, utilisées par `recuperation.py` |
| `app.py` | Interface Streamlit (analyse, base documentaire, règles, biologie) |
| `src/` | Fonctions utilisées par `app.py` (fichiers JSON, documents, analyse) |

## Liens entre les scripts

```
base_documentaire/ --> indexation.py --> chroma_db/

                       recuperation.py   (passages des recommandations)
                     /                  \
input.json --> main.py                    --> generation.py --> décision du LLM
                     \                  /
                       expert_system.py  (alertes)
```

Pour chaque patient, `main.py` récupère les passages utiles avec `recuperation.py` et les alertes avec `expert_system.py`, puis les transmet à `generation.py` qui rend la décision finale.
`recuperation.py` utilise la base `chroma_db/` créée par `indexation.py` : il faut lancer `indexation.py` avant `main.py`.

## Exécution

**Interface web**

```bash
streamlit run app.py
```

Les résultats des analyses sont enregistrés dans `resultats.json`.

![Liste des dossiers analysés : indicateurs, filtres, avis pharmaceutique, alertes du système expert et sources citées](interface_screenshot_1.png)

*Résultats d'analyse : pour chaque patient, profil, biologie, prescription, avis pharmaceutique, alertes du système expert et sources cliquables.*

![Consultation d'une source citée : le PDF s'ouvre directement à la page référencée](interface_screenshot_2.png)

*Consultation d'une source : un clic sur une référence ouvre le PDF à la page citée par le modèle.*

**Tous les patients**

```bash
python3 main.py
```

Affiche pour chaque patient : son identifiant, la décision (`PATIENT VALIDÉ` ou `INTERVENTION PHARMACEUTIQUE PROPOSÉE`), la justification et les sources citées par le modèle.

**Un patient avec le LLM**

```bash
python3 generation.py --idpatient PAT-0001
```

Affiche la décision et la justification.

**Système expert**

```bash
python3 expert_system.py --idpatient PAT-0001
```

Affiche les alertes détectées, ou `Aucune alerte`.

Les règles sont dans `regles_expert.json`. Une règle se déclenche si tous ses champs sont vérifiés :

| Champ | Signification |
|---|---|
| `medicaments` | tous ces médicaments (DCI) sont prescrits |
| `conditions` | toutes ces conditions sont vraies |
| `parmi` + `minimum` | au moins `minimum` de ces conditions sont vraies |
| `alerte` | message affiché quand la règle se déclenche |

Seul `alerte` est obligatoire. Une condition s'écrit `donnee operateur valeur`, par exemple `age >= 80`, avec les opérateurs `>=`, `<=`, `>`, `<`, `==`, `!=`.
Les données utilisables sont les champs du patient (`age`, `poids_kg`...), ceux de sa biologie (`creatinine_serique`...) et la dose de chaque médicament prescrit (`dose_apixaban`...).

**Indexation** (à lancer une fois, puis à chaque ajout de PDF)

```bash
python3 indexation.py
```

Affiche le nombre de passages indexés par PDF et crée le dossier `chroma_db/`.

**Récupération**

```bash
python3 recuperation.py --idpatient PAT-0001
```

Affiche les passages les plus pertinents pour le patient, avec leur PDF et leur page.
