# -*- coding: utf-8 -*-
"""복합 원료 수동 매핑 - 'Glowtree Complex GT-7' 안에 뭐가 들었나.

성분표에 자사 혼합물이나 추출물 블렌드가 한 줄로 적혀 오는 일이 아주 흔하다.
`GT-7 Brightening Complex 3.0%` 한 줄로는 어느 나라 기준에도 대조할 수 없다.
INCI 사전에 그런 이름이 없기 때문이다.

지금까지는 '매칭하지 못한 행' 으로 빼 두고 끝이었다. 그러면 그 3%가
**규제 대조에서 통째로 빠진다.** 그 안에 레티놀이 들어 있어도 모른다.

그래서 담당자가 원료사 사양서를 보고 직접 쪼개 넣게 한다.

  GT-7 Brightening Complex  3.0%   ← 처방에 넣는 양
    ├ Ascorbyl Glucoside    20%    ← 원료 안에서의 비율
    ├ Niacinamide           10%
    └ Butylene Glycol       70%

**처방 내 실제 함량 = 원료 투입량 × 원료 내 비율** 이다.
위라면 Ascorbyl Glucoside 는 3.0% x 20% = 0.6% 다.
이 곱셈을 사람이 암산하면 자리 수를 틀린다. 그래서 계산해서 보여 준다.

지켜야 할 것:
  - 원료 내 비율 합이 100%가 아니면 **고쳐 주지 않는다.** 그렇다고 적어 준다.
    사양서에 "기타 90%" 가 안 적힌 경우가 많아서, 합이 안 맞는 게 정상일 때도 있다
  - 비율을 모르면 비워 둔다. 0으로 채우면 '안 들어 있다' 가 된다
  - 한 번 쪼개 두면 같은 이름이 다시 올라와도 그대로 쓴다 (매번 다시 적지 않는다)
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
DB_PATH = os.path.join(DATA_DIR, "mixes.db")

_local = threading.local()

PERCENT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")

SCHEMA = """
CREATE TABLE IF NOT EXISTS mix (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    key        TEXT NOT NULL UNIQUE,      -- 정규화한 원료 이름
    name       TEXT NOT NULL,             -- 성분표에 적힌 이름 그대로
    raw        TEXT NOT NULL DEFAULT '',  -- 원문 줄
    dose       TEXT NOT NULL DEFAULT '',  -- 처방에 넣는 양 (3.0%)
    note       TEXT NOT NULL DEFAULT '',
    author     TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS part (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    mix_id  INTEGER NOT NULL,
    inci    TEXT NOT NULL,
    name    TEXT NOT NULL DEFAULT '',     -- 국문 표기 (있으면)
    ratio   TEXT NOT NULL DEFAULT '',     -- 원료 안에서의 비율
    note    TEXT NOT NULL DEFAULT '',
    seq     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_part_mix ON part(mix_id);
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
    return datetime.now(SEOUL).strftime("%Y-%m-%d %H:%M")


def norm_key(name):
    """이름 표기가 조금 달라도 같은 원료로 본다."""
    text = unicodedata.normalize("NFKC", (name or "")).strip().lower()
    return re.sub(r"[^a-z0-9가-힣]+", "", text)


def _clean(value, limit):
    return (str(value or "").strip())[:limit]


def percent_of(text):
    """'3.0%' -> 3.0. 못 읽으면 None (0 으로 때우지 않는다)."""
    m = PERCENT_RE.search(str(text or ""))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def _fmt(value):
    """0.6 -> '0.6', 3.0 -> '3'"""
    return ("%g" % round(value, 4))


# ---------------------------------------------------------------------------
# 읽기
# ---------------------------------------------------------------------------

def _parts_of(mix_id):
    return [dict(r) for r in _conn().execute(
        "SELECT * FROM part WHERE mix_id = ? ORDER BY seq, id", (mix_id,))]


def _decorate(row):
    """처방 내 실제 함량까지 계산해서 돌려준다."""
    mix = dict(row)
    dose = percent_of(mix["dose"])
    mix["dose_value"] = dose
    parts = []
    ratio_sum = 0.0
    unknown = 0

    for part in _parts_of(mix["id"]):
        ratio = percent_of(part["ratio"])
        part["ratio_value"] = ratio
        if ratio is None:
            unknown += 1
            part["actual"] = ""
            part["actual_value"] = None
        else:
            ratio_sum += ratio
            if dose is None:
                part["actual"] = ""
                part["actual_value"] = None
            else:
                value = dose * ratio / 100.0
                part["actual_value"] = value
                part["actual"] = "{}%".format(_fmt(value))
        parts.append(part)

    mix["parts"] = parts
    mix["ratio_sum"] = round(ratio_sum, 4)
    mix["ratio_unknown"] = unknown
    # 합이 100 이 아니어도 고쳐 주지 않는다. 사양서에 기타 성분이 빠져 있을 수 있다
    mix["ratio_ok"] = abs(ratio_sum - 100.0) < 0.01 and not unknown
    if unknown:
        mix["ratio_note"] = ("비율을 적지 않은 성분이 {}건 있습니다. "
                             "그 성분은 처방 내 함량을 계산하지 않습니다.".format(unknown))
    elif mix["ratio_ok"]:
        mix["ratio_note"] = "원료 내 비율 합계 100%."
    else:
        mix["ratio_note"] = ("원료 내 비율 합계가 {}% 입니다. "
                             "사양서에 기타 성분이 빠져 있으면 100%가 아닌 게 "
                             "정상입니다. 임의로 맞추지 않았습니다."
                             .format(_fmt(ratio_sum)))
    if dose is None:
        mix["dose_note"] = "처방 투입량을 읽지 못해 실제 함량을 계산하지 못했습니다."
    else:
        mix["dose_note"] = ""
    return mix


def get(name):
    row = _conn().execute("SELECT * FROM mix WHERE key = ?",
                          (norm_key(name),)).fetchone()
    return _decorate(row) if row else None


def get_by_id(mix_id):
    row = _conn().execute("SELECT * FROM mix WHERE id = ?", (mix_id,)).fetchone()
    return _decorate(row) if row else None


def all_mixes():
    return [_decorate(r) for r in _conn().execute(
        "SELECT * FROM mix ORDER BY updated_at DESC, id DESC")]


def count():
    return _conn().execute("SELECT COUNT(*) FROM mix").fetchone()[0]


# ---------------------------------------------------------------------------
# 쓰기
# ---------------------------------------------------------------------------

def save(name, raw="", dose="", parts=None, note="", author=""):
    """복합 원료 하나를 쪼개 저장한다. 하위 성분이 없으면 저장하지 않는다."""
    rows = []
    for index, part in enumerate(parts or []):
        inci = _clean(part.get("inci"), 160)
        if not inci:
            continue
        rows.append({
            "inci": inci,
            "name": _clean(part.get("name"), 120),
            "ratio": _clean(part.get("ratio"), 24),
            "note": _clean(part.get("note"), 200),
            "seq": index,
        })
    if not rows:
        return None

    conn = _conn()
    key = norm_key(name)
    stamp = _now()
    conn.execute(
        """INSERT INTO mix (key, name, raw, dose, note, author, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(key) DO UPDATE SET
             name = excluded.name, raw = excluded.raw, dose = excluded.dose,
             note = excluded.note, author = excluded.author,
             updated_at = excluded.updated_at""",
        (key, _clean(name, 160), _clean(raw, 200), _clean(dose, 24),
         _clean(note, 500), _clean(author, 40), stamp, stamp))
    mix_id = conn.execute("SELECT id FROM mix WHERE key = ?", (key,)).fetchone()["id"]

    # 쪼갠 내용은 통째로 갈아 끼운다. 지운 줄이 남아 있으면 안 된다
    conn.execute("DELETE FROM part WHERE mix_id = ?", (mix_id,))
    for row in rows:
        conn.execute(
            "INSERT INTO part (mix_id, inci, name, ratio, note, seq) "
            "VALUES (?,?,?,?,?,?)",
            (mix_id, row["inci"], row["name"], row["ratio"], row["note"], row["seq"]))
    conn.commit()
    return mix_id


def remove(mix_id):
    conn = _conn()
    conn.execute("DELETE FROM part WHERE mix_id = ?", (mix_id,))
    cur = conn.execute("DELETE FROM mix WHERE id = ?", (mix_id,))
    conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# 규제 대조에 넘길 성분 줄
# ---------------------------------------------------------------------------

def as_ingredients(name):
    """쪼갠 하위 성분을 규제 대조용 성분 줄로 바꾼다.

    함량은 **처방 내 실제 함량**을 적는다. 원료 내 비율(20%)을 그대로 넘기면
    0.6% 짜리를 20% 로 판정해 엉뚱하게 '기준 초과' 가 난다.
    """
    mix = get(name)
    if not mix:
        return []

    rows = []
    for index, part in enumerate(mix["parts"]):
        rows.append({
            "key": "mix-{}-{}".format(mix["id"], index),
            "name": part["name"] or part["inci"],
            "inci": part["inci"],
            "category": "복합 원료 구성",
            # 계산이 안 된 성분은 함량을 비워 둔다. 0 으로 채우면 '안 들어감' 이 된다
            "requested": part["actual"] or "",
            "from_mix": mix["name"],
            "from_mix_id": mix["id"],
            "mix_ratio": part["ratio"],
            "mix_dose": mix["dose"],
        })
    return rows
