"""Application configuration and filesystem paths.

Central place for constants so the rest of the app does not hard-code paths
or magic strings. Paths are resolved relative to the project root so the app
works regardless of the directory ``streamlit run`` is launched from.
"""

from __future__ import annotations

from pathlib import Path

# Project root is the parent of the ``src`` directory.
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = PROJECT_ROOT / "data"
ASSETS_DIR: Path = PROJECT_ROOT / "assets"

# Optional brand assets. If present, they are displayed in the header; otherwise
# the header gracefully falls back to a styled wordmark.
TCU_LOGO_FILE: Path = ASSETS_DIR / "tcu_logo.png"
FROG_LOGO_FILE: Path = ASSETS_DIR / "horned_frog.png"

# Roster workbook (uploaded/replaced each semester by the instructor on the
# Admin page). A realistic sample is generated automatically on first run.
ROSTER_FILE: Path = DATA_DIR / "roster.xlsx"

# Small sidecar file recording when the active roster was uploaded.
ROSTER_META_FILE: Path = DATA_DIR / "roster_meta.json"

# Submitted peer evaluations are appended here as rows.
EVALUATIONS_FILE: Path = DATA_DIR / "evaluations.csv"

# Instructor-editable application settings (e.g. the student survey password).
SETTINGS_FILE: Path = DATA_DIR / "app_settings.json"

# --- Persistent storage (Google Sheets) ---------------------------------- #
# When the Google service-account secrets are configured (see src/gsheets.py),
# the app persists everything to these worksheet tabs instead of local files,
# because Streamlit Community Cloud disks are ephemeral. Each tab is created
# automatically on first write if it does not already exist.
GS_ROSTER_TAB: str = "roster"
GS_RESPONSES_TAB: str = "responses"
GS_META_TAB: str = "roster_meta"
GS_SETTINGS_TAB: str = "settings"

# Emails entered without a domain get this appended (e.g. "mark.layton").
TCU_EMAIL_DOMAIN: str = "tcu.edu"

# Instructor area is password-gated. For production, override via the
# ``TCU_INSTRUCTOR_PASSWORD`` environment variable or a Streamlit secret named
# ``instructor_password``. This default is only a fallback for local use.
DEFAULT_INSTRUCTOR_PASSWORD: str = "GoFrogs2026"

# Students must enter a shared survey password (provided by the instructor) in
# addition to their TCU email. The instructor can change it on the Administration
# page; this default applies until they do. It is intentionally different from the
# instructor password above.
DEFAULT_STUDENT_PASSWORD: str = "Frogs2026"

# --- Branding / course identity ------------------------------------------- #
APP_TITLE: str = "INSC 30313 – Peer Evaluation"
APP_SUBTITLE: str = "The Fresh Connection Simulation"
APP_ICON: str = "🐸"  # TCU Horned Frogs

# Release metadata shown on the Administration → Version / Build Info panel.
APP_NAME: str = "INSC 30313 Peer Evaluation"
APP_VERSION: str = "1.0.0"
DEPLOYMENT_TARGET: str = "Streamlit Community Cloud"

UNIVERSITY: str = "Texas Christian University"
SCHOOL: str = "Neeley School of Business"
COURSE_CODE: str = "INSC 30313"
COURSE_NAME: str = "Introduction to Supply Chain Management"

# Official TCU palette.
TCU_PURPLE: str = "#4D1979"
TCU_PURPLE_DARK: str = "#3A1259"
TCU_WHITE: str = "#FFFFFF"
TCU_LIGHT_GRAY: str = "#F4F4F6"
REVIEW_HIGHLIGHT: str = "#FEF3C7"  # soft yellow for "needs review" rows

# Rating scale for the numeric criteria (Preparation, Contribution).
SCALE_MIN: int = 1
SCALE_MAX: int = 5

# Survey rounds. Stored internally as stable codes; displayed with friendly
# labels. A student may submit each round exactly once.
ROUND_CODES: list[str] = ["round_1_4", "final"]
ROUND_LABELS: dict[str, str] = {
    "round_1_4": "Rounds 1–4 Debrief",
    "final": "End of Semester Peer Survey",
}
# Display labels in dropdown order.
ROUND_DISPLAY: list[str] = [ROUND_LABELS[c] for c in ROUND_CODES]


