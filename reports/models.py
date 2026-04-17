from django.db import models
from django.conf import settings
from django.utils import timezone
import os


class Report(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'En attente'),
        ('PROCESSING', 'Traitement en cours'),
        ('COMPLETED', 'Terminé'),
        ('FAILED', 'Échec'),
        ('REFUSED', 'Refusé'),
    ]

    title = models.CharField(max_length=200, verbose_name="Titre du rapport")
    file = models.FileField(upload_to='reports/', verbose_name="Fichier (PDF/Image)")
    uploaded_at = models.DateTimeField(default=timezone.now, verbose_name="Date de téléchargement")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reports'
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    processed_text = models.TextField(blank=True, null=True, verbose_name="Texte extrait")

    def __str__(self):
        return f"{self.title} - {self.user.username}"

    def filename(self):
        return os.path.basename(self.file.name)


class RapportHeader(models.Model):
    """
    Partie 1 — Informations générales du rapport d'essai.
    Liée à Report par une relation OneToOne.
    Sert de table de dimension dans Power BI / SSIS.
    """
    report = models.OneToOneField(
        Report,
        on_delete=models.CASCADE,
        related_name='header',
        verbose_name="Rapport source"
    )

    # Champs entête
    client                  = models.CharField(max_length=255, blank=True, verbose_name="Client")
    date_emission           = models.CharField(max_length=255, null=True, blank=True, verbose_name="Date d'émission")
    ose                     = models.CharField(max_length=500, blank=True, verbose_name="Objet soumis à l'essai")
    code                    = models.CharField(max_length=100, blank=True, verbose_name="Code")
    bon_de_commande         = models.CharField(max_length=200, blank=True, verbose_name="Bon de commande N°")
    nature_echantillon      = models.CharField(max_length=300, blank=True, verbose_name="Nature de l'échantillon")
    transport_par           = models.CharField(max_length=200, blank=True, verbose_name="Transport effectué par")
    date_prelevement        = models.DateField(null=True, blank=True, verbose_name="Date du prélèvement")
    date_reception          = models.DateField(null=True, blank=True, verbose_name="Date de réception")
    date_debut_essais       = models.DateField(null=True, blank=True, verbose_name="Date du début d'essais")
    responsable_laboratoire = models.CharField(max_length=200, blank=True, verbose_name="Responsable laboratoire")

    class Meta:
        verbose_name = "Entête rapport"
        verbose_name_plural = "Entêtes rapports"

    def __str__(self):
        return f"Header [{self.report.title}] — {self.client}"


class RapportResultat(models.Model):
    """
    Partie 2 — Lignes du tableau des résultats (sans la colonne Critère norme interne DICK).
    Liée à RapportHeader par FK.
    Sert de table de faits dans Power BI / SSIS.
    """
    header  = models.ForeignKey(
        RapportHeader,
        on_delete=models.CASCADE,
        related_name='resultats',
        verbose_name="Entête rapport"
    )

    essai   = models.CharField(max_length=200, verbose_name="Essai")
    resultat = models.CharField(max_length=200, verbose_name="Résultat")
    unite   = models.CharField(max_length=100, blank=True, verbose_name="Unités")

    class Meta:
        verbose_name = "Résultat"
        verbose_name_plural = "Résultats"
        ordering = ['id']

    def __str__(self):
        return f"{self.essai} : {self.resultat} {self.unite}"