"""Grades & completion: the total may be hidden; the rate comes from graded work; missing / late counts;
failing to read grades never breaks the page. 成绩与完成情况。"""
from __future__ import annotations

import re

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
    assert "90.0%" in card and "27/30 · 2 项" in card         # omitted and ungraded work don't count
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


def grades(build, subs, lang="zh"):
    page = build(NOW, FakeCanvas(submissions={1001: subs}), lang=lang)
    return page.html.split('id="grades"')[1].split("</section>")[0]


def test_rates_have_one_decimal_and_are_never_rounded_up_to_100(build):
    """1459.25 of 1460 points is 99.9%, not "100%" (and the total beside it already had a decimal)."""
    card = grades(build, [sub(1459.25, 1460)])
    assert '<span class="h3 mb-0">99.9%</span>' in card and "1459.25/1460 · 1 项" in card and ">100%<" not in card
    almost = grades(build, [sub(1459.99, 1460)])                  # 99.9993%: rounds to 100.0 but is not full marks
    assert '<span class="h3 mb-0">99.9%</span>' in almost
    assert '<span class="h3 mb-0">100.0%</span>' in grades(build, [sub(10, 10), sub(5, 5)])


def test_each_course_with_graded_work_has_a_labelled_progress_bar(build):
    card = grades(build, [sub(9, 10), sub(18, 20)])
    bar = re.search(r'<div class="progress progress-sm" ([^>]*)><div class="progress-bar" style="width:([\d.]+)%"></div></div>', card)
    assert bar and bar.group(2) == "90.0"
    assert 'role="progressbar"' in bar.group(1) and 'aria-valuenow="90.0" aria-valuemin="0" aria-valuemax="100"' in bar.group(1)
    assert 'aria-label="已批改作业得分率 90.0%（27/30 分，2 项）"' in bar.group(1)
    assert card.count("progressbar") == 1                          # DEMO 002A has nothing graded: no bar, just the note
    assert "还没有批改的作业" in card


def test_english_grades_card_has_no_chinese(build):
    card = grades(build, [sub(9, 10, late=True), sub(None, 10, missing=True)], lang="en")
    assert "90.0%" in card and "9/10 · 1 graded" in card and "Missing 1" in card and "Late 1" in card
    assert 'aria-label="Graded work: 90.0% (9/10 points, 1 graded)"' in card
    assert not re.search(r"[一-鿿]", card)


def test_a_phone_row_is_two_columns_under_the_course_and_its_flags(build):
    """Course + flags share the first line, the grade and the rate the second (170 px per course before); from the
    small breakpoint on it is one line again, with the flags at the far end."""
    card = grades(build, [sub(9, 10)])
    assert re.findall(r'<div class="(col-[^"]*)">', card.split('<div class="list-group-item grade-row">')[1])[:2] == [
        "col-6 col-sm-3", "col-6 col-sm-2 text-end order-sm-1"]
    assert '<div class="col-12 order-sm-2"><div class="progress progress-sm"' in card          # the bar stays under both
    assert card.count("col-6 col-sm-3 d-flex") == 2 and card.count("col-6 col-sm-4 d-flex") == 2      # two courses
