# -*- coding: utf-8 -*-
"""성분 관심도 트렌드 - 실시간 데이터 수집·조회.

출처: Wikimedia Pageviews API (키 불필요, 일 단위 갱신)
  https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/...

Wikipedia 문서 조회수를 '성분에 대한 소비자 관심도' 대리 지표로 쓴다.
판매량이 아니라 관심도라는 점, 성분명이 다의어면 왜곡될 수 있다는 점을 화면에 명시한다.

레이트리밋이 빡빡해서(연속 10여 건이면 429) 디스크에 캐시하고,
한 번 요청에 소수만 새로 받아온다. 미리 채워 두려면:

    python trend_store.py          # 캐시 워밍업 (전부 수집)
    python trend_store.py --force  # TTL 무시하고 다시 수집
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "trenddata")
CACHE_PATH = os.path.join(CACHE_DIR, "pageviews.json")

API = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
       "{project}/all-access/all-agents/{article}/daily/{start}/{end}")
PROJECT = "en.wikipedia"
USER_AGENT = "todo-trade-trends/1.0 (cosmetics trade dashboard; educational prototype)"

TTL_HOURS = 12          # 조회수는 하루 단위로 갱신되므로 12시간이면 충분하다
WINDOW_DAYS = 30        # 받아올 기간
MAX_FETCH_PER_CALL = 3  # 화면 로딩이 느려지지 않게 한 번에 새로 받는 개수를 제한
FETCH_DELAY = 1.2       # 초 - 레이트리밋 회피

# 추적 성분. article 은 영문 위키 문서명.
# 다의어라 왜곡이 큰 항목(Peptide 등)은 일부러 뺐다.
INGREDIENTS = [
    {"key": "niacinamide", "name": "나이아신아마이드", "inci": "Niacinamide",
     "article": "Niacinamide", "category": "브라이트닝"},
    {"key": "retinol", "name": "레티놀", "inci": "Retinol",
     "article": "Retinol", "category": "안티에이징"},
    {"key": "hyaluronic", "name": "히알루론산", "inci": "Sodium Hyaluronate",
     "article": "Hyaluronic_acid", "category": "보습"},
    {"key": "salicylic", "name": "살리실릭애씨드", "inci": "Salicylic Acid",
     "article": "Salicylic_acid", "category": "각질·트러블"},
    {"key": "azelaic", "name": "아젤라익애씨드", "inci": "Azelaic Acid",
     "article": "Azelaic_acid", "category": "각질·트러블"},
    {"key": "ceramide", "name": "세라마이드", "inci": "Ceramide NP",
     "article": "Ceramide", "category": "장벽"},
    {"key": "bakuchiol", "name": "바쿠치올", "inci": "Bakuchiol",
     "article": "Bakuchiol", "category": "안티에이징"},
    {"key": "panthenol", "name": "판테놀", "inci": "Panthenol",
     "article": "Panthenol", "category": "진정"},
    {"key": "arbutin", "name": "알부틴", "inci": "Arbutin",
     "article": "Arbutin", "category": "브라이트닝"},
    {"key": "tranexamic", "name": "트라넥사믹애씨드", "inci": "Tranexamic Acid",
     "article": "Tranexamic_acid", "category": "브라이트닝"},
    {"key": "squalane", "name": "스쿠알란", "inci": "Squalane",
     "article": "Squalane", "category": "보습"},
    {"key": "centella", "name": "센텔라아시아티카", "inci": "Centella Asiatica Extract",
     "article": "Centella_asiatica", "category": "진정"},
]

SOURCE = {
    "name": "Wikimedia Pageviews API",
    "url": "https://wikimedia.org/api/rest_v1/",
    "project": PROJECT,
    "note": "영문 위키백과 문서 조회수 (판매량이 아니라 관심도 대리 지표)",
}


# ---------------------------------------------------------------------------
# 캐시
# ---------------------------------------------------------------------------

def _load_cache():
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_cache(cache):
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, CACHE_PATH)


def _is_stale(entry, ttl_hours=TTL_HOURS):
    if not entry or not entry.get("fetched_at"):
        return True
    try:
        fetched = datetime.fromisoformat(entry["fetched_at"])
    except ValueError:
        return True
    return datetime.now(timezone.utc) - fetched > timedelta(hours=ttl_hours)


# ---------------------------------------------------------------------------
# 수집
# ---------------------------------------------------------------------------

def _fetch_article(article, window_days=WINDOW_DAYS):
    """한 성분의 일별 조회수를 받아온다. 실패하면 예외를 그대로 올린다."""
    end = date.today() - timedelta(days=1)     # 오늘 데이터는 아직 안 쌓인다
    start = end - timedelta(days=window_days - 1)
    url = API.format(
        project=PROJECT,
        article=urllib.parse.quote(article, safe=""),
        start=start.strftime("%Y%m%d"),
        end=end.strftime("%Y%m%d"),
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=25) as res:
        payload = json.loads(res.read().decode("utf-8"))

    series = [{"date": item["timestamp"][:8], "views": item["views"]}
              for item in payload.get("items", [])]
    return {
        "series": series,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def refresh(force=False, limit=MAX_FETCH_PER_CALL, verbose=False):
    """오래된 항목만 골라 새로 받아온다. (성공 건수, 실패 건수)"""
    cache = _load_cache()
    stale = [i for i in INGREDIENTS
             if force or _is_stale(cache.get(i["key"]))]
    if limit:
        stale = stale[:limit]

    done = failed = 0
    for idx, ing in enumerate(stale):
        try:
            cache[ing["key"]] = _fetch_article(ing["article"])
            done += 1
            if verbose:
                print("  OK   {:<18} {}일치".format(ing["name"], len(cache[ing["key"]]["series"])))
        except urllib.error.HTTPError as exc:
            failed += 1
            if verbose:
                print("  FAIL {:<18} HTTP {}".format(ing["name"], exc.code))
            if exc.code == 429:
                break   # 레이트리밋이면 더 두드리지 않는다
        except Exception as exc:                      # noqa: BLE001
            failed += 1
            if verbose:
                print("  FAIL {:<18} {}".format(ing["name"], str(exc)[:40]))

        if idx < len(stale) - 1:
            time.sleep(FETCH_DELAY)

    if done:
        _save_cache(cache)
    return done, failed


# ---------------------------------------------------------------------------
# 조회
# ---------------------------------------------------------------------------

def _summarize(series):
    """최근 7일 vs 직전 7일 평균으로 증감률을 낸다."""
    views = [row["views"] for row in series]
    if len(views) < 14:
        return None

    recent = views[-7:]
    previous = views[-14:-7]
    recent_avg = sum(recent) / 7
    prev_avg = sum(previous) / 7
    growth = ((recent_avg - prev_avg) / prev_avg * 100) if prev_avg else 0.0

    spark = views[-14:]
    return {
        "recent_avg": recent_avg,
        "prev_avg": prev_avg,
        "growth": growth,
        "spark": spark,
        "spark_points": _spark_points(spark),
        "peak": max(views),
        "from": series[0]["date"],
        "to": series[-1]["date"],
    }


def _spark_points(values, width=96, height=26):
    """스파크라인용 SVG polyline 좌표 문자열."""
    if len(values) < 2:
        return ""
    low, high = min(values), max(values)
    span = (high - low) or 1
    step = width / (len(values) - 1)
    return " ".join(
        "{:.1f},{:.1f}".format(i * step, height - (v - low) / span * height)
        for i, v in enumerate(values)
    )


def _eu_status(inci):
    """EU 규제 상태 한 줄 요약. 규제 DB가 없으면 None."""
    try:
        import reg_store
    except ImportError:
        return None
    if not reg_store.is_available():
        return None

    hits = reg_store.lookup(inci)
    if not hits:
        return {"level": "ok", "label": "제한 없음", "detail": "Annex II~VI 미등재"}

    banned = [h for h in hits if h["annex"] == "II"]
    limited = [h for h in hits if h["annex"] in ("III", "IV", "V", "VI")]
    if banned and not limited:
        return {"level": "ban", "label": "사용 금지",
                "detail": "Annex II No.{}".format(banned[0]["ref_no"])}
    if limited:
        row = limited[0]
        return {"level": "warn", "label": "조건부 사용",
                "detail": "Annex {} No.{}{}".format(
                    row["annex"], row["ref_no"],
                    " · " + row["max_concentration"] if row["max_concentration"] else "")}
    return {"level": "ok", "label": "제한 없음", "detail": ""}


def get_ingredient_trends(auto_refresh=True, force=False):
    """성분별 관심도 트렌드. 캐시가 없는 항목은 status='pending' 으로 돌려준다."""
    if auto_refresh:
        refresh(force=force)

    cache = _load_cache()
    rows, collected, missing = [], 0, 0

    for ing in INGREDIENTS:
        entry = cache.get(ing["key"])
        summary = _summarize(entry["series"]) if entry and entry.get("series") else None

        row = dict(ing)
        row["eu"] = _eu_status(ing["inci"])
        if summary:
            row.update(summary)
            row["status"] = "stale" if _is_stale(entry) else "live"
            row["fetched_at"] = entry["fetched_at"][:10]
            collected += 1
        else:
            row.update({"recent_avg": 0, "prev_avg": 0, "growth": 0.0, "spark": [],
                        "status": "pending", "fetched_at": ""})
            missing += 1
        rows.append(row)

    ranked = sorted([r for r in rows if r["status"] != "pending"],
                    key=lambda r: r["recent_avg"], reverse=True)
    for i, row in enumerate(ranked, start=1):
        row["rank"] = i
    for row in rows:
        row.setdefault("rank", 0)

    rows.sort(key=lambda r: (r["rank"] == 0, r["rank"]))

    live = [r for r in rows if r["status"] != "pending"]

    return {
        "rows": rows,
        "collected": collected,
        "missing": missing,
        "total": len(rows),
        "source": dict(SOURCE),
        "window_days": WINDOW_DAYS,
        "updated_at": max((r["fetched_at"] for r in rows if r["fetched_at"]), default=""),
        "rising": sorted(live, key=lambda r: r["growth"], reverse=True)[:3],
        "falling": sorted(live, key=lambda r: r["growth"])[:3],
        "categories": _by_category(live),
        "regulated": [r for r in live if r["eu"] and r["eu"]["level"] != "ok"],
    }


def _by_category(rows):
    """카테고리별 관심도 집계 - 어느 기능군이 뜨고 지는지 본다."""
    buckets = {}
    for row in rows:
        bucket = buckets.setdefault(row["category"], {
            "category": row["category"], "count": 0, "volume": 0.0,
            "growth_sum": 0.0, "top": None,
        })
        bucket["count"] += 1
        bucket["volume"] += row["recent_avg"]
        bucket["growth_sum"] += row["growth"]
        if bucket["top"] is None or row["recent_avg"] > bucket["top"]["recent_avg"]:
            bucket["top"] = row

    result = []
    for bucket in buckets.values():
        bucket["growth"] = bucket["growth_sum"] / bucket["count"]
        bucket["top_name"] = bucket["top"]["name"] if bucket["top"] else ""
        del bucket["growth_sum"], bucket["top"]
        result.append(bucket)

    result.sort(key=lambda b: b["volume"], reverse=True)
    peak = max((b["volume"] for b in result), default=1) or 1
    for bucket in result:
        bucket["ratio"] = bucket["volume"] / peak * 100
    return result


def get_ingredient(key):
    """성분 하나의 정의를 찾는다."""
    for ing in INGREDIENTS:
        if ing["key"] == key:
            return dict(ing)
    return None


if __name__ == "__main__":
    force = "--force" in sys.argv
    print("성분 관심도 캐시 워밍업 ({}종, 출처: {})".format(len(INGREDIENTS), SOURCE["name"]))

    # 레이트리밋에 걸리면 점점 길게 쉬면서 남은 것만 다시 받는다
    for attempt in range(8):
        ok, fail = refresh(force=force and attempt == 0, limit=3, verbose=True)
        if ok == 0 and fail == 0:
            break                      # 더 받을 게 없다
        if fail and attempt < 7:
            wait = min(15 * (attempt + 1), 60)
            print("  … 레이트리밋 대기 {}초".format(wait))
            time.sleep(wait)
        elif attempt < 7:
            time.sleep(3)

    data = get_ingredient_trends(auto_refresh=False)
    print("\n수집 {}/{}건 · 캐시: {}".format(data["collected"], data["total"], CACHE_PATH))
    for row in data["rows"]:
        if row["status"] == "pending":
            print("  {:<18} (미수집)".format(row["name"]))
        else:
            print("  {:>2}. {:<18} 일평균 {:>6,.0f}  {:+6.1f}%".format(
                row["rank"], row["name"], row["recent_avg"], row["growth"]))
