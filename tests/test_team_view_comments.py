"""Regression tests for Team View comment lookup.

Production failed with KeyError: 'evaluatee_email' because ``comments()``
dropped the column Team View uses to attach a written comment to the student
who received it. These tests cover that lookup for teams with no evaluations,
evaluations without comments, and completed evaluations.
"""

from __future__ import annotations

import pandas as pd

from src import config, evaluation

BROOKS = "brooks.patel@tcu.edu"
CARMEN = "carmen.ortiz@tcu.edu"
AVERY = "avery.nguyen@tcu.edu"


def _evaluations(*rows: dict) -> pd.DataFrame:
    frame = pd.DataFrame(list(rows), columns=config.EVALUATION_COLUMNS)
    return frame


def _row(**overrides) -> dict:
    base = {
        "timestamp": "2026-10-01T12:00:00",
        "round": "round_1_4",
        "section": "001",
        "team": "Team Frog",
        "evaluator_email": AVERY,
        "evaluator_name": "Avery Nguyen",
        "evaluatee_email": BROOKS,
        "evaluatee_name": "Brooks Patel",
        "preparation": 4,
        "contribution": 5,
        "fair_share": "Yes",
        "comments": "Clear leader.",
    }
    base.update(overrides)
    return base


def _roster() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"name": "Avery Nguyen", "email": AVERY, "section": "001", "team": "Team Frog"},
            {"name": "Brooks Patel", "email": BROOKS, "section": "001", "team": "Team Frog"},
            {"name": "Carmen Ortiz", "email": CARMEN, "section": "001", "team": "Team Frog"},
            {"name": "Isla Gardner", "email": "isla.gardner@tcu.edu", "section": "002", "team": "Team Horned"},
            {"name": "Jules Kim", "email": "jules.kim@tcu.edu", "section": "002", "team": "Team Horned"},
        ]
    )


def _team_comments(df: pd.DataFrame, section: str, team: str, round_code: str | None):
    """Same section/team narrowing Team View does before matching a member."""
    cdf = evaluation.comments(df, round_code)
    if not cdf.empty:
        cdf = cdf[(cdf["section"] == section) & (cdf["team"] == team)]
    return cdf


def _comment_lines(cdf: pd.DataFrame, email: str) -> list[str]:
    return [
        f"_{config.round_label(r['round'])}_: {r['comments']}"
        for _, r in evaluation.comments_for_evaluatee(cdf, email).iterrows()
    ]


def test_comments_schema_includes_evaluatee_email_when_empty():
    empty = pd.DataFrame(columns=config.EVALUATION_COLUMNS)
    cdf = evaluation.comments(empty, "round_1_4")

    assert list(cdf.columns) == evaluation.COMMENT_COLUMNS
    assert cdf.empty
    # The production expression must not raise on a team with no evaluations.
    matched = cdf[cdf["evaluatee_email"] == BROOKS]
    assert matched.empty


def test_team_with_no_evaluations_lists_members_and_no_comments():
    roster = _roster()
    members = roster[(roster["section"] == "001") & (roster["team"] == "Team Frog")]
    table = evaluation.team_table(pd.DataFrame(columns=config.EVALUATION_COLUMNS), members, "round_1_4")
    cdf = _team_comments(pd.DataFrame(columns=config.EVALUATION_COLUMNS), "001", "Team Frog", "round_1_4")

    assert list(table["name"]) == ["Avery Nguyen", "Brooks Patel", "Carmen Ortiz"]
    assert table["num_reviews"].tolist() == [0, 0, 0]
    assert table["needs_review"].tolist() == [False, False, False]
    assert _comment_lines(cdf, BROOKS) == []


def test_blank_comments_are_omitted_without_dropping_scores():
    """Scores were submitted, but nobody wrote a comment."""
    df = _evaluations(
        _row(comments="   "),
        _row(
            evaluator_email=CARMEN,
            evaluator_name="Carmen Ortiz",
            evaluatee_email=AVERY,
            evaluatee_name="Avery Nguyen",
            preparation=2,
            contribution=2,
            fair_share="No",
            comments="",
        ),
    )
    cdf = _team_comments(df, "001", "Team Frog", "round_1_4")
    assert cdf.empty
    assert "evaluatee_email" in cdf.columns
    assert list(cdf[cdf["evaluatee_email"] == BROOKS].iterrows()) == []

    summary = evaluation.student_summary(df, "round_1_4")
    brooks = summary[summary["evaluatee_email"] == BROOKS].iloc[0]
    assert brooks["num_reviews"] == 1
    assert brooks["avg_preparation"] == 4.0
    assert brooks["avg_contribution"] == 5.0
    assert brooks["fair_share_yes"] == 1
    assert brooks["fair_share_no"] == 0


