# -*- coding: utf-8 -*-
"""프로젝트 - 한 건의 해외영업 업무를 처음부터 끝까지 묶는 축.

지금까지 만든 화면은 각각 잘 돌지만 서로 남남이었다. 요청서를 분석한 결과가
견적 화면으로 이어지지 않고, 샘플 피드백은 어디에도 안 남고, 일정은 따로 놀았다.
이 모듈은 그 사이를 잇는다.

    바이어 요청 접수 → 요청서 분석 → 바이어 확인사항 → 연구소·공장 전달
    → 샘플 제작·피드백 → 견적 비교 → 일정 관리 → 후속 연락

**완성형 서비스가 아니라 업무 흐름을 검증하는 시제품이다.** 그래서 화면을 예쁘게
만드는 것보다 두 가지를 우선한다.

  1) 한 프로젝트 안에서 다음 화면으로 이어지는가
  2) 지금 보고 있는 값이 **어디서 온 값인지** 화면에 드러나는가

두 번째가 특히 중요하다. 시제품에서 제일 위험한 건 예시로 깔아 둔 숫자를
확정값으로 착각하는 것이다. 그래서 모든 값에 상태(VALUE_STATES)를 붙인다.

일정은 새로 만들지 않고 기존 일정관리(schedule_store)에 건을 만들어 연결한다.
단계(PHASES)가 이미 이 업무 흐름과 같기 때문이다.
"""

import json
import os
import re
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    SEOUL = ZoneInfo("Asia/Seoul")
except Exception:                                    # noqa: BLE001
    SEOUL = timezone.utc

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "projects.db")

_local = threading.local()


# ---------------------------------------------------------------------------
# 값의 상태 - 이 시제품의 뼈대
# ---------------------------------------------------------------------------
#   화면에 뜬 숫자가 고객이 준 값인지, 우리가 깔아 둔 예시인지 구분되지 않으면
#   시제품으로 업무 흐름을 검증할 수가 없다. 그래서 값마다 상태를 붙인다.

VALUE_STATES = {
    "example": {"label": "예시 데이터", "css": "example", "rank": 0,
                "desc": "시연용으로 깔아 둔 값입니다. 실제 값이 아닙니다"},
    "default": {"label": "기본값", "css": "default", "rank": 1,
                "desc": "시스템 기본값입니다. 확인하고 고쳐 쓰세요"},
    "analysis": {"label": "분석 결과", "css": "analysis", "rank": 2,
                 "desc": "요청서에서 읽어낸 값입니다"},
    "check": {"label": "확인 필요", "css": "check", "rank": 3,
              "desc": "빠졌거나 애매해서 바이어·담당자 확인이 필요합니다"},
    "user": {"label": "사용자 입력", "css": "user", "rank": 4,
             "desc": "담당자가 직접 넣은 값입니다"},
    "confirmed": {"label": "확정값", "css": "confirmed", "rank": 5,
                  "desc": "양쪽이 합의해 확정한 값입니다"},
}
STATE_ORDER = ["example", "default", "analysis", "check", "user", "confirmed"]


def state_meta(key):
    return dict(VALUE_STATES.get(key, VALUE_STATES["default"]), key=key)


# ---------------------------------------------------------------------------
# 업무 흐름 단계
# ---------------------------------------------------------------------------
#   done_when 은 "이 단계가 끝났다고 볼 수 있는 조건"이다. 사람이 체크하는 게
#   아니라 실제로 값이 들어왔는지로 판정한다. 시제품의 진행률은 그래야 믿을 수 있다.

STAGES = [
    {"key": "intake", "label": "요청 접수", "icon": "📥",
     "desc": "바이어 요청을 받아 프로젝트를 연다"},
    {"key": "analysis", "label": "요청서 분석", "icon": "🔍",
     "desc": "원문에서 제품 조건을 읽어낸다"},
    {"key": "questions", "label": "확인사항 정리", "icon": "❓",
     "desc": "빠진 조건을 모아 바이어에게 묻는다"},
    {"key": "handoff", "label": "연구소·공장 전달", "icon": "📤",
     "desc": "받는 쪽이 쓰는 문서로 바꿔 넘긴다"},
    {"key": "sample", "label": "샘플·피드백", "icon": "🧪",
     "desc": "샘플을 만들고 피드백을 받는다"},
    {"key": "quote", "label": "견적 비교", "icon": "💰",
     "desc": "조건을 바꿔 가며 단가를 비교한다"},
    {"key": "schedule", "label": "일정 관리", "icon": "🗓",
     "desc": "샘플·생산·선적 일정을 건다"},
    {"key": "followup", "label": "후속 연락", "icon": "✉️",
     "desc": "회신하고 다음 연락일을 잡는다"},
]
STAGE_MAP = {s["key"]: s for s in STAGES}
STAGE_KEYS = [s["key"] for s in STAGES]

STATUS_META = {
    "active": {"label": "진행 중", "css": "ok"},
    "hold": {"label": "보류", "css": "warn"},
    "won": {"label": "수주", "css": "confirmed"},
    # '종료' 라고만 적으면 수주하고 끝난 건과 구분이 안 된다
    "lost": {"label": "무산", "css": "none"},
}

# ---------------------------------------------------------------------------
# 무산 사유
# ---------------------------------------------------------------------------
#   왜 안 갔는지를 안 적으면 내년에 같은 회사와 같은 일을 처음부터 다시 한다.
#
#   signal=True 는 **체리피커로 의심할 만한 사유**다.
#   단가가 안 맞아 무산된 건 정상적인 협상 결과지 체리피커가 아니다.
#   이 구분이 없으면 멀쩡한 고객사까지 싸잡게 된다.

DROP_REASONS = [
    {"value": "no_reply", "label": "연락 두절", "signal": True,
     "hint": "견적·샘플을 보낸 뒤 회신이 끊긴 경우"},
    {"value": "info_only", "label": "정보만 받아감", "signal": True,
     "hint": "진행 의사 없이 단가·처방·성분표만 받아간 것으로 보이는 경우"},
    {"value": "repeat_sample", "label": "샘플만 반복 수령", "signal": True,
     "hint": "샘플을 여러 차례 받고도 발주 논의로 넘어가지 않은 경우"},
    {"value": "price", "label": "단가 합의 실패", "signal": False,
     "hint": "정상적인 협상 결과입니다"},
    {"value": "moq", "label": "수량(MOQ) 미달", "signal": False, "hint": ""},
    {"value": "spec", "label": "사양·처방 불일치", "signal": False, "hint": ""},
    {"value": "regulation", "label": "규제·인증 문제", "signal": False,
     "hint": "성분 한도, 현지 등록 불가 등"},
    {"value": "timeline", "label": "납기 불가", "signal": False, "hint": ""},
    {"value": "competitor", "label": "타사 선정", "signal": False, "hint": ""},
    {"value": "customer_side", "label": "고객사 사정", "signal": False,
     "hint": "출시 취소, 예산 삭감, 담당자 교체 등"},
    {"value": "our_side", "label": "우리 사정", "signal": False,
     "hint": "생산 여력 부족, 수익성 미달 등"},
    {"value": "other", "label": "기타", "signal": False, "hint": ""},
]
DROP_MAP = {row["value"]: row for row in DROP_REASONS}
SIGNAL_REASONS = {row["value"] for row in DROP_REASONS if row["signal"]}

# 고객사를 어떻게 볼지. **단정하지 않는다.** 숫자를 보여주고 담당자가 판단한다.
SIGNAL_LEVELS = {
    "none": {"label": "신호 없음", "css": "ok"},
    "watch": {"label": "참고", "css": "warn"},
    "high": {"label": "주의해서 볼 신호", "css": "danger"},
}

# ---------------------------------------------------------------------------
# 제품 조건 - 프로젝트가 들고 있는 값의 목록
# ---------------------------------------------------------------------------
#   key 는 요청서 분석(dummy_data.analyze_document)의 항목 키와 맞춰 뒀다.
#   그래야 분석 결과가 그대로 프로젝트로 넘어온다.

