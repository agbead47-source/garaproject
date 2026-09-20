# -*- coding: utf-8 -*-
"""미국 화장품 규제 - 연방규정집(eCFR) 실데이터.

EU 는 부속서에 성분이 다 적혀 있어 대조가 단순하다. 미국은 다르다.
**미국에는 일반 화장품 성분의 사전 허가 목록이 없다.** 그래서
"목록에 없으니 적합" 이라고 말하면 틀린다. 안전성 입증 책임이 제조사에 있을 뿐이다.

대신 세 가지는 법으로 못 박혀 있다.

  1. 금지·제한 성분   21 CFR 700 Subpart B, 250.250
     수은·비티오놀·염화비닐·클로로포름 등. 목록에 걸리면 못 쓴다
  2. 색소             21 CFR 73 Subpart C (인증 면제) / 74 Subpart C (인증 대상)
     **여기는 EU 와 반대로 포지티브 리스트다.** 등재되지 않은 색소는 쓸 수 없고,
     등재됐어도 용도(눈가·입술·외용)가 갈린다. Part 74 색소는 FDA 배치 인증을
     받은 로트만 쓸 수 있다 — 한국 업체가 자주 놓치는 지점이다
  3. 자외선차단 성분   21 CFR 352 / 700.35
     미국에서 자외선차단제는 화장품이 아니라 **OTC 의약품**이다.
     한국에서 기능성화장품인 것이 미국에서는 drug 으로 갈린다

출처: eCFR API (전자 연방규정집) - 키가 필요 없다
  https://www.ecfr.gov/developers/documentation/api/v1
  `/api/versioner/v1/full/{date}/title-21.xml?part=N`
  (이 엔드포인트는 gzip 압축 응답을 요구한다. Accept-Encoding 을 붙여야 한다)

지켜야 할 것:
  - 화면을 열 때마다 부르지 않는다. 받아 둔 원문을 읽는다
  - **미등재를 적합이라고 말하지 않는다.** 미국은 사전 허가 목록이 없다
  - 판정을 원문 없이 내놓지 않는다. 조문 번호와 원문 발췌를 같이 적는다
  - 연방규정집이 스스로 밝힌 기준일(up_to_date_as_of)과 우리가 받아 온 시각을
    따로 적는다
  - robots.txt 가 막는 경로(/search, /compare, /api/renderer)는 건드리지 않는다

    python us_reg_store.py            # 받아 둘 때가 됐으면 수집
    python us_reg_store.py --force    # 지금 수집
    python us_reg_store.py --status   # 받아 둔 상태만 보기
"""

import gzip
import io
import json
import os
import re
import sqlite3
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    SEOUL = ZoneInfo("Asia/Seoul")
except Exception:                                    # noqa: BLE001
    SEOUL = timezone.utc

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "us_reg.db")

_local = threading.local()

USER_AGENT = ("todo-trade-usreg/1.0 "
              "(cosmetics export compliance; educational prototype)")

ECFR = "https://www.ecfr.gov/api/versioner/v1"
TITLES_URL = ECFR + "/titles.json"

# 연방규정집은 매일 바뀌지 않는다. 하루 한 번만 확인한다.
EVERY_HOURS = 24


# ---------------------------------------------------------------------------
# 받아 올 조문
# ---------------------------------------------------------------------------

PARTS = [
    {"part": "700", "subpart": "B", "kind": "restrict",
     "label": "화장품 금지·제한 성분", "cite": "21 CFR 700"},
    {"part": "250", "subpart": None, "kind": "restrict",
     "label": "특정 의약품 규정 (헥사클로로펜 등)", "cite": "21 CFR 250"},
    {"part": "73", "subpart": "C", "kind": "color_exempt",
     "label": "색소 (인증 면제)", "cite": "21 CFR 73 Subpart C"},
    {"part": "74", "subpart": "C", "kind": "color_certified",
     "label": "색소 (배치 인증 대상)", "cite": "21 CFR 74 Subpart C"},
    {"part": "740", "subpart": None, "kind": "label",
     "label": "경고 문구", "cite": "21 CFR 740"},
]
KIND_LABEL = {
    "restrict": "금지·제한",
    "color_exempt": "색소 (인증 면제)",
    "color_certified": "색소 (배치 인증 대상)",
    "label": "경고 문구",
}

# ---------------------------------------------------------------------------
# 이름 색인
# ---------------------------------------------------------------------------
#   조문 제목에 성분명이 그대로 있는 경우(색소)는 제목에서 뽑는다.
#   금지 조문은 제목이 문장이라("Use of mercury compounds in cosmetics...")
#   성분명을 따로 적어 준다.

