# -*- coding: utf-8 -*-
"""일정관리 - 개발 건별 일정 저장소.

해외영업 담당자가 실제로 쫓기는 건 '문서'가 아니라 '날짜'다.
개발요청을 넣은 뒤 샘플이 언제 나오고, 언제 보내고, 피드백을 언제까지 받고,
단가를 언제 확정해 발주를 언제 받아야 선적이 맞는지가 한 화면에 있어야 한다.

이 모듈만 SQLite(data/schedule.db)를 쓴다. 기존 화면의 더미 규칙과는 별개다.
"""

import os
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    SEOUL = ZoneInfo("Asia/Seoul")
except Exception:                                    # noqa: BLE001
    SEOUL = timezone.utc

TIMEZONE_LABEL = "Asia/Seoul"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "schedule.db")

_local = threading.local()


# ---------------------------------------------------------------------------
# 단계 정의
#   offset = 착수일로부터 며칠 뒤가 기본 계획일인지 (업계 통상 리드타임 가안)
#   link   = 그 단계에서 실제로 쓰는 화면
# ---------------------------------------------------------------------------

PHASES = [
    {"key": "request", "label": "개발요청 전달", "icon": "📄", "offset": 0,
     "owner": "해외영업", "link": "compose", "link_label": "요청서 작성",
     "hint": "요청서를 연구소·공장에 넘긴 날. 여기서 모든 날짜가 시작된다."},
    {"key": "review", "label": "규제·처방 검토", "icon": "🌍", "offset": 7,
     "owner": "연구소", "link": "regulation", "link_label": "규제 검색",
     "hint": "판매국 금지·한도 성분을 먼저 걸러야 샘플을 두 번 안 만든다."},
    {"key": "sample", "label": "샘플 제작", "icon": "🧪", "offset": 21,
     "owner": "연구소", "link": "sample", "link_label": "샘플 미리보기",
     "hint": "1차 샘플. 향·색·점도 확정 전이라 재제작이 흔하다."},
    {"key": "sample_send", "label": "샘플 발송", "icon": "📦", "offset": 26,
     "owner": "해외영업", "link": None, "link_label": None,
     "hint": "국제 특송 3~5일. 성분표·CoA 를 같이 보낸다."},
    {"key": "feedback", "label": "고객 피드백", "icon": "💬", "offset": 40,
     "owner": "고객사", "link": "customers", "link_label": "고객사 관리",
     "hint": "가장 많이 밀리는 구간. 회신 기한을 먼저 못박아 두는 게 낫다."},
    {"key": "quote", "label": "단가 확정", "icon": "💰", "offset": 48,
     "owner": "해외영업", "link": "pricing", "link_label": "영업단가 계산",
     "hint": "원가·선적조건·환율이 정해져야 확정 견적이 나간다."},
    {"key": "po", "label": "본생산 발주 (PO)", "icon": "📝", "offset": 58,
     "owner": "고객사", "link": None, "link_label": None,
     "hint": "발주와 선금 입금 확인까지가 한 묶음이다."},
    {"key": "production", "label": "본생산", "icon": "🏭", "offset": 88,
     "owner": "공장", "link": None, "link_label": None,
     "hint": "자재 입고가 늦으면 여기서 통째로 밀린다."},
    {"key": "shipment", "label": "선적·서류", "icon": "🚢", "offset": 103,
     "owner": "해외영업", "link": None, "link_label": None,
     "hint": "B/L·C/O·인보이스. 서류 하나 빠지면 통관에서 멈춘다."},
]

PHASE_MAP = {row["key"]: row for row in PHASES}
PHASE_ORDER = {row["key"]: i for i, row in enumerate(PHASES)}
PHASE_KEYS = [row["key"] for row in PHASES]

# 리드타임 배수 - 급한 건과 여유 있는 건의 간격이 실제로 많이 다르다
PACES = [
    {"value": "rush", "label": "단축 (급건)", "factor": 0.7, "desc": "전시회·발주 마감이 걸린 건"},
    {"value": "standard", "label": "표준", "factor": 1.0, "desc": "통상 리드타임"},
    {"value": "relaxed", "label": "여유", "factor": 1.3, "desc": "신규 제형·인증이 얽힌 건"},
]
PACE_MAP = {row["value"]: row for row in PACES}

