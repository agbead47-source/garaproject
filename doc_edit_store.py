# -*- coding: utf-8 -*-
"""내부 전달 문서에서 고친 값 저장소.

자동 변환이 늘 맞게 나오지는 않는다. 용량 표기가 어색하거나, 납기를 영업이
고객사와 다시 잡았거나, "이 건은 무향 샘플부터"처럼 한 줄 덧붙여야 할 때가
있다. 그 수정이 새로고침 한 번에 날아가면 아무도 이 화면에서 고치지 않는다.

그래서 고친 값만 SQLite(data/doc_edits.db)에 남긴다. 원래 값은 저장하지 않는다.
변환 결과가 바뀌면 고친 값이 그 위에 다시 덮이면 된다. 되돌리기를 누르면
저장한 줄을 지우고 자동 변환 값으로 돌아간다.

문서 하나를 가리키는 키는 `원본파일|문서종류|언어` 세 조각이다.
언어까지 넣는 이유는, 한국어 문서에 적은 문장이 영문 문서에 그대로 끼어들면
안 되기 때문이다.
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
DB_PATH = os.path.join(DATA_DIR, "doc_edits.db")

_local = threading.local()

# 문서 종류 - 이 셋 말고는 받지 않는다
DOC_KINDS = ("lab", "factory", "sales")

# 고객사 소개 밑의 영업 담당자 코멘트. 자동 변환에는 없는 칸이라 키를 따로 둔다
COMMENT_FIELD = "_comment"

LIMITS = {"doc_key": 300, "field": 60, "value": 500}

# 원본 파일명에 공백·한글·괄호가 들어와도 되지만, 구분자(|)는 못 들어간다
_DOC_KEY_RE = re.compile(r"^[^|]{1,200}\|(%s)\|[a-z]{2}$" % "|".join(DOC_KINDS))
_FIELD_RE = re.compile(r"^[A-Za-z0-9_]{1,60}$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS doc_edits (
    doc_key    TEXT NOT NULL,
    field      TEXT NOT NULL,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (doc_key, field)
);
"""


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


def doc_key(file_name, kind, lang):
    """문서 하나를 가리키는 키. 파일명은 구분자만 털어 낸다."""
    name = (file_name or "(무제)").replace("|", "/").strip()[:200] or "(무제)"
    kind = kind if kind in DOC_KINDS else "lab"
    lang = (lang or "ko")[:2].lower()
    return "{}|{}|{}".format(name, kind, lang)


def valid_key(key):
    return bool(key) and bool(_DOC_KEY_RE.match(key))


def valid_field(field):
    return bool(field) and bool(_FIELD_RE.match(field))


# ---------------------------------------------------------------------------
# 조회
# ---------------------------------------------------------------------------

def edits_for(key):
    """{항목 키: 고친 값} - 문서 한 벌을 그릴 때 한 번 읽는다."""
    if not valid_key(key):
        return {}
    conn = connect()
    rows = conn.execute(
        "SELECT field, value FROM doc_edits WHERE doc_key = ?", (key,))
    return {r["field"]: r["value"] for r in rows}


def count_for(keys):
    """여러 문서의 수정 건수 합. (되돌리기 버튼을 보여줄지 판단용)"""
    keys = [k for k in keys if valid_key(k)]
    if not keys:
        return 0
    conn = connect()
    sql = "SELECT COUNT(*) FROM doc_edits WHERE doc_key IN ({})".format(
        ",".join("?" * len(keys)))
    return conn.execute(sql, keys).fetchone()[0]


# ---------------------------------------------------------------------------
# 저장
# ---------------------------------------------------------------------------

def save_edit(key, field, value):
    """고친 값 한 칸을 남긴다.

    빈 값으로 저장하면 줄을 지운다 - 자동 변환 값으로 돌아간다는 뜻이다.
    돌려주는 값은 화면에 실제로 들어갈 값이다(길이를 잘랐을 수 있다).
    """
    if not (valid_key(key) and valid_field(field)):
        return None

    value = (value or "").strip()[:LIMITS["value"]]
    conn = connect()
    if not value:
        conn.execute("DELETE FROM doc_edits WHERE doc_key = ? AND field = ?",
                     (key, field))
        conn.commit()
        return ""

    conn.execute(
        "INSERT INTO doc_edits (doc_key, field, value, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(doc_key, field) DO UPDATE SET value = excluded.value, "
        "updated_at = excluded.updated_at",
        (key, field, value, now_iso()))
    conn.commit()
    return value


def reset_docs(keys):
    """문서 몇 벌의 수정을 통째로 지운다. 지운 줄 수를 돌려준다."""
    keys = [k for k in keys if valid_key(k)]
    if not keys:
        return 0
    conn = connect()
    cur = conn.execute("DELETE FROM doc_edits WHERE doc_key IN ({})".format(
        ",".join("?" * len(keys))), keys)
    conn.commit()
    return cur.rowcount


def apply_to(doc, key):
    """문서 한 벌에 저장된 수정을 덮어씌운다.

    `edited` 를 붙여 두면 화면에서 고친 칸을 노란색으로 표시할 수 있고,
    `auto` 에 자동 변환 값을 남겨 두면 되돌렸을 때 그 값으로 돌아간다.
    """
    edits = edits_for(key)
    doc["edit_key"] = key
    doc["comment"] = edits.get(COMMENT_FIELD, "")
    doc["edited_count"] = len(edits)

    for section in doc.get("sections", []):
        for row in section["rows"]:
            row["auto"] = row["value"]
            if row["key"] in edits:
                row["value"] = edits[row["key"]]
                row["edited"] = True
            else:
                row["edited"] = False
    return doc
