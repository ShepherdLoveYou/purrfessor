"""HTML rendering with Tabler (UI kit) + FullCalendar (timetable); the page shell is templates/page.html.
页面渲染：Tabler（UI 套件）+ FullCalendar（课程表）；外壳在 templates/page.html。All text comes from i18n.
"""
from __future__ import annotations

import base64
import html
import json
import re
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path

from .i18n import JS, T
from .model import Task, as_date
from .schedule import classes_on, classify, label, week_number

PKG = Path(__file__).resolve().parent
TEMPLATE = PKG / "templates" / "page.html"
CAT = PKG / "assets" / "cat.jpg"
LOGO = PKG / "assets" / "logo.svg"

# Tabler color names; one per course, shared by badges and the calendar (which needs real hex values)
COLORS = ["blue", "pink", "teal", "orange", "purple", "green", "indigo", "red", "cyan", "yellow", "lime", "azure"]
HEX = {"blue": "#066fd1", "pink": "#d6336c", "teal": "#0ca678", "orange": "#f76707", "purple": "#ae3ec9",
       "green": "#2fb344", "indigo": "#4263eb", "red": "#d63939", "cyan": "#17a2b8", "yellow": "#f59f00",
       "lime": "#74b816", "azure": "#4299e1", "secondary": "#667382"}
URGENCY_BADGE = {"u-over": "bg-red-lt", "u-24": "bg-red-lt", "u-72": "bg-orange-lt", "u-week": "bg-blue-lt",
                 "u-later": "bg-secondary-lt"}


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def same_words(s: str) -> str:
    """'Lab 1：Hello, World' and 'Lab 1: Hello, World' are the same title — no need to show the original."""
    return re.sub(r"[\W_]+", "", s.casefold())


def shorten(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n].rstrip() + "…"


def course_colors(names) -> dict[str, str]:
    return {n: COLORS[i % len(COLORS)] for i, n in enumerate(sorted(set(names)))}


def urgency(delta: timedelta) -> str:
    s = delta.total_seconds()
    return "u-over" if s < 0 else "u-24" if s < 86400 else "u-72" if s < 3 * 86400 else "u-week" if s < 7 * 86400 else "u-later"


def course_badge(course: str, colors: dict) -> str:
    return f'<span class="badge bg-{colors.get(course, "secondary")}-lt">{esc(course)}</span>'


def link(text: str, url: str, cls: str = "text-reset") -> str:
    return f'<a class="{cls}" href="{esc(url)}" target="_blank" rel="noopener">{esc(text)}</a>' if url else esc(text)


def link_badge(inner: str, url: str, color: str) -> str:
    """A small badge that opens `url` (plain badge when there is none). `inner` is trusted HTML."""
    return (f'<a class="badge {color}" href="{esc(url)}" target="_blank" rel="noopener">{inner}</a>' if url
            else f'<span class="badge {color}">{inner}</span>')


def where_html(c: dict, t: T) -> str:
    where, url = c.get("where", ""), c.get("link", "")
    if where.startswith("http"):
        where, url = "", where
    parts = [f'<i class="ti ti-map-pin"></i> {esc(where)}'] if where else []
    if url:
        parts.append(f'<a href="{esc(url)}" target="_blank" rel="noopener"><i class="ti ti-video"></i> '
                     f'{t("zoom") if "zoom" in url else t("link")}</a>')
    return " · ".join(parts)


def class_note(c: dict, t: T) -> str:
    who = ""
    if c.get("teacher"):
        who = f'{t("ta") if c.get("type") in ("discussion", "lab") else t("instructor")} {c["teacher"]}'
    return " · ".join(x for x in (who, c.get("note", "")) if x)


# ---------------------------------------------------------------- pieces

def expandable(text: str, cls: str = "") -> str:
    """Text clamped to a few lines; a tap, or Enter / Space on the keyboard, shows the rest (the page script toggles .open)."""
    return (f'<div class="text-secondary small {cls} preview" tabindex="0" role="button" aria-expanded="false">'
            f'{esc(text)}</div>')


