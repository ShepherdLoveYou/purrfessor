"""Page structure and phone layout contracts that need no browser: the heading, the sticky nav, the card headers, the
safe areas. (The measured layout, at 360-412 px wide, is in test_frontend.py.) 页面结构和手机布局的约定。"""
from __future__ import annotations

import re

from conftest import FakeCanvas, item, pt
from purrfessor.render import TEMPLATE

CSS = TEMPLATE.read_text(encoding="utf-8")
NOW = pt("2026-10-09 12:00")


def test_the_page_title_is_the_one_h1(build):
    """A real h1 (it was an h2); the look is Tabler's .page-title, unchanged."""
    for lang, title in (("zh", "Tester 的今日"), ("en", "Tester&#x27;s Today")):
        page = build(NOW, lang=lang)
        assert re.findall(r"<h1[ >]", page.html) == ["<h1 "]
        assert f'<h1 class="page-title">{title}</h1>' in page.html


def test_the_term_progress_can_move_under_the_title_on_a_phone(build):
    page = build(NOW)
    assert '<div class="col-auto term-col"><div class="term-week text-end small text-secondary">' in page.html
    phone = re.search(r"@media \(max-width: 575\.98px\) \{(.*?)\n  \}", CSS, re.S).group(1)
    assert ".page-header .term-col { width: 100%" in phone and ".term-progress { flex: 1; width: auto; }" in phone


def test_long_card_notes_drop_under_the_title_on_a_phone(build):
    """The grey note beside a card title squeezed the title into two lines: the long ones carry .card-note."""
    page = build(NOW, FakeCanvas(planner=[item(1, 1001, "Essay", pt("2026-10-10 23:59"))]))
    notes = re.findall(r'<div class="card-actions card-note text-secondary small">', page.html)
    assert len(notes) >= 3                                     # to-do, timetable and at least one more
    for sid in ("todo", "timetable"):
        assert 'card-actions card-note' in page.section(sid)
    assert 'card-actions text-secondary small">' in page.section("today")      # short: stays beside the title
    assert ".card-note { flex: 1 0 100%;" in CSS and ".card-header { flex-wrap: wrap; row-gap: .125rem; padding-block: .75rem; }" in CSS


def test_the_sticky_nav_cancels_exactly_the_container_padding():
    """Its margin used to be a fixed -.75rem, more than the phone's 8 px padding: 4 px of sideways scrolling."""
    assert "margin: 1rem calc(-1 * var(--pad-r)) 0 calc(-1 * var(--pad-l))" in CSS
    assert "padding: .5rem var(--pad-r) .5rem var(--pad-l)" in CSS
    assert "-.75rem" not in re.search(r"\.nav-sticky \{[^}]*\}", CSS).group(0)


def test_safe_area_insets_pad_the_container_and_the_nav():
    """viewport-fit=cover lets the page run under a notch / rounded corners when the phone is held sideways."""
    assert "max(var(--tblr-page-padding, .75rem), env(safe-area-inset-left, 0px))" in CSS
    assert "max(var(--tblr-page-padding, .75rem), env(safe-area-inset-right, 0px))" in CSS
    assert "padding-top: env(safe-area-inset-top, 0px); padding-bottom: env(safe-area-inset-bottom, 0px)" in CSS
    assert "top: env(safe-area-inset-top, 0px)" in re.search(r"\.nav-sticky \{[^}]*\}", CSS).group(0)
