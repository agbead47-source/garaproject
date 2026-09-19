# -*- coding: utf-8 -*-
"""화장품 규제 공지 수집 - 규제 화면 '최신 규제 소식' 피드.

규제 판정(성분별 허용 기준)은 reg_store 가 EU 법령으로 하고,
이 모듈은 그 앞단 - **규제가 바뀐다는 소식을 먼저 알아채는 일**을 맡는다.
성분 기준이 바뀌기 전에 공지가 먼저 뜨기 때문이다.

동작 방식 (업로드받은 regulation_crawler.py 를 그대로 옮겼다)
  1. SOURCES 에 등록한 규제기관 페이지에 접속
  2. 페이지 안의 링크 중 키워드(cosmetic, MoCRA 등)가 든 것만 골라냄
  3. 처음 보는 링크만 '신규'로 표시해 누적 저장

사이트마다 HTML 구조를 분석하지 않아도 되도록 '링크 텍스트 + 키워드' 방식이라
사이트 디자인이 바뀌어도 잘 안 깨진다. 대신 메뉴·네비게이션 링크가 섞여 들어올 수
있어서, 걸러낸 근거(어떤 키워드에 걸렸는지)를 같이 저장해 화면에 보여준다.

설치: pip install requests beautifulsoup4
실행: python regnews_store.py            # 수집
      python regnews_store.py --dry-run  # 저장하지 않고 결과만 출력

화면에서는 규제 화면의 '지금 수집' 버튼으로도 돌릴 수 있다.
"""

import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "newsdata")
STORE_PATH = os.path.join(DATA_DIR, "regulation_news.json")
CSV_PATH = os.path.join(DATA_DIR, "regulation_news.csv")

# ── 1. 수집할 사이트 목록 ─────────────────────────────────────
# URL 은 예시다. 브라우저로 한 번 열어보고 공지 목록이 보이는 페이지로 바꿔 쓰면
# 결과가 훨씬 깨끗해진다. (지금 URL 은 기관 대문이라 메뉴 링크가 섞인다)
SOURCES = [
    {
        "key": "fda",
        "region": "미국",
        "flag": "🇺🇸",
        "agency": "FDA",
        "url": "https://www.fda.gov/cosmetics",
        "keywords": ["cosmetic", "mocra", "fragrance allergen", "gmp", "registration"],
    },
    {
        "key": "eu",
        "region": "EU",
        "flag": "🇪🇺",
        "agency": "European Commission",
        "url": "https://single-market-economy.ec.europa.eu/sectors/cosmetics_en",
        "keywords": ["cosmetic", "regulation", "annex", "cmr", "omnibus"],
    },
    {
        "key": "bpom",
        "region": "인도네시아",
        "flag": "🇮🇩",
        "agency": "BPOM",
        "url": "https://www.pom.go.id",
        "keywords": ["kosmetik", "cosmetic", "halal"],
    },
    {
        # 국문 사이트라 키워드도 국문이어야 한다. 제목이 영문 기관보다 짧아
        # 최소 길이도 낮춰 잡는다 ('화장품법 개정' = 7자).
        "key": "mfds",
        "region": "한국",
        "flag": "🇰🇷",
        "agency": "식약처 (MFDS)",
        "url": "https://www.mfds.go.kr/brd/m_99/list.do",
        "keywords": ["화장품", "기능성", "원료", "고시", "개정", "안전기준",
                     "입법예고", "행정예고"],
        "min_title": 6,
        "note": "주소 확인 필요 — 브라우저로 열어 공지 목록이 보이는 게시판인지 확인하세요",
    },
]
SOURCE_MAP = {row["key"]: row for row in SOURCES}

HEADERS = {"User-Agent": "Mozilla/5.0 (To-do team student project; trade dashboard)"}
DELAY_SECONDS = 3        # 사이트 사이 대기 시간 (서버 부담 줄이기)
TIMEOUT = 15
MIN_TITLE_LEN = 10       # '더보기' 같은 짧은 메뉴 링크 제외 (사이트별로 덮어쓸 수 있다)
MAX_PER_SOURCE = 40      # 대문 페이지는 링크가 많아 상한을 둔다
MAX_KEEP = 300           # 저장소에 쌓아 둘 최대 건수


def now_iso():
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


# ── 2. robots.txt 확인: 수집이 허용된 페이지인지 체크 ─────────────
def is_allowed(url):
    parsed = urlparse(url)
    robots_url = "{}://{}/robots.txt".format(parsed.scheme, parsed.netloc)
    rp = RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(HEADERS["User-Agent"], url)
    except Exception:                                    # noqa: BLE001
        return True   # robots.txt 를 못 읽으면 일단 진행


