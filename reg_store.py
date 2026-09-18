# -*- coding: utf-8 -*-
"""EU 화장품 규제 실데이터 조회 계층.

regdata/sync_eu.py 가 만들어 둔 SQLite(regdata/regulation.db)를 읽어
성분 하나가 EU에서 어떤 판정을 받는지 계산한다.

DB가 없으면 `is_available()` 이 False를 돌려주고, 화면은 기존 더미로 돌아간다.
(가안 상태에서도 그대로 실행되도록)
"""

import os
import re
import sqlite3
import threading

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "regdata", "regulation.db")

# 부속서별 성격 - 판정의 출발점
ANNEX_KIND = {
    "II": "ban",     # 사용 금지
    "III": "limit",  # 조건부 사용 제한
    "IV": "limit",   # 허용 색소 (용도 제한)
    "V": "limit",    # 허용 방부제
    "VI": "limit",   # 허용 자외선 차단성분
}

CAS_PATTERN = re.compile(r"\d{2,7}-\d{2}-\d")
# EU 법령은 소수점에 쉼표를 쓴다: "0,05 %"
PERCENT_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
UNUSED_WORDS = ("미사용", "free-from", "free from", "미배합", "불검출")

_local = threading.local()


def _connect():
    """스레드마다 읽기 전용 커넥션을 하나씩 쓴다. (Flask 개발 서버는 멀티스레드)"""
    con = getattr(_local, "con", None)
    if con is None:
        con = sqlite3.connect(DB_PATH, check_same_thread=False)
        con.row_factory = sqlite3.Row
        _local.con = con
    return con


def is_available():
    """실데이터 DB가 준비돼 있는지."""
    return os.path.exists(DB_PATH)


def get_meta():
    """수집 출처와 기준일. DB가 없으면 None."""
    if not is_available():
        return None
    rows = _connect().execute("SELECT key, value FROM meta").fetchall()
    return {r["key"]: r["value"] for r in rows}


# ---------------------------------------------------------------------------
# 이름 대조
# ---------------------------------------------------------------------------

