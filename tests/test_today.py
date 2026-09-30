"""End-to-end tests with fake data and time travel: the task state machine and page invariants (Chinese UI).
端到端测试：假数据 + 时间快进，检查作业状态机和页面不变量（中文界面）。"""
from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime, timedelta

import pytest
from conftest import FakeCanvas, announcement, item, pt


def check_invariants(page, now):
    """Rules that must hold for every generated page."""
    d = page.data
    # 1. the "next deadline" list is sorted by time
    dues = [t["due"] for t in d["tasks"]]
    assert dues == sorted(dues)
    # 2. the stat cards agree with the lists
    overdue = [k for k, v in page.states.items() if v == "overdue"]
    assert page.stats["逾期未交"] == len(overdue)
    assert page.stats["今天的课"] == len(page.today_classes)
    # 3. overdue really is past due; "soon"/"later" is not (off-Canvas tasks may be up to 12 h past due)
    for tid, state in page.states.items():
        due = datetime.fromisoformat(re.search(rf'data-due="([^"]+)" data-id="{re.escape(tid)}"', page.html).group(1))
        if state == "overdue":
            assert due < now, tid
        if state in ("soon", "later"):
            assert due >= now - timedelta(hours=12), tid
    # 4. submitted work is never the "next deadline"
    done_ids = {k for k, v in page.states.items() if v == "done"}
    assert not done_ids & {t["id"] for t in d["tasks"]}


# ---------------------------------------------------------------- the task state machine

def test_assignment_lifecycle_late_submission(build):
    """Not submitted in time → overdue → submitted late → done → gone 3 days later. States only move forward."""
    due = pt("2026-10-16 23:59")
    submit_at = due + timedelta(days=1)
    seen = []
    now = due - timedelta(days=16)
    while now <= due + timedelta(days=5):
        canvas = FakeCanvas(planner=[item(1, 1001, "Essay 1", due, submitted=now >= submit_at,
                                          missing=due < now < submit_at)])
        page = build(now, canvas)
        check_invariants(page, now)
        state = page.state("canvas-assignment-1")
        if not seen or seen[-1] != state:
            seen.append(state)
        now += timedelta(hours=6)
    assert seen == ["later", "soon", "overdue", "done", None], seen


def test_submitted_early_never_overdue(build):
    due = pt("2026-10-09 23:59")
    for now in [due - timedelta(days=3), due + timedelta(hours=1), due + timedelta(days=2)]:
        page = build(now, FakeCanvas(planner=[item(2, 1001, "Quiz", due, submitted=True)]))
        assert page.state("canvas-assignment-2") == "done"
    assert build(due + timedelta(days=4), FakeCanvas(planner=[item(2, 1001, "Quiz", due, submitted=True)])) \
        .state("canvas-assignment-2") is None


@pytest.mark.parametrize("flags", [{"excused": True}, {"marked": True}])
def test_excused_or_marked_complete_counts_as_done(build, flags):
    due = pt("2026-10-09 23:59")
    page = build(due + timedelta(hours=2), FakeCanvas(planner=[item(3, 1001, "Reading", due, **flags)]))
    assert page.state("canvas-assignment-3") == "done"
    assert page.stats["逾期未交"] == 0


def test_long_overdue_is_not_silently_dropped(build):
    """Work due 3 weeks ago and never submitted stays in "overdue"."""
    due = pt("2026-10-02 23:59")
    page = build(due + timedelta(days=21), FakeCanvas(planner=[item(4, 1001, "Lab 1", due, missing=True)]))
    assert page.state("canvas-assignment-4") == "overdue"


def test_non_submittable_item_never_overdue(build):
    """Items without a submission (paper worksheets, reading pages) disappear after their due time."""
    due = pt("2026-10-02 10:00")
    canvas = FakeCanvas(planner=[item(5, 1001, "In-class worksheet", due, submittable=False)])
    assert build(due - timedelta(days=1), canvas).state("canvas-assignment-5") == "soon"
    assert build(due + timedelta(days=1), canvas).state("canvas-assignment-5") is None


