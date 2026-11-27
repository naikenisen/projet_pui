#!/usr/bin/env python3
"""Convertit CIS_RCP.csv (RCP ANSM au format HTML) en un fichier Markdown par médicament.

Le CSV est un TSV à deux colonnes : Code_CIS, RCP_html.
Aucune dépendance externe : uniquement la bibliothèque standard.

Usage :
    python rcp_to_markdown.py                         # tout convertir
    python rcp_to_markdown.py --limit 20              # tester sur 20 médicaments
    python rcp_to_markdown.py --codes 61266250 62869109
"""

import argparse
import csv
import re
import sys
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent

# Classe CSS du paragraphe -> préfixe Markdown
TITRES = {
    "ammannexetitre": "## ",
    "ammannexetitre1": "## ",
    "ammannexetitre2": "### ",
    "ammannexetitre2bis": "### ",
    "ammannexetitre3": "#### ",
    "ammannexetitre4": "##### ",
    "ammtableautitre1": "#### ",
}
PUCES = {
    "ammlistepuces1": "- ",
    "ammlistepuces2": "  - ",
    "ammlistepuces3": "    - ",
}
CLASSES_GRAS = {"gras", "ammcorpstextegras", "ammcorpstextegrascar", "ammcorpstextegras0"}
CLASSES_ITALIQUE = {"italique", "bodytextitalic"}
CLASSES_IGNOREES = {"alignright"}  # liens « Retour en haut de la page »

BALISES_BLOC = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"}
BALISES_GRAS = {"b", "strong"}
BALISES_ITALIQUE = {"i", "em"}

SYMBOLES_PUCE = "·•▪●○■□◦"  # \uf0xx : puces des polices Symbol/Wingdings
PUCE_DEBUT = re.compile(rf"^(?:[{SYMBOLES_PUCE}]\s*|[§\-–o]\s+)+")
PUCE_SYMBOLE = re.compile(rf"^(?:[{SYMBOLES_PUCE}]\s*)+")
# Titres de rubrique RCP parfois écrits sans classe dédiée (ex. « 1. DENOMINATION DU MEDICAMENT »)
TITRE_RUBRIQUE = re.compile(
    r"^\d{1,2}\.\s+(DENOMINATION|COMPOSITION|FORME PHARMACEUTIQUE|DONNEES CLINIQUES|"
    r"PROPRIETES PHARMACOLOGIQUES|DONNEES PHARMACEUTIQUES|TITULAIRE|NUMERO|DATE DE PREMIERE|"
    r"DATE DE MISE A JOUR|DOSIMETRIE|INSTRUCTIONS POUR LA PREPARATION|CONDITIONS DE PRESCRIPTION)"
)
ETOILES_VIDES = re.compile(r"(?<!\*)\*\*\*\*(?!\*)")  # gras adjacents : **a****b** -> **ab**


def corriger_cp1252(texte: str) -> str:
    """Remplace les caractères de contrôle C1 (U+0080–U+009F) par leur équivalent Windows-1252
    (ex. U+0092 -> ’), fréquents dans ce fichier."""
    def remplace(m):
        try:
            return bytes([ord(m.group())]).decode("cp1252")
        except UnicodeDecodeError:
            return ""
    return re.sub(r"[\x80-\x9f]", remplace, texte)


def sans_emphase(texte: str) -> str:
    """Retire les marqueurs d'emphase Markdown et dé-échappe les astérisques littéraux."""
    return re.sub(r"(?<!\\)\*", "", texte).replace("\\*", "*").strip()


def entourer(contenu: str, marqueur: str) -> str:
    """Entoure le texte d'un marqueur d'emphase en conservant les espaces autour."""
    coeur = contenu.strip()
    if not coeur:
        return contenu
    # retire les marqueurs identiques imbriqués (mais pas les astérisques échappés \*)
    if marqueur == "**":
        coeur = re.sub(r"(?<!\\)\*\*", "", coeur)
    else:
        coeur = re.sub(r"(?<![\\*])\*(?!\*)", "", coeur)
    debut = contenu[: len(contenu) - len(contenu.lstrip())]
    fin = contenu[len(contenu.rstrip()):]
    return f"{debut}{marqueur}{coeur}{marqueur}{fin}"


