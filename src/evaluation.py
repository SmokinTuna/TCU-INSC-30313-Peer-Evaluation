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


def comments(df: pd.DataFrame, round_name: str | None = None) -> pd.DataFrame:
    """Non-empty written comments, with context columns."""
    cols = ["round", "section", "team", "evaluator_name", "evaluatee_name", "comments"]
    data = _filter_round(df, round_name)
    if data.empty:
        return pd.DataFrame(columns=cols)
    has_text = data["comments"].astype(str).str.strip().replace("nan", "").ne("")
    out = data[has_text]
    return out[cols].reset_index(drop=True)


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