def test_due_date_extended_moves_group(build):
    now = pt("2026-10-05 12:00")
    old = build(now, FakeCanvas(planner=[item(6, 1002, "Project", pt("2026-10-04 23:59"))]))
    assert old.state("canvas-assignment-6") == "overdue"
    new = build(now, FakeCanvas(planner=[item(6, 1002, "Project", pt("2026-10-30 23:59"))]))
    assert new.state("canvas-assignment-6") == "later"
    assert new.stats["逾期未交"] == 0


def test_new_assignment_appears_and_next_due_updates(build):
    now = pt("2026-10-05 12:00")
    canvas = FakeCanvas(planner=[item(7, 1001, "HW 1", pt("2026-10-09 23:59"))])
    assert build(now, canvas).data["tasks"][0]["title"] == "HW 1"
    canvas.planner.append(item(8, 1002, "Pop quiz", pt("2026-10-06 09:00")))
    page = build(now, canvas)
    assert page.state("canvas-assignment-8") == "soon"
    assert page.data["tasks"][0]["title"] == "Pop quiz"


# ---------------------------------------------------------------- announcements

def test_new_announcement_with_deadline_creates_task_once(build):
    now = pt("2026-10-05 09:00")
    msg = "<p>Please complete the survey by Friday, October 9th.</p><p>Also the reading is due 10/9.</p>"
    canvas = FakeCanvas(announcements=[announcement(50, 1001, "Survey", msg, now - timedelta(hours=2))])
    page = build(now, canvas)
    assert "Survey" in page.announcements
    assert [k for k in page.states if k.startswith("ann-50-")] == ["ann-50-1009"]   # same day twice → one task
    # a Canvas assignment on the same day in the same course → no duplicate
    canvas.planner.append(item(9, 1001, "Survey", pt("2026-10-09 23:59")))
    page = build(now, canvas)
    assert not [k for k in page.states if k.startswith("ann-50-")]


def test_announcement_deadline_windows(build):
    now = pt("2026-10-05 09:00")
    msg = "Old thing was due 10/1. Final paper due December 11. Quiz by 10/12."
    page = build(now, FakeCanvas(announcements=[announcement(51, 1002, "Dates", msg, now)]))
    assert {k for k in page.states if k.startswith("ann-51-")} == {"ann-51-1012"}   # past or > 30 days: skipped


def test_old_announcements_hidden_and_cancel_flag_only_same_day(build):
    lecture_day = pt("2026-10-06 08:00")    # Tuesday; DEMO 002A lecture at 15:30
    canvas = FakeCanvas(announcements=[
        announcement(60, 1002, "CLASS CANCELLED TODAY", "Sorry, class is cancelled today.", lecture_day - timedelta(hours=1)),
        announcement(61, 1001, "Welcome", "Hello!", lecture_day - timedelta(days=12)),
    ])
    page = build(lecture_day, canvas)
    assert "Welcome" not in page.announcements                 # older than 10 days
    assert any("可能取消" in c for c in page.today_classes if "DEMO 002A" in c)
    thursday = build(pt("2026-10-08 08:00"), canvas)           # only on that day
    assert not any("可能取消" in c for c in thursday.today_classes)


def test_ai_enrichment_translates_and_replaces_regex_deadlines(build):
    now = pt("2026-10-05 09:00")
    canvas = FakeCanvas(planner=[item(10, 1001, "Week 2: Attendance Quiz", pt("2026-10-09 16:00"))],
                        announcements=[announcement(70, 1002, "Reminder", "Survey due next Friday.", now)])
    ai = {"model": "fake-model",
          "tasks": [{"id": "canvas-assignment-10", "title": "TEST 101：第 2 周：出勤测验"}],
          "announcements": [{"id": "70", "title": "提醒", "summary": "下周五前填问卷。",
                             "deadlines": [{"what": "填问卷", "due": "2026-10-09T23:59", "quote": "Survey due next Friday."}]}]}
    page = build(now, canvas, ai=ai)
    assert "第 2 周：出勤测验" in page.html and "Week 2: Attendance Quiz" in page.html   # translation + original
    assert "TEST 101：第 2 周" not in page.html                                           # course prefix stripped
    assert "提醒" in page.announcements and "下周五前填问卷。" in page.html
    assert page.state("ann-70-1009") == "soon" and "填问卷" in page.html
    assert "fake-model" in page.html


