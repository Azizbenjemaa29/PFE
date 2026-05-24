"""
Commande de test OCR :
    python manage.py test_ocr <chemin_fichier>

Exemples :
    python manage.py test_ocr rapport.pdf
    python manage.py test_ocr scan.png
    python manage.py test_ocr rapport.pdf --dpi 300
    python manage.py test_ocr rapport.pdf --raw
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Teste le module OCR (EasyOCR) sur un fichier PDF ou image."

    def add_arguments(self, parser):
        parser.add_argument("file", type=str, help="Chemin vers le PDF ou l'image à traiter")
        parser.add_argument("--dpi", type=int, default=200, help="Résolution de rendu (PDF seulement, défaut 200)")
        parser.add_argument("--raw", action="store_true", help="Afficher uniquement le texte brut OCR")

    def handle(self, *args, **options):
        from reports.ocr_engine import extract_rapport_ocr, extract_rapport_from_image

        file_path = Path(options["file"]).resolve()
        if not file_path.exists():
            raise CommandError(f"Fichier introuvable : {file_path}")

        suffix = file_path.suffix.lower()
        self.stdout.write(self.style.NOTICE(f"Traitement OCR de : {file_path}"))

        if suffix == ".pdf":
            result = extract_rapport_ocr(str(file_path), dpi=options["dpi"])
        elif suffix in (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"):
            result = extract_rapport_from_image(str(file_path))
        else:
            raise CommandError(f"Extension non supportée : {suffix}. Utilisez .pdf, .png, .jpg, .tiff")

        if options["raw"]:
            self.stdout.write(result["raw_text"])
            return

        self.stdout.write(self.style.SUCCESS("\n=== HEADER ==="))
        for key, value in result["header"].items():
            self.stdout.write(f"  {key:<30} : {value}")

        self.stdout.write(self.style.SUCCESS(f"\n=== RÉSULTATS ({len(result['resultats'])} lignes) ==="))
        for row in result["resultats"]:
            self.stdout.write(
                f"  {row['essai']:<40} | {row['resultat']:<15} | {row['unite']}"
            )

        self.stdout.write(self.style.SUCCESS(f"\n=== TEXTE BRUT (500 premiers caractères) ==="))
        self.stdout.write(result["raw_text"][:500])
