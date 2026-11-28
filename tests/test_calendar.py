"""The timetable shows Saturday and Sunday when a class meets then or a deadline falls on one in the weeks it opens on
(it hid them whenever no class met, so weekend deadlines were on the to-do list but not on the calendar).
课程表：周末有课，或者这几周内有周末截止的作业时，才显示周六周日。"""
from __future__ import annotations

from conftest import CONFIG, FakeCanvas, item, pt

NOW = pt("2026-10-09 12:00")          # Friday; the calendar opens on the week of Mon 10/5 and the two after it (to 10/23)
HIDE_WEEKEND = [0, 6]                  # FullCalendar numbers Sunday 0 … Saturday 6
SATURDAY_CLASS = CONFIG + """
[[classes]]
course = "TEST 101"
kind = "Workshop"
days = ["Sat"]
start = "10:00"
end = "11:00"
from = "2026-09-28"
until = "2026-12-04"
"""


def hidden(build, *tasks, config=CONFIG, **kw):
    page = build(NOW, FakeCanvas(planner=list(tasks)), config=config, **kw)
    return page.data["calendar"]["hiddenDays"], page


def test_no_weekend_when_nothing_happens_then(build):
    assert hidden(build, item(1, 1001, "Friday", pt("2026-10-09 23:59")))[0] == HIDE_WEEKEND


def test_a_saturday_deadline_shows_the_weekend(build):
    days, page = hidden(build, item(1, 1001, "Module H", pt("2026-10-10 23:59")))
    assert days == []
    assert [e["start"] for e in page.data["calendar"]["events"] if e.get("allDay") and "Module H" in e["title"]] == ["2026-10-10"]


def test_a_sunday_deadline_in_the_next_two_weeks_shows_the_weekend(build):
    assert hidden(build, item(1, 1001, "Practice", pt("2026-10-18 23:59")))[0] == []


def test_a_far_off_weekend_deadline_does_not_keep_seven_columns_for_the_whole_term(build):
    """Saturday 10/24 is after the weeks the calendar opens on."""
    assert hidden(build, item(1, 1001, "Project", pt("2026-10-24 23:59")))[0] == HIDE_WEEKEND


def test_a_weekend_deadline_from_before_this_week_is_not_in_view(build):
    assert hidden(build, item(1, 1001, "Old", pt("2026-10-03 23:59"), missing=True))[0] == HIDE_WEEKEND


def test_a_submitted_weekend_deadline_needs_no_column(build):
    assert hidden(build, item(1, 1001, "Handed in", pt("2026-10-10 23:59"), submitted=True))[0] == HIDE_WEEKEND


def test_a_weekend_class_shows_the_weekend(build):
    days, page = hidden(build, config=SATURDAY_CLASS)
    assert days == []
    assert any(e["start"].startswith("2026-10-10T10:00") for e in page.data["calendar"]["events"])


def test_the_script_hands_the_hidden_days_to_the_calendar(build):
    page = build(NOW)
    assert "hiddenDays: cal.hiddenDays || []" in page.html
