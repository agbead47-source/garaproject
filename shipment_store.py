# -*- coding: utf-8 -*-
"""선적과 서류 - "내 물건 언제 출발해?" 에 답하는 자리.

바이어가 제일 자주 묻는 두 가지가 이것이다.
  "언제 출발해?"      ETD / ATD
  "B/L 사본 언제 줘?"  서류 상태

그런데 이 정보는 포워더 메일함에 흩어져 있다. 물어볼 때마다 메일을 뒤진다.

**서류 목록은 거래조건(Incoterms)에 따라 달라진다.** 이게 핵심이다.
EXW 로 팔면 수출통관도 바이어 몫이라 우리가 B/L 을 줄 일이 없고,
CIF 면 보험증권까지 우리가 낸다. 조건을 안 보고 서류 목록을 고정해 두면
"왜 보험증권을 안 줘요?" 와 "이건 우리가 왜 해요?" 가 같이 나온다.

지켜야 할 것:
  - 날짜를 모르면 비워 둔다. ETD 를 지어내면 바이어가 그 날짜로 창고를 잡는다
  - **예정(ETD/ETA)과 실제(ATD/ATA)를 같은 칸에 넣지 않는다.** 섞이면
    "출발했다" 와 "출발할 예정이다" 가 구분이 안 된다
  - 포워더가 준 날짜인지 우리가 잡은 날짜인지 적는다
  - 서류는 '발급' 과 '바이어 송부' 와 '원본 발송' 이 다 다른 단계다
"""

import os
import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    SEOUL = ZoneInfo("Asia/Seoul")
except Exception:                                    # noqa: BLE001
    SEOUL = timezone.utc

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "shipments.db")

_local = threading.local()


# ---------------------------------------------------------------------------
# 거래조건별 우리 몫
# ---------------------------------------------------------------------------
#   ours: 이 조건에서 **우리(매도인)가** 내는 서류
#   뒤로 갈수록 우리가 부담하는 범위가 넓어진다.
#
#   CoA·MSDS 는 어느 조건에서도 우리 몫이다. 거래조건이 아니라
#   **제조사가 내는 제품 서류**라서 EXW 로 팔아도 바이어가 요구한다.
#   그래서 PRODUCT_DOCS 로 따로 두고 모든 조건에 더한다.

INCOTERMS = [
    {"code": "EXW", "label": "EXW · 공장 인도",
     "desc": "공장에서 넘깁니다. 수출통관도 바이어 몫입니다.",
     "ours": ["pi", "ci", "pl"]},
    {"code": "FCA", "label": "FCA · 운송인 인도",
     "desc": "수출통관까지 우리가 합니다.",
     "ours": ["pi", "ci", "pl", "co", "export"]},
    {"code": "FOB", "label": "FOB · 본선 인도",
     "desc": "선적항 본선에 올릴 때까지 우리 몫입니다.",
     "ours": ["pi", "ci", "pl", "co", "export", "bl"]},
    {"code": "CFR", "label": "CFR · 운임 포함",
     "desc": "도착항까지 운임을 우리가 냅니다.",
     "ours": ["pi", "ci", "pl", "co", "export", "bl"]},
    {"code": "CIF", "label": "CIF · 운임·보험 포함",
     "desc": "운임에 적하보험까지 우리가 냅니다.",
     "ours": ["pi", "ci", "pl", "co", "export", "bl", "insurance"]},
    {"code": "DAP", "label": "DAP · 목적지 인도",
     "desc": "도착지까지 가져다 줍니다. 수입통관은 바이어 몫입니다.",
     "ours": ["pi", "ci", "pl", "co", "export", "bl", "insurance"]},
    {"code": "DDP", "label": "DDP · 관세 포함 인도",
     "desc": "수입통관·관세까지 우리가 냅니다. 부담이 가장 큽니다.",
     "ours": ["pi", "ci", "pl", "co", "export", "bl", "insurance", "import"]},
]
# 거래조건과 무관하게 제조사가 내는 서류
PRODUCT_DOCS = ["coa", "msds"]
for _row in INCOTERMS:
    _row["ours"] = _row["ours"] + PRODUCT_DOCS

INCOTERM_MAP = {row["code"]: row for row in INCOTERMS}
DEFAULT_INCOTERM = "FOB"


# ---------------------------------------------------------------------------
# 서류
# ---------------------------------------------------------------------------

