"""The late window: work that Canvas still takes after its due time (lock_at). The row says until when, and an
overdue task that is still open is not shown as dead. Time stays in the school's time zone. 补交窗口。"""
from __future__ import annotations

import re
from datetime import timedelta

from conftest import FakeCanvas, item, pt, submission_row

DUE = pt("2026-11-20 23:59")                # Friday
LOCK = pt("2026-11-22 23:59")               # Sunday: 48 h later


def row(page, tid: str) -> str:
    return re.search(rf'<div class="list-group-item task[^"]*"[^>]*data-id="{re.escape(tid)}".*?</div></div></div>',
                     page.html, re.S).group(0)


def test_note_before_the_due_time(build):
    page = build(DUE - timedelta(days=2), FakeCanvas(planner=[item(1, 1001, "Lab 5", DUE, lock=LOCK)]))
    block = row(page, "canvas-assignment-1")
    assert 'class="text-secondary small mt-1 lock-note"' in block
    assert "过了截止时间还能交，到 11/22 周日 23:59 关闭（晚交可能扣分）" in block
    assert f'data-lock="{LOCK.isoformat()}"' in block
    assert 'class="badge bg-blue-lt cd"' in block or "bg-orange-lt cd" in block     # the normal countdown to the due time
    assert "还能交 ·" not in block                                                 # not "open" yet: it is not even due


def test_overdue_but_still_open_is_not_shown_as_dead(build):
    now = DUE + timedelta(hours=20)
    page = build(now, FakeCanvas(planner=[item(1, 1001, "Lab 5", DUE, lock=LOCK)]))
    block = row(page, "canvas-assignment-1")
    assert page.state("canvas-assignment-1") == "overdue"                          # still late: counters unchanged
    assert page.stats["逾期未交"] == 1
    assert 'class="badge bg-orange-lt cd">还能交 · 1天4小时</span>' in block
    assert "已截止" not in block and "11/22 周日 23:59" in block


def test_locked_for_good_is_plain_overdue(build):
    page = build(LOCK + timedelta(hours=1), FakeCanvas(planner=[item(1, 1001, "Lab 5", DUE, lock=LOCK)]))
    block = row(page, "canvas-assignment-1")
    assert "lock-note" not in block and "data-lock" not in block and "还能交" not in block
    assert "已截止" in block and "bg-red-lt cd" in block


def test_no_note_when_the_lock_is_the_due_time(build):
    """Quizzes close when they are due; a lock within the hour is the same deadline, not a window."""
    now = DUE - timedelta(days=1)
    planner = [item(1, 1001, "Quiz", DUE, kind="quiz", lock=DUE),
               item(2, 1001, "Almost the same", DUE, lock=DUE + timedelta(minutes=59)),
               item(3, 1001, "Exactly an hour", DUE, lock=DUE + timedelta(hours=1)),
               item(4, 1001, "A bit more", DUE, lock=DUE + timedelta(hours=1, minutes=1)),
               item(5, 1001, "Locks before it is due", DUE, lock=DUE - timedelta(days=1))]
    page = build(now, FakeCanvas(planner=planner))
    for tid, expected in [(1, False), (2, False), (3, False), (4, True), (5, False)]:
        assert ("lock-note" in row(page, f"canvas-quiz-{tid}" if tid == 1 else f"canvas-assignment-{tid}")) == expected, tid


def test_done_work_has_no_note(build):
    page = build(DUE - timedelta(days=1), FakeCanvas(planner=[item(1, 1001, "Lab 5", DUE, lock=LOCK, submitted=True)]))
    block = row(page, "canvas-assignment-1")
    assert "lock-note" not in block and "data-lock" not in block and "已交" in block


def test_school_time_zone_not_utc(build):
    """lock_at arrives in UTC: 2026-11-22T07:59:59Z is Saturday 23:59 in Riverside, not Sunday morning."""
    page = build(DUE, FakeCanvas(planner=[item(1, 1001, "Lab 5", DUE, lock=pt("2026-11-21 23:59"))]))
    block = row(page, "canvas-assignment-1")
    assert "11/21 周六 23:59" in block and "07:59" not in block
    assert 'data-lock="2026-11-21T23:59:00-08:00"' in block


def test_lock_falls_back_to_the_assignment_when_the_planner_has_none(build):
    """Work with an override due date has no lock_at in the planner; the assignment in students/submissions does."""
    planner = [item(1, 1001, "Lab 5", DUE)]
    canvas = FakeCanvas(planner=planner, submissions={1001: [submission_row(1, "Lab 5", 150, due=DUE, lock=LOCK)]})
    assert "11/22 周日 23:59" in row(build(DUE - timedelta(days=1), canvas), "canvas-assignment-1")
    # the planner's own value wins when both exist
    other = pt("2026-11-23 12:00")
    canvas = FakeCanvas(planner=[item(1, 1001, "Lab 5", DUE, lock=other)],
                        submissions={1001: [submission_row(1, "Lab 5", 150, due=DUE, lock=LOCK)]})
    block = row(build(DUE - timedelta(days=1), canvas), "canvas-assignment-1")
    assert "11/23 周一 12:00" in block and "11/22" not in block


def test_quiz_lock_falls_back_through_the_assignment_id(build):
    quiz = item(153927, 1001, "Quiz 1", DUE, kind="quiz", aid=1136126)
    canvas = FakeCanvas(planner=[quiz], submissions={1001: [submission_row(1136126, "Quiz 1", 45, due=DUE, lock=LOCK)]})
    assert "lock-note" in row(build(DUE - timedelta(days=1), canvas), "canvas-quiz-153927")


def test_degrades_silently_when_data_is_missing(build):
    """No lock anywhere, no submissions data, a record without its assignment, an unparsable value: just no note."""
    odd = submission_row(3, "Odd", 10, due=DUE)
    odd["assignment"]["lock_at"] = None
    canvas = FakeCanvas(planner=[item(1, 1001, "No lock", DUE), item(2, 1001, "No data", DUE), item(3, 1001, "Null", DUE)],
                        submissions={1001: [{"assignment_id": 1}, odd, {"assignment": None}]})
    page = build(DUE - timedelta(days=1), canvas)
    assert 'mt-1 lock-note"' not in page.html and 'data-lock="' not in page.html       # (the script mentions both)
    assert len(page.states) >= 3 and page.state("canvas-assignment-1") == "soon"


def test_english_has_no_chinese(build):
    now = DUE + timedelta(hours=20)
    page = build(now, FakeCanvas(planner=[item(1, 1001, "Lab 5", DUE, lock=LOCK)]), lang="en")
    block = row(page, "canvas-assignment-1")
    assert "Can still be submitted until Sun 11/22 23:59 (late work may lose points)" in block
    assert "Still open · 1d 4h" in block and not re.search(r"[一-鿿]", block)
    assert page.data["i18n"]["lateOpen"] == "Still open · {t}"


def test_the_page_script_keeps_the_badge_and_note_live(build):
    page = build(DUE, FakeCanvas(planner=[item(1, 1001, "Lab 5", DUE, lock=LOCK)]))
    assert "dataset.lock" in page.html and "L.lateOpen" in page.html and page.data["i18n"]["lateOpen"] == "还能交 · {t}"
