# -*- coding: utf-8 -*-
"""엑셀로 올린 고객사 저장소.

기존 고객사 카드(`dummy_data._CUSTOMER_PROFILES`)는 더미다. 엑셀에서 올라온
회사는 더미에 없으니 어딘가에 실제로 담아야 하고, 그게 이 모듈이다.
SQLite(data/customers.db)를 쓴다 - 담당자 저장소(contact_store)와 같은 방식.

고객사 카드는 요청사항·메일 이력까지 들고 있지만 엑셀에는 회사·담당자·연락처만
들어온다. 없는 값을 지어내지 않고 빈 채로 두고, 화면에서 "엑셀로 등록"이라고
밝힌다. 나머지는 사람이 채우는 자리다.
"""

import os
import re
import sqlite3
import threading
import unicodedata
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
    SEOUL = ZoneInfo("Asia/Seoul")
except Exception:                                    # noqa: BLE001
    SEOUL = timezone.utc

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "customers.db")

_local = threading.local()

LIMITS = {"name": 120, "country": 40, "city": 60, "manager": 40,
          "channel": 80, "note": 500, "grade": 12, "since": 10}

GRADES = ("vip", "regular", "new")
DEFAULT_GRADE = "new"

# 국가 이름 -> 국기. 엑셀에 국기까지 적어 달라고 할 수는 없다.
COUNTRY_FLAGS = {
    "미국": "🇺🇸", "중국": "🇨🇳", "일본": "🇯🇵", "홍콩": "🇭🇰", "대만": "🇹🇼",
    "베트남": "🇻🇳", "태국": "🇹🇭", "싱가포르": "🇸🇬", "말레이시아": "🇲🇾",
    "인도네시아": "🇮🇩", "필리핀": "🇵🇭", "인도": "🇮🇳", "호주": "🇦🇺",
    "뉴질랜드": "🇳🇿", "캐나다": "🇨🇦", "멕시코": "🇲🇽", "브라질": "🇧🇷",
    "영국": "🇬🇧", "프랑스": "🇫🇷", "독일": "🇩🇪", "이탈리아": "🇮🇹",
    "스페인": "🇪🇸", "네덜란드": "🇳🇱", "폴란드": "🇵🇱", "러시아": "🇷🇺",
    "우크라이나": "🇺🇦", "카자흐스탄": "🇰🇿", "튀르키예": "🇹🇷",
    "아랍에미리트": "🇦🇪", "사우디아라비아": "🇸🇦", "이스라엘": "🇮🇱",
    "대한민국": "🇰🇷", "한국": "🇰🇷",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    country    TEXT,
    city       TEXT,
    grade      TEXT NOT NULL DEFAULT 'new',
    manager    TEXT,
    channel    TEXT,
    since      TEXT,
    note       TEXT,
    source     TEXT NOT NULL DEFAULT 'excel',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_key ON customers(name COLLATE NOCASE);
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


def norm_name(name):
    """회사명 비교용 표기. 대소문자·공백·전각 차이로 같은 회사를 둘로 만들지 않는다."""
    text = unicodedata.normalize("NFKC", (name or "")).strip().lower()
    return re.sub(r"\s+", " ", text)


def make_id(name, taken):
    """회사명에서 고객사 id 를 만든다. 겹치면 뒤에 번호를 붙인다."""
    slug = unicodedata.normalize("NFKD", (name or ""))
    slug = slug.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")[:28]
    if not slug:
        # 한글·중국어만 있는 이름이면 알파벳이 남지 않는다
        slug = "cust-{:x}".format(abs(hash(norm_name(name))) % 0xFFFFF)

    candidate = slug
    n = 2
    while candidate in taken:
        candidate = "{}-{}".format(slug, n)
        n += 1
    return candidate


def _clean(value, key):
    return (str(value) if value is not None else "").strip()[:LIMITS.get(key, 200)]


def blank_profile(row):
    """엑셀에서 올라온 회사를 고객사 카드 모양으로 맞춘다.

    요청사항·메일·거래 통계는 엑셀에 없다. 0 이나 빈 목록으로 두고,
    화면에서 "엑셀로 등록"이라고 밝힌다. 지어내지 않는다.
    """
    data = dict(row)
    return {
        "id": data["id"],
        "name": data["name"],
        "country": data["country"] or "",
        "flag": COUNTRY_FLAGS.get(data["country"] or "", "🏳"),
        "city": data["city"] or "",
        "grade": data["grade"] if data["grade"] in GRADES else DEFAULT_GRADE,
        "manager": data["manager"] or "",
        "since": data["since"] or "",
        "last_contact": "",
        "channel": data["channel"] or "",
        "buyer": {"name": "", "title": "", "email": "", "phone": "",
                  "timezone": "", "language": ""},
        "tags": [],
        "stats": {"orders": 0, "amount": "—", "active": 0, "avg_reply": "—"},
        "requests": [],
        "emails": [],
        "projects": [],
        "notes": [],
        "history": [],
        "note": data["note"] or "",
        "imported": True,                 # 화면에서 더미 카드와 구분하는 표시
        "created_at": data["created_at"],
    }


# ---------------------------------------------------------------------------
# 조회
# ---------------------------------------------------------------------------

def all_rows():
    conn = connect()
    return [dict(r) for r in conn.execute(
        "SELECT * FROM customers ORDER BY created_at DESC, name ASC")]


def profiles(keyword="", grade="all"):
    """엑셀로 등록된 고객사를 카드 모양으로. (더미 카드와 같은 키를 갖는다)"""
    rows = []
    needle = (keyword or "").strip().lower()
    for row in all_rows():
        if grade != "all" and row["grade"] != grade:
            continue
        if needle and needle not in " ".join(
                [row["name"], row["country"] or ""]).lower():
            continue
        rows.append(blank_profile(row))
    return rows


def profile(customer_id):
    conn = connect()
    row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    return blank_profile(row) if row else None


def find_by_name(name):
    """회사명으로 찾기. 표기 차이를 무시한다."""
    key = norm_name(name)
    if not key:
        return None
    for row in all_rows():
        if norm_name(row["name"]) == key:
            return row
    return None


def count():
    conn = connect()
    return conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]