def task_html(task: Task, now: datetime, colors: dict, t: T, state: str = "") -> str:
    color = colors.get(task.course, "secondary")
    # What the row says about when: the day heading above a "soon" row already says the day, so only the time; every other
    # row has no such heading ("overdue", "later", "done"), so it gets the date ("10/5 Mon 12:30", not "Monday 12:30").
    when = f"{task.due:%H:%M}" if state == "soon" else t.when(task.due)
    text = [esc(task.source if task.manual and task.source != "announcement" else t.kind(task.kind))]
    if task.points:
        text.append(esc(t("pts", p=f"{task.points:g}")))
    text.append(when)
    meta = course_badge(task.course, colors) + f'<span>{" · ".join(text)}</span>'     # no text node starts with a "·"
    if task.feedback:      # the comment itself stays on Canvas: the badge only links to where it is
        meta += link_badge(f'<i class="ti ti-message-dots"></i> {t("has_feedback")}', task.url, "bg-blue-lt")
    # the weekly homework is the same title every week: the name a screen reader says carries the course and the due date too
    name = t("tick_title", title=task.display_title, course=task.course, when=t.when(task.due))
    lead = (f'<label class="tick-hit"><input class="form-check-input m-0 tick" type="checkbox" data-key="{esc(task.id)}" '
            f'aria-label="{esc(name)}"></label>' if task.manual or not task.done
            else f'<span class="status-dot status-{"green" if task.done else color} d-block" aria-hidden="true"></span>')
    original = (f'<div class="text-secondary small original">{esc(task.title)}</div>'
                if task.translated and same_words(task.translated) != same_words(task.title) else "")
    note = expandable(task.note, "mt-1 preview-2") if task.note else ""       # a long quote from an announcement: two lines, tap for the rest
    window = task.late_window(now)           # past the due time but Canvas still takes the work
    if task.done:
        badge = f'<span class="badge bg-green-lt cd-done"><i class="ti ti-check"></i> {t("submitted")}</span>'
    elif window and task.due <= now:
        badge = f'<span class="badge bg-orange-lt cd">{esc(t("late_open", t=t.countdown(window - now)))}</span>'
    else:
        badge = f'<span class="badge {URGENCY_BADGE[urgency(task.due - now)]} cd">{esc(t.countdown(task.due - now))}</span>'
    lock = f' data-lock="{window.isoformat()}"' if window else ""
    manual = ' data-manual="1"' if task.manual else ""     # not on Canvas: the page script never calls it overdue
    lock_note = (f'<div class="text-secondary small mt-1 lock-note"><i class="ti ti-lock-open"></i> '
                 f'{esc(t("late_until", when=t.when(window)))}</div>' if window else "")
    return (f'<div class="list-group-item task{" done" if task.done else ""}" data-due="{task.due.isoformat()}" '
            f'data-id="{esc(task.id)}" data-state="{state}"{lock}{manual}>'
            f'<div class="row align-items-center g-3"><div class="col-auto">{lead}</div>'
            f'<div class="col min-w-0"><div class="fw-medium title">{link(task.display_title, task.url)}</div>{original}'
            f'<div class="text-secondary small mt-1 d-flex flex-wrap gap-2 align-items-center">{meta}</div>'
            f'{note}{lock_note}</div><div class="col-auto">{badge}</div></div></div>')


UNDATED_SHOWN, UNDATED_PER_COURSE = 8, 3      # at most 8 rows, and no course (31 placeholders…) fills them alone


def undated_row(u: dict, colors: dict, t: T) -> str:
    """Work with no due date: no tick box and no countdown (it is not a deadline); a date found in the
    description is shown as a hint to check, never as a fact."""
    pts = t("pts", p=f"{u['points']:g}")
    hints = "".join(f'<div class="text-secondary small mt-1"><i class="ti ti-calendar-question"></i> '
                    f'{esc(t("undated_hint", when=t.when(h["due"]), quote=shorten(h["quote"], 140)))}</div>' for h in u["hints"])
    return (f'<div class="list-group-item undated-item"><div class="fw-medium title">{link(u["title"], u["url"])}</div>'
            f'<div class="text-secondary small mt-1 d-flex flex-wrap gap-2 align-items-center">'
            f'{" · ".join([course_badge(u["course"], colors), pts, t("no_due")])}</div>{hints}</div>')


def undated_html(items: list[dict], colors: dict, t: T, min_points: float) -> str:
    """Collapsed list inside the to-do card: biggest points first, the same course at most UNDATED_PER_COURSE times,
    UNDATED_SHOWN rows in all, then "+N more"."""
    if not items:
        return ""
    shown, per_course = [], {}
    for u in items:
        if len(shown) < UNDATED_SHOWN and per_course.get(u["course"], 0) < UNDATED_PER_COURSE:
            shown.append(u)
            per_course[u["course"]] = per_course.get(u["course"], 0) + 1
    rows = "".join(undated_row(u, colors, t) for u in shown)
    if len(items) > len(shown):
        rows += f'<div class="list-group-item text-secondary small">{t("undated_more", n=len(items) - len(shown))}</div>'
    return (f'<details class="card-footer" id="undated"><summary class="text-primary fw-medium">{t("undated_n", n=len(items))}'
            f'</summary><div class="text-secondary small mt-2">{esc(t("undated_help", pts=f"{min_points:g}"))}</div>'
            f'<div class="list-group list-group-flush mt-2">{rows}</div></details>')


