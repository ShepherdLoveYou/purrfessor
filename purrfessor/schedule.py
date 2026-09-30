"""Timetable days, recurring off-Canvas tasks, week numbers and the task state machine.
课表、Canvas 之外的固定作业、第几周，以及作业的状态机。"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .model import Task, as_date, hm

WEEKDAY_KEYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def label(c: dict, t) -> str:
    """'Lecture' / 'Discussion 021' / a manual class's own kind."""
    if "type" not in c:
        return c.get("kind", "")
    base = t.meeting(c["type"])
    return base if c["type"] in ("lecture", "exam") else f"{base} {c.get('section', '')}".strip()


def apply_notes(classes: list[dict], notes: list[dict], t) -> list[dict]:
    """[[notes]] in the config: add a note / link, or change from / until / where, matched by course and kind.
    kind may be a type key ('discussion'), or the label in either language ('讨论课', 'Discussion 021')."""
    out = []
    for c in classes:
        c = dict(c)
        names = {c.get("type", ""), label(c, t), c.get("kind", "")}
        for n in notes:
            want = n.get("kind", "")
            if n.get("course") != c["course"] or not any(x and x.startswith(want) for x in names):
                continue
            if n.get("note"):
                c["note"] = " · ".join(x for x in (c.get("note"), n["note"]) if x)
            for key in ("link", "from", "until", "where"):
                if key in n:
                    c[key] = n[key]
        out.append(c)
    return out


def week_number(day: date, term: dict) -> int:
    w1 = as_date(term["week1_monday"])
    return 0 if day < w1 else (day - w1).days // 7 + 1


def classes_on(day: date, classes: list[dict], holidays: set[str], tz) -> list[dict]:
    if day.isoformat() in holidays:
        return []
    out = []
    for c in classes:
        if WEEKDAY_KEYS[day.weekday()] not in c.get("days", []):
            continue
        if "from" in c and day < as_date(c["from"]) or "until" in c and day > as_date(c["until"]):
            continue
        start = datetime.combine(day, hm(c["start"]), tz)
        end = datetime.combine(day, hm(c["end"]), tz) if c.get("end") else start + timedelta(minutes=50)
        out.append({**c, "start_dt": start, "end_dt": end})
    return sorted(out, key=lambda c: c["start_dt"])


def recurring_tasks(now: datetime, recurring: list[dict], tz) -> list[Task]:
    """Weekly tasks Canvas can't see (Top Hat, a homework site…), generated for the next three weeks."""
    out = []
    for r in recurring:
        first, last = as_date(r["from"]), as_date(r["until"])
        for i in range(-1, 21):
            day = now.date() + timedelta(days=i)
            if WEEKDAY_KEYS[day.weekday()] != r["weekday"] or not first <= day <= last:
                continue
            due = datetime.combine(day, hm(r.get("due", "23:59")), tz)
            if due < now - timedelta(hours=12):
                continue
            out.append(Task(id=f"{r['platform']}-{r['course']}-{day.isoformat()}", title=r["title"],
                            course=r["course"], due=due, url=r.get("url", ""), source=r["platform"],
                            kind="planner_note", note=r.get("note", "")))
    return out


def classify(now: datetime, tasks: list[Task], term: dict) -> tuple[list[Task], list[Task], list[Task]]:
    """→ (overdue, pending, recently done). The page and the agent use this same rule.
    Overdue = Canvas task not submitted and past due, this term only. Off-Canvas tasks are never overdue:
    they drop off 12 h after their due time."""
    term_start = as_date(term["week1_monday"]) - timedelta(days=14)
    overdue = sorted((t for t in tasks if not t.done and not t.manual and t.due < now and t.due.date() >= term_start),
                     key=lambda t: t.due)
    ids = {t.id for t in overdue}
    pending = sorted((t for t in tasks if not t.done and t.due >= now - timedelta(hours=12) and t.id not in ids),
                     key=lambda t: t.due)
    done = sorted((t for t in tasks if t.done and t.due >= now - timedelta(days=3)), key=lambda t: t.due)
    return overdue, pending, done
