# -*- coding: utf-8 -*-
"""고객사 담당자 저장소.

고객사 한 곳에 담당자는 보통 한 명이 아니다.
발주를 넣는 구매 담당, 성분표·인증서를 요구하는 품질 담당, 선적 서류를 챙기는
물류 담당이 따로 있고, 메일을 누구에게 보내느냐에 따라 회신 속도가 달라진다.
그래서 담당자를 목록으로 들고, 역할과 대표 담당자를 같이 관리한다.

이 모듈은 SQLite(data/contacts.db)를 쓴다 - 화면에서 넣은 담당자가 실제로 남는다.
처음 실행할 때만 기존 더미 고객사의 바이어를 대표 담당자로 깔아 둔다.
"""

import os
import re
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
DB_PATH = os.path.join(DATA_DIR, "contacts.db")

_local = threading.local()

# 담당자 역할 - 무역 실무에서 실제로 나뉘는 단위
#   누구에게 무엇을 보내야 하는지가 역할로 갈린다
ROLES = [
    {"value": "buyer", "label": "구매·발주", "icon": "🛒",
     "desc": "발주(PO)와 단가 협의 창구"},
    {"value": "rnd", "label": "개발·제형", "icon": "🧪",
     "desc": "처방·샘플 피드백을 주는 담당"},
    {"value": "qa", "label": "품질·인증", "icon": "🔬",
     "desc": "성분표·CoA·인증서를 요구하는 담당"},
    {"value": "logistics", "label": "물류·선적", "icon": "🚢",
     "desc": "선적 일정과 서류를 챙기는 담당"},
    {"value": "finance", "label": "대금·결제", "icon": "💳",
     "desc": "인보이스와 송금을 처리하는 담당"},
    {"value": "other", "label": "기타", "icon": "👤",
     "desc": "위에 해당하지 않는 담당"},
]
ROLE_MAP = {row["value"]: row for row in ROLES}
DEFAULT_ROLE = "buyer"

