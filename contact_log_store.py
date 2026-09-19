# -*- coding: utf-8 -*-
"""고객사 연락 기록 - 누구와 무슨 연락을 했나.

고객사 화면에 메일 본문까지 다 펼쳐 두니 정작 필요한 게 안 보였다.
고객사 화면에서 알고 싶은 건 "이 회사와 최근에 무슨 얘기가 오갔나" 한 줄이다.
메일 원문을 읽는 건 그 건(프로젝트)에서 할 일이다.

그래서 여기는 **간단 메모**만 남긴다.

    2026-09-16 · Emily Park(구매·발주) · 📧 이메일 · 받음
    레티놀 농도 EU 기준 문의. 단가 조정 폭도 같이 물어봄

담당자는 목록에서 고르되 **이름을 같이 적어 둔다.** 담당자가 퇴사해 명단에서
지워져도 "누구와 한 연락인지" 는 남아 있어야 한다. 기록이 사라지면 안 된다.
"""

import os
import sqlite3
import threading
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
    SEOUL = ZoneInfo("Asia/Seoul")
except Exception:                                    # noqa: BLE001
    SEOUL = timezone.utc

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "contact_log.db")

_local = threading.local()

# 프로젝트의 '바이어 연락' 과 같은 말을 쓴다. 화면마다 다른 낱말을 쓰면
# 같은 기록인지 다른 기록인지 헷갈린다.
CHANNELS = {
    "email": {"label": "이메일", "icon": "📧"},
    "call": {"label": "전화", "icon": "📞"},
    "meeting": {"label": "미팅·화상", "icon": "👥"},
    "message": {"label": "메신저", "icon": "💬"},
    "sample": {"label": "샘플 발송", "icon": "📦"},
    "other": {"label": "기타", "icon": "•"},
}
CHANNEL_ORDER = ["email", "call", "meeting", "message", "sample", "other"]

DIRECTIONS = {
    "in": {"label": "받음", "css": "in"},
    "out": {"label": "보냄", "css": "out"},
}

MEMO_LIMIT = 400

SCHEMA = """
CREATE TABLE IF NOT EXISTS contact_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT NOT NULL,
    at          TEXT NOT NULL,          -- 연락한 날 (YYYY-MM-DD)
    contact_id  INTEGER,                -- 담당자 목록에서 고른 경우
    person      TEXT NOT NULL DEFAULT '',  -- 그때 적힌 이름 (명단이 바뀌어도 남는다)
    role        TEXT NOT NULL DEFAULT '',  -- 그때의 역할
    channel     TEXT NOT NULL DEFAULT 'email',
    direction   TEXT NOT NULL DEFAULT 'out',
    memo        TEXT NOT NULL,
    owner       TEXT NOT NULL DEFAULT '',  -- 우리 쪽 담당
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_log_customer ON contact_log(customer_id);
"""


def _conn():
    conn = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        conn.commit()
        _local.conn = conn
    return conn


def init_db():
    _conn()


def _now():
    return datetime.now(SEOUL)


def today_iso():
    return _now().date().isoformat()


def _clean(value, limit):
    return (str(value or "").strip())[:limit]


def channels():
    return [dict(CHANNELS[key], value=key) for key in CHANNEL_ORDER]


def _decorate(row):
    item = dict(row)
    item["channel_meta"] = CHANNELS.get(item["channel"], CHANNELS["other"])
    item["direction_meta"] = DIRECTIONS.get(item["direction"], DIRECTIONS["out"])
    return item


def add(customer_id, data):
    """연락 한 줄. 메모가 비면 넣지 않는다 (날짜만 남은 줄은 쓸모가 없다)."""
    memo = _clean(data.get("memo"), MEMO_LIMIT)
    if not memo:
        return False

    channel = data.get("channel")
    direction = data.get("direction")
    _conn().execute(
        """INSERT INTO contact_log (customer_id, at, contact_id, person, role,
                                    channel, direction, memo, owner, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (_clean(customer_id, 60),
         _clean(data.get("at"), 10) or today_iso(),
         data.get("contact_id") or None,
         _clean(data.get("person"), 60),
         _clean(data.get("role"), 40),
         channel if channel in CHANNELS else "email",
         direction if direction in DIRECTIONS else "out",
         memo,
         _clean(data.get("owner"), 40),
         _now().strftime("%Y-%m-%d %H:%M:%S")))
    _conn().commit()
    return True


def remove(log_id, customer_id):
    """잘못 적은 줄을 지운다. 남의 고객사 기록을 지우지 못하게 같이 건다."""
    cur = _conn().execute("DELETE FROM contact_log WHERE id = ? AND customer_id = ?",
                          (log_id, _clean(customer_id, 60)))
    _conn().commit()
    return cur.rowcount > 0


def of_customer(customer_id, limit=None):
    sql = ("SELECT * FROM contact_log WHERE customer_id = ? "
           "ORDER BY at DESC, id DESC")
    args = [_clean(customer_id, 60)]
    if limit:
        sql += " LIMIT ?"
        args.append(int(limit))
    return [_decorate(row) for row in _conn().execute(sql, args)]


def last_of(customer_id):
    rows = of_customer(customer_id, limit=1)
    return rows[0] if rows else None


def counts():
    """고객사별 건수. 목록 화면에서 한 번에 쓴다."""
    return {row["customer_id"]: row["n"] for row in _conn().execute(
        "SELECT customer_id, COUNT(*) AS n FROM contact_log GROUP BY customer_id")}