FIELD_GROUPS = [
    {"key": "product", "label": "제품",
     "fields": [
         ("product_name", "제품명"),
         ("product_type", "제품 유형"),
         ("volume", "용량"),
         ("texture", "제형"),
         ("fragrance", "향"),
         ("key_ingredients", "핵심 성분"),
         ("free_from", "배제 성분"),
         ("claims", "표방 문구"),
         ("benchmark", "벤치마크"),
     ]},
    {"key": "package", "label": "용기·포장",
     "fields": [
         ("container", "용기"),
         ("container_supply", "용기 수급 (사급/자급)"),
         ("package_design", "패키지 디자인"),
         ("label", "라벨·표기"),
     ]},
    {"key": "commerce", "label": "거래 조건",
     "fields": [
         ("target_country", "판매 국가"),
         ("moq", "발주 수량 (MOQ)"),
         ("target_price", "목표 단가"),
         ("currency", "결제 통화"),
         ("trade_terms", "거래 조건 (Incoterms)"),
         ("payment_terms", "결제 조건"),
         ("delivery", "납기"),
     ]},
    {"key": "compliance", "label": "서류·규제",
     "fields": [
         ("documents", "요구 서류"),
         ("responsible_person", "현지 책임자"),
         ("regulation_note", "규제 메모"),
     ]},
]
FIELD_LABELS = {k: v for g in FIELD_GROUPS for k, v in g["fields"]}
FIELD_KEYS = list(FIELD_LABELS)

# ---------------------------------------------------------------------------
# 바이어 확인사항 - 견적을 내려면 반드시 있어야 하는 것들
# ---------------------------------------------------------------------------
#   실무에서 이게 비어 있으면 견적이 한 번 더 왔다 갔다 한다.
#   ask_en 은 바이어에게 그대로 보낼 수 있는 영문 문장이다.

REQUIRED_ITEMS = [
    {"key": "currency", "field": "currency", "label": "결제 통화", "priority": "high",
     "why": "통화를 안 적으면 견적서를 다시 써야 합니다.",
     "ask_en": "Which currency would you like us to quote in (USD, EUR, JPY)?"},
    {"key": "trade_terms", "field": "trade_terms", "label": "거래 조건 (Incoterms)",
     "priority": "high",
     "why": "조건에 따라 단가에 들어가는 비용 범위가 달라집니다.",
     "ask_en": "Could you confirm the Incoterms and the named place "
               "(for example FOB Busan or CIF Los Angeles)?"},
    {"key": "payment_terms", "field": "payment_terms", "label": "결제 조건",
     "priority": "high",
     "why": "선금 비율과 잔금 시점이 정해져야 생산을 겁니다.",
     "ask_en": "What payment terms do you propose? "
               "Our standard is T/T 30% with order and the balance before shipment."},
    {"key": "moq", "field": "moq", "label": "발주 수량 (MOQ)", "priority": "high",
     "why": "수량이 정해져야 단가가 나옵니다.",
     "ask_en": "Could you confirm the order quantity for the first production run?"},
    {"key": "delivery", "field": "delivery", "label": "납기", "priority": "high",
     "why": "용기 발주가 납기를 좌우합니다. 늦게 알수록 위험합니다.",
     "ask_en": "By when do you need the first shipment to arrive at your warehouse?"},
    {"key": "container", "field": "container", "label": "용기 사양", "priority": "mid",
     "why": "용기가 정해져야 금형·리드타임·단가가 정해집니다.",
     "ask_en": "Could you confirm the container and cap specification?"},
    {"key": "container_supply", "field": "container_supply",
     "label": "용기 수급 (사급/자급)", "priority": "mid",
     "why": "누가 사느냐에 따라 단가와 책임이 통째로 달라집니다.",
     "ask_en": "Will you supply the containers (buyer-supplied), "
               "or should we source them and include them in the unit price?"},
    {"key": "label", "field": "label", "label": "라벨·표기", "priority": "mid",
     "why": "판매국 표기 규정에 맞춰야 통관이 됩니다.",
     "ask_en": "Will you provide the label artwork? "
               "Please also confirm the market whose labelling rules we should follow."},
    {"key": "documents", "field": "documents", "label": "요구 서류·인증",
     "priority": "mid",
     "why": "선적 때 갑자기 요구되면 출고가 밀립니다.",
     "ask_en": "Which documents do you need with each shipment "
               "(CoA, MSDS, vegan or cruelty-free certificates)?"},
]
REQUIRED_MAP = {row["key"]: row for row in REQUIRED_ITEMS}

QUESTION_STATUS = {
    "open": {"label": "확인 필요", "css": "check"},
    "asked": {"label": "문의함", "css": "warn"},
    "answered": {"label": "회신 받음", "css": "ok"},
    "closed": {"label": "정리됨", "css": "none"},
}

# 과거 요청사항과 이번 요청이 어긋나는지 보는 규칙.
#   지어내지 않는다. 낱말이 맞부딪치는 경우만 짚고, 판단은 사람이 한다.
CONFLICT_RULES = [
    {"past": ["무향", "fragrance-free"], "field": "fragrance",
     "clash": ["시트러스", "citrus", "플로럴", "floral", "향료", "머스크", "musk", "로즈"],
     "note": "과거에 무향을 요구한 고객사인데 이번 요청에는 향이 적혀 있습니다."},
    {"past": ["fob", "fob 부산"], "field": "trade_terms",
     "clash": ["cif", "ddp", "exw"],
     "note": "과거 견적은 FOB 기준으로 달라고 했는데 이번 조건이 다릅니다."},
    {"past": ["비건", "vegan", "크루얼티"], "field": "key_ingredients",
     "clash": ["비즈왁스", "beeswax", "라놀린", "lanolin", "honey", "꿀", "콜라겐"],
     "note": "비건 인증을 요구하는 고객사인데 동물 유래 가능 원료가 보입니다."},
    {"past": ["사급"], "field": "container_supply",
     "clash": ["자급", "공장", "we supply"],
     "note": "과거에는 용기를 직접 지급(사급)했는데 이번엔 자급으로 적혀 있습니다."},
]

# ---------------------------------------------------------------------------
# 샘플
# ---------------------------------------------------------------------------

SAMPLE_STATUS = {
    "making": {"label": "제작 중", "css": "warn", "stage": 1},
    "sent": {"label": "발송함", "css": "ok", "stage": 2},
    "feedback": {"label": "피드백 받음", "css": "ok", "stage": 3},
    "revise": {"label": "수정 요청", "css": "check", "stage": 4},
    "approved": {"label": "승인", "css": "confirmed", "stage": 5},
    "dropped": {"label": "보류", "css": "none", "stage": 0},
}
SAMPLE_STATUS_ORDER = ["making", "sent", "feedback", "revise", "approved", "dropped"]

# 샘플마다 기록하는 항목. 피드백이 어디서 갈렸는지 나중에 찾으려면 같은 칸이어야 한다.
SAMPLE_SPECS = [
    {"key": "texture", "label": "제형", "hint": "점도·발림성 계열"},
    {"key": "fragrance", "label": "향", "hint": "무향/향료명·강도"},
    {"key": "color", "label": "색상", "hint": "육안 색·변색 여부"},
    {"key": "viscosity", "label": "점도", "hint": "cps 또는 측정 조건"},
    {"key": "container", "label": "용기", "hint": "적용한 용기·펌프"},
    {"key": "feel", "label": "사용감", "hint": "흡수·잔여감"},
    {"key": "regulation", "label": "규제 이슈", "hint": "판매국 배합 한도 등"},
    {"key": "cost", "label": "원가", "hint": "개당 원가(원) — 확정 전이면 비워 둡니다"},
]
SAMPLE_SPEC_KEYS = [row["key"] for row in SAMPLE_SPECS]

