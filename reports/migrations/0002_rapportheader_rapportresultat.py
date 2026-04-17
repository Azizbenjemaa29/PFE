# Generated manually — 2026-04-03
# Ajoute les tables RapportHeader (Partie 1) et RapportResultat (Partie 2)
# pour l'extraction structurée des PDFs de rapports d'essai.
# Ces tables alimentent SSIS, SSMS et Power BI.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0001_initial'),
    ]

    operations = [
        # ------------------------------------------------------------------
        # Table Partie 1 — Entête du rapport
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name='RapportHeader',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('client',                  models.CharField(blank=True, max_length=255, verbose_name="Client")),
                ('date_emission',           models.DateField(blank=True, null=True, verbose_name="Date d'émission")),
                ('ose',                     models.CharField(blank=True, max_length=500, verbose_name="Objet soumis à l'essai")),
                ('code',                    models.CharField(blank=True, max_length=100, verbose_name='Code')),
                ('bon_de_commande',         models.CharField(blank=True, max_length=200, verbose_name='Bon de commande N°')),
                ('nature_echantillon',      models.CharField(blank=True, max_length=300, verbose_name="Nature de l'échantillon")),
                ('transport_par',           models.CharField(blank=True, max_length=200, verbose_name='Transport effectué par')),
                ('date_prelevement',        models.DateField(blank=True, null=True, verbose_name='Date du prélèvement')),
                ('date_reception',          models.DateField(blank=True, null=True, verbose_name='Date de réception')),
                ('date_debut_essais',       models.DateField(blank=True, null=True, verbose_name="Date du début d'essais")),
                ('responsable_laboratoire', models.CharField(blank=True, max_length=200, verbose_name='Responsable laboratoire')),
                ('report', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='header',
                    to='reports.report',
                    verbose_name='Rapport source',
                )),
            ],
            options={
                'verbose_name': 'Entête rapport',
                'verbose_name_plural': 'Entêtes rapports',
            },
        ),
        # ------------------------------------------------------------------
        # Table Partie 2 — Lignes résultats (sans Critère norme interne DICK)
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name='RapportResultat',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('essai',    models.CharField(max_length=200, verbose_name='Essai')),
                ('resultat', models.CharField(max_length=200, verbose_name='Résultat')),
                ('unite',    models.CharField(blank=True, max_length=100, verbose_name='Unités')),
                ('header', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='resultats',
                    to='reports.rapportheader',
                    verbose_name='Entête rapport',
                )),
            ],
            options={
                'verbose_name': 'Résultat',
                'verbose_name_plural': 'Résultats',
                'ordering': ['id'],
            },
        ),
    ]