RESTRICT_ALIASES = {
    "700.11": ["bithionol", "비티오놀"],
    "700.13": ["mercury", "mercuric", "thimerosal", "thiomersal",
               "phenylmercuric acetate", "phenylmercuric nitrate", "수은"],
    "700.14": ["vinyl chloride", "염화비닐"],
    "700.15": ["tribromsalan", "dibromsalan", "metabromsalan",
               "tetrachlorosalicylanilide", "halogenated salicylanilide"],
    "700.16": ["zirconium", "지르코늄"],
    "700.18": ["chloroform", "클로로포름"],
    "700.19": ["methylene chloride", "dichloromethane", "염화메틸렌"],
    "700.23": ["chlorofluorocarbon", "trichlorofluoromethane",
               "dichlorodifluoromethane", "프레온"],
    "700.27": ["prohibited cattle material", "bovine"],
    "250.250": ["hexachlorophene", "헥사클로로펜"],
}

# CI 번호 → 미국 색소 조문.
#   EU·한국은 CI 번호로 적고 미국은 FD&C / D&C 이름으로 적는다.
#   참고 매핑이다. 판정은 반드시 조문 원문으로 확인해야 한다.
#
#   번호 하나가 조문 둘에 걸리기도 한다 (CI 15850 = D&C Red No. 6 과 No. 7).
#   그래서 값이 목록이다.
#
#   받아 온 조문에 없는 번호를 가리키면 `--status` 가 짚어 준다.
#   (실제로 이 표를 처음 적었을 때 세 군데가 틀려 있었고 그렇게 찾았다)
CI_TO_SECTION = {
    # --- 21 CFR 73 Subpart C : 배치 인증 면제 ---
    "ci 75120": ["73.2030"],              # Annatto
    "ci 75470": ["73.2087"],              # Carmine
    "ci 40800": ["73.2095"], "ci 40820": ["73.2095"],
    "ci 40825": ["73.2095"], "ci 40850": ["73.2095"],   # β-Carotene
    "ci 75810": ["73.2125"],              # Chlorophyllin-copper (치약용)
    "ci 77000": ["73.2645"],              # Aluminum powder
    "ci 77007": ["73.2725"],              # Ultramarines
    "ci 77019": ["73.2496"],              # Mica
    "ci 77163": ["73.2162"],              # Bismuth oxychloride
    "ci 77288": ["73.2327"],              # Chromium oxide greens
    "ci 77289": ["73.2326"],              # Chromium hydroxide green
    "ci 77400": ["73.2646", "73.2647"],   # Bronze / Copper powder
    "ci 77491": ["73.2250"], "ci 77492": ["73.2250"],
    "ci 77499": ["73.2250"],              # Iron oxides
    "ci 77510": ["73.2299"],              # Ferric ferrocyanide
    "ci 77520": ["73.2298"],              # Ferric ammonium ferrocyanide
    "ci 77742": ["73.2775"],              # Manganese violet
    "ci 77820": ["73.2500"],              # Silver
    "ci 77891": ["73.2575"],              # Titanium dioxide
    "ci 77947": ["73.2991"],              # Zinc oxide

    # --- 21 CFR 74 Subpart C : 배치 인증 대상 ---
    "ci 12085": ["74.2336"],              # D&C Red No. 36
    "ci 14700": ["74.2304"],              # FD&C Red No. 4
    "ci 15510": ["74.2254"],              # D&C Orange No. 4
    "ci 15850": ["74.2306", "74.2307"],   # D&C Red No. 6 / No. 7
    "ci 15880": ["74.2334"],              # D&C Red No. 34
    "ci 15985": ["74.2706"],              # FD&C Yellow No. 6
    "ci 16035": ["74.2340"],              # FD&C Red No. 40
    "ci 17200": ["74.2333"],              # D&C Red No. 33
    "ci 19140": ["74.2705"],              # FD&C Yellow No. 5
    "ci 26100": ["74.2317"],              # D&C Red No. 17
    "ci 42053": ["74.2203"],              # FD&C Green No. 3
    "ci 42090": ["74.2101"],              # FD&C Blue No. 1
    "ci 45350": ["74.2707", "74.2708"],   # D&C Yellow No. 7 / No. 8
    "ci 45370": ["74.2255"],              # D&C Orange No. 5
    "ci 45380": ["74.2321", "74.2322"],   # D&C Red No. 21 / No. 22
    "ci 45410": ["74.2327", "74.2328"],   # D&C Red No. 27 / No. 28
    "ci 45425": ["74.2260", "74.2261"],   # D&C Orange No. 10 / No. 11
    "ci 47000": ["74.2711"],              # D&C Yellow No. 11
    "ci 47005": ["74.2710"],              # D&C Yellow No. 10
    "ci 59040": ["74.2208"],              # D&C Green No. 8
    "ci 60725": ["74.2602"],              # D&C Violet No. 2
    "ci 61565": ["74.2206"],              # D&C Green No. 6
    "ci 61570": ["74.2205"],              # D&C Green No. 5
    "ci 73360": ["74.2330"],              # D&C Red No. 30
    "ci 77266": ["74.2052"],              # D&C Black No. 2 (카본블랙)
}

