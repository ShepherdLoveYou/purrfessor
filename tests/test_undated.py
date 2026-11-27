"""Work with points but no due date (the planner lists only dated items): a collapsed list inside the to-do card.
It is never a deadline: not in the lists, counters, calendar or snapshot. 没有截止日期的大作业。"""
from __future__ import annotations

import re
from datetime import timedelta

from conftest import CONFIG, FakeCanvas, item, pt, submission_row

NOW = pt("2026-11-27 18:00")


def undated_html(page) -> str:
    return page.html.split('id="undated"')[1].split("</details>")[0] if 'id="undated"' in page.html else ""


def titles(block: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r'class="fw-medium title"><a[^>]*>(.*?)</a>', block)]


def test_card_lists_big_undated_work_biggest_first(build):
    canvas = FakeCanvas(submissions={
        1001: [submission_row(1, "Project 2", 200, cid=1001), submission_row(2, "Small reflection", 5),
               submission_row(3, "Lab 9", 80, due=pt("2026-12-01 23:59"))],        # dated: the planner's business
        1002: [submission_row(4, "Final Exam", 50, cid=1002), submission_row(5, "Final Presentation", 25, cid=1002)]})
    page = build(NOW, canvas)
    block = undated_html(page)
    assert titles(block) == ["Project 2", "Final Exam", "Final Presentation"]       # points, biggest first
    assert "200 分" in block and "没有截止日期" in block
    assert 'href="https://canvas.test/courses/1001/assignments/1"' in block         # link to the assignment
    assert "TEST 101" in block and "DEMO 002A" in block                            # course badges
    assert "还没设截止日期 · 3 项" in block
    # inside the to-do card, collapsed, after "more later"
    todo = page.section("todo")
    assert 'id="undated"' in todo and "<details" in todo and "open" not in block.split(">")[0]


def test_threshold_default_25_and_configurable(build):
    rows = {1001: [submission_row(1, "Just under", 24.5), submission_row(2, "Exactly", 25), submission_row(3, "Medium", 40)]}
    assert titles(undated_html(build(NOW, FakeCanvas(submissions=rows)))) == ["Medium", "Exactly"]
    config = CONFIG + "\n[features]\nundated_min_points = 40\n"
    page = build(NOW, FakeCanvas(submissions=rows), config=config)
    assert titles(undated_html(page)) == ["Medium"] and "40+ points" not in page.html and "40 分以上" in page.html
    assert 'id="undated"' not in build(NOW, FakeCanvas(submissions=rows), config=CONFIG + "\n[features]\nundated_min_points = 999\n").html


def test_excluded_states(build):
    rows = [
        submission_row(1, "Shown", 60),
        submission_row(2, "Has a due date", 60, due=pt("2026-12-03 23:59")),
        submission_row(3, "Due date only on the submission (override)", 60),     # replaced below
        submission_row(4, "Graded", 60, state="graded", score=50, graded_at=NOW),
        submission_row(5, "Graded without score yet", 60, graded_at=NOW),
        submission_row(6, "Handed in", 60, state="submitted", submitted=NOW),
        submission_row(7, "Handed in (state only)", 60, state="pending_review"),
        submission_row(8, "Excused", 60, excused=True),
        submission_row(9, "Unpublished", 60, published=False),
        submission_row(10, "Unpublished (state)", 60, workflow_state="unpublished"),
        submission_row(11, "Not in the grade", 60, omit_from_final_grade=True),
        submission_row(12, "Hidden in gradebook", 60, hide_in_gradebook=True),
        submission_row(13, "Not graded", 60, submission_types=["not_graded"]),
        submission_row(14, "Locked for good", 60, lock=NOW - timedelta(days=2)),
        submission_row(15, "Still open", 60, lock=NOW + timedelta(days=5)),
        submission_row(16, "No points", None), submission_row(17, "Zero points", 0),
    ]
    rows[2]["cached_due_date"] = "2026-12-02T07:59:59Z"
    page = build(NOW, FakeCanvas(submissions={1001: rows}))
    assert sorted(titles(undated_html(page))) == ["Shown", "Still open"]


def test_work_already_on_the_page_is_not_listed_twice(build):
    """An item the planner already shows (same assignment id) never appears in both places."""
    canvas = FakeCanvas(planner=[item(77, 1001, "Essay", pt("2026-12-01 23:59"), points=100)],
                        submissions={1001: [submission_row(77, "Essay", 100), submission_row(78, "Other", 90)]})
    page = build(NOW, canvas)
    assert titles(undated_html(page)) == ["Other"] and page.state("canvas-assignment-77") == "soon"


def test_never_a_deadline_counter_calendar_or_snapshot_entry(build):
    canvas = FakeCanvas(planner=[item(1, 1001, "Dated", pt("2026-11-30 23:59"))],
                        submissions={1001: [submission_row(5, "Big project", 200,
                                                           description="Submit your project by Dec 4 at 5pm.")]})
    with_undated = build(NOW, canvas)
    without = build(NOW, canvas, config=CONFIG + "\n[features]\nundated = false\n")
    assert 'id="undated"' in with_undated.html and 'id="undated"' not in without.html
    assert with_undated.stats == without.stats and with_undated.states == without.states
    assert with_undated.data["tasks"] == without.data["tasks"]                       # the "next deadline" list
    assert with_undated.data["calendar"] == without.data["calendar"]
    assert with_undated.data["state"]["tasks"].keys() == without.data["state"]["tasks"].keys()
    assert not any("undated" in k or "Big project" in v["title"] for k, v in with_undated.data["state"]["tasks"].items())
    # and it is not "new" the next day: nothing to report
    nxt = build(NOW + timedelta(hours=6), canvas, prev=with_undated)
    assert 'id="changes"' not in nxt.html


