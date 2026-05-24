"""
reports/ocr_engine.py
=====================
Module OCR basé sur EasyOCR pour l'extraction de texte depuis des images et PDFs scannés.

Ce module est une alternative à extractor.py (pdfplumber) pour les PDFs non-lisibles
(PDFs image / scannés) où pdfplumber ne peut pas extraire le texte.

Pipeline :
    PDF scanné / Image
          ↓
    Conversion page → image (pypdfium2 ou Pillow)
          ↓
    EasyOCR → texte brut par page
          ↓
    extract_header_ocr(text)       → dict champs Partie 1
    extract_resultats_ocr(text)    → list dicts Partie 2
          ↓
    { 'header': {...}, 'resultats': [...], 'raw_text': '...' }

Langues supportées : français (fr) + anglais (en)
"""

from __future__ import annotations

import re
import io
import logging
from pathlib import Path
from datetime import datetime

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Initialisation lazy du reader EasyOCR (chargé une seule fois en mémoire)
# ---------------------------------------------------------------------------

_reader = None


def get_reader():
    """
    Retourne une instance EasyOCR initialisée.
    Le modèle est chargé une seule fois (singleton lazy).
    Langues : français + anglais.
    """
    global _reader
    if _reader is None:
        import easyocr
        logger.info("Chargement du modèle EasyOCR (fr + en)…")
        _reader = easyocr.Reader(["fr", "en"], gpu=False)
        logger.info("Modèle EasyOCR chargé.")
    return _reader


# ---------------------------------------------------------------------------
# Conversion PDF → images numpy
# ---------------------------------------------------------------------------

def pdf_to_images(file_path: str, dpi: int = 200) -> list[np.ndarray]:
    """
    Convertit chaque page d'un PDF en image numpy (RGB) via pypdfium2.

    Paramètres :
        file_path : chemin absolu vers le PDF
        dpi       : résolution de rendu (200 est un bon compromis vitesse/qualité)

    Retourne :
        liste d'images numpy shape (H, W, 3)
    """
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(file_path)
    images = []
    scale = dpi / 72.0

    for page_index in range(len(pdf)):
        page = pdf[page_index]
        bitmap = page.render(scale=scale, rotation=0)
        pil_image = bitmap.to_pil()
        images.append(np.array(pil_image.convert("RGB")))

    pdf.close()
    return images


def image_file_to_array(file_path: str) -> np.ndarray:
    """
    Charge un fichier image (PNG, JPEG, TIFF…) en tableau numpy RGB.
    """
    from PIL import Image
    img = Image.open(file_path).convert("RGB")
    return np.array(img)


# ---------------------------------------------------------------------------
# OCR sur une image
# ---------------------------------------------------------------------------

def ocr_image(image: np.ndarray, detail: int = 0) -> str:
    """
    Applique EasyOCR sur une image numpy et retourne le texte brut.

    Paramètres :
        image  : tableau numpy (H, W, 3)
        detail : 0 → texte seul, 1 → liste de tuples (bbox, texte, confiance)

    Retourne :
        str  si detail=0  — texte fusionné par lignes
        list si detail=1  — résultats bruts EasyOCR
    """
    reader = get_reader()
    results = reader.readtext(image, detail=detail)

    if detail == 0:
        return "\n".join(results)

    return results


def ocr_image_with_confidence(image: np.ndarray, min_confidence: float = 0.3) -> str:
    """
    Applique EasyOCR et filtre les résultats sous un seuil de confiance.

    Retourne le texte filtré fusionné en une chaîne.
    """
    reader = get_reader()
    results = reader.readtext(image, detail=1)
    lines = [text for (_, text, conf) in results if conf >= min_confidence]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers regex (même logique que extractor.py)
# ---------------------------------------------------------------------------

def _parse_date(raw: str):
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
    m = re.search(pattern, text, flags)
    return m.group(group).strip() if m else ""


# ---------------------------------------------------------------------------
# Extraction header depuis texte OCR (Partie 1)
# ---------------------------------------------------------------------------

