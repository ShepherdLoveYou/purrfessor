"""Canvas LMS (read-only): assignments, announcements, grades, assignment details.
Canvas（只读）：作业、公告、成绩、作业说明。Works with any school's Canvas. 任何学校的 Canvas 都适用。
"""
from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta
from typing import Callable

from .model import Task, parse_iso

Get = Callable[..., object]


class Canvas:
    def __init__(self, base_url: str, token: str):
        self.base, self.token = base_url.rstrip("/"), token

    def get(self, path: str, params: dict | None = None):
        """GET /api/v1/<path>; list results are paginated automatically."""
        url = f"{self.base}/api/v1/{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        headers = {"Authorization": f"Bearer {self.token}"}
        out: list = []
        while url:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as resp:
                data = json.load(resp)
                link = resp.headers.get("Link", "")
            if not isinstance(data, list):
                return data
            out += data
            m = re.search(r'<([^>]+)>; rel="next"', link)
            url = m.group(1) if m else None
        return out


def course_label(code: str) -> str:
    """'CS_005_002_26F - INTRO…' → 'CS 005'"""
    m = re.match(r"([A-Z]+)_(\w+?)_\d+_", code or "")
    return f"{m[1]} {m[2]}" if m else (code or "").split(" - ")[0]


def strip_html(h: str) -> str:
    t = re.sub(r"<(br|/p|/li|/h\d|/div|/tr)[^>]*>|<li[^>]*>", "\n", h or "")
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"[ \t\xa0]+", " ", re.sub(r"\n\s*\n+", "\n", t)).strip()


# ---------------------------------------------------------------- assignments

def tasks(get: Get, now: datetime, names: dict, tz, base_url: str) -> list[Task]:
    items = get("planner/items", {
        "start_date": (now - timedelta(days=120)).date().isoformat(),   # keep long-overdue work
        "end_date": (now + timedelta(days=60)).date().isoformat(),
        "per_page": 100,
    })
    out = []
    for it in items:
        p = it.get("plannable") or {}
        kind = it.get("plannable_type")
        when = parse_iso(it.get("plannable_date"), tz)
        if kind == "announcement" or when is None:
            continue
        if not isinstance(it.get("submissions"), dict) and when < now:
            continue      # nothing to submit on Canvas (paper work, readings): drop once it's past
        subs = it["submissions"] if isinstance(it.get("submissions"), dict) else {}
        override = it.get("planner_override") or {}
        out.append(Task(
            id=f"canvas-{kind}-{it.get('plannable_id')}", title=p.get("title") or p.get("name") or "(untitled)",
            course=names.get(it.get("course_id")) or course_label(it.get("context_name", "")), due=when,
            url=urllib.parse.urljoin(base_url, it.get("html_url") or ""), source="Canvas", kind=kind,
            points=p.get("points_possible"),
            done=bool(subs.get("submitted") or subs.get("excused") or override.get("marked_complete"))))
    return out


def details(get: Get, task: Task) -> str:
    """Assignment / quiz / discussion description, as plain text (for the agent's read-only tool)."""
    m = re.search(r"/courses/(\d+)/(assignments|quizzes|discussion_topics)/(\d+)", task.url or "")
    if not m or task.source != "Canvas":
        return task.note or "(not on Canvas — no details)"
    data = get(f"courses/{m[1]}/{m[2]}/{m[3]}")
    return strip_html(data.get("description") or data.get("message") or "") if isinstance(data, dict) else ""


# ---------------------------------------------------------------- announcements

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
DATE_RE = re.compile(
    r"\b(?:(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(?P<d1>\d{1,2})(?:st|nd|rd|th)?\b"
    r"|(?P<m2>1[0-2]|0?[1-9])/(?P<d2>3[01]|[12]\d|0?[1-9])(?:/\d{2,4})?(?![\d/]))", re.I)
TIME_RE = re.compile(r"\b(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*([ap])\.?m\b", re.I)
DEADLINE_WORDS = re.compile(r"\bdue\b|deadline|\bby\b|submit|complete|before|\bclose|\bexam|\bquiz|midterm|\bfinal", re.I)


def nearest_date(month: int, day: int, now: datetime) -> date | None:
    """Announcements rarely give the year: pick the one closest to now."""
    for y in (now.year, now.year + 1, now.year - 1):
        try:
            d = date(y, month, day)
        except ValueError:
            continue
        if now.date() - timedelta(days=120) <= d <= now.date() + timedelta(days=240):
            return d
    return None


