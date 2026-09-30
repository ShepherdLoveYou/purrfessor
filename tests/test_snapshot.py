"""Snapshots: what changed since the previous one, and the daily archive. 快照：变化对比与归档。"""
from __future__ import annotations

import json
from datetime import timedelta

from conftest import FakeCanvas, announcement, item, pt

from purrfessor import snapshot as sn

T0 = pt("2026-10-05 06:00")
T1 = pt("2026-10-05 12:00")


def test_diff_detects_every_kind_of_change(build):
    before = FakeCanvas(planner=[item(1, 1001, "Stays", pt("2026-10-09 23:59")),
                                 item(2, 1001, "Will submit", pt("2026-10-08 23:59")),
                                 item(3, 1002, "Will move", pt("2026-10-07 23:59")),
                                 item(4, 1002, "Will vanish", pt("2026-10-20 23:59"))])
    prev = build(T0, before)
    after = FakeCanvas(planner=[item(1, 1001, "Stays", pt("2026-10-09 23:59")),
                                item(2, 1001, "Will submit", pt("2026-10-08 23:59"), submitted=True),
                                item(3, 1002, "Will move", pt("2026-10-14 23:59")),
                                item(5, 1002, "Brand new", pt("2026-10-12 23:59"))],
                       announcements=[announcement(90, 1001, "Fresh news", "hello", T1 - timedelta(hours=1))])
    page = build(T1, after, prev=prev)
    assert 'id="changes"' in page.html
    for text in ["新作业", "Brand new", "已交", "Will submit", "截止改了", "Will move", "被撤下", "Will vanish",
                 "新公告", "Fresh news"]:
        assert text in page.html, text
    assert "Stays" not in page.html.split('id="changes"')[1].split("</section>")[0]


def test_no_prev_or_no_change_shows_no_changes_card(build):
    canvas = FakeCanvas(planner=[item(1, 1001, "Same", pt("2026-10-09 23:59"))])
    assert 'id="changes"' not in build(T0, canvas).html
    prev = build(T0, canvas)
    assert 'id="changes"' not in build(T1, canvas, prev=prev).html


def test_recurring_tasks_and_natural_expiry_are_not_reported(build):
    prev = build(pt("2026-10-02 06:00"), FakeCanvas(planner=[item(1, 1001, "Due today", pt("2026-10-02 23:59"), submitted=True)]))
    page = build(pt("2026-10-09 06:00"), FakeCanvas(), prev=prev)   # a week later: old recurring tasks expire, new ones appear
    body = page.html.split('id="changes"')[1] if 'id="changes"' in page.html else ""
    assert "Online homework" not in body and "Due today" not in body


def test_state_is_embedded_for_the_next_run(build):
    page = build(T0, FakeCanvas(planner=[item(7, 1001, "HW", pt("2026-10-09 23:59"))]))
    assert "canvas-assignment-7" in page.data["state"]["tasks"]
    assert page.data["state"]["classes"]


def test_diff_function_edge_cases():
    cur = {"generated": "2026-10-05T12:00:00-07:00", "tasks": {}, "announcements": {}, "classes": []}
    assert sn.diff(None, cur) == {}
    assert sn.diff({"generated": "x"}, cur) == {"since": "x"} or sn.diff({"generated": "x"}, cur) == {}


def test_archive_add_keeps_last_30_days(tmp_path):
    site = tmp_path / "today"
    (site / "archive").mkdir(parents=True)
    (site / "index.html").write_text("today")
    for d in ["2026-08-01", "2026-09-01", "2026-09-28"]:
        (site / "archive" / f"{d}.html").write_text(d)
    sn.add(site, "2026-10-05", keep=30)
    manifest = json.loads((site / "archive" / "index.json").read_text())
    assert manifest["dates"] == ["2026-10-05", "2026-09-28"]
    assert not (site / "archive" / "2026-08-01.html").exists()
    assert (site / "archive" / "2026-10-05.html").read_text() == "today"


def test_history_links_render(build):
    page = build(T1, archive=["2026-10-04", "2026-10-03"])
    assert "历史快照" in page.html and 'href="archive/2026-10-04.html"' in page.html


def test_ai_extracted_announcement_items_do_not_cause_false_changes():
    base = {"generated": "2026-10-05T12:00:00-07:00", "announcements": {"1": {"title": "x", "course": "TEST 101"}},
            "classes": [], "tasks": {"ann-1-1009": {"title": "Fill in survey", "course": "TEST 101",
                                                    "due": "2026-10-09T23:59:00-07:00", "done": False, "source": "announcement"}}}
    cur = {**base, "generated": "2026-10-05T18:00:00-07:00", "tasks": {}}    # this time the AI didn't extract it
    assert sn.diff(base, cur) == {"since": base["generated"]}


def test_snapshot_cli_add(tmp_path):
    (tmp_path / "index.html").write_text("page")
    sn.cli(["add", "--site-dir", str(tmp_path), "--date", "2026-10-05"])
    assert (tmp_path / "archive" / "2026-10-05.html").read_text() == "page"
