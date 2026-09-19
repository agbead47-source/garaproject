# -*- coding: utf-8 -*-
"""자사 정보 - 모든 서류에 똑같이 들어가는 값.

견적서·프로포마 인보이스·커머셜 인보이스·패킹리스트·원산지증명 신청·
바이어의 거래처 등록 양식(vendor registration). 여기 들어가는 회사 정보는
전부 같은 값이다. 그런데 매번 예전 메일을 열어 복사해 쓰다 보니
영문 주소가 서류마다 조금씩 다르고, 그게 통관에서 걸린다.

그래서 한 군데 적어 두고 서류가 여기서 읽어 간다.

**영문 표기가 진짜다.** 국문 상호·주소는 우리끼리 보는 것이고,
서류에 찍혀 나가는 건 영문이다. 영문 칸이 비면 서류를 만들 수 없다.

민감한 값이 하나 있다. **은행 계좌**다.
바이어에게 주는 값이긴 하지만 화면에 그냥 깔아 두지 않는다.
  - 목록에서는 가려 두고 눌러야 보인다
  - 견적서에는 자동으로 넣지 않는다 (송금 정보는 인보이스에 들어간다)
  - 사기 메일로 계좌만 바꿔치기하는 수법이 흔해서, 바꿀 때 기록을 남긴다
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
DB_PATH = os.path.join(DATA_DIR, "company.db")

_local = threading.local()


# ---------------------------------------------------------------------------
# 칸
# ---------------------------------------------------------------------------
#   used : 이 값이 실제로 어느 서류에 들어가는가.
#          "왜 채워야 하나" 에 대한 답이라 화면에 같이 적는다.
#   doc  : True 면 서류에 그대로 찍혀 나가는 칸. 비면 서류를 못 만든다.

GROUPS = [
    {
        "key": "basic", "label": "회사", "icon": "🏢",
        "desc": "모든 서류 머리말에 들어갑니다.",
        "fields": [
            {"key": "name", "label": "국문 상호", "used": "내부·국내 서류", "limit": 120},
            {"key": "name_en", "label": "영문 상호", "doc": True, "limit": 120,
             "used": "견적서 · 인보이스 · C/O", "hint": "법인등기 영문명 그대로"},
            {"key": "ceo", "label": "대표자 (국문)", "used": "내부", "limit": 60},
            {"key": "ceo_en", "label": "대표자 (영문)", "doc": True, "limit": 60,
             "used": "견적서 서명란 · 인보이스"},
            {"key": "biz_no", "label": "사업자등록번호", "doc": True, "limit": 20,
             "used": "견적서 · 세금계산서 · C/O", "hint": "000-00-00000"},
            {"key": "corp_no", "label": "법인등록번호", "used": "계약서", "limit": 24},
        ],
    },
    {
        "key": "address", "label": "주소", "icon": "📍",
        "desc": "영문 주소가 서류에 그대로 찍힙니다. 서류마다 다르면 통관에서 걸립니다.",
        "fields": [
            {"key": "address", "label": "본사 주소 (국문)", "used": "내부", "limit": 200},
            {"key": "address_en", "label": "본사 주소 (영문)", "doc": True, "limit": 200,
             "used": "견적서 · 인보이스 · C/O · 해외 등록",
             "hint": "우편번호와 Republic of Korea 까지"},
            {"key": "factory", "label": "공장 주소 (국문)", "used": "내부", "limit": 200},
            {"key": "factory_en", "label": "공장 주소 (영문)", "doc": True, "limit": 200,
             "used": "MoCRA 시설등록 · CPNP · 실사",
             "hint": "제조소 등록에 쓰는 주소입니다. 본사와 다를 수 있습니다"},
        ],
    },
    {
        "key": "contact", "label": "연락", "icon": "📞",
        "desc": "바이어가 서류를 보고 연락하는 창구입니다.",
        "fields": [
            {"key": "tel", "label": "대표 전화", "doc": True, "limit": 40,
             "used": "견적서 · 인보이스", "hint": "+82-2-0000-0000"},
            {"key": "fax", "label": "팩스", "used": "일부 국가 서류", "limit": 40},
            {"key": "email", "label": "대표 이메일", "doc": True, "limit": 120,
             "used": "견적서 · 인보이스"},
            {"key": "website", "label": "홈페이지", "used": "바이어 등록 양식", "limit": 120},
        ],
    },
    {
        "key": "trade", "label": "수출", "icon": "🚢",
        "desc": "통관·원산지증명에 들어갑니다.",
        "fields": [
            {"key": "trade_no", "label": "무역업고유번호", "doc": True, "limit": 24,
             "used": "수출신고 · C/O", "hint": "한국무역협회 발급"},
            {"key": "customs_no", "label": "수출자부호", "used": "수출신고", "limit": 24},
            {"key": "origin", "label": "원산지 표기", "doc": True, "limit": 60,
             "used": "라벨 · C/O · 인보이스", "hint": "Made in Korea"},
            {"key": "hs_codes", "label": "주요 HS 코드", "limit": 200,
             "used": "수출신고 · 관세율 확인",
             "hint": "예: 3304.99 (기초화장품), 3307.90"},
            {"key": "port", "label": "주요 선적항", "limit": 60,
             "used": "인보이스 · B/L", "hint": "Busan, Korea"},
        ],
    },
    {
        "key": "bank", "label": "대금 수취 (T/T)", "icon": "💳",
        "desc": "바이어가 송금할 계좌입니다. 인보이스에 들어갑니다. "
                "견적서에는 넣지 않습니다.",
        "sensitive": True,
        "fields": [
            {"key": "bank_name", "label": "은행명 (영문)", "limit": 120,
             "used": "프로포마·커머셜 인보이스", "hint": "KEB HANA BANK"},
            {"key": "bank_branch", "label": "지점 (영문)", "limit": 120, "used": "인보이스"},
            {"key": "bank_address", "label": "은행 주소 (영문)", "limit": 200,
             "used": "인보이스", "hint": "일부 은행이 요구합니다"},
            {"key": "swift", "label": "SWIFT 코드", "limit": 24,
             "used": "인보이스", "hint": "영문 8자리 또는 11자리"},
            {"key": "account_no", "label": "계좌번호", "limit": 40, "used": "인보이스"},
            {"key": "account_name", "label": "예금주 (영문)", "limit": 120,
             "used": "인보이스", "hint": "영문 상호와 같아야 송금이 막히지 않습니다"},
        ],
    },
    {
        "key": "sales", "label": "해외영업 담당", "icon": "🙋",
        "desc": "견적서·메일 서명에 들어갑니다.",
        "fields": [
            {"key": "sales_name", "label": "담당자 (국문)", "used": "내부", "limit": 60},
            {"key": "sales_name_en", "label": "담당자 (영문)", "doc": True, "limit": 60,
             "used": "견적서 발행자 · 메일 서명"},
            {"key": "sales_title_en", "label": "직급 (영문)", "limit": 60,
             "used": "메일 서명", "hint": "Overseas Sales Manager"},
            {"key": "sales_email", "label": "담당자 이메일", "doc": True, "limit": 120,
             "used": "견적서 · 메일"},
            {"key": "sales_tel", "label": "담당자 전화", "limit": 40, "used": "메일 서명"},
        ],
    },
]

GROUP_MAP = {row["key"]: row for row in GROUPS}
FIELDS = [dict(f, group=g["key"], sensitive=bool(g.get("sensitive")))
          for g in GROUPS for f in g["fields"]]
FIELD_MAP = {row["key"]: row for row in FIELDS}
DOC_FIELDS = [row["key"] for row in FIELDS if row.get("doc")]
SENSITIVE_FIELDS = [row["key"] for row in FIELDS if row["sensitive"]]

# 가안이라 깔아 두는 예시값. **예시라고 화면에 적는다.**
SAMPLE = {
    "name": "주식회사 투두트레이드",
    "name_en": "TO-DO TRADE CO., LTD.",
    "ceo": "김무역", "ceo_en": "Kim Moo-yeok",
    "biz_no": "123-45-67890",
    "address": "서울특별시 강남구 테헤란로 123, 8층",
    "address_en": "8F, 123 Teheran-ro, Gangnam-gu, Seoul 06234, Republic of Korea",
    "factory": "충청북도 청주시 흥덕구 산단로 45",
    "factory_en": "45 Sandan-ro, Heungdeok-gu, Cheongju, Chungcheongbuk-do, "
                  "Republic of Korea",
    "tel": "+82-2-1234-5678",
    "email": "sales@todotrade.co.kr",
    "website": "www.todotrade.co.kr",
    "origin": "Made in Korea",
    "hs_codes": "3304.99 (기초화장품) · 3307.90 (기타 화장품)",
    "port": "Busan, Korea",
    "sales_name": "홍길동",
    "sales_name_en": "Hong Gil-dong",
    "sales_title_en": "Overseas Sales Manager",
    "sales_email": "gildong.hong@todotrade.co.kr",
}

# 견적서 직인 이미지 (static/). 실제 운영에서는 스캔한 법인 직인으로 바꾼다.
SEAL_FILE = "seal.svg"


SCHEMA = """
CREATE TABLE IF NOT EXISTS company (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bank_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    field      TEXT NOT NULL,
    at         TEXT NOT NULL,
    who        TEXT NOT NULL DEFAULT ''
);
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
    return datetime.now(SEOUL).strftime("%Y-%m-%d %H:%M:%S")


