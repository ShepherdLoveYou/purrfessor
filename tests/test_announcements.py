"""An announcement's preview is the start of its body (about 600 characters, not a hard cut at 220 that left nothing to
reveal), without the greeting and without a first line that repeats the title; tapping it shows the rest.
公告预览：正文开头约 600 字，去掉问候语和重复标题，点开能看到更多。"""
from __future__ import annotations

import re

import pytest
from browser import needs_chrome, run_page
from conftest import FakeCanvas, announcement, pt
from purrfessor.canvas import PREVIEW_CHARS, preview

NOW = pt("2026-10-09 12:00")
LONG = " ".join(f"Sentence number {i} says something useful about the course." for i in range(1, 40))      # ~2300 characters


@pytest.mark.parametrize("title,text,expected", [
    ("Plain", "The midterm is on Friday.", "The midterm is on Friday."),
    ("Dates", "Hi everyone,\nThe midterm is Friday.", "The midterm is Friday."),
    ("Dates", "Greetings All,\nThe midterm is Friday.", "The midterm is Friday."),
    ("Dates", "Hi PSYC 001,\nWelcome back.", "Welcome back."),
    ("Dates", "Good morning, everyone!\nQuiz today.", "Quiz today."),
    ("Dates", "Hello Students and TAs!\nQuiz today.", "Quiz today."),
    ("Dates", "Hello everyone.\nQuiz today.", "Quiz today."),
    # the greeting is only the first words of a sentence that carries the content: that stays
    ("Homework for Tomorrow", "Hi all, since I was not able to hold class on Monday, our homework is the same as before.",
     "Since I was not able to hold class on Monday, our homework is the same as before."),
    ("WRIT 001L | Week 8: Reading", "WRIT 001L | Week 8 Reading\nGreetings All,\nPlease read chapter 3.", "Please read chapter 3."),
    ("WRIT 001L | Week 8: Reading", "Greetings All,\nWRIT 001L | Week 8: Reading\nPlease read chapter 3.", "Please read chapter 3."),
    ("Dates", "Hi", ""),
])
def test_the_greeting_and_a_repeated_title_are_skipped(title, text, expected):
    assert preview(title, text) == expected


@pytest.mark.parametrize("text", ["High scores were posted.", "Hi-C sequencing is due, so hurry.",
                                  "Hello is the first program you write, and it is due Friday."])
def test_text_that_only_starts_like_a_greeting_is_kept(text):
    """Three words at most between the greeting word and the comma, and the comma straight after them."""
    assert preview("Title", text) == text


def test_only_the_first_line_is_a_greeting_and_a_title_line_is_only_dropped_at_the_start():
    assert preview("T", "Hi all,\nHello team, the quiz is Friday.") == "Hello team, the quiz is Friday."
    assert preview("Quiz", "Read this.\nQuiz") == "Read this.\nQuiz"


def test_a_long_announcement_keeps_about_600_characters_and_is_cut_at_a_word():
    got = preview("T", LONG)
    assert PREVIEW_CHARS == 600 and 0.6 * 600 < len(got) <= 601 and got.endswith("…")
    assert LONG.startswith(got[:-1]) and not got[:-1].endswith(" ")          # a prefix of the body, no half word
    assert got[:-1].rsplit(" ", 1)[-1] in LONG.split()
    assert preview("T", LONG[:600]) == LONG[:600].strip()                      # exactly at the limit: nothing cut


def test_text_without_spaces_is_cut_at_the_limit():
    assert preview("T", "字" * 900) == "字" * 600 + "…"


# ---------------------------------------------------------------- on the page

def ann_page(build, message, title="Reminder", lang="zh"):
    return build(NOW, FakeCanvas(announcements=[announcement(5, 1001, title, message, NOW)]), lang=lang)


def preview_html(page):
    return re.search(r'<div class="text-secondary small mt-2 preview"[^>]*>(.*?)</div>', page.html, re.S).group(1)


def test_the_page_shows_the_body_not_the_greeting(build):
    page = ann_page(build, "<p>Hi everyone,</p><p>Reminder: bring your laptop to lab.</p>")
    assert preview_html(page) == "Reminder: bring your laptop to lab."


def test_the_page_carries_far_more_than_the_old_220_characters(build):
    shown = preview_html(ann_page(build, "<p>" + LONG + "</p>"))
    assert len(shown) > 550 and "Sentence number 9 " in shown and shown.endswith("…")       # the old cut was inside sentence 4
    assert len(shown) <= 601                                                                 # still a short page


def test_an_announcement_that_is_only_a_greeting_has_no_preview_box(build):
    assert 'class="text-secondary small mt-2 preview"' not in ann_page(build, "<p>Hi everyone,</p>").html


def test_the_cancel_flag_still_reads_the_start_of_the_original_text(build):
    """The class-cancelled warning looks at the first 220 characters of what was written, greeting included."""
    now = pt("2026-10-06 08:00")                      # Tuesday: DEMO 002A lecture
    msg = "<p>Hi everyone,</p><p>Sorry, class is cancelled today.</p>"
    page = build(now, FakeCanvas(announcements=[announcement(60, 1002, "Notice", msg, now)]))
    assert any("可能取消" in c for c in page.today_classes if "DEMO 002A" in c)


@needs_chrome
def test_tapping_the_preview_reveals_text_that_was_hidden(build, tmp_path):
    """Collapsed it is three lines of a longer text; open it is taller and nothing is cut."""
    page = ann_page(build, "<p>" + LONG + "</p>")
    probe = "({chars: p.textContent.length, shut: shut, open: p.clientHeight, cut: shut_scroll > shut})"
    steps = [(1200, "window.p = document.querySelector('#news .preview'); window.shut = p.clientHeight; window.shut_scroll = p.scrollHeight;"),
             (1300, "p.click();")]
    got = run_page(page, tmp_path, NOW, probe, steps, size=(390, 800))
    assert isinstance(got, dict), got
    assert got["cut"] is True                          # the text is longer than the three lines that show
    assert got["open"] > got["shut"] * 2, got          # and opening it shows it
    assert got["chars"] > 550