def test_completed_evaluations_attach_comments_by_email():
    df = _evaluations(
        _row(comments="Clear leader."),
        _row(
            evaluator_email=CARMEN,
            evaluator_name="Carmen Ortiz",
            preparation=2,
            contribution=4,
            fair_share="No",
            comments="Missed two meetings.",
        ),
        _row(
            evaluatee_email=CARMEN,
            evaluatee_name="Carmen Ortiz",
            preparation=5,
            contribution=5,
            fair_share="Yes",
            comments="Always prepared.",
        ),
        _row(
            round="final",
            comments="This final-round note must stay on the final round.",
        ),
        _row(
            section="002",
            team="Team Horned",
            evaluator_email="isla.gardner@tcu.edu",
            evaluator_name="Isla Gardner",
            evaluatee_email="jules.kim@tcu.edu",
            evaluatee_name="Jules Kim",
            comments="Different team.",
        ),
    )
    cdf = _team_comments(df, "001", "Team Frog", "round_1_4")

    # This is the expression that raised KeyError: 'evaluatee_email'.
    brooks_rows = cdf[cdf["evaluatee_email"] == BROOKS]
    assert len(brooks_rows) == 2

    debrief = config.round_label("round_1_4")
    lines = _comment_lines(cdf, BROOKS)
    assert lines == [
        f"_{debrief}_: Clear leader.",
        f"_{debrief}_: Missed two meetings.",
    ]
    # Team View shows the comment and the round, not who wrote it.
    assert all("Avery" not in line and "Carmen" not in line for line in lines)
    assert _comment_lines(cdf, CARMEN) == [f"_{debrief}_: Always prepared."]
    assert _comment_lines(cdf, AVERY) == []
    assert "Different team." not in set(cdf["comments"])
    assert "Different team." in set(evaluation.comments(df, "round_1_4")["comments"])

    summary = evaluation.student_summary(df, "round_1_4")
    brooks = summary[summary["evaluatee_email"] == BROOKS].iloc[0]
    assert brooks["num_reviews"] == 2
    assert brooks["avg_preparation"] == 3.0
    assert brooks["avg_contribution"] == 4.5
    assert int(brooks["fair_share_yes"]) == 1
    assert int(brooks["fair_share_no"]) == 1

    members = _roster()
    members = members[(members["section"] == "001") & (members["team"] == "Team Frog")]
    table = evaluation.team_table(df, members, "round_1_4")
    by_email = table.set_index("email")
    assert int(by_email.loc[AVERY, "num_reviews"]) == 0
    assert bool(by_email.loc[AVERY, "needs_review"]) is False
    assert int(by_email.loc[BROOKS, "num_reviews"]) == 2
    assert bool(by_email.loc[BROOKS, "needs_review"]) is False
    assert bool(by_email.loc[CARMEN, "needs_review"]) is False


def test_needs_review_threshold_is_unchanged():
    df = _evaluations(
        _row(preparation=2, contribution=5, fair_share="No", comments=""),
        _row(
            evaluator_email=CARMEN,
            evaluator_name="Carmen Ortiz",
            preparation=4,
            contribution=5,
            fair_share="No",
            comments="",
        ),
    )
    members = _roster()
    members = members[(members["section"] == "001") & (members["team"] == "Team Frog")]
    table = evaluation.team_table(df, members, "round_1_4")
    brooks = table[table["email"] == BROOKS].iloc[0]
    assert int(brooks["fair_share_no"]) == 2
    assert bool(brooks["needs_review"]) is True


def test_email_match_ignores_case_and_whitespace():
    df = _evaluations(_row(evaluatee_email="  Brooks.Patel@TCU.edu  ", comments="Shown live."))
    cdf = evaluation.comments(df, "round_1_4")
    assert _comment_lines(cdf, BROOKS) == [f"_{config.round_label('round_1_4')}_: Shown live."]


def test_comments_missing_evaluatee_email_do_not_raise_or_misassign():
    """Upstream rows that lack the column keep their text but are not attached."""
    raw = pd.DataFrame(
        [
            {
                "round": "round_1_4",
                "section": "001",
                "team": "Team Frog",
                "evaluator_name": "Avery Nguyen",
                "evaluatee_name": "Brooks Patel",
                "comments": "Orphan comment.",
            }
        ]
    )
    cdf = evaluation.comments(raw, "round_1_4")
    assert "evaluatee_email" in cdf.columns
    assert cdf.iloc[0]["comments"] == "Orphan comment."
    assert pd.isna(cdf.iloc[0]["evaluatee_email"])
    assert _comment_lines(cdf, BROOKS) == []
    assert list(cdf[cdf["evaluatee_email"] == BROOKS].iterrows()) == []


def test_other_round_comments_stay_on_that_round():
    df = _evaluations(
        _row(comments="Debrief note."),
        _row(round="final", comments="Final note."),
    )
    final = _team_comments(df, "001", "Team Frog", "final")
    assert _comment_lines(final, BROOKS) == [f"_{config.round_label('final')}_: Final note."]
    assert evaluation.student_summary(df, "final").iloc[0]["num_reviews"] == 1


def test_missing_survey_still_uses_evaluator_email():
    roster = _roster()
    df = _evaluations(_row())
    missing = evaluation.missing_survey(roster, df, "round_1_4")
    missing_frog = missing[(missing["section"] == "001") & (missing["team"] == "Team Frog")]
    assert set(missing_frog["email"]) == {BROOKS, CARMEN}
