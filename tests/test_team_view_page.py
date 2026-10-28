"""Team View page tests.

The helper-only tests never executed ``page_team_view``. Two failures got
through:

* A repeated ``evaluatee_email`` header makes ``frame[column]`` a DataFrame.
  ``comments_for_evaluatee`` then raised
  ``AttributeError: 'DataFrame' object has no attribute 'str'`` at the call in
  ``page_team_view``.
* ``read_csv`` turned section ``036`` into the integer ``36`` and team ``2``
  into ``2``, so the page's equality filter dropped every written comment.
"""

from __future__ import annotations

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src import config, evaluation, storage

AVERY = "avery.nguyen@tcu.edu"
BROOKS = "brooks.patel@tcu.edu"
CARMEN = "carmen.ortiz@tcu.edu"
EVALUATOR = "Carmen Ortiz"


def _roster_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"email": AVERY, "name": "Avery Nguyen", "section": "036", "team": "1"},
            {"email": BROOKS, "name": "Brooks Patel", "section": "036", "team": "1"},
            {"email": CARMEN, "name": "Carmen Ortiz", "section": "036", "team": "1"},
            {"email": "isla.gardner@tcu.edu", "name": "Isla Gardner", "section": "036", "team": "2"},
            {"email": "jules.kim@tcu.edu", "name": "Jules Kim", "section": "036", "team": "2"},
        ]
    )


def _row(**overrides) -> dict:
    base = {
        "timestamp": "2026-10-01T12:00:00",
        "round": "round_1_4",
        "section": "036",
        "team": "1",
        "evaluator_email": CARMEN,
        "evaluator_name": EVALUATOR,
        "evaluatee_email": BROOKS,
        "evaluatee_name": "Brooks Patel",
        "preparation": "4",
        "contribution": "5",
        "fair_share": "Yes",
        "comments": "Clear leader.",
    }
    base.update(overrides)
    return base


@pytest.fixture
def local_data(tmp_path, monkeypatch):
    """Point storage at a temp roster and keep Google Sheets from being called."""
    import src.gsheets as gsheets

    monkeypatch.setattr(gsheets, "is_configured", lambda: False)
    monkeypatch.setattr(gsheets, "overwrite_df", _refuse_write)
    monkeypatch.setattr(gsheets, "append_row", _refuse_write)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "ROSTER_FILE", tmp_path / "roster.xlsx")
    monkeypatch.setattr(config, "EVALUATIONS_FILE", tmp_path / "evaluations.csv")
    monkeypatch.setattr(config, "ROSTER_META_FILE", tmp_path / "roster_meta.json")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "app_settings.json")
    _roster_frame().to_excel(config.ROSTER_FILE, index=False)
    return tmp_path


def _refuse_write(*_args, **_kwargs):
    raise AssertionError("Team View must not write evaluation records")


def _write_csv(rows: list[dict]) -> None:
    pd.DataFrame(rows, columns=config.EVALUATION_COLUMNS).to_csv(
        config.EVALUATIONS_FILE, index=False
    )


def _open_team_view(team: str | None = None) -> AppTest:
    app = AppTest.from_file("app.py", default_timeout=45)
    app.secrets = {"instructor_password": "test-instructor"}
    app.session_state["is_instructor"] = True
    app.run()
    app.radio[0].set_value("Team View").run()
    if team is not None:
        team_box = next(box for box in app.selectbox if box.label == "Team")
        team_box.set_value(team).run()
    _assert_no_exception(app)
    return app


def _assert_no_exception(app: AppTest) -> None:
    if not app.exception:
        return
    traces = []
    for exc in app.exception:
        message = getattr(exc.proto, "message", "") or ""
        traces.append(message + "\n" + "\n".join(exc.stack_trace))
    pytest.fail("page_team_view raised:\n" + "\n---\n".join(traces))


def _comment_markdown(app: AppTest) -> list[str]:
    lines = []
    for expander in app.expander:
        lines.extend(item.value for item in expander.markdown)
    return lines