def stored():
    """담당자가 실제로 넣은 값만."""
    return {row["key"]: row["value"] for row in
            _conn().execute("SELECT key, value FROM company") if row["value"]}


def values():
    """서류가 읽어 갈 값. 입력값이 없으면 예시값으로 채운다."""
    saved = stored()
    out = {}
    for row in FIELDS:
        out[row["key"]] = saved.get(row["key"]) or SAMPLE.get(row["key"], "")
    out["seal_file"] = SEAL_FILE
    return out


def state_of(key, saved=None):
    """이 칸의 값이 어디서 왔나. 예시를 입력값으로 착각하면 안 된다."""
    saved = stored() if saved is None else saved
    if saved.get(key):
        return "user"
    if SAMPLE.get(key):
        return "sample"
    return "empty"


def save(data, who=""):
    """넣은 값을 저장한다. 빈 칸은 '지우기' 로 본다 (예시값으로 되돌아간다)."""
    conn = _conn()
    before = stored()
    changed = []
    for row in FIELDS:
        key = row["key"]
        if key not in data:
            continue
        value = (str(data.get(key) or "")).strip()[:row["limit"]]
        if value == before.get(key, ""):
            continue
        conn.execute(
            "INSERT INTO company (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "updated_at = excluded.updated_at", (key, value, _now()))
        changed.append(key)

    # 계좌가 바뀐 건 따로 남긴다. 사기 메일로 계좌만 바꿔치기하는 수법이 흔하다
    for key in changed:
        if key in SENSITIVE_FIELDS:
            conn.execute("INSERT INTO bank_log (field, at, who) VALUES (?,?,?)",
                         (FIELD_MAP[key]["label"], _now(), (who or "")[:40]))
    conn.commit()
    return changed


def bank_history(limit=10):
    return [dict(r) for r in _conn().execute(
        "SELECT * FROM bank_log ORDER BY id DESC LIMIT ?", (limit,))]


def board():
    """화면 한 장. 칸마다 값이 어디서 왔는지를 같이 들고 간다."""
    saved = stored()
    live = values()
    groups = []
    for group in GROUPS:
        rows = []
        for field in group["fields"]:
            key = field["key"]
            rows.append(dict(
                field,
                value=live.get(key, ""),
                saved=saved.get(key, ""),
                state=state_of(key, saved),
                sensitive=bool(group.get("sensitive")),
            ))
        groups.append(dict(group, rows=rows))

    # 서류에 찍혀 나가는 칸 중 진짜로 비어 있는 것
    missing = [FIELD_MAP[k]["label"] for k in DOC_FIELDS if not live.get(k)]
    # 예시값 그대로인 칸. 이대로 서류를 내보내면 남의 회사 이름이 나간다
    sample_left = [FIELD_MAP[k]["label"] for k in DOC_FIELDS
                   if state_of(k, saved) == "sample"]

    return {
        "groups": groups,
        "values": live,
        "saved_count": len(saved),
        "doc_total": len(DOC_FIELDS),
        "missing": missing,
        "sample_left": sample_left,
        "ready": not missing and not sample_left,
        "bank_history": bank_history(),
    }
