# Extraction Pipeline — Rapport d'Essai

> Module d'extraction structurée de PDFs natifs (digitaux) pour LabAssistant
> Alimentation : SQL Server → SSIS · SSMS · Power BI

---

## Overview

Quand un utilisateur upload un PDF de type "Rapport d'Essai", le système extrait automatiquement les données en deux parties et les persiste dans deux tables SQL Server dédiées.

```
PDF Upload (digital natif)
        ↓
    pdfplumber          ← pas d'OCR, lecture directe du texte
        ↓
    extractor.py        ← regex (Part 1) + table parsing (Part 2)
        ↓
    RapportHeader       ← dimension table (Part 1)
    RapportResultat     ← fact table     (Part 2)
        ↓
    SQL Server → SSIS / SSMS / Power BI
```

---

## Files Added / Modified

| File | Action | Role |
|------|--------|------|
| `reports/models.py` | Modified | Ajout des modèles `RapportHeader` et `RapportResultat` |
| `reports/extractor.py` | **New** | Moteur d'extraction pdfplumber |
| `reports/views.py` | Modified | Appel automatique de l'extraction à l'upload |
| `reports/migrations/0002_rapportheader_rapportresultat.py` | **New** | Migration Django pour les deux nouvelles tables |

---

## Database Schema

### Relation entre les tables

```
reports_report  (existant)
     │
     │ OneToOne (report_id)
     ▼
reports_rapportheader        ← Partie 1 — dimension
     │
     │ FK (header_id)  1 → N
     ▼
reports_rapportresultat      ← Partie 2 — faits
```

---

### Table : `reports_rapportheader` (Partie 1)

Informations générales extraites de l'entête du rapport.

| Colonne | Type SQL | Description |
|---------|----------|-------------|
| `id` | BIGINT PK | Clé primaire auto |
| `report_id` | BIGINT FK | → `reports_report.id` (OneToOne) |
| `client` | VARCHAR(255) | Ex : `DICK` |
| `date_emission` | DATE | Ex : `2025-11-03` |
| `ose` | VARCHAR(500) | Objet soumis à l'essai — Ex : `EAU DE SONEDE` |
| `code` | VARCHAR(100) | Ex : `C/20-ZALILA` |
| `bon_de_commande` | VARCHAR(200) | Numéro bon de commande |
| `nature_echantillon` | VARCHAR(300) | Ex : `EAU DE SONEDE` |
| `transport_par` | VARCHAR(200) | Ex : `DICK` |
| `date_prelevement` | DATE | Ex : `2025-11-02` |
| `date_reception` | DATE | Ex : `2025-11-03` |
| `date_debut_essais` | DATE | Ex : `2025-11-03` |
| `responsable_laboratoire` | VARCHAR(200) | Ex : `HAZZI HASSEN` |

---

### Table : `reports_rapportresultat` (Partie 2)

Lignes du tableau des résultats. La colonne **"Critère norme interne DICK" est exclue** volontairement.

| Colonne | Type SQL | Description |
|---------|----------|-------------|
| `id` | BIGINT PK | Clé primaire auto |
| `header_id` | BIGINT FK | → `reports_rapportheader.id` |
| `essai` | VARCHAR(200) | Nom du paramètre — Ex : `pH`, `Sulfates`, `Chlorure` |
| `resultat` | VARCHAR(200) | Valeur mesurée — Ex : `7.29`, `259`, `1959à 25 °C` |
| `unite` | VARCHAR(100) | Unité — Ex : `mg/l`, `g/l`, `µs/cm` |

**Exemple de données extraites depuis le PDF :**

| essai | resultat | unite |
|-------|----------|-------|
| pH | 7.29 | |
| Dureté | 59 | °F |
| Sulfates | 259 | mg/l |
| Nitrate | 35 | mg/l |
| Chlorure | 363 | mg/l |
| Sodium | 149 | mg/l |
| Conductivité | 1959à 25 °C | µs/cm |
| Sels totaux | 1.48 | g/l |

---

## `reports/extractor.py`

Point d'entrée : `extract_rapport(pdf_path: str) -> dict`

### Fonctions internes

| Fonction | Rôle |
|----------|------|
| `extract_rapport(pdf_path)` | Orchestre l'extraction complète, retourne `{ header, resultats, raw_text }` |
| `extract_header(text)` | Parse le texte brut avec regex pour extraire les 11 champs de la Partie 1 |
| `extract_resultats(page)` | Lit les tableaux pdfplumber et retourne les lignes Essai/Résultat/Unités |
| `_parse_date(raw)` | Convertit `"DD/MM/YYYY"` en objet `date` Python |
| `_field(pattern, text)` | Helper regex générique |

### Retour de `extract_rapport`

```python
{
    "header": {
        "client": "DICK",
        "date_emission": date(2025, 11, 3),
        "ose": "EAU DE SONEDE",
        "code": "C/20-ZALILA",
        "bon_de_commande": "****************",
        "nature_echantillon": "EAU DE SONEDE",
        "transport_par": "DICK",
        "date_prelevement": date(2025, 11, 2),
        "date_reception": date(2025, 11, 3),
        "date_debut_essais": date(2025, 11, 3),
        "responsable_laboratoire": "HAZZI HASSEN",
    },
    "resultats": [
        { "essai": "pH",          "resultat": "7.29",        "unite": ""      },
        { "essai": "Dureté",      "resultat": "59",           "unite": "°F"    },
        { "essai": "Sulfates",    "resultat": "259",          "unite": "mg/l"  },
        ...
    ],
    "raw_text": "..."  # texte brut complet → Report.processed_text
}
```

---

## `reports/views.py` — `_run_extraction()`

Appelée automatiquement après chaque upload réussi. Gère le cycle de vie du statut :

```
PENDING → PROCESSING → COMPLETED
                    ↘ FAILED  (exception capturée, message dans processed_text)
```

La fonction est idempotente : elle supprime les éventuelles données existantes avant de réinsérer (`filter(...).delete()` avant `create()`).

---

## Installation

### Dépendance à ajouter

```bash
pip install pdfplumber
```

### Migration

```bash
python manage.py migrate
```

Résultat attendu :
```
Applying reports.0002_rapportheader_rapportresultat... OK
```

---

## Intégration SSIS / SSMS / Power BI

### SSMS — Requête de vérification

```sql
SELECT
    h.client,
    h.date_emission,
    h.ose,
    h.code,
    h.responsable_laboratoire,
    r.essai,
    r.resultat,
    r.unite
FROM reports_rapportheader h
JOIN reports_rapportresultat r ON r.header_id = h.id
ORDER BY h.id, r.id;
```

### SSIS

Connecter la source OLE DB sur `Projet_pfe` et utiliser les deux tables comme sources pour vos flux de données ETL. La jointure se fait sur `header_id`.

### Power BI

1. **Connecter** Power BI Desktop à SQL Server (`localhost`, `Projet_pfe`)
2. **Importer** les tables `reports_rapportheader` et `reports_rapportresultat`
3. **Relation** : `rapportheader.id` → `rapportresultat.header_id` (1 à plusieurs)
4. Schéma en étoile prêt — slicer par `client`, `date_emission`, `essai`, etc.