class RcpVersMarkdown(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lignes: list[str] = []
        self.denomination: str | None = None
        self.date_maj: str | None = None
        # Pile de tampons inline (pour gérer gras / italique imbriqués)
        self.tampons: list[list[str]] = [[]]
        self.pile_inline: list[str | None] = []  # marqueur à appliquer à la fermeture
        self.bloc_classe: set[str] = set()
        self.ignorer_profondeur = 0
        # Tableaux
        self.profondeur_table = 0
        self.table: list[list[str]] | None = None
        self.cellule: list[str] | None = None
        self.dernier_etait_puce = False
        self.attente_denomination = False  # vrai juste après le titre « 1. DENOMINATION »

    # ---------- utilitaires ----------
    @staticmethod
    def _classes(attrs) -> set[str]:
        d = dict(attrs)
        return {c.lower() for c in (d.get("class") or "").split()}

    def _texte_bloc(self) -> str:
        # Vide la pile inline et renvoie le texte courant
        while len(self.tampons) > 1:
            self._fermer_inline()
        texte = "".join(self.tampons[0])
        self.tampons = [[]]
        return texte

    def _fermer_inline(self):
        contenu = "".join(self.tampons.pop())
        marqueur = self.pile_inline.pop() if self.pile_inline else None
        if marqueur:
            contenu = entourer(contenu, marqueur)
        self.tampons[-1].append(contenu)

    def _emettre(self, ligne: str, puce: bool = False):
        if self.cellule is not None:
            self.cellule.append(ligne)
            return
        if self.lignes and not (puce and self.dernier_etait_puce):
            self.lignes.append("")
        self.lignes.append(ligne)
        self.dernier_etait_puce = puce

    def _vider_bloc(self):
        brut = self._texte_bloc()
        classes = self.bloc_classe
        self.bloc_classe = set()
        # \n provient des <br>
        morceaux = [re.sub(r"[ \t\r\f\v]+", " ", m).strip() for m in brut.split("\n")]
        morceaux = [ETOILES_VIDES.sub("", m) for m in morceaux]
        morceaux = [m for m in morceaux if m.strip("* ")]
        if not morceaux:
            return
        texte = morceaux[0] if len(morceaux) == 1 else None

        if self.denomination is None and ("ammdenomination" in classes or self.attente_denomination):
            self.denomination = sans_emphase(" ".join(morceaux))
        if "datenotif" in classes:
            t = " ".join(morceaux)
            m = re.search(r"(\d{2}/\d{2}/\d{4})", t)
            self.date_maj = m.group(1) if m else None
            self._emettre(f"*{t}*")
            return

        prefixe_titre = next((TITRES[c] for c in classes if c in TITRES), None)
        if not prefixe_titre and TITRE_RUBRIQUE.match(sans_emphase(" ".join(morceaux))):
            prefixe_titre = "## "
        if prefixe_titre:
            t = sans_emphase(" ".join(morceaux))
            t = t.replace("Retour en haut de la page", "").strip()
            self.attente_denomination = "DENOMINATION" in t.upper() and self.denomination is None
            if t:
                if self.cellule is not None:
                    self._emettre(f"**{t}**")
                else:
                    self._emettre(prefixe_titre + t)
            return

        self.attente_denomination = False
        separateur = "<br>" if self.cellule is not None else "  \n"
        texte = texte if texte is not None else separateur.join(morceaux)

        prefixe_puce = next((PUCES[c] for c in classes if c in PUCES), None)
        if prefixe_puce:
            texte = PUCE_DEBUT.sub("", texte)
            if self.cellule is not None:
                self._emettre("• " + texte)
            else:
                self._emettre(prefixe_puce + texte, puce=True)
            return

        if PUCE_SYMBOLE.match(texte):  # puce « à la main » dans un paragraphe normal
            texte = PUCE_DEBUT.sub("", PUCE_SYMBOLE.sub("", texte))
            if self.cellule is not None:
                self._emettre("• " + texte)
            else:
                self._emettre("- " + texte, puce=True)
            return

        if classes & CLASSES_GRAS and self.cellule is None:
            texte = entourer(texte, "**")
        self._emettre(texte)

    # ---------- tableaux ----------
    def _fermer_table(self):
        lignes = [l for l in (self.table or []) if any(c.strip() for c in l)]
        self.table = None
        if not lignes:
            return
        nb_col = max(len(l) for l in lignes)
        def fmt(l):
            cells = [c.replace("|", "\\|") for c in l] + [""] * (nb_col - len(l))
            return "| " + " | ".join(cells) + " |"
        md = [fmt(lignes[0]), "| " + " | ".join(["---"] * nb_col) + " |"]
        md += [fmt(l) for l in lignes[1:]]
        self._emettre("\n".join(md))

    # ---------- callbacks HTMLParser ----------
    def handle_starttag(self, tag, attrs):
        classes = self._classes(attrs)
        if self.ignorer_profondeur:
            if tag in BALISES_BLOC:
                self.ignorer_profondeur += 1
            return
        if tag in ("script", "style", "head"):
            self.ignorer_profondeur = 1
            return

        if tag == "table":
            self.profondeur_table += 1
            if self.profondeur_table == 1:
                self._vider_bloc()
                self.table = []
            return
        if self.profondeur_table > 1:
            # tableaux imbriqués : aplatis dans la cellule courante
            if tag in ("td", "th", "tr"):
                self.tampons[-1].append(" ")
            return
        if tag == "tr" and self.table is not None:
            self.table.append([])
            return
        if tag in ("td", "th") and self.table is not None:
            if not self.table:
                self.table.append([])
            self.cellule = []
            self.tampons = [[]]
            return

        if tag in BALISES_BLOC:
            self._vider_bloc()
            if classes & CLASSES_IGNOREES:
                self.ignorer_profondeur = 1
                return
            self.bloc_classe = classes
            return
        if tag == "br":
            self.tampons[-1].append("\n")
            return
        if tag == "img":
            return

        # inline
        marqueur = None
        if tag in BALISES_GRAS or classes & CLASSES_GRAS:
            marqueur = "**"
        elif tag in BALISES_ITALIQUE or classes & CLASSES_ITALIQUE:
            marqueur = "*"
        elif tag == "sup":
            marqueur = None
        self.pile_inline.append(marqueur)
        self.tampons.append([])

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if self.ignorer_profondeur:
            if tag in BALISES_BLOC or tag in ("script", "style", "head"):
                self.ignorer_profondeur -= 1
            return

        if tag == "table":
            self.profondeur_table -= 1
            if self.profondeur_table == 0 and self.table is not None:
                self._fermer_table()
            return
        if self.profondeur_table > 1:
            return
        if tag in ("td", "th") and self.cellule is not None:
            self._vider_bloc()
            self.table[-1].append("<br>".join(self.cellule))
            self.cellule = None
            return
        if tag == "tr":
            return

        if tag in BALISES_BLOC:
            self._vider_bloc()
            return
        if tag in ("br", "img"):
            return
        if len(self.tampons) > 1:
            self._fermer_inline()

    def handle_data(self, data):
        if self.ignorer_profondeur:
            return
        self.tampons[-1].append(re.sub(r"\s+", " ", data).replace("*", "\\*"))

    def resultat(self) -> str:
        self._vider_bloc()
        if self.table is not None:
            self._fermer_table()
        texte = "\n".join(self.lignes)
        texte = re.sub(r"\n{3,}", "\n\n", texte)
        return texte.strip() + "\n"


def nom_fichier(code: str, denomination: str | None) -> str:
    if not denomination:
        return f"{code}.md"
    slug = unicodedata.normalize("NFKD", denomination).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "_", slug).lower()[:80].strip("_")
    return f"{code}_{slug}.md" if slug else f"{code}.md"