FEEDBACK_SIDES = {
    "buyer": {"label": "바이어 피드백", "css": "buyer", "icon": "🌐"},
    "internal": {"label": "내부 검토", "css": "internal", "icon": "🏭"},
}
FEEDBACK_VERDICTS = {
    "good": {"label": "좋음", "css": "ok"},
    "revise": {"label": "수정 요청", "css": "check"},
    "reject": {"label": "부적합", "css": "missing"},
    "note": {"label": "참고", "css": "none"},
}

# ---------------------------------------------------------------------------
# 견적 대안
# ---------------------------------------------------------------------------

QUOTE_BASIS = {
    "real": {"label": "실제 원가", "css": "confirmed",
             "desc": "구매팀 원가표에서 온 값입니다"},
    "example": {"label": "기본 예시값", "css": "example",
                "desc": "시연용 기본값입니다. 실제 원가가 아닙니다"},
}

CONTAINER_TIERS = [
    {"key": "basic", "label": "기본 용기", "factor": 1.0,
     "desc": "표준 사양 · 추가 가공 없음"},
    {"key": "premium", "label": "고급 용기", "factor": 1.35,
     "desc": "이중 용기·무광 도장 등 (원가 가정 +35%)"},
    {"key": "buyer", "label": "사급 (고객사 지급)", "factor": 0.0,
     "desc": "고객사가 용기를 대 주면 단가에서 빠집니다"},
]
CONTAINER_MAP = {row["key"]: row for row in CONTAINER_TIERS}

# ---------------------------------------------------------------------------
# 후속 연락
# ---------------------------------------------------------------------------

