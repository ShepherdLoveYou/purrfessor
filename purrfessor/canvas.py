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
Fetched = list[tuple[dict, list[dict]]]       # (course, its students/submissions): see submissions()


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

def assignment_id(kind: str | None, plannable_id, plannable: dict) -> int | None:
    """The Canvas assignment behind a planner item: itself, or (quizzes, graded discussions) the one it links to."""
    try:
        return int(plannable_id if kind == "assignment" else plannable.get("assignment_id"))
    except (TypeError, ValueError):
        return None


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
        submittable = isinstance(it.get("submissions"), dict)       # else a reading or other item nobody hands in
        subs = it["submissions"] if submittable else {}
        override = it.get("planner_override") or {}
        # a grade the teacher has not posted yet is not visible to the student: not "graded" either
        graded = bool(subs.get("graded") and not subs.get("excused") and subs.get("posted_at", True))
        out.append(Task(
            id=f"canvas-{kind}-{it.get('plannable_id')}", title=p.get("title") or p.get("name") or "(untitled)",
            course=names.get(it.get("course_id")) or course_label(it.get("context_name", "")), due=when,
            url=urllib.parse.urljoin(base_url, it.get("html_url") or ""), source="Canvas", kind=kind,
            points=p.get("points_possible"), aid=assignment_id(kind, it.get("plannable_id"), p), graded=graded,
            feedback=bool(subs.get("has_feedback")),
            submittable=submittable, lock_at=parse_iso(p.get("lock_at"), tz) if submittable else None,
            # graded without a submission (in-class work, grades the teacher typed in) is finished too, unless Canvas
            # also flags it missing
            done=bool(subs.get("submitted") or subs.get("excused") or override.get("marked_complete")
                      or (subs.get("graded") and not subs.get("missing")))))
    return out


def details(get: Get, task: Task) -> str:
    """Assignment / quiz / discussion description, as plain text (for the agent's read-only tool)."""
    m = re.search(r"/courses/(\d+)/(assignments|quizzes|discussion_topics)/(\d+)", task.url or "")
    if not m or task.source != "Canvas":
        return task.note or "(not on Canvas — no details)"
    data = get(f"courses/{m[1]}/{m[2]}/{m[3]}")
    return strip_html(data.get("description") or data.get("message") or "") if isinstance(data, dict) else ""


def attach_submissions(tasks: list[Task], fetched: Fetched, tz, scores: bool = True) -> None:
    """Add what only the students/submissions data has: the points earned on graded work, and the lock time of items whose
    planner entry has none (work with an override due date; items nobody can hand in get no lock). It is the data
    grades() already fetched (matched by assignment id), so no request per item. Items without a match stay as they are."""
    by_aid = {}
    for _, subs in fetched:
        for s in subs:
            aid = s.get("assignment_id") or (s.get("assignment") or {}).get("id")
            if aid is not None:
                by_aid[aid] = s
    for task in tasks:
        s = by_aid.get(task.aid)
        if s is None:
            continue
        if scores and task.graded and isinstance(s.get("score"), (int, float)):
            task.score = float(s["score"])
        if task.lock_at is None and task.submittable:
            task.lock_at = parse_iso((s.get("assignment") or {}).get("lock_at"), tz)


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


# ---------------------------------------------------------------- submissions: grades, scores, unscheduled work

def submissions(get: Get, courses: list[dict], section_pattern: re.Pattern | None = None) -> Fetched:
    """The student's submission records (with the assignment info) of every real course: one request per course.
    Grades, scores, lock times and work without a due date all read this, so nothing is fetched twice.
    A school preset can tell real courses from other sites by their course code (`section_pattern`); without one
    (any other school) every course I am a student in counts. Nothing here assumes a school's code format.
    每门课取一次提交记录（带作业信息），成绩、分数、锁定时间、没有截止日期的作业都从这里读。
    学校预设可以用课号格式区分真正的课程；没有时（别的学校）就取所有我是学生的课程。"""
    out = []
    for c in courses:
        if section_pattern is not None:
            if not section_pattern.match(c.get("course_code", "")):
                continue                           # skip orientation / non-course sites
        elif not any(e.get("type") == "student" for e in c.get("enrollments") or []):
            continue                               # a site where I am a teacher, an observer or nothing
        out.append((c, get(f"courses/{c['id']}/students/submissions",
                           {"student_ids[]": "self", "include[]": "assignment", "per_page": 100})))
    return out


def grades(fetched: Fetched, names: dict) -> list[dict]:
    """Per course: current grade (often hidden by instructors), unweighted rate on graded work,
    missing and late counts. Lecture + discussion Canvas courses are merged by display name."""
    rows = []
    for c, subs in fetched:
        enr = next((e for e in c.get("enrollments") or [] if e.get("type") == "student"), {})
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


def handed_in(s: dict) -> bool:
    """A submission record that is submitted, graded or excused (Canvas workflow_state, with the plain fields as backup)."""
    return bool(s.get("excused") or s.get("submitted_at") or s.get("graded_at") or s.get("score") is not None
                or s.get("workflow_state") in ("submitted", "graded", "pending_review"))


def undated(fetched: Fetched, names: dict, now: datetime, tz, base_url: str, min_points: float = 25,
            known: frozenset | set = frozenset()) -> list[dict]:
    """Published work worth `min_points` or more that has no due date and nothing handed in yet: the planner only
    lists dated items, so the biggest project or exam of the term can be missing from the page. Biggest first.
    Work that is excused, graded, locked, unpublished or kept out of the final grade is left out; so is anything
    already on the page (`known` assignment ids). A date in the description is only a hint ("hints"), read by the
    same rule-based helper as announcements, never a deadline.
    没有截止日期的大作业：planner 只列有日期的项，所以学期里最大的作业可能不在页面上。作业说明里的日期只当提示。"""
    out = []
    for c, subs in fetched:
        course = names.get(c["id"]) or course_label(c.get("course_code", ""))
        for s in subs:
            a = s.get("assignment") or {}
            points = a.get("points_possible")
            if not isinstance(points, (int, float)) or points <= 0 or points < min_points:
                continue
            if a.get("due_at") or s.get("cached_due_date"):
                continue                           # dated: the planner has it (or will, once it is near)
            if a.get("published") is False or a.get("workflow_state") in ("unpublished", "deleted"):
                continue
            if a.get("omit_from_final_grade") or a.get("hide_in_gradebook") or "not_graded" in (a.get("submission_types") or []):
                continue                           # practice / survey work: it does not count towards the grade
            if handed_in(s):
                continue
            lock = parse_iso(a.get("lock_at"), tz)
            if lock and lock < now:
                continue                           # closed for good
            aid = a.get("id") or s.get("assignment_id")
            if aid in known:
                continue
            seen, hints = set(), []
            for m in deadline_mentions(strip_html(a.get("description") or ""), now, tz):
                if m["due"] >= now and m["due"] not in seen:
                    seen.add(m["due"])
                    hints.append({"due": m["due"], "quote": m["quote"]})
            out.append({"id": f"canvas-undated-{aid}", "title": a.get("name") or "(untitled)", "course": course,
                        "points": points, "hints": sorted(hints, key=lambda h: h["due"])[:2],
                        "url": a.get("html_url") or (urllib.parse.urljoin(base_url, f"/courses/{c['id']}/assignments/{aid}")
                                                    if aid else "")})
    return sorted(out, key=lambda u: (-u["points"], u["course"], u["title"]))