DOCS = [
    {"key": "pi", "label": "프로포마 인보이스 (PI)", "icon": "📄",
     "when": "발주 전", "note": "바이어가 이걸로 송금·L/C 를 엽니다"},
    {"key": "ci", "label": "커머셜 인보이스 (CI)", "icon": "📄",
     "when": "선적 시", "note": "통관 금액의 근거입니다"},
    {"key": "pl", "label": "패킹리스트 (P/L)", "icon": "📦",
     "when": "선적 시", "note": "박스 수·중량·부피. CI 와 숫자가 맞아야 합니다"},
    {"key": "bl", "label": "선하증권 (B/L · AWB)", "icon": "🚢",
     "when": "출항 후", "note": "원본이 있어야 화물을 찾습니다. 사본 먼저 보내 달라는 "
                               "요청이 제일 많습니다"},
    {"key": "co", "label": "원산지증명서 (C/O)", "icon": "🏷",
     "when": "선적 전후", "note": "FTA 특혜세율을 쓰려면 양식이 따로 있습니다"},
    {"key": "insurance", "label": "적하보험증권", "icon": "🛡",
     "when": "선적 전", "note": "CIF·DAP·DDP 에서 우리가 냅니다"},
    {"key": "export", "label": "수출신고필증", "icon": "🛃",
     "when": "선적 전", "note": "국내 서류입니다. 바이어에게 줄 일은 드뭅니다",
     "internal": True},
    {"key": "import", "label": "수입통관 서류", "icon": "🛃",
     "when": "도착 후", "note": "DDP 에서만 우리 몫입니다"},
    {"key": "coa", "label": "시험성적서 (CoA)", "icon": "🔬",
     "when": "선적 시", "note": "배치별로 나옵니다"},
    {"key": "msds", "label": "MSDS / SDS", "icon": "⚗",
     "when": "선적 시", "note": "항공 운송이면 거의 항상 요구합니다"},
]
DOC_MAP = {row["key"]: row for row in DOCS}

# 서류 하나의 진행 단계. '만들었다' 와 '보냈다' 와 '원본을 보냈다' 는 다르다.
DOC_STATES = {
    "none": {"label": "준비 전", "css": "none", "rank": 0},
    "ready": {"label": "발급 완료", "css": "ready", "rank": 1},
    "sent": {"label": "사본 송부", "css": "sent", "rank": 2},
    "original": {"label": "원본 발송", "css": "done", "rank": 3},
    "na": {"label": "해당 없음", "css": "na", "rank": 4},
}
DOC_STATE_ORDER = ["none", "ready", "sent", "original", "na"]

# 선적 건의 상태
STATUSES = {
    "booking": {"label": "부킹 중", "css": "warn", "step": 0},
    "booked": {"label": "부킹 확정", "css": "ok", "step": 1},
    "departed": {"label": "출항", "css": "ok", "step": 2},
    "arrived": {"label": "도착", "css": "confirmed", "step": 3},
    "cleared": {"label": "통관 완료", "css": "confirmed", "step": 4},
    "hold": {"label": "보류", "css": "none", "step": 0},
}
STATUS_ORDER = ["booking", "booked", "departed", "arrived", "cleared", "hold"]

MODES = {
    "sea": {"label": "해상", "icon": "🚢", "doc": "B/L"},
    "air": {"label": "항공", "icon": "✈️", "doc": "AWB"},
    "express": {"label": "특송", "icon": "📮", "doc": "운송장"},
}
MODE_ORDER = ["sea", "air", "express"]


