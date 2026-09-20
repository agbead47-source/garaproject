# -*- coding: utf-8 -*-
"""무역 서류 리비전 - 어느 게 최종인가.

견적을 내고 발주가 진행되면 PI·CI·P/L 이 오간다. 수량이 바뀌고 단가가 바뀌고
선적 조건이 바뀐다. 그때마다 파일을 새로 만들어 메일로 보낸다.
파일 이름은 `견적서_최종.xlsx`, `견적서_최종_수정.xlsx`, `견적서_진짜최종.xlsx` 가 된다.

**사고는 여기서 난다.** 바이어는 Rev 2 를 보고 발주했는데 공장에는 Rev 1 이
넘어가 있다. 수량이 다르면 그대로 잘못 만든다.

그래서 발행할 때마다 한 줄씩 남기고, 확정된 판은 **잠근다.**

지켜야 할 것:
  - 지우지 않는다. 틀린 판도 남긴다. 어디서 갈렸는지 봐야 한다
  - **잠근 판은 고칠 수 없다.** 고치려면 새 리비전을 낸다
  - 무엇이 바뀌었는지 적게 한다. 적지 않으면 나중에 아무도 모른다
  - 확정판은 하나뿐이다. 새로 확정하면 앞의 확정은 풀린다
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
DB_PATH = os.path.join(DATA_DIR, "doc_revs.db")

_local = threading.local()

# 서류 종류
KINDS = {
    "quote": {"label": "견적서 (Quotation)", "icon": "💰",
              "note": "가격 제안입니다. 아직 계약이 아닙니다"},
    "pi": {"label": "프로포마 인보이스 (PI)", "icon": "📄",
           "note": "바이어가 이걸로 송금하거나 L/C 를 엽니다. 숫자가 틀리면 돈이 틀립니다"},
    "ci": {"label": "커머셜 인보이스 (CI)", "icon": "📄",
           "note": "통관 금액의 근거입니다. PI 와 다르면 통관에서 걸립니다"},
    "pl": {"label": "패킹리스트 (P/L)", "icon": "📦",
           "note": "CI 와 수량·중량이 맞아야 합니다"},
    "spec": {"label": "제품 사양서", "icon": "🧪", "note": ""},
    "other": {"label": "기타", "icon": "📎", "note": ""},
}
KIND_ORDER = ["quote", "pi", "ci", "pl", "spec", "other"]

STATES = {
    "draft": {"label": "작성 중", "css": "draft",
              "desc": "아직 안 보냈습니다. 고칠 수 있습니다"},
    "sent": {"label": "발송함", "css": "sent",
             "desc": "바이어에게 나갔습니다"},
    "final": {"label": "확정", "css": "final",
              "desc": "이 판으로 진행합니다. 잠겨 있어 고칠 수 없습니다"},
    "void": {"label": "폐기", "css": "void",
             "desc": "쓰지 않기로 한 판입니다. 기록으로만 남깁니다"},
}
STATE_ORDER = ["draft", "sent", "final", "void"]


SCHEMA = """
CREATE TABLE IF NOT EXISTS rev (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'quote',
    rev        INTEGER NOT NULL DEFAULT 0,
    state      TEXT NOT NULL DEFAULT 'draft',
    title      TEXT NOT NULL DEFAULT '',
    summary    TEXT NOT NULL DEFAULT '',   -- 이번 판에서 바뀐 것
    amount     TEXT NOT NULL DEFAULT '',   -- 금액·수량처럼 틀리면 사고 나는 값
    qty        TEXT NOT NULL DEFAULT '',
    terms      TEXT NOT NULL DEFAULT '',
    file_name  TEXT NOT NULL DEFAULT '',
    sent_to    TEXT NOT NULL DEFAULT '',
    author     TEXT NOT NULL DEFAULT '',
    at         TEXT NOT NULL,
    locked_at  TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_rev_project ON rev(project_id, kind);
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


def _clean(value, limit):
    return (str(value or "").strip())[:limit]


FIELDS = {"title": 160, "summary": 500, "amount": 60, "qty": 40,
          "terms": 120, "file_name": 200, "sent_to": 160, "author": 40}


def next_rev(project_id, kind):
    row = _conn().execute(
        "SELECT MAX(rev) AS n FROM rev WHERE project_id = ? AND kind = ?",
        (project_id, kind)).fetchone()
    return (row["n"] or 0) + 1


def add(project_id, kind, data):
    """새 판을 낸다. 앞 판을 고치지 않고 번호를 올린다."""
    if kind not in KINDS:
        kind = "other"
    out = {key: _clean(data.get(key), limit) for key, limit in FIELDS.items()}
    state = data.get("state") if data.get("state") in STATES else "draft"
    rev = next_rev(project_id, kind)

    conn = _conn()
    cur = conn.execute(
        "INSERT INTO rev (project_id, kind, rev, state, {}, at, locked_at) "
        "VALUES (?,?,?,?, {}, ?, ?)".format(
            ", ".join(out), ", ".join("?" * len(out))),
        [project_id, kind, rev, state] + list(out.values())
        + [_now(), _now() if state == "final" else ""])

    if state == "final":
        _unfinal_others(conn, project_id, kind, cur.lastrowid)
    conn.commit()
    return cur.lastrowid


def _unfinal_others(conn, project_id, kind, keep_id):
    """확정판은 하나뿐이다. 새로 확정하면 앞의 확정은 풀린다."""
    conn.execute(
        "UPDATE rev SET state = 'sent', locked_at = '' "
        "WHERE project_id = ? AND kind = ? AND id != ? AND state = 'final'",
        (project_id, kind, keep_id))


def update(rev_id, data):
    """고치기. **잠긴 판은 못 고친다.**"""
    row = _conn().execute("SELECT * FROM rev WHERE id = ?", (rev_id,)).fetchone()
    if row is None:
        return False, "찾을 수 없습니다."
    if row["state"] == "final":
        return False, ("확정된 판은 고칠 수 없습니다. "
                       "바꾸려면 새 리비전(Rev {})을 내세요."
                       .format(next_rev(row["project_id"], row["kind"])))

    out = {key: _clean(data.get(key), limit) for key, limit in FIELDS.items()}
    _conn().execute(
        "UPDATE rev SET {} WHERE id = ?".format(
            ", ".join("{} = ?".format(k) for k in out)),
        list(out.values()) + [rev_id])
    _conn().commit()
    return True, "고쳤습니다."


def set_state(rev_id, state):
    if state not in STATES:
        return False, "알 수 없는 상태입니다."
    conn = _conn()
    row = conn.execute("SELECT * FROM rev WHERE id = ?", (rev_id,)).fetchone()
    if row is None:
        return False, "찾을 수 없습니다."

    conn.execute("UPDATE rev SET state = ?, locked_at = ? WHERE id = ?",
                 (state, _now() if state == "final" else "", rev_id))
    if state == "final":
        _unfinal_others(conn, row["project_id"], row["kind"], rev_id)
    conn.commit()

    if state == "final":
        return True, ("Rev {} 을(를) 확정했습니다. 이 판은 잠겨서 고칠 수 없습니다. "
                      "앞의 확정판이 있었다면 '발송함' 으로 내려갑니다."
                      .format(row["rev"]))
    return True, "상태를 바꿨습니다."


def remove(rev_id):
    """잠긴 판은 지우지 않는다. 폐기로만 바꾼다."""
    row = _conn().execute("SELECT state FROM rev WHERE id = ?",
                          (rev_id,)).fetchone()
    if row is None:
        return False, "찾을 수 없습니다."
    if row["state"] == "final":
        return False, "확정된 판은 지울 수 없습니다. 폐기로 바꾸거나 새 판을 내세요."
    _conn().execute("DELETE FROM rev WHERE id = ?", (rev_id,))
    _conn().commit()
    return True, "지웠습니다."


def _decorate(row):
    item = dict(row)
    item["kind_meta"] = KINDS.get(item["kind"], KINDS["other"])
    item["state_meta"] = dict(STATES.get(item["state"], STATES["draft"]),
                              key=item["state"])
    item["locked"] = item["state"] == "final"
    item["name"] = "{} Rev {}".format(item["kind_meta"]["label"], item["rev"])
    return item


def of_project(project_id, kind=None):
    sql = "SELECT * FROM rev WHERE project_id = ?"
    args = [project_id]
    if kind:
        sql += " AND kind = ?"
        args.append(kind)
    sql += " ORDER BY kind, rev DESC"
    return [_decorate(r) for r in _conn().execute(sql, args)]


def board(project_id):
    """종류별로 묶어서. 종류마다 확정판이 무엇인지가 제일 중요하다."""
    rows = of_project(project_id)
    groups = []
    for key in KIND_ORDER:
        mine = [r for r in rows if r["kind"] == key]
        if not mine:
            continue
        final = next((r for r in mine if r["locked"]), None)
        latest = mine[0]
        groups.append({
            "kind": key,
            "meta": KINDS[key],
            "rows": mine,
            "final": final,
            "latest": latest,
            # 최신판이 확정판이 아니면 둘이 엇갈려 있다는 뜻이다
            "drifted": bool(final and latest["id"] != final["id"]),
        })
    return {
        "groups": groups,
        "total": len(rows),
        "final_count": sum(1 for r in rows if r["locked"]),
        "drifted": [g for g in groups if g["drifted"]],
    }


def kinds():
    return [dict(KINDS[k], value=k) for k in KIND_ORDER]


def states():
    return [dict(STATES[k], value=k) for k in STATE_ORDER]