def normalize_name(name):
    """sync_eu.py 와 같은 규칙으로 정규화해야 색인과 맞는다."""
    if not name:
        return ""
    text = re.sub(r"\(.*?\)", " ", name.lower())
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def lookup(*names):
    """성분명/INCI/CAS 중 하나라도 맞는 부속서 항목을 찾는다."""
    if not is_available():
        return []

    keys = []
    for name in names:
        if not name:
            continue
        for piece in re.split(r"[/;,]| 등 ", str(name)):
            piece = piece.strip()
            if not piece:
                continue
            if CAS_PATTERN.fullmatch(piece):
                keys.append(piece)
            else:
                key = normalize_name(piece)
                if len(key) > 2:
                    keys.append(key)

    if not keys:
        return []

    placeholders = ",".join("?" * len(keys))
    rows = _connect().execute(
        """SELECT s.* FROM eu_name n JOIN eu_substance s ON s.id = n.substance_id
           WHERE n.name_norm IN ({}) GROUP BY s.id
           ORDER BY CASE s.annex WHEN 'II' THEN 0 WHEN 'III' THEN 1 WHEN 'V' THEN 2
                                 WHEN 'VI' THEN 3 ELSE 4 END""".format(placeholders),
        keys,
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 판정
# ---------------------------------------------------------------------------

def _percent(text):
    """'0.5%' / '0,05 %' 에서 숫자만 뽑는다. 없으면 None."""
    if not text:
        return None
    m = PERCENT_PATTERN.search(str(text))
    return float(m.group(1).replace(",", ".")) if m else None


def _limits(text):
    """허용 기준 문장에 들어 있는 모든 농도를 뽑는다."""
    return sorted(float(v.replace(",", ".")) for v in PERCENT_PATTERN.findall(text or ""))


def _is_unused(requested):
    low = str(requested or "").lower()
    return any(word in low for word in UNUSED_WORDS)


def judge(name, inci=None, cas=None, requested=None):
    """성분 한 건의 EU 판정을 만든다.

    돌려주는 값은 화면 표의 한 행과 같은 모양이다.
    실데이터가 없으면 None - 호출하는 쪽이 더미로 돌아가야 한다.
    (DB가 없을 때 "Annex 미등재 = 적합"으로 잘못 단정하지 않기 위함)
    """
    if not is_available():
        return None

    hits = lookup(inci, name, cas)

    if not hits:
        return {
            "status": "ok",
            "limit": "개별 제한 없음 (Annex 미등재)",
            "rule": "Regulation (EC) No 1223/2009",
            "note": "부속서 II~VI 어디에도 없는 성분입니다. 일반 성분으로 사용할 수 있으나 안전성 평가는 별도입니다.",
            "annex": "",
            "ref_no": "",
            "matched_name": "",
        }

    banned = [h for h in hits if ANNEX_KIND.get(h["annex"]) == "ban"]
    limited = [h for h in hits if ANNEX_KIND.get(h["annex"]) == "limit"]
    primary = (limited or banned)[0]

    detail = {
        "annex": primary["annex"],
        "ref_no": primary["ref_no"],
        "matched_name": primary["inci_name"] or primary["chemical_name"] or "",
        "rule": "Annex {} No.{} · Regulation (EC) No 1223/2009".format(
            primary["annex"], primary["ref_no"]),
    }

    # 금지 목록에 있고, 조건부 허용(Annex III 등) 항목이 따로 없으면 사용 불가
    if banned and not limited:
        detail.update({
            "status": "ok" if _is_unused(requested) else "ban",
            "limit": "사용 금지",
            "note": ("성분표에 미사용으로 표기돼 있어 해당 없음. (금지 목록 등재 성분)"
                     if _is_unused(requested)
                     else "Annex II 등재 — EU에서는 화장품에 사용할 수 없습니다."),
            "annex": banned[0]["annex"],
            "ref_no": banned[0]["ref_no"],
            "matched_name": banned[0]["chemical_name"] or "",
            "rule": "Annex II No.{} · Regulation (EC) No 1223/2009".format(banned[0]["ref_no"]),
        })
        return detail

    limit_text = primary["max_concentration"] or ""
    conditions = primary["product_type"] or ""
    allowed = _limits(limit_text)
    asked = _percent(requested)

    detail["limit"] = limit_text or (conditions and "용도 제한 있음") or "조건부 사용 가능"

    extra = []
    if banned:
        extra.append("Annex II에도 등재돼 있어 예외 용도(Annex {} No.{}) 밖에서는 사용할 수 없습니다.".format(
            primary["annex"], primary["ref_no"]))
    if conditions:
        extra.append("적용 범위: {}".format(conditions))

    if _is_unused(requested):
        detail["status"] = "ok"
        extra.insert(0, "성분표에 미사용으로 표기돼 있어 판정 대상이 아닙니다.")
    elif asked is None:
        detail["status"] = "warn"
        extra.insert(0, "성분표에서 함량을 읽지 못했습니다. 담당자 확인이 필요합니다.")
    elif not allowed:
        detail["status"] = "warn"
        extra.insert(0, "허용 기준이 수치가 아니라 조건문으로 적혀 있습니다. 원문을 확인하세요.")
    elif asked > allowed[-1]:
        detail["status"] = "ban"
        extra.insert(0, "요청 {}%는 최대 허용 {}%를 초과합니다.".format(
            _fmt(asked), _fmt(allowed[-1])))
    elif asked > allowed[0]:
        detail["status"] = "warn"
        extra.insert(0, "제품 유형에 따라 기준이 {}~{}%로 갈립니다. 해당 유형 기준을 확인하세요.".format(
            _fmt(allowed[0]), _fmt(allowed[-1])))
    else:
        detail["status"] = "ok"
        extra.insert(0, "요청 {}%는 허용 기준 {}% 이내입니다.".format(
            _fmt(asked), _fmt(allowed[0])))

    if primary["wording"]:
        extra.append("라벨 문구: {}".format(primary["wording"]))

    detail["note"] = " ".join(extra)
    return detail


def _fmt(value):
    """0.5 -> '0.5', 25.0 -> '25'"""
    return ("%g" % value)
