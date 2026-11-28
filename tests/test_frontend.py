"""The page script, run for real: Chrome loads the generated page with a pretended clock, a few scripted actions
(time passing, a tap on a tick box) and a probe that reads the page back. The page's CDN files are removed first, so
these tests need Chrome but no network: the script and the inline CSS are all they use.
页面脚本的行为测试：用 Chrome 真正运行生成的页面，假时钟、脚本化的操作（时间流逝、点打勾框）、最后读回页面状态。不需要网络。"""
from __future__ import annotations

import re
from datetime import timedelta

import pytest
from browser import PLAIN, needs_cdn, needs_chrome, run_page
from conftest import FakeCanvas, item, pt

NEXT = ("({big: document.querySelector('#next-due .next-big').className, text: document.querySelector('#next-due .next-big').textContent,"
        " bar: document.getElementById('next-due').style.getPropertyValue('--c'), title: document.querySelector('#next-due .next-title').textContent})")


# ---------------------------------------------------------------- the next-deadline countdown follows urgency

@needs_chrome
@pytest.mark.parametrize("hours,tone", [(6, "tone-red"), (23, "tone-red"), (30, "tone-orange"), (70, "tone-orange"), (80, None), (300, None)])
def test_next_deadline_number_is_coloured_by_urgency_not_by_course(build, tmp_path, hours, tone):
    """A green "8 hours left" reads as "fine" when it is due tonight: red under 24 h, orange under 72 h (the badge
    thresholds), the normal text colour after that. The course colour stays on the status bar."""
    now = pt("2026-10-09 12:00")
    page = build(now, FakeCanvas(planner=[item(1, 1001, "Essay", now + timedelta(hours=hours))]), config=PLAIN)
    got = run_page(page, tmp_path, now, NEXT)
    assert got["title"] == "Essay"
    classes = got["big"].split()
    assert [c for c in classes if c.startswith("tone-")] == ([tone] if tone else [])
    assert re.fullmatch(r"#[0-9a-f]{6}", got["bar"].strip()), got["bar"]       # the course colour is still on the bar


@needs_chrome
def test_next_deadline_tone_follows_the_clock_and_clears(build, tmp_path):
    """The tone is recomputed every second: orange at 40 h left, red once the clock passes 20 h before the due time."""
    now = pt("2026-10-09 12:00")
    page = build(now, FakeCanvas(planner=[item(1, 1001, "Essay", now + timedelta(hours=40))]), config=PLAIN)
    got = run_page(page, tmp_path, now, NEXT, steps=[(1500, f"jump({20 * 3600 * 1000})")])
    assert "tone-red" in got["big"].split() and "tone-orange" not in got["big"].split()


# ---------------------------------------------------------------- the phone header

LAYOUT = ("({inner: innerWidth, sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,"
          " lines: Math.round(document.querySelector('h1.page-title').getBoundingClientRect().height /"
          " parseFloat(getComputedStyle(document.querySelector('h1.page-title')).lineHeight)),"
          " nav: [document.querySelector('.nav-sticky').getBoundingClientRect().left, document.querySelector('.nav-sticky').getBoundingClientRect().right]})")


@needs_chrome
@needs_cdn
@pytest.mark.parametrize("lang", ["zh", "en"])
@pytest.mark.parametrize("width", [360, 375, 390, 412])
def test_phone_header_keeps_the_title_on_one_line_and_never_scrolls_sideways(build, tmp_path, width, lang):
    """The sticky nav used to be 4 px wider than the screen on a phone, and the term progress squeezed the title into two lines."""
    now = pt("2026-10-09 12:00")
    page = build(now, FakeCanvas(planner=[item(1, 1001, "Essay", now + timedelta(hours=6))]), lang=lang)
    got = run_page(page, tmp_path, now, LAYOUT, size=(width, 900), cdn=True)
    assert got["lines"] == 1, got
    assert got["sw"] <= got["cw"], got                              # compared with clientWidth: a classic scrollbar takes 15 px
    assert got["nav"][0] >= 0 and got["nav"][1] <= got["cw"], got   # the nav is as wide as the screen, not wider


# ---------------------------------------------------------------- the counters follow the clock and the ticks

COUNTERS = "[].map.call(document.querySelectorAll('[data-stat]'), function (e) { return e.dataset.stat + '=' + e.textContent; }).sort()"
HOUR = 3600 * 1000


@needs_chrome
def test_a_canvas_task_whose_time_passes_while_the_page_is_open_becomes_overdue(build, tmp_path):
    """Built with the work still ahead (due today, in 3 days), opened and left open past its due time: it moves from
    "due today / due in 3 days" to "overdue" without a reload, and the red / green avatar follows."""
    now = pt("2026-10-09 12:00")
    page = build(now, FakeCanvas(planner=[item(1, 1001, "Quiz", now + timedelta(hours=2))]), config=PLAIN)
    assert page.stats["今天截止"] == 1 and page.stats["逾期未交"] == 0
    probe = f"({{counters: {COUNTERS}, avatar: document.querySelector('[data-stat=overdue]').closest('.row').querySelector('.avatar').className}})"
    before = run_page(page, tmp_path, now, probe)
    assert before["counters"] == ["due_3d=1", "due_today=1", "overdue=0"] and "bg-green" in before["avatar"]
    after = run_page(page, tmp_path, now, probe, steps=[(1500, f"jump({3 * HOUR})")])
    assert after["counters"] == ["due_3d=0", "due_today=0", "overdue=1"] and "bg-red" in after["avatar"]


