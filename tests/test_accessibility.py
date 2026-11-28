"""Accessibility contracts: a name for every tick box, one h1 and labelled sections, progress bars with values, live
counters that are not rewritten every second, keyboard-operable previews, calm motion. 无障碍：打勾框有名字、一个 h1、
区块有标签、进度条有数值、计数器是 live 区域但不会每秒重写、预览可用键盘操作、减少动态效果。"""
from __future__ import annotations

import re
from datetime import timedelta

import pytest
from browser import PLAIN, needs_chrome, run_page
from conftest import FakeCanvas, announcement, item, pt
from purrfessor.render import TEMPLATE

CSS = TEMPLATE.read_text(encoding="utf-8")
NOW = pt("2026-10-09 12:00")
CJK = re.compile(r"[一-鿿]")


def canvas():
    return FakeCanvas(planner=[item(1, 1001, 'Essay "A" & <B>', pt("2026-10-10 23:59")), item(2, 1001, "Quiz 2", pt("2026-10-11 23:59"))],
                      announcements=[announcement(5, 1001, "Notice", "<p>Bring your laptop to the lab on Friday, please.</p>", NOW)],
                      submissions={1001: [{"score": 9, "missing": False, "late": False, "assignment": {"points_possible": 10}}]})


@pytest.mark.parametrize("lang,prefix,end", [("zh", "标记为已完成：", "截止"), ("en", "Mark as done: ", "")])
def test_every_tick_box_names_its_task(build, lang, prefix, end):
    """The name carries the title, the course and the due date: the weekly homework is one title every week, and two
    courses can each have a "Quiz 2" due at the same minute. Run on the default config, which has the weekly homework."""
    cv = canvas()
    cv.planner.append(item(3, 1002, "Quiz 2", pt("2026-10-11 23:59")))      # the same title and time as assignment 2, another course
    page = build(NOW, cv, lang=lang)
    labels = re.findall(r'<input class="form-check-input m-0 tick" type="checkbox" data-key="([^"]+)" aria-label="([^"]*)">', page.html)
    assert len(labels) >= 6 and len({label for _, label in labels}) == len(labels)      # no two boxes read the same
    by_key = dict(labels)
    homework = [label for key, label in labels if key.startswith("HW-DEMO")]
    assert len(homework) == 3 and all("Online homework" in label for label in homework)   # three weeks, one title, three names
    essay, quiz_a, quiz_b = (by_key[f"canvas-assignment-{n}"] for n in (1, 2, 3))
    assert essay.startswith(f"{prefix}Essay &quot;A&quot; &amp; &lt;B&gt;")                  # escaped, and the title is in it
    assert "TEST 101" in essay and "TEST 101" in quiz_a and "DEMO 002A" in quiz_b and quiz_a != quiz_b
    assert ("10/10 周六 23:59" if lang == "zh" else "Sat 10/10 23:59") in essay and essay.endswith(end)
    if lang == "en":
        assert not CJK.search(" ".join(by_key.values()))


def test_one_h1_then_h2_sections_each_labelled_by_its_heading(build):
    page = build(NOW, canvas())
    assert re.findall(r"<h[1-6][ >]", page.html) == ["<h1 "] + ["<h2 "] * 5            # todo, today, grades, timetable, news
    sections = re.findall(r'<section id="(\w+)" class="card" aria-labelledby="(\w+-title)">', page.html)
    assert [sid for sid, _ in sections] == ["todo", "today", "grades", "timetable", "news"]
    for sid, labelled in sections:
        assert labelled == f"{sid}-title"
        assert re.search(rf'<h2 class="card-title" id="{labelled}">', page.html), sid


def test_the_brief_and_changes_sections_are_labelled_too(build):
    from purrfessor import agent
    page = build(NOW, canvas())
    assert 'aria-labelledby="brief-title"' not in page.html                       # no brief without the AI: nothing to label
    prev = build(NOW - timedelta(hours=6), FakeCanvas(planner=[item(2, 1001, "Quiz 2", pt("2026-10-11 23:59"))]))
    changed = build(NOW, canvas(), prev=prev)
    assert 'id="changes"' in changed.html and 'aria-labelledby="changes-title"' in changed.html
    assert '<h2 class="card-title" id="changes-title">' in changed.html and agent is not None


