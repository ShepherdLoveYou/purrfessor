"""A small "has feedback" badge on the task row, linking to the task. Only the fact is used: the comment text is
private and never reaches the page or the snapshot. 有评语标记。"""
from __future__ import annotations

import json
import re
from datetime import timedelta

from conftest import FakeCanvas, item, pt

DUE = pt("2026-11-20 23:59")


def row(page, tid: str) -> str:
    """The HTML of one task row."""
    return re.search(rf'<div class="list-group-item task[^"]*"[^>]*data-id="{re.escape(tid)}".*?</div></div></div>',
                     page.html, re.S).group(0)


def test_badge_links_to_the_task_and_shows_no_text(build):
    canvas = FakeCanvas(planner=[item(5, 1001, "Lab 5", DUE, submitted=True, graded=True, feedback=True),
                                 item(6, 1001, "Lab 6", DUE, submitted=True, graded=True)])
    page = build(DUE + timedelta(days=2), canvas)
    with_fb, without = row(page, "canvas-assignment-5"), row(page, "canvas-assignment-6")
    url = re.search(r'class="text-reset" href="([^"]+)"', with_fb).group(1)
    assert f'<a class="badge bg-blue-lt" href="{url}" target="_blank" rel="noopener">' in with_fb
    assert "有评语" in with_fb and "有评语" not in without
    assert "PRIVATE-COMMENT-TEXT" not in page.html and "A TA" not in page.html
    assert "PRIVATE-COMMENT-TEXT" not in json.dumps(page.data)               # not in the snapshot either


def test_badge_also_on_unfinished_and_overdue_rows(build):
    canvas = FakeCanvas(planner=[item(7, 1001, "Draft", DUE + timedelta(days=3), feedback=True),
                                 item(8, 1001, "Missed", DUE, missing=True, feedback=True)])
    page = build(DUE + timedelta(days=1), canvas)
    assert "有评语" in row(page, "canvas-assignment-7") and "有评语" in row(page, "canvas-assignment-8")


def test_absent_field_means_no_badge(build):
    """Other schools / New Quizzes may not send has_feedback at all."""
    plain = item(9, 1001, "No field", DUE + timedelta(days=3))
    del plain["submissions"]["has_feedback"]
    assert "有评语" not in build(DUE, FakeCanvas(planner=[plain])).html
    assert "有评语" not in build(DUE, FakeCanvas(planner=[item(10, 1001, "Not submittable", DUE + timedelta(days=3),
                                                              submittable=False)])).html


def test_work_with_feedback_stays_on_the_list_longer(build):
    """Feedback usually comes days after the due time, so those rows outlive the usual 3 days (up to 14)."""
    canvas = FakeCanvas(planner=[item(11, 1001, "Graded lab", DUE, submitted=True, graded=True, feedback=True),
                                 item(12, 1001, "Graded quiz", DUE, submitted=True, graded=True)])
    week = build(DUE + timedelta(days=7), canvas)
    assert week.state("canvas-assignment-11") == "done" and week.state("canvas-assignment-12") is None
    assert build(DUE + timedelta(days=13), canvas).state("canvas-assignment-11") == "done"
    assert build(DUE + timedelta(days=15), canvas).state("canvas-assignment-11") is None
    assert week.stats["逾期未交"] == 0                                           # still finished work, never overdue


def test_english_badge_has_no_chinese(build):
    page = build(DUE + timedelta(days=1), FakeCanvas(planner=[item(5, 1001, "Lab 5", DUE, submitted=True, graded=True,
                                                                  feedback=True)]), lang="en")
    block = row(page, "canvas-assignment-5")
    assert "Feedback" in block and not re.search(r"[一-鿿]", block)
