"""Presentation helpers: TCU theme CSS, header/footer, and reusable cards.

This module is purely cosmetic. It contains no business logic — it only injects
styling and renders branded HTML fragments used across the app's pages.
"""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

from . import config


# --------------------------------------------------------------------------- #
# Asset helpers
# --------------------------------------------------------------------------- #
def _data_uri(path: Path) -> str | None:
    """Return a base64 data URI for a local image, or None if it is missing."""
    try:
        if path.exists() and path.is_file():
            mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            return f"data:{mime};base64,{encoded}"
    except Exception:  # pragma: no cover - never let branding break the app
        return None
    return None


# --------------------------------------------------------------------------- #
# Global theme
# --------------------------------------------------------------------------- #
def inject_css() -> None:
    """Inject the TCU theme. Safe to call once near the top of the app."""
    st.markdown(
        f"""
        <style>
        :root {{
            --tcu-purple: {config.TCU_PURPLE};
            --tcu-purple-dark: {config.TCU_PURPLE_DARK};
            --tcu-gray: {config.TCU_LIGHT_GRAY};
        }}

        /* App background + base typography */
        .stApp {{
            background-color: var(--tcu-gray);
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            color: #1f2330;
        }}
        .block-container {{
            padding-top: 1.5rem;
            padding-bottom: 2rem;
            max-width: 1200px;
        }}

        /* Branded header bar (white card, purple text + purple logos) */
        .tcu-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            background: #fff;
            color: var(--tcu-purple);
            border: 1px solid #ECECF1;
            border-bottom: 4px solid var(--tcu-purple);
            border-radius: 16px;
            padding: 1.1rem 1.5rem;
            box-shadow: 0 2px 12px rgba(31, 35, 48, 0.06);
            margin-bottom: 1.25rem;
        }}
        .tcu-header-left {{ display: flex; align-items: center; gap: 1.1rem; }}
        .tcu-mark {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            color: var(--tcu-purple);
            font-weight: 800;
            letter-spacing: 1px;
            font-size: 1.4rem;
            flex: 0 0 auto;
        }}
        .tcu-mark img {{ height: 58px; width: auto; object-fit: contain; }}
        .tcu-title {{ font-size: 1.6rem; font-weight: 700; line-height: 1.15; margin: 0; color: var(--tcu-purple); }}
        .tcu-subtitle {{ font-size: 0.98rem; color: #4b5563; margin: 2px 0 0 0; }}
        .tcu-affil {{ font-size: 0.8rem; color: #6b7280; margin: 6px 0 0 0; letter-spacing: .01em; }}
        .tcu-frog img {{ height: 58px; width: auto; object-fit: contain; }}
        .tcu-frog-emoji {{ font-size: 2.4rem; line-height: 1; }}

        /* Generic card */
        .tcu-card {{
            background: #fff;
            border-radius: 14px;
            padding: 1.1rem 1.3rem;
            box-shadow: 0 2px 10px rgba(31, 35, 48, 0.06);
            border: 1px solid #ECECF1;
            margin-bottom: 1rem;
        }}
        .tcu-card h3 {{ margin: 0 0 .4rem 0; color: var(--tcu-purple); font-size: 1.15rem; }}
        .tcu-card.accent {{ border-left: 5px solid var(--tcu-purple); }}
        .tcu-card p {{ margin: .35rem 0; line-height: 1.5; }}

        /* Green success card */
        .tcu-success {{
            background: #ECFDF3;
            border: 1px solid #ABEFC6;
            border-left: 6px solid #16A34A;
            border-radius: 14px;
            padding: 1.4rem 1.6rem;
            margin-bottom: 1rem;
        }}
        .tcu-success h3 {{ margin: 0 0 .5rem 0; color: #15803D; font-size: 1.3rem; }}
        .tcu-success p {{ margin: .35rem 0; line-height: 1.55; color: #14532D; }}

        /* Status badges */
        .tcu-badge-review {{
            background: #FEF3C7; color: #B45309; border-radius: 999px;
            padding: 3px 12px; font-weight: 700; font-size: .8rem; white-space: nowrap;
        }}
        .tcu-badge-ok {{
            background: #ECFDF3; color: #15803D; border-radius: 999px;
            padding: 3px 12px; font-weight: 600; font-size: .8rem; white-space: nowrap;
        }}

        /* Sidebar help card */
        .tcu-help {{
            background: var(--tcu-gray); border: 1px solid #ECECF1; border-radius: 12px;
            padding: .85rem 1rem; margin-top: .5rem; font-size: .85rem; color: #4b5563;
        }}
        .tcu-help strong {{ color: var(--tcu-purple); }}

        /* Numbered "what happens next" steps */
        .tcu-steps {{ display: flex; flex-direction: column; gap: .6rem; }}
        .tcu-step {{ display: flex; align-items: flex-start; gap: .7rem; }}
        .tcu-step-num {{
            flex: 0 0 auto;
            background: var(--tcu-purple);
            color: #fff;
            width: 28px; height: 28px;
            border-radius: 50%;
            display: inline-flex; align-items: center; justify-content: center;
            font-weight: 700; font-size: .9rem;
        }}

        /* KPI cards */
        .kpi-card {{
            background: #fff;
            border-radius: 14px;
            padding: 1rem 1.1rem;
            border: 1px solid #ECECF1;
            border-top: 4px solid var(--tcu-purple);
            box-shadow: 0 2px 10px rgba(31, 35, 48, 0.06);
            height: 100%;
        }}
        .kpi-label {{
            color: #6b7280; font-size: .82rem; font-weight: 600;
            text-transform: uppercase; letter-spacing: .04em; margin: 0;
        }}
        .kpi-value {{ color: var(--tcu-purple); font-size: 2rem; font-weight: 800; margin: .25rem 0 0 0; }}
        .kpi-value.warn {{ color: #B45309; }}

        /* Primary + download buttons in TCU purple with hover darken */
        .stButton > button[kind="primary"],
        .stFormSubmitButton > button[kind="primary"],
        button[data-testid="stBaseButton-primary"],
        button[data-testid="stBaseButton-primaryFormSubmit"] {{
            background-color: var(--tcu-purple);
            border-color: var(--tcu-purple);
            color: #fff;
            border-radius: 10px;
            font-weight: 600;
            transition: background-color .15s ease, border-color .15s ease;
        }}
        .stButton > button[kind="primary"]:hover,
        .stFormSubmitButton > button[kind="primary"]:hover,
        button[data-testid="stBaseButton-primary"]:hover,
        button[data-testid="stBaseButton-primaryFormSubmit"]:hover {{
            background-color: var(--tcu-purple-dark);
            border-color: var(--tcu-purple-dark);
            color: #fff;
        }}
        .stDownloadButton > button {{
            border-radius: 10px;
            border: 1px solid var(--tcu-purple);
            color: var(--tcu-purple);
            font-weight: 600;
        }}
        .stDownloadButton > button:hover {{
            background-color: var(--tcu-purple);
            color: #fff;
            border-color: var(--tcu-purple);
        }}

        /* Section headings */
        .tcu-section-title {{
            color: var(--tcu-purple);
            font-weight: 700;
            font-size: 1.15rem;
            margin: .25rem 0 .5rem 0;
            display: flex; align-items: center; gap: .5rem;
        }}

        /* Footer */
        .tcu-footer {{
            margin-top: 2rem;
            padding: 1.1rem 0 .25rem 0;
            border-top: 1px solid #E2E2EA;
            text-align: center;
            color: #6b7280;
            font-size: .85rem;
            line-height: 1.5;
        }}
        .tcu-footer strong {{ color: var(--tcu-purple); }}

        /* Input fields: always show a defined boundary (not only on focus) */
        div[data-baseweb="input"],
        div[data-baseweb="base-input"],
        div[data-baseweb="textarea"],
        .stTextArea textarea,
        div[data-baseweb="select"] > div {{
            border: 1px solid #C7CCD6 !important;
            border-radius: 8px !important;
            background-color: #fff !important;
        }}
        div[data-baseweb="input"]:focus-within,
        div[data-baseweb="base-input"]:focus-within,
        .stTextArea textarea:focus,
        div[data-baseweb="select"] > div:focus-within {{
            border-color: var(--tcu-purple) !important;
            box-shadow: 0 0 0 2px rgba(77, 25, 121, 0.15) !important;
        }}

        /* Sidebar accent */
        [data-testid="stSidebar"] {{ background-color: #fff; border-right: 1px solid #ECECF1; }}
        .tcu-sidebar-brand {{
            text-align: center;
            padding: .35rem 0 1rem 0;
            border-bottom: 1px solid #ECECF1;
            margin-bottom: 1rem;
        }}
        .tcu-sidebar-logo {{ height: 60px; width: auto; object-fit: contain; }}
        .tcu-sidebar-mark {{
            display: inline-block;
            color: var(--tcu-purple);
            font-weight: 800;
            font-size: 1.8rem;
            letter-spacing: 2px;
        }}
        .tcu-sidebar-course {{
            margin-top: .5rem;
            font-weight: 700;
            font-size: 1.05rem;
            color: var(--tcu-purple);
        }}
        .tcu-sidebar-school {{ font-size: .8rem; color: #6b7280; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Header / footer
# --------------------------------------------------------------------------- #
def sidebar_brand() -> None:
    """Render the TCU logo + course code at the top of the sidebar."""
    logo_uri = _data_uri(config.TCU_LOGO_FILE)
    logo_html = (
        f'<img class="tcu-sidebar-logo" src="{logo_uri}" alt="TCU"/>'
        if logo_uri
        else '<div class="tcu-sidebar-mark">TCU</div>'
    )
    st.markdown(
        f"""
        <div class="tcu-sidebar-brand">
            {logo_html}
            <div class="tcu-sidebar-course">{config.COURSE_CODE}</div>
            <div class="tcu-sidebar-school">{config.SCHOOL}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    """Render the branded header bar with logo, title, subtitle, and frog mark."""
    logo_uri = _data_uri(config.TCU_LOGO_FILE)
    frog_uri = _data_uri(config.FROG_LOGO_FILE)

    mark_inner = f'<img src="{logo_uri}" alt="TCU logo"/>' if logo_uri else "TCU"
    if frog_uri:
        frog_html = f'<div class="tcu-frog"><img src="{frog_uri}" alt="Horned Frog"/></div>'
    else:
        frog_html = f'<div class="tcu-frog-emoji" title="TCU Horned Frogs">{config.APP_ICON}</div>'

    st.markdown(
        f"""
        <div class="tcu-header">
            <div class="tcu-header-left">
                <div class="tcu-mark">{mark_inner}</div>
                <div>
                    <p class="tcu-title">{config.APP_TITLE}</p>
                    <p class="tcu-subtitle">{config.APP_SUBTITLE}</p>
                    <p class="tcu-affil">{config.UNIVERSITY} · {config.SCHOOL}</p>
                </div>
            </div>
            {frog_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_footer() -> None:
    """Render the institutional footer."""
    st.markdown(
        f"""
        <div class="tcu-footer">
            <strong>{config.UNIVERSITY}</strong><br/>
            {config.SCHOOL}<br/>
            {config.COURSE_CODE} – {config.COURSE_NAME}
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Reusable fragments
# --------------------------------------------------------------------------- #
def info_card(title: str, body_html: str, accent: bool = True) -> None:
    """Render a white rounded card with a purple title and HTML body."""
    cls = "tcu-card accent" if accent else "tcu-card"
    st.markdown(
        f'<div class="{cls}"><h3>{title}</h3>{body_html}</div>',
        unsafe_allow_html=True,
    )


def success_card(title: str, body_html: str) -> None:
    """Render a green success card."""
    st.markdown(
        f'<div class="tcu-success"><h3>✅ {title}</h3>{body_html}</div>',
        unsafe_allow_html=True,
    )


def review_badge(needs_review: bool) -> str:
    """Return badge HTML for a student's review status."""
    if needs_review:
        return '<span class="tcu-badge-review">⚠ Needs Review</span>'
    return '<span class="tcu-badge-ok">✓ OK</span>'


def section_title(text: str, icon: str = "") -> None:
    """Render a purple section heading with an optional leading icon."""
    prefix = f"{icon} " if icon else ""
    st.markdown(f'<div class="tcu-section-title">{prefix}{text}</div>', unsafe_allow_html=True)


def kpi_card(label: str, value: str, warn: bool = False) -> None:
    """Render a single KPI card (use inside an ``st.columns`` cell)."""
    value_cls = "kpi-value warn" if warn else "kpi-value"
    st.markdown(
        f'<div class="kpi-card"><p class="kpi-label">{label}</p>'
        f'<p class="{value_cls}">{value}</p></div>',
        unsafe_allow_html=True,
    )
