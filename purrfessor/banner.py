"""Class times, rooms and instructors from Ellucian Banner's public class search (SSB9).
Many US universities run the same Banner endpoints; the school preset gives the URL and the course-code format.
从 Ellucian Banner 公开选课查询读取上课时间、教室、老师。不少美国大学用的是同一套接口；地址和课号格式写在学校预设里。
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

from .model import as_date

TYPES = {"Lecture": "lecture", "Discussion": "discussion", "Laboratory": "lab", "Workshop": "workshop",
         "Seminar": "seminar", "Studio": "studio", "Activity": "activity"}
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WEEKDAY_KEYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def enrolled_sections(courses: list[dict], pattern: re.Pattern, term_suffix: dict) -> set[tuple]:
    """(subject, number, section, term) from Canvas course codes and section names,
    e.g. a discussion section listed under the lecture's Canvas site."""
    out = set()
    for c in courses:
        for name in [c.get("course_code", "")] + [s.get("name", "") for s in c.get("sections") or []]:
            m = pattern.match(name or "")
            if m and m[5] in term_suffix:
                out.add((m[1], m[2], m[3], f"20{m[4]}{term_suffix[m[5]]}"))
    return out


def person(display_name: str) -> str:
    """'Wood, William' → 'William Wood'"""
    last, _, first = display_name.partition(", ")
    return f"{first} {last}".strip()


def opener():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor())


def classes(sections: set[tuple], base_url: str, http=None) -> tuple[list[dict], list[dict]]:
    """→ (meetings with fixed times, online sections without a meeting time)."""
    http = http or opener()
    call = lambda path, data=None: http.open(f"{base_url}/{path}", data=data, timeout=30).read()  # noqa: E731
    call("term/termSelection?mode=search")
    timed, online, selected = [], [], None
    for subj, num, term in sorted({(s, n, t) for s, n, _, t in sections}):
        if term != selected:
            call("term/search?mode=search", f"term={term}".encode())
            selected = term
        call("classSearch/resetDataForm", b"")
        query = urllib.parse.urlencode({"txt_subject": subj, "txt_courseNumber": num, "txt_term": term,
                                        "pageOffset": 0, "pageMaxSize": 500, "sortColumn": "subjectDescription",
                                        "sortDirection": "asc"})
        wanted = {seq for s, n, seq, t in sections if (s, n, t) == (subj, num, term)}
        for sec in json.loads(call(f"searchResults/searchResults?{query}")).get("data") or []:
            if sec.get("courseNumber") != num or sec.get("sequenceNumber") not in wanted:
                continue
            kind = TYPES.get(sec.get("scheduleTypeDescription", ""), "activity")
            teacher = next((person(f["displayName"]) for f in sec.get("faculty", []) if f.get("primaryIndicator")), "")
            for mf in sec.get("meetingsFaculty", []):
                m = mf.get("meetingTime") or {}
                is_online = (m.get("building") or "").upper() == "ONLINE"
                entry = {"course": f"{subj} {num}", "type": kind, "section": sec["sequenceNumber"],
                         "where": "" if is_online else f"{m.get('buildingDescription', '')} {m.get('room', '')}".strip(),
                         "online": is_online, "teacher": teacher}
                days = [WEEKDAY_KEYS[i] for i, d in enumerate(DAYS) if m.get(d)]
                if not (days and m.get("beginTime") and m.get("endTime")):
                    online.append(entry)
                    continue
                if "exam" in (m.get("meetingTypeDescription") or "").lower():
                    entry["type"] = "exam"
                entry.update(days=days, start=f"{m['beginTime'][:2]}:{m['beginTime'][2:]}",
                             end=f"{m['endTime'][:2]}:{m['endTime'][2:]}",
                             **{"from": datetime.strptime(m["startDate"], "%m/%d/%Y").date(),
                                "until": datetime.strptime(m["endDate"], "%m/%d/%Y").date()})
                timed.append(entry)
    return timed, online


def derive_term(term_cfg: dict, timed: list[dict], sections: set, today: date, term_names: dict) -> dict:
    """Term name, week-1 Monday and last class day from the schedule, unless set in the config.
    Week 1 = the first Monday on/after the first class (a Thursday start makes those days week 0)."""
    term = dict(term_cfg)
    starts = [as_date(c["from"]) for c in timed if c.get("from")]
    ends = [as_date(c["until"]) for c in timed if c.get("until")]
    if "week1_monday" not in term:
        first = min(starts) if starts else today - timedelta(days=today.weekday())
        term["week1_monday"] = first + timedelta(days=(7 - first.weekday()) % 7)
    if "last_class_day" not in term:
        term["last_class_day"] = max(ends) if ends else as_date(term["week1_monday"]) + timedelta(weeks=10)
    if "name" not in term:
        code = max((s[3] for s in sections), default="")
        term["name"] = f"{term_names.get(code[4:], '')} {code[:4]}".strip()
    return term
