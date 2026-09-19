# -*- coding: utf-8 -*-
"""거래처 저장소.

고객사만 관리하면 안 된다. 해외영업 한 건이 돌아가려면 파는 쪽(바이어·현지
에이전트)과 사는 쪽(원료사·부자재·임가공·포워더·시험기관)이 같이 움직인다.
바이어 연락처만 정리해 두고 임가공 업체 담당자는 메신저를 뒤지는 게 실제 모습이다.

그래서 회사마다 **유형(kind)** 을 붙인다. 등급(VIP·일반·신규)은 파는 쪽에만
의미가 있어서 사는 쪽에는 띄우지 않는다.

원래 이름은 "엑셀로 올린 고객사 저장소" 였다.

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

# ---------------------------------------------------------------------------
# 거래처 유형
# ---------------------------------------------------------------------------
#   side 로 파는 쪽·사는 쪽을 가른다. 같은 '거래처' 라도 챙기는 게 다르다.
#   파는 쪽은 등급·요청사항·견적이 중요하고,
#   사는 쪽은 납기·단가·품질 문제 이력이 중요하다.

KINDS = [
    {"value": "buyer", "label": "고객사 (바이어)", "icon": "🛍️", "side": "sell",
     "desc": "우리가 파는 쪽. 발주를 넣는 해외 브랜드·유통사"},
    {"value": "agent", "label": "현지 에이전트·유통", "icon": "🌏", "side": "sell",
     "desc": "현지 수입자, EU 책임자(RP), 중국 경내책임자 등"},
    {"value": "vendor", "label": "원료·부자재 공급처", "icon": "🧴", "side": "buy",
     "desc": "벌크 원료, 용기·펌프·단상자를 대는 곳"},
    {"value": "subcon", "label": "하청·임가공", "icon": "🏭", "side": "buy",
     "desc": "충전·포장 등 우리 대신 만드는 곳"},
    {"value": "logistics", "label": "물류·포워더", "icon": "🚢", "side": "buy",
     "desc": "선적·통관·내륙 운송을 맡는 곳"},
    {"value": "lab", "label": "시험·인증기관", "icon": "🔬", "side": "buy",
     "desc": "안정성·미생물 시험, 인증 심사기관"},
    {"value": "other", "label": "기타", "icon": "🏢", "side": "",
     "desc": "위에 해당하지 않는 거래처"},
]
KIND_MAP = {row["value"]: row for row in KINDS}
KIND_ORDER = [row["value"] for row in KINDS]
DEFAULT_KIND = "buyer"

# 등급을 띄울 유형. 임가공 업체에 'VIP 고객사' 라고 적히면 우습다.
GRADED_KINDS = {"buyer", "agent"}


def kind_meta(value):
    return KIND_MAP.get(value or "", KIND_MAP[DEFAULT_KIND])


def kinds():
    return [dict(row) for row in KINDS]

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
    kind       TEXT NOT NULL DEFAULT 'buyer',
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


# 나중에 붙인 칸. 이미 만들어진 DB 에도 넣어 줘야 한다.
LATE_COLUMNS = [("kind", "TEXT NOT NULL DEFAULT 'buyer'")]


def _add_missing_columns(conn):
    have = {row["name"] for row in conn.execute("PRAGMA table_info(customers)")}
    for column, decl in LATE_COLUMNS:
        if column not in have:
            conn.execute("ALTER TABLE customers ADD COLUMN {} {}".format(column, decl))
    conn.commit()


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()
    _add_missing_columns(conn)


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
        "kind": data.get("kind") or DEFAULT_KIND,
        "kind_meta": kind_meta(data.get("kind")),
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
        # 엑셀로 올린 것과 화면에서 직접 넣은 것을 구분한다
        "imported": True,
        "source": data.get("source") or "excel",
        "created_at": data["created_at"],
    }


# ---------------------------------------------------------------------------
# 조회
# ---------------------------------------------------------------------------

def all_rows():
    conn = connect()
    return [dict(r) for r in conn.execute(
        "SELECT * FROM customers ORDER BY created_at DESC, name ASC")]


def profiles(keyword="", grade="all", kind="all"):
    """등록된 거래처를 카드 모양으로. (더미 카드와 같은 키를 갖는다)"""
    rows = []
    needle = (keyword or "").strip().lower()
    for row in all_rows():
        if grade != "all" and row["grade"] != grade:
            continue
        if kind != "all" and (row["kind"] or DEFAULT_KIND) != kind:
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


def count_by_kind():
    conn = connect()
    return {row["kind"] or DEFAULT_KIND: row["n"] for row in conn.execute(
        "SELECT kind, COUNT(*) AS n FROM customers GROUP BY kind")}


# ---------------------------------------------------------------------------
# 저장
# ---------------------------------------------------------------------------

def create(data, taken_ids=()):
    """고객사 한 곳을 새로 넣는다. 반환값은 새 id."""
    conn = connect()
    stamp = now_iso()

    name = _clean(data.get("name"), "name")
    grade = (data.get("grade") or "").strip().lower()
    kind = (data.get("kind") or "").strip().lower()
    taken = set(taken_ids) | {row["id"] for row in all_rows()}

    customer_id = make_id(name, taken)
    conn.execute(
        """INSERT INTO customers
           (id, name, country, city, grade, kind, manager, channel, since, note,
            source, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (customer_id, name,
         _clean(data.get("country"), "country"), _clean(data.get("city"), "city"),
         grade if grade in GRADES else DEFAULT_GRADE,
         kind if kind in KIND_MAP else DEFAULT_KIND,
         _clean(data.get("manager"), "manager"), _clean(data.get("channel"), "channel"),
         _clean(data.get("since"), "since"), _clean(data.get("note"), "note"),
         # 엑셀로 올라온 것인지 화면에서 직접 넣은 것인지
         "manual" if data.get("source") == "manual" else "excel",
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
    kind = (data.get("kind") or "").strip().lower()
    merged["kind"] = kind if kind in KIND_MAP else (row["kind"] or DEFAULT_KIND)

    conn.execute(
        """UPDATE customers SET country = ?, city = ?, grade = ?, kind = ?,
           manager = ?, channel = ?, since = ?, note = ?, updated_at = ?
           WHERE id = ?""",
        (merged["country"], merged["city"], merged["grade"], merged["kind"],
         merged["manager"], merged["channel"], merged["since"], merged["note"],
         now_iso(), customer_id))
    conn.commit()
    return True


def delete(customer_id):
    conn = connect()
    cur = conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
    conn.commit()
    return cur.rowcount > 0
