"""Shared data model and small helpers. 共用的数据结构和小工具。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


LATE_MIN = timedelta(hours=1)    # a lock this close to the due time is the same deadline, not a late window


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
    check: str = ""           # "read by AI, please check": said next to the date, not inside the (clamped) note
    aid: int | None = None    # Canvas assignment id behind this item (a quiz's differs from its own id)
    graded: bool = False      # graded and the grade is posted (excused work is not "graded")
    score: float | None = None  # points earned, when graded and Canvas shows them
    feedback: bool = False    # the grader left comments (only the fact: the text is private and never kept)
    lock_at: datetime | None = None   # Canvas closes submissions then (None: never, or unknown)
    submittable: bool = False         # Canvas takes work for it (the planner item came with a submissions record)

    @property
    def manual(self) -> bool:
        """Not on Canvas → completion can't be read; the student ticks it off on the page."""
        return self.source != "Canvas"

    @property
    def display_title(self) -> str:
        return self.translated or self.title

    def late_window(self, now: datetime) -> datetime | None:
        """Until when unfinished work can still be handed in after its due time: lock_at, if it is more than an hour
        after the due time (a quiz that locks when it is due has no window) and has not passed. Else None."""
        if self.done or self.lock_at is None or self.lock_at <= now or self.lock_at - self.due <= LATE_MIN:
            return None
        return self.lock_at


def as_date(v) -> date:
    return v if isinstance(v, date) and not isinstance(v, datetime) else date.fromisoformat(str(v)[:10])


def hm(s: str) -> time:
    h, m = map(int, s.split(":"))
    return time(h, m)


def parse_iso(s: str | None, tz: ZoneInfo) -> datetime | None:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(tz) if s else None
