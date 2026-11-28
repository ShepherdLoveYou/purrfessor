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
