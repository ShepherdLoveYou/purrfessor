"""New grades: the snapshot remembers who was graded and with what score, and the "since last update" card says
"Lab 5 graded: 144/150". An old snapshot without grade info never floods the card. 新出分提示。"""
from __future__ import annotations

import json
import re

from conftest import CONFIG, FakeCanvas, item, parse, pt, submission_row

from purrfessor import snapshot as sn

DUE = pt("2026-11-20 23:59")
T0, T1, T2 = pt("2026-11-24 06:00"), pt("2026-11-25 06:00"), pt("2026-11-26 06:00")


def lab(graded: bool, score=None, pid=5, title="Lab 5", points=150, **kw):
    """(planner item, students/submissions row) of one submitted lab, graded or not yet."""
    return (item(pid, 1001, title, DUE, submitted=True, graded=graded, points=points, **kw),
            submission_row(pid, title, points, due=DUE, state="graded" if graded else "submitted",
                           score=score, graded_at=T1 if graded else None, submitted=DUE))


def canvas_with(*labs, **kw) -> FakeCanvas:
    return FakeCanvas(planner=[p for p, _ in labs], submissions={1001: [s for _, s in labs]}, **kw)


def changes_block(page) -> str:
    return page.section("changes") if 'id="changes"' in page.html else ""


def strip_grade_info(page):
    """The page as the previous version of the code would have built it: no graded / score / points in the state."""
    html = page.html
    m = re.search(r'(<script type="application/json" id="data">)(.*?)(</script>)', html, re.S)
    data = json.loads(m.group(2).replace("<\\/", "</"))
    for task in data["state"]["tasks"].values():
        for key in ("graded", "score", "points"):
            task.pop(key, None)
    body = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return parse(html[:m.start(2)] + body + html[m.end(2):])


def test_newly_graded_work_is_announced_with_its_score(build):
    prev = build(T0, canvas_with(lab(False)))
    page = build(T1, canvas_with(lab(True, score=144)), prev=prev)
    block = changes_block(page)
    assert "出分了" in block and "Lab 5" in block and "<b>144/150</b>" in block
    assert block.count("出分了") == 1
    # the next build has nothing new to say
    assert 'id="changes"' not in build(T2, canvas_with(lab(True, score=144)), prev=page).html


def test_state_keeps_graded_and_score_but_nothing_private(build):
    canvas = canvas_with(lab(True, score=144, feedback=True))
    page = build(T1, canvas)
    entry = page.data["state"]["tasks"]["canvas-assignment-5"]
    assert entry["graded"] is True and entry["score"] == 144 and entry["points"] == 150
    assert "PRIVATE-COMMENT-TEXT" not in page.html and "A TA" not in page.html


def test_first_build_after_the_upgrade_does_not_announce_every_graded_item(build):
    """The previous snapshot has no grade info: nothing is "new". The build after that works normally."""
    labs = [lab(True, score=144), lab(True, score=140, pid=6, title="Lab 6"), lab(False, pid=7, title="Lab 7")]
    old = strip_grade_info(build(T0, canvas_with(*labs)))
    assert "graded" not in old.data["state"]["tasks"]["canvas-assignment-5"]
    first = build(T1, canvas_with(*labs), prev=old)
    assert "graded" not in sn.diff(old.data["state"], first.data["state"])
    assert "出分了" not in first.html
    # and the state it wrote carries grade info, so the next real grade is announced
    later = [lab(True, score=144), lab(True, score=140, pid=6, title="Lab 6"), lab(True, score=90, pid=7, title="Lab 7")]
    second = build(T2, canvas_with(*later), prev=first)
    block = changes_block(second)
    assert block.count("出分了") == 1 and "Lab 7" in block and "90/150" in block and "Lab 6" not in block


def test_old_state_json_still_loads_and_diffs():
    old = {"generated": "2026-11-24T06:00:00-08:00", "announcements": {}, "classes": [],
           "tasks": {"canvas-assignment-5": {"title": "Lab 5", "course": "TEST 101", "due": "2026-11-20T23:59:00-08:00",
                                             "done": True, "source": "Canvas"}}}
    cur = {"generated": "2026-11-25T06:00:00-08:00", "announcements": {}, "classes": [],
           "tasks": {"canvas-assignment-5": {**old["tasks"]["canvas-assignment-5"], "graded": True, "score": 144.0,
                                             "points": 150.0}}}
    assert sn.diff(old, cur) == {"since": old["generated"]}