# 화장품용 목록에 일부러 안 넣은 번호.
#   못 찾은 것과 "미국에서는 못 쓴다" 는 전혀 다른 말이다.
CI_NOT_LISTED = {
    "ci 45430": "FD&C Red No. 3 — 1990년에 화장품·외용약 용도가 취소됐습니다.",
    "ci 77480": "Gold — 21 CFR 73 Subpart C(화장품)에 등재돼 있지 않습니다.",
    "ci 16185": "FD&C Red No. 2 (아마란스) — 미국에서 취소된 색소입니다.",
}


# 색소로 보이는 이름. 미국은 색소가 포지티브 리스트라 판정이 반대로 간다.
COLOR_HINT = re.compile(
    r"\b(ci\s?\d{5}|fd&c|d&c|ext\.?\s?d&c|"
    r"(?:red|blue|green|yellow|orange|violet|black|brown)\s+no\.?\s*\d+|"
    r"적색|황색|청색|녹색|등색|흑색|자색)\b", re.I)

# 미국에서 자외선차단제는 OTC 의약품이다. 한국의 기능성화장품과 갈린다.
SUNSCREEN_ACTIVES = [
    "aminobenzoic acid", "avobenzone", "cinoxate", "dioxybenzone",
    "ensulizole", "phenylbenzimidazole sulfonic acid", "homosalate",
    "meradimate", "octinoxate", "ethylhexyl methoxycinnamate",
    "octisalate", "ethylhexyl salicylate", "octocrylene", "oxybenzone",
    "benzophenone-3", "padimate o", "sulisobenzone", "benzophenone-4",
    "titanium dioxide", "zinc oxide", "trolamine salicylate",
    "ensulizole", "octyl methoxycinnamate",
]

# 미국에서 화장품과 의약품의 경계는 성분과 효능 표방으로 갈린다.
#   같은 성분이라도 "각질 관리" 라고 적으면 화장품이고
#   "여드름 치료" 라고 적으면 OTC 의약품이다. 시설 기준부터 달라진다.
DRUG_ACTIVES = [
    {"names": ["hydroquinone", "하이드로퀴논"], "level": "banned",
     "text": "미국에서 하이드로퀴논은 화장품에 쓸 수 없습니다. "
             "OTC 미백 제품은 2020년 CARES Act 로 시장에서 빠졌고 지금은 처방 의약품입니다."},
    {"names": ["minoxidil", "미녹시딜"], "level": "drug",
     "text": "탈모 치료 OTC 의약품 성분입니다 (21 CFR 310.527). 화장품이 아닙니다."},
    {"names": ["salicylic acid", "살리실릭"], "level": "claim",
     "text": "여드름 OTC 모노그래프 성분입니다 (21 CFR 333 Subpart D). "
             "각질 관리로 적으면 화장품이지만 여드름 효능을 표방하면 의약품이 됩니다."},
    {"names": ["benzoyl peroxide", "벤조일퍼옥사이드"], "level": "drug",
     "text": "여드름 OTC 의약품 성분입니다 (21 CFR 333 Subpart D)."},
    {"names": ["resorcinol", "레조르시놀"], "level": "claim",
     "text": "여드름 OTC 모노그래프 성분입니다. 효능을 표방하면 의약품이 됩니다."},
    {"names": ["sodium fluoride", "sodium monofluorophosphate", "불소"], "level": "drug",
     "text": "충치 예방 OTC 의약품 성분입니다 (21 CFR 355)."},
]

# 성분표에 "미사용" 으로 적힌 것은 판정 대상이 아니다 (EU 쪽과 같은 규칙)
UNUSED_WORDS = ("미사용", "free-from", "free from", "미배합", "불검출")

# 안 넣은 성분의 허용 기준 칸
NONE_LIMIT = "해당 없음"
PERCENT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")


