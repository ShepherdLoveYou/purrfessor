"""Run the generated page in headless Chrome: a pretended clock, scripted actions, and a probe that reads the page back.
The page's CDN files are removed first (unless a layout test asks for them), so most tests need Chrome but no network.
在无头 Chrome 里运行生成的页面：假时钟、脚本化的操作、最后读回页面状态。默认去掉 CDN 文件，所以大多数测试不需要网络。"""
from __future__ import annotations

import html as htmllib
import json
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

import pytest
from conftest import CONFIG

CHROME = next((p for p in ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                           shutil.which("google-chrome") or "", shutil.which("chromium") or ""]
               if p and shutil.os.path.exists(p)), None)


def render_dom(html: str, tmp_path, name: str = "p.html") -> str:
    f = tmp_path / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(html, encoding="utf-8")
    cmd = [CHROME, "--headless=new", "--disable-gpu", f"--user-data-dir={tmp_path / 'ud'}",
           "--virtual-time-budget=4000", "--dump-dom", f.as_uri()]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=40).stdout
    except subprocess.TimeoutExpired as e:   # a per-second timer can keep Chrome alive after it dumped the DOM
        return (e.output or b"").decode() if isinstance(e.output, bytes) else (e.output or "")


needs_chrome = pytest.mark.skipif(CHROME is None, reason="no Chrome")


PAGE_TEMPLATE = Path(__file__).resolve().parent.parent / "purrfessor" / "templates" / "page.html"
# every file the page takes from a CDN, read from the template so that a version bump needs no change here
CDN_URLS = re.findall(r'(?:href|src)="(https://[^"]+)"', PAGE_TEMPLATE.read_text(encoding="utf-8"))
TABLER_CSS = next(u for u in CDN_URLS if u.endswith("/tabler.min.css"))


def cdn_reachable() -> bool:
    """A quick ping from Python, so that a machine with no network skips at once. It cannot promise that Chrome gets the
    files too (see run_page: a layout test skips itself when a CDN file did not arrive)."""
    try:
        urllib.request.urlopen(TABLER_CSS, timeout=5).close()
        return True
    except OSError:
        return False


needs_cdn = pytest.mark.skipif(not cdn_reachable(), reason="no network: layout tests need Tabler's real CSS")
# in the page: did every CDN stylesheet and FullCalendar arrive, and does Tabler define its variables (a 200 that is not CSS)?
CDN_LOADED = ("[].every.call(document.querySelectorAll('link[rel=stylesheet][href^=\"https:\"]'), function (l) { return !!l.sheet; })"
              " && !!window.FullCalendar && !!getComputedStyle(document.body).getPropertyValue('--tblr-body-bg').trim()")
PLAIN = CONFIG.split("[[recurring]]")[0]      # no weekly homework task to get in the way of "the next deadline"

CLOCK = """<script>(function () {
  var Real = Date, base = Real.now(), at = Date.parse("%s"), shift = 0;
  function now() { return at + shift + (Real.now() - base); }
  window.Date = class extends Real { constructor(...a) { if (a.length) super(...a); else super(now()); } static now() { return now(); } };
  window.jump = function (ms) { shift += ms; };
  %s
})();</script>"""
BLOCK_STORAGE = 'Object.defineProperty(window, "localStorage", { get: function () { throw new Error("blocked"); } });'


def framed(doc: str, width: int, height: int) -> str:
    """The page in an iframe of exactly this size: headless Chrome will not open a window narrower than 500 px, and media
    queries (max-width: 575px …) answer for the iframe. srcdoc keeps it same-origin: the probe writes its result into the outer page."""
    return ('<!doctype html><meta charset="utf-8"><body style="margin:0">'
            f'<iframe id="f" style="width:{width}px;height:{height}px;border:0" srcdoc="{htmllib.escape(doc, quote=True)}"></iframe>')


def hermetic(page: str) -> str:
    """The page without its CDN files (no FullCalendar, no Tabler CSS): the script copes with a missing calendar."""
    return re.sub(r'<link rel="stylesheet" href="https://[^"]+">|<script src="https://[^"]+"></script>', "", page)


def run_page(page, tmp_path, now, probe="null", steps=(), blocked_storage=False, size=None, cdn=False, init="", css="",
             name="p.html"):
    """Load page.html in Chrome with the clock at `now`; `steps` = [(virtual ms, js)] run in order (the js can call
    jump(ms) to move the clock on); at 3.5 s the value of the JS expression `probe` is returned, parsed from JSON.
    cdn=True keeps Tabler / FullCalendar (layout tests need the real CSS) and skips the test if Chrome did not get all of
    them (the deploy runs the suite as its gate: a CDN hiccup must not block it); `init` is JS that runs before the page's own,
    `css` is added to the head (a stand-in for the Tabler rules a test needs), `name` is the file name ("archive/2026-10-09.html"
    makes it a snapshot page); `size` = (width, height) of the viewport, from 320 up (see framed)."""
    run = "".join(f'setTimeout(function () {{ {js} }}, {ms});' for ms, js in steps)
    loaded = f'out.setAttribute("data-cdn", {CDN_LOADED} ? "ok" : "missing");' if cdn else ""
    out = (f'setTimeout(function () {{ var r; try {{ r = JSON.stringify({probe}); }} catch (e) {{ r = JSON.stringify("ERR " + e); }}'
           f'var out = document.createElement("pre"); out.id = "probe-result"; out.textContent = r; {loaded}'
           f'(window.parent !== window ? window.parent.document : document).body.appendChild(out); }}, 3500);')   # a framed page reports to its frame
    doc = page.html if hasattr(page, "html") else page
    doc = doc if cdn else hermetic(doc)
    doc = doc.replace("<head>", f"<head><style>{css}</style>" + CLOCK % (now.isoformat(), (BLOCK_STORAGE if blocked_storage else "") + init), 1)
    doc = doc.replace("</body>", f"<script>{run}{out}</script></body>")
    assert not (size and name != "p.html"), "a sized page runs in an iframe: it has no file name of its own"
    dom = render_dom(framed(doc, *size) if size else doc, tmp_path, name=name)
    found = re.search(r'<pre id="probe-result"[^>]*>(.*?)</pre>', dom, re.S)
    assert found, "the probe never ran: " + dom[-600:]
    if cdn and 'data-cdn="missing"' in dom:      # the ping from Python passed, but Chrome did not get every file: a flaky CDN is not a bug
        pytest.skip("a CDN file did not load in Chrome")
    return json.loads(htmllib.unescape(found.group(1)))
