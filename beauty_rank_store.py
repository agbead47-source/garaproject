# -*- coding: utf-8 -*-
"""화장품 랭킹·소식 - 수집·조회.

"지금 미국에서 뭐가 팔리나"를 보는 자리다. 성분 관심도(15번)가 검색·조회수라면
이건 **실제로 팔리는 물건의 순위**다. ODM 영업이 바이어에게 "이런 게 올라오고
있습니다" 라고 말할 때 쓰는 숫자다.

출처 두 갈래:

  1) 아마존 베스트셀러 (Beauty & Personal Care / Skin Care / Makeup / Hair Care)
     - robots.txt 는 이 경로를 막지 않는다 (확인함)
     - 다만 **아마존 이용약관은 자동 수집을 제한한다.** 공식 경로는
       Product Advertising API 다. 그래서 이 수집기는 **기본이 꺼져 있고**,
       `.env` 에서 담당자가 직접 켜야 돈다 (AMAZON_RANK_ENABLED=1)
     - 켜더라도 하루 1회, 카테고리 사이 3초를 쉰다. 값은 순위·제목·ASIN 만 담는다

  2) 화장품 매거진 RSS (업계 소식)
     - 공개 RSS 라 그대로 읽는다. 하루 1회

지켜야 할 것:
  - 화면을 열 때마다 외부를 두드리지 않는다. 받아 둔 값을 같이 본다
  - 차단되면 우회하지 않는다. 막혔다고 화면에 적는다 (FDA 때와 같은 규칙)
  - 순위 변동은 **우리가 받아 둔 어제 자료와 비교한 값**이다. 아마존이 주는 값이 아니다
  - 브랜드·키워드는 제목에서 뽑은 **추정값**이다. 그렇게 표시한다

    python beauty_rank_store.py            # 받을 때가 된 것만
    python beauty_rank_store.py --force    # 주기 무시
    python beauty_rank_store.py --status   # 받아 둔 상태만
"""

import html as html_mod
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from collections import Counter
from datetime import datetime, timedelta, timezone

import app_env

try:
    from zoneinfo import ZoneInfo
    SEOUL = ZoneInfo("Asia/Seoul")
except Exception:                                    # noqa: BLE001
    SEOUL = timezone.utc

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "beauty_rank.db")

_local = threading.local()

USER_AGENT = ("todo-trade-beautyrank/1.0 "
              "(cosmetics market research; educational prototype)")

EVERY_HOURS = 20          # 하루 1회
FETCH_DELAY = 3.0         # 카테고리 사이 쉬는 시간(초)
KEEP_DAYS = 45            # 순위 스냅샷 보관 기간

AMAZON_BASE = "https://www.amazon.com"

# 아마존 베스트셀러 카테고리. 화장품과 직접 관련된 것만.
AMAZON_CATEGORIES = [
    {"key": "beauty", "label": "뷰티 전체", "label_en": "Beauty & Personal Care",
     "path": "/gp/bestsellers/beauty/"},
    {"key": "skincare", "label": "스킨케어", "label_en": "Skin Care",
     "path": "/gp/bestsellers/beauty/11060451/"},
    {"key": "makeup", "label": "메이크업", "label_en": "Makeup",
     "path": "/gp/bestsellers/beauty/11058281/"},
    {"key": "haircare", "label": "헤어케어", "label_en": "Hair Care",
     "path": "/gp/bestsellers/beauty/11057241/"},
]
CATEGORY_MAP = {row["key"]: row for row in AMAZON_CATEGORIES}

# 화장품 매거진 RSS. 실제로 열리는 것만 남겼다.
#   (Cosmetics Design 410 Gone · Happi 403 · Beauty Packaging 403 - 빼 뒀다)
MAGAZINES = [
    {"key": "gcn", "label": "Global Cosmetics News", "region": "🌐 글로벌",
     "url": "https://www.globalcosmeticsnews.com/feed/"},
    {"key": "cosbiz", "label": "Cosmetics Business", "region": "🇬🇧 영국",
     "url": "https://www.cosmeticsbusiness.com/rss"},
    {"key": "jangup", "label": "장업신문", "region": "🇰🇷 국내",
     "url": "http://www.jangup.com/rss/allArticle.xml"},
]
MAGAZINE_MAP = {row["key"]: row for row in MAGAZINES}

