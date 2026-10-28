"""INSC 30313 – Peer Evaluation (The Fresh Connection Simulation).

Streamlit application entry point. Run locally with:

    streamlit run app.py

Students see only the Peer Evaluation page. Instructors unlock the Dashboard,
Team View, and Administration pages with a password (sidebar → Instructor login).

This file is UI/wiring only; all data logic lives in ``src`` and is unchanged
by the UI work (roster validation, calculations, storage, and duplicate
prevention all live there).
"""

from __future__ import annotations

import datetime as dt
import io
import os
import subprocess
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from src import config, evaluation, storage, ui

_PAGE_ICON = str(config.FROG_LOGO_FILE) if config.FROG_LOGO_FILE.exists() else config.APP_ICON
st.set_page_config(page_title=config.APP_TITLE, page_icon=_PAGE_ICON, layout="wide")


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def get_roster() -> pd.DataFrame:
    if "roster" not in st.session_state:
        st.session_state.roster = storage.load_roster()
    return st.session_state.roster


def refresh_roster() -> pd.DataFrame:
    st.session_state.roster = storage.load_roster()
    return st.session_state.roster


def _to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


def _round_code_from_choice(choice: str) -> str | None:
    return None if choice == "All rounds" else config.round_code(choice)


def _instructor_password() -> str:
    """Resolve the instructor password from secrets, env, or the default."""
    try:
        if "instructor_password" in st.secrets:
            return str(st.secrets["instructor_password"])
    except Exception:
        pass
    return os.environ.get("TCU_INSTRUCTOR_PASSWORD", config.DEFAULT_INSTRUCTOR_PASSWORD)


def _style_with_review(disp: pd.DataFrame, status_col: str = "Status"):
    def _row_style(row: pd.Series) -> list[str]:
        color = config.REVIEW_HIGHLIGHT if str(row.get(status_col, "")) else ""
        return [f"background-color: {color}" for _ in row]

    fmt = {}
    for col in ("Avg Preparation", "Avg Contribution"):
        if col in disp.columns:
            fmt[col] = lambda v: "—" if pd.isna(v) else f"{v:.2f}"
    return disp.style.apply(_row_style, axis=1).format(fmt)


def _fmt_avg(value) -> str:
    return "—" if pd.isna(value) else f"{float(value):.2f}"