CONTACT_CHANNELS = {
    "email": {"label": "이메일", "icon": "📧"},
    "call": {"label": "전화", "icon": "📞"},
    "meeting": {"label": "미팅·화상", "icon": "👥"},
    "message": {"label": "메신저", "icon": "💬"},
    "sample": {"label": "샘플 발송", "icon": "📦"},
    "other": {"label": "기타", "icon": "•"},
}
CONTACT_CHANNEL_ORDER = ["email", "call", "meeting", "message", "sample", "other"]
CONTACT_DIRECTIONS = {
    "in": {"label": "받음", "css": "in"},
    "out": {"label": "보냄", "css": "out"},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT NOT NULL,
    title         TEXT NOT NULL,
    customer_id   TEXT,
    customer_name TEXT,
    buyer_name    TEXT,
    buyer_email   TEXT,
    country       TEXT,
    owner         TEXT,
    stage         TEXT NOT NULL DEFAULT 'intake',
    status        TEXT NOT NULL DEFAULT 'active',
    closed_reason TEXT NOT NULL DEFAULT '',
    closed_note   TEXT NOT NULL DEFAULT '',
    closed_at     TEXT NOT NULL DEFAULT '',
    source_file   TEXT,
    source_text   TEXT,
    schedule_id   INTEGER,
    parts         TEXT,
    note          TEXT,
    is_demo       INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fields (
    project_id INTEGER NOT NULL,
    key        TEXT NOT NULL,
    value      TEXT,
    state      TEXT NOT NULL DEFAULT 'default',
    source     TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (project_id, key)
);

CREATE TABLE IF NOT EXISTS questions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    key        TEXT NOT NULL,
    label      TEXT NOT NULL,
    ask_en     TEXT,
    why        TEXT,
    priority   TEXT NOT NULL DEFAULT 'mid',
    status     TEXT NOT NULL DEFAULT 'open',
    answer     TEXT,
    conflict   TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS samples (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    code       TEXT NOT NULL,
    round      INTEGER NOT NULL DEFAULT 1,
    status     TEXT NOT NULL DEFAULT 'making',
    made_at    TEXT,
    sent_at    TEXT,
    note       TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sample_specs (
    sample_id INTEGER NOT NULL,
    key       TEXT NOT NULL,
    value     TEXT,
    state     TEXT NOT NULL DEFAULT 'user',
    PRIMARY KEY (sample_id, key)
);

CREATE TABLE IF NOT EXISTS sample_notes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id INTEGER NOT NULL,
    side      TEXT NOT NULL DEFAULT 'buyer',
    verdict   TEXT NOT NULL DEFAULT 'note',
    body      TEXT NOT NULL,
    at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quotes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    label      TEXT NOT NULL,
    qty        INTEGER NOT NULL DEFAULT 5000,
    container  TEXT NOT NULL DEFAULT 'basic',
    incoterm   TEXT NOT NULL DEFAULT 'FOB',
    margin     REAL NOT NULL DEFAULT 25,
    currency   TEXT NOT NULL DEFAULT 'USD',
    fx         REAL NOT NULL DEFAULT 1385,
    unit_cost  REAL NOT NULL DEFAULT 0,
    basis      TEXT NOT NULL DEFAULT 'example',
    chosen     INTEGER NOT NULL DEFAULT 0,
    note       TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contacts_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    at         TEXT NOT NULL,
    direction  TEXT NOT NULL DEFAULT 'out',
    channel    TEXT NOT NULL DEFAULT 'email',
    contact_id INTEGER,
    person     TEXT NOT NULL DEFAULT '',
    role       TEXT NOT NULL DEFAULT '',
    summary    TEXT NOT NULL,
    next_date  TEXT,
    next_action TEXT,
    owner      TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fields_p ON fields(project_id);
CREATE INDEX IF NOT EXISTS idx_questions_p ON questions(project_id);
CREATE INDEX IF NOT EXISTS idx_samples_p ON samples(project_id);
CREATE INDEX IF NOT EXISTS idx_quotes_p ON quotes(project_id);
CREATE INDEX IF NOT EXISTS idx_contacts_p ON contacts_log(project_id);
"""


# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------

def now_seoul():
    return datetime.now(SEOUL)


def now_iso():
    return now_seoul().strftime("%Y-%m-%d %H:%M:%S")


def today_iso():
    return now_seoul().date().isoformat()


def connect():
    conn = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    return conn


# 나중에 붙인 칸. 이미 만들어진 DB 에도 넣어 줘야 한다.
#   CREATE TABLE IF NOT EXISTS 는 있는 표를 그냥 두고 지나간다.
LATE_COLUMNS = [
    ("contacts_log", "contact_id", "INTEGER"),
    ("contacts_log", "person", "TEXT NOT NULL DEFAULT ''"),
    ("contacts_log", "role", "TEXT NOT NULL DEFAULT ''"),
    ("projects", "closed_reason", "TEXT NOT NULL DEFAULT ''"),
    ("projects", "closed_note", "TEXT NOT NULL DEFAULT ''"),
    ("projects", "closed_at", "TEXT NOT NULL DEFAULT ''"),
]


def _add_missing_columns(conn):
    for table, column, decl in LATE_COLUMNS:
        have = {row["name"] for row in conn.execute(
            "PRAGMA table_info({})".format(table))}
        if column not in have:
            conn.execute("ALTER TABLE {} ADD COLUMN {} {}".format(table, column, decl))
    conn.commit()


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()
    _add_missing_columns(conn)


def _clean(value, limit=500):
    return (str(value) if value is not None else "").strip()[:limit]


def _norm(text):
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


# ---------------------------------------------------------------------------
# 프로젝트
# ---------------------------------------------------------------------------

def _code(project_id):
    return "PRJ-{}-{:03d}".format(now_seoul().strftime("%Y%m%d"), project_id)


def create_project(data, analysis=None, profile=None):
    """프로젝트 한 건을 연다.

    analysis 를 주면 요청서 분석 결과를 그대로 제품 조건으로 옮겨 담고,
    빠진 항목은 바이어 확인사항으로 만든다. 여기서 흐름이 시작된다.
    """
    init_db()
    conn = connect()
    stamp = now_iso()

    cur = conn.execute(
        """INSERT INTO projects
           (code, title, customer_id, customer_name, buyer_name, buyer_email,
            country, owner, stage, status, source_file, source_text, parts,
            note, is_demo, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("", _clean(data.get("title"), 120) or "이름 없는 건",
         _clean(data.get("customer_id"), 60), _clean(data.get("customer_name"), 120),
         _clean(data.get("buyer_name"), 80), _clean(data.get("buyer_email"), 120),
         _clean(data.get("country"), 40), _clean(data.get("owner"), 40) or "해외영업",
         "intake", "active",
         _clean(data.get("source_file"), 200),
         _clean(data.get("source_text"), 20000),
         json.dumps(data.get("parts") or [], ensure_ascii=False),
         _clean(data.get("note")), 1 if data.get("is_demo") else 0,
         stamp, stamp))
    project_id = cur.lastrowid
    conn.execute("UPDATE projects SET code = ? WHERE id = ?", (_code(project_id), project_id))
    conn.commit()

    if analysis:
        apply_analysis(project_id, analysis, profile=profile)

    return project_id


def get_project(project_id):
    conn = connect()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["parts"] = json.loads(data["parts"] or "[]")
    data["status_meta"] = STATUS_META.get(data["status"], STATUS_META["active"])
    data["stage_meta"] = STAGE_MAP.get(data["stage"], STAGES[0])
    data["drop_meta"] = DROP_MAP.get(data.get("closed_reason") or "")
    return data


def list_projects(status="all"):
    conn = connect()
    sql = "SELECT * FROM projects"
    args = []
    if status != "all":
        sql += " WHERE status = ?"
        args.append(status)
    sql += " ORDER BY updated_at DESC, id DESC"

    rows = []
    for row in conn.execute(sql, args):
        item = dict(row)
        item["parts"] = json.loads(item["parts"] or "[]")
        item["status_meta"] = STATUS_META.get(item["status"], STATUS_META["active"])
        item["stage_meta"] = STAGE_MAP.get(item["stage"], STAGES[0])
        # 목록에서도 왜 무산됐는지가 바로 보여야 한다
        item["drop_meta"] = DROP_MAP.get(item.get("closed_reason") or "")
        item["progress"] = progress(item["id"])
        rows.append(item)
    return rows


def update_project(project_id, data):
    conn = connect()
    current = get_project(project_id)
    if current is None:
        return False

    merged = {}
    for key, limit in (("title", 120), ("customer_id", 60), ("customer_name", 120),
                       ("buyer_name", 80), ("buyer_email", 120), ("country", 40),
                       ("owner", 40), ("note", 500)):
        value = data.get(key)
        merged[key] = _clean(value, limit) if value is not None else (current[key] or "")

    status = data.get("status")
    merged["status"] = status if status in STATUS_META else current["status"]
    stage = data.get("stage")
    merged["stage"] = stage if stage in STAGE_MAP else current["stage"]

    conn.execute(
        """UPDATE projects SET title=?, customer_id=?, customer_name=?, buyer_name=?,
           buyer_email=?, country=?, owner=?, note=?, status=?, stage=?, updated_at=?
           WHERE id=?""",
        (merged["title"], merged["customer_id"], merged["customer_name"],
         merged["buyer_name"], merged["buyer_email"], merged["country"],
         merged["owner"], merged["note"], merged["status"], merged["stage"],
         now_iso(), project_id))
    conn.commit()
    return True


def set_parts(project_id, parts):
    """포장 구성(용기·부자재). 포장재 가격 동향과 이어지는 값이다."""
    conn = connect()
    conn.execute("UPDATE projects SET parts = ?, updated_at = ? WHERE id = ?",
                 (json.dumps(list(parts), ensure_ascii=False), now_iso(), project_id))
    conn.commit()


def set_schedule(project_id, schedule_id):
    conn = connect()
    conn.execute("UPDATE projects SET schedule_id = ?, updated_at = ? WHERE id = ?",
                 (schedule_id, now_iso(), project_id))
    conn.commit()


def delete_project(project_id):
    conn = connect()
    for table in ("fields", "questions", "quotes", "contacts_log"):
        conn.execute("DELETE FROM {} WHERE project_id = ?".format(table), (project_id,))
    for row in conn.execute("SELECT id FROM samples WHERE project_id = ?", (project_id,)):
        conn.execute("DELETE FROM sample_specs WHERE sample_id = ?", (row["id"],))
        conn.execute("DELETE FROM sample_notes WHERE sample_id = ?", (row["id"],))
    conn.execute("DELETE FROM samples WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    return True


# ---------------------------------------------------------------------------
# 제품 조건 (값 + 상태)
# ---------------------------------------------------------------------------

def set_field(project_id, key, value, state="user", source=""):
    conn = connect()
    conn.execute(
        """INSERT INTO fields (project_id, key, value, state, source, updated_at)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(project_id, key) DO UPDATE SET
             value = excluded.value, state = excluded.state,
             source = excluded.source, updated_at = excluded.updated_at""",
        (project_id, key, _clean(value, 1000),
         state if state in VALUE_STATES else "user", _clean(source, 500), now_iso()))
    conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now_iso(), project_id))
    conn.commit()


def raw_fields(project_id):
    conn = connect()
    return {r["key"]: dict(r) for r in
            conn.execute("SELECT * FROM fields WHERE project_id = ?", (project_id,))}


def field_value(project_id, key, default=""):
    row = raw_fields(project_id).get(key)
    return (row or {}).get("value") or default


def field_groups(project_id):
    """화면에 뿌릴 제품 조건. 값이 없어도 칸은 남겨 둔다 (빠진 게 보여야 한다)."""
    stored = raw_fields(project_id)
    groups = []
    for group in FIELD_GROUPS:
        rows = []
        for key, label in group["fields"]:
            item = stored.get(key) or {}
            value = item.get("value") or ""
            state = item.get("state") or ("check" if not value else "default")
            rows.append({
                "key": key, "label": label, "value": value,
                "state": state, "state_meta": state_meta(state),
                "source": item.get("source") or "",
                "empty": not value,
            })
        groups.append({"key": group["key"], "label": group["label"], "rows": rows})
    return groups


def apply_analysis(project_id, analysis, profile=None):
    """요청서 분석 결과를 프로젝트 값으로 옮긴다.

    분석에서 읽어낸 값은 `analysis`, 확인이 필요하다고 표시된 값은 `check`.
    상태를 그대로 옮겨야 나중에 "이거 우리가 확인한 값이던가?" 를 되물을 수 있다.
    """
    conn = connect()
    moved = 0
    for item in analysis.get("items", []):
        key = item.get("key")
        if key not in FIELD_LABELS:
            continue
        value = (item.get("value") or "").strip()
        if item.get("status") == "missing" or not value:
            state = "check"
        elif item.get("status") == "check":
            state = "check"
        else:
            state = "analysis"
        set_field(project_id, key, value, state,
                  source=item.get("source") or "요청서 분석")
        moved += 1

    # 원문과 파일명도 프로젝트에 남긴다
    if analysis.get("source_text"):
        conn.execute("UPDATE projects SET source_text = ?, source_file = ?, "
                     "stage = ?, updated_at = ? WHERE id = ?",
                     (analysis["source_text"][:20000], analysis.get("file_name", ""),
                      "analysis", now_iso(), project_id))
        conn.commit()

    rebuild_questions(project_id, profile=profile)
    return moved


# ---------------------------------------------------------------------------
# 바이어 확인사항
# ---------------------------------------------------------------------------

def _conflicts(project_id, profile):
    """고객사 과거 요청과 이번 요청이 부딪치는 곳.

    자동 대조일 뿐이다. 낱말이 맞부딪치는 경우만 짚고 판단은 사람이 한다.
    """
    if not profile:
        return {}

    stored = raw_fields(project_id)
    found = {}
    past_rows = profile.get("requests", [])

    for rule in CONFLICT_RULES:
        past = next((r for r in past_rows
                     if any(word in _norm(r.get("title", "") + " " + r.get("detail", ""))
                            for word in rule["past"])), None)
        if past is None:
            continue

        value = _norm((stored.get(rule["field"]) or {}).get("value", ""))
        if not value:
            continue
        hit = next((w for w in rule["clash"] if w in value), "")
        if not hit:
            continue

        found[rule["field"]] = {
            "note": rule["note"],
            "past": past.get("title", ""),
            "past_source": past.get("source", ""),
            "now": (stored.get(rule["field"]) or {}).get("value", ""),
        }
    return found


def rebuild_questions(project_id, profile=None):
    """빠진 조건을 확인사항으로 만든다. 이미 있는 항목은 건드리지 않는다."""
    conn = connect()
    stored = raw_fields(project_id)
    existing = {r["key"]: dict(r) for r in
                conn.execute("SELECT * FROM questions WHERE project_id = ?", (project_id,))}
    conflicts = _conflicts(project_id, profile)
    stamp = now_iso()
    made = 0

    for item in REQUIRED_ITEMS:
        field = stored.get(item["field"]) or {}
        value = (field.get("value") or "").strip()
        state = field.get("state") or "check"
        conflict = conflicts.get(item["field"])

        # 값이 있고 확인 필요 표시도 없고 충돌도 없으면 물어볼 이유가 없다
        settled = bool(value) and state in ("analysis", "user", "confirmed") and not conflict
        if settled:
            # 값이 채워졌는데 확인사항이 열려 있으면 닫는다.
            #   (견적 대안을 고르거나 회신을 반영하면 여기로 이어진다)
            old = existing.get(item["key"])
            if old and old["status"] in ("open", "asked"):
                conn.execute("UPDATE questions SET status='closed', updated_at=? "
                             "WHERE id = ?", (stamp, old["id"]))
            continue

        if item["key"] in existing:
            # 충돌 메모만 갱신한다 (담당자가 적어 둔 답은 보존)
            conn.execute("UPDATE questions SET conflict = ?, updated_at = ? WHERE id = ?",
                         (json.dumps(conflict, ensure_ascii=False) if conflict else None,
                          stamp, existing[item["key"]]["id"]))
            continue

        conn.execute(
            """INSERT INTO questions
               (project_id, key, label, ask_en, why, priority, status, conflict,
                created_at, updated_at)
               VALUES (?,?,?,?,?,?,'open',?,?,?)""",
            (project_id, item["key"], item["label"], item["ask_en"], item["why"],
             item["priority"],
             json.dumps(conflict, ensure_ascii=False) if conflict else None,
             stamp, stamp))
        made += 1

    # 필수 항목이 아니어도 과거 요청과 부딪치면 물어봐야 한다.
    #   (향·성분처럼 견적에는 안 들어가지만 샘플을 다시 만들게 만드는 것들)
    for field_key, conflict in conflicts.items():
        if any(item["field"] == field_key for item in REQUIRED_ITEMS):
            continue
        key = "conflict_" + field_key
        if key in existing:
            conn.execute("UPDATE questions SET conflict = ?, updated_at = ? WHERE id = ?",
                         (json.dumps(conflict, ensure_ascii=False), stamp,
                          existing[key]["id"]))
            continue

        label = FIELD_LABELS.get(field_key, field_key)
        conn.execute(
            """INSERT INTO questions
               (project_id, key, label, ask_en, why, priority, status, conflict,
                created_at, updated_at)
               VALUES (?,?,?,?,?,'high','open',?,?,?)""",
            (project_id, key, "{} (과거 요청과 다름)".format(label),
             "In your earlier projects you asked for \u201c{}\u201d. "
             "This request says \u201c{}\u201d. "
             "Could you confirm which applies to this project?".format(
                 conflict["past"], conflict["now"][:120]),
             conflict["note"],
             json.dumps(conflict, ensure_ascii=False), stamp, stamp))
        made += 1

    conn.commit()
    return made


def questions_of(project_id):
    conn = connect()
    rows = []
    order = {"high": 0, "mid": 1, "low": 2}
    for row in conn.execute("SELECT * FROM questions WHERE project_id = ?", (project_id,)):
        item = dict(row)
        item["status_meta"] = QUESTION_STATUS.get(item["status"], QUESTION_STATUS["open"])
        item["conflict"] = json.loads(item["conflict"]) if item["conflict"] else None
        field_key = REQUIRED_MAP.get(item["key"], {}).get("field", "")
        if not field_key and item["key"].startswith("conflict_"):
            field_key = item["key"][len("conflict_"):]
        item["field_key"] = field_key
        item["field_value"] = field_value(project_id, field_key, "") if field_key else ""
        rows.append(item)

    rows.sort(key=lambda r: (r["status"] != "open", order.get(r["priority"], 9), r["id"]))
    return rows


def update_question(question_id, data):
    conn = connect()
    row = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
    if row is None:
        return None

    status = data.get("status")
    status = status if status in QUESTION_STATUS else row["status"]
    answer = data.get("answer")
    answer = _clean(answer, 1000) if answer is not None else (row["answer"] or "")
    ask_en = data.get("ask_en")
    ask_en = _clean(ask_en, 1000) if ask_en is not None else (row["ask_en"] or "")

    conn.execute("UPDATE questions SET status=?, answer=?, ask_en=?, updated_at=? WHERE id=?",
                 (status, answer, ask_en, now_iso(), question_id))
    conn.commit()

    # 회신을 받았으면 그 값을 제품 조건에 확정값으로 올린다 - 여기서 흐름이 이어진다
    if status == "answered" and answer:
        field = REQUIRED_MAP.get(row["key"], {}).get("field")
        if not field and row["key"].startswith("conflict_"):
            field = row["key"][len("conflict_"):]
        if field in FIELD_LABELS:
            set_field(row["project_id"], field, answer, "confirmed",
                      source="바이어 회신 ({})".format(today_iso()))
    return dict(row)


def mark_questions(project_id, keys, status):
    conn = connect()
    if not keys:
        return 0
    marks = ",".join("?" * len(keys))
    cur = conn.execute(
        "UPDATE questions SET status = ?, updated_at = ? "
        "WHERE project_id = ? AND key IN ({})".format(marks),
        [status, now_iso(), project_id] + list(keys))
    conn.commit()
    return cur.rowcount


def draft_email(project_id, keys=()):
    """고른 확인사항으로 바이어에게 보낼 영문 메일 초안을 만든다.

    번역기가 아니다. 미리 적어 둔 영문 문장을 순서대로 엮는다.
    TODO: 실제 연동 (LLM 문장 다듬기)
    """
    project = get_project(project_id)
    if project is None:
        return None

    picked = [q for q in questions_of(project_id)
              if not keys or q["key"] in set(keys)]
    picked = [q for q in picked if q["status"] in ("open", "asked")]

    name = project["buyer_name"] or "there"
    product = field_value(project_id, "product_name", project["title"])

    lines = ["Dear {},".format(name), ""]
    lines.append("Thank you for your enquiry regarding {}.".format(product))
    lines.append("Before we prepare the quotation and the development schedule, "
                 "could you kindly confirm the following?")
    lines.append("")

    for idx, q in enumerate(picked, start=1):
        lines.append("{}. {}".format(idx, q["ask_en"]))
        # 충돌 항목은 ask_en 안에 이미 과거 요청이 들어 있다. 두 번 적지 않는다
        if q["conflict"] and not q["key"].startswith("conflict_"):
            lines.append("   (We noted your earlier requirement: {}. "
                         "Please confirm which applies to this project.)".format(
                             q["conflict"]["past"]))
    if not picked:
        lines.append("(고를 항목이 없습니다 — 확인사항을 먼저 선택해 주세요.)")

    lines.append("")
    lines.append("Once we have your confirmation we will send the quotation "
                 "and the sample schedule.")
    lines.append("")
    lines.append("Best regards,")
    lines.append(project["owner"] or "Overseas Sales Team")

    return {
        "to": project["buyer_email"] or "",
        "subject": "[{}] Confirmation needed before quotation - {}".format(
            project["customer_name"] or "Enquiry", product),
        "body": "\n".join(lines),
        "count": len(picked),
        "keys": [q["key"] for q in picked],
    }


# ---------------------------------------------------------------------------
# 샘플
# ---------------------------------------------------------------------------

def add_sample(project_id, data):
    conn = connect()
    stamp = now_iso()
    code = _clean(data.get("code"), 20) or _next_code(project_id)
    try:
        round_no = int(data.get("round") or 1)
    except (TypeError, ValueError):
        round_no = 1

    cur = conn.execute(
        """INSERT INTO samples (project_id, code, round, status, made_at, note,
                                created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (project_id, code, max(round_no, 1),
         data.get("status") if data.get("status") in SAMPLE_STATUS else "making",
         _clean(data.get("made_at"), 10) or today_iso(),
         _clean(data.get("note")), stamp, stamp))
    sample_id = cur.lastrowid

    for spec in SAMPLE_SPECS:
        value = data.get("spec_" + spec["key"])
        if value:
            conn.execute("INSERT INTO sample_specs (sample_id, key, value, state) "
                         "VALUES (?,?,?,'user')",
                         (sample_id, spec["key"], _clean(value, 300)))
    conn.commit()
    conn.execute("UPDATE projects SET stage = 'sample', updated_at = ? WHERE id = ? "
                 "AND stage IN ('intake','analysis','questions','handoff')",
                 (now_iso(), project_id))
    conn.commit()
    return sample_id


def _next_code(project_id):
    conn = connect()
    used = {r["code"] for r in
            conn.execute("SELECT code FROM samples WHERE project_id = ?", (project_id,))}
    for letter in "ABCDEFGH":
        if letter not in used:
            return letter
    return "S{}".format(len(used) + 1)


def update_sample(sample_id, data):
    conn = connect()
    row = conn.execute("SELECT * FROM samples WHERE id = ?", (sample_id,)).fetchone()
    if row is None:
        return False

    status = data.get("status")
    status = status if status in SAMPLE_STATUS else row["status"]
    sent_at = data.get("sent_at")
    sent_at = _clean(sent_at, 10) if sent_at is not None else (row["sent_at"] or "")
    if status == "sent" and not sent_at:
        sent_at = today_iso()

    conn.execute("""UPDATE samples SET status=?, sent_at=?, note=?, round=?, updated_at=?
                    WHERE id=?""",
                 (status, sent_at,
                  _clean(data.get("note")) if data.get("note") is not None else (row["note"] or ""),
                  int(data.get("round") or row["round"]), now_iso(), sample_id))

    for spec in SAMPLE_SPECS:
        key = "spec_" + spec["key"]
        if key not in data:
            continue
        conn.execute(
            """INSERT INTO sample_specs (sample_id, key, value, state) VALUES (?,?,?,'user')
               ON CONFLICT(sample_id, key) DO UPDATE SET value = excluded.value""",
            (sample_id, spec["key"], _clean(data.get(key), 300)))
    conn.commit()
    return True


def add_feedback(sample_id, data):
    conn = connect()
    body = _clean(data.get("body"), 2000)
    if not body:
        return False

    side = data.get("side") if data.get("side") in FEEDBACK_SIDES else "buyer"
    verdict = data.get("verdict") if data.get("verdict") in FEEDBACK_VERDICTS else "note"
    conn.execute("INSERT INTO sample_notes (sample_id, side, verdict, body, at) "
                 "VALUES (?,?,?,?,?)",
                 (sample_id, side, verdict, body, now_iso()))

    # 피드백이 들어오면 샘플 상태도 따라 움직인다 (손으로 또 바꾸지 않게)
    row = conn.execute("SELECT * FROM samples WHERE id = ?", (sample_id,)).fetchone()
    if row is not None:
        nxt = {"good": "feedback", "revise": "revise", "reject": "revise"}.get(verdict)
        if nxt and row["status"] in ("making", "sent", "feedback"):
            conn.execute("UPDATE samples SET status = ?, updated_at = ? WHERE id = ?",
                         (nxt, now_iso(), sample_id))
    conn.commit()
    return True


def delete_sample(sample_id):
    conn = connect()
    conn.execute("DELETE FROM sample_specs WHERE sample_id = ?", (sample_id,))
    conn.execute("DELETE FROM sample_notes WHERE sample_id = ?", (sample_id,))
    conn.execute("DELETE FROM samples WHERE id = ?", (sample_id,))
    conn.commit()
    return True


def samples_of(project_id):
    conn = connect()
    rows = []
    for row in conn.execute(
            "SELECT * FROM samples WHERE project_id = ? ORDER BY round ASC, code ASC",
            (project_id,)):
        item = dict(row)
        item["status_meta"] = SAMPLE_STATUS.get(item["status"], SAMPLE_STATUS["making"])

        specs = {r["key"]: dict(r) for r in conn.execute(
            "SELECT * FROM sample_specs WHERE sample_id = ?", (item["id"],))}
        item["specs"] = [{
            "key": spec["key"], "label": spec["label"], "hint": spec["hint"],
            "value": (specs.get(spec["key"]) or {}).get("value") or "",
        } for spec in SAMPLE_SPECS]

        item["notes"] = [dict(r, side_meta=FEEDBACK_SIDES.get(r["side"], FEEDBACK_SIDES["buyer"]),
                              verdict_meta=FEEDBACK_VERDICTS.get(r["verdict"],
                                                                 FEEDBACK_VERDICTS["note"]))
                         for r in conn.execute(
                             "SELECT * FROM sample_notes WHERE sample_id = ? ORDER BY id DESC",
                             (item["id"],))]
        item["buyer_notes"] = [n for n in item["notes"] if n["side"] == "buyer"]
        rows.append(item)
    return rows


# ---------------------------------------------------------------------------
# 견적 대안
# ---------------------------------------------------------------------------

def add_quote(project_id, data):
    conn = connect()

    def _f(key, default=0.0):
        try:
            return float(str(data.get(key, default)).replace(",", ""))
        except (TypeError, ValueError):
            return float(default)

    container = data.get("container") if data.get("container") in CONTAINER_MAP else "basic"
    basis = data.get("basis") if data.get("basis") in QUOTE_BASIS else "example"

    conn.execute(
        """INSERT INTO quotes (project_id, label, qty, container, incoterm, margin,
                               currency, fx, unit_cost, basis, note, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (project_id, _clean(data.get("label"), 60) or "대안",
         int(_f("qty", 5000)) or 1, container,
         _clean(data.get("incoterm"), 8) or "FOB", _f("margin", 25),
         _clean(data.get("currency"), 4) or "USD", _f("fx", 1385) or 1,
         _f("unit_cost", 0), basis, _clean(data.get("note"), 300), now_iso()))
    conn.commit()
    conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now_iso(), project_id))
    conn.commit()
    return True


