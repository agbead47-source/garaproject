# -*- coding: utf-8 -*-
"""국가별 화장품 수출입 - 실데이터 수집·조회.

출처: UN Comtrade public preview API (키 불필요)
  https://comtradeapi.un.org/public/v1/preview/C/A/HS

한국(reporter 410)이 신고한 화장품 4개 HS 코드의 국가별 수출·수입액을 받아온다.
"어느 시장이 크고, 어디가 늘고 있고, kg당 얼마에 나가는가"는 해외영업이 늘
쓰는 숫자다. 관심도 트렌드(성분)와 달리 이건 대리 지표가 아니라 통관 실적이다.

무역 통계는 반드시 구멍이 난다. 이 모듈은 그 구멍을 0으로 덮지 않고 표시한다.
처리 규칙은 아래 `결측치 처리` 주석 참고.

    python trade_store.py              # 전부 수집 (약 40초)
    python trade_store.py --force      # 캐시를 무시하고 다시 수집
    python trade_store.py --no-mirror  # 미러 통계 보완 없이
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
CACHE_DIR = os.path.join(BASE_DIR, "tradedata")
CACHE_PATH = os.path.join(CACHE_DIR, "comtrade.json")
REF_PATH = os.path.join(CACHE_DIR, "partner_areas.json")

API = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
REF_API = "https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json"
USER_AGENT = "todo-trade-stats/1.0 (cosmetics trade dashboard; educational prototype)"

# preview 엔드포인트는 500건에서 잘린다. 잘린 줄 모르면 조용히 손실된다.
PREVIEW_LIMIT = 500

REPORTER = 410                 # 대한민국
YEARS_BACK = 3                 # 최근 3개 연도
TTL_DAYS = 20                  # 연 단위 통계라 자주 받을 이유가 없다
FETCH_DELAY = 1.2              # 초
MAX_FETCH_PER_CALL = 6         # 화면 수집 버튼 한 번에 받는 블록 수
MIRROR_LIMIT = 8               # 한 번에 미러로 메울 국가 수

FLOWS = [
    {"code": "X", "label": "수출", "mirror_flow": "M"},
    {"code": "M", "label": "수입", "mirror_flow": "X"},
]
FLOW_MAP = {f["code"]: f for f in FLOWS}

# 화장품으로 묶는 HS 4단위. 비누(3401) 같은 생활용품은 뺐다.
HS_CODES = [
    {"code": "3303", "label": "향수·화장수", "short": "향수"},
    {"code": "3304", "label": "기초·색조", "short": "기초·색조"},
    {"code": "3305", "label": "두발용", "short": "두발"},
    {"code": "3307", "label": "면도·목욕·데오드란트", "short": "면도·목욕"},
]
HS_MAP = {h["code"]: h for h in HS_CODES}

SOURCE = {
    "name": "UN Comtrade",
    "url": "https://comtradeapi.un.org/public/v1/preview/C/A/HS",
    "reporter": "대한민국(410) 신고 기준",
    "note": "통관 신고 실적. 수출은 FOB, 수입은 CIF 기준이라 상대국 통계와 6~10% 차이가 난다.",
}

# 국가가 아닌 집계 코드. 국가별 순위에 섞이면 중복·왜곡이 생긴다.
#   490(Other Asia, nes)은 사실상 대만이라 실제 거래처다. 빼지 않고 이름만 밝혀 둔다.
_SKIP_PARTNERS = {0}           # World (합계 행)
_SKIP_NAME_HINTS = (
    "Areas, nes", "Bunkers", "Free Zones", "Special Categories", "Neutral Zone",
    "Europe EU, nes", "Europe EFTA, nes", "Eastern Europe, nes", "Other Europe, nes",
    "Africa CAMEU region, nes", "CACM, nes", "Caribbean, nes", "LAIA, nes",
    "North America and Central America, nes", "Oceania, nes", "Rest of America, nes",
    "Western Asia, nes", "So. African Customs Union",
)

# 자주 나오는 시장은 한국어로 부른다. 없으면 영문 이름을 그대로 쓴다.
KO_NAMES = {
    842: "미국", 156: "중국", 392: "일본", 344: "홍콩", 704: "베트남",
    643: "러시아", 490: "기타 아시아(대만 등)", 784: "아랍에미리트", 616: "폴란드",
    764: "태국", 826: "영국", 124: "캐나다", 360: "인도네시아", 36: "호주",
    458: "말레이시아", 251: "프랑스", 250: "프랑스", 702: "싱가포르", 398: "카자흐스탄",
    528: "네덜란드", 608: "필리핀", 792: "튀르키예", 417: "키르기스스탄",
    116: "캄보디아", 699: "인도", 356: "인도", 276: "독일", 682: "사우디아라비아",
    804: "우크라이나", 104: "미얀마", 484: "멕시코", 233: "에스토니아",
    203: "체코", 76: "브라질", 496: "몽골", 440: "리투아니아", 724: "스페인",
    860: "우즈베키스탄", 752: "스웨덴", 208: "덴마크", 368: "이라크", 380: "이탈리아",
    642: "루마니아", 376: "이스라엘", 56: "벨기에", 152: "칠레", 414: "쿠웨이트",
    410: "대한민국", 554: "뉴질랜드", 710: "남아프리카공화국", 818: "이집트",
    634: "카타르", 512: "오만", 48: "바레인", 400: "요르단", 422: "레바논",
    586: "파키스탄", 50: "방글라데시", 144: "스리랑카", 524: "네팔", 418: "라오스",
    112: "벨라루스", 31: "아제르바이잔", 268: "조지아", 51: "아르메니아",
    762: "타지키스탄", 795: "투르크메니스탄", 348: "헝가리", 703: "슬로바키아",
    705: "슬로베니아", 191: "크로아티아", 100: "불가리아", 300: "그리스",
    620: "포르투갈", 372: "아일랜드", 246: "핀란드", 578: "노르웨이", 40: "오스트리아",
    756: "스위스", 170: "콜롬비아", 604: "페루", 32: "아르헨티나", 858: "우루과이",
    218: "에콰도르", 320: "과테말라", 591: "파나마", 214: "도미니카공화국",
    566: "나이지리아", 404: "케냐", 504: "모로코", 788: "튀니지", 12: "알제리",
}


# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------

def target_years(today=None):
    """받아올 연도. 올해 실적은 연 단위로 아직 올라오지 않는다."""
    year = (today or date.today()).year
    return list(range(year - YEARS_BACK, year))


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stale(entry, ttl_days=TTL_DAYS):
    if not entry or not entry.get("fetched_at"):
        return True
    try:
        fetched = datetime.fromisoformat(entry["fetched_at"])
    except ValueError:
        return True
    return datetime.now(timezone.utc) - fetched > timedelta(days=ttl_days)


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save(path, payload):
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, path)


def _empty_cache():
    return {"blocks": {}, "mirror": {}, "updated_at": ""}


def block_key(year, flow, code):
    return "{}|{}|{}".format(year, flow, code)


def mirror_key(year, flow, partner):
    return "{}|{}|{}".format(year, flow, partner)


def planned_blocks(years=None):
    """받아야 할 블록 전체. (연도 × 수출입 × HS 코드)"""
    years = years or target_years()
    return [(y, f["code"], h["code"])
            for y in years for f in FLOWS for h in HS_CODES]


# ---------------------------------------------------------------------------
# 수집
# ---------------------------------------------------------------------------

def _get(params, timeout=40):
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def _fetch_block(year, flow, code):
    """한 해 · 한 방향 · 한 HS 코드의 상대국별 실적."""
    payload = _get({"reporterCode": REPORTER, "period": year,
                    "flowCode": flow, "cmdCode": code})
    data = payload.get("data") or []

    rows = []
    for item in data:
        partner = item.get("partnerCode")
        if partner is None:
            continue
        rows.append({
            "p": partner,
            "v": item.get("primaryValue"),
            "w": item.get("netWgt"),
            # 신고값이 아니라 추정값이면 화면에서 밝힌다
            "est": bool(item.get("isQtyEstimated") or item.get("legacyEstimationFlag")),
        })

    return {
        "rows": rows,
        "count": payload.get("count", len(rows)),
        # 500건에서 잘렸다면 이 블록은 불완전하다
        "truncated": len(data) >= PREVIEW_LIMIT,
        "fetched_at": _now(),
    }


def _fetch_mirror(year, flow, partner):
    """미러 통계 - 상대국이 신고한 반대 방향 실적.

    우리 통계에서 빠진 나라라도 상대국이 신고했으면 규모는 알 수 있다.
    FOB/CIF 차이가 있어 값이 정확히 같지는 않다. 그래서 따로 표시한다.

    상대국 하나당 한 번만 부른다. HS 4개를 묶어도 4건이라 잘릴 일이 없다.
    """
    payload = _get({"reporterCode": partner, "period": year,
                    "flowCode": FLOW_MAP[flow]["mirror_flow"],
                    "cmdCode": ",".join(h["code"] for h in HS_CODES),
                    "partnerCode": REPORTER})

    by_code = {}
    for row in payload.get("data") or []:
        if row.get("primaryValue"):
            by_code[row.get("cmdCode")] = (by_code.get(row.get("cmdCode"), 0.0)
                                           + row["primaryValue"])
    return {"by_code": by_code, "v": sum(by_code.values()) or None,
            "fetched_at": _now()}


def refresh_partners(force=False):
    """상대국 코드표. 1년에 한 번 바뀔까 말까 한 파일이다."""
    ref = _load(REF_PATH, None)
    if ref and not force and not _stale(ref, ttl_days=180):
        return ref

    req = urllib.request.Request(REF_API, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=40) as res:
        payload = json.loads(res.read().decode("utf-8"))

    areas = {}
    for row in payload.get("results", []):
        areas[str(row["id"])] = {
            "name": row.get("text") or row.get("PartnerDesc") or "",
            "iso2": (row.get("PartnerCodeIsoAlpha2") or "").strip(),
        }

    ref = {"areas": areas, "fetched_at": _now()}
    _save(REF_PATH, ref)
    return ref


def collect(limit=MAX_FETCH_PER_CALL, force=False, mirror=True, verbose=False):
    """오래된 블록만 골라 받아온다. 화면 버튼과 CLI가 같이 쓴다."""
    cache = _load(CACHE_PATH, _empty_cache())
    years = target_years()

    try:
        refresh_partners()
    except Exception as exc:                           # noqa: BLE001
        if verbose:
            print("  코드표 갱신 실패: {}".format(str(exc)[:60]))

    todo = [b for b in planned_blocks(years)
            if force or _stale(cache["blocks"].get(block_key(*b)))]
    remaining = len(todo)
    if limit:
        todo = todo[:limit]

    done = failed = 0
    for idx, (year, flow, code) in enumerate(todo):
        key = block_key(year, flow, code)
        try:
            cache["blocks"][key] = _fetch_block(year, flow, code)
            done += 1
            if verbose:
                block = cache["blocks"][key]
                print("  OK   {} {:<4} {:<5} 상대국 {:>3}건{}".format(
                    year, FLOW_MAP[flow]["label"], code, len(block["rows"]),
                    "  ※500건에서 잘림" if block["truncated"] else ""))
        except urllib.error.HTTPError as exc:
            failed += 1
            if verbose:
                print("  FAIL {} {} {} HTTP {}".format(year, flow, code, exc.code))
            if exc.code in (429, 403):
                break                                  # 레이트리밋이면 그만 두드린다
        except Exception as exc:                       # noqa: BLE001
            failed += 1
            if verbose:
                print("  FAIL {} {} {} {}".format(year, flow, code, str(exc)[:50]))

        if idx < len(todo) - 1:
            time.sleep(FETCH_DELAY)

    mirrored = 0
    if mirror and not failed:
        mirrored = _collect_mirrors(cache, years, verbose=verbose)

    if done or mirrored:
        cache["updated_at"] = _now()
        _save(CACHE_PATH, cache)

    return {"done": done, "failed": failed,
            "remaining": max(remaining - done, 0), "mirrored": mirrored}


def _collect_mirrors(cache, years, verbose=False):
    """최신 연도에서 빠진 나라를 상대국 신고로 메울 수 있는지 확인한다.

    직전 연도엔 있었는데 최신 연도에 없는 나라만 본다. 거래가 끊긴 것인지
    신고가 안 된 것인지는 상대국 통계를 봐야 갈린다.
    """
    if len(years) < 2:
        return 0

    latest, prev = years[-1], years[-2]
    targets = []
    for flow in FLOWS:
        # 그 해에 아예 한 줄도 없는 나라만 본다. 코드 하나가 비는 것은 결측이 아니라
        # 그 품목이 안 나간 것이다.
        now_have = _reported_partners(cache, latest, flow["code"])
        prev_have = _reported_partners(cache, prev, flow["code"], with_value=True)
        if not now_have or not prev_have:
            continue

        for partner, value in prev_have.items():
            if partner in now_have or partner in _SKIP_PARTNERS:
                continue
            key = mirror_key(latest, flow["code"], partner)
            if key in cache["mirror"]:
                continue
            targets.append((value, latest, flow["code"], partner, key))

    targets.sort(reverse=True)                         # 직전 연도 규모가 큰 곳부터
    done = 0
    for _, year, flow, partner, key in targets[:MIRROR_LIMIT]:
        try:
            cache["mirror"][key] = _fetch_mirror(year, flow, partner)
            done += 1
            if verbose:
                got = cache["mirror"][key]["v"]
                print("  미러 {} {} ← {:<5} {}".format(
                    year, FLOW_MAP[flow]["label"], partner,
                    "{:,.0f} USD".format(got) if got else "상대국도 미신고"))
        except Exception as exc:                       # noqa: BLE001
            if verbose:
                print("  미러 실패 {} {}".format(partner, str(exc)[:40]))
            break
        time.sleep(FETCH_DELAY)
    return done


# ---------------------------------------------------------------------------
# 결측치 처리
# ---------------------------------------------------------------------------
#   무역 통계는 반드시 구멍이 난다. 여기서 정할 것은 "어떻게 메우느냐"보다
#   "메운 것을 어떻게 밝히느냐"다. 빈 칸을 0으로 만들면 화면에서는 '수출이 끊긴
#   나라'로 보이는데, 실제로는 신고가 안 된 것뿐인 경우가 많다.
#
#   먼저 갈라야 하는 것이 있다. "0"과 "모름"은 다르다.
#   Comtrade 는 거래가 없는 상대국을 아예 싣지 않는다. 그 해 통계가 올라와 있는데
#   이름이 없다면 그건 결측이 아니라 거래가 없었다는 뜻이다(실적 없음 = 0).
#   반대로 그 해 통계 자체를 아직 안 들고 있으면(미공개거나 아직 안 받았거나)
#   그건 0이 아니라 모름이다. 둘을 같은 칸에 그리면 안 된다.
#
#     reported  신고값 그대로
#     none      실적 없음(0). 통계는 들고 있고 그 나라 이름만 없다
#     mirror    우리 쪽엔 빠졌는데 상대국이 신고한 값 (FOB/CIF 차이가 섞인다)
#     partial   HS 코드 일부만 받아 둔 상태 - 실제보다 작은 값이다
#     interp    앞뒤 연도가 있어 가운데를 선형 보간한 값
#     missing   메우지 않음. 0이 아니라 모름
#
#   보간은 가운데가 빈 칸에만 한다. 양 끝은 건드리지 않는다.
#   끝을 늘리는 것은 보간이 아니라 예측이고, 여기서 할 일이 아니다.
#
#   증감률은 두 해 모두 실측(reported/none/mirror)일 때만 낸다.
#   보간값으로 추세를 그리면 만들어 낸 숫자로 만들어 낸 그래프가 된다.
#   합계도 실측만 더한다. 보간값을 총액에 넣으면 총액이 추정치가 된다.

FILL_META = {
    "reported": {"label": "신고", "css": "ok", "desc": "한국 통관 신고값 그대로"},
    "none": {"label": "실적 없음", "css": "none",
             "desc": "그 해 통계에 이 나라가 없음 = 거래 없음(0). 모름이 아니다"},
    "mirror": {"label": "미러", "css": "warn",
               "desc": "우리 쪽엔 빠졌는데 상대국이 신고한 값 (FOB/CIF 차이 포함)"},
    "partial": {"label": "수집 중", "css": "warn",
                "desc": "HS 코드 일부만 받아 둔 상태라 실제보다 작다 (합계·증감률 제외)"},
    "interp": {"label": "보간", "css": "warn",
               "desc": "앞뒤 연도 사이를 선형 보간한 값 (합계·증감률 제외)"},
    "missing": {"label": "미보고", "css": "missing",
                "desc": "메우지 않음. 0이 아니라 모름"},
}
FILL_ORDER = ["reported", "none", "mirror", "partial", "interp", "missing"]

# 실측으로 인정하는 상태. 합계와 증감률에 쓴다.
SOLID = ("reported", "none", "mirror")


def _fill_series(series):
    """연도별 시계열의 구멍을 메운다.

    가운데가 비었고 앞뒤가 실측이면 선형 보간한다. 양 끝은 보간하지 않는다.
    """
    years = sorted(series)
    for idx, year in enumerate(years):
        cell = series[year]
        if cell["status"] != "missing":
            continue

        before = next((series[y] for y in reversed(years[:idx])
                       if series[y]["status"] in SOLID), None)
        after = next((series[y] for y in years[idx + 1:]
                      if series[y]["status"] in SOLID), None)
        if before and after:
            cell["value"] = (before["value"] + after["value"]) / 2
            cell["status"] = "interp"
    return series


# ---------------------------------------------------------------------------
# 조회
# ---------------------------------------------------------------------------

def _partner_meta(ref, code):
    """상대국 이름·국기. 코드표가 없어도 코드만으로 굴러가게 둔다."""
    area = (ref.get("areas") or {}).get(str(code), {})
    name_en = area.get("name") or "코드 {}".format(code)
    iso2 = area.get("iso2") or ""

    flag = ""
    if len(iso2) == 2 and iso2.isalpha():
        flag = "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in iso2.upper())

    return {
        "code": code,
        "name": KO_NAMES.get(code, name_en),
        "name_en": name_en,
        "flag": flag,
        "skip": any(hint in name_en for hint in _SKIP_NAME_HINTS),
    }


def _reported_partners(cache, year, flow, with_value=False):
    """그 해 그 방향으로 한 줄이라도 신고된 상대국."""
    found = {}
    for hs in HS_CODES:
        block = cache["blocks"].get(block_key(year, flow, hs["code"]))
        if not block:
            continue
        for row in block["rows"]:
            if row["p"] in _SKIP_PARTNERS or not row.get("v"):
                continue
            found[row["p"]] = found.get(row["p"], 0.0) + row["v"]
    return found if with_value else set(found)


def _have_codes(cache, years, codes, flow):
    """{연도: 받아 둔 HS 코드 수}.

    0과 모름을 가르는 기준이다. 그 해 통계를 들고 있는데 나라 이름이 없으면
    거래가 없었던 것이고, 통계 자체가 없으면 모르는 것이다.
    """
    return {y: sum(1 for c in codes
                   if (cache["blocks"].get(block_key(y, flow, c)) or {}).get("rows"))
            for y in years}


def _collect_cells(cache, years, codes, flow):
    """상대국 × 연도 격자. 고른 HS 코드만 더한다."""
    grid = {}
    for year in years:
        for code in codes:
            block = cache["blocks"].get(block_key(year, flow, code))
            if not block:
                continue
            for row in block["rows"]:
                if row["p"] in _SKIP_PARTNERS or not row.get("v"):
                    continue
                cell = grid.setdefault(row["p"], {}).setdefault(
                    year, {"value": 0.0, "weight": 0.0, "codes": 0, "est": False})
                cell["value"] += row["v"]
                cell["weight"] += row.get("w") or 0.0
                cell["codes"] += 1
                cell["est"] = cell["est"] or row.get("est", False)
    return grid


def _series_for(grid, partner, years, cache, flow, have_codes, want):
    """한 나라 한 방향의 연도별 값 + 상태."""
    raw = grid.get(partner, {})
    series = {}

    for year in years:
        cell = raw.get(year)
        have = have_codes.get(year, 0)

        if have == 0:
            # 그 해 통계를 아직 안 들고 있다. 0이 아니라 모름이다.
            series[year] = {"value": None, "weight": 0.0, "status": "missing",
                            "codes": 0, "est": False}
            continue

        if cell:
            series[year] = {
                "value": cell["value"], "weight": cell["weight"],
                "status": "reported" if have == want else "partial",
                "codes": cell["codes"], "est": cell["est"],
            }
            continue

        if have < want:
            # 절반만 받아 둔 상태에서 이름이 없다고 0이라고 할 수는 없다
            series[year] = {"value": None, "weight": 0.0, "status": "missing",
                            "codes": 0, "est": False}
            continue

        # 통계는 다 들고 있는데 이름이 없다. 상대국이 신고했는지 한 번 더 본다.
        entry = cache["mirror"].get(mirror_key(year, flow, partner))
        value = entry.get("v") if entry else None
        if value:
            series[year] = {"value": value, "weight": 0.0, "status": "mirror",
                            "codes": 0, "est": False}
        else:
            series[year] = {"value": 0.0, "weight": 0.0, "status": "none",
                            "codes": 0, "est": False}

    return _fill_series(series)


def _growth(series, year, prev_year):
    """전년비. 두 해 모두 실측일 때만 낸다."""
    now, prev = series.get(year), series.get(prev_year)
    if not (now and prev):
        return None
    if now["status"] not in SOLID or prev["status"] not in SOLID:
        return None
    if not prev["value"]:
        return None                       # 0에서 출발한 증감률은 의미가 없다
    return (now["value"] - prev["value"]) / prev["value"] * 100


def is_ready():
    cache = _load(CACHE_PATH, None)
    return bool(cache and cache.get("blocks"))


def status():
    """수집 진행 상태. 화면 버튼 문구에 쓴다."""
    cache = _load(CACHE_PATH, _empty_cache())
    years = target_years()
    planned = planned_blocks(years)
    have = [b for b in planned if cache["blocks"].get(block_key(*b))]
    fresh = [b for b in planned if not _stale(cache["blocks"].get(block_key(*b)))]
    return {
        "collected": len(have),
        "fresh": len(fresh),
        "total": len(planned),
        "mirror": len(cache.get("mirror") or {}),
        "updated_at": (cache.get("updated_at") or "")[:10],
        "years": years,
    }


def get_trade(hs="all", year=None, top=25):
    """국가별 화장품 수출입.

    hs: "all" 또는 HS 4단위 코드 하나
    year: 기준 연도 (기본값은 수집된 가장 최근 연도)
    """
    cache = _load(CACHE_PATH, _empty_cache())
    ref = _load(REF_PATH, {"areas": {}})
    info = status()

    hs = hs if hs in HS_MAP else "all"
    codes = [hs] if hs != "all" else [h["code"] for h in HS_CODES]

    # 블록이 하나도 없는 연도는 통계가 아직 안 올라온 것이다. 연도 목록에서 뺀다.
    years = [y for y in info["years"]
             if any(cache["blocks"].get(block_key(y, f["code"], c))
                    and cache["blocks"][block_key(y, f["code"], c)]["rows"]
                    for f in FLOWS for c in codes)]

    if not years:
        return {
            "ready": False, "rows": [], "years": [], "year": None, "prev_year": None,
            "hs": hs, "hs_codes": HS_CODES, "hs_label": "", "flows": FLOWS,
            "source": dict(SOURCE), "fill_meta": FILL_META, "fill_rows": [],
            "fill": {k: 0 for k in FILL_ORDER}, "totals": {}, "progress": info,
            "truncated": [], "skipped": 0, "row_total": 0,
        }

    year = year if year in years else years[-1]
    prev_year = years[years.index(year) - 1] if years.index(year) > 0 else None

    grids, have_codes = {}, {}
    for flow in FLOWS:
        grids[flow["code"]] = _collect_cells(cache, years, codes, flow["code"])
        have_codes[flow["code"]] = _have_codes(cache, years, codes, flow["code"])

    partners = sorted(set(grids["X"]) | set(grids["M"]))
    rows, skipped = [], 0
    fill_count = {k: 0 for k in FILL_ORDER}

    for partner in partners:
        meta = _partner_meta(ref, partner)
        if meta["skip"]:
            skipped += 1
            continue

        entry = dict(meta)
        for flow in FLOWS:
            code = flow["code"]
            series = _series_for(grids[code], partner, years, cache, code,
                                 have_codes[code], len(codes))
            cell = series[year]
            side = {
                "value": cell["value"],
                "status": cell["status"],
                "meta": FILL_META[cell["status"]],
                "solid": cell["status"] in SOLID,
                "growth": _growth(series, year, prev_year) if prev_year else None,
                "series": [{"year": y, "value": series[y]["value"],
                            "status": series[y]["status"]} for y in years],
                "est": cell["est"],
                "codes": cell["codes"],
            }
            # kg당 단가 - 신고 중량이 있을 때만. ODM 견적에서 바로 쓰는 숫자다
            side["unit_price"] = (cell["value"] / cell["weight"]
                                  if cell["weight"] and cell["value"] else None)
            entry[code] = side
            fill_count[cell["status"]] += 1

        x, m = entry["X"], entry["M"]
        entry["balance"] = ((x["value"] or 0) - (m["value"] or 0)
                            if (x["solid"] or m["solid"]) else None)
        entry["sort_value"] = (x["value"] or 0) if x["solid"] else 0
        entry["sort_alt"] = (m["value"] or 0) if m["solid"] else 0
        rows.append(entry)

    rows.sort(key=lambda r: (r["sort_value"], r["sort_alt"]), reverse=True)
    for idx, row in enumerate(rows, start=1):
        row["rank"] = idx

    # 합계는 실측만 더한다 (보간·미보고 제외)
    export_total = sum(r["X"]["value"] or 0 for r in rows if r["X"]["solid"])
    import_total = sum(r["M"]["value"] or 0 for r in rows if r["M"]["solid"])

    prev_export = None
    if prev_year:
        prev_export = 0.0
        for row in rows:
            cell = next((s for s in row["X"]["series"] if s["year"] == prev_year), None)
            if cell and cell["status"] in SOLID and cell["value"]:
                prev_export += cell["value"]

    shown = rows[:top] if top else rows
    for row in shown:
        row["share"] = ((row["X"]["value"] or 0) / export_total * 100
                        if export_total and row["X"]["solid"] else None)

    return {
        "ready": True,
        "rows": shown,
        "row_total": len(rows),
        "years": years,
        "year": year,
        "prev_year": prev_year,
        "hs": hs,
        "hs_codes": HS_CODES,
        "hs_label": HS_MAP[hs]["label"] if hs != "all" else "화장품 4개 코드 합계",
        "flows": FLOWS,
        "source": dict(SOURCE),
        "fill_meta": FILL_META,
        "fill": fill_count,
        "fill_rows": [dict(FILL_META[k], key=k, count=fill_count[k])
                      for k in FILL_ORDER],
        "totals": {
            "export": export_total,
            "import": import_total,
            "balance": export_total - import_total,
            "export_growth": ((export_total - prev_export) / prev_export * 100
                              if prev_export else None),
            "countries": len(rows),
        },
        "progress": info,
        "skipped": skipped,
        "truncated": [k for k, b in cache["blocks"].items() if b.get("truncated")],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _force_utf8_console():
    """윈도우 콘솔(cp949)에서 한글·기호가 터지지 않게."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


