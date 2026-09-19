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
    {"key": "retinol", "label": "레티놀", "en": "Retinol",
     "words": ["retinol", "retinal"]},
    {"key": "niacinamide", "label": "나이아신아마이드", "en": "Niacinamide",
     "words": ["niacinamide"]},
    {"key": "vitaminc", "label": "비타민C", "en": "Vitamin C",
     "words": ["vitamin c", "ascorbic"]},
    {"key": "hyaluronic", "label": "히알루론산", "en": "Hyaluronic acid",
     "words": ["hyaluronic", "hyaluron"]},
    {"key": "ceramide", "label": "세라마이드", "en": "Ceramide",
     "words": ["ceramide"]},
    {"key": "peptide", "label": "펩타이드", "en": "Peptide",
     "words": ["peptide"]},
    {"key": "salicylic", "label": "살리실릭", "en": "Salicylic acid / BHA",
     "words": ["salicylic", "bha"]},
    {"key": "collagen", "label": "콜라겐", "en": "Collagen",
     "words": ["collagen"]},
    {"key": "spf", "label": "자외선차단", "en": "Sun protection",
     "words": ["spf", "sunscreen", "sun screen"]},
    {"key": "fragrance_free", "label": "무향", "en": "Fragrance-free",
     "words": ["fragrance free", "fragrance-free", "unscented"]},
    {"key": "serum", "label": "세럼", "en": "Serum",
     "words": ["serum"]},
    {"key": "cleanser", "label": "클렌저", "en": "Cleanser",
     "words": ["cleanser", "cleansing", "face wash"]},
    {"key": "mask", "label": "마스크·패치", "en": "Mask / patch",
     "words": ["mask", "patch"]},
    {"key": "moisturizer", "label": "모이스처라이저", "en": "Moisturiser",
     "words": ["moisturizer", "moisturizing", "lotion"]},
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
# AI 분석 (데모)
# ---------------------------------------------------------------------------
#   LLM 이 아니다. 규칙 기반이고 화면에 그렇게 적는다.
#   대신 **말을 지어내지 않는다.** 이 프로젝트가 이미 들고 있는 네 가지 자료를
#   맞대 보고, 근거를 한 줄씩 같이 적는다.
#
#     아마존 순위     - 신규 진입 · 급상승 · 한국 브랜드 비중 · 제목 낱말
#     성분 관심도     - 위키백과 조회수 (15번)
#     EU 규제        - 법령 실데이터 (13번)
#     매거진 소식     - RSS 제목 (28번)
#
#   TODO: 실제 연동 (LLM 요약). 붙이더라도 근거 줄은 그대로 달아야 한다.

# 낱말 -> 규제·관심도에서 찾을 INCI 이름
_KEYWORD_INCI = {
    "retinol": "Retinol",
    "niacinamide": "Niacinamide",
    "salicylic": "Salicylic Acid",
    "hyaluronic": "Sodium Hyaluronate",
    "ceramide": "Ceramide NP",
}

BRIEF_KIND = "규칙 기반 데모"


def _josa(word, pair="이/가"):
    """받침에 맞는 조사. "히알루론산 가" 처럼 나오면 읽는 사람이 걸린다."""
    a, b = pair.split("/")
    last = (word or "").strip()[-1:]
    if not last:
        return b
    code = ord(last)
    if 0xAC00 <= code <= 0xD7A3:
        return a if (code - 0xAC00) % 28 else b
    # 영문·숫자는 소리대로 대충 맞춘다 (완벽할 필요는 없다)
    return b if last.lower() in "aeiouy0123456789" else a


def _trend_growth(inci):
    """성분 관심도(15번)에서 그 성분의 최근 증감률. 없으면 None."""
    try:
        import trend_store
        data = trend_store.get_ingredient_trends(auto_refresh=False)
    except Exception:                                 # noqa: BLE001
        return None
    for row in data.get("rows", []):
        if row.get("status") == "pending":
            continue
        if row.get("inci", "").lower() == (inci or "").lower():
            return row
    return None


def _eu_limit(inci):
    """EU 규제(13번)에서 한 줄. 실데이터가 없으면 None."""
    try:
        import reg_store
        return reg_store.judge(inci, inci=inci)
    except Exception:                                 # noqa: BLE001
        return None