# 상위권 제목에서 세어 보는 낱말.
#   ODM 영업이 "요즘 뭘 내세우나"를 볼 때 쓰는 각도다.
KEYWORDS = [
    {"key": "retinol", "label": "레티놀", "words": ["retinol", "retinal"]},
    {"key": "niacinamide", "label": "나이아신아마이드", "words": ["niacinamide"]},
    {"key": "vitaminc", "label": "비타민C", "words": ["vitamin c", "ascorbic"]},
    {"key": "hyaluronic", "label": "히알루론산", "words": ["hyaluronic", "hyaluron"]},
    {"key": "ceramide", "label": "세라마이드", "words": ["ceramide"]},
    {"key": "peptide", "label": "펩타이드", "words": ["peptide"]},
    {"key": "salicylic", "label": "살리실릭", "words": ["salicylic", "bha"]},
    {"key": "collagen", "label": "콜라겐", "words": ["collagen"]},
    {"key": "spf", "label": "자외선차단", "words": ["spf", "sunscreen", "sun screen"]},
    {"key": "fragrance_free", "label": "무향", "words": ["fragrance free", "fragrance-free",
                                                       "unscented"]},
    {"key": "serum", "label": "세럼", "words": ["serum"]},
    {"key": "cleanser", "label": "클렌저", "words": ["cleanser", "cleansing", "face wash"]},
    {"key": "mask", "label": "마스크·패치", "words": ["mask", "patch"]},
    {"key": "moisturizer", "label": "모이스처라이저", "words": ["moisturizer",
                                                            "moisturizing", "lotion"]},
]

# K-뷰티 브랜드. 제목에 이 이름이 들어가면 한국 브랜드로 센다(추정).
K_BRANDS = [
    "medicube", "cosrx", "beauty of joseon", "anua", "tirtir", "laneige", "innisfree",
    "some by mi", "mixsoon", "round lab", "torriden", "skin1004", "dr.jart", "dr jart",
    "isntree", "purito", "biodance", "goodal", "haruharu", "abib", "numbuzin",
    "sulwhasoo", "etude", "banila co", "missha", "klairs", "mediheal", "peripera",
    "rom&nd", "romand", "amuse", "vt cosmetics", "d'alba", "dalba", "kahi", "ma:nyo",
    "manyo", "nacific", "pyunkang yul", "iunik", "axis-y", "beplain", "jumiso",
]

STATUS_META = {
    "ok": {"label": "정상", "css": "ok"},
    "off": {"label": "꺼 둠", "css": "none"},
    "stale": {"label": "업데이트 지연", "css": "warn"},
    "blocked": {"label": "수집 차단됨", "css": "missing"},
    "error": {"label": "수집 실패", "css": "missing"},
    "empty": {"label": "아직 수집 안 됨", "css": "none"},
}

