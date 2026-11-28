"""A school that is not UCR: no [banner] section_pattern, course codes like "BIO101-FA26". The Canvas-data features
(grades, scores in grade notices, lock times, work without a due date) must not depend on UCR's course-code format.
不是 UCR 的学校：没有 section_pattern，课号长得完全不同；基于提交记录的功能不能依赖 UCR 的课号格式。"""
from __future__ import annotations

from datetime import timedelta

from conftest import GENERIC_CONFIG, GENERIC_COURSES, FakeCanvas, item, pt, submission_row

NOW = pt("2026-11-27 18:00")
DUE = pt("2026-11-29 23:59")
LOCK = DUE + timedelta(days=3)


def fetched_paths(canvas: FakeCanvas) -> list[str]:
    return [p for p, _ in canvas.calls if p.endswith("/students/submissions")]


def generic_canvas(**kw) -> FakeCanvas:
    rows = [submission_row(1, "Lab report", 100, cid=2001),
            submission_row(2, "Graded lab", 20, cid=2001, due=pt("2026-11-20 23:59"), state="graded", score=18, graded_at=NOW),
            submission_row(3, "Lab 3", 50, cid=2001, due=DUE, lock=LOCK)]
    return FakeCanvas(courses=GENERIC_COURSES, submissions={2001: rows, 2002: [submission_row(9, "Not mine", 90, cid=2002)]},
                      planner=[item(3, 2001, "Lab 3", DUE, points=50, lock=LOCK),
                               item(2, 2001, "Graded lab", pt("2026-11-26 23:59"), submitted=True, graded=True, points=20)],
                      **kw)


def test_features_work_without_a_section_pattern(build):
    canvas = generic_canvas()
    page = build(NOW, canvas, config=GENERIC_CONFIG)
    assert fetched_paths(canvas) == ["courses/2001/students/submissions"]           # only the course I am a student in
    assert 'id="undated"' in page.html and "Lab report" in page.section("todo")      # work without a due date
    assert 'id="grades"' in page.html and "BIO 101" in page.section("grades")    # the grades card
    assert "data-lock=" in page.section("todo")                                      # lock time (from the planner)


def test_scores_and_lock_fallback_come_from_the_shared_submissions(build):
    """A grade notice with the score, and a lock time the planner did not carry, both read the fetched submissions."""
    graded = lambda g: item(2, 2001, "Graded lab", pt("2026-11-20 23:59"), submitted=True, graded=g, points=20)  # noqa: E731
    row = submission_row(2, "Graded lab", 20, cid=2001, due=pt("2026-11-20 23:59"), state="graded", score=18, graded_at=NOW)
    lock_row = submission_row(3, "Lab 3", 50, cid=2001, due=DUE, lock=LOCK)
    prev = build(NOW - timedelta(days=1), FakeCanvas(courses=GENERIC_COURSES, planner=[graded(False)],
                                                     submissions={2001: [row]}), config=GENERIC_CONFIG)
    page = build(NOW, FakeCanvas(courses=GENERIC_COURSES, planner=[graded(True), item(3, 2001, "Lab 3", DUE, points=50)],
                                 submissions={2001: [row, lock_row]}), prev=prev, config=GENERIC_CONFIG)
    assert "<b>18/20</b>" in page.section("changes")
    assert f'data-lock="{LOCK.isoformat()}"' in page.section("todo")                 # planner had none: the assignment's


def test_course_without_a_student_enrollment_is_not_fetched(build):
    """The only filter without a pattern: I must be a student in the course (not a teacher or an admin of a site)."""
    canvas = generic_canvas()
    build(NOW, canvas, config=GENERIC_CONFIG)
    assert "courses/2002/students/submissions" not in fetched_paths(canvas)


def test_a_configured_pattern_still_filters_by_course_code(build):
    """UCR (and any preset that sets section_pattern) keeps its behaviour: only codes that match are fetched."""
    config = GENERIC_CONFIG + '\n[banner]\nsection_pattern = \'^BIO\\d+\'\n'
    canvas = FakeCanvas(courses=GENERIC_COURSES + [{"id": 2003, "course_code": "Orientation 2026",
                                                    "enrollments": [{"type": "student"}], "sections": []}],
                        submissions={2001: [submission_row(1, "Lab report", 100, cid=2001)]})
    build(NOW, canvas, config=config)
    assert fetched_paths(canvas) == ["courses/2001/students/submissions"]
    # the UCR preset: its own pattern, not the generic rule
    plain = FakeCanvas()
    build(NOW, plain)
    assert fetched_paths(plain) == ["courses/1001/students/submissions", "courses/1002/students/submissions"]
