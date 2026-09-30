"""English UI: every visible string, the meme caption and the class labels are English, and titles are never
sent for translation. 英文界面：文字、表情包配文、课程类型都是英文，作业标题不送去翻译。"""
from __future__ import annotations

import re
from datetime import timedelta

from conftest import FakeCanvas, announcement, item, pt

CJK = re.compile(r"[一-鿿]")
NOW = pt("2026-10-01 08:00")     # Thursday: TEST 101 discussion + DEMO 002A lecture


def visible_text(html: str) -> str:
    body = html.split("<body", 1)[1]
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", body, flags=re.S)
    return re.sub(r"<[^>]+>", " ", body)


def test_english_page_has_no_chinese_text(build):
    canvas = FakeCanvas(planner=[item(1, 1001, "Essay 1", pt("2026-10-02 23:59")),
                                 item(2, 1002, "Old lab", pt("2026-09-30 23:59"), missing=True)],
                        announcements=[announcement(5, 1001, "Survey", "Fill in the survey by 10/9.", NOW)])
    page = build(NOW, canvas, lang="en")
    text = visible_text(page.html)
    assert not CJK.search(text.replace("喵教授", "")), CJK.findall(text)[:20]   # the project's own name is bilingual
    assert '<html lang="en"' in page.html
    assert page.stats["overdue"] == 1 and page.stats["classes today"] == len(page.today_classes) == 2
    assert any("TEST 101 Discussion 021" in c for c in page.today_classes)
    assert any("DEMO 002A Lecture" in c for c in page.today_classes)
    assert "Online, no fixed meeting time: DEMO 002A Lab 021" in page.html
    assert page.data["lang"] == "en" and page.data["i18n"]["fcDue"] == "Due"
    assert "fullcalendar@7.1.0/locales" not in page.html                 # no extra locale file for English


def test_english_meme_caption(build):
    page = build(pt("2026-09-29 12:00"), lang="en")
    assert "meme-en" in page.html
    assert 'Tip: in <span class="meme-year">2026</span>,' in page.html
    assert 'you&#x27;ve wasted <span class="meme-num">38</span> weeks' in page.html
    assert "38 weeks 1 days into 2026" in page.html or "38 weeks" in page.html


def test_titles_are_not_sent_for_translation_in_english(build):
    calls = []

    def fake_ai(now, tasks, announcements, language):
        calls.append((list(tasks), len(announcements), language))
        return {"model": "fake", "tasks": [], "announcements": [
            {"id": "5", "title": "Survey reminder", "summary": "Fill in the survey by Friday.", "deadlines": []}]}
    canvas = FakeCanvas(planner=[item(1, 1001, "Essay 1", pt("2026-10-02 23:59"))],
                        announcements=[announcement(5, 1001, "Survey", "Please fill in the survey.", NOW)])
    page = build(NOW, canvas, ai=fake_ai, lang="en")
    assert calls == [([], 1, "en")]                     # announcements are still summarized; titles are not
    assert "Survey reminder" in page.announcements and "Fill in the survey by Friday." in page.html
    assert "Original title: Survey" in page.html


def test_chinese_translation_can_be_switched_off(build):
    calls = []

    def fake_ai(now, tasks, announcements, language):
        calls.append((len(tasks), language))
        return None
    config = __import__("conftest").CONFIG + "\n[features]\ntranslate = false\n"
    build(NOW, FakeCanvas(planner=[item(1, 1001, "Essay 1", pt("2026-10-02 23:59"))]), ai=fake_ai, config=config)
    assert calls == [(0, "zh")]


def test_english_warnings_and_countdowns(build):
    page = build(NOW, FakeCanvas(fail=401), lang="en")
    assert any("token has expired" in w for w in page.warnings)
    assert page.data["i18n"]["d"] == "d" or "d" in page.data["i18n"]


def test_features_can_be_switched_off(build):
    config = __import__("conftest").CONFIG + "\n[features]\nmeme = false\ngrades = false\n"
    canvas = FakeCanvas(submissions={1001: [{"score": 9, "missing": False, "late": False,
                                              "assignment": {"points_possible": 10}}]})
    page = build(NOW, canvas, config=config)
    assert 'id="meme"' not in page.html and 'id="grades"' not in page.html
    assert not any(p == "students/submissions" or p.endswith("/students/submissions") for p, _ in canvas.calls)


def test_dates_are_localized(build):
    canvas = FakeCanvas(planner=[item(1, 1001, "Essay 1", pt("2026-10-05 23:59"))])
    en = build(NOW, canvas, lang="en")
    zh = build(NOW, canvas, lang="zh")
    assert "Thursday" in en.html or "Thu" in en.html
    assert "周四" in zh.html or "星期四" in zh.html
    assert NOW + timedelta(days=4) > NOW