# 입력값 길이 상한 (가안이라 느슨하게 자르기만 한다)
LIMITS = {
    "name": 60, "title": 80, "email": 120, "phone": 40,
    "timezone": 60, "language": 60, "note": 500,
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT NOT NULL,
    name        TEXT NOT NULL,
    title       TEXT,
    role        TEXT NOT NULL DEFAULT 'buyer',
    email       TEXT,
    phone       TEXT,
    timezone    TEXT,
    language    TEXT,
    note        TEXT,
    is_primary  INTEGER NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_contacts_customer ON contacts(customer_id);
"""


# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------

def now_iso():
    return datetime.now(SEOUL).strftime("%Y-%m-%d %H:%M:%S")


def connect():
    conn = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    return conn


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()


def _clean(data, key):
    """폼 값 하나를 다듬는다. 공백 제거 + 길이 제한."""
    return (data.get(key) or "").strip()[:LIMITS.get(key, 200)]


def _row(row):
    d = dict(row)
    d["is_primary"] = bool(d["is_primary"])
    d["is_active"] = bool(d["is_active"])
    d["role_meta"] = ROLE_MAP.get(d["role"], ROLE_MAP["other"])
    return d


def validate(data):
    """담당자 입력값 검사. (문제가 없으면 빈 리스트)"""
    errors = []
    if not _clean(data, "name"):
        errors.append("담당자 이름은 반드시 필요합니다.")

    email = _clean(data, "email")
    if email and not _EMAIL_RE.match(email):
        errors.append("이메일 형식이 올바르지 않습니다: {}".format(email))
    return errors


# ---------------------------------------------------------------------------
# 조회
# ---------------------------------------------------------------------------

def list_contacts(customer_id, include_inactive=True):
    """고객사 한 곳의 담당자. 대표 → 활성 → 등록순."""
    conn = connect()
    sql = "SELECT * FROM contacts WHERE customer_id = ?"
    if not include_inactive:
        sql += " AND is_active = 1"
    sql += " ORDER BY is_primary DESC, is_active DESC, id ASC"
    return [_row(r) for r in conn.execute(sql, (customer_id,))]


def get_contact(contact_id):
    conn = connect()
    row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    return _row(row) if row else None


def contacts_by_customer():
    """{고객사 id: [담당자, ...]} - 목록 화면에서 한 번에 쓴다."""
    conn = connect()
    grouped = {}
    for row in conn.execute(
        "SELECT * FROM contacts ORDER BY is_primary DESC, is_active DESC, id ASC"
    ):
        grouped.setdefault(row["customer_id"], []).append(_row(row))
    return grouped


def primary_of(contacts):
    """대표 담당자. 지정이 없으면 첫 활성 담당자, 그마저 없으면 None."""
    if not contacts:
        return None
    for row in contacts:
        if row["is_primary"] and row["is_active"]:
            return row
    for row in contacts:
        if row["is_active"]:
            return row
    return contacts[0]


# ---------------------------------------------------------------------------
# 등록 · 수정
# ---------------------------------------------------------------------------

def _clear_primary(conn, customer_id, keep_id=None):
    if keep_id is None:
        conn.execute("UPDATE contacts SET is_primary = 0 WHERE customer_id = ?",
                     (customer_id,))
    else:
        conn.execute(
            "UPDATE contacts SET is_primary = 0 WHERE customer_id = ? AND id != ?",
            (customer_id, keep_id))


def add_contact(customer_id, data):
    """담당자 추가. 첫 담당자는 자동으로 대표가 된다. 반환값은 새 id."""
    conn = connect()
    stamp = now_iso()
    role = data.get("role") if data.get("role") in ROLE_MAP else DEFAULT_ROLE

    existing = conn.execute(
        "SELECT COUNT(*) FROM contacts WHERE customer_id = ?", (customer_id,)
    ).fetchone()[0]
    make_primary = bool(data.get("is_primary")) or existing == 0

    if make_primary:
        _clear_primary(conn, customer_id)

    cur = conn.execute(
        """INSERT INTO contacts
           (customer_id, name, title, role, email, phone, timezone, language,
            note, is_primary, is_active, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,1,?,?)""",
        (customer_id, _clean(data, "name"), _clean(data, "title"), role,
         _clean(data, "email"), _clean(data, "phone"), _clean(data, "timezone"),
         _clean(data, "language"), _clean(data, "note"),
         1 if make_primary else 0, stamp, stamp))
    conn.commit()
    return cur.lastrowid


def update_contact(contact_id, data):
    """담당자 수정. 없는 id 면 False."""
    conn = connect()
    current = get_contact(contact_id)
    if current is None:
        return False

    role = data.get("role") if data.get("role") in ROLE_MAP else current["role"]
    conn.execute(
        """UPDATE contacts
           SET name = ?, title = ?, role = ?, email = ?, phone = ?,
               timezone = ?, language = ?, note = ?, updated_at = ?
           WHERE id = ?""",
        (_clean(data, "name") or current["name"], _clean(data, "title"), role,
         _clean(data, "email"), _clean(data, "phone"), _clean(data, "timezone"),
         _clean(data, "language"), _clean(data, "note"), now_iso(), contact_id))

    if data.get("is_primary"):
        _clear_primary(conn, current["customer_id"], keep_id=contact_id)
        conn.execute("UPDATE contacts SET is_primary = 1 WHERE id = ?", (contact_id,))
    conn.commit()
    return True


def set_primary(contact_id):
    """대표 담당자 지정. 비활성 담당자는 대표가 될 수 없다."""
    conn = connect()
    current = get_contact(contact_id)
    if current is None or not current["is_active"]:
        return False

    _clear_primary(conn, current["customer_id"], keep_id=contact_id)
    conn.execute("UPDATE contacts SET is_primary = 1, updated_at = ? WHERE id = ?",
                 (now_iso(), contact_id))
    conn.commit()
    return True


def set_active(contact_id, active):
    """담당자 활성/비활성. 퇴사·담당 변경은 지우지 않고 비활성으로 남긴다.

    (주고받은 메일의 상대가 누구였는지는 남아야 한다)
    대표 담당자를 비활성으로 돌리면 남은 담당자 중 한 명이 대표를 이어받는다.
    """
    conn = connect()
    current = get_contact(contact_id)
    if current is None:
        return False

    conn.execute("UPDATE contacts SET is_active = ?, updated_at = ? WHERE id = ?",
                 (1 if active else 0, now_iso(), contact_id))

    if not active and current["is_primary"]:
        conn.execute("UPDATE contacts SET is_primary = 0 WHERE id = ?", (contact_id,))
        heir = conn.execute(
            """SELECT id FROM contacts
               WHERE customer_id = ? AND is_active = 1 AND id != ?
               ORDER BY id ASC LIMIT 1""",
            (current["customer_id"], contact_id)).fetchone()
        if heir:
            conn.execute("UPDATE contacts SET is_primary = 1 WHERE id = ?", (heir["id"],))
    conn.commit()
    return True


def delete_contact(contact_id):
    """담당자 삭제. 잘못 넣은 행을 지우는 용도 (담당 변경은 비활성을 쓴다)."""
    conn = connect()
    current = get_contact(contact_id)
    if current is None:
        return False

    conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
    if current["is_primary"]:
        heir = conn.execute(
            """SELECT id FROM contacts
               WHERE customer_id = ? AND is_active = 1 ORDER BY id ASC LIMIT 1""",
            (current["customer_id"],)).fetchone()
        if heir:
            conn.execute("UPDATE contacts SET is_primary = 1 WHERE id = ?", (heir["id"],))
    conn.commit()
    return True


# ---------------------------------------------------------------------------
# 최초 1회 시드
#   기존 더미 고객사에 있던 바이어 한 명을 대표 담당자로 옮겨 놓는다.
#   (담당자 탭이 텅 빈 채로 시작하지 않도록)
# ---------------------------------------------------------------------------

# 더미 데이터의 메일 발신자 중 바이어가 아닌 사람 - 두 번째 담당자로 깔아 둔다
_EXTRA_SEED = {
    "glowtree": {
        "name": "Daniel Cho", "title": "QA Manager", "role": "qa",
        "email": "daniel.cho@glowtree-beauty.com", "phone": "+1 213-555-0152",
        "timezone": "PST (한국 −16시간)", "language": "English",
        "note": "처방 수정본 승인과 인증서 요청은 이쪽에서 옵니다.",
    },
}


def _seed_rows(profiles):
    """시드로 넣을 담당자 행. (프로필의 buyer + 더미 메일에 나오던 담당자)"""
    rows = []
    for profile in profiles:
        buyer = profile.get("buyer") or {}
        if not buyer.get("name"):
            continue
        rows.append((profile["id"], {
            "name": buyer.get("name"),
            "title": buyer.get("title"),
            "role": DEFAULT_ROLE,
            "email": buyer.get("email"),
            "phone": buyer.get("phone"),
            "timezone": buyer.get("timezone"),
            "language": buyer.get("language"),
        }, True))

        extra = _EXTRA_SEED.get(profile["id"])
        if extra:
            rows.append((profile["id"], extra, False))
    return rows


def seed_from_profiles(profiles):
    """고객사 더미 프로필의 buyer 를 대표 담당자로 심는다. (비어 있을 때만)

    여러 워커가 동시에 뜨면 둘 다 '비어 있다'고 보고 두 번 심을 수 있어서
    BEGIN IMMEDIATE 로 한 번에 하나만 들어가게 한다.
    """
    conn = connect()
    stamp = now_iso()
    conn.execute("BEGIN IMMEDIATE")
    try:
        if conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]:
            conn.rollback()
            return 0

        rows = _seed_rows(profiles)
        conn.executemany(
            """INSERT INTO contacts
               (customer_id, name, title, role, email, phone, timezone, language,
                note, is_primary, is_active, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,1,?,?)""",
            [(customer_id, _clean(data, "name"), _clean(data, "title"),
              data.get("role") if data.get("role") in ROLE_MAP else DEFAULT_ROLE,
              _clean(data, "email"), _clean(data, "phone"), _clean(data, "timezone"),
              _clean(data, "language"), _clean(data, "note"),
              1 if primary else 0, stamp, stamp)
             for customer_id, data, primary in rows])
        conn.commit()
        return len(rows)
    except Exception:                                # noqa: BLE001
        conn.rollback()
        raise
