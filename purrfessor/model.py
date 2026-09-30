"""Shared data model and small helpers. 共用的数据结构和小工具。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo


@dataclass
class Task:
    id: str
    title: str
    course: str
    due: datetime
    url: str
    source: str               # "Canvas", "announcement", or a platform name like "Top Hat"
    kind: str = "assignment"  # Canvas planner type; localized when rendered
    points: float | None = None
    done: bool = False
    note: str = ""
    translated: str = ""      # AI translation of the title (Chinese UI only)
    ai_note: bool = False     # note came from the AI reading an announcement

    @property
    def manual(self) -> bool:
        """Not on Canvas → completion can't be read; the student ticks it off on the page."""
        return self.source != "Canvas"

    @property
    def display_title(self) -> str:
        return self.translated or self.title


def as_date(v) -> date:
    return v if isinstance(v, date) and not isinstance(v, datetime) else date.fromisoformat(str(v)[:10])


def hm(s: str) -> time:
    h, m = map(int, s.split(":"))
    return time(h, m)


def parse_iso(s: str | None, tz: ZoneInfo) -> datetime | None:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(tz) if s else None
