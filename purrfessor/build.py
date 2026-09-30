"""Build the dashboard page. 生成页面。

  python -m purrfessor.build --config purrfessor.toml --out _build/index.html [--prev _prev/plain/index.html]

Environment: CANVAS_TOKEN (required for Canvas data), GEMINI_API_KEY (optional: translation, announcement reading,
the brief agent). The page is still generated when anything fails; the reason shows at the top.
环境变量：CANVAS_TOKEN（读 Canvas 必需）、GEMINI_API_KEY（可选：翻译、理解公告、今日简报）。任何一步失败页面照常生成。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

from . import agent as brief_agent
from . import banner, canvas
from .config import Settings, load
from .enrich import enrich, parse_due
from .i18n import T
from .model import Task
from .render import render
from .schedule import apply_notes, classes_on, classify, label, recurring_tasks
from .snapshot import carry_memory, diff, load_prev_state, make_state


def make_canvas(S: Settings):
    """Factory kept separate so tests can swap in a fake Canvas."""
    return canvas.Canvas(S.canvas_url, os.environ.get("CANVAS_TOKEN", ""))


def strip_course_prefix(title: str, course: str) -> str:
    """'CS 005：Lab 0' → 'Lab 0' (the course is already shown as a badge)."""
    pattern = r"^\s*" + r"\s*".join(map(re.escape, course.split())) + r"\s*[:：\-–·|]?\s*"
    return re.sub(pattern, "", title, flags=re.I) or title


def apply_ai(ai: dict, tasks: list[Task], announcements: list[dict], tz) -> None:
    """Merge the Gemini result: translated titles (Chinese UI), announcement titles and summaries;
    AI-read deadlines replace the regex ones."""
    titles = {str(x.get("id")): x.get("title", "") for x in ai.get("tasks") or [] if isinstance(x, dict)}
    for t in tasks:
        t.translated = strip_course_prefix((titles.get(t.id) or "").strip(), t.course)
    by_id = {str(x.get("id")): x for x in ai.get("announcements") or [] if isinstance(x, dict)}
    for a in announcements:
        x = by_id.get(str(a["id"]))
        if not x:
            continue
        a["ai_title"], a["summary"] = str(x.get("title", "")), str(x.get("summary", ""))
        mentions = []
        for d in x.get("deadlines") or []:
            due = parse_due(str(d.get("due", "")), tz) if isinstance(d, dict) else None
            if due:
                mentions.append({"due": due, "what": str(d.get("what", ""))[:80], "quote": str(d.get("quote", ""))[:200]})
        a["mentions"] = mentions


def agent_deps(now: datetime, S: Settings, tasks: list[Task], classes: list[dict], announcements: list[dict],
               changes: dict, get, t: T) -> brief_agent.Deps:
    holidays = {str(h) for h in S.term.get("holidays", [])}
    overdue, pending, _ = classify(now, tasks, S.term)
    by_id = {x.id: x for x in overdue + pending}
    views = [{"id": x.id, "title": x.display_title, "course": x.course, "due": x.due.isoformat(), "points": x.points,
              "source": x.source, "state": "overdue" if x in overdue else "pending",
              "hours_left": round((x.due - now).total_seconds() / 3600, 1)} for x in overdue + pending]

    def cls(day):
        return [{"course": c["course"], "kind": label(c, t), "where": c.get("where", ""),
                 "start": f"{c['start_dt']:%H:%M}", "end": f"{c['end_dt']:%H:%M}"}
                for c in classes_on(day, classes, holidays, S.tz)]
    anns = [{"id": str(a["id"]), "course": a["course"], "title": a.get("ai_title") or a["title"],
             "summary": a.get("summary") or a["preview"], "text": a.get("text", "")[:3000], "posted": a["when"].isoformat()}
            for a in announcements if a["when"] and a["when"] >= now - timedelta(days=10)]
    return brief_agent.Deps(now=now, name=S.name, school=S.school, language=S.language, tasks=views,
                            classes_today=cls(now.date()), classes_tomorrow=cls(now.date() + timedelta(days=1)),
                            announcements=anns, changes=changes,
                            details=lambda tid: canvas.details(get, by_id[tid]) if tid in by_id else "")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Build the Purrfessor dashboard page")
    ap.add_argument("--config", default="purrfessor.toml")
    ap.add_argument("--out", default="_build/index.html")
    ap.add_argument("--now", help="debug: pretend it is this time (ISO 8601)")
    ap.add_argument("--prev", help="previous (decrypted) page, for 'since last update' and the agent's memory")
    ap.add_argument("--archive-dates", help='JSON {"dates": [...]} of snapshots already online')
    ap.add_argument("--archive-base", default="archive/")
    ap.add_argument("--home-url", default="", help="optional link back to a home page")
    args = ap.parse_args(argv)

    S = load(args.config)
    t = T(S.language)
    now = datetime.fromisoformat(args.now).astimezone(S.tz) if args.now else datetime.now(S.tz)
    warnings = [t(w) for w in S.warnings]
    pattern = re.compile(S.banner.get("section_pattern", r"^([A-Z]+)_(\w+?)_(\d{3})_(\d{2})([WSUF])"))

    client = make_canvas(S)
    courses, tasks, announcements, ai_model, grades = [], [], [], "", []
    if not os.environ.get("CANVAS_TOKEN"):
        warnings.append(t("warn_no_token"))
    else:
        try:
            courses = client.get("courses", {"enrollment_state": "active", "include[]": ["sections", "total_scores"],
                                             "per_page": 100})
            tasks = canvas.tasks(client.get, now, S.courses, S.tz, S.canvas_url)
            announcements = canvas.announcements(client.get, now, S.courses, courses, S.tz)
            # announcements are always summarized in the UI language; titles are translated only for a Chinese UI
            ai = enrich(now, tasks if S.translate else [], announcements, S.language)
            if ai:
                apply_ai(ai, tasks, announcements, S.tz)
                ai_model = ai["model"]
            tasks += canvas.announcement_tasks(announcements, tasks, now, t)
            if S.on("grades"):
                try:
                    grades = canvas.grades(client.get, courses, S.courses, pattern)
                except Exception as e:  # noqa: BLE001 - grades are optional
                    print(f"  · grades unavailable: {type(e).__name__}")
        except urllib.error.HTTPError as e:
            warnings.append(t("warn_token") if e.code == 401 else t("warn_http", code=e.code))
        except Exception as e:  # noqa: BLE001 - network trouble must not break the page
            warnings.append(t("warn_net", err=type(e).__name__))
    tasks += recurring_tasks(now, S.recurring, S.tz)

    timed, online, from_banner = [], [], False
    if S.banner.get("url"):
        sections = banner.enrolled_sections(courses, pattern, S.banner.get("term_suffix", {}))
        if sections:
            try:
                timed, online = banner.classes(sections, S.banner["url"], banner.opener())
                from_banner = True
            except Exception as e:  # noqa: BLE001 - the registrar site is sometimes down
                warnings.append(t("warn_banner", err=type(e).__name__))
    else:
        sections = set()
    S.term = banner.derive_term(S.term, timed, sections, now.date(), S.banner.get("term_names", {}))
    classes = apply_notes(timed, S.notes, t) + S.classes
    online = apply_notes(online, S.notes, t)

    state = make_state(now, tasks, announcements, classes)
    prev_state = load_prev_state(args.prev)
    changes = diff(prev_state, state)
    kinds = [k for k in changes if k != "since"]
    print(f"  · snapshot: {'no previous one' if not prev_state else ', '.join(kinds) if kinds else 'unchanged'}")

    today = now.date().isoformat()
    brief, brief_info = None, "disabled"
    if S.on("agent"):
        memory = carry_memory(prev_state, state, today)
        deps = agent_deps(now, S, tasks, classes, announcements, changes, client.get, t)
        deps.feedback = {"lessons": memory["lessons"], "evaluations": memory["feedback"]}
        deps.grades = grades
        brief, brief_info = brief_agent.run_brief(deps)
    state.update(carry_memory(prev_state, state, today, brief))
    last = state["feedback"][-1] if state["feedback"] else None
    print(f"  · brief: {brief_info}")
    print(f"  · memory: {len(state['lessons'])} lessons" + (
        f"; {last['brief_date']} follow-through: done {last['done']} · missed {last['missed']} · open {last['open']}"
        if last else ""))

    archive = []
    if args.archive_dates and Path(args.archive_dates).exists():
        archive = [d for d in json.loads(Path(args.archive_dates).read_text()).get("dates", []) if d != today]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(now, S, classes, online, tasks, announcements, warnings, ai_model, brief=brief,
                          changes=changes, state=state, archive=archive, archive_base=args.archive_base,
                          grades=grades, home_url=args.home_url, from_banner=from_banner), encoding="utf-8")
    count = lambda src: sum(x.source == src for x in tasks)  # noqa: E731
    print(f"✓ {out} · {S.school} · {S.language} · Canvas {count('Canvas')} · from announcements {count('announcement')}"
          f" · recurring {len(tasks) - count('Canvas') - count('announcement')} · announcements {len(announcements)}"
          f" · class meetings {len(timed)} + online {len(online)}" + (f" · AI {ai_model}" if ai_model else "")
          + "".join(f"\n  ⚠ {w}" for w in warnings))


if __name__ == "__main__":
    main()
