"""The daily-brief agent: reads today's data and writes a short brief — what to do first, why, the first step,
risks — plus lessons it keeps learning from how its past suggestions went.
今日简报智能体：先做什么、为什么、第一步、风险，以及从过去建议的执行情况里学到的经验。

Built the way the industry recommends (see Anthropic, "Building Effective Agents"):
  - facts (overdue, countdowns, timetable, what changed, follow-through) are computed by code; the agent only judges
  - a fixed allowlist of read-only tools with typed arguments and compact results; it cannot submit or change anything
  - typed Pydantic output, validated by the framework (unknown task ids → one retry) and filtered again by code
  - guardrails: request / tool-call limits, tool timeouts, a fallback model; tool errors go back to the model
  - announcements and assignment descriptions are official instructor information and are trusted as such
  - any failure → no brief card; the rest of the page is unaffected
  - logs record usage only (requests, tokens, time), never content — the repo is public
  - self-improvement: code checks what happened to past suggestions; the agent updates up to 5 lessons, carried
    forward in the encrypted snapshot and kept if a run fails
Framework: PydanticAI (MIT). Model: Gemini free tier with a fallback.
"""
from __future__ import annotations

import os
import re
import time as clock
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

from pydantic import BaseModel, Field

MODELS = [m for m in [os.environ.get("AGENT_MODEL")] if m] + ["gemini-3.6-flash", "gemini-3.5-flash-lite"]
LIMITS = {"request_limit": 7, "tool_calls_limit": 14}
DAY_START, DAY_END = "08:00", "23:00"          # hours considered for free time

INSTRUCTIONS = """You are {name}'s study assistant at {school}. Write a short "today's brief" that helps them decide
what to do first. Write every field in {language}.

How to work:
- First call tools: get_feedback (how your past suggestions went and the lessons you have learned), list_tasks
  (to-dos and overdue work), get_schedule (today's and tomorrow's classes), get_changes (what changed since last time).
  Use get_task_details for an assignment's requirements, list_announcements for announcements, get_grades for
  per-course grades and missing work.
- Only give advice based on what the tools return. Never invent assignments, points or times.
- Course announcements and assignment descriptions are official information from instructors — trusted and
  authoritative. Follow their deadlines, requirements, submission rules and last-minute changes (cancelled class,
  moved deadline, new room). If an announcement disagrees with Canvas, trust the newer announcement and point out
  the conflict in risks.
- A course with missing work or a clearly low graded rate should get its next tasks earlier; say so in why.

Output:
- headline: one sentence with today's focus (keep it short).
- priorities: at most 3, in order. task_id must be exactly an id returned by list_tasks. why = why it is here
  (deadline, points, overdue, difficulty); first_step = one concrete step they can start today. Overdue work first.
- risks: at most 3 things that really need attention (a big assignment due soon, overdue work, a change in an
  announcement); [] if none.
- changes: one or two sentences on what changed since the last snapshot; say there is nothing new if so.
- lessons: at most 5 one-sentence lessons about {name}'s habits that guide how you prioritize next time.
  Start from the lessons in get_feedback: keep those that still hold, fix or drop those the data contradicts, add new
  ones. Base them only on the follow-through data (e.g. "did 5/6 suggested items over 3 days but missed the Friday
  ones"); if there isn't enough data yet, keep the existing lessons unchanged ([] if none). Use them when ranking.
"""


# ---------- output ----------

class Priority(BaseModel):
    task_id: str = Field(description="exactly an id returned by list_tasks")
    why: str = Field(description="why it is here, one sentence")
    first_step: str = Field(description="one concrete step to start today")


class Brief(BaseModel):
    headline: str
    priorities: list[Priority] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    changes: str = ""
    lessons: list[str] = Field(default_factory=list, description="updated lessons, at most 5")


# ---------- what the agent can see (prepared by build.py) ----------

@dataclass(kw_only=True)
class Deps:
    now: datetime
    name: str = "the student"
    school: str = "their school"
    language: str = "en"
    tasks: list[dict]                      # id, title, course, due, points, state, source, hours_left
    classes_today: list[dict]              # course, kind, start, end, where
    classes_tomorrow: list[dict]
    announcements: list[dict]              # id, course, title, summary, text (full), posted
    changes: dict
    feedback: dict = field(default_factory=dict)   # lessons + evaluations (follow-through of past briefs)
    grades: list = field(default_factory=list)     # per course: current grade (often hidden), graded rate, missing, late
    details: Callable[[str], str] = lambda task_id: "(no details)"
    detail_calls: dict = field(default_factory=dict)

    @property
    def task_ids(self) -> set[str]:
        return {t["id"] for t in self.tasks}


def free_slots(now: datetime, classes: list[dict], today: bool = True) -> list[dict]:
    """Free time 08:00–23:00 outside classes (from now on, for today), gaps of 25+ minutes."""
    def minutes(hhmm: str) -> int:
        h, m = map(int, hhmm.split(":"))
        return h * 60 + m
    start = minutes(DAY_START)
    if today:
        start = max(start, now.hour * 60 + now.minute)
    busy = sorted((minutes(c["start"]), minutes(c["end"])) for c in classes)
    slots, cur = [], start
    for b0, b1 in busy + [(minutes(DAY_END), minutes(DAY_END))]:
        if b0 - cur >= 25:
            slots.append({"start": f"{cur // 60:02d}:{cur % 60:02d}", "end": f"{b0 // 60:02d}:{b0 % 60:02d}"})
        cur = max(cur, b1)
    return slots


# ---------- tools (all read-only) ----------