def delete_quote(quote_id):
    conn = connect()
    conn.execute("DELETE FROM quotes WHERE id = ?", (quote_id,))
    conn.commit()
    return True


def choose_quote(project_id, quote_id):
    conn = connect()
    conn.execute("UPDATE quotes SET chosen = 0 WHERE project_id = ?", (project_id,))
    conn.execute("UPDATE quotes SET chosen = 1 WHERE id = ? AND project_id = ?",
                 (quote_id, project_id))
    conn.commit()

    row = conn.execute("SELECT * FROM quotes WHERE id = ?", (quote_id,)).fetchone()
    if row is not None:
        # 고른 대안의 조건을 제품 조건으로 올린다 - 여기서도 흐름이 이어진다
        set_field(project_id, "moq", "{:,}개".format(row["qty"]), "confirmed",
                  source="견적 대안 '{}' 선택".format(row["label"]))
        set_field(project_id, "trade_terms", row["incoterm"], "confirmed",
                  source="견적 대안 '{}' 선택".format(row["label"]))
        set_field(project_id, "currency", row["currency"], "confirmed",
                  source="견적 대안 '{}' 선택".format(row["label"]))
    return True


# 물류비 가정 (개당). 실제 포워더 견적이 아니라 비교를 위한 기본 예시값이다.
_LOGI_ASSUMPTION = {"EXW": 0, "FCA": 60, "FOB": 110, "CFR": 240, "CIF": 260}