def test_original_title_hidden_when_translation_only_changes_punctuation(build):
    now = pt("2026-10-05 09:00")
    canvas = FakeCanvas(planner=[item(10, 1001, "Lab 1: Hello, World", pt("2026-10-09 16:00"))])
    ai = {"model": "m", "tasks": [{"id": "canvas-assignment-10", "title": "Lab 1：Hello，World"}], "announcements": []}
    page = build(now, canvas, ai=ai)
    assert "Lab 1：Hello，World" in page.html and 'class="text-secondary small original">Lab 1: Hello' not in page.html


@pytest.mark.parametrize("bad", [
    {"tasks": "oops", "announcements": None},
    {"tasks": [{"id": "canvas-assignment-10"}], "announcements": [{"id": "70", "deadlines": [{"due": "next week"}]}]},
    {"announcements": [{"id": "70", "deadlines": "none"}]},
])
def test_malformed_ai_output_does_not_break_page(build, bad):
    now = pt("2026-10-05 09:00")
    canvas = FakeCanvas(planner=[item(10, 1001, "Quiz", pt("2026-10-09 16:00"))],
                        announcements=[announcement(70, 1002, "Reminder", "text", now)])
    page = build(now, canvas, ai={"model": "x", **bad})
    assert page.state("canvas-assignment-10") == "soon"


def test_ai_unavailable_falls_back_to_rules(build):
    now = pt("2026-10-05 09:00")
    canvas = FakeCanvas(announcements=[announcement(71, 1001, "Due", "Homework due 10/7.", now)])
    page = build(now, canvas, ai=None)
    assert page.state("ann-71-1007") == "soon"


# ---------------------------------------------------------------- weeks, timetable, term

@pytest.mark.parametrize("now,week", [
    ("2026-09-25 12:00", "Week 0 / 10"), ("2026-09-28 08:00", "Week 1 / 10"),
    ("2026-10-12 08:00", "Week 3 / 10"), ("2026-12-04 08:00", "Week 10 / 10"),
])
def test_week_number_progression(build, now, week):
    assert build(pt(now)).week == week


def test_term_is_derived_from_banner(build):
    assert "Fall 2026" in build(pt("2026-10-05 09:00")).html


def test_classes_follow_banner_and_notes(build):
    # Thursday: the TEST 101 discussion only starts on 10/1 (moved by [[notes]])
    assert not any("讨论课" in c for c in build(pt("2026-09-24 08:00")).today_classes)
    thu = build(pt("2026-10-01 08:00"))
    assert any("TEST 101 讨论课 021" in c for c in thu.today_classes)
    assert "starts in week 1" in thu.section("today")              # the note is shown
    assert not any("022" in c for c in thu.today_classes)          # section not enrolled in
    assert any("DEMO 002A 大课" in c for c in thu.today_classes)
    assert "线上课" in thu.html and "DEMO 002A Lab 021" in thu.html


def test_holiday_and_term_end_have_no_classes(build):
    assert build(pt("2026-11-11 08:00")).today_classes == []       # holiday (Wednesday)
    assert build(pt("2026-12-07 08:00")).today_classes == []       # the Monday after the term
    assert "没有课" in build(pt("2026-12-04 20:00")).tomorrow        # Saturday


def test_recurring_tasks_roll_forward_and_stop(build):
    week1 = build(pt("2026-10-01 12:00"))
    assert week1.state("HW-DEMO 002A-2026-10-02") == "soon"
    after = build(pt("2026-10-03 13:00"))                           # more than 12 h past due
    assert after.state("HW-DEMO 002A-2026-10-02") is None
    assert after.state("HW-DEMO 002A-2026-10-09") == "soon"
    end = build(pt("2026-12-05 12:00"))
    assert not [k for k in end.states if k.startswith("HW-")]       # none after the term