SCHEMA = """
CREATE TABLE IF NOT EXISTS sections (
    section    TEXT PRIMARY KEY,      -- 700.13, 74.2101 ...
    part       TEXT NOT NULL,
    kind       TEXT NOT NULL,
    heading    TEXT NOT NULL,
    subject    TEXT NOT NULL DEFAULT '',   -- 제목에서 뽑은 성분·색소 이름
    body       TEXT NOT NULL,
    scope      TEXT NOT NULL DEFAULT '',   -- 색소 용도 범위 (all/external/listed/...)
    scope_text TEXT NOT NULL DEFAULT '',
    cite       TEXT NOT NULL DEFAULT '',
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aliases (
    name    TEXT NOT NULL,            -- 소문자 정규화된 이름
    section TEXT NOT NULL,
    PRIMARY KEY (name, section)
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------

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


def _iso():
    return _now().replace(microsecond=0).isoformat()


def _meta_get(key, default=""):
    row = _conn().execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def _meta_set(key, value):
    conn = _conn()
    conn.execute("INSERT INTO meta (key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (key, str(value)))
    conn.commit()


def is_available():
    """받아 둔 조문이 있는지. 없으면 화면은 더미로 돌아간다."""
    try:
        return bool(_conn().execute(
            "SELECT 1 FROM sections LIMIT 1").fetchone())
    except sqlite3.Error:
        return False


def get_meta():
    if not is_available():
        return None
    return {
        "source": "eCFR (전자 연방규정집) · 21 CFR",
        "source_url": "https://www.ecfr.gov/current/title-21",
        "cfr_date": _meta_get("cfr_date"),          # 연방규정집이 밝힌 기준일
        "amended_on": _meta_get("amended_on"),      # 마지막 개정일
        "fetched_at": _meta_get("fetched_at"),      # 우리가 받아 온 시각
        "section_count": _meta_get("section_count", "0"),
        "parts": ", ".join(p["cite"] for p in PARTS),
    }


# ---------------------------------------------------------------------------
# 수집
# ---------------------------------------------------------------------------

def _get(url, timeout=90):
    """eCFR 은 이 엔드포인트에서 압축 응답을 요구한다."""
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "gzip",
    })
    with urllib.request.urlopen(req, timeout=timeout) as res:
        raw = res.read()
        if res.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    return raw.decode("utf-8", "replace")


def _plain(xml):
    """법령 XML 을 읽을 수 있는 문장으로."""
    text = re.sub(r"<HEAD>.*?</HEAD>", " ", xml, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = (text.replace("&#xA7;", "§").replace("&amp;", "&")
                .replace("&#x2014;", "—").replace("&#x2019;", "'")
                .replace("&lt;", "<").replace("&gt;", ">"))
    text = re.sub(r"&#x([0-9A-Fa-f]+);",
                  lambda m: chr(int(m.group(1), 16)), text)
    return re.sub(r"\s+", " ", text).strip()


def _heading(xml):
    m = re.search(r"<HEAD>(.*?)</HEAD>", xml, re.S)
    return _plain(m.group(1)) if m else ""


def _subject(heading):
    """조문 제목에서 성분·색소 이름만 떼어낸다. (§ 74.2101 FD&C Blue No. 1.)"""
    text = re.sub(r"^\s*§\s*[\d.]+\s*", "", heading).strip()
    return text.rstrip(".").strip()


# 색소 조문이 쓰는 표현. 원문 그대로가 답이고, 이건 요약일 뿐이다.
def _color_scope(body):
    low = body.lower()
    if "area of the eye" in low and "including cosmetics intended for use in the area of the eye" in low:
        return "all", "눈가 포함 화장품 전반"
    if "may not be used for coloring" in low or "shall not be used in" in low:
        return "limited", "용도 제한 있음 (원문 확인 필요)"
    if "externally applied" in low:
        return "external", "외용 화장품만 (눈가 사용 불가)"
    if "for coloring the following cosmetics" in low:
        return "listed", "조문에 열거된 제품에만"
    if "hair on the scalp" in low:
        return "hair", "두피 모발 착색용"
    return "", ""


def _norm(name):
    text = (name or "").strip().lower()
    text = text.replace("＆", "&")
    text = re.sub(r"\s+", " ", text)
    # "CI77891" · "C.I. 77891" 을 "ci 77891" 로 모은다
    text = re.sub(r"\bc\.?\s?i\.?\s*(\d{5})\b", r"ci \1", text)
    return text.strip(" .,;")


def _index(conn, section, names):
    for name in names:
        key = _norm(name)
        if key:
            conn.execute("INSERT OR IGNORE INTO aliases (name, section) "
                         "VALUES (?, ?)", (key, section))


def _cfr_date():
    """연방규정집이 스스로 밝힌 title 21 기준일."""
    data = json.loads(_get(TITLES_URL, timeout=30))
    for row in data.get("titles", []):
        if str(row.get("number")) == "21":
            return row.get("up_to_date_as_of", ""), row.get("latest_amended_on", "")
    return "", ""


def collect(force=False):
    """조문을 받아 둔다. 실패하면 이전 값을 지우지 않는다."""
    conn = _conn()

    if not force and is_available():
        last = _meta_get("fetched_at")
        if last:
            try:
                age = (_now() - datetime.fromisoformat(last)).total_seconds() / 3600
                if age < EVERY_HOURS:
                    return {"ok": True, "skipped": True,
                            "message": "최근에 받아 둔 게 있어 건너뜁니다."}
            except ValueError:
                pass

    try:
        cfr_date, amended = _cfr_date()
    except Exception as exc:                          # noqa: BLE001
        return {"ok": False, "message": "eCFR 기준일을 읽지 못했습니다: {}".format(exc)}
    if not cfr_date:
        return {"ok": False, "message": "eCFR 이 title 21 기준일을 주지 않았습니다."}

    rows = []
    failed = []
    for spec in PARTS:
        url = "{}/full/{}/title-21.xml?part={}".format(ECFR, cfr_date, spec["part"])
        if spec["subpart"]:
            url += "&subpart=" + spec["subpart"]
        try:
            xml = _get(url)
        except Exception as exc:                      # noqa: BLE001
            failed.append("{} ({})".format(spec["cite"], exc))
            continue

        for block in re.split(r"(?=<DIV8 )", xml)[1:]:
            num = re.search(r'N="([^"]+)"', block)
            if not num:
                continue
            heading = _heading(block)
            body = _plain(block)
            scope, scope_text = ("", "")
            if spec["kind"].startswith("color"):
                scope, scope_text = _color_scope(body)
            rows.append({
                "section": num.group(1), "part": spec["part"], "kind": spec["kind"],
                "heading": heading, "subject": _subject(heading), "body": body,
                "scope": scope, "scope_text": scope_text, "cite": spec["cite"],
            })

    if not rows:
        return {"ok": False,
                "message": "조문을 하나도 받지 못했습니다. 이전 값은 그대로 뒀습니다. "
                           + (" / ".join(failed) if failed else "")}

    # 다 받은 뒤에 한 번에 갈아 끼운다. 중간에 실패해도 반쪽짜리가 남지 않는다.
    conn.execute("DELETE FROM sections")
    conn.execute("DELETE FROM aliases")
    stamp = _iso()
    for row in rows:
        conn.execute(
            "INSERT INTO sections (section, part, kind, heading, subject, body, "
            "scope, scope_text, cite, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (row["section"], row["part"], row["kind"], row["heading"],
             row["subject"], row["body"], row["scope"], row["scope_text"],
             row["cite"], stamp))

        names = []
        if row["kind"].startswith("color"):
            # 색소는 제목이 곧 이름이다 ("FD&C Blue No. 1")
            names.append(row["subject"])
            # "D&C Red No. 6" 처럼 조문 하나가 여러 번호를 담기도 한다
            for extra in re.findall(r"(?:FD&C|D&C|Ext\. D&C)\s+\w+\s+No\.\s*\d+",
                                    row["heading"] + " " + row["body"][:400]):
                names.append(extra)
        names += RESTRICT_ALIASES.get(row["section"], [])
        _index(conn, row["section"], names)

    for ci, targets in CI_TO_SECTION.items():
        for section in targets:
            conn.execute("INSERT OR IGNORE INTO aliases (name, section) "
                         "VALUES (?, ?)", (ci, section))

    conn.commit()
    _meta_set("cfr_date", cfr_date)
    _meta_set("amended_on", amended)
    _meta_set("fetched_at", stamp)
    _meta_set("section_count", len(rows))

    return {"ok": True, "skipped": False, "count": len(rows),
            "cfr_date": cfr_date, "failed": failed,
            "message": "조문 {}건을 받았습니다 (기준일 {}).{}".format(
                len(rows), cfr_date,
                " 일부 실패: " + " / ".join(failed) if failed else "")}


# ---------------------------------------------------------------------------
# 조회
# ---------------------------------------------------------------------------

def _section(number):
    row = _conn().execute("SELECT * FROM sections WHERE section = ?",
                          (number,)).fetchone()
    return dict(row) if row else None


# 부분일치에 쓸 최소 길이. 짧은 낱말이 아무 데나 걸리면 엉뚱한 판정이 나온다.
PARTIAL_MIN = 6


def lookup(*names):
    """이름으로 조문을 찾는다.

    두 방향을 다 본다.
      - 성분명이 조문 이름에 들어 있는 경우 ("Red No. 6" ⊂ "D&C Red No. 6 Lake")
      - 조문 이름이 성분명에 들어 있는 경우 ("mercuric" ⊂ "Mercuric Chloride")
    뒤쪽을 빼먹으면 Mercuric Chloride 가 수은 조문에 안 걸린다.
    낱말 경계로 맞춰서 "gold" 가 "goldenrod" 에 걸리는 일은 막는다.
    """
    conn = _conn()
    found = {}

    def _take(rows):
        for row in rows:
            found[row["section"]] = dict(row)

    keys = [k for k in (_norm(n) for n in names) if k and len(k) >= 3]

    # 1) 정확히 같은 이름
    for key in keys:
        _take(conn.execute(
            "SELECT s.* FROM aliases a JOIN sections s ON s.section = a.section "
            "WHERE a.name = ?", (key,)))
    if found:
        return list(found.values())

    # 2) 성분명이 조문 이름 안에 있는가
    for key in keys:
        if len(key) >= PARTIAL_MIN:
            _take(conn.execute(
                "SELECT s.* FROM aliases a JOIN sections s ON s.section = a.section "
                "WHERE a.name LIKE ?", ("%" + key + "%",)))
    if found:
        return list(found.values())

    # 3) 조문 이름이 성분명 안에 있는가 (Mercuric Chloride → mercuric)
    rows = conn.execute(
        "SELECT a.name, s.* FROM aliases a JOIN sections s ON s.section = a.section "
        "WHERE LENGTH(a.name) >= ?", (PARTIAL_MIN,)).fetchall()
    for key in keys:
        for row in rows:
            if re.search(r"(?<![a-z0-9])" + re.escape(row["name"]) + r"(?![a-z0-9])", key):
                found[row["section"]] = dict(row)
    return list(found.values())


def _is_unused(requested):
    text = (requested or "").strip().lower()
    return any(word in text for word in UNUSED_WORDS)


def _percent(text):
    m = PERCENT_RE.search(text or "")
    return float(m.group(1).replace(",", ".")) if m else None


def _excerpt(body, limit=320):
    """판정 근거로 붙일 원문 발췌. 판정만 내놓고 근거를 숨기지 않는다."""
    i = body.lower().find("may be safely used")
    if i < 0:
        i = body.lower().find("(b)")
    if i < 0:
        i = 0
    text = body[i:i + limit].strip()
    return text + ("…" if len(body) - i > limit else "")


def drug_active(name, inci=None):
    """화장품이 아니라 의약품 쪽으로 갈리는 성분인가."""
    text = " ".join(filter(None, [(name or ""), (inci or "")])).lower()
    for row in DRUG_ACTIVES:
        if any(word in text for word in row["names"]):
            return row
    return None


def is_sunscreen_active(name, inci=None):
    text = " ".join(filter(None, [(name or ""), (inci or "")])).lower()
    return any(active in text for active in SUNSCREEN_ACTIVES)


def looks_like_color(name, inci=None):
    text = " ".join(filter(None, [(name or ""), (inci or "")]))
    return bool(COLOR_HINT.search(text))


def judge(name, inci=None, cas=None, requested=None):
    """성분 한 건의 미국 판정.

    돌려주는 모양은 EU 쪽(reg_store.judge)과 같다. 화면에서 같이 쓰기 위해서다.
    받아 둔 조문이 없으면 None - 부르는 쪽이 더미로 돌아가야 한다.
    """
    if not is_available():
        return None

    unused = _is_unused(requested)
    hits = lookup(inci, name, cas)

    restrict = [h for h in hits if h["kind"] == "restrict"]
    colors = [h for h in hits if h["kind"].startswith("color")]

    # 1) 금지·제한 조문이 먼저다
    if restrict:
        row = restrict[0]
        return {
            "status": "ok" if unused else "ban",
            "unused": unused,
            "limit": NONE_LIMIT if unused else "사용 금지·제한",
            "rule": "21 CFR {} · {}".format(row["section"], row["subject"][:60]),
            "note": (("성분표에 미사용으로 표기돼 있어 해당 없음. (금지·제한 조문 등재) "
                      if unused else
                      "21 CFR {} 에 금지·제한으로 등재된 성분입니다. ".format(row["section"]))
                     + "원문: " + _excerpt(row["body"], 220)),
            "annex": row["section"],
            "ref_no": row["section"],
            "matched_name": row["subject"],
            "section": row["section"],
            "kind": row["kind"],
        }

    # 2) 색소는 포지티브 리스트다. EU 와 반대로 "없으면 못 쓴다"
    if colors:
        row = colors[0]
        certified = row["kind"] == "color_certified"
        notes = []
        if row["scope_text"]:
            notes.append("용도 범위: " + row["scope_text"] + ".")
        if certified:
            notes.append("FDA 배치 인증(certification)을 받은 로트만 쓸 수 있습니다. "
                         "원료사에 해당 로트의 인증서를 요청하세요.")
        else:
            notes.append("배치 인증은 면제되는 색소입니다.")
        notes.append("원문: " + _excerpt(row["body"], 240))

        status = "ok"
        if unused:
            status = "ok"
            notes.insert(0, "성분표에 미사용으로 표기돼 있어 판정 대상이 아닙니다.")
        elif row["scope"] in ("external", "listed", "limited", "hair"):
            # 제품 유형에 따라 갈린다. 우리는 제품 유형을 모른다 - 단정하지 않는다
            status = "warn"
            notes.insert(0, "제품 유형에 따라 쓸 수 있는지가 갈립니다. "
                            "이 제품이 조문이 허용한 범위에 드는지 확인하세요.")

        return {
            "status": status,
            "unused": unused,
            "limit": (NONE_LIMIT if unused else
                      (row["scope_text"] or "등재 색소 (용도 조건 있음)")),
            "limit_if_used": row["scope_text"] or "",
            "rule": "21 CFR {} · {}".format(row["section"], row["subject"][:60]),
            "note": " ".join(notes),
            "annex": row["section"],
            "ref_no": row["section"],
            "matched_name": row["subject"],
            "section": row["section"],
            "kind": row["kind"],
        }

    # 3) 화장품용으로 취소·미등재인 걸 이미 아는 번호는 그렇게 말한다.
    #    "못 찾았다" 와 "쓸 수 없다" 는 전혀 다른 말이다.
    for candidate in (inci, name):
        known = not_listed(candidate)
        if known:
            return {
                "status": "ok" if unused else "ban",
                "unused": unused,
                "limit": NONE_LIMIT if unused else "화장품 사용 불가",
                "rule": "21 CFR 73 / 74 Subpart C (미등재)",
                "note": (("성분표에 미사용으로 표기돼 있어 해당 없음. " if unused else "")
                         + known + " 미국은 색소가 포지티브 리스트라 "
                         "등재되지 않은 색소는 화장품에 쓸 수 없습니다."),
                "annex": "", "ref_no": "", "matched_name": "",
                "section": "", "kind": "color_revoked",
            }

    # 4) 색소처럼 보이는데 못 찾았다 - 미국에서는 이게 문제다
    if looks_like_color(name, inci) and not unused:
        return {
            "status": "warn",
            "limit": "색소 등재 확인 필요",
            "rule": "21 CFR 73 / 74 Subpart C",
            "note": ("미국은 색소가 포지티브 리스트입니다. 21 CFR 73·74 에 등재되지 "
                     "않은 색소는 화장품에 쓸 수 없습니다. 받아 둔 조문에서 이 이름을 "
                     "찾지 못했습니다 — 미등재이거나, CI 번호와 미국 명칭(FD&C·D&C)이 "
                     "달라 대조가 안 된 것입니다. 원료사에 미국 명칭과 조문 번호를 "
                     "확인하세요."),
            "annex": "",
            "ref_no": "",
            "matched_name": "",
            "section": "",
            "kind": "color_unknown",
        }

    # 5) 화장품과 의약품의 경계에 걸친 성분
    drug = drug_active(name, inci)
    if drug and not unused:
        return {
            "status": "ban" if drug["level"] == "banned" else "warn",
            "limit": {"banned": "화장품 사용 불가",
                      "drug": "OTC 의약품 성분",
                      "claim": "효능 표방 시 의약품"}[drug["level"]],
            "rule": "21 CFR 310 / 333 / 355 (OTC 의약품)",
            "note": drug["text"],
            "annex": "", "ref_no": "", "matched_name": "",
            "section": "", "kind": "otc",
        }

    # 6) 자외선차단 성분이면 화장품이 아니라 OTC 의약품이다
    if is_sunscreen_active(name, inci) and not unused:
        return {
            "status": "warn",
            "limit": "OTC 의약품 성분",
            "rule": "21 CFR 352 · 21 CFR 700.35",
            "note": ("미국에서 자외선차단제는 화장품이 아니라 OTC 의약품입니다. "
                     "한국에서 기능성화장품인 제품이 미국에서는 drug 으로 갈립니다. "
                     "SPF 를 표시해 팔려면 OTC 모노그래프 성분·함량·라벨(Drug Facts)을 "
                     "따라야 하고, 시설도 의약품 기준을 받습니다. "
                     "SPF 표시를 하지 않는다면 이 판정은 해당하지 않습니다."),
            "annex": "",
            "ref_no": "",
            "matched_name": "",
            "section": "",
            "kind": "otc",
        }

    # 7) 아무 데도 없다. 적합이 아니다.
    return {
        "status": "ok" if unused else "warn",
        "unused": unused,
        "limit": NONE_LIMIT if unused else "개별 금지 규정 없음",
        "rule": "21 CFR 700 / 73 / 74 (미등재)",
        "note": ("미국에는 일반 화장품 성분의 사전 허가 목록이 없습니다. "
                 "금지·제한 조문(21 CFR 700 등)에 걸리지 않는다는 뜻이지 "
                 "'적합 판정' 이 아닙니다. MoCRA 에 따라 안전성 입증 자료를 "
                 "제조사가 갖추고 보관해야 합니다."),
        "annex": "",
        "ref_no": "",
        "matched_name": "",
        "section": "",
        "kind": "none",
    }


# ---------------------------------------------------------------------------
# 제품 단위 - 이 제품이 미국에서 화장품인가 의약품인가
# ---------------------------------------------------------------------------
#   성분 하나씩 보면 놓친다. 자외선차단 성분이 하나라도 들어가고 SPF 를 적으면
#   그 순간 제품 전체가 OTC 의약품이 된다. 시설 기준부터 라벨까지 다 달라진다.
#   영업이 바이어에게 "이건 화장품으로 못 팝니다" 를 먼저 말할 수 있어야 한다.

OTC_LEVELS = {
    "drug": {"label": "OTC 의약품", "css": "drug",
             "desc": "화장품이 아니라 OTC 의약품으로 갈립니다"},
    "claim": {"label": "표방하면 의약품", "css": "claim",
              "desc": "효능을 표방하면 의약품이 됩니다"},
    "banned": {"label": "화장품 사용 불가", "css": "banned",
               "desc": "화장품에 쓸 수 없는 성분이 있습니다"},
    "cosmetic": {"label": "화장품", "css": "cosmetic",
                 "desc": "OTC 로 갈릴 성분이 보이지 않습니다"},
}


def otc_of(name, inci=None, requested=None):
    """성분 하나가 화장품·의약품 경계에 걸리는가. 안 걸리면 None."""
    if _is_unused(requested):
        return None
    drug = drug_active(name, inci)
    if drug:
        return {"level": drug["level"], "why": drug["text"],
                "rule": "21 CFR 310 / 333 / 355"}
    if is_sunscreen_active(name, inci):
        return {
            "level": "claim",
            "why": ("자외선차단 성분입니다. SPF 를 표시해 팔면 화장품이 아니라 "
                    "OTC 의약품(21 CFR 352)이 됩니다. SPF 표시를 안 하면 "
                    "이 판정은 해당하지 않습니다."),
            "rule": "21 CFR 352",
        }
    return None


def otc_verdict(rows):
    """제품 단위 OTC 판정. rows: [{name, inci, requested}, …]"""
    hits = []
    for row in rows or []:
        found = otc_of(row.get("name"), row.get("inci"), row.get("requested"))
        if found:
            hits.append(dict(found,
                             name=row.get("name") or row.get("inci") or ""))

    if any(h["level"] == "banned" for h in hits):
        level = "banned"
    elif any(h["level"] == "drug" for h in hits):
        level = "drug"
    elif hits:
        level = "claim"
    else:
        level = "cosmetic"

    if level == "cosmetic":
        why = ("성분 {}건에서 OTC 로 갈릴 성분이 보이지 않습니다. "
               "다만 효능 문구로도 의약품이 됩니다 — 라벨 문안을 같이 보세요."
               .format(len(rows or [])))
    else:
        # 아래에 성분별로 다시 적으므로 여기서는 세기만 한다
        why = "성분 {}건 중 {}건이 의약품 쪽으로 갈립니다.".format(
            len(rows or []), len(hits))

    return {
        "level": level,
        "level_meta": dict(OTC_LEVELS[level], key=level),
        "hits": hits,
        "why": why,
    }


def sections(kind=None, keyword=""):
    """받아 둔 조문 목록. 화면에서 원문을 훑어볼 때 쓴다."""
    sql = "SELECT * FROM sections"
    args = []
    where = []
    if kind:
        where.append("kind = ?")
        args.append(kind)
    keyword = (keyword or "").strip().lower()
    if keyword:
        where.append("(LOWER(subject) LIKE ? OR LOWER(body) LIKE ? OR section LIKE ?)")
        args += ["%" + keyword + "%"] * 3
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY CAST(part AS INTEGER), section"
    return [dict(r) for r in _conn().execute(sql, args)]


def check_ci_map():
    """CI 매핑이 실제 조문을 가리키는지 본다.

    조문 목록은 법이 바뀌면 바뀐다. 우리 표가 낡으면 조용히 못 찾고 지나가는데,
    그건 "미등재" 와 구분이 안 된다. 그래서 대놓고 짚어 준다.
    """
    have = {r["section"] for r in sections()}
    bad = []
    for ci, targets in sorted(CI_TO_SECTION.items()):
        missing = [t for t in targets if t not in have]
        if missing:
            bad.append((ci, missing))
    return bad


def not_listed(name):
    """화장품용으로 등재돼 있지 않다고 이미 알고 있는 번호인가."""
    return CI_NOT_LISTED.get(_norm(name))


def counts():
    rows = _conn().execute(
        "SELECT kind, COUNT(*) AS n FROM sections GROUP BY kind").fetchall()
    return {r["kind"]: r["n"] for r in rows}


if __name__ == "__main__":
    init_db()
    if "--status" in sys.argv:
        meta = get_meta()
        if not meta:
            print("아직 받아 둔 조문이 없습니다. python us_reg_store.py --force")
        else:
            for key, value in meta.items():
                print("{:14} {}".format(key, value))
            for kind, n in counts().items():
                print("  {:18} {}건".format(KIND_LABEL.get(kind, kind), n))
            bad = check_ci_map()
            if bad:
                print("\nCI 매핑이 가리키는 조문을 찾지 못했습니다 "
                      "(법이 바뀌었거나 표가 낡았습니다):")
                for ci, missing in bad:
                    print("  {:10} -> {}".format(ci, ", ".join(missing)))
            else:
                print("\nCI 매핑 {}개 모두 실제 조문을 가리킵니다.".format(
                    len(CI_TO_SECTION)))
    else:
        out = collect(force="--force" in sys.argv)
        print(out["message"])
