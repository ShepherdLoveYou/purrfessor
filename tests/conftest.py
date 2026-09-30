"""Test doubles — a fake Canvas, a fake Banner class search, no real AI — and a parser that turns a generated
page into something tests can assert on. Only fictional courses (TEST 101, DEMO 002A); no real timetable.
测试替身：假 Canvas、假选课系统、不调用真实 AI；以及把生成的页面解析成可断言的结构。全部是虚构课程。
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from purrfessor import agent as ag
from purrfessor import banner as bn
from purrfessor import build as bt

TZ = ZoneInfo("America/Los_Angeles")
UTC = timezone.utc


def pt(s: str) -> datetime:
    """'2026-10-02 23:59' → Pacific time"""
    return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)


def z(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- fake Canvas ----------

COURSES = [
    {"id": 1001, "course_code": "TEST_101_001_26F", "enrollments": [{"type": "student", "computed_current_score": 91.5}],
     "sections": [
        {"name": "TEST_101_001_26F - INTRO TESTING"}, {"name": "TEST_101_021_26F - INTRO TESTING"}]},
    {"id": 1002, "course_code": "DEMO_002A_010_26F", "enrollments": [{"type": "student", "computed_current_score": None}],
     "sections": [
        {"name": "DEMO_002A_010_26F - DEMO"}, {"name": "DEMO_002A_021_26F - DEMO"}]},
    {"id": 1003, "course_code": "Orientation 2026", "sections": []},   # not a real course: ignored
]
CODE = {c["id"]: c["course_code"] for c in COURSES}


def item(pid, cid, title, due: datetime, kind="assignment", submitted=False, missing=False, excused=False,
         marked=False, submittable=True, points=10):
    return {"plannable_id": pid, "plannable_type": kind, "course_id": cid,
            "context_name": f"{CODE[cid]} - COURSE", "plannable_date": z(due),
            "plannable": {"title": title, "points_possible": points},
            "submissions": ({"submitted": submitted, "missing": missing, "excused": excused, "graded": False}
                            if submittable else False),
            "planner_override": {"marked_complete": True} if marked else None,
            "html_url": f"/courses/{cid}/assignments/{pid}"}


def announcement(aid, cid, title, message, posted: datetime, unread=True):
    return {"id": aid, "title": title, "message": message, "posted_at": z(posted),
            "context_code": f"course_{cid}", "html_url": f"https://canvas.test/courses/{cid}/announcements/{aid}",
            "read_state": "unread" if unread else "read"}


@dataclass
class FakeCanvas:
    planner: list = field(default_factory=list)
    announcements: list = field(default_factory=list)
    fail: int | None = None          # e.g. 401: token expired
    submissions: dict = field(default_factory=dict)   # course id → submissions (grades)
    grades_fail: bool = False
    calls: list = field(default_factory=list)

    def get(self, path, params=None):
        params = params or {}
        self.calls.append((path, dict(params)))
        if self.fail:
            raise urllib.error.HTTPError(f"https://canvas.test/{path}", self.fail, "fail", {}, None)
        if path == "courses":
            return COURSES
        if path == "planner/items":
            lo, hi = date.fromisoformat(params["start_date"]), date.fromisoformat(params["end_date"])
            return [i for i in self.planner
                    if lo <= datetime.fromisoformat(i["plannable_date"].replace("Z", "+00:00")).date() <= hi]
        if path == "announcements":
            lo, hi = date.fromisoformat(params["start_date"]), date.fromisoformat(params["end_date"])
            codes = set(params["context_codes[]"])
            return [a for a in self.announcements if a["context_code"] in codes
                    and lo <= datetime.fromisoformat(a["posted_at"].replace("Z", "+00:00")).date() <= hi]
        if path.startswith("courses/") and path.endswith("/students/submissions"):
            if self.grades_fail:
                raise urllib.error.HTTPError(path, 403, "forbidden", {}, None)
            return self.submissions.get(int(path.split("/")[1]), [])
        if path.startswith("courses/") and "/assignments/" in path:
            return {"description": "<p>Write a 1500-word essay. <b>Rubric</b> attached.</p>"}
        raise AssertionError(f"unexpected Canvas path {path}")


# ---------- fake Banner (public class search response format) ----------

def meeting(days: str, begin: str | None, end: str | None, building="TSTB", desc="Test Building", room="101",
            start="09/24/2026", stop="12/04/2026", mtype="Class"):
    names = {"M": "monday", "T": "tuesday", "W": "wednesday", "R": "thursday", "F": "friday"}
    mt = {v: False for v in names.values()}
    mt.update({names[d]: True for d in days})
    mt.update(beginTime=begin, endTime=end, building=building, buildingDescription=desc, room=room,
              startDate=start, endDate=stop, meetingTypeDescription=mtype)
    return {"meetingTime": mt}


BANNER = {
    ("TEST", "101"): [
        {"courseNumber": "101", "sequenceNumber": "001", "scheduleTypeDescription": "Lecture",
         "faculty": [{"displayName": "Prof, Ada", "primaryIndicator": True}],
         "meetingsFaculty": [meeting("MWF", "1000", "1050")]},
        {"courseNumber": "101", "sequenceNumber": "021", "scheduleTypeDescription": "Discussion",
         "faculty": [{"displayName": "Assistant, Tee", "primaryIndicator": True}],
         "meetingsFaculty": [meeting("R", "1400", "1450", room="202")]},
        {"courseNumber": "101", "sequenceNumber": "022", "scheduleTypeDescription": "Discussion",   # not enrolled
         "faculty": [], "meetingsFaculty": [meeting("R", "1500", "1550")]},
    ],
    ("DEMO", "002A"): [
        {"courseNumber": "002A", "sequenceNumber": "010", "scheduleTypeDescription": "Lecture",
         "faculty": [{"displayName": "Lecturer, Bo", "primaryIndicator": True}],
         "meetingsFaculty": [meeting("TR", "1530", "1650", desc="Demo Hall", room="1020")]},
        {"courseNumber": "002A", "sequenceNumber": "021", "scheduleTypeDescription": "Laboratory",
         "faculty": [], "meetingsFaculty": [meeting("", None, None, building="ONLINE", desc="Online", room="ONLINE")]},
    ],
}


class FakeResp:
    def __init__(self, body: bytes):
        self.body = body

    def read(self):
        return self.body


class FakeOpener:
    def __init__(self, banner, fail=False):
        self.banner, self.fail = banner, fail

    def open(self, url, data=None, timeout=None):
        if self.fail:
            raise urllib.error.URLError("banner down")
        if "searchResults" in url:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            key = (q["txt_subject"][0], q["txt_courseNumber"][0])
            return FakeResp(json.dumps({"data": self.banner.get(key, [])}).encode())
        return FakeResp(b"{}")


# ---------- personal config ----------

CONFIG = """
preset = "ucr"
language = "{lang}"
name = "Tester"

