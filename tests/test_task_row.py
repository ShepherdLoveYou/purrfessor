"""A task row reads cleanly on a phone: no stray "·", the time only under a day heading, the date where there is no such
heading, and a long quote from an announcement clamped to two lines that open on a tap or a key.
手机上的任务行：没有孤零零的“·”，日分组下只写时间，没有分组标题的行写日期，公告里的长引用两行截断、点一下展开。"""
from __future__ import annotations

import re
from datetime import timedelta

import pytest
from browser import needs_chrome, run_page
from conftest import CONFIG, FakeCanvas, announcement, item, pt

NOW = pt("2026-10-09 12:00")


def row(page, tid: str) -> str:
    return re.search(rf'<div class="list-group-item task[^"]*"[^>]*data-id="{re.escape(tid)}".*?</div></div></div>',
                     page.html, re.S).group(0)


def meta(block: str) -> str:
    return re.search(r'<div class="text-secondary small mt-1 d-flex flex-wrap gap-2 align-items-center">(.*?)</div>', block, re.S).group(1)


def test_no_text_in_the_meta_line_starts_or_ends_with_a_dot(build):
    """The line is a flex row: a text node that began with "· " showed as a lone dot at the start of a wrapped line."""
    canvas = FakeCanvas(planner=[item(1, 1001, "Reading", pt("2026-10-10 23:59"), points=5, feedback=True)])
    block = meta(row(build(NOW, canvas), "canvas-assignment-1"))
    assert not re.search(r">\s*·|·\s*<", block), block
    assert re.fullmatch(r'<span class="badge bg-\w+-lt">TEST 101</span><span>作业 · 5 分 · 23:59</span>'
                        r'<a class="badge bg-blue-lt" href="[^"]*" target="_blank" rel="noopener">.*</a>', block, re.S), block


def test_a_row_under_a_day_heading_says_only_the_time(build):
    canvas = FakeCanvas(planner=[item(1, 1001, "Reading", pt("2026-10-10 23:59")), item(2, 1001, "Today", pt("2026-10-09 18:00"))])
    page = build(NOW, canvas)
    assert "明天 · 10/10 周六 · 1" in page.html and "今天 · 10/9 周五" in page.html          # the headings say the day
    assert "<span>作业 · 10 分 · 23:59</span>" in row(page, "canvas-assignment-1")
    assert "<span>作业 · 10 分 · 18:00</span>" in row(page, "canvas-assignment-2")
    assert "明天 23:59" not in page.html and "今天 18:00" not in page.html


def test_rows_without_a_day_heading_say_the_date(build):
    """Later, overdue and recently handed-in rows are not grouped by day: the weekday alone ("周五") was ambiguous."""
    canvas = FakeCanvas(planner=[item(1, 1001, "Later", pt("2026-11-13 23:59")),
                                 item(2, 1001, "Overdue", pt("2026-10-05 11:00"), missing=True),
                                 item(3, 1001, "Handed in", pt("2026-10-08 23:59"), submitted=True)])
    page = build(NOW, canvas)
    assert "<span>作业 · 10 分 · 11/13 周五 23:59</span>" in row(page, "canvas-assignment-1")
    assert "<span>作业 · 10 分 · 10/5 周一 11:00</span>" in row(page, "canvas-assignment-2")
    assert "<span>作业 · 10 分 · 10/8 周四 23:59</span>" in row(page, "canvas-assignment-3")


def test_english_rows_have_no_chinese(build):
    canvas = FakeCanvas(planner=[item(1, 1001, "Essay", pt("2026-10-10 23:59")), item(2, 1001, "Old", pt("2026-10-05 11:00"), missing=True)])
    page = build(NOW, canvas, lang="en")
    assert "<span>Assignment · 10 pts · 23:59</span>" in row(page, "canvas-assignment-1")
    assert "<span>Assignment · 10 pts · Mon 10/5 11:00</span>" in row(page, "canvas-assignment-2")
    assert not re.search(r"[一-鿿]", row(page, "canvas-assignment-1") + row(page, "canvas-assignment-2"))


