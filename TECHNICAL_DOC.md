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

*Generated for LabAssistant v1.0 — Poulina Group Holding PFE Project — 2026*