def quote_rows(project_id):
    """견적 대안을 나란히 볼 수 있게 계산한다.

    값이 실제 원가인지 기본 예시값인지(`basis`)를 끝까지 달고 다닌다.
    시제품에서 제일 위험한 게 예시 숫자를 실제로 믿는 것이다.
    """
    conn = connect()
    rows = []
    for row in conn.execute(
            "SELECT * FROM quotes WHERE project_id = ? ORDER BY id ASC", (project_id,)):
        item = dict(row)
        tier = CONTAINER_MAP[item["container"]]

        # 용기값은 원가의 일부로 가정한다. 사급이면 빠진다.
        base = item["unit_cost"]
        container_cost = base * 0.25 * tier["factor"]
        cost = base * 0.75 + container_cost
        logi = _LOGI_ASSUMPTION.get(item["incoterm"], 0)
        total_cost = cost + logi

        margin = max(min(item["margin"], 94.0), 0.0)
        price_krw = total_cost / (1 - margin / 100) if margin < 100 else total_cost
        unit = price_krw / (item["fx"] or 1)

        item.update({
            "tier": tier,
            "basis_meta": QUOTE_BASIS[item["basis"]],
            "container_cost": container_cost,
            "logistics": logi,
            "total_cost": total_cost,
            "price_krw": price_krw,
            "unit_price": unit,
            "amount": unit * item["qty"],
            "chosen": bool(item["chosen"]),
        })
        rows.append(item)

    if rows:
        cheapest = min(r["unit_price"] for r in rows)
        for row in rows:
            row["gap"] = row["unit_price"] - cheapest
            row["best"] = abs(row["gap"]) < 1e-9
    return rows