def class_html(c: dict, colors: dict, t: T) -> str:
    warn = (f' <a class="badge bg-orange-lt" href="{esc(c["warn_url"])}" target="_blank" rel="noopener">'
            f'<i class="ti ti-alert-triangle"></i> {t("maybe_cancelled")}</a>' if c.get("warn_url") else "")
    note = class_note(c, t)
    return (f'<div class="list-group-item cls" data-start="{c["start_dt"].isoformat()}" data-end="{c["end_dt"].isoformat()}">'
            f'<div class="row align-items-center g-3">'
            f'<div class="col-auto text-center time-col"><div class="fw-bold">{c["start_dt"]:%H:%M}</div>'
            f'<div class="text-secondary small">{c["end_dt"]:%H:%M}</div></div>'
            f'<div class="col-auto"><span class="status-dot status-{colors.get(c["course"], "secondary")} d-block" aria-hidden="true"></span></div>'
            f'<div class="col min-w-0"><div class="fw-medium">{course_badge(c["course"], colors)} {esc(label(c, t))}{warn}</div>'
            f'<div class="text-secondary small mt-1">{where_html(c, t)}{" · " + esc(note) if note else ""}</div></div>'
            f'<div class="col-auto"><span class="badge bg-secondary-lt cd"></span></div></div></div>')


def stat_card(icon: str, color: str, value: int, label_: str, href: str, key: str = "") -> str:
    # the counters the script updates are polite live regions (they change when a task is ticked or its time passes);
    # not inline: a nested same-type quote is a syntax error before Python 3.12
    stat = f' data-stat="{key}" aria-live="polite" aria-atomic="true"' if key else ""
    return (f'<div class="col-6 col-lg-3"><a class="card card-sm card-link text-reset" href="{href}"><div class="card-body">'
            f'<div class="row align-items-center"><div class="col-auto"><span class="bg-{color} text-white avatar">'
            f'<i class="ti ti-{icon} fs-2"></i></span></div><div class="col"><div class="h1 mb-0 lh-1"{stat}>{value}</div>'
            f'<div class="text-secondary small">{esc(label_)}</div></div></div></div></a></div>')


def next_card(id_: str, label_: str, icon: str, t: T) -> str:
    return (f'<div class="col-md-6"><div class="card next" id="{id_}"><div class="card-status-start"></div>'
            f'<div class="card-body"><div class="subheader"><i class="ti ti-{icon}"></i> {esc(label_)}</div>'
            f'<div class="h1 my-2 next-big">—</div><div class="fw-medium next-title">{t("loading")}</div>'
            f'<div class="text-secondary small next-meta"></div></div></div></div>')