# ---------------------------------------------------------------------------
# 저장
# ---------------------------------------------------------------------------

def create(data, taken_ids=()):
    """고객사 한 곳을 새로 넣는다. 반환값은 새 id."""
    conn = connect()
    stamp = now_iso()

    name = _clean(data.get("name"), "name")
    grade = (data.get("grade") or "").strip().lower()
    taken = set(taken_ids) | {row["id"] for row in all_rows()}

    customer_id = make_id(name, taken)
    conn.execute(
        """INSERT INTO customers
           (id, name, country, city, grade, manager, channel, since, note,
            source, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,'excel',?,?)""",
        (customer_id, name,
         _clean(data.get("country"), "country"), _clean(data.get("city"), "city"),
         grade if grade in GRADES else DEFAULT_GRADE,
         _clean(data.get("manager"), "manager"), _clean(data.get("channel"), "channel"),
         _clean(data.get("since"), "since"), _clean(data.get("note"), "note"),
         stamp, stamp))
    conn.commit()
    return customer_id


def update(customer_id, data):
    """빈 칸은 건드리지 않는다. 엑셀에 안 적었다고 지우면 안 된다."""
    conn = connect()
    row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if row is None:
        return False

    merged = {}
    for key in ("country", "city", "manager", "channel", "since", "note"):
        merged[key] = _clean(data.get(key), key) or (row[key] or "")

    grade = (data.get("grade") or "").strip().lower()
    merged["grade"] = grade if grade in GRADES else row["grade"]

    conn.execute(
        """UPDATE customers SET country = ?, city = ?, grade = ?, manager = ?,
           channel = ?, since = ?, note = ?, updated_at = ? WHERE id = ?""",
        (merged["country"], merged["city"], merged["grade"], merged["manager"],
         merged["channel"], merged["since"], merged["note"], now_iso(), customer_id))
    conn.commit()
    return True


def delete(customer_id):
    conn = connect()
    cur = conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
    conn.commit()
    return cur.rowcount > 0