def test_every_progress_bar_is_a_progressbar_with_a_value_and_a_name(build):
    page = build(NOW, canvas())
    bars = re.findall(r'<div class="progress progress-sm[^"]*" ([^>]*)>', page.html)
    assert len(bars) == 3                                                            # the term, the year, one graded course
    for attrs in bars:
        assert 'role="progressbar"' in attrs and 'aria-valuemin="0"' in attrs and 'aria-valuemax="100"' in attrs, attrs
        assert re.search(r'aria-valuenow="[\d.]+"', attrs) and re.search(r'aria-label="[^"]+"', attrs), attrs
    assert re.search(r'aria-label="学期进度：第 2 周，共 10 周" aria-valuenow="\d+"', page.html)
    assert re.search(r'aria-label="全年进度" aria-valuenow="7\d\.\d"', page.html)                 # 9 October: 78 percent of 2026


def test_english_progress_labels_have_no_chinese(build):
    page = build(NOW, canvas(), lang="en")
    assert 'aria-label="Term progress: week 2 of 10"' in page.html and 'aria-label="Year progress"' in page.html
    assert not CJK.search(re.sub(r"喵教授", "", " ".join(re.findall(r'aria-label="([^"]*)"', page.html))))


def test_only_the_three_stat_counters_are_live_regions_not_the_timers(build):
    """The counters change when a task is ticked or a time passes; the countdowns change every second and must stay silent."""
    page = build(NOW, canvas())
    live = re.findall(r'<[^>]*aria-live="([^"]*)"[^>]*>', page.html)
    assert live == ["polite"] * 3
    for key in ("overdue", "due_today", "due_3d"):
        assert f'data-stat="{key}" aria-live="polite" aria-atomic="true"' in page.html
    assert page.html.count("aria-live") == 3
    timer = re.search(r'<span class="badge [^"]*\bcd">', page.html).group(0)
    assert "aria-live" not in timer and 'aria-live' not in re.search(r'<div class="h1 my-2 next-big">', page.html).group(0)


def test_a_preview_is_not_a_button_until_the_page_finds_it_cut_off(build):
    """Whether the clamp cuts anything off depends on the screen, so the server cannot say: the script adds the button."""
    news = build(NOW, canvas()).section("news")
    assert re.search(r'<div class="text-secondary small mt-2 preview">Bring your laptop', news)
    assert not re.search(r'class="[^"]*preview[^"]*"[^>]*(tabindex|role|aria-expanded)', build(NOW, canvas()).html)


NOTES = ("(function () { return [].map.call(document.querySelectorAll('#news .preview'), function (p) {"
         " return {start: p.textContent.slice(0, 6), tabindex: p.getAttribute('tabindex'), role: p.getAttribute('role'),"
         " expanded: p.getAttribute('aria-expanded'), cut: p.classList.contains('cut')}; }); })()")
LONG_TEXT = "Please read the syllabus again. " * 8                     # 250 characters: about five lines on a phone, two on a desk
SHORT = {"start": "Bring ", "tabindex": None, "role": None, "expanded": None, "cut": False}
BUTTON = {"start": "Please", "tabindex": "0", "role": "button", "expanded": "false", "cut": True}


def two_notes():
    return FakeCanvas(announcements=[announcement(5, 1001, "Short", "<p>Bring your laptop to the lab, please.</p>", NOW),
                                     announcement(6, 1001, "Long", f"<p>{LONG_TEXT}</p>", NOW - timedelta(hours=1))])


@needs_chrome
def test_only_the_note_that_is_cut_off_is_a_tab_stop_with_a_button_role(build, tmp_path):
    """Before, every note was: 13 tab stops on the real page, 4 of them with nothing more to show, each named by its whole paragraph."""
    page = build(NOW, two_notes(), config=PLAIN)
    assert run_page(page, tmp_path, NOW, NOTES, size=(390, 900)) == [SHORT, BUTTON]
    assert run_page(page, tmp_path, NOW, NOTES, size=(1400, 900)) == [SHORT, {**SHORT, "start": "Please"}]       # on a desk nothing is cut


@needs_chrome
def test_a_note_becomes_a_button_when_the_window_gets_narrower_and_stops_when_it_gets_wider(build, tmp_path):
    page = build(NOW, two_notes(), config=PLAIN)
    # (headless Chrome with a pretended clock paints no frames, so it never sends the resize event itself: send it)
    frame = "window.parent.document.getElementById('f').style.width = '%dpx'; window.dispatchEvent(new Event('resize'));"
    steps = [(1200, "window.log = []; window.snap = function () { log.push(%s[1]); };" % NOTES),
             (1300, "snap();"), (1400, frame % 1400), (1700, "snap();"), (1800, frame % 390), (2100, "snap();")]
    narrow, wide, narrow_again = run_page(page, tmp_path, NOW, "log", steps, size=(390, 900))
    assert narrow == BUTTON and wide == {**SHORT, "start": "Please"} and narrow_again == BUTTON