def extract_header_ocr(text: str) -> dict:
    """
    Extrait les champs de l'entête depuis le texte brut produit par OCR.
    Même structure de retour que extract_header() dans extractor.py.
    """
    client = _field(r"Client\s*[:\-]\s*(.+?)(?=\s{2,}|Date|\n|$)", text)

    date_emission = _parse_date(_field(
        r"Date\s+d.?[ée]mission\s*[:\-]?\s*(\d{2}[-/]\d{2}[-/]\d{2,4})", text
    ))

    ose = _field(
        r"Objet\s+soumis.{0,20}essai.{0,10}[:\-]\s*(.+?)(?=\s{2,}|Date|\n|$)", text
    )

    code = _field(r"Code\s*[:\-]\s*(.+?)(?=\s{2,}|Date|\n|$)", text)

    bon_de_commande = _field(
        r"Bon\s+de\s+commande\s+N[o°]?\s*[:\-]\s*(.+?)(?=\s{2,}|Date|\n|$)", text
    )

    nature_echantillon = _field(
        r"Nature\s+de\s+l.?[ée]chantillon\s*[:\-]\s*(.+?)(?=\s{2,}|\n|$)", text
    )

    transport_par = _field(
        r"Transport\s+effect[ué][ée]\s+par\s*[:\-]\s*(.+?)(?=\s{2,}|\n|$)", text
    )

    date_prelevement = _parse_date(_field(
        r"Date\s+du\s+pr[ée]l[eè]vement\s*[:\-]?\s*(\d{2}[-/]\d{2}[-/]\d{2,4})", text
    ))

    date_reception = _parse_date(_field(
        r"Date\s+de\s+r[ée]ception\s*[:\-]?\s*(\d{2}[-/]\d{2}[-/]\d{2,4})", text
    ))

    date_debut_essais = _parse_date(_field(
        r"Date\s+du\s+d[ée]but\s+d.?essais?\s*[:\-]?\s*(\d{2}[-/]\d{2}[-/]\d{2,4})", text
    ))

    responsable = _field(
        r"Responsable\s+(?:du\s+)?laboratoire\s*\n?\s*([A-Z][A-Za-zÀ-ÿ\s]{3,30})", text
    ) or ""

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
# Extraction tableau de résultats depuis texte OCR (Partie 2)
# ---------------------------------------------------------------------------

def extract_resultats_ocr(text: str) -> list[dict]:
    """
    Tente d'extraire les lignes du tableau des résultats depuis le texte OCR brut.

    L'OCR produit du texte non structuré — on cherche des patterns typiques :
        "Essai   résultat   unité"
    via des heuristiques simples sur chaque ligne.

    Retourne une liste de dicts { essai, methode_essai, resultat, unite }.
    Note : la détection de tableau en OCR est approximative.
    """
    rows = []
    lines = text.splitlines()

    # Heuristique : lignes contenant un chiffre (résultat probable) entouré de texte
    result_pattern = re.compile(
        r"^(.+?)\s{2,}([\d,.\-\+]+(?:\s*[\d,.\-\+]*)?)\s{1,}([a-zA-Z%°/µ²³]+)?\s*$"
    )

    in_table = False
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Détecter le début du tableau (ligne d'en-tête)
        if re.search(r"[Ee]ssais?\s+.*(R[ée]sultat|[Mm][ée]thode)", line):
            in_table = True
            continue

        if not in_table:
            continue

        m = result_pattern.match(line)
        if m:
            rows.append({
                "essai":         m.group(1).strip(),
                "methode_essai": "",
                "resultat":      m.group(2).strip(),
                "unite":         (m.group(3) or "").strip(),
            })

    return rows


# ---------------------------------------------------------------------------
# Point d'entrée principal — PDF scanné
# ---------------------------------------------------------------------------

def extract_rapport_ocr(file_path: str, dpi: int = 200) -> dict:
    """
    Point d'entrée principal pour l'extraction OCR d'un PDF scanné.

    Paramètre :
        file_path : chemin absolu vers le fichier PDF
        dpi       : résolution de rendu des pages (défaut 200)

    Retourne :
        {
            "header":    { ...champs Partie 1... },
            "resultats": [ { "essai": ..., "methode_essai": ..., "resultat": ..., "unite": ... }, ... ],
            "raw_text":  "...",
            "engine":    "easyocr"
        }
    """
    images = pdf_to_images(file_path, dpi=dpi)
    full_text = ""

    for i, image in enumerate(images):
        logger.info("OCR page %d/%d…", i + 1, len(images))
        page_text = ocr_image(image, detail=0)
        full_text += page_text + "\n"

    return {
        "header":    extract_header_ocr(full_text),
        "resultats": extract_resultats_ocr(full_text),
        "raw_text":  full_text.strip(),
        "engine":    "easyocr",
    }


def extract_rapport_from_image(file_path: str) -> dict:
    """
    Point d'entrée pour l'extraction OCR d'un fichier image (PNG, JPEG, TIFF).

    Retourne le même format que extract_rapport_ocr().
    """
    image = image_file_to_array(file_path)
    raw_text = ocr_image(image, detail=0)

    return {
        "header":    extract_header_ocr(raw_text),
        "resultats": extract_resultats_ocr(raw_text),
        "raw_text":  raw_text.strip(),
        "engine":    "easyocr",
    }