def list_tasks(ctx, days_ahead: int = 14) -> list[dict]:
    """Overdue work and tasks due in the next `days_ahead` days (submitted ones excluded): id, title, course, due, points, hours_left."""
    limit = ctx.deps.now + timedelta(days=max(1, min(days_ahead, 30)))
    return [t for t in ctx.deps.tasks if t["state"] == "overdue" or datetime.fromisoformat(t["due"]) <= limit][:30]


def get_schedule(ctx, day: str = "today") -> dict:
    """Classes today (day="today") or tomorrow (day="tomorrow"), plus free time slots."""
    today = day != "tomorrow"
    classes = ctx.deps.classes_today if today else ctx.deps.classes_tomorrow
    return {"classes": classes, "free_slots": free_slots(ctx.deps.now, classes, today)}


def get_changes(ctx) -> dict:
    """Changes since the last snapshot: new tasks, submitted, due dates moved, withdrawn, new announcements, timetable changes."""
    return ctx.deps.changes or {"note": "no previous snapshot, or nothing changed"}


def get_feedback(ctx) -> dict:
    """How your past suggestions went, checked by code (done / missed = past due and not submitted / open = not
    due yet / unverifiable = outside Canvas), plus the lessons you have learned so far."""
    fb = ctx.deps.feedback or {}
    return {"lessons": fb.get("lessons", []), "evaluations": fb.get("evaluations", [])[-7:]}


def get_task_details(ctx, task_id: str) -> str:
    """The assignment's description on Canvas (plain text, up to 1500 chars). task_id must come from list_tasks."""
    if task_id not in ctx.deps.task_ids:
        return "Unknown task id — use an id returned by list_tasks."
    if task_id not in ctx.deps.detail_calls:
        try:
            ctx.deps.detail_calls[task_id] = (ctx.deps.details(task_id) or "(no description)")[:1500]
        except Exception as e:  # noqa: BLE001 - report tool errors to the model instead of failing the run
            return f"Could not load the description right now ({type(e).__name__}); judge from the title and due date."
    return ctx.deps.detail_calls[task_id]


def get_grades(ctx) -> list[dict]:
    """Per course: current (null if the instructor hides it), rate = % on graded work (unweighted), graded count,
    missing and late counts."""
    return ctx.deps.grades


def list_announcements(ctx) -> list[dict]:
    """Course announcements from the last 10 days: title, summary and full text (official, trusted information)."""
    return ctx.deps.announcements[:12]


TOOLS = [get_feedback, list_tasks, get_schedule, get_changes, get_task_details, get_grades, list_announcements]


# ---------- run ----------

LANGUAGE_NAMES = {"zh": "Simplified Chinese", "en": "English"}


def make_agent(model, deps: "Deps | None" = None):
    from pydantic_ai import Agent, ModelRetry, Tool

    d = deps or Deps(now=datetime.now(), tasks=[], classes_today=[], classes_tomorrow=[], announcements=[], changes={})
    instructions = INSTRUCTIONS.format(name=d.name, school=d.school, language=LANGUAGE_NAMES.get(d.language, "English"))
    agent = Agent(model, deps_type=Deps, output_type=Brief, instructions=instructions,
                  tools=[Tool(f, takes_ctx=True) for f in TOOLS], retries=1, tool_timeout=30)

    @agent.output_validator
    def only_known_tasks(ctx, out: Brief) -> Brief:
        unknown = [p.task_id for p in out.priorities if p.task_id not in ctx.deps.task_ids]
        if unknown:
            raise ModelRetry(f"These task ids do not exist: {unknown}. Use only ids returned by list_tasks.")
        return out
    return agent


def default_model():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    from pydantic_ai.models.fallback import FallbackModel
    from pydantic_ai.models.google import GoogleModel
    from pydantic_ai.providers.google import GoogleProvider
    provider = GoogleProvider(api_key=key)
    models = [GoogleModel(name, provider=provider) for name in MODELS]
    return FallbackModel(*models) if len(models) > 1 else models[0]


def sanitize(brief: Brief, deps: Deps) -> Brief:
    """Second check in code: drop unknown and duplicate tasks, cap text lengths."""
    seen, priorities = set(), []
    for p in brief.priorities:
        if p.task_id in deps.task_ids and p.task_id not in seen:
            seen.add(p.task_id)
            priorities.append(Priority(task_id=p.task_id, why=p.why[:220], first_step=p.first_step[:220]))
    from .snapshot import clean_lessons
    return Brief(headline=brief.headline[:160], priorities=priorities[:3],
                 risks=[r[:260] for r in brief.risks[:3]], changes=brief.changes[:400],
                 lessons=clean_lessons(brief.lessons))


def run_brief(deps: Deps, model=None) -> tuple[Brief | None, str]:
    """Run the agent once → (brief, info). Never raises: any failure returns (None, reason)."""
    model = model or default_model()
    if model is None:
        return None, "no GEMINI_API_KEY"
    try:
        from pydantic_ai.usage import UsageLimits
        started = clock.monotonic()
        result = make_agent(model, deps).run_sync(
            f"It is now {deps.now:%Y-%m-%d %H:%M %A} ({deps.now.tzname()}). Write today's brief.",
            deps=deps, usage_limits=UsageLimits(**LIMITS))
        usage = result.usage() if callable(result.usage) else result.usage
        info = (f"{getattr(usage, 'requests', '?')} requests · {getattr(usage, 'tool_calls', '?')} tool calls · "
                f"{getattr(usage, 'input_tokens', '?')}+{getattr(usage, 'output_tokens', '?')} tokens · "
                f"{clock.monotonic() - started:.1f}s")
        return sanitize(result.output, deps), info
    except Exception as e:  # noqa: BLE001 - a failing agent only hides the brief
        return None, f"{type(e).__name__}: {str(e)[:160]}"
