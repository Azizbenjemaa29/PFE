# LabAssistant — Technical Documentation

> Système de gestion de rapports de laboratoire — Poulina Group Holding
> Stack : Django 5.2 · Microsoft SQL Server · Bootstrap 5.3

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Pipeline Modules](#3-pipeline-modules)
4. [File Responsibilities](#4-file-responsibilities)
5. [Database Schema](#5-database-schema)
6. [URL Routing](#6-url-routing)
7. [Setup & Installation](#7-setup--installation)
8. [Usage Examples](#8-usage-examples)

---

## 1. Project Overview

**LabAssistant** is a Django web application built for Poulina Group Holding to digitize and automate the management of laboratory reports. It provides:

- **OCR-based text extraction** from uploaded PDF and image files
- **Role-based access control** (Admin / User) with multi-subsidiary (filiale) support
- **Report lifecycle tracking** from upload through processing to completion
- **AI assistant integration** (infrastructure in place, implementation pending)
- **User profile management** with editable account information

### High-Level Architecture

```
Browser
  │
  ▼
Django Application (MVT Pattern)
  ├── blog/          ← Authentication & user management
  ├── reports/       ← Report upload, processing, dashboard
  └── config/        ← Django project configuration
  │
  ▼
Microsoft SQL Server (Projet_pfe database)
```

**Design pattern:** Traditional Django MVT (Model–View–Template), server-side rendering, no REST API layer.

---

## 2. Architecture

### Application Layout

```
PFE/
├── blog/                        # App: authentication & users
│   ├── models.py                # CustomUser model
│   ├── views.py                 # home, signup views
│   ├── forms.py                 # CustomUserCreationForm
│   ├── backends.py              # Custom auth backend (login by nom)
│   ├── admin.py
│   └── migrations/
│       ├── 0001_initial.py
│       └── 0002_customuser_email.py
├── config/                      # Django project config
│   ├── settings.py
│   ├── urls.py                  # Root URL dispatcher
│   ├── wsgi.py
│   └── asgi.py
├── reports/                     # App: report management
│   ├── models.py                # Report model
│   ├── views.py                 # dashboard, upload, history, profil, manage_users
│   ├── forms.py                 # ReportForm, ProfilForm
│   ├── urls.py                  # reports/ URL namespace
│   ├── admin.py
│   ├── migrations/
│   │   └── 0001_initial.py
│   ├── static/reports/images/   # logo.png
│   └── templates/reports/       # dashboard, history, upload, profil, manage_users
├── templates/registration/      # Auth templates (home, login, signup, base)
├── manage.py
└── venv/                        # Python virtual environment
```

### Request Lifecycle

```
HTTP Request
  │
  ▼
config/urls.py          → dispatches to blog.views or reports.urls
  │
  ├── blog/views.py     → home(), signup()
  └── reports/views.py  → dashboard(), upload_report(), history(),
                          delete_report(), manage_users(), profil()
  │
  ▼
Model (ORM query → SQL Server)
  │
  ▼
Template (.html) rendered → HTTP Response
```

---

## 3. Pipeline Modules

### 3.1 Authentication Module (`blog/`)

| Stage | Description |
|-------|-------------|
| **Input** | POST: `nom`, `password` (login) or `nom`, `prenom`, `filiale`, `password1`, `password2` (signup) |
| **Processing** | `NomBackend.authenticate()` looks up user by `nom` field instead of email |
| **Output** | Django session cookie; redirect to `reports:dashboard` |
| **Key logic** | `USERNAME_FIELD = "nom"` — overrides Django default (email). Custom backend required to support this. |

**Authentication flow:**

```
POST /login/
  → NomBackend.authenticate(username=nom, password=...)
  → User.objects.get(nom=username)
  → user.check_password(password)
  → login(request, user)
  → redirect → /reports/dashboard/
```

**Signup flow:**

```
POST /signup/
  → CustomUserCreationForm.is_valid()
  → form.save()          ← creates CustomUser with role='user'
  → login(request, user)
  → redirect → /reports/dashboard/
```

---

### 3.2 Report Upload Module (`reports/views.upload_report`)

| Stage | Description |
|-------|-------------|
| **Input** | POST multipart form: `title` (str), `file` (PDF/PNG/JPG/TIFF, max 25 MB) |
| **Processing** | `ReportForm` validates; file saved to `reports/` media folder; `Report` created with `status='PENDING'` |
| **Output** | `Report` record in DB; redirect to dashboard |
| **Pending** | Background OCR task to populate `processed_text` and update `status` |

**Status lifecycle:**

```
PENDING → PROCESSING → COMPLETED
                    ↘ FAILED
```

---

### 3.3 Dashboard Module (`reports/views.dashboard`)

| Stage | Description |
|-------|-------------|
| **Input** | Authenticated session (`request.user`) |
| **Processing** | Role-based queryset: Admin → `Report.objects.all()`, User → `Report.objects.filter(user=request.user)` |
| **Output** | Rendered `dashboard.html` with stats (`completed_count`, `pending_count`, `users_count`) and report list |

---

### 3.4 History Module (`reports/views.history`)

| Stage | Description |
|-------|-------------|
| **Input** | Authenticated session |
| **Processing** | Same role-based queryset as dashboard, ordered by `-uploaded_at` |
| **Output** | Timeline view of all reports with status badges and delete actions |

---

### 3.5 Profile Module (`reports/views.profil`)

| Stage | Description |
|-------|-------------|
| **Input** | GET: current user instance. POST: `nom`, `prenom`, `filiale`, `email` |
| **Processing** | `ProfilForm(request.POST, instance=request.user)` → `form.save()` updates `CustomUser` record |
| **Output** | Redirect to `reports:profil` on success; form with errors on failure |

---

### 3.6 User Management Module (`reports/views.manage_users`)

| Stage | Description |
|-------|-------------|
| **Input** | Admin session only (`role == 'admin'`); non-admins redirected |
| **Processing** | `User.objects.filter(role='user')` — lists all regular users |
| **Output** | Rendered `manage_users.html` with users table |

---

## 4. File Responsibilities

### Config

| File | Role |
|------|------|
| `config/settings.py` | Django configuration: database (MSSQL), installed apps, auth model, static files, login redirects |
| `config/urls.py` | Root URL dispatcher: mounts `blog.views`, `auth_views`, and `reports.urls` |
| `config/wsgi.py` | WSGI entry point for production deployment |
| `config/asgi.py` | ASGI entry point (async support) |
| `manage.py` | Django CLI utility for migrations, runserver, shell, etc. |

### Blog App

| File | Role |
|------|------|
| `blog/models.py` | Defines `CustomUser` (extends `AbstractBaseUser`) with fields: `nom`, `prenom`, `filiale`, `email`, `role`. Replaces Django's default user. |
| `blog/backends.py` | `NomBackend` — custom auth backend that looks up users by `nom` field instead of email |
| `blog/forms.py` | `CustomUserCreationForm` — registration form exposing `nom`, `prenom`, `filiale`, passwords |
| `blog/views.py` | `home()` renders landing page; `signup()` handles user creation and auto-login |
| `blog/admin.py` | Admin registrations (currently empty) |
| `blog/migrations/0001_initial.py` | Creates `blog_customuser` table with all base fields |
| `blog/migrations/0002_customuser_email.py` | Adds `email` column to `blog_customuser` |

### Reports App

| File | Role |
|------|------|
| `reports/models.py` | Defines `Report` model: `title`, `file`, `uploaded_at`, `user` (FK), `status`, `processed_text`. Includes `filename()` helper. |
| `reports/views.py` | All report views: `dashboard`, `upload_report`, `history`, `delete_report`, `manage_users`, `profil` |
| `reports/forms.py` | `ReportForm` (upload); `ProfilForm` (profile edit with Bootstrap widget classes) |
| `reports/urls.py` | URL patterns under `reports/` namespace |
| `reports/admin.py` | Admin registrations (currently empty) |
| `reports/migrations/0001_initial.py` | Creates `reports_report` table |

### Templates

| File | Role |
|------|------|
| `templates/registration/home.html` | Public landing page — hero, features, how-it-works, CTA. Standalone (no base.html). |
| `templates/registration/base.html` | Base layout for auth pages (navbar + footer) |
| `templates/registration/login.html` | Login form (extends base.html) |
| `templates/registration/signup.html` | Signup form (extends base.html) |
| `reports/templates/reports/dashboard.html` | Main app dashboard — 3-column layout, stats, OCR upload, reports table |
| `reports/templates/reports/history.html` | Timeline history of report activity |
| `reports/templates/reports/upload.html` | Simple report upload form |
| `reports/templates/reports/profil.html` | User profile view + edit form |
| `reports/templates/reports/manage_users.html` | Admin user list (admin-only) |

### Static

| File | Role |
|------|------|
| `reports/static/reports/images/logo.png` | Poulina Group Holding logo — used in navbar, sidebar, footer |

---

## 5. Database Schema

### Table: `blog_customuser`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | BIGINT | PK, auto-increment |
| `password` | VARCHAR(128) | hashed (Django PBKDF2) |
| `last_login` | DATETIME | nullable |
| `is_superuser` | BIT | default 0 |
| `nom` | VARCHAR(100) | UNIQUE, NOT NULL — used as USERNAME_FIELD |
| `prenom` | VARCHAR(100) | NOT NULL |
| `filiale` | VARCHAR(100) | NOT NULL |
| `email` | VARCHAR(254) | nullable, blank allowed |
| `role` | VARCHAR(10) | choices: `admin`, `user` — default `user` |
| `is_active` | BIT | default 1 |
| `is_staff` | BIT | default 0 |

### Table: `reports_report`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | BIGINT | PK, auto-increment |
| `title` | VARCHAR(200) | NOT NULL |
| `file` | VARCHAR(max) | file path, upload_to=`reports/` |
| `uploaded_at` | DATETIME | default NOW |
| `user_id` | BIGINT | FK → `blog_customuser.id` ON DELETE CASCADE |
| `status` | VARCHAR(20) | choices: PENDING, PROCESSING, COMPLETED, FAILED |
| `processed_text` | TEXT | nullable |

### Entity Relationship

```
blog_customuser ──< reports_report
    (1)               (many)
    id ──────────→ user_id (FK, CASCADE)
```

---

## 6. URL Routing

### Root (`config/urls.py`)

| URL | View | Name |
|-----|------|------|
| `/` | `blog.views.home` | `home` |
| `/signup/` | `blog.views.signup` | `signup` |
| `/login/` | `auth_views.LoginView` | `login` |
| `/logout/` | `auth_views.LogoutView` | `logout` |
| `/admin/` | Django admin site | — |
| `/reports/` | `reports.urls` (namespace) | — |

### Reports namespace (`reports/urls.py`)

| URL | View | Name |
|-----|------|------|
| `/reports/dashboard/` | `views.dashboard` | `reports:dashboard` |
| `/reports/upload/` | `views.upload_report` | `reports:upload_report` |
| `/reports/history/` | `views.history` | `reports:history` |
| `/reports/delete/<int:pk>/` | `views.delete_report` | `reports:delete_report` |
| `/reports/users/` | `views.manage_users` | `reports:manage_users` |
| `/reports/profil/` | `views.profil` | `reports:profil` |

**Auth redirects (settings.py):**

```python
LOGIN_REDIRECT_URL  = 'reports:dashboard'
LOGOUT_REDIRECT_URL = 'home'
```

---

## 7. Setup & Installation

### Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.10+ |
| Microsoft SQL Server | 2019+ |
| ODBC Driver for SQL Server | 17 |
| pip | latest |

### Step 1 — Clone / Extract the project

```bash
cd C:\Users\medaz\Desktop
# project folder: PFE/
```

### Step 2 — Create and activate virtual environment

```bash
cd PFE
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS
```

### Step 3 — Install dependencies

```bash
pip install django==5.2.11
pip install mssql-django==1.6
pip install pyodbc==5.3.0
```

Or from a freeze file if available:

```bash
pip install -r requirements.txt
```

### Step 4 — Configure the database

Create the database in SQL Server Management Studio:

```sql
CREATE DATABASE Projet_pfe;
```

Verify `config/settings.py` matches your environment:

```python
DATABASES = {
    'default': {
        'ENGINE': 'mssql',
        'NAME': 'Projet_pfe',
        'HOST': 'localhost',
        'PORT': '1433',
        'OPTIONS': {
            'driver': 'ODBC Driver 17 for SQL Server',
            'trusted_connection': 'yes',   # Windows Authentication
        },
    }
}
```

> For SQL Server Authentication, set `USER` and `PASSWORD` and remove `trusted_connection`.

### Step 5 — Run migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

Expected output:

```
Applying blog.0001_initial... OK
Applying blog.0002_customuser_email... OK
Applying reports.0001_initial... OK
```

### Step 6 — Create a superuser (admin)

```bash
python manage.py createsuperuser
```

Prompts: `nom`, `prenom`, `filiale`, `password`.

### Step 7 — Collect static files (production only)

```bash
python manage.py collectstatic
```

### Step 8 — Run the development server

```bash
python manage.py runserver
```

Application available at: `http://127.0.0.1:8000/`

---

## 8. Usage Examples

### Start the server

```bash
cd C:\Users\medaz\Desktop\PFE
venv\Scripts\activate
python manage.py runserver
```

### Create a regular user (via signup)

```
GET  http://127.0.0.1:8000/signup/
POST http://127.0.0.1:8000/signup/
     nom=dupont&prenom=jean&filiale=Siège&password1=xxx&password2=xxx
→ redirect → /reports/dashboard/
```

### Login

```
POST http://127.0.0.1:8000/login/
     username=dupont&password=xxx
→ redirect → /reports/dashboard/
```

### Upload a report

```
GET  http://127.0.0.1:8000/reports/upload/
POST http://127.0.0.1:8000/reports/upload/
     title=Rapport Mars&file=<binary PDF>
→ Report created with status=PENDING
→ redirect → /reports/dashboard/
```

### Delete a report

```
POST http://127.0.0.1:8000/reports/delete/42/
     (CSRF token required)
→ redirect → /reports/dashboard/
```

### Admin: manage users

```
GET http://127.0.0.1:8000/reports/users/
    (requires role=admin)
→ Table of all role='user' accounts
```

### Django shell — query examples

```bash
python manage.py shell
```

```python
# List all users
from blog.models import CustomUser
CustomUser.objects.all()

# List pending reports
from reports.models import Report
Report.objects.filter(status='PENDING')

# Manually update a report status
r = Report.objects.get(pk=1)
r.status = 'COMPLETED'
r.processed_text = 'Texte extrait ici...'
r.save()
```

### Django admin panel

```
http://127.0.0.1:8000/admin/
```

Login with the superuser created in Step 6.

---

## Appendix — Environment Variables (recommended for production)

Currently, sensitive values are hardcoded in `settings.py`. For production, externalize them:

```python
import os
SECRET_KEY = os.environ['DJANGO_SECRET_KEY']
DEBUG      = os.environ.get('DEBUG', 'False') == 'True'
```

Set in environment or `.env` file (use `python-decouple` or `django-environ`):

```env
DJANGO_SECRET_KEY=your-secret-key
DEBUG=False
DB_HOST=your-sql-server-host
DB_NAME=Projet_pfe
```

---

## Updates from 2026-04-20

This section captures technical insights, decisions, and code-level changes
that emerged during the 2026-04-20 working session. Changes are grouped by
subsystem. All line references are to files at this date.

### 9.1 Date Extraction — Dual Format Support

**Problem.** `extract_header()` only accepted `DD/MM/YYYY`; Format 2 PDFs
using `DD-MM-YYYY` (e.g. `26-12-2024`) failed silently. Additional survey
of real PDFs surfaced two more variants:
- Singular `d'essai` label (vs. plural `d'essais`)
- Missing colon after the date label (`Date d'émission 14-03-2025`)

**Fix — [reports/extractor.py](reports/extractor.py).**

```python
def _parse_date(raw: str):
    """Convertit DD/MM/YYYY, DD-MM-YYYY, DD/MM/YY ou DD-MM-YY en objet date."""
    if not raw:
        return None
    raw = raw.strip().replace("-", "/")
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None
```

All four date-field regexes now use `\d{2}[-/]\d{2}[-/]\d{4}`, with the
colon optional (`\s*:?\s*`) and `d'essais?` accepting singular + plural:

| Field              | Pattern (core) |
|--------------------|----------------|
| date_emission      | `Date\s+d.émission\s*:?\s*(\d{2}[-/]\d{2}[-/]\d{4})` |
| date_prelevement   | `Date\s+du\s+prélèvement\s*:?\s*(\d{2}[-/]\d{2}[-/]\d{4})` |
| date_reception     | `Date\s+de\s+réception\s*:?\s*(\d{2}[-/]\d{2}[-/]\d{4})` |
| date_debut_essais  | `Date\s+du\s+début\s+d.essais?\s*:?\s*(\d{2}[-/]\d{2}[-/]\d{4})` |

Verified across three representative PDFs (EL MAZRAA, SABA 14-03-2025,
CEDRIA 20-10-2025).

### 9.2 Responsable Laboratoire — Default Value

Some rapports omit the `Responsable laboratoire` block. To avoid
producing `RapportHeader.responsable_laboratoire=""` downstream, the
extractor now falls back to `"HAZZI HASSEN"`.

```python
# reports/extractor.py:90-92
responsable = _field(
    r"Responsable\s+(?:du\s+)?laboratoire\s*\n?\s*([A-Z][A-Za-zÀ-ÿ\s]{3,30})", text
) or "HAZZI HASSEN"
```

### 9.3 Méthode d'essai — New Column with Per-Format Handling

**Design constraint.** Two report layouts coexist:

| Format | Table columns |
|--------|---------------|
| **A**  | Essais \| Méthode d'essai \| Résultat \| Unités |
| **B**  | Essais \| Résultat \| Unités |

Before this session, `extract_resultats_pdf()` assumed Format B and
silently shifted Format A columns (méthode was dropped, résultat went
into the méthode slot).

**Schema change.**

```python
# reports/models.py — RapportResultat
essai         = models.CharField(max_length=200, verbose_name="Essai")
methode_essai = models.CharField(max_length=300, blank=True,
                                  verbose_name="Méthode d'essai")
resultat      = models.CharField(max_length=200, verbose_name="Résultat")
unite         = models.CharField(max_length=100, blank=True, verbose_name="Unités")
```

Migration: `reports/migrations/0007_rapportresultat_methode_essai.py`
(applied to `Projet_pfe` on SQL Server — verified via
`INFORMATION_SCHEMA.COLUMNS`: column exists as `nvarchar(300)`).

**Extractor change — header detection.** The parser now inspects the
header row of each candidate table for the literal `"thode"` substring
(case-insensitive) to locate the méthode column. The offset from the
méthode column is then used to read `resultat` and `unite`:

```python
# reports/extractor.py — inside extract_resultats_pdf()
for i, cell in enumerate(row):
    if cell and "thode" in cell.lower():
        methode_idx = i
        break
```

If `methode_idx is None` → Format B path (methode_essai="").
If present → Format A path, columns read at offsets `+0/+1/+2` from
the méthode index.

**Design decision: no lookup fallback.** An earlier iteration used a
hardcoded `METHODE_LOOKUP` dict to infer méthode from the essai name
(e.g. `pH → Electrochimie`). Per user requirement this was **removed** —
méthode is only populated when the PDF actually provides it. Rationale:
lookup values risked being wrong for non-standard or newer methods;
absence is more honest than a guessed default.

**View wiring — [reports/views.py:_run_extraction](reports/views.py).**

```python
RapportResultat.objects.create(
    header=header_obj,
    essai=row['essai'],
    methode_essai=row.get('methode_essai', ''),
    resultat=row['resultat'],
    unite=row['unite'],
)
```

**SSMS caveat.** SQL Server Management Studio caches table schemas.
After the migration, `SELECT TOP 1000 Rows` auto-generated queries may
still reference the old column list. Right-click `Tables → Refresh` in
Object Explorer (or write the SELECT manually including
`[methode_essai]`) to see the new column.

### 9.4 Media File Serving in Development

**Problem.** Clicking a PDF link in the dashboard returned a Django
404 page. `{{ report.file.url }}` produced `/reports/<filename>.pdf`
which collided with the `reports/` app URLconf. `MEDIA_URL` /
`MEDIA_ROOT` had never been defined.

**Fix.**

```python
# config/settings.py
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR   # preserves existing upload_to='reports/' paths
```

```python
# config/urls.py
from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

`report.file.url` now yields `/media/reports/<filename>.pdf`. No files
moved on disk; existing DB rows still resolve.

**Production note.** The `DEBUG`-gated `static()` helper is dev-only.
For production, serve `/media/` via the reverse proxy (nginx/IIS) or
cloud storage (Azure Blob, S3) with the same URL prefix.

### 9.5 Multi-File Batch Upload

**Backend — [reports/views.py:upload_report](reports/views.py).** Now iterates
`request.FILES.getlist('file')`. Each file goes through the same
extension/size check before being turned into a `Report`. Exceptions
during save or extraction are caught **per file**, so one bad upload
doesn't abort the batch.

```python
# Constants declared at module scope
MAX_UPLOAD_SIZE = 25 * 1024 * 1024   # 25 MB
MAX_FILES_PER_BATCH = 10
ALLOWED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.tiff'}
```

- **Title handling.** When >1 file is uploaded with a single title, the
  filename is appended so each `Report.title` stays distinct
  (`"Rapport Labo Mars — file1.pdf"`).
- **Per-file feedback.** `django.contrib.messages` produces a success or
  error alert per file, plus a batch-level summary (`N réussi(s),
  M échec(s)`).

**Frontend — [reports/templates/reports/dashboard.html](reports/templates/reports/dashboard.html).**

- `<input type="file" name="file" multiple>` with `accept`
- JS wraps file selection & drag-drop in a single `applyFiles()` helper
  performing client-side validation (ext, 25 MB, 10-file cap). Selected
  files render as a bullet list with per-file MB footprint.
- Bootstrap alerts block added above the admin banner to surface
  `messages.success / error / warning`.

**Standalone page — [reports/templates/reports/upload.html](reports/templates/reports/upload.html).**
Rewritten from `{% for field in form %}` boilerplate to an explicit form
with multi-file input and a preview list. The `ReportForm` ModelForm is
still used, but only for GET-side metadata; POST is handled directly
(file list + title + `extract_now` flag).

### 9.6 Repository & Git Hygiene

- **.gitignore** added at repo root — ignores bytecode (`__pycache__/`,
  `*.py[cod]`), virtualenv (`venv/`, `.venv/`), Django state
  (`db.sqlite3`, `media/`, `staticfiles/`), env files, IDE metadata, and
  client lab data (`reports/*.pdf`, `reports/*.jpg`, etc.). Lab reports
  are **not** committed to git.
- **Git identity** set at repo-local scope only (`git config --local`)
  — not global.
- **Outstanding TODO.** `SECRET_KEY` at [config/settings.py:24](config/settings.py#L24)
  is the Django-generated `django-insecure-…` default. Move to an env
  variable (and rotate) before any production deployment.

### 9.7 Database Engine Reminder

The project targets **Microsoft SQL Server** via `django-mssql-backend`
(driver: `ODBC Driver 17 for SQL Server`). Any developer running
migrations must have the driver installed and `Projet_pfe` reachable
on `localhost:1433` with trusted connection. Migrations do not use
SQLite — `db.sqlite3` is gitignored but has no functional role.

---

*Generated for LabAssistant v1.0 — Poulina Group Holding PFE Project — 2026*