def test_diff_cases():
    def state(graded, score=None):
        return {"generated": "2026-11-25T06:00:00-08:00", "announcements": {}, "classes": [],
                "tasks": {"t": {"title": "Lab 5", "course": "X", "due": "2026-11-20T23:59:00-08:00", "done": True,
                                "source": "Canvas", "graded": graded, "score": score, "points": 150.0}}}
    assert sn.diff(state(False), state(True, 144.0))["graded"][0]["score"] == 144.0
    assert sn.diff(state(False), state(True, None))["graded"][0]["score"] is None      # graded, no visible score
    regrade = sn.diff(state(True, 140.0), state(True, 144.0))["graded"][0]
    assert regrade["old_score"] == 140.0 and regrade["score"] == 144.0
    assert "graded" not in sn.diff(state(True, 144.0), state(True, 144.0))             # unchanged
    assert "graded" not in sn.diff(state(True, None), state(True, 144.0))              # score only became visible
    assert "graded" not in sn.diff(state(True, 144.0), state(False))                   # un-graded: nothing to cheer
    assert "graded" not in sn.diff(state(False), state(False))


def test_regrade_shows_the_old_score(build):
    prev = build(T0, canvas_with(lab(True, score=140)))
    page = build(T1, canvas_with(lab(True, score=144)), prev=prev)
    block = changes_block(page)
    assert "<b>144/150 （原来 140）</b>" in block


def test_graded_without_a_visible_score_still_says_graded(build):
    prev = build(T0, canvas_with(lab(False)))
    page = build(T1, canvas_with(lab(True, score=None)), prev=prev)
    block = changes_block(page)
    assert "出分了" in block and "Lab 5" in block and "<b>" not in block


def test_excused_and_unposted_grades_do_not_count(build):
    excused = item(8, 1001, "Excused work", DUE, excused=True, graded=True, points=10)        # Canvas: graded? = excused
    unposted = item(9, 1001, "Not posted yet", DUE, submitted=True, graded=True, posted=False, points=10)
    page = build(T1, FakeCanvas(planner=[excused, unposted]))
    tasks = page.data["state"]["tasks"]
    assert tasks["canvas-assignment-8"]["graded"] is False and tasks["canvas-assignment-9"]["graded"] is False
    # the unposted grade appears later: that is the moment it is announced
    posted = item(9, 1001, "Not posted yet", DUE, submitted=True, graded=True, points=10)
    nxt = build(T2, FakeCanvas(planner=[excused, posted], submissions={1001: [
        submission_row(9, "Not posted yet", 10, due=DUE, state="graded", score=8, graded_at=T2)]}), prev=page)
    assert "Not posted yet" in changes_block(nxt) and "<b>8/10</b>" in changes_block(nxt)
    assert "Excused work" not in changes_block(nxt)


def test_quiz_scores_are_matched_through_the_assignment_id(build):
    quiz = item(153927, 1001, "Quiz 1", DUE, kind="quiz", submitted=True, graded=True, points=45, aid=1136126)
    row = submission_row(1136126, "Quiz 1", 45, due=DUE, state="graded", score=41, graded_at=T1)
    prev = build(T0, FakeCanvas(planner=[replace_graded(quiz, False)], submissions={1001: [row]}))
    page = build(T1, FakeCanvas(planner=[quiz], submissions={1001: [row]}), prev=prev)
    assert "<b>41/45</b>" in changes_block(page) and "Quiz 1" in changes_block(page)


def replace_graded(planner_item: dict, graded: bool) -> dict:
    """The same planner item before it was graded."""
    out = json.loads(json.dumps(planner_item))
    out["submissions"].update(graded=graded, posted_at=None)
    return out


def test_scores_are_hidden_when_grades_are_off_but_the_notice_stays(build):
    config = CONFIG + "\n[features]\ngrades = false\n"
    prev = build(T0, canvas_with(lab(False)), config=config)
    page = build(T1, canvas_with(lab(True, score=144)), prev=prev, config=config)
    assert page.data["state"]["tasks"]["canvas-assignment-5"]["score"] is None
    assert "出分了" in changes_block(page) and "144" not in changes_block(page)


def test_no_request_per_item(build):
    canvas = canvas_with(lab(True, score=144), lab(True, score=140, pid=6, title="Lab 6"), lab(False, pid=7, title="Lab 7"))
    build(T1, canvas)
    paths = [p for p, _ in canvas.calls]
    assert sorted(set(paths)) == ["announcements", "courses", "courses/1001/students/submissions",
                                  "courses/1002/students/submissions", "planner/items"]
    assert len(paths) == len(set(paths))                                               # each exactly once


