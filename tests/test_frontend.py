"""The page script, run for real: Chrome loads the generated page with a pretended clock, a few scripted actions
(time passing, a tap on a tick box) and a probe that reads the page back. The page's CDN files are removed first, so
these tests need Chrome but no network: the script and the inline CSS are all they use.
页面脚本的行为测试：用 Chrome 真正运行生成的页面，假时钟、脚本化的操作（时间流逝、点打勾框）、最后读回页面状态。不需要网络。"""
from __future__ import annotations

import html as htmllib
import json
import re
from datetime import timedelta

import pytest
from conftest import CONFIG, FakeCanvas, item, pt
from test_today import CHROME, render_dom

needs_chrome = pytest.mark.skipif(CHROME is None, reason="no Chrome")
PLAIN = CONFIG.split("[[recurring]]")[0]      # no weekly homework task to get in the way of "the next deadline"

CLOCK = """<script>(function () {
  var Real = Date, base = Real.now(), at = Date.parse("%s"), shift = 0;
  function now() { return at + shift + (Real.now() - base); }
  window.Date = class extends Real { constructor(...a) { if (a.length) super(...a); else super(now()); } static now() { return now(); } };
  window.jump = function (ms) { shift += ms; };
  %s
})();</script>"""
BLOCK_STORAGE = 'Object.defineProperty(window, "localStorage", { get: function () { throw new Error("blocked"); } });'


def hermetic(page: str) -> str:
    """The page without its CDN files (no FullCalendar, no Tabler CSS): the script copes with a missing calendar."""
    return re.sub(r'<link rel="stylesheet" href="https://[^"]+">|<script src="https://[^"]+"></script>', "", page)


def run_page(page, tmp_path, now, probe="null", steps=(), blocked_storage=False, size=None):
    """Load page.html in Chrome with the clock at `now`; `steps` = [(virtual ms, js)] run in order (the js can call
    jump(ms) to move the clock on); at 3.5 s the value of the JS expression `probe` is returned, parsed from JSON."""
    run = "".join(f'setTimeout(function () {{ {js} }}, {ms});' for ms, js in steps)
    out = (f'setTimeout(function () {{ var r; try {{ r = JSON.stringify({probe}); }} catch (e) {{ r = JSON.stringify("ERR " + e); }}'
           f'var p = document.createElement("pre"); p.id = "probe-result"; p.textContent = r; document.body.appendChild(p); }}, 3500);')
    doc = hermetic(page.html if hasattr(page, "html") else page)
    doc = doc.replace("<head>", "<head>" + CLOCK % (now.isoformat(), BLOCK_STORAGE if blocked_storage else ""), 1)
    doc = doc.replace("</body>", f"<script>{run}{out}</script></body>")
    dom = render_dom(doc, tmp_path, size)
    found = re.search(r'<pre id="probe-result">(.*?)</pre>', dom, re.S)
    assert found, "the probe never ran: " + dom[-600:]
    return json.loads(htmllib.unescape(found.group(1)))


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
