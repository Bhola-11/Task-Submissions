# Student Task Submission Portal
## Django + MVT + PostgreSQL + Google Drive API Integration

A production-ready **Django + MVT + PostgreSQL** web application enabling students to securely submit assignment/project ZIP archives and providing instructors/administrators with a high-performance dashboard to manage, review, inspect, download, and synchronize submissions directly with **Google Drive**.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Features](#2-features)
3. [Technology Stack](#3-technology-stack)
4. [Critical ZIP Integrity & Non-Repackaging Guarantee](#4-critical-zip-integrity--non-repackaging-guarantee)
5. [MVT Architecture](#5-mvt-architecture)
6. [Folder Structure](#6-folder-structure)
7. [PostgreSQL Setup](#7-postgresql-setup)
8. [Environment Variables](#8-environment-variables)
9. [Installation](#9-installation)
10. [Google Drive API Setup](#10-google-drive-api-setup)
11. [Migrations](#11-migrations)
12. [Running Locally](#12-running-locally)
13. [Creating Admin User](#13-creating-admin-user)
14. [ZIP Upload & SHA-256 Checksum Calculation](#14-zip-upload--sha-256-checksum-calculation)
15. [Admin Dashboard & Google Drive Status](#15-admin-dashboard--google-drive-status)
16. [Individual Google Drive Sync & Local ZIP Download](#16-individual-google-drive-sync--local-zip-download)
17. [Save All to Google Drive (Server-Side Batch Sync)](#17-save-all-to-google-drive-server-side-batch-sync)
18. [Download All ZIPs (Master Archive)](#18-download-all-zips-master-archive)
19. [Testing & Verification](#19-testing--verification)
20. [Security Audit & Protections](#20-security-audit--protections)

---

## 1. Project Overview

The **Student Task Submission Portal** is designed for educational institutions, bootcamps, and coding academies. It provides:
- A modern, accessible student landing page with drag-and-drop ZIP upload and real-time upload progress tracking.
- Rigorous security inspection including binary magic-byte validation, extension filtering, MIME validation, file size enforcement, and path-traversal protection.
- Immediate **SHA-256 binary checksum computation** stored in PostgreSQL for strict integrity auditing.
- Exact preservation of student ZIP archives (including `.git/`, `.gitignore`, hidden files, and nested directories).
- A custom Admin Dashboard with aggregated metrics, status filters, search, pagination, individual original ZIP downloads, a dynamically generated master ZIP packager, and **Google Drive cloud synchronization**.

---

## 2. Features

### Student Submission Portal
* **Drag & Drop Upload Zone**: Interactive upload area with drag-over visual feedback, file picker, file size/name preview, and file remove/replace options.
* **Progress Bar & Loading State**: Real-time progress bar powered by `XMLHttpRequest.upload.onprogress`.
* **Multi-Layer ZIP Security**:
  * Extension validation (`.zip` only).
  * MIME type inspection.
  * **Binary Magic Byte Validation**: Inspects headers for `PK\x03\x04`, `PK\x05\x06`, and `PK\x07\x08`.
  * Configurable file size limits (`MAX_FILE_SIZE_MB`).
  * Unique server-side filename generation (`submission_<UUID>_<timestamp>.zip`).
* **SHA-256 Checksum**: Calculates hexadecimal hash of original stream upon upload for integrity verification.
* **Instant Submission Receipt**: Confirmation page showing Submission ID, Student Name, Task Name, Stored Size, and a one-click Copy ID button.

### Custom Admin Dashboard & Google Drive Sync
* **Custom Admin Authentication**: Session-protected login and logout workflows.
* **Summary Metrics Grid**: Live aggregation of Total Submissions, Pending, Reviewed, Today's Submissions, Total Storage, and **Google Drive Synced** count.
* **Search & Filter**: Search by student, task, filename, or SHA-256 hash; filter by Review Status (`Pending`, `Reviewed`), Google Drive Status (`Uploaded`, `Not Uploaded`, `Failed`), and submission date.
* **Pagination**: High-performance database pagination.
* **Status Toggling**: One-click toggle between `Pending` and `Reviewed`.
* **Individual Google Drive Upload**: Directly syncs the student's original unmodified ZIP to Google Drive.
* **Save All to Google Drive**: Server-side batch synchronization of all student task ZIPs without client browser downloads.
* **Individual ZIP Download**: Direct streaming download of original unmodified student archives.
* **Download All ZIPs**: Dynamically generates `All-Student-Tasks-YYYY-MM-DD.zip` containing all individual intact student ZIPs.

---

## 3. Technology Stack

* **Backend Framework**: Python 3.11+, Django 5.0 (MVT Pattern)
* **Database**: PostgreSQL 17+ (using `psycopg2-binary`)
* **Cloud Storage**: Google Drive API v3 (`google-api-python-client`, `google-auth`, `google-auth-oauthlib`, `google-auth-httplib2`)
* **Frontend**: Semantic HTML5, Vanilla CSS3 (Custom Design System with CSS Variables), Vanilla JavaScript (ES6+)
* **Static Assets**: WhiteNoise
* **Environment Management**: `python-dotenv`

---

## 4. Critical ZIP Integrity & Non-Repackaging Guarantee

The application follows the strict **Original ZIP Preservation Rule**:

```
[ Student ZIP Upload ]
         │
         ▼
[ Binary Magic Byte Validation & SHA-256 Checksum ]
         │
         ▼
[ Store Original ZIP Binary in media/submissions/ ]
         │
         ▼
[ Google Drive API: MediaFileUpload(original_zip_path) ]
         │
         ▼
[ Google Drive Cloud Storage (Intact ZIP) ]
```

* **No Extraction**: The application NEVER extracts or decompresses student ZIP files.
* **No Stripping**: `.git/`, `.gitignore`, hidden files/folders (`.env`, `.vscode`), configuration files, and nested directories are preserved 100% intact.
* **No Repackaging**: ZIP files uploaded to Google Drive or downloaded in master archives are byte-exact streams of the original upload.

---

## 5. MVT Architecture

```
[ HTTP Request ]
       │
       ▼
   urls.py ────────► views.py (Controllers & Request Handlers)
                        │           ▲
             ┌──────────┴──────┐    │
             ▼                 ▼    │
      forms.py /          services/
      validators.py       ├── __init__.py (Submission & Packaging Logic)
                          └── google_drive_service.py (Drive API Client & Sync)
                               │
                               ▼
                          models.py ◄───► PostgreSQL Database (Github_db)
                               │
                               ▼
                         templates/ (Jinja/Django HTML UI) & static/ (CSS/JS)
                               │
                               ▼
                        [ HTTP Response ]
```

---

## 6. Folder Structure

```text
Submission_System/
│
├── manage.py                     # Django CLI utility
├── verify_acceptance.py          # End-to-end acceptance test script
├── requirements.txt              # Production dependencies
├── .env                          # Local environment settings
├── .env.example                  # Environment configuration template
├── .gitignore                    # Version control ignore list
├── README.md                     # Comprehensive documentation
│
├── config/                       # Project configuration
│   ├── __init__.py
│   ├── settings.py               # Database, security, and storage settings
│   ├── urls.py                   # Root URL routing & error handlers
│   ├── wsgi.py                   # WSGI server entrypoint
│   └── asgi.py                   # ASGI server entrypoint
│
├── submissions/                  # Core application
│   ├── __init__.py
│   ├── apps.py                   # Application registry
│   ├── admin.py                  # Standard Django Admin registration
│   ├── models.py                 # Submission model & PostgreSQL indexes
│   ├── views.py                  # Student, Admin & Google Drive view handlers
│   ├── forms.py                  # Student submission & Admin filter forms
│   ├── validators.py             # Binary magic byte & size validators
│   ├── context_processors.py     # Global template settings processor
│   ├── urls.py                   # App URL routes
│   │
│   ├── services/
│   │   ├── __init__.py           # Submission management & Master ZIP packager
│   │   └── google_drive_service.py # Google Drive v3 API & SHA-256 checksums
│   │
│   ├── management/
│   │   └── commands/
│   │       └── setup_admin.py    # Creates default superuser
│   │
│   ├── migrations/
│   │   ├── 0001_initial.py
│   │   ├── 0002_submission_google_drive_error_and_more.py
│   │   └── __init__.py
│   │
│   ├── static/
│   │   └── submissions/
│   │       ├── css/
│   │       │   ├── styles.css    # Core responsive stylesheet
│   │       │   └── admin.css     # Admin dashboard & Google Drive styles
│   │       └── js/
│   │           ├── upload.js     # Drag-and-drop & progress upload logic
│   │           └── admin.js      # Copy ID & interactive controls
│   │
│   ├── templates/
│   │   └── submissions/
│   │       ├── base.html         # Base HTML layout
│   │       ├── submit.html       # Student upload landing page
│   │       ├── success.html      # Submission receipt confirmation
│   │       ├── admin_login.html  # Custom admin login form
│   │       ├── dashboard.html    # Admin management dashboard
│   │       ├── submission_detail.html # Single submission view with Drive sync
│   │       └── errors/
│   │           ├── 400.html
│   │           ├── 403.html
│   │           ├── 404.html
│   │           └── 500.html
│   │
│   └── tests/
│       ├── __init__.py
│       ├── test_models.py        # Model unit tests
│       ├── test_validators.py    # Magic bytes & security tests
│       ├── test_views.py         # HTTP endpoint & Google Drive view tests
│       └── test_services.py      # Aggregation & Google Drive mock tests
│
├── media/
│   └── submissions/              # Secure physical ZIP file repository
│
└── static/                       # Project-level static directory
```

---

## 7. PostgreSQL Setup

Create or verify the PostgreSQL database:

```sql
CREATE DATABASE "Github_db";
```

---

## 8. Environment Variables

Create `.env` in the root directory:

```ini
SECRET_KEY=django-insecure-production-ready-submission-portal-key-2026
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost

DB_NAME=Github_db
DB_USER=postgres
DB_PASSWORD=your_postgres_password
DB_HOST=localhost
DB_PORT=5432

MAX_FILE_SIZE_MB=50
MEDIA_ROOT=

# Google Drive API Integration
GOOGLE_SERVICE_ACCOUNT_FILE=path/to/service_account.json
GOOGLE_DRIVE_FOLDER_ID=your_google_drive_folder_id_here
```

---

## 9. Installation

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## 10. Google Drive API Setup

1. Create a Google Cloud Project in the [Google Cloud Console](https://console.cloud.google.com/).
2. Enable the **Google Drive API**.
3. Create a **Service Account** and download the JSON key file (e.g., `service_account.json`).
4. Place `service_account.json` in your project folder (it is automatically ignored by `.gitignore`).
5. In Google Drive, create a folder for student submissions (e.g., `Student Task Submissions`).
6. Share that folder with your Service Account's email address (with **Editor** permissions).
7. Copy the Folder ID from the Google Drive URL (`https://drive.google.com/drive/folders/<FOLDER_ID>`) and set `GOOGLE_DRIVE_FOLDER_ID` in `.env`.

---

## 11. Migrations

Apply migrations to PostgreSQL:

```bash
python manage.py migrate
```

---

## 12. Running Locally

Start the development server:

```bash
python manage.py runserver 127.0.0.1:8000
```

* **Student Portal**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
* **Admin Dashboard**: [http://127.0.0.1:8000/admin/dashboard/](http://127.0.0.1:8000/admin/dashboard/)
* **Django Admin**: [http://127.0.0.1:8000/django-admin/](http://127.0.0.1:8000/django-admin/)

---

## 13. Creating Admin User

```bash
python manage.py setup_admin
```
* **Default Username**: `admin`
* **Default Password**: `admin123`

---

## 14. ZIP Upload & SHA-256 Checksum Calculation

When a student submits their assignment:
1. Client and server validate extension (`.zip`), MIME type, and magic bytes (`PK\x03\x04`, `PK\x05\x06`, `PK\x07\x08`).
2. Server calculates the **SHA-256 hexadecimal checksum** from the binary stream without decompressing.
3. The original file is stored under `media/submissions/submission_<UUID>_<timestamp>.zip`.
4. Metadata is saved in PostgreSQL: `sha256_checksum`, `file_size`, `status='Pending'`, `google_drive_status='Not Uploaded'`.

---

## 15. Admin Dashboard & Google Drive Status

The dashboard displays:
- **KPI Cards**: Total Submissions, Pending, Reviewed, **Google Drive Synced**, and Total Storage.
- **Filters**: Filter by Review Status and **Google Drive Status** (`Not Uploaded`, `Uploaded`, `Failed`).
- **Table Badges**:
  - `☁️ Uploaded` (includes link to open file in Google Drive).
  - `Not Uploaded`.
  - `❌ Failed` (includes error tooltip).

---

## 16. Individual Google Drive Sync & Local ZIP Download

- **Save to Google Drive**: Click `☁️ Drive` on any submission row or on the detail page to upload that student's original ZIP.
- **Local Download**: Click `Download` to download the student's original ZIP directly.

---

## 17. Save All to Google Drive (Server-Side Batch Sync)

Click **Save All to Google Drive** in the top bar:
- Server-side execution: The administrator's browser does **NOT** download any files.
- Django iterates through all submissions and streams each original ZIP to the Google Drive folder.
- Skips already uploaded files unless forced.
- Displays summary:
  ```text
  Google Drive Sync Completed — Total: 150, Uploaded: 142, Already Uploaded: 5, Failed: 3
  ```

---

## 18. Download All ZIPs (Master Archive)

Click **Download All ZIPs** to generate `All-Student-Tasks-YYYY-MM-DD.zip`:
- Contains all individual student ZIPs untouched:
  ```text
  All-Student-Tasks-2026-09-04.zip
  ├── Rahul_Portfolio.zip
  ├── Aman_Ecommerce.zip
  └── Priya_AI_Chatbot.zip
  ```

---

## 19. Testing & Verification

### Run Unit & Integration Tests:
```bash
python manage.py test
```
*25 automated tests covering models, validators, magic-byte inspection, services, views, and Google Drive mock sync.*

### Run End-to-End Acceptance Test:
```bash
python verify_acceptance.py
```
*Tests submissions with `.git/` folders, validates SHA-256 checksums, tests Google Drive sync, and verifies master ZIP packaging.*

---

## 20. Security Audit & Protections

| Security Layer | Implementation |
|---|---|
| **Binary Magic Bytes** | Rejects non-ZIP files disguised with `.zip` extensions. |
| **Path Traversal Defense** | Sanitizes original filenames, preventing `../` traversal attacks. |
| **SHA-256 Checksums** | Audits stored files against binary tampering. |
| **Credential Protection** | Service account JSON files excluded via `.gitignore`. |
| **Role-Based Access Control** | Admin dashboard and Google Drive actions restricted to staff superusers. |
| **CSRF & Injection Defense** | Full CSRF verification and Django ORM parameterized queries with PostgreSQL indexing. |