def test_duplicate_evaluatee_email_does_not_raise_attribute_error():
    """The expression in page_team_view used to raise AttributeError here."""
    left = pd.DataFrame([_row(evaluatee_email="", comments="Clear leader.")])
    right = pd.DataFrame({"evaluatee_email": [BROOKS]})
    duplicated = pd.concat([left, right], axis=1)
    assert isinstance(duplicated["evaluatee_email"], pd.DataFrame)

    matched = list(evaluation.comments_for_evaluatee(duplicated, BROOKS).iterrows())
    assert [row["comments"] for _, row in matched] == ["Clear leader."]
    assert all(EVALUATOR not in row["comments"] for _, row in matched)


def test_integer_section_still_matches_roster_code():
    frame = pd.DataFrame([_row(section=36, team=2, comments="Shown live.")])
    narrowed = evaluation.comments_for_team(evaluation.comments(frame, None), "036", "2")
    lines = [
        row["comments"]
        for _, row in evaluation.comments_for_evaluatee(narrowed, BROOKS).iterrows()
    ]
    assert lines == ["Shown live."]


def test_load_evaluations_keeps_section_text(local_data):
    _write_csv([_row()])
    loaded = storage.load_evaluations()
    assert loaded.loc[0, "section"] == "036"
    assert loaded.loc[0, "team"] == "1"
    assert list(loaded.columns).count("evaluatee_email") == 1


def test_page_team_view_renders_comments_for_real_sections(local_data):
    _write_csv(
        [
            _row(comments="Clear leader."),
            _row(
                evaluator_email=AVERY,
                evaluator_name="Avery Nguyen",
                evaluatee_email=CARMEN,
                evaluatee_name="Carmen Ortiz",
                preparation="2",
                contribution="3",
                fair_share="No",
                comments="   ",
            ),
        ]
    )
    app = _open_team_view()

    comments = _comment_markdown(app)
    assert comments == [f"- _{config.round_label('round_1_4')}_: Clear leader."]
    assert EVALUATOR not in comments[0]
    assert "Avery Nguyen" not in comments[0]
    assert "No comments." in [caption.value for caption in app.caption]

    metrics = {(metric.label, metric.value) for metric in app.metric}
    assert ("Reviews", "1") in metrics
    assert ("Reviews", "0") in metrics
    assert ("Avg Prep", "4.00") in metrics
    assert ("Avg Prep", "2.00") in metrics
    assert ("Avg Prep", "—") in metrics

    empty = _open_team_view("2")
    assert _comment_markdown(empty) == []
    assert [caption.value for caption in empty.caption].count("No comments.") == 2


def test_page_team_view_duplicate_sheet_header(local_data, monkeypatch):
    """Sheets keeps a repeated header; CSV readers rename it. Team View must not crash."""
    import src.gsheets as gsheets

    header = [
        "timestamp", "round", "section", "team", "evaluator_email", "evaluator_name",
        "evaluatee_email", "evaluatee_email", "evaluatee_name", "preparation",
        "contribution", "fair_share", "comments",
    ]
    responses = pd.DataFrame(
        [[
            "t", "round_1_4", "036", "1",
            CARMEN, EVALUATOR,
            "", BROOKS,
            "Brooks Patel", "4", "5", "Yes", "Clear leader.",
        ]],
        columns=header,
    )
    assert isinstance(responses["evaluatee_email"], pd.DataFrame)
    roster = _roster_frame()

    def read_df(title: str) -> pd.DataFrame:
        if title == config.GS_ROSTER_TAB:
            return roster
        if title == config.GS_RESPONSES_TAB:
            return responses
        return pd.DataFrame()

    monkeypatch.setattr(gsheets, "is_configured", lambda: False)
    monkeypatch.setattr(storage, "_use_sheets", lambda: True)
    monkeypatch.setattr(gsheets, "read_df", read_df)

    app = _open_team_view()
    comments = _comment_markdown(app)
    assert comments == [f"- _{config.round_label('round_1_4')}_: Clear leader."]
    assert EVALUATOR not in " ".join(comments)
    assert ("Avg Prep", "4.00") in {(metric.label, metric.value) for metric in app.metric}
