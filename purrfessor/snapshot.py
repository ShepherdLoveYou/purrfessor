"""Snapshots and memory. 快照与记忆。

Each build embeds its state in the (encrypted) page. The next build fetches the live page, decrypts it on the
CI runner and diffs against it ("since last update"), carries the agent's memory forward, and archives one
snapshot per day. No cache, no commits, no plaintext left anywhere.
每次生成都把状态嵌进（加密的）页面；下次运行取回线上页面、在 CI 机器上解密，算出"和上次比的变化"，
把智能体的记忆传下去，每天归档一份快照。不用缓存、不产生提交、不留明文。

CLI (used by GitHub Actions):
  python -m purrfessor.snapshot fetch --base URL --prev-dir _prev --archive-dir _site/archive
  python -m purrfessor.snapshot add   --site-dir _site --date 2026-09-29 --keep 30
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

TRACKED = {"Canvas", "announcement"}   # weekly off-Canvas tasks are generated, never "new"


# ---------- state and diff ----------

def make_state(now, tasks, announcements, classes) -> dict:
    return {
        "generated": now.isoformat(),
        "tasks": {t.id: {"title": t.display_title, "course": t.course, "due": t.due.isoformat(),
                         "done": t.done, "source": t.source} for t in tasks if t.source in TRACKED},
        "announcements": {str(a["id"]): {"title": a.get("ai_title") or a["title"], "course": a["course"]}
                          for a in announcements},
        "classes": sorted({f'{c["course"]}|{c.get("kind", "")}|{",".join(c.get("days", []))}|'
                           f'{c.get("start", "")}-{c.get("end", "")}|{c.get("where", "")}' for c in classes}),
    }


def diff(prev: dict | None, cur: dict) -> dict:
    """Compare with the previous snapshot: new tasks, just submitted, due date changed, withdrawn,
    new announcements, timetable changes."""
    if not prev:
        return {}
    # Only real Canvas assignments are compared. Items read out of announcements are AI-extracted and may vary
    # slightly between runs, which would show up as false "withdrawn"; new announcements are reported on their own.
    p = {k: v for k, v in prev.get("tasks", {}).items() if v.get("source") == "Canvas"}
    c = {k: v for k, v in cur["tasks"].items() if v.get("source") == "Canvas"}
    now = cur["generated"]
    out = {
        "since": prev.get("generated", ""),
        "new_tasks": [dict(id=k, **v) for k, v in c.items() if k not in p and not v["done"]],
        "completed": [dict(id=k, **v) for k, v in c.items() if k in p and v["done"] and not p[k]["done"]],
        "due_changed": [dict(id=k, old_due=p[k]["due"], **v) for k, v in c.items()
                        if k in p and v["due"] != p[k]["due"]],
        # only items that vanished before their due time (withdrawn by the instructor), not ones that simply expired
        "removed": [dict(id=k, **v) for k, v in p.items()
                    if k not in c and not v["done"] and v["due"] > now],
        "new_announcements": [dict(id=k, **v) for k, v in cur["announcements"].items()
                              if k not in prev.get("announcements", {})],
        "classes_added": [x for x in cur["classes"] if x not in set(prev.get("classes", []))],
        "classes_removed": [x for x in prev.get("classes", []) if x not in set(cur["classes"])],
    }
    return {k: v for k, v in out.items() if v}


# ---------- self-improvement: check whether the last advice was followed, carry lessons forward ----------

MAX_LESSONS, LESSON_LEN, KEEP_BRIEF_DAYS, KEEP_FEEDBACK = 5, 160, 7, 14


def evaluate(prev: dict | None, cur: dict, today: str) -> dict | None:
    """What happened to the priorities of the latest brief before today? Judged by code, not by the AI.
    done = submitted · missed = past due, not submitted · open = not due yet · unverifiable = off-Canvas task"""
    briefs = (prev or {}).get("briefs", {})
    past = sorted(d for d in briefs if d < today)
    if not past:
        return None
    day = past[-1]
    items = []
    for tid in briefs[day].get("priorities", []):
        t = cur["tasks"].get(tid) or (prev or {}).get("tasks", {}).get(tid)
        if not t:
            outcome = "unverifiable"
        elif t["source"] != "Canvas":
            outcome = "unverifiable"
        elif cur["tasks"].get(tid, {}).get("done"):
            outcome = "done"
        elif t["due"] < cur["generated"]:
            outcome = "missed"
        else:
            outcome = "open"
        items.append({"task_id": tid, "title": (t or {}).get("title", tid), "due": (t or {}).get("due", ""),
                      "outcome": outcome})
    count = {k: sum(i["outcome"] == k for i in items) for k in ("done", "missed", "open", "unverifiable")}
    return {"brief_date": day, "checked_at": cur["generated"], "items": items, **count}


def clean_lessons(lessons) -> list[str]:
    """Guardrails for lessons: strings only, trimmed, de-duplicated, LESSON_LEN chars each, MAX_LESSONS at most."""
    out = []
    for x in lessons or []:
        x = " ".join(str(x).split())[:LESSON_LEN] if isinstance(x, str) else ""
        if x and x not in out:
            out.append(x)
    return out[:MAX_LESSONS]


def carry_memory(prev: dict | None, cur: dict, today: str, brief=None) -> dict:
    """The memory stored in this snapshot: briefs of the last KEEP_BRIEF_DAYS days, the last KEEP_FEEDBACK
    evaluations and the current lessons. If the agent failed this time (brief=None), nothing is lost."""
    prev = prev or {}
    briefs = {d: b for d, b in prev.get("briefs", {}).items()
              if d >= (date.fromisoformat(today) - timedelta(days=KEEP_BRIEF_DAYS)).isoformat()}
    if brief is not None:
        briefs[today] = {"priorities": [p.task_id for p in brief.priorities], "generated": cur["generated"]}
    feedback = [f for f in prev.get("feedback", []) if isinstance(f, dict)]
    ev = evaluate(prev, cur, today)
    if ev:
        feedback = [f for f in feedback if f.get("brief_date") != ev["brief_date"]] + [ev]
    lessons = clean_lessons(brief.lessons) if brief is not None and brief.lessons else clean_lessons(prev.get("lessons"))
    return {"briefs": briefs, "feedback": feedback[-KEEP_FEEDBACK:], "lessons": lessons}


def load_prev_state(path: str | None) -> dict | None:
    """The state embedded in the previous (decrypted) page, or None (first run, decryption failed, …)."""
    if not path or not Path(path).exists():
        return None
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>',
                  Path(path).read_text(encoding="utf-8", errors="ignore"), re.S)
    try:
        return json.loads(m.group(1).replace("<\\/", "</")).get("state") if m else None
    except ValueError:
        return None


# ---------- online archive: fetch, add, prune ----------

def _get(url: str) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.read()
    except (urllib.error.URLError, TimeoutError):
        return None


def fetch(base: str, prev_dir: Path, archive_dir: Path) -> None:
    """Download the previous (encrypted) page and all archived snapshots so the next deploy keeps them."""
    base = base.rstrip("/")
    prev_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    page = _get(f"{base}/index.html")
    if page:
        (prev_dir / "index.html").write_bytes(page)
    manifest = _get(f"{base}/archive/index.json")
    dates = json.loads(manifest).get("dates", []) if manifest else []
    kept = []
    for d in dates:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and (body := _get(f"{base}/archive/{d}.html")):
            (archive_dir / f"{d}.html").write_bytes(body)
            kept.append(d)
    (prev_dir / "archive.json").write_text(json.dumps({"dates": kept}), encoding="utf-8")
    print(f"previous page: {'found' if page else 'none'} · archived snapshots: {len(kept)}")


def add(site_dir: Path, day: str, keep: int) -> None:
    """Save this (encrypted) page as today's snapshot and keep only the last `keep` days."""
    archive = site_dir / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(site_dir / "index.html", archive / f"{day}.html")
    cutoff = (date.fromisoformat(day) - timedelta(days=keep)).isoformat()
    dates = sorted((f.stem for f in archive.glob("*.html") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", f.stem)), reverse=True)
    for d in dates:
        if d <= cutoff:
            (archive / f"{d}.html").unlink()
    dates = [d for d in dates if d > cutoff]
    (archive / "index.json").write_text(json.dumps({"dates": dates}), encoding="utf-8")
    print(f"archived snapshots: {len(dates)} (last {keep} days)")


def cli(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="purrfessor snapshot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--base", required=True)
    f.add_argument("--prev-dir", default="_prev")
    f.add_argument("--archive-dir", default="_site/archive")
    a = sub.add_parser("add")
    a.add_argument("--site-dir", default="_site")
    a.add_argument("--date", help="YYYY-MM-DD (default: today in the school's time zone, from --config)")
    a.add_argument("--config", default="purrfessor.toml")
    a.add_argument("--keep", type=int, default=30)
    args = ap.parse_args(argv)
    if args.cmd == "fetch":
        fetch(args.base, Path(args.prev_dir), Path(args.archive_dir))
    else:
        if not args.date:
            from datetime import datetime

            from .config import load
            args.date = datetime.now(load(args.config).tz).date().isoformat()
        add(Path(args.site_dir), args.date, args.keep)


if __name__ == "__main__":
    cli()