PROJECT_STATUS = [
    {"value": "active", "label": "진행 중"},
    {"value": "hold", "label": "보류"},
    {"value": "done", "label": "완료"},
    {"value": "dropped", "label": "중단"},
]
STATUS_LABELS = {row["value"]: row["label"] for row in PROJECT_STATUS}

ACCOUNT_KINDS = [
    {"value": "customer", "label": "고객사 요청"},
    {"value": "prospect", "label": "신규 바이어"},
    {"value": "inhouse", "label": "자사 기획"},
]
ACCOUNT_KIND_LABELS = {row["value"]: row["label"] for row in ACCOUNT_KINDS}

OWNERS = ["해외영업", "연구소", "공장", "구매팀", "품질", "고객사"]

# 일정 상태 표시 기준
SOON_DAYS = 3


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    account      TEXT,
    account_kind TEXT NOT NULL DEFAULT 'customer',
    country      TEXT,
    owner        TEXT,
    status       TEXT NOT NULL DEFAULT 'active',
    start_date   TEXT NOT NULL,
    pace         TEXT NOT NULL DEFAULT 'standard',
    note         TEXT,
    origin       TEXT NOT NULL DEFAULT 'manual',
    prospect_id  INTEGER,
    customer_id  TEXT,
    is_demo      INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    phase      TEXT NOT NULL,
    title      TEXT NOT NULL,
    owner      TEXT,
    plan_date  TEXT NOT NULL,
    done_date  TEXT,
    status     TEXT NOT NULL DEFAULT 'open',
    note       TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_plan ON tasks(plan_date);
"""


# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------

def now_iso():
    return datetime.now(SEOUL).strftime("%Y-%m-%d %H:%M:%S")


def today():
    return datetime.now(SEOUL).date()


def today_iso():
    return today().isoformat()


def parse_date(value, fallback=None):
    """YYYY-MM-DD 만 받는다. 못 읽으면 fallback (기본 None)."""
    try:
        return date.fromisoformat((value or "").strip())
    except (ValueError, AttributeError):
        return fallback


def connect():
    conn = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _local.conn = conn
    return conn


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()


def _row(row):
    return dict(row) if row is not None else None


# ---------------------------------------------------------------------------
# 건(프로젝트)
# ---------------------------------------------------------------------------

def default_plan(start, pace="standard"):
    """단계별 기본 계획일. 착수일 + 리드타임 × 배수."""
    factor = PACE_MAP.get(pace, PACE_MAP["standard"])["factor"]
    plan = []
    for phase in PHASES:
        days = int(round(phase["offset"] * factor))
        plan.append({
            "phase": phase["key"],
            "title": phase["label"],
            "owner": phase["owner"],
            "plan_date": (start + timedelta(days=days)).isoformat(),
        })
    return plan


def create_project(data, with_tasks=True):
    """건을 만들고 기본 일정까지 깐다. 반환값은 새 id."""
    conn = connect()
    stamp = now_iso()
    start = parse_date(data.get("start_date"), today())
    pace = data.get("pace") if data.get("pace") in PACE_MAP else "standard"
    kind = data.get("account_kind") if data.get("account_kind") in ACCOUNT_KIND_LABELS else "customer"

    cur = conn.execute(
        """INSERT INTO projects
           (title, account, account_kind, country, owner, status, start_date, pace,
            note, origin, prospect_id, customer_id, is_demo, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ((data.get("title") or "이름 없는 건").strip(),
         (data.get("account") or "").strip() or None,
         kind,
         (data.get("country") or "").strip() or None,
         (data.get("owner") or "").strip() or None,
         data.get("status") if data.get("status") in STATUS_LABELS else "active",
         start.isoformat(),
         pace,
         (data.get("note") or "").strip() or None,
         (data.get("origin") or "manual").strip(),
         data.get("prospect_id"),
         (data.get("customer_id") or "").strip() or None,
         1 if data.get("is_demo") else 0,
         stamp, stamp))
    project_id = cur.lastrowid

    if with_tasks:
        for item in default_plan(start, pace):
            conn.execute(
                """INSERT INTO tasks
                   (project_id, phase, title, owner, plan_date, status, created_at, updated_at)
                   VALUES (?,?,?,?,?, 'open', ?, ?)""",
                (project_id, item["phase"], item["title"], item["owner"],
                 item["plan_date"], stamp, stamp))

    conn.commit()
    return project_id


