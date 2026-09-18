# -*- coding: utf-8 -*-
"""EU 화장품 규제(Regulation (EC) No 1223/2009) 실데이터 수집 스크립트.

API 키가 필요 없는 EU 공식 엔드포인트 두 곳만 사용한다.

  1) EU Publications Office SPARQL - 최신 통합본(consolidated) CELEX 번호를 찾는다
  2) EU Cellar (publications.europa.eu/resource/celex/...) - 통합본 전문(XHTML)을 받는다

받은 전문에서 Annex II(사용 금지), III(사용 제한), IV(색소), V(방부제), VI(자외선 차단제)
표를 뽑아 SQLite(regdata/regulation.db)에 적재한다.

실행:
    python regdata/sync_eu.py            # 캐시가 있으면 재사용
    python regdata/sync_eu.py --refresh  # 통합본을 다시 내려받는다

규제는 초 단위로 바뀌지 않으므로 화면에서 매번 호출하지 않고,
이 스크립트를 주기적으로(주 1회 정도) 돌려 DB를 갱신하는 방식이다.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
DB_PATH = os.path.join(BASE_DIR, "regulation.db")

SPARQL_URL = "http://publications.europa.eu/webapi/rdf/sparql"
CELLAR_URL = "http://publications.europa.eu/resource/celex/{celex}"

# 기본 법령: 화장품 규정 (EC) No 1223/2009
BASE_CELEX = "32009R1223"
CONSOLIDATED_PREFIX = "02009R1223-"

USER_AGENT = "todo-trade-regdata/1.0 (cosmetics regulation sync)"
TIMEOUT = 180

# 부속서별 열 구성 (EUR-Lex 통합본 표 기준)
ANNEX_COLUMNS = {
    "II": ["ref_no", "chemical_name", "cas", "ec"],
    "III": ["ref_no", "chemical_name", "inci_name", "cas", "ec",
            "product_type", "max_concentration", "other", "wording"],
    "IV": ["ref_no", "chemical_name", "inci_name", "cas", "ec", "colour",
           "product_type", "max_concentration", "other", "wording"],
    "V": ["ref_no", "chemical_name", "inci_name", "cas", "ec",
          "product_type", "max_concentration", "other", "wording"],
    "VI": ["ref_no", "chemical_name", "inci_name", "cas", "ec",
           "product_type", "max_concentration", "other", "wording"],
}

ANNEX_LABELS = {
    "II": "사용 금지 물질",
    "III": "사용 제한 물질",
    "IV": "허용 색소",
    "V": "허용 방부제",
    "VI": "허용 자외선 차단성분",
}

ANNEX_ORDER = ["ANNEX I", "ANNEX II", "ANNEX III", "ANNEX IV",
               "ANNEX V", "ANNEX VI", "ANNEX VII"]

# 통합본에만 붙는 개정 표시 기호 (▼M32, ►M5, ◄ 등)
AMENDMENT_MARK = re.compile("[▼►◄─]+\\s*[MCB]?\\d*")

NBSP = " "


# ---------------------------------------------------------------------------
# 1) 수집
# ---------------------------------------------------------------------------

def _get(url, accept, params=None):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Accept": accept,
        "Accept-Language": "eng",
        "User-Agent": USER_AGENT,
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        return res.read().decode("utf-8", errors="replace")


def find_latest_celex():
    """SPARQL로 가장 최신 통합본 CELEX 번호를 찾는다. (예: 02009R1223-20260518)"""
    query = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT ?celex WHERE {
  ?w cdm:resource_legal_id_celex ?celex .
  FILTER(STRSTARTS(STR(?celex), "%s"))
} ORDER BY DESC(?celex) LIMIT 1
""" % CONSOLIDATED_PREFIX

    body = _get(SPARQL_URL, "application/sparql-results+json", {
        "query": query,
        "format": "application/sparql-results+json",
    })
    rows = json.loads(body).get("results", {}).get("bindings", [])
    if not rows:
        # 통합본을 못 찾으면 원본 법령으로 넘어간다
        print("  ! 통합본을 찾지 못해 원본 법령을 사용합니다.")
        return BASE_CELEX
    return rows[0]["celex"]["value"]