# ── 3. 한 사이트에서 키워드 링크 뽑기 ─────────────────────────
def crawl_source(source):
    """한 기관 페이지에서 키워드가 든 링크를 모은다. (항목들, 실패 사유)"""
    url = source["url"]
    if not is_allowed(url):
        return [], "robots.txt 에서 수집을 허용하지 않습니다"

    try:
        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        res.raise_for_status()
    except requests.Timeout:
        return [], "{}초 안에 응답이 없습니다".format(TIMEOUT)
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        return [], "HTTP {} 응답 (주소가 바뀌었는지 확인하세요)".format(code)
    except requests.ConnectionError:
        # 사내망·방화벽·프록시에서 막히면 여기로 온다
        return [], "접속할 수 없습니다 (네트워크 차단 여부를 확인하세요)"
    except requests.RequestException as e:
        return [], "수집 실패: {}".format(str(e)[:120])

    # res.text 가 아니라 바이트를 넘긴다.
    # 응답 헤더에 charset 이 없으면 requests 는 ISO-8859-1 로 읽어 버려서
    # 국문 사이트(식약처 등) 제목이 깨지고 키워드가 하나도 안 걸린다.
    soup = BeautifulSoup(res.content, "html.parser")
    results, seen_links = [], set()
    min_title = source.get("min_title", MIN_TITLE_LEN)

    for a in soup.find_all("a", href=True):
        title = " ".join(a.get_text().split())       # 공백 정리
        if len(title) < min_title:
            continue

        lowered = title.lower()
        hit = next((k for k in source["keywords"] if k in lowered), None)
        if hit is None:
            continue

        link = urljoin(url, a["href"])               # 상대경로 → 전체 주소
        if link in seen_links:
            continue
        seen_links.add(link)

        results.append({
            "key": source["key"],
            "region": source["region"],
            "flag": source["flag"],
            "agency": source["agency"],
            "title": title,
            "link": link,
            "keyword": hit,                          # 어떤 키워드에 걸렸는지
        })
        if len(results) >= MAX_PER_SOURCE:
            break

    return results, None


# ── 4. 저장소: 처음 보는 링크만 새로 쌓는다 ──────────────────────
def _load():
    try:
        with open(STORE_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"items": [], "runs": []}
    data.setdefault("items", [])
    data.setdefault("runs", [])
    return data


def _save(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = STORE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STORE_PATH)
    _export_csv(data["items"])


def _export_csv(items):
    """엑셀에서 열어볼 수 있게 CSV 로도 떨어뜨린다. (utf-8-sig: 한글 안 깨짐)"""
    with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["수집일", "지역", "기관", "제목", "링크"])
        writer.writeheader()
        writer.writerows([{
            "수집일": it["first_seen"][:10],
            "지역": it["region"],
            "기관": it["agency"],
            "제목": it["title"],
            "링크": it["link"],
        } for it in items])


def collect(keys=None, verbose=False):
    """등록된 사이트를 돌며 수집한다. 반환값은 이번 수집 요약."""
    data = _load()
    known = {it["link"] for it in data["items"]}
    stamp = now_iso()

    targets = [s for s in SOURCES if not keys or s["key"] in keys]
    fresh, failures, checked = [], [], 0

    for idx, source in enumerate(targets):
        items, error = crawl_source(source)
        if error:
            failures.append({"agency": source["agency"], "region": source["region"],
                             "error": error})
            if verbose:
                print("[실패] {}: {}".format(source["agency"], error))
        else:
            checked += len(items)
            for item in items:
                if item["link"] in known:
                    continue
                known.add(item["link"])
                item["first_seen"] = stamp
                fresh.append(item)
            if verbose:
                print("[완료] {}: {}건 (신규 {}건)".format(
                    source["agency"], len(items),
                    sum(1 for i in fresh if i["key"] == source["key"])))

        if idx < len(targets) - 1:
            time.sleep(DELAY_SECONDS)

    run = {
        "at": stamp,
        "new": len(fresh),
        "checked": checked,
        "failures": failures,
        "sources": [s["key"] for s in targets],
    }
    # 최신 항목이 앞에 오게 쌓고, 너무 불어나지 않게 자른다
    data["items"] = (fresh + data["items"])[:MAX_KEEP]
    data["runs"] = ([run] + data["runs"])[:20]
    _save(data)
    return run


def get_news(limit=12, region="all"):
    """화면에 뿌릴 규제 소식. 수집한 적이 없으면 rows 가 빈 채로 돌아온다."""
    data = _load()
    last_run = data["runs"][0] if data["runs"] else None
    new_links = set()
    if last_run:
        new_links = {it["link"] for it in data["items"]
                     if it.get("first_seen") == last_run["at"]}

    rows = data["items"]
    if region != "all":
        rows = [it for it in rows if it["key"] == region]

    return {
        "rows": [dict(it, is_new=it["link"] in new_links) for it in rows[:limit]],
        "total": len(data["items"]),
        "last_run": last_run,
        "collected": bool(data["items"]),
        "sources": [{"key": s["key"], "region": s["region"], "flag": s["flag"],
                     "agency": s["agency"], "url": s["url"], "note": s.get("note", "")}
                    for s in SOURCES],
        "store_path": os.path.relpath(STORE_PATH, BASE_DIR),
        "csv_path": os.path.relpath(CSV_PATH, BASE_DIR),
    }


# ── 5. 실행 ─────────────────────────────────────────────
if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    print("규제 공지 수집 ({}곳)".format(len(SOURCES)))

    if dry:
        for src in SOURCES:
            items, error = crawl_source(src)
            print("[{}] {}".format(src["agency"], error or "{}건".format(len(items))))
            for it in items[:5]:
                print("   - {}".format(it["title"][:80]))
            time.sleep(DELAY_SECONDS)
        sys.exit(0)

    run = collect(verbose=True)
    print("\n신규 {}건 · 확인 {}건 → {}".format(run["new"], run["checked"], STORE_PATH))
    for fail in run["failures"]:
        print("  실패 · {} — {}".format(fail["agency"], fail["error"]))

    data = get_news(limit=10)
    for row in data["rows"]:
        print("  {} [{}] {}".format("NEW" if row["is_new"] else "   ",
                                    row["region"], row["title"][:70]))