[courses]
"1001" = "TEST 101"
"1002" = "DEMO 002A"

[[notes]]
course = "TEST 101"
kind = "discussion"
from = "2026-10-01"
note = "starts in week 1"

[[recurring]]
course = "DEMO 002A"
title = "Online homework"
platform = "HW"
weekday = "Fri"
due = "23:59"
from = "2026-10-02"
until = "2026-12-04"
url = "https://hw.test"
"""


# ---------- parse the generated page ----------

@dataclass
class Page:
    html: str
    data: dict
    states: dict          # task id → overdue / soon / later / done
    stats: dict           # stat card label → number
    warnings: list
    today_classes: list   # ["TEST 101 Lecture", ...]
    tomorrow: str
    announcements: list   # announcement titles
    week: str

    def state(self, tid):
        return self.states.get(tid)

    def section(self, sid: str) -> str:
        return self.html.split(f'id="{sid}"')[1].split("</section>")[0] if f'id="{sid}"' in self.html else ""


def text(x: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x)).strip()


def parse(html: str) -> Page:
    data = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S)
                      .group(1).replace("<\\/", "</"))
    states = {}
    for m in re.finditer(r'data-id="([^"]+)" data-state="([^"]*)"', html):
        assert m.group(1) not in states, f"task {m.group(1)} is on the page more than once"
        states[m.group(1)] = m.group(2)
    stats = {m.group(2): int(m.group(1)) for m in re.finditer(
        r'<div class="h1 mb-0 lh-1">(\d+)</div><div class="text-secondary small">([^<]+)</div>', html)}
    warnings = [text(m.group(1)) for m in re.finditer(r'<div class="alert alert-warning mt-3 mb-0"[^>]*>(.*?)</div>', html)]
    today = html[html.index('id="today"'):html.index('id="todo"')]
    today_classes = [text(m.group(1)) for m in re.finditer(
        r'<div class="col min-w-0"><div class="fw-medium">(.*?)</div>', today)]
    tomorrow = text(re.search(r'<i class="ti ti-arrow-right"></i> (.*?)</div>', today).group(1))
    news = html[html.index('id="news"'):] if 'id="news"' in html else ""
    anns = [text(m.group(1)) for m in re.finditer(r'<div class="fw-medium"><a[^>]*>(.*?)</a>', news)]
    week = re.search(r"Week (\d+) / (\d+)", html).group(0)
    return Page(html, data, states, stats, warnings, today_classes, tomorrow, anns, week)


@pytest.fixture
def build(monkeypatch, tmp_path):
    """build(now, canvas=None, ai=None, banner=None, config=CONFIG, lang="zh", ...) → Page"""
    def run(now: datetime, canvas: FakeCanvas | None = None, ai=None, banner=None, config: str | None = CONFIG,
            lang: str = "zh", banner_fail=False, token=True, model=None, prev: Page | None = None, archive=None,
            home_url: str = "") -> Page:
        canvas = canvas or FakeCanvas()
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)          # tests never call a real model
        monkeypatch.setattr(ag, "default_model", lambda: model)
        monkeypatch.setattr(bt, "make_canvas", lambda S: canvas)
        monkeypatch.setattr(bn, "opener", lambda: FakeOpener(BANNER if banner is None else banner, banner_fail))
        monkeypatch.setattr(bt, "enrich", (lambda *a: ai(*a)) if callable(ai) else (lambda *a: ai))
        if token:
            monkeypatch.setenv("CANVAS_TOKEN", "test")
        else:
            monkeypatch.delenv("CANVAS_TOKEN", raising=False)
        cfg = tmp_path / "purrfessor.toml"
        if config is None:
            cfg = tmp_path / "missing.toml"
        else:
            cfg.write_text(config.replace("{lang}", lang), encoding="utf-8")
        out = tmp_path / "out.html"
        argv = ["--out", str(out), "--config", str(cfg), "--now", now.isoformat()]
        if home_url:
            argv += ["--home-url", home_url]
        if prev is not None:
            (tmp_path / "prev.html").write_text(prev.html, encoding="utf-8")
            argv += ["--prev", str(tmp_path / "prev.html")]
        if archive is not None:
            (tmp_path / "archive.json").write_text(json.dumps({"dates": archive}), encoding="utf-8")
            argv += ["--archive-dates", str(tmp_path / "archive.json")]
        bt.main(argv)
        return parse(out.read_text(encoding="utf-8"))
    return run