def meme_card(now: datetime, t: T, tz) -> tuple[str, dict]:
    """The wizard-cat meme: whole weeks since Jan 1 00:00 in the school's time zone; caption in the UI language."""
    if not CAT.exists():
        return "", {}
    start, nxt = datetime(now.year, 1, 1, tzinfo=tz), datetime(now.year + 1, 1, 1, tzinfo=tz)
    weeks = int((now - start).total_seconds() // (7 * 86400))
    days = int((now - start).total_seconds() % (7 * 86400) // 86400)
    pct = (now - start) / (nxt - start) * 100
    img = "data:image/jpeg;base64," + base64.b64encode(CAT.read_bytes()).decode()
    line1 = esc(t("meme_line1", year="\x00")).replace("\x00", f'<span class="meme-year">{now.year}</span>')
    line2 = esc(t("meme_line2", n="\x00")).replace("\x00", f'<span class="meme-num">{weeks}</span>')
    card = (f'<div class="col-12"><div class="card"><div class="card-body">'
            f'<div class="meme meme-{t.lang} mx-auto" style="--cat:url({img})" role="img" id="meme" '
            f'aria-label="{esc(t("meme_alt", year=now.year, n=weeks))}">'
            f'<div class="meme-cap" aria-hidden="true"><div>{line1}</div><div>{line2}</div></div></div>'
            f'<div class="meme-foot mx-auto mt-3"><div class="d-flex justify-content-between text-secondary small mb-1">'
            f'<span class="meme-elapsed">{esc(t("meme_elapsed", w=weeks, d=days, year=now.year))}</span>'
            f'<span>{t("meme_progress")} <b class="meme-pct text-body">{pct:.1f}%</b></span></div>'
            f'<div class="progress progress-sm" role="progressbar" aria-label="{esc(t("meme_progress"))}" aria-valuenow="{pct:.1f}" '
            f'aria-valuemin="0" aria-valuemax="100"><div class="progress-bar meme-bar" style="width:{pct:.2f}%"></div></div></div>'
            f'</div></div></div>')
    return card, {"year": now.year, "start": int(start.timestamp() * 1000), "next": int(nxt.timestamp() * 1000)}


def calendar_payload(today: date, term: dict, classes: list[dict], tasks: list[Task], colors: dict,
                     holidays: set[str], tz, t: T) -> dict:
    """FullCalendar data: every class meeting this term (holidays excluded) + deadlines in the all-day row.
    Saturday and Sunday are hidden unless a class meets then or a deadline falls on one in the next two weeks."""
    start = as_date(term["week1_monday"]) - timedelta(days=7)
    end = as_date(term.get("last_class_day", today + timedelta(days=90))) + timedelta(days=14)
    events, hours, weekend = [], [], False
    day = start
    while day <= end:
        for c in classes_on(day, classes, holidays, tz):
            events.append({"title": f"{c['course']} {label(c, t)}", "start": c["start_dt"].isoformat(),
                           "end": c["end_dt"].isoformat(), "color": HEX[colors.get(c["course"], "secondary")]})
            hours += [c["start_dt"].hour, c["end_dt"].hour + (1 if c["end_dt"].minute else 0)]
            weekend |= day.weekday() >= 5
        day += timedelta(days=1)
    shown = today - timedelta(days=today.weekday()), today + timedelta(days=14)     # this week and the next two
    for x in tasks:
        if not x.done:
            events.append({"title": f"{x.due:%H:%M} {x.course} {x.display_title}", "start": x.due.date().isoformat(),
                           "allDay": True, "url": x.url, "classNames": ["deadline"],
                           "color": HEX[colors.get(x.course, "secondary")]})
            # a Saturday or Sunday deadline in the weeks the calendar opens on needs those columns too (a far-off one
            # does not: it would keep seven columns for the whole term)
            weekend |= x.due.weekday() >= 5 and shown[0] <= x.due.date() <= shown[1]
    lo, hi = (min(hours), max(hours)) if hours else (8, 18)
    return {"events": events, "slotMinTime": f"{max(lo - 1, 0):02d}:00:00", "slotMaxTime": f"{min(hi + 1, 24):02d}:00:00",
            "hiddenDays": [] if weekend else [0, 6]}


def brief_card(brief, tasks: list[Task], colors: dict, memory: dict, t: T) -> str:
    """The agent's brief. Every task id it references has been validated."""
    by_id = {x.id: x for x in tasks}
    pri = "".join(
        f'<div class="list-group-item"><div class="row g-3 align-items-start">'
        f'<div class="col-auto"><span class="brief-num">{i}</span></div><div class="col min-w-0">'
        f'<div class="fw-medium d-flex flex-wrap align-items-center gap-2">{course_badge(by_id[p.task_id].course, colors)}'
        f'<span>{link(by_id[p.task_id].display_title, by_id[p.task_id].url)}</span></div>'
        f'<div class="text-secondary mt-2">{esc(p.why)}</div>'
        f'<div class="brief-step mt-2"><i class="ti ti-arrow-right"></i><span>{esc(p.first_step)}</span></div>'
        f'</div></div></div>' for i, p in enumerate(brief.priorities, 1) if p.task_id in by_id)
    lessons = "".join(f'<div class="list-group-item"><div class="brief-step"><i class="ti ti-bulb"></i>'
                      f'<span>{esc(x)}</span></div></div>' for x in memory.get("lessons", []))
    last = (memory.get("feedback") or [None])[-1]
    follow = ""
    if last and last.get("items"):
        text = t("brief_follow", n=len(last["items"]), day=t.md(date.fromisoformat(last["brief_date"])),
                 done=last["done"], missed=last["missed"], open=last["open"])
        if last.get("unverifiable"):
            text += t("brief_follow_unv", n=last["unverifiable"])
        follow = f'<div class="list-group-item text-secondary small"><i class="ti ti-checklist me-1"></i>{esc(text)}</div>'
    risks = "".join(f'<div class="alert alert-warning mb-2"><i class="ti ti-alert-triangle me-1"></i>{esc(r)}</div>'
                    for r in brief.risks)
    groups = ""
    if pri:
        groups += f'<div class="brief-section"><i class="ti ti-target"></i>{t("brief_first")}</div>{pri}'
    if lessons or follow:
        groups += f'<div class="brief-section"><i class="ti ti-bulb"></i>{t("brief_lessons")}</div>{follow}{lessons}'
    return (f'<div class="col-12"><section id="brief" class="card" aria-labelledby="brief-title"><div class="card-header">'
            f'<h2 class="card-title" id="brief-title"><i class="ti ti-compass me-1"></i>{t("brief")}</h2>'
            f'<div class="card-actions"><span class="badge bg-purple-lt">{t("brief_badge")}</span></div></div>'
            f'<div class="card-body"><p class="brief-headline">{esc(brief.headline)}</p></div>'
            + (f'<div class="list-group list-group-flush">{groups}</div>' if groups else "")
            + (f'<div class="card-body">{risks}</div>' if risks else "")
            + (f'<div class="card-footer text-secondary"><i class="ti ti-history me-1"></i>{esc(brief.changes)}</div>'
               if brief.changes else "")
            + '</section></div>')


def grade_html(x: dict, t: T) -> str:
    """' · 144/150' (and the old score when a grade changed) for a newly graded task; nothing if no score is shown."""
    if x.get("score") is None:
        return ""
    text = f'{x["score"]:g}/{x["points"]:g}' if x.get("points") else f'{x["score"]:g}'
    if x.get("old_score") is not None:
        text += " " + t("ch_graded_was", old=f'{x["old_score"]:g}')
    return f' · <b>{esc(text)}</b>'


GRADED_SHOWN = 5       # grades are often posted in bulk (a term of 1-point participation): list the biggest, fold the rest


def changes_card(changes: dict, colors: dict, t: T) -> str:
    """What changed since the last snapshot — computed by code, not by the AI."""
    if not changes:
        return ""
    def when(iso):
        return t.when(datetime.fromisoformat(iso))
    rows = []
    for x in changes.get("new_tasks", []):
        rows.append(("plus", "green", t("ch_new"), f'{course_badge(x["course"], colors)} {esc(x["title"])} · {esc(t("due_on", when=when(x["due"])))}'))
    for x in changes.get("completed", []):
        rows.append(("check", "green", t("ch_done"), f'{course_badge(x["course"], colors)} {esc(x["title"])}'))
    for x in changes.get("due_changed", []):
        rows.append(("calendar-event", "orange", t("ch_due"),
                     f'{course_badge(x["course"], colors)} {esc(x["title"])} · {esc(when(x["old_due"]))} → <b>{esc(when(x["due"]))}</b>'))
    graded = sorted(changes.get("graded", []), key=lambda x: (-(x.get("points") or 0), x["course"], x["title"]))
    for x in graded[:GRADED_SHOWN]:
        rows.append(("award", "green", t("ch_graded"), f'{course_badge(x["course"], colors)} {esc(x["title"])}{grade_html(x, t)}'))
    if len(graded) > GRADED_SHOWN:
        rows.append(("award", "green", t("ch_graded"), esc(t("ch_graded_more", n=len(graded) - GRADED_SHOWN))))
    for x in changes.get("removed", []):
        rows.append(("trash", "secondary", t("ch_removed"), f'{course_badge(x["course"], colors)} {esc(x["title"])}'))
    for a in changes.get("new_announcements", []):
        rows.append(("speakerphone", "blue", t("ch_news"), f'{course_badge(a["course"], colors)} {esc(a["title"])}'))
    for c in changes.get("classes_added", []):
        rows.append(("calendar-plus", "orange", t("ch_class_add"), esc(c.replace("|", " · "))))
    for c in changes.get("classes_removed", []):
        rows.append(("calendar-minus", "orange", t("ch_class_del"), esc(c.replace("|", " · "))))
    if not rows:
        return ""
    since = t("changes_since", when=when(changes["since"])) if changes.get("since") else ""
    items = "".join(f'<div class="list-group-item py-2"><div class="row g-2 align-items-center"><div class="col-auto">'
                    f'<span class="badge bg-{c}-lt"><i class="ti ti-{i}"></i> {esc(lbl)}</span></div>'
                    f'<div class="col min-w-0 small">{body}</div></div></div>' for i, c, lbl, body in rows)
    return (f'<div class="col-12"><section id="changes" class="card" aria-labelledby="changes-title"><div class="card-header"><h2 class="card-title" id="changes-title">'
            f'<i class="ti ti-arrows-diff me-1"></i>{t("changes")}</h2><div class="card-actions card-note text-secondary small">'
            f'{esc(since)}</div></div><div class="list-group list-group-flush">{items}</div></section></div>')


def grades_card(grades: list[dict], colors: dict, t: T) -> str:
    """One row per course: course and missing / late flags on top, then the grade Canvas shows and the rate on graded
    work (one decimal each), with a thin bar for that rate and the points under it. On a phone a row is about 105 px."""
    if not grades:
        return ""
    rows = []
    for g in grades:
        cur = (f'<span class="h3 mb-0">{g["current"]:.1f}%</span>' if g["current"] is not None
               else f'<span class="text-secondary">{t("grade_hidden")}</span>')
        rate, bar = f'<span class="text-secondary">{t("grade_none")}</span>', ""
        if g["rate"] is not None:
            pct = min(g["rate"], 99.9) if g["earned"] < g["possible"] else g["rate"]     # 1459.25/1460 is not "100%"
            points = {"earned": f"{g['earned']:g}", "possible": f"{g['possible']:g}", "n": g["graded"]}
            label = t("grade_rate_val", rate=f"{pct:.1f}", **points)
            detail = t("grade_rate_detail", **points)
            rate = f'<span class="h3 mb-0">{pct:.1f}%</span>'
            bar = (f'<div class="col-12 order-sm-2"><div class="progress progress-sm" role="progressbar" aria-label="{esc(label)}" '
                   f'aria-valuenow="{pct:.1f}" aria-valuemin="0" aria-valuemax="100">'
                   f'<div class="progress-bar" style="width:{pct:.1f}%"></div></div>'
                   f'<div class="text-secondary small mt-1">{esc(detail)}</div></div>')
        flags = ((f'<span class="badge bg-red-lt">{t("missing_n", n=g["missing"])}</span> ' if g["missing"] else "")
                 + (f'<span class="badge bg-orange-lt">{t("late_n", n=g["late"])}</span>' if g["late"] else "")
                 or f'<span class="badge bg-green-lt">{t("no_missing")}</span>')
        rows.append(f'<div class="list-group-item grade-row"><div class="row g-2 align-items-center">'
                    f'<div class="col-6 col-sm-3">{course_badge(g["course"], colors)}</div>'
                    f'<div class="col-6 col-sm-2 text-end order-sm-1">{flags}</div>'
                    f'<div class="col-6 col-sm-3 d-flex flex-wrap align-items-baseline column-gap-2">'
                    f'<span class="text-secondary small">{t("grade_total")}</span>{cur}</div>'
                    f'<div class="col-6 col-sm-4 d-flex flex-wrap align-items-baseline column-gap-2">'
                    f'<span class="text-secondary small">{t("grade_rate")}</span>{rate}</div>'
                    f'{bar}</div></div>')
    return (f'<div class="col-12"><section id="grades" class="card" aria-labelledby="grades-title"><div class="card-header"><h2 class="card-title" id="grades-title">'
            f'<i class="ti ti-chart-bar me-1"></i>{t("grades")}</h2><div class="card-actions card-note text-secondary small">'
            f'{t("grades_aside")}</div></div><div class="list-group list-group-flush">{"".join(rows)}</div></section></div>')


# ---------------------------------------------------------------- page

def render(now: datetime, S, classes: list[dict], online: list[dict], tasks: list[Task], announcements: list[dict],
           warnings: list[str], ai_model: str = "", brief=None, changes=None, state=None, archive=(),
           archive_base: str = "archive/", grades=(), undated=(), home_url: str = "", from_banner: bool = True) -> str:
    t, tz, today = T(S.language), S.tz, now.date()
    holidays = {str(h) for h in S.term.get("holidays", [])}
    colors = course_colors([c["course"] for c in classes + online] + [x.course for x in tasks]
                           + [u["course"] for u in undated])
    week = week_number(today, S.term)
    first, last = as_date(S.term["week1_monday"]), as_date(S.term["last_class_day"])
    total_weeks = (last - first).days // 7 + 1
    term_pct = max(0, min(100, round((today - first).days / max((last - first).days, 1) * 100)))
    overdue, pending, done = classify(now, tasks, S.term)
    horizon = today + timedelta(days=14)
    soon = [x for x in pending if x.due.date() <= horizon]
    later = [x for x in pending if x.due.date() > horizon]
    cancelled = {a["course"]: a["url"] for a in announcements
                 if a["when"] and a["when"].date() == today
                 and re.search(r"cancel", a["title"] + a.get("text", a["preview"])[:220], re.I)}
    today_cls = [{**c, "warn_url": cancelled.get(c["course"], "")} for c in classes_on(today, classes, holidays, tz)]

    logo = urllib.parse.quote(LOGO.read_text(encoding="utf-8")) if LOGO.exists() else ""
    p = [f'<div class="page-header"><div class="row g-2 align-items-center">'
         f'<div class="col-auto"><img class="brand-logo" src="data:image/svg+xml,{logo}" alt="" width="52" height="52"></div>'
         f'<div class="col">'
         f'<div class="page-pretitle" id="greet">&nbsp;</div><h1 class="page-title">{esc(t("title", name=S.name))}</h1>'
         f'<div class="text-secondary mt-1">{esc(t.long(today))} · {esc(S.term.get("name", ""))} · {esc(S.school)}</div></div>'
         f'<div class="col-auto term-col"><div class="term-week text-end small text-secondary">{t("week", n=week, total=total_weeks)}</div>'
         f'<div class="progress progress-sm term-progress" role="progressbar" '
         f'aria-label="{esc(t("term_progress", n=week, total=total_weeks))}" aria-valuenow="{term_pct}" aria-valuemin="0" '
         f'aria-valuemax="100"><div class="progress-bar" style="width:{term_pct}%"></div></div>'
         f'</div></div></div>']
    p += [f'<div class="alert alert-warning mt-3 mb-0" role="alert"><i class="ti ti-alert-triangle"></i> {esc(w)}</div>'
          for w in warnings]
    nav = [("#todo", "checklist", "nav_todo"), ("#today", "sun", "nav_today"), ("#grades", "chart-bar", "nav_grades"),
           ("#timetable", "calendar-week", "nav_timetable"), ("#news", "speakerphone", "nav_news")]
    links = "".join(f'<a class="nav-link" href="{h}"><i class="ti ti-{i}"></i> {t(k)}</a>' for h, i, k in nav)
    if home_url:
        links += f'<a class="nav-link" href="{esc(home_url)}"><i class="ti ti-home"></i> {t("nav_home")}</a>'
    p.append(f'<nav class="nav-sticky"><div class="nav nav-pills">{links}</div></nav>')

    p.append('<div class="row row-cards">')
    p.append(stat_card("school", "blue", len(today_cls), t("stat_classes"), "#today"))
    ahead = [x for x in pending if x.due >= now]     # off-Canvas work stays 12 h after its time, counted nowhere (as in the script)
    p.append(stat_card("alarm", "red", sum(x.due.date() == today for x in ahead), t("stat_due_today"), "#todo", "due_today"))
    p.append(stat_card("hourglass-high", "orange", sum(x.due - now <= timedelta(days=3) for x in ahead),
                       t("stat_due_3d"), "#todo", "due_3d"))
    p.append(stat_card("alert-triangle", "red" if overdue else "green", len(overdue), t("stat_overdue"), "#todo", "overdue"))
    p.append(next_card("next-class", t("next_class"), "clock", t))
    p.append(next_card("next-due", t("next_due"), "flag", t))
    meme_html, meme_data = meme_card(now, t, tz) if S.on("meme") else ("", {})
    p.append(meme_html)
    if brief:
        p.append(brief_card(brief, tasks, colors, state or {}, t))
    p.append(changes_card(changes or {}, colors, t))

    rows = "".join(class_html(c, colors, t) for c in today_cls) or \
        f'<div class="list-group-item text-secondary">{t("no_classes_today")}</div>'
    tmr = classes_on(today + timedelta(days=1), classes, holidays, tz)
    tmr_html = ("、" if t.lang == "zh" else ", ").join(
        f'{c["start_dt"]:%H:%M} {esc(c["course"])} {esc(label(c, t))}' for c in tmr) if tmr else t("no_classes")
    today_html = (f'<div class="col-12"><section id="today" class="card" aria-labelledby="today-title"><div class="card-header"><h2 class="card-title" id="today-title">'
             f'<i class="ti ti-sun me-1"></i>{t("today_classes")}</h2><div class="card-actions text-secondary small">'
             f'{esc(t("classes_count", weekday=t.weekday(today), n=len(today_cls)))}</div></div>'
             f'<div class="list-group list-group-flush">{rows}</div>'
             f'<div class="card-footer text-secondary small"><i class="ti ti-arrow-right"></i> {t("tomorrow", items=tmr_html)}</div>'
             f'</section></div>')

    body = []
    if overdue:
        body.append(f'<div class="list-group-header text-danger">{t("overdue_group", n=len(overdue))}</div>')
        body += [task_html(x, now, colors, t, "overdue") for x in overdue]
    groups: dict[date, list[Task]] = {}
    for x in soon:
        groups.setdefault(x.due.date(), []).append(x)
    for day, xs in groups.items():
        body.append(f'<div class="list-group-header{" text-primary" if day == today else ""}">'
                    f'{esc(t.day_heading(day, today))} · {len(xs)}</div>')
        body += [task_html(x, now, colors, t, "soon") for x in xs]
    if not body:
        body.append(f'<div class="list-group-item text-secondary">{t("nothing_due")}</div>')
    extra = ""
    if later:
        extra += (f'<details class="card-footer"><summary class="text-primary fw-medium">{t("later_n", n=len(later))}</summary>'
                  f'<div class="list-group list-group-flush mt-2">{"".join(task_html(x, now, colors, t, "later") for x in later)}</div></details>')
    extra += undated_html(list(undated), colors, t, S.undated_min_points)
    if done:
        extra += (f'<details class="card-footer"><summary class="text-success fw-medium">{t("done_n", n=len(done))}</summary>'
                  f'<div class="list-group list-group-flush mt-2">{"".join(task_html(x, now, colors, t, "done") for x in done)}</div></details>')
    p.append(f'<div class="col-12"><section id="todo" class="card" aria-labelledby="todo-title"><div class="card-header"><h2 class="card-title" id="todo-title">'
             f'<i class="ti ti-checklist me-1"></i>{t("todo_title")}</h2><div class="card-actions card-note text-secondary small">'
             f'{t("todo_aside")}</div></div><div class="list-group list-group-flush">{"".join(body)}</div>{extra}</section></div>')
    p.append(today_html)   # what is due comes first; today's classes sit right below it

    p.append(grades_card(list(grades), colors, t))

    online_note = ""
    if online:
        names = ("、" if t.lang == "zh" else ", ").join(sorted({f'{c["course"]} {label(c, t)}' for c in online}))
        online_note = f'<div class="card-footer text-secondary small"><i class="ti ti-world"></i> {esc(t("online_note", names=names))}</div>'
    p.append(f'<div class="col-12"><section id="timetable" class="card" aria-labelledby="timetable-title"><div class="card-header"><h2 class="card-title" id="timetable-title">'
             f'<i class="ti ti-calendar-week me-1"></i>{t("timetable")}</h2><div class="card-actions card-note text-secondary small">'
             f'{t("timetable_aside" if from_banner else "timetable_manual")}</div></div>'
             f'<div class="card-body"><div id="calendar"></div></div>{online_note}</section></div>')

    recent = [a for a in announcements if a["when"] and a["when"] >= now - timedelta(days=10)]
    items = []
    for a in recent:
        dot = "status-dot status-blue status-dot-animated" if a["unread"] else "status-dot status-secondary"
        unread = f' <span class="badge bg-blue-lt ms-1">{t("unread")}</span>' if a["unread"] else ""
        summary = (f'<div class="mt-2">{esc(a["summary"])}</div>'
                   + (f'<div class="text-secondary small mt-1 original">{esc(t("orig_title", title=a["title"]))}</div>'
                      if a.get("ai_title") and a["ai_title"] != a["title"] else "")) if a.get("summary") else ""
        mentions = "".join(f'<div class="alert alert-warning py-2 px-3 mb-0 mt-2 small"><i class="ti ti-calendar-due"></i> '
                           f'<b>{esc(t.when(m["due"]))}</b>　{esc(m["what"] or m["quote"])}</div>' for m in a["mentions"])
        items.append(f'<div class="list-group-item"><div class="row g-3"><div class="col-auto pt-1"><span class="{dot} d-block" aria-hidden="true"></span></div>'
                     f'<div class="col min-w-0"><div class="fw-medium">{link(a.get("ai_title") or a["title"], a["url"])}{unread}</div>'
                     f'<div class="text-secondary small mt-1 d-flex gap-2 align-items-center">{course_badge(a["course"], colors)}'
                     f'{esc(t.when(a["when"], today))}</div>{summary}'
                     f'{expandable(a["preview"], "mt-2") if a["preview"] else ""}{mentions}</div></div></div>')
    if items:
        p.append(f'<div class="col-12"><section id="news" class="card" aria-labelledby="news-title"><div class="card-header"><h2 class="card-title" id="news-title">'
                 f'<i class="ti ti-speakerphone me-1"></i>{t("news")}</h2><div class="card-actions card-note text-secondary small">'
                 f'{t("news_aside")}</div></div><div class="list-group list-group-flush">{"".join(items)}</div></section></div>')
    p.append('</div>')
    if archive:
        snaps = " · ".join(f'<a href="{esc(archive_base)}{d}.html">{int(d[5:7])}/{int(d[8:10])}</a>' for d in archive[:14])
        p.append(f'<div class="text-center small mt-4"><i class="ti ti-history"></i> {t("history")} {snaps}</div>')
    foot = [t("footer_updated", when=f"{now:%m/%d %H:%M}", tz=now.tzname()), t("footer_auto"), t("footer_live")]
    if ai_model:
        foot.append(t("footer_ai", model=ai_model))
    built = t("footer_built", tabler='<a href="https://tabler.io" target="_blank" rel="noopener">Tabler</a>',
              fc='<a href="https://fullcalendar.io" target="_blank" rel="noopener">FullCalendar</a>')
    p.append(f'<footer class="text-center text-secondary small mt-4">{esc(" · ".join(foot))}<br>{built} · '
             f'<a href="https://github.com/ShepherdLoveYou/purrfessor" target="_blank" rel="noopener">{t("footer_project")}</a></footer>')

    upcoming = []
    for i in range(8):
        upcoming += classes_on(today + timedelta(days=i), classes, holidays, tz)
    data = {
        "tz": str(tz), "lang": t.lang, "fcLocale": t("fc_locale"), "i18n": {**JS[t.lang], "fcDue": t("fc_due"),
                                                                            "snapNote": t("snapshot_note", date="{date}"),
                                                                            "lateOpen": t("late_open", t="{t}")},
        "classes": [{"course": c["course"], "kind": label(c, t), "where": c.get("where", ""),
                     "start": c["start_dt"].isoformat(), "end": c["end_dt"].isoformat(),
                     "color": HEX[colors.get(c["course"], "secondary")]} for c in upcoming],
        "tasks": [{"id": x.id, "title": x.display_title, "course": x.course, "due": x.due.isoformat(), "url": x.url,
                   "manual": x.manual, "color": HEX[colors.get(x.course, "secondary")]} for x in pending],
        "calendar": calendar_payload(today, S.term, classes, tasks, colors, holidays, tz, t),
        "meme": meme_data, "state": state or {},
    }
    page = TEMPLATE.read_text(encoding="utf-8")
    return (page.replace("{{LANG}}", t("html_lang")).replace("{{FAVICON}}", logo).replace("{{TITLE}}", esc(t("page_title", name=S.name)))
                .replace("{{FC_LOCALE_SCRIPT}}", "" if t.lang == "en" else
                         f'<script src="https://cdn.jsdelivr.net/npm/fullcalendar@7.1.0/locales/{t("fc_locale")}/global.js"></script>')
                .replace("{{SNAP_LATEST}}", esc(t("snapshot_latest")))
                .replace("{{BODY}}", "\n".join(p))
                .replace("{{DATA}}", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")))