# ---------------------------------------------------------------- the note quoted from an announcement

ANN = [announcement(51, 1002, "Dates", "Hi all, the final survey is due 10/12, please submit it on time. " * 4, NOW)]


def test_a_quoted_note_is_two_lines_that_open_on_a_tap_or_a_key(build):
    page = build(NOW, FakeCanvas(announcements=ANN))
    block = row(page, "ann-51-1012")
    note = re.search(r'<div class="text-secondary small mt-1 preview-2 preview"([^>]*)>(.*?)</div>', block, re.S)
    assert note and 'tabindex="0" role="button" aria-expanded="false"' in note.group(1)
    assert "final survey is due 10/12" in note.group(2)
    assert ".preview-2 { -webkit-line-clamp: 2; }" in page.html


def test_the_note_suffix_is_short_in_both_languages(build):
    zh = row(build(NOW, FakeCanvas(announcements=ANN)), "ann-51-1012")
    en = row(build(NOW, FakeCanvas(announcements=ANN), lang="en"), "ann-51-1012")
    assert "” —— 自动读的，请核对</div>" in zh and "请点开核对" not in zh
    assert "” — read from the announcement, please check</div>" in en and "double-check" not in en and not re.search(r"[一-鿿]", en)


def test_the_note_suffix_when_the_ai_read_it(build):
    ai = {"model": "m", "tasks": [], "announcements": [{"id": "51", "title": "Dates", "summary": "s", "deadlines": [
        {"what": "Survey", "due": "2026-10-12T23:59", "quote": "the final survey is due 10/12"}]}]}
    page = build(NOW, FakeCanvas(announcements=ANN), ai=ai)
    assert "“the final survey is due 10/12” —— AI 读的，请核对</div>" in row(page, "ann-51-1012")


@needs_chrome
def test_the_note_opens_and_closes_with_click_enter_and_space_but_not_other_keys(build, tmp_path):
    page = build(NOW, FakeCanvas(announcements=ANN))
    key = "p.dispatchEvent(new KeyboardEvent('keydown', {key: '%s', bubbles: true, cancelable: true}))"
    state = "({open: p.classList.contains('open'), expanded: p.getAttribute('aria-expanded')})"
    steps = [(1200, "window.p = document.querySelector('#todo .preview'); window.log = []; "
                    "window.snap = function () { log.push(" + state + "); };"),
             (1300, "p.click(); snap();"),                       # click opens
             (1400, key % "Enter" + "; snap();"),                  # Enter closes
             (1500, key % " " + "; snap();"),                      # Space opens
             (1600, key % "Tab" + "; snap();"),                    # Tab does nothing
             (1700, key % "Escape" + "; snap();")]                # nor does Escape
    log = run_page(page, tmp_path, NOW, "log", steps)
    assert log == [{"open": True, "expanded": "true"}, {"open": False, "expanded": "false"},
                   {"open": True, "expanded": "true"}, {"open": True, "expanded": "true"}, {"open": True, "expanded": "true"}]


def test_nothing_changes_for_a_task_without_a_note(build):
    page = build(NOW, FakeCanvas(planner=[item(1, 1001, "Plain", pt("2026-10-10 23:59"))]), config=CONFIG.split("[[recurring]]")[0])
    assert "preview" not in row(page, "canvas-assignment-1")


@pytest.mark.parametrize("hours", [3, 40])
def test_the_row_still_has_its_countdown_badge_and_tick_box(build, hours):
    page = build(NOW, FakeCanvas(planner=[item(1, 1001, "Essay", NOW + timedelta(hours=hours))]))
    block = row(page, "canvas-assignment-1")
    assert 'class="form-check-input m-0 tick"' in block and re.search(r'<span class="badge bg-\w+-lt cd">', block)
