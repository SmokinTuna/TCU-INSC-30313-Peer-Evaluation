"""Analytics for peer evaluations.

Produces the instructor-facing summaries:

* **Per-student summary** of scores *received*: number of reviews, Average
  Preparation, Average Contribution, and Fair Share Yes/No counts.
* **Missing Survey report**: which students on the roster have not submitted an
  evaluation for a given round.

No grade-adjustment / Peer Assessment Factor logic is included.
"""

from __future__ import annotations

import pandas as pd

from . import config

YES_VALUES = {"yes", "y", "true", "1"}


def _filter_round(df: pd.DataFrame, round_name: str | None) -> pd.DataFrame:
    if round_name and round_name != "All rounds":
        return df[df["round"].astype(str) == str(round_name)]
    return df


def needs_review_mask(frame: pd.DataFrame) -> pd.Series:
    """Boolean mask flagging students who need instructor review.

    Criteria (any of):
      * Average Preparation < REVIEW_SCORE_THRESHOLD
      * Average Contribution < REVIEW_SCORE_THRESHOLD
      * Fair Share "No" count >= REVIEW_FAIR_SHARE_NO_THRESHOLD

    Rows with no reviews (NaN averages) are NOT flagged.
    """
    if frame.empty:
        return pd.Series([], dtype=bool)
    prep = pd.to_numeric(frame.get("avg_preparation"), errors="coerce")
    contrib = pd.to_numeric(frame.get("avg_contribution"), errors="coerce")
    no = pd.to_numeric(frame.get("fair_share_no"), errors="coerce").fillna(0)
    return (
        (prep < config.REVIEW_SCORE_THRESHOLD)
        | (contrib < config.REVIEW_SCORE_THRESHOLD)
        | (no >= config.REVIEW_FAIR_SHARE_NO_THRESHOLD)
    )