@needs_chrome
def test_an_open_note_stays_a_button_so_that_it_can_be_closed(build, tmp_path):
    page = build(NOW, two_notes(), config=PLAIN)
    steps = [(1200, "window.log = []; window.snap = function () { log.push(%s[1]); };" % NOTES),
             (1300, "document.querySelectorAll('#news .preview')[1].click(); snap();"), (1400, "snap();")]
    opened, still = run_page(page, tmp_path, NOW, "log", steps, size=(390, 900))
    assert opened == still == {**BUTTON, "expanded": "true"}


@needs_chrome
def test_a_note_in_a_closed_details_is_looked_at_again_when_it_is_opened(build, tmp_path):
    """The "later" list is a closed <details>. Chrome measures what is inside it, other browsers may report no size at
    load: undo what the script decided at load (as such a browser would have left it), open it, and the note is a button."""
    quote = "Hi all, the final survey is due 10/30, " + "and please read the syllabus again " * 8 + "thanks."      # one long sentence: the whole quote
    page = build(NOW, FakeCanvas(announcements=[announcement(7, 1001, "Dates", f"<p>{quote}</p>", NOW)]), config=PLAIN)
    note = "document.querySelector('#todo details .preview')"
    state = f"({{tabindex: {note}.getAttribute('tabindex'), role: {note}.getAttribute('role'), cut: {note}.classList.contains('cut')}})"
    undo = f"{note}.classList.remove('cut'); ['tabindex', 'role', 'aria-expanded'].forEach(function (a) {{ {note}.removeAttribute(a); }});"
    steps = [(1200, f"window.log = []; {undo} log.push({state}); {note}.closest('details').open = true;"), (1600, f"log.push({state});")]
    undone, opened = run_page(page, tmp_path, NOW, "log", steps, size=(390, 900))
    assert undone == {"tabindex": None, "role": None, "cut": False} and opened == {"tabindex": "0", "role": "button", "cut": True}


def test_decorative_status_dots_are_hidden_from_screen_readers(build):
    page = build(NOW, canvas())
    dots = re.findall(r'<span class="status-dot[^>]*>', page.html)
    assert dots and all('aria-hidden="true"' in d for d in dots)


def test_motion_and_focus_rules_are_in_the_stylesheet():
    assert "@media (prefers-reduced-motion: reduce) { .status-dot-animated::before { animation: none !important; } }" in CSS
    assert ".tick:focus-visible { outline: 2px solid var(--ring); outline-offset: 3px; }" in CSS
    assert ".preview:focus-visible { outline: 2px solid var(--ring);" in CSS


# ---------------------------------------------------------------- the script

@needs_chrome
def test_a_counter_is_only_rewritten_when_its_number_changes(build, tmp_path):
    """The counters are live regions: assigning the same text every second would be announced every second."""
    page = build(NOW, FakeCanvas(planner=[item(1, 1001, "Quiz", NOW + timedelta(hours=2))]), config=PLAIN)
    watch = ("window.hits = {}; document.querySelectorAll('[data-stat]').forEach(function (el) { hits[el.dataset.stat] = 0; "
             "new MutationObserver(function (m) { hits[el.dataset.stat] += m.length; }).observe(el, {childList: true, characterData: true, subtree: true}); });")
    probe = "({hits: hits, text: [].map.call(document.querySelectorAll('[data-stat]'), function (e) { return e.dataset.stat + '=' + e.textContent; })})"
    quiet = run_page(page, tmp_path, NOW, probe, [(1100, watch)])
    assert quiet["hits"] == {"overdue": 0, "due_today": 0, "due_3d": 0}, quiet       # five ticks went by, nothing was rewritten
    assert sorted(quiet["text"]) == ["due_3d=1", "due_today=1", "overdue=0"]


@needs_chrome
def test_the_year_progress_bar_value_follows_the_clock(build, tmp_path):
    """The page was built in October but opened on 1 July: the bar and its aria-valuenow say about half a year."""
    page = build(NOW, canvas())
    got = run_page(page, tmp_path, pt("2026-07-02 12:00"),
                   "document.querySelector('.meme-bar').parentNode.getAttribute('aria-valuenow') + '|' + document.querySelector('.meme-bar').style.width")
    value, width = got.split("|")
    assert 49.0 <= float(value) <= 50.5 and abs(float(value) - float(width.rstrip("%"))) < 0.1
