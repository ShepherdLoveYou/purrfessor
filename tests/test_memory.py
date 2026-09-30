"""The self-improvement loop: code checks whether advice was followed → the agent updates its lessons →
the lessons travel to the next run inside the snapshot; nothing is lost on failure. 自改进闭环。"""
from __future__ import annotations

from conftest import FakeCanvas, item, pt
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from purrfessor import agent as ag
from purrfessor import snapshot as sn


def brief(priorities, lessons=()):
    return {"headline": "Today's focus", "priorities": [{"task_id": t, "why": "why", "first_step": "step"} for t in priorities],
            "risks": [], "changes": "nothing new", "lessons": list(lessons)}


def agent_that(output, seen=None):
    """Call get_feedback first (recording what it returned in `seen`), then answer with `output`."""
    state = {"n": 0}

    def fn(messages, info):
        state["n"] += 1
        if state["n"] == 1:
            return ModelResponse(parts=[ToolCallPart("get_feedback", {})])
        if seen is not None:
            seen["feedback"] = " ".join(str(p) for m in messages for p in getattr(m, "parts", []))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])
    return FunctionModel(fn)


def failing_agent():
    def fn(messages, info):
        raise RuntimeError("model down")
    return FunctionModel(fn)


A, B, C = "canvas-assignment-1", "canvas-assignment-2", "canvas-assignment-3"


def canvas(a_done=False, b_done=False):
    return FakeCanvas(planner=[item(1, 1001, "Essay", pt("2026-10-06 23:59"), submitted=a_done),
                               item(2, 1002, "Morning quiz", pt("2026-10-06 09:00"), submitted=b_done),
                               item(3, 1001, "Reading", pt("2026-10-12 23:59"))])


def test_self_improvement_loop_across_days(build):
    # day 1: suggests A and B; nothing to check yet
    day1 = build(pt("2026-10-05 12:30"), canvas(), model=agent_that(brief([A, B])))
    assert day1.data["state"]["briefs"]["2026-10-05"]["priorities"] == [A, B]
    assert day1.data["state"]["lessons"] == [] and day1.data["state"]["feedback"] == []

    # day 2: A submitted, B missed → code evaluates it and hands it to the agent, which writes a lesson
    seen = {}
    lesson = "Morning quizzes get missed; flag them the evening before"
    day2 = build(pt("2026-10-07 08:00"), canvas(a_done=True), prev=day1,
                 model=agent_that(brief([C], lessons=[lesson]), seen))
    fb = day2.data["state"]["feedback"][-1]
    assert fb["brief_date"] == "2026-10-05" and (fb["done"], fb["missed"]) == (1, 1)
    assert "'missed': 1" in seen["feedback"]                     # the evaluation reached the agent
    assert day2.data["state"]["lessons"] == [lesson]
    assert "它学到的经验" in day2.html and lesson in day2.html
    assert "已交 1 · 错过 1" in day2.html and "自改进智能体生成" in day2.html

    # day 3: the agent fails → no brief, but lessons and history are kept
    day3 = build(pt("2026-10-08 08:00"), canvas(a_done=True), prev=day2, model=failing_agent())
    assert 'id="brief"' not in day3.html
    assert day3.data["state"]["lessons"] == [lesson]
    assert "2026-10-07" in day3.data["state"]["briefs"]

    # day 4: no new lessons → keep the old ones; the latest brief (10/7, suggested C, not due yet) is checked
    day4 = build(pt("2026-10-09 08:00"), canvas(a_done=True), prev=day3, model=agent_that(brief([C])))
    assert day4.data["state"]["lessons"] == [lesson]
    last = day4.data["state"]["feedback"][-1]
    assert last["brief_date"] == "2026-10-07" and last["open"] == 1


def test_no_key_keeps_memory_too(build):
    day1 = build(pt("2026-10-05 12:30"), canvas(), model=agent_that(brief([A], lessons=["lesson one"])))
    day2 = build(pt("2026-10-06 12:30"), canvas(), prev=day1, model=None)
    assert day2.data["state"]["lessons"] == ["lesson one"]


def test_lessons_guardrails():
    raw = ["  a  ", "", "a", "x" * 200, None, 3, "b", "c", "d", "e", "f"]
    out = sn.clean_lessons(raw)
    assert out[0] == "a" and len(out) == sn.MAX_LESSONS and all(len(x) <= sn.LESSON_LEN for x in out)
    assert out.count("a") == 1


def test_evaluate_marks_off_canvas_items_unverifiable():
    prev = {"briefs": {"2026-10-05": {"priorities": ["HW-DEMO 002A-2026-10-09", "gone-id"]}}, "tasks": {}}
    cur = {"generated": "2026-10-06T08:00:00-07:00", "tasks": {}}
    ev = sn.evaluate(prev, cur, "2026-10-06")
    assert ev["unverifiable"] == 2 and ev["done"] == 0


def test_memory_is_pruned():
    old = {f"2026-09-{d:02d}": {"priorities": []} for d in range(1, 29)}
    prev = {"briefs": old, "feedback": [{"brief_date": f"2026-08-{d:02d}"} for d in range(1, 29)], "lessons": []}
    cur = {"generated": "2026-10-01T08:00:00-07:00", "tasks": {}}
    mem = sn.carry_memory(prev, cur, "2026-10-01")
    assert all(d >= "2026-09-24" for d in mem["briefs"]) and len(mem["feedback"]) <= sn.KEEP_FEEDBACK


def test_same_day_reevaluation_replaces_not_duplicates():
    prev = {"briefs": {"2026-10-05": {"priorities": []}},
            "feedback": [{"brief_date": "2026-10-05", "done": 0}], "tasks": {}, "lessons": []}
    cur = {"generated": "2026-10-06T18:00:00-07:00", "tasks": {}}
    mem = sn.carry_memory(prev, cur, "2026-10-06")
    assert [f["brief_date"] for f in mem["feedback"]] == ["2026-10-05"]


def test_feedback_tool_is_read_only_and_returns_memory():
    deps = ag.Deps(now=pt("2026-10-06 08:00"), tasks=[], classes_today=[], classes_tomorrow=[], announcements=[],
                   changes={}, feedback={"lessons": ["x"], "evaluations": [{"brief_date": "2026-10-05"}]})

    class Ctx:
        pass
    ctx = Ctx()
    ctx.deps = deps
    assert ag.get_feedback(ctx) == {"lessons": ["x"], "evaluations": [{"brief_date": "2026-10-05"}]}