SCHEMA = """
CREATE TABLE IF NOT EXISTS shipment (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL,
    label       TEXT NOT NULL DEFAULT '',
    incoterm    TEXT NOT NULL DEFAULT 'FOB',
    mode        TEXT NOT NULL DEFAULT 'sea',
    status      TEXT NOT NULL DEFAULT 'booking',
    forwarder   TEXT NOT NULL DEFAULT '',
    booking_no  TEXT NOT NULL DEFAULT '',
    bl_no       TEXT NOT NULL DEFAULT '',
    container   TEXT NOT NULL DEFAULT '',
    port_from   TEXT NOT NULL DEFAULT '',
    port_to     TEXT NOT NULL DEFAULT '',
    etd         TEXT NOT NULL DEFAULT '',   -- 출항 예정
    atd         TEXT NOT NULL DEFAULT '',   -- 실제 출항
    eta         TEXT NOT NULL DEFAULT '',   -- 도착 예정
    ata         TEXT NOT NULL DEFAULT '',   -- 실제 도착
    date_source TEXT NOT NULL DEFAULT '',   -- 이 날짜를 누가 줬나
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shipment_doc (
    shipment_id INTEGER NOT NULL,
    key         TEXT NOT NULL,
    state       TEXT NOT NULL DEFAULT 'none',
    at          TEXT NOT NULL DEFAULT '',
    note        TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (shipment_id, key)
);

CREATE INDEX IF NOT EXISTS idx_ship_project ON shipment(project_id);
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


def _stamp():
    return _now().strftime("%Y-%m-%d %H:%M:%S")


def _clean(value, limit):
    return (str(value or "").strip())[:limit]


def _as_date(text):
    text = (text or "").strip()[:10]
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------

FIELDS = {
    "label": 80, "incoterm": 8, "mode": 10, "status": 12,
    "forwarder": 80, "booking_no": 40, "bl_no": 40, "container": 80,
    "port_from": 60, "port_to": 60,
    "etd": 10, "atd": 10, "eta": 10, "ata": 10,
    "date_source": 80, "note": 500,
}


def _payload(data):
    out = {key: _clean(data.get(key), limit) for key, limit in FIELDS.items()}
    if out["incoterm"] not in INCOTERM_MAP:
        out["incoterm"] = DEFAULT_INCOTERM
    if out["mode"] not in MODES:
        out["mode"] = "sea"
    if out["status"] not in STATUSES:
        out["status"] = "booking"
    # 날짜는 읽히는 것만 남긴다. 못 읽으면 비워 둔다 - 지어내지 않는다
    for key in ("etd", "atd", "eta", "ata"):
        out[key] = out[key] if _as_date(out[key]) else ""
    return out


def add(project_id, data):
    out = _payload(data)
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO shipment (project_id, {}, created_at, updated_at) "
        "VALUES (?, {}, ?, ?)".format(
            ", ".join(out), ", ".join("?" * len(out))),
        [project_id] + list(out.values()) + [_stamp(), _stamp()])
    conn.commit()
    return cur.lastrowid


def update(shipment_id, data):
    out = _payload(data)
    conn = _conn()
    conn.execute(
        "UPDATE shipment SET {}, updated_at = ? WHERE id = ?".format(
            ", ".join("{} = ?".format(k) for k in out)),
        list(out.values()) + [_stamp(), shipment_id])
    conn.commit()
    return True


def remove(shipment_id):
    conn = _conn()
    conn.execute("DELETE FROM shipment_doc WHERE shipment_id = ?", (shipment_id,))
    conn.execute("DELETE FROM shipment WHERE id = ?", (shipment_id,))
    conn.commit()
    return True


def set_doc(shipment_id, key, state, at="", note=""):
    if key not in DOC_MAP or state not in DOC_STATES:
        return False
    conn = _conn()
    conn.execute(
        "INSERT INTO shipment_doc (shipment_id, key, state, at, note) "
        "VALUES (?,?,?,?,?) "
        "ON CONFLICT(shipment_id, key) DO UPDATE SET "
        "state = excluded.state, at = excluded.at, note = excluded.note",
        (shipment_id, key, state,
         _clean(at, 10) if _as_date(at) else (today_iso() if state != "none" else ""),
         _clean(note, 200)))
    conn.commit()
    return True


# ---------------------------------------------------------------------------
# 읽기
# ---------------------------------------------------------------------------

def _dday(day, ref=None):
    target = _as_date(day)
    if not target:
        return None, ""
    ref = ref or _now().date()
    days = (target - ref).days
    if days < 0:
        return days, "D+{}".format(-days)
    if days == 0:
        return 0, "오늘"
    return days, "D-{}".format(days)


def _decorate(row):
    ship = dict(row)
    term = INCOTERM_MAP.get(ship["incoterm"], INCOTERM_MAP[DEFAULT_INCOTERM])
    mode = MODES.get(ship["mode"], MODES["sea"])
    ship["incoterm_meta"] = term
    ship["mode_meta"] = mode
    ship["status_meta"] = STATUSES.get(ship["status"], STATUSES["booking"])

    saved = {r["key"]: dict(r) for r in _conn().execute(
        "SELECT * FROM shipment_doc WHERE shipment_id = ?", (ship["id"],))}

    docs = []
    for spec in DOCS:
        mine = spec["key"] in term["ours"]
        row_state = (saved.get(spec["key"]) or {}).get("state")
        if not row_state:
            # 이 조건에서 우리 몫이 아니면 처음부터 '해당 없음' 으로 둔다
            row_state = "none" if mine else "na"
        docs.append(dict(
            spec,
            state=row_state,
            state_meta=dict(DOC_STATES[row_state], key=row_state),
            at=(saved.get(spec["key"]) or {}).get("at", ""),
            note_saved=(saved.get(spec["key"]) or {}).get("note", ""),
            ours=mine,
            # 항공이면 B/L 이 아니라 AWB 다
            label=(spec["label"] if spec["key"] != "bl"
                   else "{} ({})".format(
                       "항공운송장" if ship["mode"] == "air" else "선하증권",
                       mode["doc"])),
        ))

    mine_docs = [d for d in docs if d["ours"]]
    done = [d for d in mine_docs if d["state"] in ("sent", "original")]
    ship["docs"] = docs
    ship["docs_mine"] = mine_docs
    ship["docs_done"] = len(done)
    ship["docs_total"] = len(mine_docs)
    ship["docs_open"] = [d for d in mine_docs if d["state"] == "none"]

    # 예정과 실제를 절대 같은 칸에 넣지 않는다
    ship["etd_days"], ship["etd_label"] = _dday(ship["etd"])
    ship["eta_days"], ship["eta_label"] = _dday(ship["eta"])
    ship["departed"] = bool(ship["atd"])
    ship["arrived"] = bool(ship["ata"])

    # 지연: 실제가 예정보다 늦었나
    ship["etd_late"] = _late(ship["etd"], ship["atd"])
    ship["eta_late"] = _late(ship["eta"], ship["ata"])

    ship["next"] = _next_action(ship)
    return ship


def _late(planned, actual):
    plan, real = _as_date(planned), _as_date(actual)
    if not plan or not real:
        return None
    return (real - plan).days


def _next_action(ship):
    """지금 뭘 해야 하나. 바이어가 묻기 전에 알아야 한다."""
    if ship["status"] == "hold":
        return "보류 상태입니다. 무엇 때문에 멈췄는지 메모에 적어 두세요."
    if not ship["etd"]:
        return "출항 예정일(ETD)이 비어 있습니다. 포워더에게 부킹 확정을 받으세요."
    if not ship["departed"]:
        if ship["etd_days"] is not None and ship["etd_days"] < 0:
            return ("예정일({})이 지났는데 실제 출항일이 없습니다. "
                    "출항했는지 포워더에게 확인하세요.".format(ship["etd"]))
        return "출항 전입니다. 선적 서류를 미리 맞춰 두세요."
    bl = next((d for d in ship["docs_mine"] if d["key"] == "bl"), None)
    if bl and bl["state"] == "none":
        return ("출항했습니다. **B/L 사본**을 바이어가 곧 요청합니다. "
                "포워더에게 먼저 받아 두세요.").replace("**", "")
    if ship["docs_open"]:
        return "아직 준비 안 된 서류가 {}건 있습니다 — {}.".format(
            len(ship["docs_open"]),
            " · ".join(d["label"] for d in ship["docs_open"][:3]))
    if not ship["arrived"]:
        return "서류는 다 나갔습니다. 도착까지 지켜보면 됩니다."
    return "도착했습니다. 통관·인수 확인만 남았습니다."


def of_project(project_id):
    return [_decorate(r) for r in _conn().execute(
        "SELECT * FROM shipment WHERE project_id = ? ORDER BY "
        "CASE WHEN etd = '' THEN 1 ELSE 0 END, etd, id", (project_id,))]


def get(shipment_id):
    row = _conn().execute("SELECT * FROM shipment WHERE id = ?",
                          (shipment_id,)).fetchone()
    return _decorate(row) if row else None


def board(limit=20):
    """전체 선적 현황. 일정 화면에서 한눈에 본다."""
    rows = [_decorate(r) for r in _conn().execute(
        "SELECT * FROM shipment WHERE status != 'cleared' ORDER BY "
        "CASE WHEN etd = '' THEN 1 ELSE 0 END, etd LIMIT ?", (limit,))]
    return {
        "rows": rows,
        "total": len(rows),
        "sailing": sum(1 for r in rows if r["departed"] and not r["arrived"]),
        "waiting": sum(1 for r in rows if not r["departed"]),
        "no_etd": sum(1 for r in rows if not r["etd"]),
        "doc_open": sum(len(r["docs_open"]) for r in rows),
    }


def incoterms():
    return [dict(row) for row in INCOTERMS]


def doc_states():
    return [dict(DOC_STATES[k], value=k) for k in DOC_STATE_ORDER]


def modes():
    return [dict(MODES[k], value=k) for k in MODE_ORDER]


def statuses():
    return [dict(STATUSES[k], value=k) for k in STATUS_ORDER]
