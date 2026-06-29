# 🐸 INSC 30313 – Peer Evaluation

**The Fresh Connection Simulation** · Texas Christian University · Neeley School
of Business

A self-contained [Streamlit](https://streamlit.io) web application for running
**peer evaluations** on team/group projects across the semester, styled with the
official TCU palette.

Students simply enter their **TCU email** and pick a **survey round** — the app
looks up their **section** and **team** from an uploaded Excel roster and shows
only that student's teammates to evaluate. Instructors get a dashboard
summarizing Preparation, Contribution, Fair Share responses, comments, and a
Missing Survey report, and can replace the roster each semester from the
Administration page — no JSON or CSV editing required.

**Storage:** for local development the roster is an Excel workbook and responses
are a CSV in the `data/` folder. For deployment on **Streamlit Community Cloud**
(whose disk is ephemeral), the app instead persists the roster, responses, and
settings to a **Google Spreadsheet** via a service account — see
[Persistent storage](#persistent-storage-local-vs-google-sheets) and
[Deploying to Streamlit Community Cloud](#deploying-to-streamlit-community-cloud).

---

## Features

- **Peer Evaluation** (students): enter your **full TCU email**
  (`mark.layton@tcu.edu`) and the **survey password** the instructor provides
  (both must be valid to open the survey). Choose the survey round (**Rounds 1–4
  Debrief** or **End of Semester Peer Survey**). The app auto-detects your
  section/team and shows only your teammates (never yourself). Rate each teammate
  on **Preparation** and **Contribution** (1–5; every question is required and
  starts unselected), answer **"Did this teammate do their fair share?"
  (Yes/No)**, and add optional comments. **Each round can be submitted exactly
  once** — a duplicate attempt is politely blocked.
- **Dashboard** (instructors): KPI cards (Average Preparation, Average
  Contribution, Fair Share Yes %, Missing Surveys), a searchable per-student
  summary (by name, email, section, or team) that highlights students **needing
  review**, number of reviews received, written comments, a **Missing Survey
  report for both rounds** with CSV export, charts, and CSV exports.
- **Team View** (instructors): pick a **Section → Team** to see every member's
  metrics, Needs Review flag, and comments — designed for use live during oral
  presentations.
- **Administration**: a storage-backend status banner (Google Sheets vs local);
  **Student Survey Access** to view/change the student survey password; course
  settings; **validated** roster upload that reports missing columns, duplicate
  emails, blank cells, and missing section/team assignments *before* the roster
  becomes active; a "Roster Loaded Successfully" summary (Students / Sections /
  Teams / Upload Date); current-roster preview; template/roster downloads; and a
  Semester Reset to clear all submitted evaluations.
- Works out of the box with a sample roster generated on first run.

**Needs Review** flags a student when Average Preparation < 3.0, **or** Average
Contribution < 3.0, **or** they received two or more "No" fair-share responses.

There is **no** Peer Assessment Factor or automatic grade adjustment.

### Branding

The header uses the official TCU purple (`#4D1979`). To show real logos, drop
`assets/tcu_logo.png` (header mark) and/or `assets/horned_frog.png` (upper-right
corner) into the `assets/` folder — see `assets/README.md`. Without them, the
header falls back to a styled "TCU" wordmark and a Horned Frog emoji.

---

## Roster format

The roster is an Excel workbook (`.xlsx`) with these columns (header names are
case-insensitive; extra columns are ignored):

| Column   | Description                              | Example                     |
|----------|------------------------------------------|-----------------------------|
| `email`  | Student's TCU email (the lookup key)     | `avery.nguyen@tcu.edu`      |
| `name`   | Display name                             | `Avery Nguyen`              |
| `section`| Course section                           | `001`                       |
| `team`   | Team name within the section             | `Team Frog`                 |

Friendly header names are accepted (case-insensitive): **Student Name**, **TCU
Email**, **Section**, **Team**. Registrar/Banner exports also work out of the box
— a **`Group`** column (e.g. `Group (1 - 9)`) is treated as the team, and names in
`Last,First` form are shown as `First Last`. On upload the workbook is validated —
duplicate emails, missing columns, blank cells, and missing section/team
assignments are reported before the roster becomes the authoritative source.

A student's **teammates** are everyone sharing the same `section` **and** `team`
(excluding the student themselves). Download a ready-to-fill template from the
**Administration** page.

---

## Project structure

```
TCU Peer Evaluation/
├── app.py                # Streamlit entry point + page routing (UI only)
├── requirements.txt      # Python dependencies (pinned)
├── README.md
├── .gitignore
├── .streamlit/
│   ├── config.toml           # Forced light TCU theme
│   └── secrets.toml.example  # Template for secrets (copy to secrets.toml; never commit real one)
├── assets/               # Brand logos (TCU wordmark + Horned Frog)
├── data/                 # LOCAL fallback only (git-ignored; ephemeral on Cloud)
│   ├── roster.xlsx       # Roster workbook (sample auto-created on first run)
│   ├── roster_meta.json  # Records when the active roster was uploaded
│   ├── app_settings.json # Instructor-editable settings (e.g. student password)
│   └── evaluations.csv   # Created at runtime as evaluations are submitted
└── src/
    ├── __init__.py
    ├── config.py         # Paths, branding, rounds, rubric, roster schema, tab names, sample data
    ├── storage.py        # Persistence + lookups (Google Sheets or local fallback)
    ├── gsheets.py        # Google Sheets backend (auth via st.secrets, read/write tabs)
    ├── evaluation.py     # Summary analytics + Missing Survey report
    └── ui.py             # TCU theme CSS, header/footer, cards (presentation only)
```

---

## Setup & running locally

### 1. Install Python

This project needs **Python 3.10 or newer**. Check whether it is installed:

```powershell
python --version
```

If you see an error (e.g. "Python was not found"), install it from
[python.org/downloads](https://www.python.org/downloads/). During installation
on Windows, **check "Add python.exe to PATH"**, then restart your terminal.

### 2. Create a virtual environment (recommended)

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

### 4. Run the app

```powershell
streamlit run app.py
```

Streamlit will open the app in your browser (usually at
<http://localhost:8501>). With no secrets configured, the app runs in **local
file mode** (data in `data/`) — perfect for offline testing. Configure Google
Sheets secrets (below) to use durable external storage.

---

## Persistent storage (local vs Google Sheets)

The app auto-detects its storage backend at runtime:

| Backend | When it's used | Where data lives |
|---|---|---|
| **Google Sheets** | `gcp_service_account` **and** `google_sheets.spreadsheet` secrets are present | Worksheet tabs `roster`, `responses`, `roster_meta`, `settings` in your spreadsheet |
| **Local files** (fallback) | secrets are absent | `data/roster.xlsx`, `data/evaluations.csv`, `data/roster_meta.json`, `data/app_settings.json` |

> ⚠️ **Streamlit Community Cloud disks are ephemeral.** Files written to `data/`
> are wiped on every restart/redeploy. **Always configure Google Sheets for any
> real/shared deployment** so responses are never lost. The Administration page
> shows a banner telling you which backend is active.

All app functionality — email lookup, teammate lookup, duplicate prevention, the
two survey rounds, the Missing Survey report, Dashboard, Team View, and CSV
exports — works identically on either backend.

---

## Deploying to Streamlit Community Cloud

These are the exact, end-to-end steps to deploy with Google Sheets storage.

### A. Create the Google Spreadsheet

1. Go to <https://sheets.google.com> and create a **new blank spreadsheet**
   (name it e.g. `INSC 30313 Peer Evaluation Data`).
2. You do **not** need to add tabs or headers — the app creates the `roster`,
   `responses`, `roster_meta`, and `settings` tabs automatically on first use.
3. Copy the spreadsheet **URL** from the browser (or just the long id between
   `/d/` and `/edit`). You'll need it as `google_sheets.spreadsheet`.

### B. Create a Google service account

1. Open the [Google Cloud Console](https://console.cloud.google.com/) and create
   (or select) a project.
2. **APIs & Services → Library**: enable both the **Google Sheets API** and the
   **Google Drive API**.
3. **APIs & Services → Credentials → Create credentials → Service account**.
   Give it a name (e.g. `peer-eval`) and create it (no roles required).
4. Open the new service account → **Keys → Add key → Create new key → JSON**.
   A `.json` key file downloads. **Keep it private — never commit it to GitHub.**
5. Copy the service account's email (looks like
   `peer-eval@your-project.iam.gserviceaccount.com`).
6. Back in your spreadsheet, click **Share** and share it with that email as an
   **Editor**.

### C. Push the code to GitHub

1. Create a GitHub repository and push this project. The entry point is
   **`app.py`** and dependencies are pinned in **`requirements.txt`**.
2. Confirm secrets are **not** committed: `.gitignore` already ignores
   `.streamlit/secrets.toml`, the service-account JSON, and the `data/` files.
   Only `.streamlit/secrets.toml.example` (a placeholder) is in the repo.

### D. Create the app on Streamlit Community Cloud

1. Go to <https://share.streamlit.io> and sign in with GitHub.
2. **Create app → Deploy a public app from a repo**. Select your repository and
   branch, set **Main file path** to `app.py`. (Optionally pick Python 3.11+ under
   *Advanced settings*.)
3. Open **Advanced settings → Secrets** and paste the following, filling in your
   real values (this is the same format as `.streamlit/secrets.toml.example`):

   ```toml
   instructor_password = "your-instructor-password"
   student_password = "your-student-password"

   [gcp_service_account]
   type = "service_account"
   project_id = "your-project-id"
   private_key_id = "..."
   private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
   client_email = "peer-eval@your-project-id.iam.gserviceaccount.com"
   client_id = "..."
   auth_uri = "https://accounts.google.com/o/oauth2/auth"
   token_uri = "https://oauth2.googleapis.com/token"
   auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
   client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/peer-eval%40your-project-id.iam.gserviceaccount.com"
   universe_domain = "googleapis.com"

   [google_sheets]
   spreadsheet = "https://docs.google.com/spreadsheets/d/your-spreadsheet-id/edit"
   ```

   > **Copying `private_key`:** in the downloaded JSON the key contains literal
   > `\n` sequences — paste it exactly as-is (keep the `\n`), wrapped in double
   > quotes, as shown above.

4. Click **Deploy**. On first load the app seeds the `roster` tab with the sample
   roster; replace it from **Administration → Roster Upload**.

### E. Verify

1. Open the app → **Instructor login** with your `instructor_password`.
2. On **Administration**, confirm the banner reads
   **"Persistent storage: Google Sheets."**
3. Upload your real roster, set the **student survey password**, then submit a
   test evaluation as a student and confirm a new row appears in the `responses`
   tab of your spreadsheet.

### Updating secrets later

Change values anytime in **Streamlit Cloud → your app → Settings → Secrets**;
the app restarts automatically. To rotate the student password without touching
secrets, use **Administration → Student Survey Access**.

---

## Typical semester workflow

1. **Instructor → Administration**: download the template, fill in `email`,
   `name`, `section`, `team` for every student, and upload it to set the roster.
2. **Students → Peer Evaluation**: each round, students enter their TCU email,
   choose the round, and rate their teammates.
3. **Instructor → Dashboard**: review KPI cards and Fair Share metrics, scan the
   highlighted students needing review, read comments, and use the Missing Survey
   report to follow up with students who haven't submitted.
4. **Instructor → Team View**: during oral presentations, pick a Section → Team
   to see each member's metrics, Needs Review flag, and comments at a glance.

---

## Common tasks

### Uploading / replacing the roster

1. Log in as instructor (sidebar → **Instructor login**).
2. Go to **Administration → Roster Upload** and choose an `.xlsx`/`.xlsm` file.
3. Review the **Roster Validation Results** (errors block activation; warnings
   don't). When it reports *Ready to activate*, click **Activate this roster**.
4. The active roster is written to the `roster` tab in Google Sheets (or
   `data/roster.xlsx` in local mode) and replaces the previous one. Existing
   submitted responses are **not** deleted.
5. Need a starting point? Use **Administration → Downloads → Download Template**.

### Setting the student survey password

**Administration → Student Survey Access** shows the current password and lets
you change it. Students must enter this (plus their TCU email) to open the survey.

### Exporting results

On the **Dashboard** (instructor), use the **Export** section:

- **Download summary (CSV)** — one row per student with reviews received,
  Average Preparation/Contribution, and Fair Share Yes/No counts.
- **Download raw evaluations (CSV)** — every individual response.

The **Missing Survey report** offers per-round and combined CSV downloads of
students who haven't submitted. (In Google Sheets mode you can also open the
spreadsheet's `responses` tab directly.)

---

## Data & privacy

- **Secrets are never committed.** Passwords and the Google service-account key
  live only in `st.secrets` (local `.streamlit/secrets.toml` or the Streamlit
  Cloud Secrets UI). `.gitignore` excludes `secrets.toml`, `*.json` keys, and the
  `data/` files.
- **Google Sheets mode:** student data lives in your private spreadsheet, shared
  only with the service account and people you choose. Restrict spreadsheet
  sharing accordingly.
- **Local mode:** data stays in the git-ignored `data/` folder.
- Passwords (`instructor_password`, `student_password`) are read from
  `st.secrets`; built-in defaults exist only as a local-dev fallback and should
  be overridden in production.
- The Administration page includes a **Semester Reset** to clear all submitted
  evaluations (the roster is preserved).

---

## Customizing

- Edit branding, survey rounds, the 1–5 rating scale, review thresholds, and the
  sample roster in `src/config.py` (`APP_TITLE`, `APP_SUBTITLE`, `ROUND_CODES`/
  `ROUND_LABELS`, `SCALE_MIN`/`SCALE_MAX`, `REVIEW_SCORE_THRESHOLD`,
  `REVIEW_FAIR_SHARE_NO_THRESHOLD`, `SAMPLE_ROSTER`). Survey rounds are stored
  internally as stable codes (`round_1_4`, `final`) and shown with friendly
  labels.
- Theme colors and the header/footer/cards live in `src/ui.py` (presentation
  only — no business logic).
- The rubric (Preparation, Contribution, Fair Share) is rendered in
  `page_submit` in `app.py` and aggregated in `src/evaluation.py`.