MOVE_META = {
    "new": {"label": "NEW", "css": "up"},
    "up": {"label": "▲", "css": "up"},
    "down": {"label": "▼", "css": "down"},
    "same": {"label": "—", "css": "flat"},
    "unknown": {"label": "", "css": "flat"},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS ranks (
    category    TEXT NOT NULL,
    captured_on TEXT NOT NULL,   -- 우리가 받아 온 날 (YYYY-MM-DD)
    rank        INTEGER NOT NULL,
    asin        TEXT,
    title       TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (category, captured_on, rank)
);

CREATE TABLE IF NOT EXISTS articles (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source     TEXT NOT NULL,
    title      TEXT NOT NULL,
    url        TEXT NOT NULL UNIQUE,
    published  TEXT,
    summary    TEXT,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    key      TEXT PRIMARY KEY,
    last_try TEXT,
    last_ok  TEXT,
    status   TEXT,
    message  TEXT
);

CREATE INDEX IF NOT EXISTS idx_ranks_day ON ranks(category, captured_on);
CREATE INDEX IF NOT EXISTS idx_articles_src ON articles(source, published);
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


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()


def amazon_enabled():
    """아마존 수집은 담당자가 켜야 돈다.

    robots.txt 는 막지 않지만 이용약관이 자동 수집을 제한한다.
    켤지 말지는 회사가 정할 일이라 기본을 꺼 둔다.
    """
    return app_env.get("AMAZON_RANK_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


def get_source(key):
    conn = connect()
    row = conn.execute("SELECT * FROM sources WHERE key = ?", (key,)).fetchone()
    return dict(row) if row else {"key": key, "last_try": "", "last_ok": "",
                                  "status": "empty", "message": ""}


def _save_source(key, **fields):
    row = get_source(key)
    row.update(fields)
    conn = connect()
    conn.execute(
        """INSERT INTO sources (key, last_try, last_ok, status, message)
           VALUES (?,?,?,?,?)
           ON CONFLICT(key) DO UPDATE SET last_try=excluded.last_try,
             last_ok=excluded.last_ok, status=excluded.status,
             message=excluded.message""",
        (key, row["last_try"], row["last_ok"], row["status"], row["message"]))
    conn.commit()
    return row


def _hours_since(stamp):
    try:
        moment = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=SEOUL)
    except (TypeError, ValueError):
        return None
    return (now_seoul() - moment).total_seconds() / 3600


def _clean(text, limit=300):
    text = html_mod.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _get(url, timeout=40):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as res:
        # 한글 매거진이 EUC-KR 인 경우가 있어 바이트로 받아 직접 푼다
        return res.read()


def _decode(raw):
    for enc in ("utf-8", "euc-kr", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# 아마존 베스트셀러
# ---------------------------------------------------------------------------

def _robots_ok(path):
    """받아 오기 전에 robots.txt 를 확인한다. 막혀 있으면 두드리지 않는다."""
    parser = urllib.robotparser.RobotFileParser()
    try:
        raw = _get(AMAZON_BASE + "/robots.txt", timeout=20)
        parser.parse(_decode(raw).splitlines())
    except Exception:                                 # noqa: BLE001
        return False, "robots.txt 를 읽지 못했습니다"

    if not parser.can_fetch("*", AMAZON_BASE + path):
        return False, "robots.txt 가 {} 수집을 막고 있습니다".format(path)
    return True, ""


_BLOCK_WORDS = ("captcha", "enter the characters", "robot check",
                "type the characters you see")


def parse_bestsellers(html):
    """순위 · 제목 · ASIN 만 뽑는다.

    클래스 이름이 난독화돼 있어 `gridItemRoot` 덩어리로 자른 뒤
    순위 뱃지와 이미지 alt(제품명)를 집는다.
    """
    rows = []
    for chunk in re.split(r'<div id="gridItemRoot"', html)[1:]:
        rank = re.search(r'class="zg-bdg-text">#(\d+)</span>', chunk)
        title = re.search(r'<img[^>]+alt="([^"]{5,400})"', chunk)
        if not (rank and title):
            continue
        asin = re.search(r"/dp/([A-Z0-9]{10})", chunk)
        rows.append({
            "rank": int(rank.group(1)),
            "title": _clean(title.group(1), 300),
            "asin": asin.group(1) if asin else "",
        })
    rows.sort(key=lambda r: r["rank"])
    return rows


def collect_amazon(force=False, verbose=False):
    """카테고리 네 곳의 오늘 순위를 받아 둔다."""
    if not amazon_enabled():
        _save_source("amazon", status="off",
                     message="꺼져 있습니다. 아마존 이용약관을 확인하고 "
                             ".env 에 AMAZON_RANK_ENABLED=1 을 넣으면 켜집니다.")
        return {"skipped": True, "reason": "꺼져 있음", "rows": 0}

    source = get_source("amazon")
    age = _hours_since(source["last_ok"])
    if not force and age is not None and age < EVERY_HOURS:
        return {"skipped": True, "reason": "{:.1f}시간 전에 받았습니다".format(age),
                "rows": 0}

    ok, why = _robots_ok(AMAZON_CATEGORIES[0]["path"])
    if not ok:
        # 막아 놨으면 우회하지 않는다
        _save_source("amazon", last_try=now_iso(), status="blocked", message=why)
        if verbose:
            print("  아마존:", why)
        return {"skipped": True, "reason": why, "rows": 0}

    _save_source("amazon", last_try=now_iso())
    conn = connect()
    day = today_iso()
    stamp = now_iso()
    saved, failed = 0, []

    for idx, cat in enumerate(AMAZON_CATEGORIES):
        try:
            html = _decode(_get(AMAZON_BASE + cat["path"]))
        except Exception as exc:                      # noqa: BLE001
            failed.append("{} ({})".format(cat["label"], str(exc)[:40]))
            if verbose:
                print("  FAIL {:<10} {}".format(cat["key"], str(exc)[:50]))
            continue

        low = html.lower()
        if any(word in low for word in _BLOCK_WORDS):
            _save_source("amazon", status="blocked",
                         message="아마존이 자동 수집을 막았습니다(로봇 확인 화면). "
                                 "우회하지 않고 멈췄습니다.")
            if verbose:
                print("  아마존이 로봇 확인 화면을 띄웠습니다. 멈춥니다.")
            return {"skipped": False, "blocked": True, "rows": saved}

        rows = parse_bestsellers(html)
        if not rows:
            failed.append("{} (항목 0건 — 화면 구조가 바뀌었을 수 있습니다)".format(cat["label"]))
            continue

        for row in rows:
            conn.execute(
                """INSERT INTO ranks (category, captured_on, rank, asin, title, fetched_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(category, captured_on, rank) DO UPDATE SET
                     asin=excluded.asin, title=excluded.title,
                     fetched_at=excluded.fetched_at""",
                (cat["key"], day, row["rank"], row["asin"], row["title"], stamp))
            saved += 1
        conn.commit()

        if verbose:
            print("  OK   {:<10} {}건".format(cat["key"], len(rows)))
        if idx < len(AMAZON_CATEGORIES) - 1:
            time.sleep(FETCH_DELAY)

    _prune()
    if saved:
        _save_source("amazon", status="ok", last_ok=now_iso(),
                     message="{}건 · {} 기준".format(saved, day) +
                             (" · 실패 {}".format("; ".join(failed)) if failed else ""))
    else:
        _save_source("amazon", status="error",
                     message="받지 못했습니다: {}".format("; ".join(failed) or "원인 불명"))
    return {"skipped": False, "rows": saved, "failed": failed}


def _prune():
    """오래된 스냅샷은 버린다. 순위 변동만 보면 되니 한 달 반이면 넉넉하다."""
    limit = (now_seoul() - timedelta(days=KEEP_DAYS)).date().isoformat()
    conn = connect()
    conn.execute("DELETE FROM ranks WHERE captured_on < ?", (limit,))
    conn.commit()


# ---------------------------------------------------------------------------
# 화장품 매거진 RSS
# ---------------------------------------------------------------------------

def _rss_items(text):
    items = []
    for chunk in re.findall(r"<item[\s>].*?</item>", text, re.S):
        def pick(tag):
            m = re.search(r"<{0}[^>]*>(.*?)</{0}>".format(tag), chunk, re.S)
            if not m:
                return ""
            value = m.group(1)
            value = re.sub(r"^\s*<!\[CDATA\[|\]\]>\s*$", "", value.strip(), flags=re.S)
            return value.strip()

        link = pick("link") or pick("guid")
        title = _clean(pick("title"), 250)
        if not (link and title):
            continue
        items.append({
            "title": title,
            "url": _clean(link, 500),
            "published": _clean(pick("pubDate") or pick("dc:date"), 60),
            "summary": _clean(pick("description"), 400),
        })
    return items


def collect_magazines(force=False, verbose=False):
    """업계 매거진 RSS. 공개 피드라 그대로 읽는다."""
    source = get_source("magazine")
    age = _hours_since(source["last_ok"])
    if not force and age is not None and age < EVERY_HOURS:
        return {"skipped": True, "reason": "{:.1f}시간 전에 받았습니다".format(age),
                "new": 0}

    _save_source("magazine", last_try=now_iso())
    conn = connect()
    stamp = now_iso()
    new, failed = 0, []

    for idx, mag in enumerate(MAGAZINES):
        try:
            text = _decode(_get(mag["url"], timeout=30))
        except Exception as exc:                      # noqa: BLE001
            failed.append("{} ({})".format(mag["label"], str(exc)[:40]))
            if verbose:
                print("  FAIL {:<22} {}".format(mag["label"], str(exc)[:45]))
            continue

        rows = _rss_items(text)
        for row in rows:
            cur = conn.execute(
                """INSERT INTO articles (source, title, url, published, summary, fetched_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(url) DO NOTHING""",
                (mag["key"], row["title"], row["url"], row["published"],
                 row["summary"], stamp))
            new += cur.rowcount
        conn.commit()

        if verbose:
            print("  OK   {:<22} {}건".format(mag["label"], len(rows)))
        if idx < len(MAGAZINES) - 1:
            time.sleep(1.0)

    _save_source("magazine",
                 status="ok" if new or not failed else "error",
                 last_ok=now_iso() if not failed or new else source["last_ok"],
                 message="새 글 {}건".format(new) +
                         (" · 실패 {}".format("; ".join(failed)) if failed else ""))
    return {"skipped": False, "new": new, "failed": failed}


def collect(force=False, verbose=False):
    init_db()
    return {
        "amazon": collect_amazon(force=force, verbose=verbose),
        "magazine": collect_magazines(force=force, verbose=verbose),
    }


# ---------------------------------------------------------------------------
# 조회
# ---------------------------------------------------------------------------

def _days(category):
    conn = connect()
    return [r["captured_on"] for r in conn.execute(
        "SELECT DISTINCT captured_on FROM ranks WHERE category = ? "
        "ORDER BY captured_on DESC", (category,))]


def _is_k_brand(title):
    low = title.lower()
    return next((b for b in K_BRANDS if b in low), "")


def _keywords_of(title):
    low = title.lower()
    return [k["key"] for k in KEYWORDS if any(w in low for w in k["words"])]


def rank_board(category="beauty", day=None):
    """한 카테고리의 순위표. 변동은 우리가 받아 둔 이전 스냅샷과 비교한 값이다."""
    init_db()
    cat = CATEGORY_MAP.get(category, AMAZON_CATEGORIES[0])
    days = _days(cat["key"])

    source = get_source("amazon")
    base = {
        "category": cat,
        "categories": AMAZON_CATEGORIES,
        "days": days,
        "day": None,
        "prev_day": None,
        "rows": [],
        "keywords": [],
        "k_brands": 0,
        "status": source["status"] or "empty",
        "status_meta": STATUS_META.get(source["status"] or "empty", STATUS_META["empty"]),
        "message": source["message"],
        "enabled": amazon_enabled(),
        "last_ok": source["last_ok"],
    }
    if not days:
        return base

    day = day if day in days else days[0]
    prev_day = next((d for d in days if d < day), None)

    conn = connect()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM ranks WHERE category = ? AND captured_on = ? ORDER BY rank",
        (cat["key"], day))]
    prev = {}
    if prev_day:
        prev = {r["asin"] or r["title"]: r["rank"] for r in conn.execute(
            "SELECT asin, title, rank FROM ranks WHERE category = ? AND captured_on = ?",
            (cat["key"], prev_day))}

    counter = Counter()
    k_count = 0
    for row in rows:
        key = row["asin"] or row["title"]
        before = prev.get(key)
        if not prev_day:
            move, delta = "unknown", 0
        elif before is None:
            move, delta = "new", 0
        elif before > row["rank"]:
            move, delta = "up", before - row["rank"]
        elif before < row["rank"]:
            move, delta = "down", row["rank"] - before
        else:
            move, delta = "same", 0

        row["move"] = move
        row["move_meta"] = MOVE_META[move]
        row["delta"] = delta
        row["prev_rank"] = before
        row["k_brand"] = _is_k_brand(row["title"])
        row["url"] = ("https://www.amazon.com/dp/{}".format(row["asin"])
                      if row["asin"] else "")
        hits = _keywords_of(row["title"])
        row["keywords"] = hits
        counter.update(hits)
        if row["k_brand"]:
            k_count += 1

    keywords = [dict(k, count=counter[k["key"]])
                for k in KEYWORDS if counter[k["key"]]]
    keywords.sort(key=lambda k: -k["count"])

    base.update({
        "day": day, "prev_day": prev_day, "rows": rows,
        "keywords": keywords, "k_brands": k_count,
    })
    return base


