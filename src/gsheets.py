"""Google Sheets persistence backend.

Streamlit Community Cloud's filesystem is **ephemeral**: anything written to disk
is lost when the app restarts or redeploys. To keep peer-evaluation responses and
the roster durable, this module stores them in a Google Spreadsheet instead.

Credentials and the target spreadsheet are read from ``st.secrets`` (never from
the repository):

    [gcp_service_account]      # the service-account JSON, field by field
    type = "service_account"
    project_id = "..."
    private_key_id = "..."
    private_key = "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
    client_email = "svc@project.iam.gserviceaccount.com"
    client_id = "..."
    token_uri = "https://oauth2.googleapis.com/token"

    [google_sheets]
    spreadsheet = "<spreadsheet key or full URL>"

When these secrets are absent (e.g. local development without Google set up),
:func:`is_configured` returns ``False`` and the app falls back to local files.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

# Read + write to the specific spreadsheet (drive scope lets us open by key/URL).
_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# --------------------------------------------------------------------------- #
# Secrets helpers
# --------------------------------------------------------------------------- #
def get_secret(key: str, default: str = "") -> str:
    """Return a top-level secret as a string, or ``default`` if unavailable."""
    try:
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return default


def _spreadsheet_ref() -> str:
    """Spreadsheet key or URL from ``[google_sheets]`` in secrets."""
    try:
        gs = st.secrets.get("google_sheets", {})
        return str(gs.get("spreadsheet") or gs.get("spreadsheet_id") or gs.get("url") or "")
    except Exception:
        return ""


def is_configured() -> bool:
    """True only when service-account secrets and a spreadsheet ref both exist."""
    try:
        has_account = "gcp_service_account" in st.secrets
    except Exception:
        has_account = False
    return bool(has_account and _spreadsheet_ref())


# --------------------------------------------------------------------------- #
# Client / spreadsheet (cached as resources for the session)
# --------------------------------------------------------------------------- #
@st.cache_resource(show_spinner=False)
def _client():
    import gspread
    from google.oauth2.service_account import Credentials

    info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(info, scopes=_SCOPES)
    return gspread.authorize(creds)


@st.cache_resource(show_spinner=False)
def _spreadsheet():
    client = _client()
    ref = _spreadsheet_ref()
    if ref.startswith("http"):
        return client.open_by_url(ref)
    return client.open_by_key(ref)


def _get_or_create_ws(title: str, headers: list[str] | None = None):
    """Return the worksheet, creating it (with optional header row) if missing."""
    sh = _spreadsheet()
    try:
        return sh.worksheet(title)
    except Exception:
        ncols = max(4, len(headers or []))
        ws = sh.add_worksheet(title=title, rows=200, cols=ncols)
        if headers:
            ws.update(values=[headers], range_name="A1")
        return ws


# --------------------------------------------------------------------------- #
# Tabular data (roster, responses)
# --------------------------------------------------------------------------- #
def read_df(title: str) -> pd.DataFrame:
    """Read a worksheet into a DataFrame of strings (empty if tab/data absent)."""
    sh = _spreadsheet()
    try:
        ws = sh.worksheet(title)
    except Exception:
        return pd.DataFrame()
    values = ws.get_all_values()
    if not values:
        return pd.DataFrame()
    header = values[0]
    rows = values[1:]
    df = pd.DataFrame(rows, columns=header)
    # Trim fully blank trailing rows that Sheets sometimes returns.
    if not df.empty:
        df = df[~(df.apply(lambda r: all(str(v).strip() == "" for v in r), axis=1))]
    return df.reset_index(drop=True)


def overwrite_df(title: str, df: pd.DataFrame, headers: list[str] | None = None) -> None:
    """Replace a worksheet's contents with ``df`` (header row + values)."""
    sh = _spreadsheet()
    cols = list(headers or df.columns)
    try:
        ws = sh.worksheet(title)
        ws.clear()
    except Exception:
        ws = sh.add_worksheet(title=title, rows=max(200, len(df) + 10), cols=max(4, len(cols)))
    body = df.reindex(columns=cols).astype(str).values.tolist() if not df.empty else []
    ws.update(values=[cols] + body, range_name="A1", value_input_option="RAW")


def append_row(title: str, values: list, headers: list[str] | None = None) -> None:
    """Append a single row, creating the tab (with headers) if needed."""
    ws = _get_or_create_ws(title, headers)
    ws.append_row([("" if v is None else str(v)) for v in values], value_input_option="RAW")


# --------------------------------------------------------------------------- #
# Key/value data (roster metadata, app settings)
# --------------------------------------------------------------------------- #
def read_kv(title: str) -> dict:
    """Read a two-column ``key``/``value`` worksheet into a dict."""
    df = read_df(title)
    if df.empty or "key" not in df.columns or "value" not in df.columns:
        return {}
    return {str(k): str(v) for k, v in zip(df["key"], df["value"])}


def write_kv(title: str, mapping: dict) -> None:
    """Persist a dict to a two-column ``key``/``value`` worksheet."""
    df = pd.DataFrame({"key": list(mapping.keys()), "value": [str(v) for v in mapping.values()]})
    overwrite_df(title, df, headers=["key", "value"])