def test_graded_without_a_submission_is_one_notice_not_two(build):
    """Canvas counts graded, not missing work as done, so an in-class quiz flips to "done" at the very moment it is
    graded: "Graded 9/10" says it all, there is no separate "Submitted" row for the same item."""
    quiz = lambda g: item(5, 1001, "In-class quiz", DUE, graded=g, points=10)       # never submitted by the student  # noqa: E731
    row = submission_row(5, "In-class quiz", 10, due=DUE, state="graded", score=9, graded_at=T1)
    prev = build(T0, FakeCanvas(planner=[quiz(False)], submissions={1001: [row]}))
    page = build(T1, FakeCanvas(planner=[quiz(True)], submissions={1001: [row]}), prev=prev)
    block = changes_block(page)
    assert block.count("In-class quiz") == 1 and "出分了" in block and "<b>9/10</b>" in block
    assert "已交" not in block
    assert sn.diff(prev.data["state"], page.data["state"]).keys() == {"since", "graded"}


def test_submitted_work_that_is_not_graded_yet_still_says_submitted(build):
    """The two notices stay separate for different items: one handed in, another graded without a hand-in."""
    DUE2 = pt("2026-11-21 23:59")
    quiz = lambda g: item(5, 1001, "In-class quiz", DUE, graded=g, points=10)  # noqa: E731
    handed = lambda s: item(6, 1001, "Lab 6", DUE2, submitted=s, points=10)    # noqa: E731
    row = submission_row(5, "In-class quiz", 10, due=DUE, state="graded", score=9, graded_at=T1)
    prev = build(T0, FakeCanvas(planner=[quiz(False), handed(False)], submissions={1001: [row]}))
    page = build(T1, FakeCanvas(planner=[quiz(True), handed(True)], submissions={1001: [row]}), prev=prev)
    block = changes_block(page)
    assert block.count("出分了") == 1 and "In-class quiz" in block and block.count("已交") == 1 and "Lab 6" in block


def posting(n: int, points=1, start=10, big=False):
    """n one-point items graded at once (a participation grade posted for the whole term), plus a big one if asked."""
    labs = [lab(True, score=points, pid=start + i, title=f"Participation {i:02d}", points=points) for i in range(n)]
    return labs + ([lab(True, score=88, pid=900, title="Midterm", points=100)] if big else [])


def test_a_posting_batch_does_not_fill_the_card(build):
    """30 one-point items posted at once: the biggest few are listed, the rest fold into one "+N more" row."""
    before = [lab(False, pid=10 + i, title=f"Participation {i:02d}", points=1) for i in range(30)] + [
        lab(False, pid=900, title="Midterm", points=100)]
    prev = build(T0, canvas_with(*before))
    page = build(T1, canvas_with(*posting(30, big=True)), prev=prev)
    block = changes_block(page)
    assert block.count("list-group-item") == 6                                  # 5 graded + 1 "more"
    assert "Midterm" in block and "<b>88/100</b>" in block                      # biggest work first, always shown
    assert "还有 26 项" in block
    assert block.count("Participation") == 4                                   # the rest of the 5 rows


def test_exactly_the_cap_has_no_more_row(build):
    prev = build(T0, canvas_with(*[lab(False, pid=10 + i, title=f"Item {i}") for i in range(6)]))
    five = build(T1, canvas_with(*([lab(True, score=140, pid=10 + i, title=f"Item {i}") for i in range(5)]
                                   + [lab(False, pid=15, title="Item 5")])), prev=prev)
    assert changes_block(five).count("出分了") == 5 and "还有" not in changes_block(five)
    six = build(T1, canvas_with(*[lab(True, score=140, pid=10 + i, title=f"Item {i}") for i in range(6)]), prev=prev)
    assert changes_block(six).count("出分了") == 6 and "还有 1 项" in changes_block(six)


def test_the_snapshot_keeps_every_grade_even_when_the_card_folds_them(build):
    prev = build(T0, canvas_with(*[lab(False, pid=10 + i, title=f"Item {i}", points=1) for i in range(12)]))
    page = build(T1, canvas_with(*posting(12, start=10)), prev=prev)
    assert len(sn.diff(prev.data["state"], page.data["state"])["graded"]) == 12
    assert changes_block(page).count("list-group-item") == 6


def test_english_card_has_no_chinese(build):
    prev = build(T0, canvas_with(lab(False)), lang="en")
    page = build(T1, canvas_with(lab(True, score=144)), prev=prev, lang="en")
    block = changes_block(page)
    assert "Graded" in block and "<b>144/150</b>" in block and not re.search(r"[一-鿿]", block)
    regrade = build(T2, canvas_with(lab(True, score=148)), prev=page, lang="en")
    assert "(was 144)" in changes_block(regrade) and not re.search(r"[一-鿿]", changes_block(regrade))
    prev = build(T0, canvas_with(*[lab(False, pid=10 + i, title=f"Item {i}", points=1) for i in range(8)]), lang="en")
    batch = build(T1, canvas_with(*posting(8)), prev=prev, lang="en")
    assert "+3 more" in changes_block(batch) and not re.search(r"[一-鿿]", changes_block(batch))
