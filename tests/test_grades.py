"""Grades & completion: the total may be hidden; the rate comes from graded work; missing / late counts;
failing to read grades never breaks the page. 成绩与完成情况。"""
from __future__ import annotations

from conftest import FakeCanvas, pt

NOW = pt("2026-10-20 12:00")


def sub(score, points, missing=False, late=False, omit=False):
    return {"score": score, "missing": missing, "late": late,
            "assignment": {"points_possible": points, "omit_from_final_grade": omit}}


def test_grades_card_shows_rate_missing_late_and_hidden_totals(build):
    canvas = FakeCanvas(submissions={
        1001: [sub(9, 10), sub(18, 20, late=True), sub(None, 10, missing=True), sub(5, 5, omit=True)],
        1002: [sub(None, 10)],
    })
    page = build(NOW, canvas)
    card = page.html.split('id="grades"')[1].split("</section>")[0]
    assert "91.5%" in card                                   # TEST 101 shows its total
    assert "90%（27/30，2 项）" in card                        # omitted and ungraded work don't count
    assert "缺交 1" in card and "晚交 1" in card
    assert "老师未公开" in card and "还没有批改的作业" in card   # DEMO 002A
    assert "Orientation" not in card                         # not a real course


def test_grades_failure_is_not_fatal(build):
    page = build(NOW, FakeCanvas(grades_fail=True))
    assert 'id="grades"' not in page.html and 'id="todo"' in page.html


def test_nav_has_home_link(build):
    page = build(NOW, home_url="../")
    assert 'href="../"' in page.html and "首页" in page.html
    assert 'class="nav-link" href="../"' not in build(NOW).html