if __name__ == "__main__":
    _force_utf8_console()
    force = "--force" in sys.argv
    mirror = "--no-mirror" not in sys.argv

    years = target_years()
    print("국가별 화장품 수출입 수집 - {} / HS {} / 출처 {}".format(
        "·".join(str(y) for y in years),
        ",".join(h["code"] for h in HS_CODES), SOURCE["name"]))

    total_done = total_failed = total_mirror = 0
    for _ in range(12):
        result = collect(limit=MAX_FETCH_PER_CALL, force=force and total_done == 0,
                         mirror=mirror, verbose=True)
        total_done += result["done"]
        total_failed += result["failed"]
        total_mirror += result["mirrored"]
        if result["remaining"] == 0 or (result["done"] == 0 and result["failed"] == 0):
            break
        if result["failed"]:
            print("  … 잠시 대기 20초")
            time.sleep(20)

    print("\n블록 {}건 수집, 실패 {}건, 미러 보완 {}건".format(
        total_done, total_failed, total_mirror))

    data = get_trade()
    if not data["ready"]:
        print("수집된 자료가 없습니다.")
        sys.exit(1)

    tot = data["totals"]
    print("\n{}년 · {} · 국가 {}곳".format(data["year"], data["hs_label"], tot["countries"]))
    print("  수출 {:,.0f} USD{}  |  수입 {:,.0f} USD  |  수지 {:+,.0f} USD".format(
        tot["export"],
        " ({:+.1f}%)".format(tot["export_growth"]) if tot["export_growth"] is not None else "",
        tot["import"], tot["balance"]))

    print("\n상위 15개 시장")
    for row in data["rows"][:15]:
        x = row["X"]
        print("  {:>2}. {:<20} {:>12,.0f} USD  {:>7}  {:>9}  [{}]".format(
            row["rank"], row["name"], x["value"] or 0,
            "{:+.1f}%".format(x["growth"]) if x["growth"] is not None else "비교불가",
            "{:,.1f}/kg".format(x["unit_price"]) if x["unit_price"] else "-",
            x["meta"]["label"]))

    print("\n결측치 처리")
    for row in data["fill_rows"]:
        print("  {:<6} {:>4}칸  {}".format(row["label"], row["count"], row["desc"]))
    if data["truncated"]:
        print("  ※ 500건에서 잘린 블록: {}".format(", ".join(data["truncated"])))
    print("  집계 코드 제외: {}곳".format(data["skipped"]))