def _git_run(args: list[str]) -> str:
    """Run a short read-only git command, returning stdout (or '')."""
    try:
        out = subprocess.run(
            ["git", *args], cwd=str(config.PROJECT_ROOT),
            capture_output=True, text=True, timeout=3,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return ""


def _git_commit() -> str:
    return _git_run(["rev-parse", "--short", "HEAD"]) or "unavailable"


def _build_date() -> str:
    """Last commit date when in a git checkout, else this file's modified time."""
    commit_date = _git_run(["log", "-1", "--format=%cd", "--date=format:%Y-%m-%d %H:%M"])
    if commit_date:
        return commit_date
    try:
        ts = Path(__file__).stat().st_mtime
        return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:  # pragma: no cover
        return "unknown"


def _storage_mode() -> str:
    return "Google Sheets" if storage._use_sheets() else "Local File Fallback"


# --------------------------------------------------------------------------- #
# Page: Peer Evaluation (student)
# --------------------------------------------------------------------------- #
def _render_success() -> None:
    ui.success_card(
        "Thank You",
        "<p>Your peer evaluation has been successfully submitted.</p>"
        "<p>Your responses are confidential and have been recorded.</p>"
        "<p>Thank you for helping create a fair evaluation process.</p>"
        "<p>Good luck with the remainder of the semester.</p>",
    )
    if st.button("Submit another evaluation"):
        st.session_state.pop("last_submission", None)
        st.rerun()


def page_submit() -> None:
    if st.session_state.get("last_submission"):
        _render_success()
        return

    ui.info_card(
        "Your Feedback Matters",
        "<p>Please evaluate each teammate honestly, professionally, and objectively.</p>"
        "<p>Your responses are confidential and are used only by the course instructor.</p>"
        "<p>The survey normally requires less than five minutes.</p>",
    )

    roster = get_roster()
    if roster.empty:
        st.warning(
            "No roster has been uploaded yet. Please contact your instructor so the "
            "course roster can be loaded."
        )
        return

    c1, c2 = st.columns([2, 1])
    email_raw = c1.text_input("TCU Email Address", placeholder="mark.layton@tcu.edu")
    access_pw = c1.text_input(
        "Survey Password", type="password", placeholder="Provided by your instructor",
        help="Your instructor will give you this password. It is the same for all students.",
    )
    c1.caption("Enter your full TCU email address (including @tcu.edu) and the survey "
               "password from your instructor. Your section and project team are "
               "identified automatically.")
    round_label = c2.selectbox("Survey Round", options=config.ROUND_DISPLAY)
    round_code = config.round_code(round_label)

    email_clean = email_raw.strip().lower()
    if not email_clean:
        st.info("Enter your full TCU email address to begin.")
        return
    if not email_clean.endswith("@tcu.edu"):
        st.error(
            "Please enter your **full** TCU email address, including **@tcu.edu** "
            "(for example, `mark.layton@tcu.edu`)."
        )
        return

    # Student access gate: email + shared survey password must both be valid.
    if not access_pw:
        st.info("Enter the survey password provided by your instructor to continue.")
        return
    if access_pw.strip() != storage.get_student_password():
        st.error(
            "That survey password is incorrect. Please check the password your "
            "instructor provided and try again."
        )
        return

    student = storage.lookup_student(roster, email_raw)
    if student is None:
        normalized = storage.normalize_email(email_raw)
        st.error(
            f"We couldn't find **{normalized}** in the course roster. "
            "Please double-check your TCU email for typos. If it still isn't found, "
            "contact your instructor so your enrollment can be confirmed."
        )
        return

    mates = storage.teammates(roster, student)
    st.success(
        f"Welcome, **{student['name']}** — Section **{student['section'] or '—'}**, "
        f"**{student['team'] or '—'}**."
    )

    if mates.empty:
        st.warning(
            "We found your record, but you don't have any teammates listed for your "
            "section and team yet. This is usually a roster setup issue — please "
            "contact your instructor so your team assignment can be corrected."
        )
        return

    # Hard duplicate prevention: each round may be submitted once.
    if storage.has_submitted(email_raw, round_code):
        st.info(
            f"✅ You have already submitted the **{round_label}**. "
            "Each student may complete each survey only once. If you believe this "
            "is an error, please contact your instructor."
        )
        return

    ui.info_card(
        "What happens next?",
        '<div class="tcu-steps">'
        '<div class="tcu-step"><span class="tcu-step-num">1</span>'
        "<span>We'll identify your section and project team.</span></div>"
        '<div class="tcu-step"><span class="tcu-step-num">2</span>'
        "<span>You'll evaluate each teammate.</span></div>"
        '<div class="tcu-step"><span class="tcu-step-num">3</span>'
        "<span>Your responses remain confidential.</span></div>"
        "</div>",
    )

    lo, hi = config.SCALE_MIN, config.SCALE_MAX
    rating_options = list(range(lo, hi + 1))
    rating_key = f"{lo} = needs improvement · {hi} = outstanding"
    st.markdown(
        f"Rate each teammate for the **{round_label}** on a **{lo}–{hi}** scale "
        f"({rating_key}). Every question is required — select a number for each one."
    )

    with st.form("evaluation_form"):
        responses: dict[str, dict] = {}
        for _, mate in mates.iterrows():
            with st.container(border=True):
                st.markdown(f"### {mate['name']}")

                prep = st.radio(
                    f"**1. Preparation** — Did {mate['name'].split()[0]} come prepared and "
                    "complete assigned work on time?",
                    options=rating_options, index=None, horizontal=True,
                    key=f"{mate['email']}_prep",
                )
                st.caption(rating_key)
                contrib = st.radio(
                    f"**2. Contribution** — Did {mate['name'].split()[0]} actively contribute "
                    "to the team's work and discussions?",
                    options=rating_options, index=None, horizontal=True,
                    key=f"{mate['email']}_contrib",
                )
                st.caption(rating_key)
                fair = st.radio(
                    f"**3. Fair Share** — Did {mate['name'].split()[0]} do their fair share "
                    "of the work?",
                    options=["Yes", "No"], index=None, horizontal=True,
                    key=f"{mate['email']}_fair",
                )
                comment = st.text_area(
                    "Comments (optional)", key=f"{mate['email']}_comment",
                    placeholder="Specific, constructive feedback...",
                )
            responses[mate["email"]] = {
                "name": mate["name"], "preparation": prep, "contribution": contrib,
                "fair_share": fair, "comments": comment,
            }

        st.markdown("")
        bcol1, bcol2, bcol3 = st.columns([1, 2, 1])
        with bcol2:
            submitted = st.form_submit_button(
                "Submit Evaluation", type="primary", use_container_width=True
            )

    if submitted:
        # Require every rating question to be answered before saving.
        incomplete = [
            data["name"] for data in responses.values()
            if data["preparation"] is None
            or data["contribution"] is None
            or data["fair_share"] is None
        ]
        if incomplete:
            st.error(
                "Please answer **all three questions** (Preparation, Contribution, and "
                "Fair Share) for every teammate before submitting. Still needed for: "
                + ", ".join(incomplete) + "."
            )
            return

        if storage.has_submitted(email_raw, round_code):
            st.info(
                f"It looks like the **{round_label}** was already submitted for your "
                "account, so no new responses were saved."
            )
            return
        normalized = storage.normalize_email(email_raw)
        timestamp = dt.datetime.now().isoformat(timespec="seconds")
        for mate_email, data in responses.items():
            storage.append_evaluation(
                {
                    "timestamp": timestamp,
                    "round": round_code,
                    "section": student["section"],
                    "team": student["team"],
                    "evaluator_email": normalized,
                    "evaluator_name": student["name"],
                    "evaluatee_email": mate_email,
                    "evaluatee_name": data["name"],
                    "preparation": data["preparation"],
                    "contribution": data["contribution"],
                    "fair_share": data["fair_share"],
                    "comments": data["comments"].strip(),
                }
            )
        st.session_state["last_submission"] = {
            "name": student["name"], "round_label": round_label,
        }
        st.rerun()


# --------------------------------------------------------------------------- #
# Page: Dashboard
# --------------------------------------------------------------------------- #
def _dashboard_table(table_view: pd.DataFrame) -> None:
    review_mask = evaluation.needs_review_mask(table_view)
    disp = table_view.copy()
    disp.insert(0, "Status", ["⚠ Needs Review" if flag else "" for flag in review_mask])
    disp = disp.rename(
        columns={
            "evaluatee_name": "Student", "evaluatee_email": "Email",
            "section": "Section", "team": "Team", "num_reviews": "# Reviews",
            "avg_preparation": "Avg Preparation", "avg_contribution": "Avg Contribution",
            "fair_share_yes": "Fair Share: Yes", "fair_share_no": "Fair Share: No",
        }
    )
    disp = disp[
        ["Status", "Student", "Email", "Section", "Team", "# Reviews",
         "Avg Preparation", "Avg Contribution", "Fair Share: Yes", "Fair Share: No"]
    ]
    st.dataframe(_style_with_review(disp), use_container_width=True, hide_index=True)

    flagged = int(review_mask.sum())
    if flagged:
        st.caption(
            f"⚠ {flagged} student(s) flagged for review "
            f"(Avg Preparation or Contribution below {config.REVIEW_SCORE_THRESHOLD:.1f}, "
            f"or {config.REVIEW_FAIR_SHARE_NO_THRESHOLD}+ \"No\" fair-share responses)."
        )


def _missing_block(roster: pd.DataFrame, df: pd.DataFrame, section_filter: list[str]) -> None:
    if roster.empty:
        st.warning(
            "No roster is loaded, so the Missing Survey report can't be computed. "
            "Upload the course roster on the Administration page first."
        )
        return

    combined: list[pd.DataFrame] = []
    for code in config.ROUND_CODES:
        label = config.round_label(code)
        missing = evaluation.missing_survey(roster, df, code)
        if section_filter:
            missing = missing[missing["section"].isin(section_filter)]
        st.markdown(f"**{label}**")
        if missing.empty:
            st.success(f"Everyone (with teammates) has completed the {label}. ✅")
        else:
            st.warning(f"{len(missing)} student(s) have not completed the {label}:")
            st.dataframe(missing, use_container_width=True, hide_index=True)
            st.download_button(
                f"Download missing list — {label} (CSV)",
                data=missing.to_csv(index=False).encode("utf-8"),
                file_name=f"missing_{code}.csv", mime="text/csv", key=f"missing_dl_{code}",
            )
            tagged = missing.copy()
            tagged.insert(0, "round", label)
            combined.append(tagged)

    if combined:
        all_missing = pd.concat(combined, ignore_index=True)
        st.download_button(
            "Download combined missing list (CSV)",
            data=all_missing.to_csv(index=False).encode("utf-8"),
            file_name="missing_all_rounds.csv", mime="text/csv", key="missing_dl_all",
        )


def page_dashboard() -> None:
    roster = get_roster()
    df = storage.load_evaluations()

    c1, c2 = st.columns([1, 2])
    round_choice = c1.selectbox("Survey Round", options=["All rounds"] + config.ROUND_DISPLAY)
    round_code = _round_code_from_choice(round_choice)

    summary = evaluation.student_summary(df, round_code)
    # Section options come from the roster (union with any sections seen in
    # submissions) so sections with zero submissions are NOT hidden from the
    # Missing Survey report.
    roster_sections = (
        [s for s in roster["section"].astype(str).unique() if s.strip()]
        if not roster.empty else []
    )
    summary_sections = list(summary["section"].astype(str).unique()) if not summary.empty else []
    sections = sorted(set(roster_sections) | set(summary_sections))
    section_filter = c2.multiselect("Filter by section", options=sections, default=sections)
    base_view = summary[summary["section"].isin(section_filter)] if section_filter else summary

    missing_count = None
    if round_code is not None:
        miss = evaluation.missing_survey(roster, df, round_code)
        if section_filter:
            miss = miss[miss["section"].isin(section_filter)]
        missing_count = len(miss)

    # --- KPI cards (5) --- #
    ui.section_title("Key metrics", "📊")
    k1, k2, k3, k4, k5 = st.columns(5)
    if base_view.empty:
        with k1: ui.kpi_card("Average Preparation", "—")
        with k2: ui.kpi_card("Average Contribution", "—")
        with k3: ui.kpi_card("Fair Share %", "—")
        with k4: ui.kpi_card("Needs Review", "0")
        with k5: ui.kpi_card("Missing Surveys", "—" if missing_count is None else str(missing_count),
                             warn=bool(missing_count))
    else:
        yes = int(base_view["fair_share_yes"].sum())
        no = int(base_view["fair_share_no"].sum())
        yes_pct = (yes / (yes + no) * 100) if (yes + no) > 0 else 0.0
        flagged = int(evaluation.needs_review_mask(base_view).sum())
        with k1: ui.kpi_card("Average Preparation", f"{base_view['avg_preparation'].mean():.2f}")
        with k2: ui.kpi_card("Average Contribution", f"{base_view['avg_contribution'].mean():.2f}")
        with k3: ui.kpi_card("Fair Share %", f"{yes_pct:.0f}%")
        with k4: ui.kpi_card("Needs Review", str(flagged), warn=flagged > 0)
        with k5: ui.kpi_card("Missing Surveys", "—" if missing_count is None else str(missing_count),
                             warn=bool(missing_count))

    st.markdown("")

    if df.empty:
        st.info("No evaluations have been submitted yet.")
        st.divider()
        ui.section_title("Missing Survey report", "📭")
        _missing_block(roster, df, section_filter)
        return

    # --- Search + Student Summary --- #
    ui.section_title("Student Summary", "👥")
    query = st.text_input(
        "Search", placeholder="Search by student name, TCU email, section, or team…",
        label_visibility="collapsed",
    ).strip().lower()

    table_view = base_view
    if query and not base_view.empty:
        haystack = (
            base_view["evaluatee_name"].astype(str).str.lower() + " "
            + base_view["evaluatee_email"].astype(str).str.lower() + " "
            + base_view["section"].astype(str).str.lower() + " "
            + base_view["team"].astype(str).str.lower()
        )
        table_view = base_view[haystack.str.contains(query, regex=False)]

    if table_view.empty:
        st.caption("No students match the current round, section, or search.")
    else:
        _dashboard_table(table_view)

        chart_df = table_view.melt(
            id_vars=["evaluatee_name", "team"],
            value_vars=["avg_preparation", "avg_contribution"],
            var_name="metric", value_name="score",
        )
        chart_df["metric"] = chart_df["metric"].map(
            {"avg_preparation": "Preparation", "avg_contribution": "Contribution"}
        )
        chart = (
            alt.Chart(chart_df).mark_bar().encode(
                x=alt.X("score:Q", title="Average score (received)", scale=alt.Scale(domain=[0, config.SCALE_MAX])),
                y=alt.Y("evaluatee_name:N", sort="-x", title=None),
                color=alt.Color("metric:N", title="Metric", scale=alt.Scale(range=[config.TCU_PURPLE, "#9B6FC4"])),
                yOffset="metric:N",
                tooltip=["evaluatee_name", "team", "metric", "score"],
            ).properties(height=max(220, 30 * len(table_view)))
        )
        st.altair_chart(chart, use_container_width=True)

    # --- Missing Survey report --- #
    st.divider()
    ui.section_title("Missing Survey report", "📭")
    _missing_block(roster, df, section_filter)

    # --- Comments --- #
    st.divider()
    ui.section_title("Comments", "💬")
    comment_df = evaluation.comments(df, round_code)
    if section_filter and not comment_df.empty:
        comment_df = comment_df[comment_df["section"].isin(section_filter)]
    if not comment_df.empty:
        comment_df = comment_df.copy()
        comment_df["round"] = comment_df["round"].map(config.round_label)
    if comment_df.empty:
        st.caption("No written comments for the current selection.")
    else:
        st.dataframe(comment_df, use_container_width=True, hide_index=True)

    # --- Export --- #
    st.divider()
    ui.section_title("Export", "⬇")
    e1, e2 = st.columns(2)
    e1.download_button(
        "Download summary (CSV)",
        data=summary.to_csv(index=False).encode("utf-8"),
        file_name="peer_evaluation_summary.csv", mime="text/csv", disabled=summary.empty,
    )
    e2.download_button(
        "Download raw evaluations (CSV)",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="peer_evaluation_raw.csv", mime="text/csv", disabled=df.empty,
    )


# --------------------------------------------------------------------------- #
# Page: Team View (cards, for live use during presentations)
# --------------------------------------------------------------------------- #
def page_team_view() -> None:
    roster = get_roster()
    df = storage.load_evaluations()

    ui.section_title("Team View", "🧑‍🤝‍🧑")
    st.caption("Pick a section and team — designed for quick reading live during oral presentations.")

    if roster.empty:
        st.warning("No roster loaded. Please add a roster on the Administration page.")
        return

    sections = sorted(s for s in roster["section"].unique() if str(s).strip())
    if not sections:
        st.warning("The roster has no section assignments.")
        return

    c1, c2, c3 = st.columns(3)
    section = c1.selectbox("Section", options=sections)
    teams = sorted(t for t in roster[roster["section"] == section]["team"].unique() if str(t).strip())
    if not teams:
        st.warning("No teams found for that section.")
        return
    team = c2.selectbox("Team", options=teams)
    round_choice = c3.selectbox("Survey Round", options=["All rounds"] + config.ROUND_DISPLAY)
    round_code = _round_code_from_choice(round_choice)

    members = storage.team_members(roster, section, team)
    table = evaluation.team_table(df, members, round_code)
    cdf = evaluation.comments(df, round_code)
    if not cdf.empty:
        cdf = cdf[(cdf["section"] == section) & (cdf["team"] == team)]

    st.markdown(f"#### {team} — Section {section}")
    if table.empty:
        st.caption("No members found for this team.")
        return

    rows = list(table.iterrows())
    for i in range(0, len(rows), 2):
        cols = st.columns(2)
        for col, (_, member) in zip(cols, rows[i:i + 2]):
            with col:
                with st.container(border=True):
                    badge = ui.review_badge(bool(member["needs_review"]))
                    st.markdown(
                        f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
                        f"<span style='font-weight:700;font-size:1.05rem;'>{member['name']}</span>{badge}</div>",
                        unsafe_allow_html=True,
                    )
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Avg Prep", _fmt_avg(member["avg_preparation"]))
                    m2.metric("Avg Contrib", _fmt_avg(member["avg_contribution"]))
                    m3.metric("Reviews", int(member["num_reviews"]))
                    st.markdown(
                        f"**Fair Share:** {int(member['fair_share_yes'])} Yes · "
                        f"{int(member['fair_share_no'])} No"
                    )
                    member_comments = [
                        f"_{config.round_label(r['round'])}_: {r['comments']}"
                        for _, r in evaluation.comments_for_evaluatee(
                            cdf, member["email"]
                        ).iterrows()
                    ]
                    if member_comments:
                        with st.expander(f"Comments ({len(member_comments)})"):
                            for c in member_comments:
                                st.markdown(f"- {c}")
                    else:
                        st.caption("No comments.")


# --------------------------------------------------------------------------- #
# Page: Administration (console)
# --------------------------------------------------------------------------- #
def _roster_template_bytes() -> bytes:
    template = pd.DataFrame(config.SAMPLE_ROSTER).rename(columns=config.ROSTER_DISPLAY_HEADERS)
    return _to_excel_bytes(template)


def page_admin() -> None:
    roster = get_roster()
    meta = storage.load_roster_meta()

    # --- Storage backend status --- #
    if storage._use_sheets():
        st.success(
            "**Persistent storage: Google Sheets** — the roster and all responses "
            "are saved to your shared spreadsheet and survive app restarts/redeploys."
        )
    else:
        st.warning(
            "**Persistent storage: local files (development mode)** — Google Sheets "
            "secrets are not configured. On Streamlit Community Cloud this is **not** "
            "durable; add the `gcp_service_account` and `google_sheets` secrets so "
            "responses are stored externally. See the README."
        )

    # --- Course Information --- #
    ui.section_title("Course Information", "⚙")
    ui.info_card(
        f"{config.COURSE_CODE} — {config.COURSE_NAME}",
        f"<p><strong>University:</strong> {config.UNIVERSITY}</p>"
        f"<p><strong>School:</strong> {config.SCHOOL}</p>"
        f"<p><strong>Simulation:</strong> {config.APP_SUBTITLE}</p>"
        f"<p><strong>Survey rounds:</strong> {', '.join(config.ROUND_DISPLAY)}</p>"
        f"<p><strong>Rating scale:</strong> {config.SCALE_MIN}–{config.SCALE_MAX} "
        "(Preparation &amp; Contribution); Fair Share = Yes/No</p>",
    )

    # --- Student Survey Access --- #
    st.divider()
    ui.section_title("Student Survey Access", "🔑")
    current_pw = storage.get_student_password()
    ui.info_card(
        "Survey Password",
        "<p>Students must enter this password (along with their TCU email) to open "
        "the peer evaluation survey. Share it with your class; it is the same for "
        "every student and is different from your instructor password.</p>"
        f"<p><strong>Current student password:</strong> "
        f"<code>{current_pw}</code></p>",
    )
    with st.form("student_password_form"):
        new_pw = st.text_input(
            "New student password", value=current_pw,
            help="Students will type this exactly. Avoid spaces at the start or end.",
        )
        saved = st.form_submit_button("Save student password", type="primary")
    if saved:
        cleaned = (new_pw or "").strip()
        if not cleaned:
            st.error("The student password cannot be blank.")
        else:
            storage.set_student_password(cleaned)
            st.success("Student survey password updated.")
            st.rerun()

    # --- Roster Upload --- #
    st.divider()
    ui.section_title("Roster Upload", "📤")
    st.markdown(
        "Upload an Excel workbook (`.xlsx`) to set the authoritative roster. "
        "Required columns (header names are case-insensitive):"
    )
    st.code("Student Name | TCU Email | Section | Team", language="text")
    upload = st.file_uploader(
        "Choose an Excel file",
        type=["xlsx", "xlsm"],
        help="Excel workbook (.xlsx or .xlsm). For older .xls files, open in Excel and "
        "use File → Save As → Excel Workbook (.xlsx).",
    )

    # --- Roster Validation Results --- #
    if upload is not None:
        st.divider()
        ui.section_title("Roster Validation Results", "✅")
        report = storage.validate_roster_bytes(upload.getvalue())

        for err in report["errors"]:
            st.error(f"❌ {err}")
        for warn in report["warnings"]:
            st.warning(f"⚠ {warn}")

        if not report["ok"]:
            st.error("Please fix the errors above and re-upload. The roster was **not** activated.")
        else:
            if not report["warnings"]:
                st.success("Validation passed with no issues.")
            ui.info_card(
                "Ready to activate",
                f"<p><strong>Students:</strong> {report['students']}</p>"
                f"<p><strong>Sections:</strong> {report['sections']}</p>"
                f"<p><strong>Teams:</strong> {report['teams']}</p>",
            )
            st.dataframe(report["clean"].head(50), use_container_width=True, hide_index=True)
            if st.button("Activate this roster", type="primary"):
                storage.save_roster_bytes(upload.getvalue())
                refresh_roster()
                st.success("Roster activated successfully.")
                st.rerun()

    # --- Current Roster --- #
    st.divider()
    ui.section_title("Current Roster", "📋")
    if roster.empty:
        st.caption("No roster loaded.")
    else:
        sections = sorted(s for s in roster["section"].unique() if str(s).strip())
        teams = roster[roster["team"].astype(str).str.strip() != ""][["section", "team"]].drop_duplicates()
        ui.info_card(
            "Roster Loaded Successfully",
            f"<p><strong>Students:</strong> {len(roster)}</p>"
            f"<p><strong>Sections:</strong> {len(sections)}</p>"
            f"<p><strong>Teams:</strong> {len(teams)}</p>"
            f"<p><strong>Upload Date:</strong> {meta.get('uploaded_at', 'Unknown')}</p>",
        )
        st.dataframe(roster, use_container_width=True, hide_index=True)

    # --- Downloads --- #
    st.divider()
    ui.section_title("Downloads", "⬇")
    d1, d2 = st.columns(2)
    d1.download_button(
        "Download Template", data=_roster_template_bytes(),
        file_name="roster_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    d2.download_button(
        "Download Current Roster", data=roster.to_csv(index=False).encode("utf-8"),
        file_name="current_roster.csv", mime="text/csv", disabled=roster.empty,
    )

    # --- Semester Reset --- #
    st.divider()
    ui.section_title("Semester Reset", "♻")
    st.warning(
        "This permanently deletes **all submitted evaluations** so you can start a "
        "fresh semester. The roster is preserved."
    )
    confirm = st.text_input("Type RESET to confirm")
    if st.button("Reset submitted evaluations", type="primary", disabled=confirm != "RESET"):
        storage.reset_evaluations()
        st.success("All submitted evaluations have been cleared.")
        st.rerun()

    # --- Version / Build Info --- #
    st.divider()
    ui.section_title("Version / Build Info", "ℹ")
    ui.info_card(
        "Build Information",
        f"<p><strong>App Name:</strong> {config.APP_NAME}</p>"
        f"<p><strong>Version:</strong> {config.APP_VERSION}</p>"
        f"<p><strong>Build Date:</strong> {_build_date()}</p>"
        f"<p><strong>Git Commit:</strong> <code>{_git_commit()}</code></p>"
        f"<p><strong>Storage Mode:</strong> {_storage_mode()}</p>"
        f"<p><strong>Deployment Target:</strong> {config.DEPLOYMENT_TARGET}</p>",
    )


# --------------------------------------------------------------------------- #
# Sidebar / auth / router
# --------------------------------------------------------------------------- #
INSTRUCTOR_PAGES = {
    "Dashboard": page_dashboard,
    "Team View": page_team_view,
    "Administration": page_admin,
}


def _sidebar() -> str:
    """Render the sidebar and return the selected instructor page (or '')."""
    st.session_state.setdefault("is_instructor", False)
    choice = ""
    with st.sidebar:
        ui.sidebar_brand()

        if st.session_state["is_instructor"]:
            choice = st.radio("Navigate", options=list(INSTRUCTOR_PAGES.keys()),
                              label_visibility="collapsed")
            st.divider()
            if st.button("Logout", use_container_width=True):
                st.session_state["is_instructor"] = False
                st.rerun()
        else:
            st.markdown(
                '<div class="tcu-help">📋 <strong>Peer Evaluation</strong><br/>'
                "Complete your teammate survey on the main page.</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="tcu-help">❓ <strong>Need help?</strong><br/>'
                "Contact your instructor if you have any questions.</div>",
                unsafe_allow_html=True,
            )
            st.divider()
            with st.expander("Instructor login"):
                pwd = st.text_input("Password", type="password", key="instr_pwd")
                if st.button("Log in", use_container_width=True):
                    if pwd and pwd == _instructor_password():
                        st.session_state["is_instructor"] = True
                        st.rerun()
                    else:
                        st.error("Incorrect password.")
    return choice


def main() -> None:
    ui.inject_css()
    get_roster()
    choice = _sidebar()

    ui.render_header()
    if st.session_state.get("is_instructor"):
        INSTRUCTOR_PAGES.get(choice, page_dashboard)()
    else:
        page_submit()
    ui.render_footer()


if __name__ == "__main__":
    main()