def seed_quotes(project_id, unit_cost=0, basis="example", currency="USD", fx=1385):
    """비교할 게 있어야 비교가 된다. 대표적인 세 가지 대안을 깔아 준다."""
    if quote_rows(project_id):
        return 0

    cost = unit_cost or 1570          # 원가표 샘플값
    made = 0
    for label, qty, container, incoterm in (
            ("5,000개 · 기본 용기 · FOB", 5000, "basic", "FOB"),
            ("10,000개 · 기본 용기 · FOB", 10000, "basic", "FOB"),
            ("5,000개 · 고급 용기 · CIF", 5000, "premium", "CIF")):
        add_quote(project_id, {
            "label": label, "qty": qty, "container": container, "incoterm": incoterm,
            "margin": 25, "currency": currency, "fx": fx,
            "unit_cost": cost * (0.94 if qty >= 10000 else 1.0),
            "basis": basis,
            "note": "수량이 늘면 부대비가 나뉘어 개당 원가가 내려간다고 가정했습니다"
                    if qty >= 10000 else "",
        })
        made += 1
    return made


# ---------------------------------------------------------------------------
# 후속 연락
# ---------------------------------------------------------------------------

def add_contact(project_id, data):
    conn = connect()
    summary = _clean(data.get("summary"), 400)
    if not summary:
        return False

    conn.execute(
        """INSERT INTO contacts_log (project_id, at, direction, channel,
                                     contact_id, person, role, summary,
                                     next_date, next_action, owner, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (project_id, _clean(data.get("at"), 10) or today_iso(),
         data.get("direction") if data.get("direction") in CONTACT_DIRECTIONS else "out",
         data.get("channel") if data.get("channel") in CONTACT_CHANNELS else "email",
         # 담당자는 목록에서 고르되 이름을 같이 적어 둔다.
         # 그 사람이 명단에서 빠져도 "누구와 한 연락인지" 는 남아야 한다
         data.get("contact_id") or None,
         _clean(data.get("person"), 60), _clean(data.get("role"), 40),
         summary, _clean(data.get("next_date"), 10),
         _clean(data.get("next_action"), 200), _clean(data.get("owner"), 40),
         now_iso()))
    conn.commit()
    conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now_iso(), project_id))
    conn.commit()
    return True


def remove_contact(project_id, log_id):
    """잘못 적은 줄을 지운다. 다른 건의 기록을 지우지 못하게 같이 건다."""
    conn = connect()
    cur = conn.execute("DELETE FROM contacts_log WHERE id = ? AND project_id = ?",
                       (log_id, project_id))
    conn.commit()
    return cur.rowcount > 0


def contacts_of(project_id):
    conn = connect()
    rows = []
    for row in conn.execute(
            "SELECT * FROM contacts_log WHERE project_id = ? ORDER BY at DESC, id DESC",
            (project_id,)):
        item = dict(row)
        item["channel_meta"] = CONTACT_CHANNELS.get(item["channel"], CONTACT_CHANNELS["other"])
        item["direction_meta"] = CONTACT_DIRECTIONS.get(item["direction"],
                                                        CONTACT_DIRECTIONS["out"])
        item["overdue"] = bool(item["next_date"] and item["next_date"] < today_iso())
        rows.append(item)
    return rows


def next_contact(project_id):
    """다음 연락 예정. 지난 것이 있으면 그걸 먼저 보여 준다."""
    rows = [r for r in contacts_of(project_id) if r["next_date"]]
    if not rows:
        return None
    overdue = [r for r in rows if r["overdue"]]
    pool = overdue or rows
    return sorted(pool, key=lambda r: r["next_date"])[0]


# ---------------------------------------------------------------------------
# 진행률 - 값이 실제로 들어왔는지로 판정한다
# ---------------------------------------------------------------------------

def progress(project_id):
    conn = connect()
    project = get_project(project_id)
    if project is None:
        return {"percent": 0, "stages": [], "done": 0, "total": len(STAGES)}

    stored = raw_fields(project_id)
    filled = sum(1 for row in stored.values() if (row["value"] or "").strip())
    questions = list(conn.execute(
        "SELECT status FROM questions WHERE project_id = ?", (project_id,)))
    open_q = sum(1 for q in questions if q["status"] == "open")
    samples = list(conn.execute(
        "SELECT status FROM samples WHERE project_id = ?", (project_id,)))
    quotes = conn.execute(
        "SELECT COUNT(*) FROM quotes WHERE project_id = ?", (project_id,)).fetchone()[0]
    contacts = conn.execute(
        "SELECT COUNT(*) FROM contacts_log WHERE project_id = ?", (project_id,)).fetchone()[0]

    tasks = 0
    if project["schedule_id"]:
        try:
            import schedule_store
            tasks = len(schedule_store.tasks_of(project["schedule_id"]))
        except Exception:                             # noqa: BLE001
            tasks = 0

    checks = {
        "intake": (bool(project["customer_name"]), "고객사·제품이 적혀 있습니다"),
        "analysis": (filled >= 5, "제품 조건 {}개가 들어왔습니다".format(filled)),
        "questions": (bool(questions) and open_q == 0,
                      "확인사항 {}건 중 미해결 {}건".format(len(questions), open_q)),
        "handoff": (bool(project["source_text"]), "원문이 있어 전달 문서를 만들 수 있습니다"),
        "sample": (bool(samples), "샘플 {}건".format(len(samples))),
        "quote": (quotes >= 2, "견적 대안 {}개".format(quotes)),
        "schedule": (tasks > 0, "일정 {}건".format(tasks)),
        "followup": (contacts > 0, "연락 이력 {}건".format(contacts)),
    }

    rows = []
    done = 0
    for stage in STAGES:
        ok, note = checks.get(stage["key"], (False, ""))
        done += 1 if ok else 0
        rows.append(dict(stage, done=ok, note=note))

    return {
        "percent": round(done / len(STAGES) * 100),
        "done": done,
        "total": len(STAGES),
        "stages": rows,
        "open_questions": open_q,
        "samples": len(samples),
        "quotes": quotes,
        "tasks": tasks,
        "contacts": contacts,
        "fields": filled,
    }


def next_actions(project_id):
    """다음에 뭘 해야 하는지. 진행률에서 빠진 첫 단계들을 그대로 쓴다."""
    info = progress(project_id)
    project = get_project(project_id)
    todo = []

    for stage in info["stages"]:
        if stage["done"]:
            continue
        todo.append({
            "stage": stage["key"], "label": stage["label"], "icon": stage["icon"],
            "note": stage["note"], "desc": stage["desc"],
        })
        if len(todo) >= 3:
            break

    upcoming = next_contact(project_id)
    if upcoming:
        todo.insert(0, {
            "stage": "followup",
            "label": "{} 바이어 연락".format(upcoming["next_date"]),
            "icon": "⏰" if upcoming["overdue"] else "✉️",
            "note": upcoming["next_action"] or upcoming["summary"],
            "desc": "지난 예정일입니다" if upcoming["overdue"] else "예정된 연락",
            "overdue": upcoming["overdue"],
        })

    return {"items": todo[:4], "owner": project["owner"] if project else ""}


# ---------------------------------------------------------------------------
# 통합 화면에 쓰는 묶음
# ---------------------------------------------------------------------------

def close_project(project_id, reason, note=""):
    """이 건은 안 간다. 사유를 남기고 접는다.

    끝이 아니다. 반년 뒤에 같은 고객사가 다시 오는 일이 흔하다.
    그래서 지우지 않고 사유만 붙여 둔다 (reopen 으로 되살릴 수 있다).
    """
    if reason not in DROP_MAP:
        return False
    conn = connect()
    conn.execute(
        "UPDATE projects SET status = 'lost', closed_reason = ?, closed_note = ?, "
        "closed_at = ?, updated_at = ? WHERE id = ?",
        (reason, _clean(note, 500), today_iso(), now_iso(), project_id))
    conn.commit()
    return True


def reopen_project(project_id):
    """다시 연다. 무산 사유는 지운다 - 지금은 진행 중인 건이다."""
    conn = connect()
    conn.execute(
        "UPDATE projects SET status = 'active', closed_reason = '', "
        "closed_note = '', closed_at = '', updated_at = ? WHERE id = ?",
        (now_iso(), project_id))
    conn.commit()
    return True


def spent_on(project_id):
    """이 건에 우리가 들인 것.

    체리피커의 실질 피해는 '기분' 이 아니라 여기 쌓인 숫자다.
    샘플을 몇 개 만들어 보냈고, 견적을 몇 번 냈고, 몇 번 연락했는가.
    """
    conn = connect()

    def _count(sql):
        return conn.execute(sql, (project_id,)).fetchone()[0]

    return {
        "samples": _count("SELECT COUNT(*) FROM samples WHERE project_id = ?"),
        "quotes": _count("SELECT COUNT(*) FROM quotes WHERE project_id = ?"),
        "contacts": _count("SELECT COUNT(*) FROM contacts_log WHERE project_id = ?"),
    }


def customer_signals(customer_id, customer_name="", skip_project_id=None):
    """이 고객사와의 이력.

    **체리피커라고 단정하지 않는다.** 한 건 무산은 흔한 일이고, 그걸로 회사를
    규정하면 멀쩡한 고객사까지 잃는다. 여기서는 숫자와 사유를 보여주기만 하고,
    판단은 담당자가 한다. 그래서 등급 이름도 '주의해서 볼 신호' 다.
    """
    conn = connect()
    if not (customer_id or customer_name):
        return None

    if customer_id:
        rows = conn.execute("SELECT * FROM projects WHERE customer_id = ?",
                            (customer_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM projects WHERE customer_name = ?",
                            (customer_name,)).fetchall()
    rows = [dict(r) for r in rows if r["id"] != skip_project_id]
    if not rows:
        return None

    lost = [r for r in rows if r["status"] == "lost"]
    signal_rows = [r for r in lost if (r.get("closed_reason") or "") in SIGNAL_REASONS]
    won = [r for r in rows if r["status"] == "won"]

    spent = {"samples": 0, "quotes": 0, "contacts": 0}
    for row in rows:
        for key, value in spent_on(row["id"]).items():
            spent[key] += value

    counted = {}
    for row in lost:
        key = row.get("closed_reason") or "other"
        counted[key] = counted.get(key, 0) + 1
    reasons = sorted(
        ({"label": DROP_MAP.get(k, DROP_MAP["other"])["label"], "count": v,
          "signal": k in SIGNAL_REASONS} for k, v in counted.items()),
        key=lambda r: -r["count"])

    # 한 건 무산으로는 아무 말도 하지 않는다
    if len(signal_rows) < 2:
        level = "none"
    elif len(signal_rows) >= 3 and not won:
        level = "high"
    else:
        level = "watch"

    if level == "none":
        why = "지금까지의 기록으로는 특별히 눈에 띄는 것이 없습니다."
    elif won:
        why = ("무산 {}건 중 {}건이 연락 두절·정보 수집 쪽입니다. "
               "다만 수주 이력이 {}건 있어 거래는 되는 곳입니다."
               .format(len(lost), len(signal_rows), len(won)))
    else:
        why = ("무산 {}건 중 {}건이 연락 두절·정보 수집 쪽이고, 아직 수주가 없습니다. "
               "샘플 {}개·견적 {}건이 나갔습니다."
               .format(len(lost), len(signal_rows), spent["samples"], spent["quotes"]))

    return {
        "customer_id": customer_id,
        "customer_name": customer_name,
        "projects": len(rows),
        "won": len(won),
        "lost": len(lost),
        "active": sum(1 for r in rows if r["status"] in ("active", "hold")),
        "signal_lost": len(signal_rows),
        "spent": spent,
        "reasons": reasons,
        "level": level,
        "level_meta": dict(SIGNAL_LEVELS[level], key=level),
        "why": why,
        "rows": [{"id": r["id"], "code": r["code"], "title": r["title"],
                  "status": r["status"],
                  "status_meta": STATUS_META.get(r["status"], STATUS_META["active"]),
                  "closed_at": r.get("closed_at") or "",
                  "drop_meta": DROP_MAP.get(r.get("closed_reason") or "")}
                 for r in sorted(rows, key=lambda x: -x["id"])],
    }


def drop_stats():
    """무산 사유 분포. 한 건씩 보면 안 보이는 게 모아 놓으면 보인다."""
    conn = connect()
    rows = conn.execute(
        "SELECT closed_reason AS r, COUNT(*) AS n FROM projects "
        "WHERE status = 'lost' GROUP BY closed_reason ORDER BY n DESC").fetchall()
    out = []
    total = 0
    for row in rows:
        meta = DROP_MAP.get(row["r"] or "")
        out.append({"label": meta["label"] if meta else "사유 미기재",
                    "count": row["n"],
                    "signal": bool(meta and meta["signal"])})
        total += row["n"]
    return {"rows": out, "total": total,
            "signal": sum(r["count"] for r in out if r["signal"])}


def hub(project_id):
    """프로젝트 통합 화면 한 장."""
    project = get_project(project_id)
    if project is None:
        return None

    return {
        "project": project,
        "fields": field_groups(project_id),
        "questions": questions_of(project_id),
        "samples": samples_of(project_id),
        "quotes": quote_rows(project_id),
        "contacts": contacts_of(project_id),
        "next_contact": next_contact(project_id),
        "spent": spent_on(project_id),
        "drop_reasons": [dict(r) for r in DROP_REASONS],
        "progress": progress(project_id),
        "next": next_actions(project_id),
        "stages": STAGES,
        "states": [state_meta(k) for k in STATE_ORDER],
    }