def deadline_mentions(text: str, now: datetime, tz) -> list[dict]:
    """Rule-based fallback: sentences with a deadline word and a date → {due, what:'', quote}. 23:59 if no time."""
    found = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
        if not DEADLINE_WORDS.search(sentence):
            continue
        for m in DATE_RE.finditer(sentence):
            month = MONTHS.index(m["mon"][:3].lower()) + 1 if m["mon"] else int(m["m2"])
            d = nearest_date(month, int(m["d1"] or m["d2"]), now)
            if not d:
                continue
            t = TIME_RE.search(sentence)
            at = time(int(t[1]) % 12 + (12 if t[3].lower() == "p" else 0), int(t[2] or 0)) if t else time(23, 59)
            found.append({"due": datetime.combine(d, at, tz), "what": "", "quote": sentence.strip()[:200]})
    return found


def announcements(get: Get, now: datetime, names: dict, courses: list[dict], tz) -> list[dict]:
    anns = get("announcements", {
        "context_codes[]": [f"course_{c['id']}" for c in courses],
        "start_date": (now - timedelta(days=14)).date().isoformat(),
        "end_date": (now + timedelta(days=1)).date().isoformat(),
        "per_page": 50,
    })
    code = {c["id"]: c.get("course_code", "") for c in courses}
    out = []
    for a in anns:
        cid = int(str(a.get("context_code", "_0")).split("_")[-1])
        text = strip_html(a.get("message", ""))
        out.append({"id": a["id"], "title": a.get("title", ""), "url": a.get("html_url", ""),
                    "course": names.get(cid) or course_label(code.get(cid, "")),
                    "when": parse_iso(a.get("posted_at"), tz), "unread": a.get("read_state") == "unread",
                    "preview": text[:220] + ("…" if len(text) > 220 else ""), "text": text,
                    "mentions": deadline_mentions(text, now, tz)})
    return sorted(out, key=lambda a: a["when"], reverse=True)


def announcement_tasks(anns: list[dict], canvas_tasks: list[Task], now: datetime, t) -> list[Task]:
    """Deadlines mentioned in announcements (next 30 days) become to-dos, unless the same course already
    has a Canvas task that day."""
    taken = {(x.course, x.due.date()) for x in canvas_tasks}
    out, seen = [], set()
    for a in anns:
        for m in a["mentions"]:
            due, key = m["due"], (a["course"], m["due"].date())
            if not now <= due <= now + timedelta(days=30) or key in taken or key in seen:
                continue
            seen.add(key)
            note_key = "ann_note_ai" if m["what"] else "ann_note_rule"
            out.append(Task(id=f"ann-{a['id']}-{due:%m%d}", title=m["what"] or t("from_announcement", title=a["title"]),
                            course=a["course"], due=due, url=a["url"], source="announcement", kind="announcement",
                            note=t(note_key, quote=m["quote"]), ai_note=bool(m["what"])))
    return out


# ---------------------------------------------------------------- grades

def grades(get: Get, courses: list[dict], names: dict, section_pattern: re.Pattern) -> list[dict]:
    """Per course: current grade (often hidden by instructors), unweighted rate on graded work,
    missing and late counts. Lecture + discussion Canvas courses are merged by display name."""
    rows = []
    for c in courses:
        if not section_pattern.match(c.get("course_code", "")):
            continue                               # skip orientation / non-course sites
        enr = next((e for e in c.get("enrollments") or [] if e.get("type") == "student"), {})
        subs = get(f"courses/{c['id']}/students/submissions",
                   {"student_ids[]": "self", "include[]": "assignment", "per_page": 100})
        graded = [s for s in subs if s.get("score") is not None and (s.get("assignment") or {}).get("points_possible")
                  and not (s.get("assignment") or {}).get("omit_from_final_grade")]
        rows.append({"course": names.get(c["id"]) or course_label(c.get("course_code", "")),
                     "current": enr.get("computed_current_score"), "graded": len(graded),
                     "earned": sum(s["score"] for s in graded),
                     "possible": sum(s["assignment"]["points_possible"] for s in graded),
                     "missing": sum(bool(s.get("missing")) for s in subs),
                     "late": sum(bool(s.get("late")) for s in subs)})
    merged: dict[str, dict] = {}
    for g in rows:
        m = merged.setdefault(g["course"], {**g, "graded": 0, "earned": 0, "possible": 0, "missing": 0, "late": 0})
        for k in ("graded", "earned", "possible", "missing", "late"):
            m[k] += g[k]
        m["current"] = m["current"] if m["current"] is not None else g["current"]
    for m in merged.values():
        m["earned"], m["possible"] = round(m["earned"], 2), round(m["possible"], 2)
        m["rate"] = round(m["earned"] / m["possible"] * 100, 1) if m["possible"] else None
    return sorted(merged.values(), key=lambda g: g["course"])
