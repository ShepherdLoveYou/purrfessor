"""Dark mode: the calendar wears the card's colours, the meme is dimmed (not a white slab) without moving or resizing,
and the page follows the system theme while it stays open. 深色模式：课表跟卡片同色，表情包压暗，系统切换主题时页面跟着变。"""
from __future__ import annotations

import re

import pytest
from browser import needs_chrome, run_page
from conftest import FakeCanvas, item, pt
from purrfessor.render import TEMPLATE

CSS = TEMPLATE.read_text(encoding="utf-8")
NOW = pt("2026-10-09 12:00")

# a matchMedia whose answer the test can flip: the page's own (prefers-color-scheme) query listens to it
FAKE_SCHEME = """
var __dark = false, __listeners = [];
window.matchMedia = function (q) { return { media: q, get matches() { return __dark; },
  addEventListener: function (t, f) { __listeners.push(f); } }; };
window.flip = function (dark) { __dark = dark; __listeners.forEach(function (f) { f({ matches: dark }); }); };
"""


def test_the_calendar_uses_the_surface_and_border_colours_of_the_page():
    """FullCalendar's forma palette is #030712 in dark mode: darker than the cards around it."""
    rule = re.search(r"#calendar \{([^}]*)\}", CSS).group(1)
    assert "--fc-forma-background: var(--tblr-bg-surface)" in rule and "--fc-forma-border: var(--tblr-border-color)" in rule
    assert "--fc-forma-muted-foreground: var(--tblr-secondary-color)" in rule          # the hour labels stay readable


def test_the_meme_is_dimmed_in_dark_mode_and_keeps_its_place_size_and_aspect():
    assert re.search(r':root\[data-bs-theme="dark"\] \.meme \{ filter: brightness\(\.[5-9]\d*\)', CSS)
    meme = re.search(r"\n  \.meme \{([^}]*)\}", CSS).group(1)
    assert "max-width: 560px" in meme and "aspect-ratio: 1170 / 792" in meme            # size and aspect are as they were
    assert "filter" not in meme                                                          # light mode is untouched


def test_the_meme_still_sits_between_the_next_cards_and_the_todo_list(build):
    page = build(NOW, FakeCanvas(planner=[item(1, 1001, "Essay", pt("2026-10-10 23:59"))]))
    at = lambda key: page.html.index(key)  # noqa: E731
    assert at('id="next-due"') < at('id="meme"') < at('id="todo"')


@needs_chrome
def test_the_page_follows_the_system_theme_while_it_is_open(build, tmp_path):
    page = build(NOW)
    state = "({bs: document.documentElement.getAttribute('data-bs-theme'), fc: document.documentElement.getAttribute('data-color-scheme')})"
    steps = [(1200, "window.log = [" + state + "];"), (1300, "flip(true); log.push(" + state + ");"),
             (1400, "flip(false); log.push(" + state + ");")]
    log = run_page(page, tmp_path, NOW, "log", steps, init=FAKE_SCHEME)
    assert log == [{"bs": "light", "fc": "light"}, {"bs": "dark", "fc": "dark"}, {"bs": "light", "fc": "light"}]


@needs_chrome
@pytest.mark.parametrize("dark", [False, True])
def test_the_theme_is_set_before_the_first_paint(build, tmp_path, dark):
    """The head script sets both attributes at once (Tabler and FullCalendar read different ones)."""
    page = build(NOW)
    init = FAKE_SCHEME.replace("__dark = false", f"__dark = {str(dark).lower()}")
    got = run_page(page, tmp_path, NOW, "document.documentElement.getAttribute('data-bs-theme') + '/' + "
                   "document.documentElement.getAttribute('data-color-scheme')", init=init)
    assert got == ("dark/dark" if dark else "light/light")
