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

import pytest
from conftest import CONFIG

CHROME = next((p for p in ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                           shutil.which("google-chrome") or "", shutil.which("chromium") or ""]
               if p and shutil.os.path.exists(p)), None)


def render_dom(html: str, tmp_path, size: tuple[int, int] | None = None) -> str:
    f = tmp_path / "p.html"
    f.write_text(html, encoding="utf-8")
    cmd = [CHROME, "--headless=new", "--disable-gpu", f"--user-data-dir={tmp_path / 'ud'}",
           *([f"--window-size={size[0]},{size[1]}"] if size else []),
           "--virtual-time-budget=4000", "--dump-dom", f.as_uri()]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=40).stdout
    except subprocess.TimeoutExpired as e:   # a per-second timer can keep Chrome alive after it dumped the DOM
        return (e.output or b"").decode() if isinstance(e.output, bytes) else (e.output or "")


needs_chrome = pytest.mark.skipif(CHROME is None, reason="no Chrome")


def cdn_reachable() -> bool:
    try:
        urllib.request.urlopen("https://cdn.jsdelivr.net/npm/@tabler/core@1.6.1/dist/css/tabler.min.css", timeout=5).close()
        return True
    except OSError:
        return False


needs_cdn = pytest.mark.skipif(not cdn_reachable(), reason="no network: layout tests need Tabler's real CSS")
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


def run_page(page, tmp_path, now, probe="null", steps=(), blocked_storage=False, size=None, cdn=False, init=""):
    """Load page.html in Chrome with the clock at `now`; `steps` = [(virtual ms, js)] run in order (the js can call
    jump(ms) to move the clock on); at 3.5 s the value of the JS expression `probe` is returned, parsed from JSON.
    cdn=True keeps Tabler / FullCalendar (layout tests need the real CSS); `init` is JS that runs before the page's own."""
    run = "".join(f'setTimeout(function () {{ {js} }}, {ms});' for ms, js in steps)
    out = (f'setTimeout(function () {{ var r; try {{ r = JSON.stringify({probe}); }} catch (e) {{ r = JSON.stringify("ERR " + e); }}'
           f'var out = document.createElement("pre"); out.id = "probe-result"; out.textContent = r; document.body.appendChild(out); }}, 3500);')
    doc = page.html if hasattr(page, "html") else page
    doc = doc if cdn else hermetic(doc)
    doc = doc.replace("<head>", "<head>" + CLOCK % (now.isoformat(), (BLOCK_STORAGE if blocked_storage else "") + init), 1)
    doc = doc.replace("</body>", f"<script>{run}{out}</script></body>")
    dom = render_dom(doc, tmp_path, size)
    found = re.search(r'<pre id="probe-result">(.*?)</pre>', dom, re.S)
    assert found, "the probe never ran: " + dom[-600:]
    return json.loads(htmllib.unescape(found.group(1)))