def fetch_document(celex, refresh=False):
    """Cellar에서 법령 전문(XHTML)을 받아 캐시에 저장하고 경로를 돌려준다."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, celex + ".html")

    if os.path.exists(path) and not refresh:
        print("  캐시 사용: {} ({:,} bytes)".format(path, os.path.getsize(path)))
        return path

    url = CELLAR_URL.format(celex=celex)
    print("  내려받는 중: {}".format(url))
    html = _get(url, "application/xhtml+xml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print("  저장: {} ({:,} bytes)".format(path, os.path.getsize(path)))
    return path


# ---------------------------------------------------------------------------
# 2) 파싱
# ---------------------------------------------------------------------------

class TableRowParser(HTMLParser):
    """표의 행/셀 텍스트만 뽑아내는 최소 파서 (외부 라이브러리 없이 동작).

    EUR-Lex 표는 한 셀 안에서 이름 하나를 <p> 하나로 적는다.
    그래서 <p>/<br> 경계를 줄바꿈으로 남겨야 "메틸파라벤, 에틸파라벤, ..."처럼
    여러 이름이 들어간 셀을 이름 단위로 나눌 수 있다.
    """

    SPLIT_TAGS = ("p", "br", "li", "div")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self._row = []
        self._cell = []
        self._in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._in_cell = True
            self._cell = []
        elif tag in self.SPLIT_TAGS and self._in_cell:
            self._cell.append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag in self.SPLIT_TAGS and self._in_cell:
            self._cell.append("\n")

    def handle_endtag(self, tag):
        if tag == "tr":
            if self._row:
                self.rows.append(self._row)
            self._row = []
        elif tag in ("td", "th") and self._in_cell:
            self._row.append(tidy("".join(self._cell)))
            self._in_cell = False
        elif tag in self.SPLIT_TAGS and self._in_cell:
            self._cell.append("\n")

    def handle_data(self, data):
        if self._in_cell:
            self._cell.append(data)


def tidy(text):
    """줄 단위 공백만 정리하고 줄바꿈(이름 구분자)은 살려 둔다."""
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def clean(text):
    """개정 표시 기호와 군더더기 공백을 없앤다."""
    text = AMENDMENT_MARK.sub(" ", text).replace(NBSP, " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip(" -") for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def flatten(text):
    """DB에 넣어 화면에 보여줄 한 줄 텍스트."""
    return re.sub(r"\s+", " ", text or "").strip()


def split_annexes(html):
    """부속서 제목 위치로 본문을 잘라 {부속서: 구간 HTML} 로 돌려준다."""
    found = {}
    for m in re.finditer(r">\s*(ANNEX [IVX]+)\s*<", html):
        found.setdefault(m.group(1), m.start())

    segments = {}
    for i, name in enumerate(ANNEX_ORDER[:-1]):
        if name not in found:
            continue
        start = found[name]
        end = len(html)
        for later in ANNEX_ORDER[i + 1:]:
            if later in found and found[later] > start:
                end = found[later]
                break
        segments[name.replace("ANNEX ", "")] = html[start:end]
    return segments


def is_header_row(cells):
    """표 머리글 / 열 기호(a b c d) 행이면 True."""
    if all(re.fullmatch(r"[a-z]", (c or "").strip()) for c in cells):
        return True
    first = (cells[0] or "").lower()
    return first in ("reference number", "chemical name/inn", "chemical name",
                     "chemical name/inn/xan", "substance identification")


def parse_annex(segment, annex):
    """한 부속서 구간에서 성분 행을 뽑아낸다."""
    columns = ANNEX_COLUMNS[annex]
    parser = TableRowParser()
    parser.feed(segment)

    records = []
    for raw in parser.rows:
        if len(raw) != len(columns):
            continue  # 머리글 병합행·삭제 표시행 등은 열 수가 다르다
        cells = [clean(c) for c in raw]
        if is_header_row(cells):
            continue
        if not any(cells):
            continue

        row = dict(zip(columns, cells))
        # 참조번호와 물질명이 모두 비면 의미 있는 행이 아니다
        if not row.get("ref_no") and not row.get("chemical_name"):
            continue
        row["annex"] = annex
        records.append(row)

    return records


# ---------------------------------------------------------------------------
# 3) 적재
# ---------------------------------------------------------------------------

SCHEMA = """
DROP TABLE IF EXISTS meta;
DROP TABLE IF EXISTS eu_substance;
DROP TABLE IF EXISTS eu_name;

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE eu_substance (
    id                INTEGER PRIMARY KEY,
    annex             TEXT NOT NULL,
    annex_label       TEXT NOT NULL,
    ref_no            TEXT,
    chemical_name     TEXT,
    inci_name         TEXT,
    cas               TEXT,
    ec                TEXT,
    colour            TEXT,
    product_type      TEXT,
    max_concentration TEXT,
    other             TEXT,
    wording           TEXT
);

CREATE TABLE eu_name (
    name_norm    TEXT NOT NULL,
    kind         TEXT NOT NULL,
    substance_id INTEGER NOT NULL REFERENCES eu_substance(id)
);