def round_label(code: str) -> str:
    """Human-facing label for a stored round code (falls back to the code)."""
    return ROUND_LABELS.get(str(code), str(code))


def round_code(label: str) -> str:
    """Stored code for a display label (falls back to the label)."""
    for code, lbl in ROUND_LABELS.items():
        if lbl == label:
            return code
    return label

# Thresholds used to flag a student for instructor review on the dashboard.
REVIEW_SCORE_THRESHOLD: float = 3.0
REVIEW_FAIR_SHARE_NO_THRESHOLD: int = 2

# Required columns in the roster workbook (canonical internal names).
# Lookups are keyed on email.
ROSTER_COLUMNS: list[str] = ["email", "name", "section", "team"]

# Friendly header names instructors actually use in their workbook, mapped to
# canonical internal names. Matching is case-insensitive and space-trimmed.
ROSTER_COLUMN_ALIASES: dict[str, str] = {
    "student name": "name",
    "name": "name",
    "full name": "name",
    "student": "name",
    "tcu email": "email",
    "email": "email",
    "email address": "email",
    "e-mail": "email",
    "section": "section",
    "course section": "section",
    "team": "team",
    "project team": "team",
    # Registrar/Banner exports label the project team as a "Group" column
    # (e.g. "Group (1 - 9)"). A startswith("group") fallback in storage covers
    # spacing variants; these explicit entries keep matching predictable.
    "group": "team",
    "group #": "team",
    "group number": "team",
    "group (1 - 9)": "team",
    "group (1-9)": "team",
}

# Human-facing labels for required columns (used in validation messages / template).
ROSTER_DISPLAY_HEADERS: dict[str, str] = {
    "name": "Student Name",
    "email": "TCU Email",
    "section": "Section",
    "team": "Team",
}

# Schema for the evaluations CSV, in order.
EVALUATION_COLUMNS: list[str] = [
    "timestamp",
    "round",
    "section",
    "team",
    "evaluator_email",
    "evaluator_name",
    "evaluatee_email",
    "evaluatee_name",
    "preparation",
    "contribution",
    "fair_share",
    "comments",
]

# Sample roster used to generate ``roster.xlsx`` on first run so the project is
# runnable out of the box. The instructor replaces it via the Admin page.
SAMPLE_ROSTER: list[dict] = [
    # Section 001 - Team Frog
    {"email": "avery.nguyen@tcu.edu", "name": "Avery Nguyen", "section": "001", "team": "Team Frog"},
    {"email": "brooks.patel@tcu.edu", "name": "Brooks Patel", "section": "001", "team": "Team Frog"},
    {"email": "carmen.ortiz@tcu.edu", "name": "Carmen Ortiz", "section": "001", "team": "Team Frog"},
    {"email": "dee.williams@tcu.edu", "name": "Dee Williams", "section": "001", "team": "Team Frog"},
    # Section 001 - Team Purple
    {"email": "ethan.brooks@tcu.edu", "name": "Ethan Brooks", "section": "001", "team": "Team Purple"},
    {"email": "fatima.khan@tcu.edu", "name": "Fatima Khan", "section": "001", "team": "Team Purple"},
    {"email": "grace.liu@tcu.edu", "name": "Grace Liu", "section": "001", "team": "Team Purple"},
    {"email": "hector.ramos@tcu.edu", "name": "Hector Ramos", "section": "001", "team": "Team Purple"},
    # Section 002 - Team Horned
    {"email": "isla.gardner@tcu.edu", "name": "Isla Gardner", "section": "002", "team": "Team Horned"},
    {"email": "jamal.carter@tcu.edu", "name": "Jamal Carter", "section": "002", "team": "Team Horned"},
    {"email": "kira.volkov@tcu.edu", "name": "Kira Volkov", "section": "002", "team": "Team Horned"},
    {"email": "liam.oconnor@tcu.edu", "name": "Liam O'Connor", "section": "002", "team": "Team Horned"},
]