@needs_chrome
def test_off_canvas_work_past_its_time_is_counted_nowhere(build, tmp_path):
    """The weekly homework site is not Canvas: the server never calls it overdue (it leaves the list 12 h after its time),
    so the script does not either."""
    now = pt("2026-10-09 20:00")                       # the Friday homework is due at 23:59
    page = build(now, FakeCanvas())
    assert page.state("HW-DEMO 002A-2026-10-09") == "soon" and 'data-manual="1"' in page.html
    probe = f"({COUNTERS})"
    assert run_page(page, tmp_path, now, probe) == ["due_3d=1", "due_today=1", "overdue=0"]
    assert run_page(page, tmp_path, now, probe, steps=[(1500, f"jump({5 * HOUR})")]) == ["due_3d=0", "due_today=0", "overdue=0"]


def test_the_server_counts_the_same_way_for_off_canvas_work_past_its_time(build):
    """Built an hour after the homework's due time: still on the list (12 h), but in no counter."""
    page = build(pt("2026-10-10 00:59"), FakeCanvas())
    assert page.state("HW-DEMO 002A-2026-10-09") == "soon"
    assert page.stats["今天截止"] == 0 and page.stats["3 天内截止"] == 0 and page.stats["逾期未交"] == 0


@needs_chrome
def test_a_snapshot_page_keeps_the_numbers_it_was_built_with(build, tmp_path):
    now = pt("2026-10-09 12:00")
    page = build(now, FakeCanvas(planner=[item(1, 1001, "Quiz", now + timedelta(hours=2))]), config=PLAIN)
    probe = f"({COUNTERS})"
    frozen = run_page(page, tmp_path, now, probe, steps=[(1500, f"jump({3 * HOUR})")], name="archive/2026-10-09.html")
    assert frozen == ["due_3d=1", "due_today=1", "overdue=0"]


@needs_chrome
def test_ticking_a_task_takes_it_out_of_the_counters_and_the_next_card(build, tmp_path):
    now = pt("2026-10-09 12:00")
    canvas = FakeCanvas(planner=[item(1, 1001, "First", now + timedelta(hours=2)), item(2, 1001, "Second", now + timedelta(hours=30))])
    page = build(now, canvas, config=PLAIN)
    probe = f"({{counters: {COUNTERS}, next: document.querySelector('#next-due .next-title').textContent, " \
            "struck: document.querySelector('.tick').closest('.task').classList.contains('checked')})"
    assert run_page(page, tmp_path, now, probe) == {"counters": ["due_3d=2", "due_today=1", "overdue=0"], "next": "First", "struck": False}
    got = run_page(page, tmp_path, now, probe, steps=[(1500, "document.querySelector('.tick').click()")])
    assert got == {"counters": ["due_3d=1", "due_today=0", "overdue=0"], "next": "Second", "struck": True}


@needs_chrome
def test_ticks_stay_for_the_visit_when_the_device_store_throws(build, tmp_path):
    """localStorage can be blocked: the strike-through and the "next deadline" card must still agree."""
    now = pt("2026-10-09 12:00")
    canvas = FakeCanvas(planner=[item(1, 1001, "First", now + timedelta(hours=2)), item(2, 1001, "Second", now + timedelta(hours=30))])
    page = build(now, canvas, config=PLAIN)
    probe = ("({store: (function () { try { return typeof localStorage.length; } catch (x) { return 'blocked'; } })(),"
             " next: document.querySelector('#next-due .next-title').textContent,"
             " struck: document.querySelector('.tick').closest('.task').classList.contains('checked'),"
             f" checked: document.querySelector('.tick').checked, counters: {COUNTERS}}})")
    got = run_page(page, tmp_path, now, probe, steps=[(1500, "document.querySelector('.tick').click()")], blocked_storage=True)
    assert got == {"store": "blocked", "next": "Second", "struck": True, "checked": True, "counters": ["due_3d=1", "due_today=0", "overdue=0"]}
    # and unticking brings it back
    back = run_page(page, tmp_path, now, probe, blocked_storage=True,
                    steps=[(1500, "document.querySelector('.tick').click()"), (2200, "document.querySelector('.tick').click()")])
    assert back["next"] == "First" and back["struck"] is False


@needs_chrome
def test_a_tick_made_in_another_tab_shows_here(build, tmp_path):
    now = pt("2026-10-09 12:00")
    canvas = FakeCanvas(planner=[item(1, 1001, "First", now + timedelta(hours=2)), item(2, 1001, "Second", now + timedelta(hours=30))])
    page = build(now, canvas, config=PLAIN)
    probe = "({next: document.querySelector('#next-due .next-title').textContent, checked: document.querySelector('.tick').checked})"
    event = "window.dispatchEvent(new StorageEvent('storage', {key: 'purrfessor-done:canvas-assignment-1', newValue: '1'}))"
    assert run_page(page, tmp_path, now, probe, steps=[(1500, event)]) == {"next": "Second", "checked": True}