CREATE INDEX idx_eu_name_norm ON eu_name(name_norm);
CREATE INDEX idx_eu_substance_annex ON eu_substance(annex);
"""

CAS_PATTERN = re.compile(r"\d{2,7}-\d{2}-\d")


def normalize_name(name):
    """이름 대조용 정규화: 소문자 + 기호 제거 + 공백 정리."""
    if not name:
        return ""
    text = re.sub(r"\(.*?\)", " ", name.lower())   # 괄호 주석 제거
    text = re.sub(r"[^a-z0-9]+", " ", text)        # 기호를 공백으로
    return re.sub(r"\s+", " ", text).strip()


def split_names(cell):
    """한 셀에 여러 이름이 들어있는 경우를 나눈다.

    EUR-Lex 표는 이름 하나를 <p> 하나로 적으므로 줄바꿈이 1차 구분자다.
    쉼표로는 나누지 않는다 ("1,4-Dihydroxybenzene" 같은 이름이 깨지기 때문).
    """
    if not cell:
        return []

    names = []
    for line in cell.split("\n"):
        for piece in re.split(r"[;/]| and its | and ", line):
            piece = piece.strip(" .,")
            if not piece:
                continue
            names.append(piece)
            # "1,4-Dihydroxybenzene (Hydroquinone)" 처럼 괄호 안에 통용명이 들어간 경우
            for alias in re.findall(r"\(([^()]{3,60})\)", piece):
                names.append(alias.strip())
    return names


def build_database(records, celex, source_url):
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)

    version_date = celex.split("-")[-1] if "-" in celex else ""
    if len(version_date) == 8:
        version_date = "{}-{}-{}".format(version_date[:4], version_date[4:6], version_date[6:])

    con.executemany(
        "INSERT INTO meta (key, value) VALUES (?, ?)",
        [
            ("source", "EU Regulation (EC) No 1223/2009"),
            ("celex", celex),
            ("version_date", version_date),
            ("source_url", source_url),
            ("fetched_at", datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")),
            ("substance_count", str(len(records))),
        ],
    )

    names = []
    for i, row in enumerate(records, start=1):
        con.execute(
            """INSERT INTO eu_substance
               (id, annex, annex_label, ref_no, chemical_name, inci_name, cas, ec,
                colour, product_type, max_concentration, other, wording)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                i, row["annex"], ANNEX_LABELS[row["annex"]], flatten(row.get("ref_no")),
                flatten(row.get("chemical_name")), flatten(row.get("inci_name")),
                flatten(row.get("cas")), flatten(row.get("ec")), flatten(row.get("colour")),
                flatten(row.get("product_type")), flatten(row.get("max_concentration")),
                flatten(row.get("other")), flatten(row.get("wording")),
            ),
        )

        seen = set()
        for kind, cell in (("inci", row.get("inci_name")), ("chemical", row.get("chemical_name"))):
            for piece in split_names(cell):
                key = normalize_name(piece)
                if key and len(key) > 2 and (key, kind) not in seen:
                    seen.add((key, kind))
                    names.append((key, kind, i))

        for piece in split_names(row.get("cas")):
            for cas in CAS_PATTERN.findall(piece):
                if (cas, "cas") not in seen:
                    seen.add((cas, "cas"))
                    names.append((cas, "cas", i))

    con.executemany("INSERT INTO eu_name (name_norm, kind, substance_id) VALUES (?,?,?)", names)
    con.commit()
    con.close()
    return len(names), version_date


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="EU 화장품 규제 실데이터 수집")
    ap.add_argument("--refresh", action="store_true", help="캐시를 무시하고 다시 내려받는다")
    ap.add_argument("--celex", help="특정 통합본 CELEX 번호를 직접 지정")
    args = ap.parse_args()

    print("[1/4] 최신 통합본 확인")
    celex = args.celex or find_latest_celex()
    print("  CELEX: {}".format(celex))

    print("[2/4] 법령 전문 수집")
    path = fetch_document(celex, refresh=args.refresh)
    with open(path, encoding="utf-8", errors="replace") as f:
        html = f.read()

    print("[3/4] 부속서 파싱")
    segments = split_annexes(html)
    records = []
    for annex in ANNEX_COLUMNS:
        if annex not in segments:
            print("  - Annex {}: 구간을 찾지 못함".format(annex))
            continue
        rows = parse_annex(segments[annex], annex)
        print("  - Annex {:<4} {:<14} {:>5}건".format(annex, ANNEX_LABELS[annex], len(rows)))
        records.extend(rows)

    if not records:
        print("파싱 결과가 비어 있습니다. 문서 구조가 바뀌었는지 확인하세요.")
        return 1

    print("[4/4] SQLite 적재")
    name_count, version_date = build_database(records, celex, CELLAR_URL.format(celex=celex))
    print("  {} -> 성분 {:,}건 / 검색용 이름 {:,}건 (기준일 {})".format(
        DB_PATH, len(records), name_count, version_date or "-"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
