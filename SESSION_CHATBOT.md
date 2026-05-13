# Session de travail — Intégration Chatbot Mistral AI
**Date :** 12/05/2026  
**Projet :** LabAssistant — Poulina Group Holding  
**Stack :** Django 5.2 · Microsoft SQL Server · Mistral AI

---

## Ce que tu m'as demandé

Intégrer un chatbot intelligent Mistral AI dans l'application Django existante, capable de :

- Lire et analyser toutes les données de la base SQL Server
- Répondre avec des données exactes (zéro hallucination)
- Streamer les réponses en temps réel (style Claude AI)
- Sauvegarder l'historique des conversations
- Exporter les conversations en PDF et Markdown
- Interface moderne dark mode

---

## Ce que j'ai analysé avant de coder

| Fichier | Ce que j'ai trouvé |
|---|---|
| `config/settings.py` | Django 5.2, base SQL Server `Projet_pfe`, auth customisée |
| `blog/models.py` | `CustomUser` (nom, prenom, filiale, role) |
| `reports/models.py` | `Report`, `RapportHeader`, `RapportResultat` |
| `reports/views.py` | Pipeline extraction PDF existant |
| `templates/registration/base.html` | Bootstrap 5.3, thème Poulina |
| `reports/templates/reports/dashboard.html` | Sidebar avec lien "Assistant IA" → `#` |

---

## Fichiers créés

### App `chatbot/`

| Fichier | Rôle |
|---|---|
| `chatbot/__init__.py` | Init de l'app |
| `chatbot/apps.py` | `ChatbotConfig` |
| `chatbot/models.py` | Modèles `Conversation` et `Message` |
| `chatbot/admin.py` | Interface admin avec inline messages |
| `chatbot/views.py` | 7 vues : chat, stream SSE, new, list, delete, export MD/PDF |
| `chatbot/urls.py` | Routes `/chatbot/`, `/chatbot/api/...`, `/chatbot/export/...` |
| `chatbot/migrations/0001_initial.py` | Migration auto-générée |

### Services

| Fichier | Rôle |
|---|---|
| `chatbot/services/sql_service.py` | Introspection schema SQL Server, validation sécurité, exécution SELECT |
| `chatbot/services/mistral_service.py` | Client REST Mistral AI (streaming + non-streaming) |
| `chatbot/services/export_service.py` | Export PDF via ReportLab, export Markdown |

### Templates

| Fichier | Rôle |
|---|---|
| `chatbot/templates/chatbot/chat.html` | Interface complète dark mode, SSE, markdown rendering |

---

## Fichiers modifiés

| Fichier | Modification |
|---|---|
| `config/settings.py` | + `chatbot` dans `INSTALLED_APPS`, + `MISTRAL_API_KEY`, `MISTRAL_MODEL`, + `python-dotenv` |
| `config/urls.py` | + `path('chatbot/', include(...))` |
| `reports/templates/reports/dashboard.html` | Lien "Assistant IA" → `{% url 'chatbot:chat' %}` |

### Fichiers créés à la racine

| Fichier | Rôle |
|---|---|
| `.env` | Variables d'environnement (clé Mistral à renseigner) |
| `requirements.txt` | Mis à jour avec `requests`, `reportlab`, `python-dotenv` |

---

## Packages installés

```
requests==2.34.0       → Appels REST vers l'API Mistral AI
reportlab==4.5.1       → Génération PDF des conversations
python-dotenv==1.2.2   → Chargement du fichier .env
```

> **Pourquoi pas le SDK `mistralai` ?**  
> Le package `mistralai` est actuellement **quarantiné sur PyPI**  
> (`pypi:project-status: quarantined`) — pip ne peut pas l'installer.  
> Le service utilise l'API REST directement via `requests`, fonctionnellement identique.

---

## Pipeline de fonctionnement

```
Question utilisateur (langage naturel)
          │
          ▼
  [1] Mistral génère SQL   (temperature 0.05 — très déterministe)
          │
          ▼
  [2] Validation sécurité  (SELECT only, 21 mots-clés dangereux bloqués)
          │
          ▼
  [3] Exécution SQL Server  (vraies données, max 150 lignes)
          │
          ▼
  [4] Mistral génère réponse (temperature 0.30, basée UNIQUEMENT sur les données réelles)
          │
          ▼
  Streaming SSE token par token → navigateur
```

---

## Résultats des tests

```
python manage.py check          → 0 erreur, 0 warning
python manage.py migrate chatbot → OK (tables créées sur SQL Server)

Test SQL service :
  Tables détectées : 16 tables (blog, reports, chatbot, auth, django_*)
  Relations FK     : 14 relations détectées automatiquement

Test validation SQL :
  [VALID]   SELECT * FROM reports_report WHERE is_deleted = 0
  [BLOCKED] DELETE FROM reports_report
  [BLOCKED] SELECT * FROM x; DROP TABLE x
  [BLOCKED] EXEC xp_cmdshell dir

Test ReportLab  → disponible, export PDF fonctionnel
Test URL resolve → /chatbot/, /chatbot/api/stream/, /chatbot/api/new/ → OK
```

---

## Pour utiliser le chatbot

**1. Ajouter ta clé Mistral dans `.env` :**
```
MISTRAL_API_KEY=ta_clé_ici
```

**2. Lancer le serveur :**
```bash
venv\Scripts\python manage.py runserver
```

**3. Ouvrir :** `http://localhost:8000/chatbot/`

---

## Exemples de questions à poser

```
- Combien de rapports ont été traités ce mois ?
- Quels clients ont le plus de rapports d'essais ?
- Liste des rapports en attente de validation
- Statistiques des rapports par statut
- Résultats des essais FASEP des 30 derniers jours
- Quel utilisateur a soumis le plus de rapports ?
```

---

*Session du 12/05/2026 · Claude Sonnet 4.6 × Aziz Benjemaa*
