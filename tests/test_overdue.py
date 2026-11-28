"""Overdue work says when it was due (the date, not just "Monday") and how long ago, in one unit: "overdue 53 days" /
"已逾期 53 天". The server writes it and the page script keeps it live, so the two must agree. 逾期的作业显示日期和逾期多久。"""
from __future__ import annotations

import re
from datetime import timedelta

import pytest
from conftest import FakeCanvas, item, pt
from purrfessor.i18n import T
from browser import PLAIN, needs_chrome, run_page

NOW = pt("2026-11-27 12:00")


def overdue_row(page):
    return re.search(r'<div class="list-group-item task[^"]*"[^>]*data-state="overdue".*?</div></div></div>', page.html, re.S).group(0)


def badge(row: str) -> str:
    return re.search(r'<span class="badge [^"]*\bcd">([^<]*)</span>', row).group(1)


@pytest.mark.parametrize("ago,zh,en", [
    (timedelta(days=53, hours=1), "已逾期 53 天", "overdue 53 days"),
    (timedelta(days=1, hours=3), "已逾期 1 天", "overdue 1 day"),
    (timedelta(days=2), "已逾期 2 天", "overdue 2 days"),
    (timedelta(hours=1, minutes=20), "已逾期 1 小时", "overdue 1 hour"),
    (timedelta(hours=5), "已逾期 5 小时", "overdue 5 hours"),
    (timedelta(minutes=12), "已逾期 12 分钟", "overdue 12 min"),
    (timedelta(seconds=5), "已逾期 1 分钟", "overdue 1 min"),
])
def test_overdue_by_uses_one_unit_and_the_english_plural(ago, zh, en):
    assert T("zh").overdue_by(-ago) == zh and T("en").overdue_by(-ago) == en
    assert T("en").countdown(-ago) == en                 # what the row's badge is built with


def test_an_overdue_row_shows_its_date_and_how_long_ago_in_both_languages(build):
    canvas = FakeCanvas(planner=[item(1, 1001, "Introduction Speech", pt("2026-10-05 11:00"), missing=True)])
    zh, en = build(NOW, canvas), build(NOW, canvas, lang="en")
    assert "10/5 周一 11:00" in overdue_row(zh) and badge(overdue_row(zh)) == "已逾期 53 天"
    assert "Mon 10/5 11:00" in overdue_row(en) and badge(overdue_row(en)) == "overdue 53 days"
    assert not re.search(r"[一-鿿]", overdue_row(en))


def test_the_script_has_the_same_words(build):
    page = build(NOW)
    assert page.data["i18n"]["overdueBy"] == "已逾期 {t}" and page.data["i18n"]["unitD"] == ["天", "天"]
    en = build(NOW, lang="en")
    assert en.data["i18n"]["overdueBy"] == "overdue {t}" and en.data["i18n"]["unitD"] == ["day", "days"]


@needs_chrome
@pytest.mark.parametrize("lang,first,later", [("zh", "已逾期 5 小时", "已逾期 1 天"), ("en", "overdue 5 hours", "overdue 1 day")])
def test_the_script_writes_the_same_badge_and_keeps_it_live(build, tmp_path, lang, first, later):
    """Opened at once the script's text equals the one the server wrote; a day later it has moved on to days."""
    due = NOW - timedelta(hours=5, minutes=10)
    page = build(NOW, FakeCanvas(planner=[item(1, 1001, "Essay", due)]), config=PLAIN, lang=lang)
    assert badge(overdue_row(page)) == first
    probe = "document.querySelector('.task[data-state=overdue] .cd').textContent"
    assert run_page(page, tmp_path, NOW, probe) == first
    assert run_page(page, tmp_path, NOW, probe, steps=[(1500, f"jump({20 * 3600 * 1000})")]) == later