def test_date_in_the_description_is_only_a_hint(build):
    desc = ("<p>Welcome to the project.</p><p>Submit your project by Friday Dec 4th at 11:59 PM for the bonus.</p>"
            "<p>The final due date is Dec 5 at 9am.</p><p>Last term's was due Oct 2.</p>")
    page = build(NOW, FakeCanvas(submissions={1001: [submission_row(5, "Project", 200, description=desc),
                                                      submission_row(6, "Nothing in text", 100, description="<p>Have fun</p>")]}))
    block = undated_html(page)
    assert "作业说明里提到" in block and "请点开核对" in block
    assert "不一定是截止时间" in block                                                  # said once, in the help text
    assert "12/4 周五 23:59" in block and "12/5 周六 09:00" in block                 # two hints at most, earliest first
    assert "Oct 2" not in block                                                      # past mentions are ignored
    assert block.count("calendar-question") == 2                                    # none for the second item
    assert page.state("canvas-undated-5") is None and not any("undated" in k for k in page.states)


def test_long_quotes_are_shortened(build):
    desc = "<p>Submit by Dec 4 at 5pm " + "and then a very long sentence follows " * 10 + "</p>"
    block = undated_html(build(NOW, FakeCanvas(submissions={1001: [submission_row(5, "Project", 200, description=desc)]})))
    assert "…”" in block and "and then a very long sentence follows " * 6 not in block


def test_hint_text_is_escaped(build):
    desc = "<p>Submit &lt;b&gt;by Dec 4 at 5pm&lt;/b&gt; &amp; \"quoted\" <script>x</script></p>"
    block = undated_html(build(NOW, FakeCanvas(submissions={1001: [submission_row(5, "Project", 200, description=desc)]})))
    assert "<b>" not in block and "<script>" not in block and "&lt;b&gt;" in block


def test_cap_and_per_course_limit(build):
    """Eight rows at most and three per course, then "+N more": a course full of placeholders cannot push another
    course's only big item out."""
    many = [submission_row(100 + i, f"Placeholder {i:02d}", 40, cid=1001) for i in range(31)]
    other = [submission_row(500, "Only big item", 25, cid=1002)]
    block = undated_html(build(NOW, FakeCanvas(submissions={1001: many, 1002: other})))
    assert titles(block) == ["Placeholder 00", "Placeholder 01", "Placeholder 02", "Only big item"]
    assert "还有 28 项没列出" in block and "还没设截止日期 · 32 项" in block
    # the overall cap, with many courses' worth of items
    courses = {1001: [submission_row(i, f"A{i}", 90 - i, cid=1001) for i in range(3)],
               1002: [submission_row(10 + i, f"B{i}", 80 - i, cid=1002) for i in range(3)]}
    assert len(titles(undated_html(build(NOW, FakeCanvas(submissions=courses))))) == 6   # 3 + 3, under the cap of 8


def test_requests_are_shared_and_features_independent(build):
    rows = {1001: [submission_row(1, "Project", 100)]}
    canvas = FakeCanvas(submissions=rows)
    page = build(NOW, canvas)
    fetches = [p for p, _ in canvas.calls if p.endswith("/students/submissions")]
    assert sorted(fetches) == ["courses/1001/students/submissions", "courses/1002/students/submissions"]  # once each
    assert 'id="grades"' in page.html and 'id="undated"' in page.html
    # grades off: still listed, still one request per course, no grades card
    canvas = FakeCanvas(submissions=rows)
    page = build(NOW, canvas, config=CONFIG + "\n[features]\ngrades = false\n")
    assert 'id="grades"' not in page.html and 'id="undated"' in page.html
    assert len([p for p, _ in canvas.calls if p.endswith("/students/submissions")]) == 2
    # undated off: grades only
    page = build(NOW, FakeCanvas(submissions=rows), config=CONFIG + "\n[features]\nundated = false\n")
    assert 'id="grades"' in page.html and 'id="undated"' not in page.html
    # both off: nothing fetched
    canvas = FakeCanvas(submissions=rows)
    build(NOW, canvas, config=CONFIG + "\n[features]\ngrades = false\nundated = false\n")
    assert not [p for p, _ in canvas.calls if p.endswith("/students/submissions")]


def test_degrades_silently(build):
    """No submissions, a failing request or missing fields: no card and the page still builds."""
    assert 'id="undated"' not in build(NOW, FakeCanvas()).html
    failing = build(NOW, FakeCanvas(grades_fail=True, planner=[item(1, 1001, "Dated", pt("2026-11-30 23:59"))]))
    assert 'id="undated"' not in failing.html and failing.state("canvas-assignment-1") == "soon"
    bare = {"assignment_id": 9, "assignment": {"points_possible": 80}}               # a school that sends little
    page = build(NOW, FakeCanvas(submissions={1001: [bare, {"assignment": None}, {}]}))
    assert titles(undated_html(page)) == ["(untitled)"]


def test_english_page_has_no_chinese(build):
    desc = "<p>Submit by Dec 4 at 5pm.</p>"
    page = build(NOW, FakeCanvas(submissions={1001: [submission_row(5, "Project", 200, description=desc)]}), lang="en")
    block = undated_html(page)
    assert "No due date yet · 1" in block and "200 pts" in block and "No due date" in block
    assert "The description mentions Fri 12/4 17:00" in block and "please check" in block
    assert "25+ points" in block
    assert not re.search(r"[一-鿿]", block)
