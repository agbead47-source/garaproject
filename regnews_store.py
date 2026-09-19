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
import re
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
# 2026-09-19 에 실제로 열어 보고 맞춘 주소다. 기관 대문이 아니라 '공지 목록'
# 페이지여야 메뉴 링크가 안 섞인다.
#
#   list_selector : 목록이 들어 있는 영역. 이 안의 링크만 본다.
#                   비워 두면 페이지 전체를 훑는다(메뉴가 섞일 수 있다).
#   min_title     : 제목 최소 길이. 국문은 제목이 짧아 낮춰 잡는다.
#   enabled       : False 면 수집하지 않는다.
SOURCES = [
    {
        # 식약처 공지는 식품·의약품·의료기기가 섞여 있어서 키워드가 특히 중요하다.
        "key": "mfds_notice",
        "region": "한국",
        "flag": "🇰🇷",
        "agency": "식약처 · 입법/행정예고",
        "url": "https://www.mfds.go.kr/brd/m_209/list.do",
        "list_selector": "div.bbs_list01",
        # '기능성'·'원료' 만으로는 건강기능식품 공지가 딸려 온다(실측).
        # '화장품' 하나면 기능성화장품·맞춤형화장품·화장품법이 전부 걸린다.
        "keywords": ["화장품"],
        "min_title": 6,
        "note": "규제가 바뀌기 전 예고 단계 — 가장 먼저 뜨는 신호",
    },
    {
        "key": "mfds_rule",
        "region": "한국",
        "flag": "🇰🇷",
        "agency": "식약처 · 제·개정 고시",
        "url": "https://www.mfds.go.kr/brd/m_207/list.do",
        "list_selector": "div.bbs_list01",
        "keywords": ["화장품"],
        "min_title": 6,
        "note": "확정된 고시 개정",
    },
    {
        # 식약처가 해외 규제 개정을 국문으로 정리해 주는 게시판.
        # 해외영업 입장에서는 원문을 직접 읽는 것보다 이게 빠르다.
        "key": "mfds_global",
        "region": "해외 (식약처 정리)",
        "flag": "🌏",
        "agency": "식약처 · 해외 규정 개정 소식",
        "url": "https://www.mfds.go.kr/brd/m_1147/list.do",
        "list_selector": "div.bbs_list01",
        "keywords": ["화장품"],
        "min_title": 6,
        "note": "해외 규제 개정을 국문으로 정리 — 원문보다 읽기 빠르다",
    },
    {
        "key": "eu",
        "region": "EU",
        "flag": "🇪🇺",
        "agency": "European Commission (DG GROW)",
        "url": "https://single-market-economy.ec.europa.eu/news_en",
        "list_selector": "",          # article 태그로 잡힌다. 전체를 훑어도 소음이 적다
        "keywords": ["cosmetic", "annex", "cmr", "omnibus", "fragrance allergen"],
    },
    {
        "key": "bpom",
        "region": "인도네시아",
        "flag": "🇮🇩",
        "agency": "BPOM",
        "url": "https://www.pom.go.id",
        "keywords": ["kosmetik", "cosmetic", "halal"],
        # 뉴스 카드의 링크 텍스트에 날짜·조회수가 같이 들어 있다
        #   "13 Jul 2026 Dilihat 6852 kali BPOM Intensifkan..." → 앞부분을 뗀다
        "title_strip": [r"^\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}:\d{2})?\s*",
                        r"^\d{1,2}\s+\w{3,9}\s+\d{4}\s*",
                        r"^Dilihat\s+[\d.,]+\s+kali\s*"],
        "min_title": 25,   # 'Notifikasi Kosmetik' 같은 메뉴 라벨 제외
    },
    {
        # 2026-09-19 확인: 어떤 주소로 요청해도 abuse-detection 페이지로 보낸다.
        # 자동 수집을 막아 둔 것이므로 우회하지 않고 꺼 둔다.
        # FDA 소식은 기관이 제공하는 이메일 구독을 쓰는 게 맞다.
        "key": "fda",
        "region": "미국",
        "flag": "🇺🇸",
        "agency": "FDA",
        "url": "https://www.fda.gov/cosmetics",
        "keywords": ["cosmetic", "mocra", "fragrance allergen", "gmp", "registration"],
        "enabled": False,
        "note": "FDA가 자동 수집을 차단합니다(abuse detection). 우회하지 않고 꺼 뒀습니다 — "
                "FDA 이메일 구독을 쓰세요",
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
_DATE_RE = re.compile(r"(20\d{2})[-./\s]+(\d{1,2})[-./\s]+(\d{1,2})")


def _published_date(anchor):
    """공지가 올라온 날. 목록 한 줄(li/article/tr) 안에서 찾는다.

    목록마다 날짜 위치가 달라서 <time datetime> 을 먼저 보고,
    없으면 그 줄의 텍스트에서 날짜 모양을 찾는다. 못 찾으면 빈 문자열.
    """
    row = anchor.find_parent(["li", "article", "tr"])
    if row is None:
        return ""

    tag = row.find("time")
    if tag and tag.get("datetime"):
        return tag["datetime"][:10]

    text = row.get_text(" ", strip=True)
    if len(text) > 400:        # 목록 한 줄이 아니라 큰 덩어리면 엉뚱한 날짜를 집는다
        return ""

    m = _DATE_RE.search(text)
    if not m:
        return ""
    try:
        return "{}-{:02d}-{:02d}".format(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return ""



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

    # 목록 영역이 지정돼 있으면 그 안만 본다. 기관 사이트는 메뉴 링크가
    # 수백 개라, 이걸 안 하면 결과가 전부 메뉴로 덮인다.
    selector = source.get("list_selector") or ""
    root = soup.select_one(selector) if selector else None
    if root is None:
        root = soup

    strips = [re.compile(pat, re.I) for pat in source.get("title_strip", [])]

    for a in root.find_all("a", href=True):
        title = " ".join(a.get_text().split())       # 공백 정리
        for pat in strips:                           # 제목 앞 군더더기 제거
            title = pat.sub("", title).strip()
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
            "published": _published_date(a),         # 공지가 올라온 날 (없으면 "")
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
        writer = csv.DictWriter(
            f, fieldnames=["공지일", "수집일", "지역", "기관", "제목", "링크"])
        writer.writeheader()
        writer.writerows([{
            "공지일": it.get("published", ""),
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

    targets = [s for s in SOURCES
               if s.get("enabled", True) and (not keys or s["key"] in keys)]
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
                     "agency": s["agency"], "url": s["url"], "note": s.get("note", ""),
                     "enabled": s.get("enabled", True)}
                    for s in SOURCES],
        "store_path": os.path.relpath(STORE_PATH, BASE_DIR),
        "csv_path": os.path.relpath(CSV_PATH, BASE_DIR),
    }


# ── 5. 실행 ─────────────────────────────────────────────
def _force_utf8_console():
    """윈도우 콘솔(cp949)에서 국문·특수문자 출력이 깨지거나 죽는 걸 막는다.

    수집한 제목에는 en dash(–) 같은 글자가 섞여 있어서, 기본 cp949 로는
    UnicodeEncodeError 로 스크립트가 통째로 멈춘다.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


if __name__ == "__main__":
    _force_utf8_console()
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