def _news_keywords(rows, top=4):
    """매거진 제목에 자주 나온 낱말."""
    counter = Counter()
    for row in rows:
        low = (row.get("title") or "").lower()
        for kw in KEYWORDS:
            if any(w in low for w in kw["words"]):
                counter[kw["key"]] += 1
    out = []
    for key, count in counter.most_common(top):
        label = next((k["label"] for k in KEYWORDS if k["key"] == key), key)
        out.append({"key": key, "label": label, "count": count})
    return out


def brief(category="beauty"):
    """순위 한 장을 읽고 시사점을 뽑는다. (규칙 기반 데모)

    값이 없으면 없다고 적는다. 비교할 어제가 없으면 변동 이야기를 만들지 않는다.
    """
    board = rank_board(category)
    rows = board["rows"]
    kind = {"kind": BRIEF_KIND, "category": board["category"]}

    if not rows:
        return dict(kind, ready=False, headline="아직 읽을 순위가 없습니다.",
                    findings=[], english="", basis=[])

    findings = []
    basis = ["아마존 {} 상위 {}개 ({} 수집)".format(
        board["category"]["label"], len(rows), board["day"])]

    # 1) 순위 변동 - 비교할 날이 있을 때만
    if board["prev_day"]:
        fresh = [r for r in rows if r["move"] == "new"]
        risers = sorted([r for r in rows if r["move"] == "up"],
                        key=lambda r: -r["delta"])[:3]
        fallers = sorted([r for r in rows if r["move"] == "down"],
                         key=lambda r: -r["delta"])[:2]

        lines = []
        if fresh:
            lines.append("신규 진입 {}개: {}".format(
                len(fresh), " / ".join(r["title"][:42] for r in fresh[:3])))
        if risers:
            lines.append("가장 많이 오른 것: " + " / ".join(
                "{} (▲{})".format(r["title"][:36], r["delta"]) for r in risers))
        if fallers:
            lines.append("많이 내린 것: " + " / ".join(
                "{} (▼{})".format(r["title"][:36], r["delta"]) for r in fallers))

        findings.append({
            "icon": "🔀", "title": "어제와 달라진 것",
            "body": "\n".join(lines) or "순위가 거의 그대로입니다.",
            "source": "{} → {} 스냅샷 비교".format(board["prev_day"], board["day"]),
        })
        basis.append("{} 스냅샷과 비교".format(board["prev_day"]))
    else:
        findings.append({
            "icon": "🔀", "title": "어제와 달라진 것",
            "body": "비교할 이전 수집이 없어 변동을 말할 수 없습니다. "
                    "내일 한 번 더 받으면 순위 변동이 나옵니다.",
            "source": "스냅샷 1회",
        })

    # 2) 한국 브랜드
    k_rows = [r for r in rows if r["k_brand"]]
    if k_rows:
        findings.append({
            "icon": "🇰🇷", "title": "한국 브랜드 {}개가 상위 {}위 안에".format(
                len(k_rows), len(rows)),
            "body": " / ".join("#{} {}".format(r["rank"], r["title"][:44])
                               for r in k_rows[:4]),
            "source": "제품명에서 찾은 추정값 — 사람이 확인해야 합니다",
        })
    else:
        findings.append({
            "icon": "🇰🇷", "title": "한국 브랜드가 상위 {}위 안에 없습니다".format(len(rows)),
            "body": "이 카테고리는 현지·글로벌 브랜드가 잡고 있습니다. "
                    "진입하려면 가격대나 카테고리를 다시 볼 필요가 있습니다.",
            "source": "제품명에서 찾은 추정값",
        })

    # 3) 자주 나온 낱말 + 성분 관심도 + EU 규제를 맞대 본다
    for kw in board["keywords"][:3]:
        inci = _KEYWORD_INCI.get(kw["key"])
        parts = ["상위 {}개 중 {}개 제품이 제목에 내세웠습니다.".format(
            len(rows), kw["count"])]
        sources = ["아마존 제품명"]

        row = _trend_growth(inci) if inci else None
        if row:
            parts.append("위키백과 관심도는 최근 2주 {}{:.1f}%입니다.".format(
                "+" if row["growth"] > 0 else "", row["growth"]))
            sources.append("성분 관심도(Wikimedia)")
            if row["growth"] > 10 and kw["count"] >= 2:
                parts.append("팔리는 쪽과 찾아보는 쪽이 같이 올라 "
                             "지금 제안하기 좋은 소재입니다.")
            elif row["growth"] < -10 and kw["count"] >= 2:
                parts.append("상위권에는 있지만 관심도는 내려가는 중이라 "
                             "신제품 축으로 밀기엔 이릅니다.")

        judged = _eu_limit(inci) if inci else None
        if judged and judged.get("status") in ("warn", "ban"):
            parts.append("EU 기준: {} ({}).".format(
                judged.get("limit", ""), judged.get("rule", "")))
            parts.append("EU 확장 계획이 있으면 배합 한도를 먼저 확인해야 합니다.")
            sources.append("EU 화장품 규정 실데이터")

        findings.append({
            "icon": "🧪", "title": "{} — 상위권 {}건".format(kw["label"], kw["count"]),
            "body": " ".join(parts),
            "source": " · ".join(sources),
        })

    # 4) 업계 소식에서 겹치는 낱말
    news = articles(24)
    if news:
        news_kw = _news_keywords(news)
        if news_kw:
            overlap = [k for k in news_kw
                       if k["key"] in {x["key"] for x in board["keywords"]}]
            body = "매거진 기사 {}건에서 {} 가 자주 나왔습니다.".format(
                len(news), " · ".join("{}({})".format(k["label"], k["count"])
                                      for k in news_kw))
            if overlap:
                names = " · ".join(k["label"] for k in overlap)
                body += " 이 중 {}{} 아마존 상위권에도 같이 올라 있습니다.".format(
                    names, _josa(names, "은/는"))
            else:
                body += " 다만 아마존 상위권 낱말과 겹치는 것은 없습니다."
        else:
            body = ("매거진 기사 {}건에는 상위권 낱말이 안 보입니다. "
                    "브랜드 소식·행사 기사가 많습니다.".format(len(news)))
        findings.append({
            "icon": "📰", "title": "업계 소식과 겹치는 것",
            "body": body,
            "source": "매거진 RSS {}곳".format(len(MAGAZINES)),
        })
        basis.append("매거진 기사 {}건".format(len(news)))

    # 머리말 한 줄
    head_bits = []
    if board["prev_day"]:
        new_n = sum(1 for r in rows if r["move"] == "new")
        if new_n:
            head_bits.append("신규 진입 {}개".format(new_n))
    if k_rows:
        head_bits.append("한국 브랜드 {}개".format(len(k_rows)))
    if board["keywords"]:
        top_kw = board["keywords"][0]["label"]
        head_bits.append("{}{} 가장 많이 걸림".format(top_kw, _josa(top_kw, "이/가")))

    headline = "{} 상위 {}개 — {}".format(
        board["category"]["label"], len(rows),
        " · ".join(head_bits) if head_bits else "특이 사항 없음")

    return dict(kind, ready=True, headline=headline, findings=findings,
                english=_brief_english(board, k_rows), basis=basis,
                day=board["day"], prev_day=board["prev_day"])


