"""
reports/extractor.py
====================
Extraction de données depuis les rapports d'essai PDF.

Pipeline :
    PDF
      ↓
    pdfplumber (lecture directe, pas d'OCR)
      ↓
    extract_header(text)       → regex → dict champs Partie 1
    extract_resultats_pdf(...) → table parse → list dicts Partie 2
      ↓
    { 'header': {...}, 'resultats': [...], 'raw_text': '...' }
"""

import re
import pdfplumber
from datetime import datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(raw: str):
    """Convertit DD/MM/YYYY, DD-MM-YYYY, DD/MM/YY ou DD-MM-YY en objet date Python."""
    if not raw:
        return None
    raw = raw.strip().replace("-", "/")
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _field(pattern: str, text: str, group: int = 1, flags=re.IGNORECASE) -> str:
    """Extrait un groupe capturé depuis le texte brut via regex."""
    m = re.search(pattern, text, flags)
    return m.group(group).strip() if m else ""


# ---------------------------------------------------------------------------
# Part 1 — Header extraction
# ---------------------------------------------------------------------------

def extract_header(text: str) -> dict:
    """
    Extrait les 11 champs de l'entête depuis le texte brut pdfplumber.
    """

    client = _field(r"Client\s*:\s*(.+?)(?=\s{2,}|Date|\n|$)", text)

    date_emission = _parse_date(_field(
        r"Date\s+d.émission\s*:\s*(\d{2}[-/]\d{2}[-/]\d{4})", text
    ))

    ose = _field(
        r"Objet\s+soumis.{0,20}essai.{0,10}:\s*(.+?)(?=\s{2,}|Date|\n|$)", text
    )

    code = _field(r"Code\s*:\s*(.+?)(?=\s{2,}|Date|\n|$)", text)

    bon_de_commande = _field(
        r"Bon\s+de\s+commande\s+N°\s*:\s*(.+?)(?=\s{2,}|Date|\n|$)", text
    )

    nature_echantillon = _field(
        r"Nature\s+de\s+l.échantillon\s*:\s*(.+?)(?=\s{2,}|\n|$)", text
    )

    transport_par = _field(
        r"Transport\s+effectué\s+par\s*:\s*(.+?)(?=\s{2,}|\n|$)", text
    )

    date_prelevement = _parse_date(_field(
        r"Date\s+du\s+prélèvement\s*:\s*(\d{2}[-/]\d{2}[-/]\d{4})", text
    ))

    date_reception = _parse_date(_field(
        r"Date\s+de\s+réception\s*:\s*(\d{2}[-/]\d{2}[-/]\d{4})", text
    ))

    date_debut_essais = _parse_date(_field(
        r"Date\s+du\s+début\s+d.essais\s*:\s*(\d{2}[-/]\d{2}[-/]\d{4})", text
    ))

    responsable = _field(
        r"Responsable\s+(?:du\s+)?laboratoire\s*\n?\s*([A-Z][A-Za-zÀ-ÿ\s]{3,30})", text
    )

    return {
        "client":                  client,
        "date_emission":           date_emission,
        "ose":                     ose,
        "code":                    code,
        "bon_de_commande":         bon_de_commande,
        "nature_echantillon":      nature_echantillon,
        "transport_par":           transport_par,
        "date_prelevement":        date_prelevement,
        "date_reception":          date_reception,
        "date_debut_essais":       date_debut_essais,
        "responsable_laboratoire": responsable,
    }


# ---------------------------------------------------------------------------
# Part 2 — Results extraction (pdfplumber tables)
# ---------------------------------------------------------------------------

def extract_resultats_pdf(page) -> list[dict]:
    """
    Extrait le tableau des résultats depuis une page pdfplumber.
    Colonnes retenues : Essais | Résultat | Unités
    Colonne ignorée   : Critère norme interne DICK

    Détecte automatiquement la table RESULTATS via son en-tête
    (contient "Essais" et "Résultat") et gère le décalage de colonne
    si une colonne '#' est présente en position 0.
    """
    rows = []
    tables = page.extract_tables()

    for table in tables:
        if not table or len(table) < 2:
            continue

        # Chercher la ligne d'en-tête qui contient "Essais" et "Résultat"
        header_row = None
        col_offset = 0
        for row in table:
            if not row:
                continue
            row_text = " ".join((c or "").lower() for c in row)
            if "essai" in row_text and "sultat" in row_text:
                header_row = row
                # Détecter le décalage : si col 0 = "#" ou vide, les essais sont en col 1
                first_col = (row[0] or "").strip().lower()
                if first_col in ("", "#", "n°"):
                    col_offset = 1
                break

        # Si cette table n'a pas d'en-tête RESULTATS, on l'ignore
        if header_row is None:
            continue

        # Extraire les lignes de données (après l'en-tête)
        found_header = False
        for row in table:
            if not row:
                continue
            if row == header_row:
                found_header = True
                continue
            if not found_header:
                continue

            essai = (row[col_offset] or "").strip() if len(row) > col_offset else ""
            if not essai:
                continue

            resultat = (row[col_offset + 1] or "").strip() if len(row) > col_offset + 1 else ""
            unite    = (row[col_offset + 2] or "").strip() if len(row) > col_offset + 2 else ""

            rows.append({"essai": essai, "resultat": resultat, "unite": unite})

    return rows


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def extract_rapport(file_path: str) -> dict:
    """
    Point d'entrée principal.

    Paramètre :
        file_path (str) : chemin absolu vers le fichier PDF.

    Retourne :
        {
            "header":    { ...champs Partie 1... },
            "resultats": [ { "essai": ..., "resultat": ..., "unite": ... }, ... ],
            "raw_text":  "..."
        }
    """
    full_text     = ""
    all_resultats = []

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            full_text += page_text + "\n"
            all_resultats.extend(extract_resultats_pdf(page))

    return {
        "header":    extract_header(full_text),
        "resultats": all_resultats,
        "raw_text":  full_text.strip(),
    }
