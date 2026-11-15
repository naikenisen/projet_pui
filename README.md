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
| `main.py` | Analyse tous les patients avec le LLM |
| `generation.py` | Analyse un patient avec le LLM |
| `expert_system.py` | Règles déterministes (dose d'apixaban) |
| `indexation.py` | Indexe les PDF de `base_documentaire/` dans ChromaDB |
| `recuperation.py` | Cherche dans ChromaDB les passages utiles pour un patient |

## Liens entre les scripts

```
input.json --> main.py --> generation.py --> décision du LLM

base_documentaire/ --> indexation.py --> chroma_db/ --> recuperation.py
```

`main.py` appelle `generation.py` pour chaque patient.
`recuperation.py` utilise la base `chroma_db/` créée par `indexation.py`.
`recuperation.py` et `expert_system.py` ne sont pas encore reliés à `main.py`.

## Exécution

**Tous les patients**

```bash
python3 main.py
```

Affiche pour chaque patient : son identifiant, la décision (`PATIENT VALIDÉ` ou `INTERVENTION PHARMACEUTIQUE PROPOSÉE`) et la justification.

**Un patient avec le LLM**

```bash
python3 generation.py --patient PAT-0001
```

Affiche la décision et la justification.

**Système expert**

```bash
python3 expert_system.py --patient PAT-0001
```

Affiche les alertes détectées, ou `Aucune alerte`.

**Indexation** (à lancer une fois, puis à chaque ajout de PDF)

```bash
python3 indexation.py
```

Affiche le nombre de passages indexés par PDF et crée le dossier `chroma_db/`.

**Récupération**

```bash
python3 recuperation.py --patient PAT-0001
```

Affiche les passages les plus pertinents pour le patient, avec leur PDF et leur page.