def _brief_english(board, k_rows):
    """바이어에게 그대로 붙일 수 있는 영문 요약.

    미리 적어 둔 문장을 값으로 채운다. 번역기가 아니다.
    """
    rows = board["rows"]
    lines = ["Amazon US - {} Best Sellers, top {} (captured {})".format(
        board["category"]["label_en"], len(rows), board["day"])]
    lines.append("")

    top3 = rows[:3]
    lines.append("Current top 3:")
    for row in top3:
        lines.append("  {}. {}".format(row["rank"], row["title"][:96]))

    if board["prev_day"]:
        fresh = [r for r in rows if r["move"] == "new"]
        risers = sorted([r for r in rows if r["move"] == "up"],
                        key=lambda r: -r["delta"])[:2]
        lines.append("")
        lines.append("Since {}: {} new entries, {} climbers.".format(
            board["prev_day"], len(fresh), len(risers)))
        for row in risers:
            lines.append("  up {} places: {}".format(row["delta"], row["title"][:80]))

    if board["keywords"]:
        lines.append("")
        lines.append("Most repeated claims in the top {}: {}.".format(
            len(rows), ", ".join("{} ({})".format(k.get("en") or k["label"],
                                                  k["count"])
                                 for k in board["keywords"][:4])))

    if k_rows:
        lines.append("")
        lines.append("Korean brands in the ranking: {}.".format(
            ", ".join(sorted({r["k_brand"].title() for r in k_rows}))))

    lines.append("")
    lines.append("Source: Amazon Best Sellers page, collected by us on {}. "
                 "Rank movement is measured against our own previous snapshot, "
                 "not supplied by Amazon.".format(board["day"]))
    return "\n".join(lines)


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