def update_project(project_id, data):
    conn = connect()
    fields, values = [], []
    for key in ("title", "account", "country", "owner", "note", "customer_id"):
        if key in data:
            value = (data.get(key) or "").strip()
            fields.append("{} = ?".format(key))
            values.append(value or None)
    if data.get("account_kind") in ACCOUNT_KIND_LABELS:
        fields.append("account_kind = ?")
        values.append(data["account_kind"])
    if data.get("status") in STATUS_LABELS:
        fields.append("status = ?")
        values.append(data["status"])
    if not fields:
        return
    fields.append("updated_at = ?")
    values.extend([now_iso(), project_id])
    conn.execute("UPDATE projects SET {} WHERE id = ?".format(", ".join(fields)), values)
    conn.commit()


def set_status(project_id, status):
    if status not in STATUS_LABELS:
        return
    conn = connect()
    conn.execute("UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
                 (status, now_iso(), project_id))
    conn.commit()


def delete_project(project_id):
    conn = connect()
    conn.execute("DELETE FROM tasks WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()


def get_project(project_id):
    conn = connect()
    return _row(conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone())


def all_projects():
    conn = connect()
    return [dict(r) for r in conn.execute(
        "SELECT * FROM projects ORDER BY start_date DESC, id DESC").fetchall()]


def find_by_prospect(prospect_id):
    conn = connect()
    return [dict(r) for r in conn.execute(
        "SELECT * FROM projects WHERE prospect_id = ? ORDER BY id DESC",
        (prospect_id,)).fetchall()]


# ---------------------------------------------------------------------------
# 일정(할 일)
# ---------------------------------------------------------------------------

def tasks_of(project_id):
    conn = connect()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE project_id = ?", (project_id,)).fetchall()]
    rows.sort(key=lambda r: (r["plan_date"], PHASE_ORDER.get(r["phase"], 99), r["id"]))
    return rows


def all_tasks(include_done=True, statuses=("active", "hold")):
    """건 정보를 붙인 일정 전체. 완료·중단 건은 기본적으로 뺀다."""
    conn = connect()
    marks = ",".join("?" for _ in statuses)
    sql = ("SELECT t.*, p.title AS project_title, p.account, p.account_kind, "
           "       p.status AS project_status, p.is_demo, p.country "
           "FROM tasks t JOIN projects p ON p.id = t.project_id "
           "WHERE p.status IN ({})".format(marks))
    params = list(statuses)
    if not include_done:
        sql += " AND t.status = 'open'"
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    rows.sort(key=lambda r: (r["plan_date"], PHASE_ORDER.get(r["phase"], 99), r["id"]))
    return rows


def add_task(project_id, data):
    conn = connect()
    stamp = now_iso()
    plan = parse_date(data.get("plan_date"), today())
    phase = data.get("phase") if data.get("phase") in PHASE_MAP else "request"
    conn.execute(
        """INSERT INTO tasks (project_id, phase, title, owner, plan_date, note,
                              status, created_at, updated_at)
           VALUES (?,?,?,?,?,?, 'open', ?, ?)""",
        (project_id, phase, (data.get("title") or "할 일").strip(),
         (data.get("owner") or "").strip() or None, plan.isoformat(),
         (data.get("note") or "").strip() or None, stamp, stamp))
    conn.commit()


def complete_task(task_id, done_date=None):
    conn = connect()
    done = parse_date(done_date, today())
    conn.execute("UPDATE tasks SET status = 'done', done_date = ?, updated_at = ? WHERE id = ?",
                 (done.isoformat(), now_iso(), task_id))
    conn.commit()


def reopen_task(task_id):
    conn = connect()
    conn.execute("UPDATE tasks SET status = 'open', done_date = NULL, updated_at = ? WHERE id = ?",
                 (now_iso(), task_id))
    conn.commit()


def reschedule_task(task_id, plan_date):
    plan = parse_date(plan_date)
    if plan is None:
        return False
    conn = connect()
    conn.execute("UPDATE tasks SET plan_date = ?, updated_at = ? WHERE id = ?",
                 (plan.isoformat(), now_iso(), task_id))
    conn.commit()
    return True


def shift_from(task_id, days):
    """한 일정을 미루면 그 뒤 단계도 같이 밀린다. 실제로 이게 제일 잦다."""
    conn = connect()
    row = _row(conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())
    if row is None or not days:
        return 0
    rows = tasks_of(row["project_id"])
    base = (row["plan_date"], PHASE_ORDER.get(row["phase"], 99), row["id"])
    moved = 0
    for item in rows:
        key = (item["plan_date"], PHASE_ORDER.get(item["phase"], 99), item["id"])
        # 기준이 된 일정 자신은 이미 옮겼으므로 두 번 밀지 않는다
        if item["id"] == row["id"] or key < base or item["status"] == "done":
            continue
        plan = parse_date(item["plan_date"])
        if plan is None:
            continue
        conn.execute("UPDATE tasks SET plan_date = ?, updated_at = ? WHERE id = ?",
                     ((plan + timedelta(days=days)).isoformat(), now_iso(), item["id"]))
        moved += 1
    conn.commit()
    return moved


def delete_task(task_id):
    conn = connect()
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()


def get_task(task_id):
    conn = connect()
    return _row(conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())


# ---------------------------------------------------------------------------
# 화면용 가공
# ---------------------------------------------------------------------------

def decorate_task(task, ref=None):
    """일정 한 건에 D-day 와 상태를 붙인다."""
    ref = ref or today()
    plan = parse_date(task["plan_date"], ref)
    row = dict(task)
    phase = PHASE_MAP.get(task["phase"], {})
    row["phase_label"] = phase.get("label", task["phase"])
    row["phase_icon"] = phase.get("icon", "•")
    row["phase_hint"] = phase.get("hint", "")
    row["link"] = phase.get("link")
    row["link_label"] = phase.get("link_label")
    row["days"] = (plan - ref).days

    if task["status"] == "done":
        done = parse_date(task.get("done_date"), plan)
        row["state"] = "done"
        row["late_days"] = max(0, (done - plan).days)
        row["d_label"] = "완료"
    elif row["days"] < 0:
        row["state"] = "overdue"
        row["late_days"] = -row["days"]
        row["d_label"] = "D+{}".format(-row["days"])
    elif row["days"] == 0:
        row["state"] = "today"
        row["late_days"] = 0
        row["d_label"] = "오늘"
    elif row["days"] <= SOON_DAYS:
        row["state"] = "soon"
        row["late_days"] = 0
        row["d_label"] = "D-{}".format(row["days"])
    else:
        row["state"] = "later"
        row["late_days"] = 0
        row["d_label"] = "D-{}".format(row["days"])
    return row


def project_view(project, tasks=None, ref=None):
    """건 하나를 목록·타임라인에 쓸 수 있게 정리한다."""
    ref = ref or today()
    rows = [decorate_task(t, ref) for t in (tasks if tasks is not None else tasks_of(project["id"]))]
    done = [r for r in rows if r["state"] == "done"]
    open_rows = [r for r in rows if r["state"] != "done"]
    overdue = [r for r in open_rows if r["state"] == "overdue"]

    upcoming = sorted(open_rows, key=lambda r: r["plan_date"])
    current = None
    for row in rows:
        if row["status"] == "open":
            current = row
            break

    view = dict(project)
    view["tasks"] = rows
    view["total"] = len(rows)
    view["done_count"] = len(done)
    view["overdue"] = overdue
    view["overdue_count"] = len(overdue)
    view["progress"] = round(len(done) / len(rows) * 100) if rows else 0
    view["next_task"] = upcoming[0] if upcoming else None
    view["current"] = current
    view["status_label"] = STATUS_LABELS.get(project["status"], project["status"])
    view["kind_label"] = ACCOUNT_KIND_LABELS.get(project["account_kind"], project["account_kind"])
    view["last_done"] = done[-1] if done else None

    if project["status"] in ("done", "dropped"):
        view["health"] = "closed"
    elif project["status"] == "hold":
        view["health"] = "hold"
    elif overdue:
        view["health"] = "late"
    elif any(r["state"] in ("today", "soon") for r in open_rows):
        view["health"] = "due"
    else:
        view["health"] = "ok"

    dates = [parse_date(r["plan_date"], ref) for r in rows]
    view["first_date"] = min(dates).isoformat() if dates else project["start_date"]
    view["last_date"] = max(dates).isoformat() if dates else project["start_date"]
    return view


def board(status="active", owner="all", keyword="", ref=None):
    """목록 화면. 급한 건이 위로 오도록 정렬한다."""
    ref = ref or today()
    keyword = (keyword or "").strip().lower()
    views = []
    for project in all_projects():
        if status != "all" and project["status"] != status:
            continue
        rows = tasks_of(project["id"])
        if owner != "all":
            if not any((t["owner"] or "") == owner for t in rows):
                continue
        if keyword:
            haystack = " ".join(str(project.get(k) or "") for k in
                                ("title", "account", "country", "owner", "note")).lower()
            if keyword not in haystack:
                continue
        views.append(project_view(project, rows, ref))

    health_rank = {"late": 0, "due": 1, "ok": 2, "hold": 3, "closed": 4}

    def sort_key(v):
        nxt = v["next_task"]
        return (health_rank.get(v["health"], 9),
                -v["overdue_count"],
                nxt["days"] if nxt else 9999,
                v["title"])

    views.sort(key=sort_key)
    return views


def summary(ref=None):
    """상단 요약. 완료·중단 건의 일정은 세지 않는다."""
    ref = ref or today()
    rows = [decorate_task(t, ref) for t in all_tasks(include_done=False)]
    week_end = ref + timedelta(days=7)
    projects = [p for p in all_projects() if p["status"] == "active"]
    return {
        "today": [r for r in rows if r["state"] == "today"],
        "overdue": [r for r in rows if r["state"] == "overdue"],
        "week": [r for r in rows if 0 <= r["days"] <= 7
                 and parse_date(r["plan_date"], ref) <= week_end],
        "active": len(projects),
        "hold": len([p for p in all_projects() if p["status"] == "hold"]),
    }


def agenda(days=14, ref=None):
    """오늘부터 N일치를 날짜별로 묶는다. 지연은 맨 앞에 따로 둔다."""
    ref = ref or today()
    rows = [decorate_task(t, ref) for t in all_tasks(include_done=False)]
    buckets = []
    for offset in range(days):
        day = ref + timedelta(days=offset)
        items = [r for r in rows if r["plan_date"] == day.isoformat()]
        if not items and offset > 0:
            continue
        buckets.append({
            "date": day.isoformat(),
            "label": "{}/{} ({})".format(day.month, day.day, WEEKDAYS[day.weekday()]),
            "is_today": offset == 0,
            "weekend": day.weekday() >= 5,
            "tasks": items,
        })
    return {"overdue": [r for r in rows if r["state"] == "overdue"], "buckets": buckets}


WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


def calendar_month(year=None, month=None, ref=None):
    """월 캘린더. 주 단위 6줄 격자로 돌려준다."""
    ref = ref or today()
    year = year or ref.year
    month = month or ref.month
    first = date(year, month, 1)
    start = first - timedelta(days=first.weekday())          # 월요일 시작

    rows = [decorate_task(t, ref) for t in all_tasks(include_done=True)]
    by_date = {}
    for row in rows:
        by_date.setdefault(row["plan_date"], []).append(row)

    weeks, cursor = [], start
    for _ in range(6):
        week = []
        for _ in range(7):
            week.append({
                "date": cursor.isoformat(),
                "day": cursor.day,
                "in_month": cursor.month == month,
                "is_today": cursor == ref,
                "weekend": cursor.weekday() >= 5,
                "tasks": by_date.get(cursor.isoformat(), []),
            })
            cursor += timedelta(days=1)
        weeks.append(week)
        if cursor.month != month and cursor > first:
            break

    prev_month = first - timedelta(days=1)
    next_month = (first + timedelta(days=31)).replace(day=1)
    return {
        "year": year, "month": month, "weeks": weeks,
        "label": "{}년 {}월".format(year, month),
        "prev": {"year": prev_month.year, "month": prev_month.month},
        "next": {"year": next_month.year, "month": next_month.month},
        "weekdays": WEEKDAYS,
    }


def timeline(views, ref=None):
    """타임라인 막대의 좌표(%)를 미리 계산해 템플릿을 단순하게 둔다."""
    ref = ref or today()
    if not views:
        return {"start": ref.isoformat(), "end": ref.isoformat(), "months": [], "rows": []}

    starts = [parse_date(v["first_date"], ref) for v in views]
    ends = [parse_date(v["last_date"], ref) for v in views]
    start = min(starts + [ref]) - timedelta(days=3)
    end = max(ends + [ref]) + timedelta(days=3)
    span = max((end - start).days, 1)

    def pct(value):
        return round((value - start).days / span * 100, 2)

    rows = []
    for view in views:
        bar_start = parse_date(view["first_date"], ref)
        bar_end = parse_date(view["last_date"], ref)
        points = []
        for task in view["tasks"]:
            plan = parse_date(task["plan_date"], ref)
            points.append({
                "left": pct(plan), "state": task["state"],
                "label": task["title"], "date": task["plan_date"],
                "icon": task["phase_icon"],
            })
        rows.append({
            "project": view,
            "left": pct(bar_start),
            "width": max(pct(bar_end) - pct(bar_start), 1),
            "points": points,
        })

    months, cursor = [], date(start.year, start.month, 1)
    while cursor <= end:
        months.append({"label": "{}월".format(cursor.month),
                       "left": max(pct(cursor), 0)})
        cursor = (cursor + timedelta(days=32)).replace(day=1)

    return {"start": start.isoformat(), "end": end.isoformat(),
            "months": months, "rows": rows, "today": pct(ref)}


# ---------------------------------------------------------------------------
# 예시 데이터
#   비어 있는 화면은 판단이 안 되니 예시를 넣을 수 있게 한다.
#   실제 건이 아니라는 표시(is_demo)를 남기고 화면에도 그대로 보여준다.
# ---------------------------------------------------------------------------

_DEMO = [
    {"title": "비타민C 브라이트닝 세럼 30ml", "account": "Glowtree Beauty",
     "account_kind": "customer", "country": "미국", "owner": "해외영업",
     "pace": "standard", "offset": -46, "done_upto": "feedback",
     "note": "2차 샘플까지 발송 완료. 피드백 회신이 예정보다 늦다."},
    {"title": "시카 진정 앰플 50ml", "account": "Nordic Bloom",
     "account_kind": "prospect", "country": "스웨덴", "owner": "해외영업",
     "pace": "rush", "offset": -12, "done_upto": "review",
     "note": "전시회 상담 건. 12월 전시 전 샘플 필요."},
    {"title": "레티놀 나이트 크림 50ml", "account": "자사 기획 (해외영업팀)",
     "account_kind": "inhouse", "country": "EU", "owner": "해외영업",
     "pace": "relaxed", "offset": -3, "done_upto": "request",
     "note": "트렌드 상승 보고 발의. EU 레티놀 한도 확인 필요."},
    {"title": "히알루론산 수분 토너 200ml", "account": "Sunbird Cosmetics",
     "account_kind": "customer", "country": "베트남", "owner": "해외영업",
     "pace": "standard", "offset": -96, "done_upto": "po",
     "note": "발주 접수. 자재 입고 일정 확인 중."},
]


def seed_demo(reset=False):
    """예시 건을 채운다. reset=True 면 기존 예시만 지우고 다시 만든다."""
    init_db()
    conn = connect()
    if reset:
        conn.execute("DELETE FROM tasks WHERE project_id IN "
                     "(SELECT id FROM projects WHERE is_demo = 1)")
        conn.execute("DELETE FROM projects WHERE is_demo = 1")
        conn.commit()
    elif conn.execute("SELECT COUNT(*) FROM projects WHERE is_demo = 1").fetchone()[0]:
        return 0

    ref = today()
    made = 0
    for item in _DEMO:
        start = ref + timedelta(days=item["offset"])
        project_id = create_project({
            "title": item["title"], "account": item["account"],
            "account_kind": item["account_kind"], "country": item["country"],
            "owner": item["owner"], "pace": item["pace"],
            "start_date": start.isoformat(), "note": item["note"],
            "origin": "demo", "is_demo": True,
        })
        limit = PHASE_ORDER.get(item["done_upto"], 0)
        for task in tasks_of(project_id):
            if PHASE_ORDER.get(task["phase"], 99) <= limit:
                plan = parse_date(task["plan_date"], ref)
                complete_task(task["id"], min(plan, ref).isoformat())
        made += 1
    return made


def clear_demo():
    init_db()
    conn = connect()
    conn.execute("DELETE FROM tasks WHERE project_id IN "
                 "(SELECT id FROM projects WHERE is_demo = 1)")
    cur = conn.execute("DELETE FROM projects WHERE is_demo = 1")
    conn.commit()
    return cur.rowcount


if __name__ == "__main__":
    import sys
    init_db()
    if "--reset" in sys.argv:
        print("예시 건 {}개를 다시 만들었습니다.".format(seed_demo(reset=True)))
    elif "--clear" in sys.argv:
        print("예시 건 {}개를 지웠습니다.".format(clear_demo()))
    else:
        print("예시 건 {}개를 넣었습니다.".format(seed_demo()))
