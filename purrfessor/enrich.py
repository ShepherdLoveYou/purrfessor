"""One Gemini call per build (free tier, via Google's open-source google-genai SDK):
  - Chinese UI: translate assignment titles; English UI: titles stay as they are
  - announcements: a title and a 1–2 sentence summary in the UI language
  - deadlines mentioned in announcements, with "next Friday" / "by Week 3" resolved to real dates
No key, no SDK, quota exhausted or a malformed reply → None, and the page falls back to the rule-based path.
每次生成调用一次 Gemini：中文界面翻译作业标题；公告写成界面语言的标题和摘要；读出公告里的截止日期。
失败时返回 None，页面退回规则方式。
"""
from __future__ import annotations

import json
import os
from datetime import datetime

MODELS = [m for m in [os.environ.get("GEMINI_MODEL")] if m] + [
    "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-flash-latest"]
LANGUAGE_NAMES = {"zh": "Simplified Chinese", "en": "English"}

PROMPT = """You help a university student keep up with coursework. It is now {now} ({tz}).
Below are the student's Canvas assignment titles and recent course announcements (JSON). Write in {language}.

1. tasks: {task_rule}
2. announcements: for each one, a short title and a 1–2 sentence summary saying what the student must do and when.
3. For each announcement, deadlines: things the student must do by a certain time (submit, fill in a survey,
   register, take an exam, attend…).
   - Resolve relative dates ("tomorrow", "next Friday", "by the end of Week 3") from the announcement's posting time.
   - No time given → 23:59 that day. due = "YYYY-MM-DDTHH:MM" in the student's time zone.
   - what = a short description in {language}; quote = the original sentence.
   - Only things the student is clearly asked to do; skip anything more than a day in the past; else [].

Data:
{data}"""

TASK_RULE = {
    "zh": ("translate each title into natural, concise Simplified Chinese. Do not add the course name. Keep numbers, "
           "course codes and product names as they are; translate the descriptive words. e.g. "
           "\"Week 2: Attendance Quiz\" → \"第 2 周：出勤测验\", \"Fall Mid-Quarter Assignment\" → \"秋季期中作业\", "
           "\"Lab 0: Cat's Meow\" → \"Lab 0：猫咪喵喵\", \"Active Practice #2\" → \"课后练习 #2（Active Practice）\"."),
    "en": "return an empty list (titles are already in English).",
}

SCHEMA = {
    "type": "object",
    "properties": {
        "tasks": {"type": "array", "items": {"type": "object", "required": ["id", "title"],
                                             "properties": {"id": {"type": "string"}, "title": {"type": "string"}}}},
        "announcements": {"type": "array", "items": {
            "type": "object", "required": ["id", "title", "summary", "deadlines"],
            "properties": {
                "id": {"type": "string"}, "title": {"type": "string"}, "summary": {"type": "string"},
                "deadlines": {"type": "array", "items": {
                    "type": "object", "required": ["what", "due", "quote"],
                    "properties": {"what": {"type": "string"}, "due": {"type": "string"},
                                   "quote": {"type": "string"}}}}}}},
    },
    "required": ["tasks", "announcements"],
}


def enrich(now: datetime, tasks: list, announcements: list[dict], language: str) -> dict | None:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key or not (tasks or announcements):
        return None
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("  · google-genai not installed — skipping AI")
        return None
    data = {
        "tasks": [{"id": t.id, "course": t.course, "title": t.title} for t in tasks] if language == "zh" else [],
        "announcements": [{"id": str(a["id"]), "course": a["course"], "posted": f"{a['when']:%Y-%m-%d %H:%M %a}",
                           "title": a["title"], "text": a.get("text", "")[:3000]} for a in announcements],
    }
    prompt = PROMPT.format(now=f"{now:%Y-%m-%d %H:%M %A}", tz=now.tzname(), language=LANGUAGE_NAMES[language],
                           task_rule=TASK_RULE[language], data=json.dumps(data, ensure_ascii=False))
    config = types.GenerateContentConfig(
        response_mime_type="application/json", response_json_schema=SCHEMA, temperature=0.2,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    client = genai.Client(api_key=key)
    for model in MODELS:
        try:
            out = json.loads(client.models.generate_content(model=model, contents=prompt, config=config).text)
            if isinstance(out, dict):
                out["model"] = model
                return out
        except Exception as e:  # noqa: BLE001 - try the next model, then fall back to rules
            print(f"  · Gemini {model} unavailable: {type(e).__name__} {str(e)[:160]}")
    return None


def parse_due(s: str, tz) -> datetime | None:
    try:
        return datetime.strptime(s.strip()[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=tz)
    except (ValueError, AttributeError):
        return None