def test_calendar_payload_matches_timetable(build):
    page = build(pt("2026-10-05 09:00"), FakeCanvas(planner=[
        item(11, 1001, "Pending", pt("2026-10-09 23:59")), item(12, 1001, "Done", pt("2026-10-08 23:59"), submitted=True)]))
    cal = page.data["calendar"]
    per_day = {}
    for e in cal["events"]:
        if not e.get("allDay"):
            per_day.setdefault(e["start"][:10], []).append(e["title"])
    # term 9/24–12/4: TEST lecture MWF, discussion Thu (from 10/1), DEMO lecture TR; no classes on holidays
    assert "2026-11-11" not in per_day and "2026-11-26" not in per_day
    assert sorted(per_day["2026-10-01"]) == ["DEMO 002A 大课", "TEST 101 讨论课 021"]
    deadlines = [e["title"] for e in cal["events"] if e.get("allDay")]
    assert any("Pending" in t for t in deadlines) and not any("Done" in t for t in deadlines)
    assert cal["hiddenDays"] == [0, 6]


# ---------------------------------------------------------------- time edge cases

def test_dst_change_keeps_wall_clock_due_time(build):
    due = pt("2026-11-06 23:59")                                    # after DST ends on 11/1
    page = build(pt("2026-10-30 12:00"), FakeCanvas(planner=[item(13, 1001, "After DST", due)]))
    t = next(t for t in page.data["tasks"] if t["id"] == "canvas-assignment-13")
    assert t["due"] == "2026-11-06T23:59:00-08:00"


def test_meme_counts_whole_weeks_and_rolls_over(build):
    page = build(pt("2026-09-29 12:00"))
    assert '<span class="meme-num">38</span>' in page.html and "浪费了" in page.html and "meme-zh" in page.html
    assert page.data["meme"]["year"] == 2026
    ny = build(pt("2027-01-01 00:30"), config=None)
    assert '<span class="meme-num">0</span>' in ny.html and ny.data["meme"]["year"] == 2027


# ---------------------------------------------------------------- graceful degradation

def test_canvas_token_expired(build):
    page = build(pt("2026-10-05 09:00"), FakeCanvas(fail=401))
    assert any("token 失效" in w for w in page.warnings)
    assert page.states == {k: v for k, v in page.states.items() if k.startswith("HW-")}   # only recurring tasks


def test_banner_down_still_builds(build):
    page = build(pt("2026-10-05 09:00"), banner_fail=True)
    assert any("选课系统" in w for w in page.warnings)


def test_no_token_and_no_config(build):
    page = build(pt("2026-10-05 09:00"), config=None, token=False)
    assert any("CANVAS_TOKEN" in w for w in page.warnings)
    assert any("PURRFESSOR_CONFIG" in w for w in page.warnings)


# ---------------------------------------------------------------- front-end smoke test

CHROME = next((p for p in ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                           shutil.which("google-chrome") or "", shutil.which("chromium") or ""]
               if p and shutil.os.path.exists(p)), None)


def render_dom(html: str, tmp_path) -> str:
    f = tmp_path / "p.html"
    f.write_text(html, encoding="utf-8")
    cmd = [CHROME, "--headless=new", "--disable-gpu", f"--user-data-dir={tmp_path / 'ud'}",
           "--virtual-time-budget=4000", "--dump-dom", f.as_uri()]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=40).stdout
    except subprocess.TimeoutExpired as e:   # a per-second timer can keep Chrome alive after it dumped the DOM
        return (e.output or b"").decode() if isinstance(e.output, bytes) else (e.output or "")


@pytest.mark.skipif(CHROME is None, reason="no Chrome")
@pytest.mark.parametrize("lang,loading", [("zh", "加载中…"), ("en", "Loading…")])
def test_frontend_script_runs(build, tmp_path, lang, loading):
    page = build(pt("2026-10-05 09:00"), FakeCanvas(planner=[item(14, 1001, "HW", pt("2027-06-01 23:59"))]), lang=lang)
    dom = render_dom(page.html, tmp_path)
    assert "</html>" in dom
    assert loading not in dom                          # the "next class / next deadline" cards were filled in
    assert 'class="fc' in dom                          # FullCalendar rendered