def convertir(code: str, html: str) -> tuple[str, str]:
    parser = RcpVersMarkdown()
    parser.feed(corriger_cp1252(html))
    parser.close()
    corps = parser.resultat()
    denom = parser.denomination or ""
    entete = [
        "---",
        f"code_cis: {code}",
        f'denomination: "{denom.replace(chr(34), chr(39))}"',
    ]
    if parser.date_maj:
        entete.append(f"date_mise_a_jour: {parser.date_maj}")
    entete += ["source: ANSM - Résumé des Caractéristiques du Produit", "---", ""]
    titre = f"# {denom}\n\n" if denom else f"# RCP {code}\n\n"
    return nom_fichier(code, parser.denomination), "\n".join(entete) + "\n" + titre + corps


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="?", default=DOSSIER / "CIS_RCP.csv", type=Path)
    ap.add_argument("-o", "--sortie", default=DOSSIER.parent / "ressources" / "rag" / "RCP", type=Path)
    ap.add_argument("--limit", type=int, help="nombre max de médicaments à convertir")
    ap.add_argument("--codes", nargs="+", help="ne convertir que ces codes CIS")
    args = ap.parse_args()

    csv.field_size_limit(sys.maxsize)
    args.sortie.mkdir(parents=True, exist_ok=True)
    codes = set(args.codes) if args.codes else None

    n = erreurs = vides = 0
    with open(args.csv, encoding="utf-8", newline="") as f:
        lecteur = csv.reader(f, delimiter="\t", quotechar='"')
        next(lecteur)  # en-tête : Code_CIS, RCP_html
        for ligne in lecteur:
            if len(ligne) < 2:
                continue
            code, html = ligne[0].strip(), ligne[1]
            if codes and code not in codes:
                continue
            if not html.strip():  # RCP absent dans le fichier source
                vides += 1
                continue
            try:
                nom, md = convertir(code, html)
                (args.sortie / nom).write_text(md, encoding="utf-8")
            except Exception as e:  # un RCP mal formé ne doit pas tout arrêter
                erreurs += 1
                print(f"[ERREUR] {code}: {e}", file=sys.stderr)
                continue
            n += 1
            if n % 500 == 0:
                print(f"{n} RCP convertis...", file=sys.stderr)
            if args.limit and n >= args.limit:
                break
            if codes and n >= len(codes):
                break

    print(f"Terminé : {n} fichiers Markdown dans {args.sortie} ({vides} RCP vides ignorés, {erreurs} erreurs)")


if __name__ == "__main__":
    main()
