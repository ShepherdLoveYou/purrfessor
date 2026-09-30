"""All user-facing text, in English and Chinese. 页面上所有文字（中文 / 英文）。

Add a language by adding a dict with the same keys. 加一种语言 = 加一份同样键名的字典。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "html_lang": "en", "fc_locale": "en", "page_title": "{name}'s Today",
        "title": "{name}'s Today", "week": "Week {n} / {total}",
        "nav_today": "Today", "nav_todo": "To-do", "nav_grades": "Grades", "nav_timetable": "Timetable",
        "nav_news": "News", "nav_home": "Home",
        "stat_classes": "classes today", "stat_due_today": "due today", "stat_due_3d": "due in 3 days",
        "stat_overdue": "overdue",
        "next_class": "Next class", "next_due": "Next deadline", "loading": "Loading…",
        "today_classes": "Today's classes", "classes_count": "{weekday} · {n}", "no_classes_today": "No classes today 🎉",
        "tomorrow": "Tomorrow: {items}", "no_classes": "no classes",
        "instructor": "Instructor", "ta": "TA", "maybe_cancelled": "Announcement says it may be cancelled",
        "zoom": "Zoom", "link": "Link",
        "todo_title": "Due in the next two weeks", "todo_aside": "Tasks outside Canvas: tick them off yourself",
        "overdue_group": "Overdue · {n}", "nothing_due": "Nothing due in two weeks 🎉",
        "later_n": "{n} more later", "done_n": "Recently submitted · {n}", "submitted": "Submitted",
        "mark_done": "Mark as done", "pts": "{p} pts", "from_announcement": "From announcement: {title}",
        "ann_note_ai": "“{quote}” — read from the announcement by AI; open it to double-check",
        "ann_note_rule": "“{quote}” — date read from the announcement; open it to double-check",
        "timetable": "Timetable", "timetable_aside": "From the class schedule · top row = deadlines that day",
        "timetable_manual": "From your config · top row = deadlines that day",
        "online_note": "Online, no fixed meeting time: {names}", "fc_due": "Due",
        "grades": "Grades & completion", "grades_aside": "Rate = points on graded work, not weighted",
        "grade_total": "Current grade", "grade_hidden": "Hidden by instructor", "grade_rate": "Graded work",
        "grade_rate_val": "{rate}% ({earned}/{possible}, {n} graded)", "grade_none": "Nothing graded yet",
        "missing_n": "Missing {n}", "late_n": "Late {n}", "no_missing": "Nothing missing",
        "changes": "Since last update", "changes_since": "Last update: {when}",
        "ch_new": "New", "ch_done": "Submitted", "ch_due": "Due date moved", "ch_removed": "Withdrawn",
        "ch_news": "New announcement", "ch_class_add": "Class added", "ch_class_del": "Class removed",
        "due_on": "due {when}",
        "brief": "Today's brief", "brief_badge": "Self-improving AI agent · just a suggestion",
        "brief_first": "Do these first", "brief_lessons": "What it has learned",
        "brief_follow": "Of the {n} it suggested on {day}: {done} done · {missed} missed · {open} not due yet",
        "brief_follow_unv": " · {n} can't be checked",
        "news": "Recent announcements", "news_aside": "Sentences with dates are highlighted",
        "unread": "Unread", "orig_title": "Original title: {title}",
        "history": "Snapshots:", "footer_updated": "Updated {when} ({tz})", "footer_auto": "refreshes 4× a day",
        "footer_live": "countdowns are live", "footer_ai": "AI by {model}",
        "footer_built": "Built with {tabler} and {fc}", "footer_project": "Purrfessor · 喵教授",
        "meme_line1": "Tip: in {year},", "meme_line2": "you've wasted {n} weeks",
        "meme_elapsed": "{w} weeks {d} days into {year}", "meme_progress": "Year progress",
        "meme_alt": "Tip: in {year}, you've wasted {n} weeks",
        "warn_no_config": "No personal config found (PURRFESSOR_CONFIG) — using defaults",
        "warn_unknown_preset": "Unknown school preset — using the generic one",
        "warn_no_token": "Couldn't read Canvas: CANVAS_TOKEN is not set. Showing only your timetable and recurring tasks",
        "warn_token": "Couldn't read Canvas: the token has expired or is invalid (401) — create a new one",
        "warn_http": "Couldn't read Canvas: HTTP {code}", "warn_net": "Couldn't read Canvas: connection error ({err})",
        "warn_banner": "Couldn't read the class schedule ({err}); showing only classes from your config",
        "snapshot_note": "This is the snapshot from {date}; it no longer updates.", "snapshot_latest": "See the latest →",
        "tick_title": "Mark as done",
        "lock_title": "{name}'s Today · Purrfessor", "lock_instructions": "Enter the password to see today's plan",
        "lock_button": "Open", "lock_placeholder": "Password", "lock_remember": "Remember me for 30 days",
        "lock_error": "Wrong password",
    },
    "zh": {
        "html_lang": "zh-CN", "fc_locale": "zh-cn", "page_title": "{name} 的今日",
        "title": "{name} 的今日", "week": "Week {n} / {total}",
        "nav_today": "今天", "nav_todo": "待办", "nav_grades": "成绩", "nav_timetable": "课程表",
        "nav_news": "公告", "nav_home": "首页",
        "stat_classes": "今天的课", "stat_due_today": "今天截止", "stat_due_3d": "3 天内截止", "stat_overdue": "逾期未交",
        "next_class": "下一节课", "next_due": "最近的截止", "loading": "加载中…",
        "today_classes": "今天的课", "classes_count": "{weekday} · {n} 节", "no_classes_today": "今天没有课 🎉",
        "tomorrow": "明天：{items}", "no_classes": "没有课",
        "instructor": "老师", "ta": "TA", "maybe_cancelled": "公告说可能取消", "zoom": "Zoom", "link": "链接",
        "todo_title": "接下来两周要交的", "todo_aside": "Canvas 之外的任务做完请自己打勾",
        "overdue_group": "逾期未交 · {n}", "nothing_due": "两周内没有要交的 🎉",
        "later_n": "更远的 {n} 项", "done_n": "最近已交 {n} 项", "submitted": "已交",
        "mark_done": "我做完了", "pts": "{p} 分", "from_announcement": "公告提到：{title}",
        "ann_note_ai": "“{quote}” —— AI 从公告里读出来的，请点开核对",
        "ann_note_rule": "“{quote}” —— 日期是从公告里自动读的，请点开核对",
        "timetable": "课程表", "timetable_aside": "自动读取选课系统 · 最上面一行是当天的截止",
        "timetable_manual": "来自你的配置 · 最上面一行是当天的截止",
        "online_note": "线上课，没有固定上课时间：{names}", "fc_due": "截止",
        "grades": "成绩与完成情况", "grades_aside": "得分率按已批改作业直接相加，未按各科权重计算",
        "grade_total": "总成绩", "grade_hidden": "老师未公开", "grade_rate": "已批改作业得分率",
        "grade_rate_val": "{rate}%（{earned}/{possible}，{n} 项）", "grade_none": "还没有批改的作业",
        "missing_n": "缺交 {n}", "late_n": "晚交 {n}", "no_missing": "没有缺交",
        "changes": "和上次比", "changes_since": "上次更新：{when}",
        "ch_new": "新作业", "ch_done": "已交", "ch_due": "截止改了", "ch_removed": "被撤下",
        "ch_news": "新公告", "ch_class_add": "课表新增", "ch_class_del": "课表去掉",
        "due_on": "{when} 截止",
        "brief": "今日简报", "brief_badge": "AI Agent 自改进智能体生成 · 仅供参考",
        "brief_first": "今天先做", "brief_lessons": "它学到的经验",
        "brief_follow": "{day} 建议先做的 {n} 件：已交 {done} · 错过 {missed} · 还没到期 {open}",
        "brief_follow_unv": " · 看不到完成情况 {n}",
        "news": "最近的公告", "news_aside": "带日期的句子会自动标出来",
        "unread": "未读", "orig_title": "原标题：{title}",
        "history": "历史快照：", "footer_updated": "数据更新于 {when}（{tz}）", "footer_auto": "每天自动更新 4 次",
        "footer_live": "倒计时实时计算", "footer_ai": "中文由 {model} 翻译",
        "footer_built": "用 {tabler} 和 {fc} 构建", "footer_project": "Purrfessor · 喵教授",
        "meme_line1": "小提示：你已经在{year}", "meme_line2": "浪费了{n}个星期了",
        "meme_elapsed": "今年已过 {w} 周 {d} 天", "meme_progress": "全年进度",
        "meme_alt": "小提示：你已经在{year}浪费了{n}个星期了",
        "warn_no_config": "没有找到个人配置（PURRFESSOR_CONFIG），先用默认设置",
        "warn_unknown_preset": "没有这个学校预设，先用通用预设",
        "warn_no_token": "没读到 Canvas：没有设置 CANVAS_TOKEN。下面只有课表和固定作业",
        "warn_token": "没读到 Canvas：token 失效或过期（401），需要重新生成",
        "warn_http": "没读到 Canvas：返回 HTTP {code}", "warn_net": "没读到 Canvas：连接出错（{err}）",
        "warn_banner": "没读到选课系统的课表（{err}），课表只显示配置里手填的部分",
        "snapshot_note": "这是 {date} 的历史快照，内容不会再更新。", "snapshot_latest": "查看最新的 →",
        "tick_title": "标记为已完成",
        "lock_title": "{name} 的今日 · 喵教授", "lock_instructions": "输入口令查看今天要做的事",
        "lock_button": "打开", "lock_placeholder": "口令", "lock_remember": "30 天内记住我", "lock_error": "口令不对",
    },
}

# Canvas planner item types. Canvas 待办类型。
KINDS = {
    "en": {"assignment": "Assignment", "quiz": "Quiz", "discussion_topic": "Discussion", "wiki_page": "Reading",
           "planner_note": "Note", "calendar_event": "Event", "assessment_request": "Peer review", "_": "Task",
           "announcement": "Announcement"},
    "zh": {"assignment": "作业", "quiz": "测验", "discussion_topic": "讨论", "wiki_page": "阅读",
           "planner_note": "备忘", "calendar_event": "日程", "assessment_request": "互评", "_": "任务",
           "announcement": "公告"},
}

# Class meeting types (Banner scheduleTypeDescription → key). 上课类型。
MEETINGS = {
    "en": {"lecture": "Lecture", "discussion": "Discussion", "lab": "Lab", "workshop": "Workshop",
           "seminar": "Seminar", "studio": "Studio", "activity": "Activity", "exam": "Exam"},
    "zh": {"lecture": "大课", "discussion": "讨论课", "lab": "Lab", "workshop": "工作坊",
           "seminar": "研讨课", "studio": "Studio", "activity": "活动", "exam": "考试"},
}

WEEKDAYS = {"en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            "zh": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]}
MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
RELATIVE = {"en": {-1: "Yesterday", 0: "Today", 1: "Tomorrow"},
            "zh": {-1: "昨天", 0: "今天", 1: "明天", 2: "后天"}}

# Text the browser script needs. 前端脚本用的文字。
JS = {
    "en": {"d": "d ", "h": "h ", "m": "m ", "s": "s", "startsIn": "starts in {t}", "inClass": "In class · {t} left",
           "noMore": "No more classes this week", "left": "{t} left", "nothingDue": "Nothing due soon 🎉",
           "due": "due", "pastDue": "Past due", "in": "in {t}", "live": "In class", "ended": "Ended",
           "rel": ["Today", "Tomorrow"], "greet": ["Up late — get some rest", "Good morning", "Good afternoon",
                                                    "Good afternoon", "Good evening"],
           "elapsed": "{w} weeks {d} days into {year}"},
    "zh": {"d": "天", "h": "小时", "m": "分", "s": "秒", "startsIn": "{t} 后开始", "inClass": "上课中 · 还剩 {t}",
           "noMore": "这周没有更多课了", "left": "还剩 {t}", "nothingDue": "近期没有要交的 🎉",
           "due": "截止", "pastDue": "已截止", "in": "{t}后", "live": "上课中", "ended": "已结束",
           "rel": ["今天", "明天", "后天"], "greet": ["夜深了，早点休息", "早上好", "中午好", "下午好", "晚上好"],
           "elapsed": "今年已过 {w} 周 {d} 天"},
}


class T:
    """t = T("zh"); t("title", name="Alex"); t.weekday(d); t.md(d) …"""

    def __init__(self, lang: str):
        self.lang = lang if lang in STRINGS else "en"
        self.s = STRINGS[self.lang]

    def __call__(self, key: str, **kw) -> str:
        return self.s[key].format(**kw) if kw else self.s[key]

    def kind(self, planner_type: str) -> str:
        return KINDS[self.lang].get(planner_type, KINDS[self.lang]["_"])

    def meeting(self, key: str) -> str:
        return MEETINGS[self.lang].get(key, key)

    def weekday(self, d: date) -> str:
        return WEEKDAYS[self.lang][d.weekday()]

    def md(self, d: date | datetime) -> str:
        """9/29 周二 · Tue 9/29"""
        return f"{d.month}/{d.day} {self.weekday(d)}" if self.lang == "zh" else f"{self.weekday(d)} {d.month}/{d.day}"

    def long(self, d: date) -> str:
        """9月29日 周二 · Tuesday, Sep 29"""
        if self.lang == "zh":
            return f"{d.month}月{d.day}日 {self.weekday(d)}"
        return f"{d:%A}, {MONTHS_EN[d.month - 1]} {d.day}"

    def rel_day(self, day: date, today: date) -> str:
        return RELATIVE[self.lang].get((day - today).days, self.weekday(day))

    def day_heading(self, day: date, today: date) -> str:
        rel = RELATIVE[self.lang].get((day - today).days) if (day - today).days >= 0 else None
        return f"{rel} · {self.md(day)}" if rel else self.md(day)

    def when(self, dt: datetime, today: date | None = None) -> str:
        head = self.rel_day(dt.date(), today) if today else self.md(dt)
        return f"{head} {dt:%H:%M}"

    def countdown(self, delta: timedelta) -> str:
        s = int(delta.total_seconds())
        if s < 0:
            return self("pastDue") if "pastDue" in self.s else JS[self.lang]["pastDue"]
        j = JS[self.lang]
        d, h, m = s // 86400, s % 86400 // 3600, s % 3600 // 60
        text = f"{d}{j['d']}{h}{j['h']}" if d else f"{h}{j['h']}{m}{j['m']}" if h else f"{m}{j['m']}"
        return text.strip()