def add_needs_review(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``frame`` with a boolean ``needs_review`` column."""
    out = frame.copy()
    out["needs_review"] = needs_review_mask(out)
    return out


def student_summary(df: pd.DataFrame, round_name: str | None = None) -> pd.DataFrame:
    """Aggregate scores received per student.

    Columns: section, team, evaluatee_name, evaluatee_email, num_reviews,
    avg_preparation, avg_contribution, fair_share_yes, fair_share_no.
    """
    columns = [
        "section",
        "team",
        "evaluatee_name",
        "evaluatee_email",
        "num_reviews",
        "avg_preparation",
        "avg_contribution",
        "fair_share_yes",
        "fair_share_no",
    ]
    data = _filter_round(df, round_name)
    if data.empty:
        return pd.DataFrame(columns=columns)

    work = data.copy()
    work["preparation"] = pd.to_numeric(work["preparation"], errors="coerce")
    work["contribution"] = pd.to_numeric(work["contribution"], errors="coerce")
    fair = work["fair_share"].astype(str).str.strip().str.lower()
    work["_fair_yes"] = fair.isin(YES_VALUES).astype(int)
    work["_fair_no"] = (~fair.isin(YES_VALUES) & fair.ne("") & fair.ne("nan")).astype(int)

    grouped = (
        work.groupby(["section", "team", "evaluatee_name", "evaluatee_email"], dropna=False)
        .agg(
            num_reviews=("evaluator_email", "count"),
            avg_preparation=("preparation", "mean"),
            avg_contribution=("contribution", "mean"),
            fair_share_yes=("_fair_yes", "sum"),
            fair_share_no=("_fair_no", "sum"),
        )
        .reset_index()
    )
    grouped["avg_preparation"] = grouped["avg_preparation"].round(2)
    grouped["avg_contribution"] = grouped["avg_contribution"].round(2)
    return grouped[columns].sort_values(["section", "team", "evaluatee_name"]).reset_index(drop=True)


# Columns returned by ``comments``. ``evaluatee_email`` is required: Team View
# attaches each comment to the student who received it, and names are not unique.
COMMENT_COLUMNS: list[str] = [
    "round",
    "section",
    "team",
    "evaluator_name",
    "evaluatee_name",
    "evaluatee_email",
    "comments",
]

_BLANK_TEXT = {"", "nan", "<na>", "nat"}


def _blank_text(value) -> bool:
    """True when a cell has no usable text.

    Scalar checks only. This deliberately does not use the ``.str`` accessor:
    a duplicated header makes ``frame[column]`` a DataFrame, and an integer
    column (CSV inference of section ``036``) has no string accessor. Both
    raised AttributeError on the Team View comments path.
    """
    if isinstance(value, pd.Series):
        return False
    try:
        if value is None or pd.isna(value):
            return True
    except (TypeError, ValueError):
        return False
    return str(value).strip().lower() in _BLANK_TEXT


def _norm_email_value(value) -> str:
    """Lowercase email, or ``""`` when the cell is blank.

    A duplicated ``email`` column makes a roster row return a Series. The
    first non-blank address is the one that was stored.
    """
    if isinstance(value, pd.Series):
        for item in value.tolist():
            text = _norm_email_value(item)
            if text:
                return text
        return ""
    if _blank_text(value):
        return ""
    text = str(value).strip().lower()
    if text == "none":
        return ""
    return text


def _label_key(value) -> str:
    """Compare section/team labels that CSV or Sheets may store as numbers.

    ``"036"``, ``36``, and ``"36.0"`` are the same course section. Names such
    as ``"Team Frog"`` are compared as trimmed text.
    """
    if _blank_text(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.isdigit():
        return str(int(text))
    return text


def collapse_duplicate_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return ``df`` with one column per header name.

    A repeated header (``evaluatee_email`` twice) makes ``df[name]`` a
    DataFrame. Calling ``.str`` on that DataFrame raises
    ``AttributeError: 'DataFrame' object has no attribute 'str'``. Each
    repeated name keeps the first non-blank cell in the row.
    """
    if df is None or not isinstance(df, pd.DataFrame) or not df.columns.has_duplicates:
        return df
    collapsed: dict[str, pd.Series] = {}
    for name in list(dict.fromkeys(df.columns)):
        block = df.loc[:, name]
        if isinstance(block, pd.Series):
            collapsed[name] = block
            continue
        chosen = block.iloc[:, 0].copy()
        for position in range(1, block.shape[1]):
            candidate = block.iloc[:, position]
            blank = chosen.map(_blank_text).astype(bool)
            chosen = chosen.mask(blank, candidate)
        collapsed[name] = chosen
    return pd.DataFrame(collapsed, index=df.index)


def comments(df: pd.DataFrame, round_name: str | None = None) -> pd.DataFrame:
    """Non-empty written comments, with context columns.

    Always returns ``COMMENT_COLUMNS``, including when there are no evaluations
    or no written comments. ``evaluatee_email`` is kept so comments can be
    matched to a roster member. Evaluator email is omitted; instructor views
    that list the writer continue to use ``evaluator_name`` only.
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty or "comments" not in df.columns:
        return pd.DataFrame(columns=COMMENT_COLUMNS)

    data = _filter_round(collapse_duplicate_columns(df), round_name)
    if data.empty:
        return pd.DataFrame(columns=COMMENT_COLUMNS)

    has_text = data["comments"].map(_blank_text).eq(False)
    out = data.loc[has_text].copy()
    for col in COMMENT_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    return out.loc[:, COMMENT_COLUMNS].reset_index(drop=True)


def comments_for_team(comments_df: pd.DataFrame, section: str, team: str) -> pd.DataFrame:
    """Comment rows for one roster section and team.

    Module-level function. Section ``036`` matches evaluations stored as
    ``36`` after CSV type inference, and team ``"2"`` matches ``2``.
    """
    if comments_df is None or not isinstance(comments_df, pd.DataFrame) or comments_df.empty:
        return pd.DataFrame(columns=COMMENT_COLUMNS)
    frame = collapse_duplicate_columns(comments_df)
    if "section" not in frame.columns or "team" not in frame.columns:
        return pd.DataFrame(columns=COMMENT_COLUMNS)
    section_key = _label_key(section)
    team_key = _label_key(team)
    mask = frame["section"].map(_label_key).eq(section_key) & frame["team"].map(_label_key).eq(team_key)
    return frame.loc[mask].reset_index(drop=True)


def comments_for_evaluatee(comments_df: pd.DataFrame, email: str) -> pd.DataFrame:
    """Comment rows about one student, matched on normalized email.

    Module-level function, not a DataFrame method. Call it as
    ``evaluation.comments_for_evaluatee(frame, email)``. An empty frame (no
    evaluations, no written comments, or no comment about this student) is
    returned with the comments schema.
    """
    if comments_df is None or not isinstance(comments_df, pd.DataFrame) or comments_df.empty:
        return pd.DataFrame(columns=COMMENT_COLUMNS)
    frame = collapse_duplicate_columns(comments_df)
    if "evaluatee_email" not in frame.columns:
        return pd.DataFrame(columns=COMMENT_COLUMNS)
    target = _norm_email_value(email)
    if not target:
        return frame.iloc[0:0].reset_index(drop=True)
    emails = frame["evaluatee_email"].map(_norm_email_value)
    return frame.loc[emails.eq(target)].reset_index(drop=True)


def missing_survey(roster: pd.DataFrame, df: pd.DataFrame, round_name: str) -> pd.DataFrame:
    """Roster students who have NOT submitted for ``round_name``.

    A student is considered to have submitted for a round if at least one
    evaluation row exists where they are the evaluator for that round. Students
    with no teammates (solo) are excluded since they have nobody to evaluate.

    Columns: section, team, name, email.
    """
    cols = ["section", "team", "name", "email"]
    if roster.empty:
        return pd.DataFrame(columns=cols)

    # Exclude students who have no teammates in their section+team.
    team_sizes = roster.groupby(["section", "team"])['email'].transform("count")
    eligible = roster[team_sizes > 1].copy()

    submitted_emails: set[str] = set()
    if not df.empty:
        round_df = df[df["round"].astype(str) == str(round_name)]
        submitted_emails = set(round_df["evaluator_email"].astype(str).str.lower())

    missing = eligible[~eligible["email"].str.lower().isin(submitted_emails)]
    return missing[cols].sort_values(["section", "team", "name"]).reset_index(drop=True)


def team_table(df: pd.DataFrame, members: pd.DataFrame, round_name: str | None = None) -> pd.DataFrame:
    """Per-member metrics for a team, including members with zero reviews.

    ``members`` is a roster subset (columns name/email/section/team). Returns one
    row per member with received-score metrics and a ``needs_review`` flag.
    """
    columns = [
        "name",
        "email",
        "num_reviews",
        "avg_preparation",
        "avg_contribution",
        "fair_share_yes",
        "fair_share_no",
        "needs_review",
    ]
    if members.empty:
        return pd.DataFrame(columns=columns)

    base = members[["name", "email"]].copy()
    summ = student_summary(df, round_name)
    if summ.empty:
        merged = base.copy()
        for c in ["num_reviews", "avg_preparation", "avg_contribution", "fair_share_yes", "fair_share_no"]:
            merged[c] = pd.NA
    else:
        right = summ[
            ["evaluatee_email", "num_reviews", "avg_preparation", "avg_contribution", "fair_share_yes", "fair_share_no"]
        ].rename(columns={"evaluatee_email": "email"})
        merged = base.merge(right, on="email", how="left")

    for c in ["num_reviews", "fair_share_yes", "fair_share_no"]:
        merged[c] = pd.to_numeric(merged[c], errors="coerce").fillna(0).astype(int)
    merged = add_needs_review(merged)
    return merged[columns].sort_values("name").reset_index(drop=True)