def articles(limit=18, source=None):
    """업계 소식.

    한 매체가 기사를 많이 쏟아내면 화면이 그 매체로 다 덮인다.
    매체별로 최신 몇 건씩 번갈아 섞는다.
    """
    init_db()
    conn = connect()

    if source in MAGAZINE_MAP:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM articles WHERE source = ? ORDER BY id DESC LIMIT ?",
            (source, limit))]
    else:
        per_source = {}
        for mag in MAGAZINES:
            per_source[mag["key"]] = [dict(r) for r in conn.execute(
                "SELECT * FROM articles WHERE source = ? ORDER BY id DESC LIMIT ?",
                (mag["key"], limit))]

        rows, idx = [], 0
        while len(rows) < limit:
            added = False
            for mag in MAGAZINES:
                bucket = per_source.get(mag["key"], [])
                if idx < len(bucket) and len(rows) < limit:
                    rows.append(bucket[idx])
                    added = True
            if not added:
                break
            idx += 1

    for row in rows:
        row["meta"] = MAGAZINE_MAP.get(row["source"], {"label": row["source"],
                                                       "region": ""})
    return rows


def status_summary():
    init_db()
    amazon = get_source("amazon")
    magazine = get_source("magazine")
    conn = connect()
    return {
        "amazon": dict(amazon,
                       meta=STATUS_META.get(amazon["status"] or "empty",
                                            STATUS_META["empty"]),
                       enabled=amazon_enabled(),
                       days=len(_days("beauty"))),
        "magazine": dict(magazine,
                         meta=STATUS_META.get(magazine["status"] or "empty",
                                              STATUS_META["empty"]),
                         total=conn.execute(
                             "SELECT COUNT(*) FROM articles").fetchone()[0]),
        "magazine_list": ["{} {}".format(m["region"], m["label"]) for m in MAGAZINES],
        "every": "하루 1회",
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _force_utf8_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


if __name__ == "__main__":
    _force_utf8_console()
    init_db()

    if "--status" in sys.argv:
        info = status_summary()
        print("아마존   ", info["amazon"]["meta"]["label"],
              "· 켜짐" if info["amazon"]["enabled"] else "· 꺼짐",
              "· 마지막", info["amazon"]["last_ok"] or "없음")
        print("        ", info["amazon"]["message"][:90])
        print("매거진   ", info["magazine"]["meta"]["label"],
              "· 기사", info["magazine"]["total"], "건")
        sys.exit()

    force = "--force" in sys.argv
    print("화장품 랭킹·소식 수집")
    if not amazon_enabled():
        print("  ※ 아마존 수집은 꺼져 있습니다 (.env 의 AMAZON_RANK_ENABLED)")
    result = collect(force=force, verbose=True)

    for key in ("amazon", "magazine"):
        part = result[key]
        if part.get("skipped"):
            print("  {} 건너뜀 - {}".format(key, part.get("reason", "")))

    board = rank_board("beauty")
    if board["rows"]:
        print("\n{} · {} 기준 상위 10".format(board["category"]["label"], board["day"]))
        for row in board["rows"][:10]:
            mark = row["move_meta"]["label"]
            if row["move"] in ("up", "down"):
                mark += str(row["delta"])
            print("  #{:<3}{:>5}  {}{}".format(
                row["rank"], mark,
                "🇰🇷 " if row["k_brand"] else "", row["title"][:64]))
        if board["keywords"]:
            print("\n  상위 {}개에서 자주 나온 낱말:".format(len(board["rows"])))
            print("   ", " · ".join("{} {}건".format(k["label"], k["count"])
                                    for k in board["keywords"][:8]))
        print("  한국 브랜드로 보이는 것: {}건".format(board["k_brands"]))

    rows = articles(5)
    if rows:
        print("\n업계 소식 최근 5건")
        for row in rows:
            print("  [{}] {}".format(row["meta"]["label"], row["title"][:70]))
