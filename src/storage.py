"""Persistence helpers for the roster workbook and submitted evaluations.

* The **roster** is an Excel workbook (``roster.xlsx``) whose columns map to the
  canonical internal names ``email``, ``name``, ``section``, ``team``. Friendly
  headers (e.g. "Student Name", "TCU Email") are accepted via an alias map. The
  instructor uploads/replaces it on the Administration page each semester; a
  realistic sample is generated on first run.
* **Evaluations** are appended to an append-only CSV so they are easy to inspect
  in Excel/Sheets and survive restarts.

All functions are defensive about missing files and bad input. Roster *upload*
goes through :func:`validate_roster` which returns a structured report so the UI
can surface duplicate emails, blank cells, and missing assignments before the
roster becomes the authoritative source.
"""

from __future__ import annotations

import datetime as dt
import io
import json

import pandas as pd

from . import config, gsheets

_BLANK_TOKENS = {"", "nan", "none", "na", "n/a", "<na>"}


def _use_sheets() -> bool:
    """True when Google Sheets is configured (the durable backend on Cloud)."""
    try:
        return gsheets.is_configured()
    except Exception:  # pragma: no cover - never let backend detection crash
        return False


def ensure_data_dir() -> None:
    """Create the data directory if it does not yet exist."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# Email handling
# --------------------------------------------------------------------------- #
def normalize_email(raw: str) -> str:
    """Normalize an email for lookup/storage.

    * trims surrounding whitespace
    * lowercases
    * appends ``@tcu.edu`` when no domain is supplied (e.g. ``mark.layton``)

    Returns an empty string for blank input.
    """
    email = str(raw or "").strip().lower()
    if email in _BLANK_TOKENS:
        return ""
    if "@" not in email:
        email = f"{email}@{config.TCU_EMAIL_DOMAIN}"
    return email


def _is_blank(value) -> bool:
    return str(value).strip().lower() in _BLANK_TOKENS


def _format_name(value: str) -> str:
    """Normalize a display name.

    Registrar exports store names as ``Last,First`` (e.g. ``Baldinelli,Katherine``).
    Convert those to a natural ``First Last`` for the teammate cards. Names that
    are already in normal order are returned unchanged.
    """
    name = str(value or "").strip()
    if "," in name:
        last, _, first = name.partition(",")
        first, last = first.strip(), last.strip()
        if first and last:
            return f"{first} {last}"
    return name


# --------------------------------------------------------------------------- #
# Roster cleaning / validation
# --------------------------------------------------------------------------- #
def _apply_aliases(raw: pd.DataFrame) -> pd.DataFrame:
    """Rename friendly headers to canonical names; drop duplicate columns."""
    rename: dict = {}
    for col in raw.columns:
        key = str(col).strip().lower()
        if key in config.ROSTER_COLUMN_ALIASES:
            rename[col] = config.ROSTER_COLUMN_ALIASES[key]
    out = raw.rename(columns=rename)
    # Fallback for registrar exports: a "Group ..." column is the project team,
    # but only when an explicit team/Project Team column wasn't already matched.
    # This deliberately ignores unrelated columns such as "Exam 3 Team #".
    if "team" not in out.columns:
        for col in out.columns:
            if str(col).strip().lower().startswith("group"):
                out = out.rename(columns={col: "team"})
                break
    # If aliasing produced duplicate canonical columns, keep the first.
    out = out.loc[:, ~out.columns.duplicated()]
    return out


def _clean_for_use(raw: pd.DataFrame) -> pd.DataFrame:
    """Return a usable, normalized roster (alias, trim, drop blank/dup emails).

    Used by :func:`load_roster`. Raises ``ValueError`` if required columns are
    missing so callers fail loudly rather than silently mis-behaving.
    """
    df = _apply_aliases(raw)
    missing = [c for c in config.ROSTER_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError("Roster is missing required column(s): " + ", ".join(missing))

    df = df[config.ROSTER_COLUMNS].copy()
    for col in config.ROSTER_COLUMNS:
        df[col] = df[col].apply(lambda v: "" if _is_blank(v) else str(v).strip())
    df["email"] = df["email"].apply(normalize_email)
    df["name"] = df["name"].apply(_format_name)

    df = df[df["email"] != ""]
    df = df.drop_duplicates(subset=["email"], keep="first").reset_index(drop=True)
    return df


def validate_roster(raw: pd.DataFrame) -> dict:
    """Validate an uploaded roster and return a structured report.

    Report keys:
        ok          - bool, True when there are no blocking errors
        errors      - list[str], blocking issues (prevent activation)
        warnings    - list[str], non-blocking issues (rows may be dropped)
        clean       - cleaned DataFrame ready to persist (or None on hard error)
        students    - int count of usable students
        sections    - int count of distinct sections
        teams       - int count of distinct (section, team) groups
    """
    errors: list[str] = []
    warnings: list[str] = []

    df = _apply_aliases(raw)

    # 1) Required columns present?
    missing = [c for c in config.ROSTER_COLUMNS if c not in df.columns]
    if missing:
        labels = [config.ROSTER_DISPLAY_HEADERS.get(c, c) for c in missing]
        errors.append("Missing required column(s): " + ", ".join(labels))
        return {
            "ok": False,
            "errors": errors,
            "warnings": warnings,
            "clean": None,
            "students": 0,
            "sections": 0,
            "teams": 0,
        }

    work = df[config.ROSTER_COLUMNS].copy()
    for col in config.ROSTER_COLUMNS:
        work[col] = work[col].apply(lambda v: "" if _is_blank(v) else str(v).strip())
    work["email_norm"] = work["email"].apply(normalize_email)

    def _rows(mask: pd.Series) -> str:
        # Excel-style row numbers (header is row 1).
        return ", ".join(str(i + 2) for i in work.index[mask].tolist())

    # 2) Blank cells (warnings) ------------------------------------------------
    blank_name = work["name"] == ""
    blank_email = work["email"] == ""
    blank_section = work["section"] == ""
    blank_team = work["team"] == ""

    if blank_name.any():
        warnings.append(f"{int(blank_name.sum())} row(s) missing Student Name (rows {_rows(blank_name)}).")
    if blank_email.any():
        warnings.append(
            f"{int(blank_email.sum())} row(s) missing TCU Email and will be ignored (rows {_rows(blank_email)})."
        )
    if blank_section.any():
        warnings.append(
            f"{int(blank_section.sum())} student(s) missing a Section assignment (rows {_rows(blank_section)})."
        )
    if blank_team.any():
        warnings.append(
            f"{int(blank_team.sum())} student(s) missing a Team assignment (rows {_rows(blank_team)})."
        )

    # 3) Duplicate emails (error) ---------------------------------------------
    valued = work[work["email_norm"] != ""]
    dup_mask = valued["email_norm"].duplicated(keep=False)
    if dup_mask.any():
        dupes = sorted(valued.loc[dup_mask, "email_norm"].unique())
        errors.append("Duplicate email(s) found: " + ", ".join(dupes))

    # 4) Each student in exactly one section / one team (error) ---------------
    if not valued.empty:
        grp = valued.groupby("email_norm")
        multi_section = grp["section"].nunique()
        multi_team = grp["team"].nunique()
        bad_sections = sorted(multi_section[multi_section > 1].index.tolist())
        bad_teams = sorted(multi_team[multi_team > 1].index.tolist())
        if bad_sections:
            errors.append("Student(s) assigned to multiple sections: " + ", ".join(bad_sections))
        if bad_teams:
            errors.append("Student(s) assigned to multiple teams: " + ", ".join(bad_teams))

    # 5) Build clean frame + stats --------------------------------------------
    clean = _clean_for_use(raw)
    sections = sorted(s for s in clean["section"].unique() if s != "")
    team_pairs = clean[(clean["team"] != "")][["section", "team"]].drop_duplicates()

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "clean": clean,
        "students": int(len(clean)),
        "sections": len(sections),
        "teams": int(len(team_pairs)),
    }


def validate_roster_bytes(data: bytes) -> dict:
    """Read uploaded Excel bytes and return a validation report (see validate_roster)."""
    try:
        raw = pd.read_excel(io.BytesIO(data), dtype=str)
    except Exception as exc:  # pragma: no cover - surfaced to the UI
        return {
            "ok": False,
            "errors": [f"Could not read the Excel file: {exc}"],
            "warnings": [],
            "clean": None,
            "students": 0,
            "sections": 0,
            "teams": 0,
        }
    return validate_roster(raw)


# --------------------------------------------------------------------------- #
# Roster persistence
# --------------------------------------------------------------------------- #
def _generate_sample_roster() -> None:
    """Write the bundled sample roster to ``roster.xlsx`` and record meta."""
    ensure_data_dir()
    pd.DataFrame(config.SAMPLE_ROSTER).to_excel(config.ROSTER_FILE, index=False)
    if not config.ROSTER_META_FILE.exists():
        save_roster_meta(source="sample (auto-generated)")


def load_roster() -> pd.DataFrame:
    """Return the active roster as a normalized DataFrame, creating a sample if absent.

    Uses Google Sheets when configured (durable on Streamlit Cloud); otherwise
    falls back to the local ``roster.xlsx`` for offline development.
    """
    if _use_sheets():
        raw = gsheets.read_df(config.GS_ROSTER_TAB)
        if raw.empty:
            # Seed the spreadsheet with the bundled sample on first run.
            sample = pd.DataFrame(config.SAMPLE_ROSTER)
            gsheets.overwrite_df(config.GS_ROSTER_TAB, sample, headers=list(sample.columns))
            if not gsheets.read_kv(config.GS_META_TAB):
                save_roster_meta(source="sample (auto-generated)")
            raw = sample
        return _clean_for_use(raw)

    ensure_data_dir()
    if not config.ROSTER_FILE.exists():
        _generate_sample_roster()
    # dtype=str preserves codes with leading zeros (e.g. section "001").
    df = pd.read_excel(config.ROSTER_FILE, dtype=str)
    return _clean_for_use(df)


def save_roster_bytes(data: bytes) -> pd.DataFrame:
    """Persist uploaded workbook bytes as the active roster after validating.

    Raises ``ValueError`` (with joined messages) if the roster has blocking
    errors. On success, records the upload timestamp in the meta sidecar.
    """
    report = validate_roster_bytes(data)
    if not report["ok"] or report["clean"] is None:
        raise ValueError("; ".join(report["errors"]) or "Roster failed validation.")
    clean = report["clean"]
    if _use_sheets():
        gsheets.overwrite_df(config.GS_ROSTER_TAB, clean, headers=config.ROSTER_COLUMNS)
    else:
        ensure_data_dir()
        clean.to_excel(config.ROSTER_FILE, index=False)
    save_roster_meta(source="uploaded")
    return clean


def save_roster_meta(source: str = "uploaded") -> dict:
    """Record when the active roster was set."""
    meta = {"uploaded_at": dt.datetime.now().isoformat(timespec="seconds"), "source": source}
    if _use_sheets():
        gsheets.write_kv(config.GS_META_TAB, meta)
    else:
        ensure_data_dir()
        with config.ROSTER_META_FILE.open("w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)
    return meta


# --------------------------------------------------------------------------- #
# Application settings (instructor-editable, e.g. student survey password)
# --------------------------------------------------------------------------- #
def load_app_settings() -> dict:
    """Return the instructor-editable settings dict (empty if not set)."""
    if _use_sheets():
        return gsheets.read_kv(config.GS_SETTINGS_TAB)
    if not config.SETTINGS_FILE.exists():
        return {}
    try:
        with config.SETTINGS_FILE.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # pragma: no cover
        return {}


def save_app_setting(key: str, value) -> dict:
    """Update a single application setting and persist it."""
    settings = load_app_settings()
    settings[key] = value
    if _use_sheets():
        gsheets.write_kv(config.GS_SETTINGS_TAB, settings)
    else:
        ensure_data_dir()
        with config.SETTINGS_FILE.open("w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2)
    return settings


def get_student_password() -> str:
    """Current student survey password.

    Precedence: instructor-set value (settings) → ``student_password`` secret →
    the built-in default. This keeps the password out of source control while
    still allowing the instructor to change it in-app.
    """
    value = str(load_app_settings().get("student_password", "")).strip()
    if value:
        return value
    secret = gsheets.get_secret("student_password", "").strip()
    return secret or config.DEFAULT_STUDENT_PASSWORD


def set_student_password(value: str) -> str:
    """Persist a new student survey password and return it (trimmed)."""
    cleaned = str(value or "").strip()
    save_app_setting("student_password", cleaned)
    return cleaned


def load_roster_meta() -> dict:
    """Return roster metadata (upload date/source), or empty dict if unknown."""
    if _use_sheets():
        return gsheets.read_kv(config.GS_META_TAB)
    if not config.ROSTER_META_FILE.exists():
        return {}
    try:
        with config.ROSTER_META_FILE.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # pragma: no cover
        return {}


# --------------------------------------------------------------------------- #
# Lookups
# --------------------------------------------------------------------------- #
def lookup_student(roster: pd.DataFrame, email: str) -> dict | None:
    """Return the roster row for an email, or None.

    Accepts a bare username (``mark.layton``) or full address; case-insensitive
    and whitespace-trimmed.
    """
    email = normalize_email(email)
    if not email:
        return None
    match = roster[roster["email"] == email]
    if match.empty:
        return None
    return match.iloc[0].to_dict()


def teammates(roster: pd.DataFrame, student: dict) -> pd.DataFrame:
    """Roster rows for the student's section+team, excluding the student.

    Students never see themselves. Returns an empty frame if the student has no
    teammates (e.g. a roster error left them alone on a team).
    """
    same = roster[
        (roster["section"] == student["section"])
        & (roster["team"] == student["team"])
        & (roster["email"] != student["email"])
    ]
    return same.sort_values("name").reset_index(drop=True)


def team_members(roster: pd.DataFrame, section: str, team: str) -> pd.DataFrame:
    """All roster rows for a given section + team (used by the Team View)."""
    members = roster[(roster["section"] == section) & (roster["team"] == team)]
    return members.sort_values("name").reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Evaluations
# --------------------------------------------------------------------------- #
def load_evaluations() -> pd.DataFrame:
    """Load all submitted evaluations with the expected schema."""
    columns = config.EVALUATION_COLUMNS
    if _use_sheets():
        df = gsheets.read_df(config.GS_RESPONSES_TAB)
        if df.empty:
            return pd.DataFrame(columns=columns)
        for col in columns:
            if col not in df.columns:
                df[col] = pd.NA
        extra = [c for c in df.columns if c not in columns]
        return df[columns + extra]

    if not config.EVALUATIONS_FILE.exists():
        return pd.DataFrame(columns=columns)
    df = pd.read_csv(config.EVALUATIONS_FILE)
    for col in columns:
        if col not in df.columns:
            df[col] = pd.NA
    extra = [c for c in df.columns if c not in columns]
    return df[columns + extra]


def append_evaluation(row: dict) -> None:
    """Append a single evaluation row, creating the store/header if needed."""
    if _use_sheets():
        values = [row.get(col, "") for col in config.EVALUATION_COLUMNS]
        gsheets.append_row(config.GS_RESPONSES_TAB, values, headers=config.EVALUATION_COLUMNS)
        return

    ensure_data_dir()
    df_row = pd.DataFrame([row], columns=config.EVALUATION_COLUMNS)
    header = not config.EVALUATIONS_FILE.exists()
    df_row.to_csv(
        config.EVALUATIONS_FILE,
        mode="a",
        header=header,
        index=False,
        encoding="utf-8",
    )


def has_submitted(evaluator_email: str, round_code: str) -> bool:
    """True if this evaluator already submitted for the given round code."""
    email = normalize_email(evaluator_email)
    df = load_evaluations()
    if df.empty or not email:
        return False
    match = (df["evaluator_email"].astype(str).str.lower() == email) & (
        df["round"].astype(str) == str(round_code)
    )
    return bool(match.any())


def reset_evaluations() -> None:
    """Clear all submitted evaluations (instructor 'clear data' action)."""
    if _use_sheets():
        gsheets.overwrite_df(
            config.GS_RESPONSES_TAB,
            pd.DataFrame(columns=config.EVALUATION_COLUMNS),
            headers=config.EVALUATION_COLUMNS,
        )
        return
    if config.EVALUATIONS_FILE.exists():
        config.EVALUATIONS_FILE.unlink()
