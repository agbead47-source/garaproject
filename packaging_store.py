# -*- coding: utf-8 -*-
"""포장재 가격 동향 - 수집·조회.

화장품 용기·포장에 쓰는 소재값이 오르는지 내리는지 보는 화면이다.
**용기 납품가를 계산하는 기능이 아니다.** 실제 납품가는 금형·수량·도장·후가공·
물류가 섞여 정해진다. 여기 숫자는 "왜 올려달라는지" 를 가늠하는 참고 지표다.

출처 두 곳:

  1) 미국 노동통계국(BLS) 생산자물가지수(PPI) - 월간 지수, API 키 없이도 된다
     키를 넣으면 v2 로 붙어 한도가 늘고 계열 이름(catalog)까지 받아 온다.
     https://www.bls.gov/developers/

  2) Metals.Dev - 알루미늄 시세, API 키 필요 (무료 100회/월)
     https://metals.dev/docs

지켜야 할 것:
  - 화면을 열 때마다 외부 API 를 부르지 않는다. 서버가 받아 둔 값을 같이 본다
  - 서버가 받아 온 시각과 공급자가 적어 둔 기준시각을 따로 적는다
  - 월간 지수를 "실시간 시세" 라고 부르지 않는다
  - 값이 없으면 비워 둔다. 0 이나 지어낸 숫자로 채우지 않는다
  - 실패하면 마지막 정상값과 그 기준일을 그대로 두고 상태만 바꾼다
  - 합성고무 지수를 실리콘 가격으로 쓰지 않는다 (다른 재질이다)
  - 소재별 상승률을 평균 내서 "포장비 몇 % 인상" 같은 숫자를 만들지 않는다

    python packaging_store.py           # 받을 때가 된 것만 수집
    python packaging_store.py --force   # 주기를 무시하고 지금 수집
    python packaging_store.py --status  # 받아 둔 상태만 보기
"""

import json
import os
import sqlite3
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

import app_env

try:
    from zoneinfo import ZoneInfo
    SEOUL = ZoneInfo("Asia/Seoul")
except Exception:                                    # noqa: BLE001
    SEOUL = timezone.utc

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "packaging.db")

_local = threading.local()

USER_AGENT = "todo-trade-packaging/1.0 (cosmetics packaging cost watch; educational prototype)"

BLS_V1 = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
BLS_V2 = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
METALS_SPOT = "https://api.metals.dev/v1/metal/spot"
METALS_LATEST = "https://api.metals.dev/v1/latest"

# 갱신 주기.
#   BLS 는 월간 지수다. 하루 한 번만 확인하면 새 발표·수정을 놓치지 않는다.
#   Metals.Dev 무료 한도가 월 100회라 하루 2회(월 최대 62회)로 잡는다.
BLS_EVERY_HOURS = 24
METALS_EVERY_HOURS = 12
# 재시도까지 한도에 포함한다. 100 을 다 쓰지 않고 여유를 남긴다.
METALS_MONTHLY_CAP = 80

CHART_MONTHS = 12

# ---------------------------------------------------------------------------
# 소재
# ---------------------------------------------------------------------------
#   kind "index" - 지수다. 가격이 아니다. 단위가 없고 기준연도 대비 값이다
#   kind "price" - 실제 시세. 통화와 단위가 붙는다

MATERIALS = [
    {
        "key": "plastic_resin", "name": "플라스틱 원료", "icon": "🧴",
        "source": "bls", "series": "WPU066212", "kind": "index",
        "unit": "지수", "market": "미국 (BLS PPI)",
        "note": "수지 원료값. 캡·펌프·튜브 등 사출 부품의 바탕이 된다",
        "cadence": "월간",
    },
    {
        "key": "plastic_bottle", "name": "플라스틱 병", "icon": "🧪",
        "source": "bls", "series": "WPU072A01014", "kind": "index",
        "unit": "지수", "market": "미국 (BLS PPI)",
        "note": "완성된 플라스틱 병 출하가 지수",
        "cadence": "월간",
    },
    {
        "key": "glass", "name": "유리 용기", "icon": "🫙",
        "source": "bls", "series": "PCU327213327213", "kind": "index",
        "unit": "지수", "market": "미국 (BLS PPI)",
        "note": "유리 용기 제조업 출하가 지수",
        "cadence": "월간",
    },
    {
        "key": "paperboard", "name": "판지", "icon": "📦",
        "source": "bls", "series": "WPU0914", "kind": "index",
        "unit": "지수", "market": "미국 (BLS PPI)",
        "note": "단상자·완충재로 쓰는 판지",
        "cadence": "월간",
    },
    {
        "key": "pulp", "name": "펄프", "icon": "📄",
        "source": "bls", "series": "WPU0911", "kind": "index",
        "unit": "지수", "market": "미국 (BLS PPI)",
        "note": "종이·라벨·설명서의 원료",
        "cadence": "월간",
    },
    {
        "key": "synthetic_rubber", "name": "합성고무", "icon": "⚫",
        "source": "bls", "series": "WPU071102", "kind": "index",
        "unit": "지수", "market": "미국 (BLS PPI)",
        "note": "개스킷·오링에 쓰는 합성고무. 실리콘과는 다른 재질입니다 "
                "- 실리콘 값 대신 쓰지 않습니다",
        "cadence": "월간",
    },
    {
        "key": "aluminum", "name": "알루미늄", "icon": "🪙",
        "source": "metals", "series": "aluminum", "kind": "price",
        "unit": "USD/t", "market": "국제 시세 (Metals.Dev)",
        "note": "알루미늄 캡·에어로졸 캔·튜브",
        "cadence": "하루 2회 업데이트",
    },
    {
        "key": "silicone", "name": "실리콘", "icon": "🩹",
        "source": None, "series": "", "kind": "none",
        "unit": "", "market": "",
        "note": "무료로 쓸 수 있는 가격 출처를 찾지 못했습니다. "
                "합성고무 지수로 대신하지 않습니다 - 다른 재질입니다",
        "cadence": "",
    },
]
MATERIAL_MAP = {m["key"]: m for m in MATERIALS}
BLS_SERIES = {m["series"]: m["key"] for m in MATERIALS if m["source"] == "bls"}

# ---------------------------------------------------------------------------
# 포장 부품 - 어떤 부품이 어떤 소재를 쓰는가
# ---------------------------------------------------------------------------
#   합성고무는 개스킷·펌프처럼 실제로 그 재질을 쓰는 부품에만 건다.

PARTS = [
    {"key": "glass_bottle", "label": "유리 병", "icon": "🫙",
     "materials": ["glass"]},
    {"key": "plastic_bottle", "label": "플라스틱 병·용기", "icon": "🧴",
     "materials": ["plastic_bottle", "plastic_resin"]},
    {"key": "cap", "label": "캡·뚜껑", "icon": "🔘",
     "materials": ["plastic_resin"]},
    {"key": "pump", "label": "펌프·디스펜서", "icon": "💧",
     "materials": ["plastic_resin", "synthetic_rubber", "aluminum"]},
    {"key": "tube", "label": "튜브", "icon": "🧪",
     "materials": ["plastic_resin", "aluminum"]},
    {"key": "gasket", "label": "개스킷·오링", "icon": "⭕",
     "materials": ["synthetic_rubber"]},
    {"key": "aluminum_can", "label": "알루미늄 캔·에어로졸", "icon": "🥫",
     "materials": ["aluminum"]},
    {"key": "carton", "label": "종이 단상자", "icon": "📦",
     "materials": ["paperboard", "pulp"]},
    {"key": "label", "label": "라벨·설명서", "icon": "🏷",
     "materials": ["pulp"]},
    {"key": "silicone_part", "label": "실리콘 부품(퍼프·브러시)", "icon": "🩹",
     "materials": ["silicone"]},
]
PART_MAP = {p["key"]: p for p in PARTS}

# 자주 쓰는 포장 구성. 매번 부품을 하나씩 고르지 않게 한다.
PRESETS = [
    {"key": "glass_set", "label": "유리병 + 플라스틱 캡 + 종이 단상자",
     "parts": ["glass_bottle", "cap", "carton"]},
    {"key": "pump_set", "label": "플라스틱 펌프 용기 + 단상자",
     "parts": ["plastic_bottle", "pump", "carton"]},
    {"key": "tube_set", "label": "튜브 + 라벨",
     "parts": ["tube", "label"]},
    {"key": "aerosol_set", "label": "알루미늄 에어로졸",
     "parts": ["aluminum_can", "cap"]},
]
PRESET_MAP = {p["key"]: p for p in PRESETS}

# 상태 표시
STATUS_META = {
    "ok": {"label": "정상", "css": "ok"},
    "stale": {"label": "업데이트 지연", "css": "warn"},
    "needs_key": {"label": "API 키 설정 필요", "css": "warn"},
    "unsupported": {"label": "미지원", "css": "none"},
    "error": {"label": "수집 실패", "css": "missing"},
    "empty": {"label": "아직 수집 안 됨", "css": "none"},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    material    TEXT NOT NULL,
    period      TEXT NOT NULL,   -- 월간은 'YYYY-MM', 일간은 'YYYY-MM-DD'
    value       REAL NOT NULL,
    ref_time    TEXT,            -- 공급자가 적어 둔 기준시각
    preliminary INTEGER NOT NULL DEFAULT 0,
    fetched_at  TEXT NOT NULL,   -- 서버가 받아 온 시각
    revised_at  TEXT,            -- 같은 기준일 값이 바뀌어 다시 저장한 시각
    PRIMARY KEY (material, period)
);

CREATE TABLE IF NOT EXISTS sources (
    key         TEXT PRIMARY KEY,
    last_try    TEXT,
    last_ok     TEXT,
    status      TEXT,
    message     TEXT,
    endpoint    TEXT,
    quota_month TEXT,
    quota_used  INTEGER NOT NULL DEFAULT 0
);
"""


# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------

def now_seoul():
    return datetime.now(SEOUL)


def now_iso():
    return now_seoul().strftime("%Y-%m-%d %H:%M:%S")


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


def _parse(stamp):
    try:
        return datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=SEOUL)
    except (TypeError, ValueError):
        return None


def _hours_since(stamp):
    moment = _parse(stamp)
    if moment is None:
        return None
    return (now_seoul() - moment).total_seconds() / 3600


def get_source(key):
    conn = connect()
    row = conn.execute("SELECT * FROM sources WHERE key = ?", (key,)).fetchone()
    return dict(row) if row else {
        "key": key, "last_try": "", "last_ok": "", "status": "empty",
        "message": "", "endpoint": "", "quota_month": "", "quota_used": 0,
    }


def _save_source(key, **fields):
    row = get_source(key)
    row.update(fields)
    conn = connect()
    conn.execute(
        """INSERT INTO sources (key, last_try, last_ok, status, message,
                                endpoint, quota_month, quota_used)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(key) DO UPDATE SET
             last_try = excluded.last_try, last_ok = excluded.last_ok,
             status = excluded.status, message = excluded.message,
             endpoint = excluded.endpoint, quota_month = excluded.quota_month,
             quota_used = excluded.quota_used""",
        (key, row["last_try"], row["last_ok"], row["status"], row["message"],
         row["endpoint"], row["quota_month"], row["quota_used"]))
    conn.commit()
    return row


def save_point(material, period, value, ref_time="", preliminary=False):
    """관측값 한 칸. 같은 기준일이 또 오면 새로 만들지 않는다.

    값이 달라졌을 때만 고친다 (BLS 는 발표 후 넉 달까지 수정한다).
    돌려주는 값: "new" | "revised" | "same"
    """
    conn = connect()
    stamp = now_iso()
    row = conn.execute(
        "SELECT value FROM observations WHERE material = ? AND period = ?",
        (material, period)).fetchone()

    if row is None:
        conn.execute(
            """INSERT INTO observations
               (material, period, value, ref_time, preliminary, fetched_at)
               VALUES (?,?,?,?,?,?)""",
            (material, period, value, ref_time, 1 if preliminary else 0, stamp))
        conn.commit()
        return "new"

    if abs(row["value"] - value) < 1e-9:
        conn.execute(
            "UPDATE observations SET fetched_at = ?, ref_time = ?, preliminary = ? "
            "WHERE material = ? AND period = ?",
            (stamp, ref_time or "", 1 if preliminary else 0, material, period))
        conn.commit()
        return "same"

    conn.execute(
        """UPDATE observations SET value = ?, ref_time = ?, preliminary = ?,
           fetched_at = ?, revised_at = ? WHERE material = ? AND period = ?""",
        (value, ref_time or "", 1 if preliminary else 0, stamp, stamp,
         material, period))
    conn.commit()
    return "revised"


def points(material, limit=400):
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM observations WHERE material = ? ORDER BY period ASC",
        (material,)).fetchall()
    return [dict(r) for r in rows][-limit:]


# ---------------------------------------------------------------------------
# 수집 - BLS (월간 지수)
# ---------------------------------------------------------------------------

def _post_json(url, payload, timeout=60):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def collect_bls(force=False, verbose=False):
    """BLS PPI 여섯 계열을 한 번에 받아 온다. (요청 1회)

    키가 없으면 v1(미등록 한도), 있으면 v2 로 붙는다.
    """
    source = get_source("bls")
    age = _hours_since(source["last_ok"])
    if not force and age is not None and age < BLS_EVERY_HOURS:
        return {"skipped": True, "reason": "{:.1f}시간 전에 받았습니다".format(age),
                "new": 0, "revised": 0}

    key = app_env.get("BLS_API_KEY")
    this_year = date.today().year
    payload = {
        "seriesid": sorted(BLS_SERIES),
        # 전년동월비까지 내려면 13개월 이상이 필요하다. 넉넉히 3년.
        "startyear": str(this_year - 2),
        "endyear": str(this_year),
    }
    url = BLS_V1
    if key:
        url = BLS_V2
        payload["registrationkey"] = key
        payload["catalog"] = True

    _save_source("bls", last_try=now_iso(),
                 endpoint="v2" if key else "v1(미등록)")

    try:
        result = _post_json(url, payload)
    except Exception as exc:                          # noqa: BLE001
        # 실패해도 이미 받아 둔 값은 그대로 둔다. 상태만 바꾼다
        _save_source("bls", status="error", message=str(exc)[:200])
        if verbose:
            print("  BLS 실패:", str(exc)[:120])
        return {"skipped": False, "error": str(exc)[:200], "new": 0, "revised": 0}

    if result.get("status") != "REQUEST_SUCCEEDED":
        message = " / ".join(result.get("message", []))[:200] or "알 수 없는 오류"
        _save_source("bls", status="error", message=message)
        if verbose:
            print("  BLS 거절:", message)
        return {"skipped": False, "error": message, "new": 0, "revised": 0}

    counts = {"new": 0, "revised": 0, "same": 0}
    titles = {}
    for series in result.get("Results", {}).get("series", []):
        material = BLS_SERIES.get(series.get("seriesID"))
        if material is None:
            continue

        catalog = series.get("catalog") or {}
        if catalog.get("series_title"):
            titles[material] = catalog["series_title"]

        for item in series.get("data", []):
            period = item.get("period", "")
            if not period.startswith("M") or period == "M13":
                continue                              # 연간 평균(M13)은 건너뛴다
            try:
                value = float(item["value"])
            except (KeyError, TypeError, ValueError):
                continue                              # 값이 없으면 비워 둔다

            notes = " ".join(f.get("text", "") for f in item.get("footnotes", []) if f)
            outcome = save_point(
                material,
                "{}-{}".format(item["year"], period[1:]),
                value,
                ref_time="{}-{}".format(item["year"], period[1:]),
                preliminary="Preliminary" in notes)
            counts[outcome] = counts.get(outcome, 0) + 1

    message = "계열 {}개".format(len(BLS_SERIES))
    if titles:
        message += " · 이름 확인됨"
    _save_source("bls", status="ok", last_ok=now_iso(), message=message)

    if verbose:
        print("  BLS OK - 새 값 {new}개, 수정 {revised}개, 그대로 {same}개".format(**counts))
    return {"skipped": False, "new": counts["new"], "revised": counts["revised"],
            "same": counts["same"], "titles": titles}


# ---------------------------------------------------------------------------
# 수집 - Metals.Dev (알루미늄)
# ---------------------------------------------------------------------------

def _get_json(url, params, timeout=40):
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT,
                                                "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def metals_quota():
    """이번 달에 몇 번 썼는지. (무료 한도는 매달 1일에 초기화된다)"""
    source = get_source("metals")
    month = now_seoul().strftime("%Y-%m")
    used = source["quota_used"] if source["quota_month"] == month else 0
    return {"month": month, "used": used, "cap": METALS_MONTHLY_CAP,
            "left": max(METALS_MONTHLY_CAP - used, 0)}


def _spend_quota(n=1):
    quota = metals_quota()
    _save_source("metals", quota_month=quota["month"], quota_used=quota["used"] + n)


def collect_metals(force=False, verbose=False):
    """알루미늄 시세 한 번. 키가 없으면 부르지 않는다."""
    key = app_env.get("METALS_DEV_API_KEY")
    if not key:
        _save_source("metals", status="needs_key",
                     message="METALS_DEV_API_KEY 가 없습니다. .env 에 넣어 주세요.")
        return {"skipped": True, "reason": "API 키 없음", "new": 0, "revised": 0}

    source = get_source("metals")
    age = _hours_since(source["last_ok"])
    if not force and age is not None and age < METALS_EVERY_HOURS:
        return {"skipped": True, "reason": "{:.1f}시간 전에 받았습니다".format(age),
                "new": 0, "revised": 0}

    quota = metals_quota()
    if quota["left"] <= 0:
        _save_source("metals", status="stale",
                     message="이번 달 무료 한도({}회)를 다 썼습니다. "
                             "다음 달 1일에 초기화됩니다.".format(METALS_MONTHLY_CAP))
        return {"skipped": True, "reason": "월 한도 소진", "new": 0, "revised": 0}

    _save_source("metals", last_try=now_iso())

    # 알루미늄 하나만 부르는 엔드포인트를 먼저 쓴다. 금·은 시세까지 받아 올 이유가 없다.
    attempts = [("spot", METALS_SPOT, {"api_key": key, "metal": "aluminum",
                                       "currency": "USD", "unit": "mt"})]
    if source["endpoint"] == "latest" or quota["left"] >= 2:
        attempts.append(("latest", METALS_LATEST,
                         {"api_key": key, "currency": "USD", "unit": "mt"}))
    if source["endpoint"] == "latest":
        attempts.reverse()                            # 지난번에 되던 쪽부터

    last_error = ""
    for name, url, params in attempts:
        if metals_quota()["left"] <= 0:
            break
        _spend_quota(1)                               # 재시도도 한도에 포함한다
        try:
            payload = _get_json(url, params)
        except urllib.error.HTTPError as exc:
            last_error = "HTTP {}".format(exc.code)
            if exc.code in (401, 403):
                _save_source("metals", status="error",
                             message="API 키가 거절됐습니다 (HTTP {}).".format(exc.code))
                return {"skipped": False, "error": last_error, "new": 0, "revised": 0}
            continue
        except Exception as exc:                      # noqa: BLE001
            last_error = str(exc)[:120]
            continue

        if payload.get("status") != "success":
            last_error = str(payload.get("error_message")
                             or payload.get("error_code") or "알 수 없는 응답")[:120]
            continue

        value = _aluminum_of(payload, name)
        if value is None:
            last_error = "응답에 알루미늄 값이 없습니다"
            continue

        ref_time = payload.get("timestamp") or ""
        day = (ref_time[:10] if len(ref_time) >= 10
               else now_seoul().strftime("%Y-%m-%d"))
        outcome = save_point("aluminum", day, value, ref_time=ref_time)

        unit = payload.get("unit") or "mt"
        currency = payload.get("currency") or "USD"
        _save_source("metals", status="ok", last_ok=now_iso(), endpoint=name,
                     message="{} {}/{} · {}".format(currency, "{:,.2f}".format(value),
                                                    unit, name))
        if verbose:
            print("  Metals OK - 알루미늄 {:,.2f} {}/{} ({})".format(
                value, currency, unit, name))
        return {"skipped": False, "new": 1 if outcome == "new" else 0,
                "revised": 1 if outcome == "revised" else 0, "value": value,
                "unit": "{}/{}".format(currency, unit)}

    _save_source("metals", status="error",
                 message="받지 못했습니다: {}".format(last_error or "원인 불명"))
    if verbose:
        print("  Metals 실패:", last_error)
    return {"skipped": False, "error": last_error, "new": 0, "revised": 0}


def _aluminum_of(payload, endpoint):
    """응답에서 알루미늄 값만 꺼낸다. 다른 금속 시세는 쓰지 않는다."""
    if endpoint == "spot":
        rate = payload.get("rate") or {}
        value = rate.get("price", payload.get("price"))
    else:
        metals = payload.get("metals") or {}
        value = metals.get("aluminum")
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def collect(force=False, verbose=False):
    """두 출처를 각자의 주기에 맞춰 받는다."""
    init_db()
    bls = collect_bls(force=force, verbose=verbose)
    metals = collect_metals(force=force, verbose=verbose)
    return {"bls": bls, "metals": metals}


# ---------------------------------------------------------------------------
# 조회
# ---------------------------------------------------------------------------

def _month_key(period):
    return period[:7]


def _monthly(rows):
    """일간 관측을 월별 마지막 값으로 접는다. (차트 눈금을 월로 맞춘다)"""
    by_month = {}
    for row in rows:
        by_month[_month_key(row["period"])] = row
    return [by_month[m] for m in sorted(by_month)]


def _pct(now, before):
    """변화율. 기준값이 없거나 0 이면 내지 않는다."""
    if now is None or before in (None, 0):
        return None
    return (now - before) / before * 100


def _spark(values, width=260, height=64, low=None, high=None):
    """꺾은선 좌표.

    low/high 를 주면 그 눈금에 맞춰 그린다. 여러 선을 겹쳐 그릴 때 선마다
    제 눈금으로 그리면 비교가 되지 않는다.
    """
    if len(values) < 2:
        return ""
    low = min(values) if low is None else low
    high = max(values) if high is None else high
    span = (high - low) or 1
    step = width / (len(values) - 1)
    return " ".join("{:.1f},{:.1f}".format(i * step, height - (v - low) / span * height)
                    for i, v in enumerate(values))


def material_view(key, months=CHART_MONTHS):
    """소재 카드 한 장에 필요한 값."""
    material = MATERIAL_MAP[key]
    view = dict(material)
    view["status_meta"] = STATUS_META["empty"]
    view["series"] = []
    view["latest"] = None
    view["changes"] = []
    view["spark"] = ""

    if material["source"] is None:
        view["status"] = "unsupported"
        view["status_meta"] = STATUS_META["unsupported"]
        return view

    source = get_source(material["source"])
    rows = _monthly(points(key))
    # 과거를 지어내지 않는다. 받아 둔 만큼만 그린다
    window = rows[-months:]

    if not window:
        view["status"] = ("needs_key" if source["status"] == "needs_key"
                          else ("error" if source["status"] == "error" else "empty"))
        view["status_meta"] = STATUS_META[view["status"]]
        view["message"] = source["message"]
        view["collected_from"] = ""
        return view

    last = window[-1]
    view["latest"] = {
        "value": last["value"],
        "period": last["period"],
        "ref_time": last["ref_time"] or last["period"],
        "preliminary": bool(last["preliminary"]),
        "revised_at": last["revised_at"] or "",
    }
    view["series"] = [{"period": r["period"], "value": r["value"]} for r in window]
    view["spark"] = _spark([r["value"] for r in window])
    view["collected_from"] = rows[0]["period"]
    view["points"] = len(rows)

    # 비교 기준이 있을 때만 변화율을 낸다
    by_month = {r["period"][:7]: r["value"] for r in rows}
    current = _month_key(last["period"])
    for label, back in (("전월 대비", 1), ("3개월 전 대비", 3), ("전년 동월 대비", 12)):
        base_month = _shift_month(current, -back)
        base = by_month.get(base_month)
        pct = _pct(last["value"], base)
        if pct is not None:
            view["changes"].append({"label": label, "pct": pct, "base": base_month})

    if material["source"] == "metals":
        fresh_hours = METALS_EVERY_HOURS * 2
    else:
        fresh_hours = BLS_EVERY_HOURS * 2
    age = _hours_since(source["last_ok"])

    if source["status"] == "needs_key":
        view["status"] = "needs_key"
    elif source["status"] == "error":
        view["status"] = "error"
    elif age is None or age > fresh_hours:
        view["status"] = "stale"
    else:
        view["status"] = "ok"

    view["status_meta"] = STATUS_META[view["status"]]
    view["message"] = source["message"]
    view["fetched_at"] = source["last_ok"]
    return view


def _shift_month(month, delta):
    year, mon = int(month[:4]), int(month[5:7])
    total = year * 12 + (mon - 1) + delta
    return "{:04d}-{:02d}".format(total // 12, total % 12 + 1)


def compare_view(keys, months=CHART_MONTHS):
    """여러 소재를 한 그림에서 본다.

    단위가 서로 다르다(지수 vs USD/t). 공통 시작 시점을 100 으로 맞춰
    '그때 대비 얼마나 움직였나' 만 비교한다. 값 자체를 겹쳐 그리지 않는다.
    """
    series = []
    for key in keys:
        material = MATERIAL_MAP.get(key)
        if material is None or material["source"] is None:
            continue
        rows = _monthly(points(key))[-months:]
        if len(rows) >= 2:
            series.append({"key": key, "name": material["name"],
                           "icon": material["icon"],
                           "rows": {r["period"][:7]: r["value"] for r in rows}})

    if len(series) < 2:
        return None

    # 모두가 값을 가진 달만 쓴다. 비어 있는 달을 이어 붙이지 않는다
    common = set(series[0]["rows"])
    for s in series[1:]:
        common &= set(s["rows"])
    common = sorted(common)
    if len(common) < 2:
        return None

    base_month = common[0]
    rebased = []
    for s in series:
        base = s["rows"][base_month]
        if not base:
            continue
        rebased.append((s, [s["rows"][m] / base * 100 for m in common]))

    if len(rebased) < 2:
        return None

    # 눈금은 모든 선이 같이 쓴다. 100 선이 그림 안에 들어오게 범위를 넓힌다
    flat = [v for _, values in rebased for v in values] + [100.0]
    low, high = min(flat), max(flat)
    pad = (high - low) * 0.08 or 1
    low, high = low - pad, high + pad

    width, height = 520, 150
    lines = [{
        "key": s["key"], "name": s["name"], "icon": s["icon"],
        "values": [round(v, 1) for v in values],
        "last": round(values[-1], 1),
        "spark": _spark(values, width=width, height=height, low=low, high=high),
    } for s, values in rebased]

    return {
        "base_month": base_month,
        "months": common,
        "lines": lines,
        "low": round(low, 1),
        "high": round(high, 1),
        # 100 = 기준달. 그림에서 어디쯤인지 미리 계산해 둔다
        "baseline_y": round(height - (100.0 - low) / (high - low) * height, 1),
        "width": width,
        "height": height,
    }


def status_summary():
    """화면 위에 붙이는 수집 상태."""
    bls = get_source("bls")
    metals = get_source("metals")
    quota = metals_quota()
    return {
        "bls": {
            "status": bls["status"], "meta": STATUS_META.get(bls["status"],
                                                             STATUS_META["empty"]),
            "last_ok": bls["last_ok"], "last_try": bls["last_try"],
            "message": bls["message"], "endpoint": bls["endpoint"],
            "has_key": bool(app_env.get("BLS_API_KEY")),
            "every": "하루 1회",
        },
        "metals": {
            "status": metals["status"], "meta": STATUS_META.get(metals["status"],
                                                                STATUS_META["empty"]),
            "last_ok": metals["last_ok"], "last_try": metals["last_try"],
            "message": metals["message"], "endpoint": metals["endpoint"],
            "has_key": bool(app_env.get("METALS_DEV_API_KEY")),
            "every": "하루 2회",
            "quota": quota,
        },
    }


def board(parts=(), preset="", months=CHART_MONTHS):
    """화면 한 장. (외부 API 를 부르지 않는다 - 받아 둔 값만 읽는다)"""
    init_db()
    chosen = list(parts)
    if preset in PRESET_MAP and not chosen:
        chosen = list(PRESET_MAP[preset]["parts"])

    wanted = None
    if chosen:
        wanted = []
        for part in chosen:
            for key in PART_MAP.get(part, {}).get("materials", []):
                if key not in wanted:
                    wanted.append(key)

    cards = [material_view(m["key"], months) for m in MATERIALS
             if wanted is None or m["key"] in wanted]

    live = [c for c in cards if c["status"] in ("ok", "stale")]
    return {
        "cards": cards,
        "parts": PARTS,
        "presets": PRESETS,
        "selected_parts": chosen,
        "preset": preset,
        "months": months,
        "compare": compare_view([c["key"] for c in live], months),
        "sources": status_summary(),
        "counts": {
            "total": len(cards),
            "ok": sum(1 for c in cards if c["status"] == "ok"),
            "stale": sum(1 for c in cards if c["status"] == "stale"),
            "needs_key": sum(1 for c in cards if c["status"] == "needs_key"),
            "unsupported": sum(1 for c in cards if c["status"] == "unsupported"),
        },
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
        print("BLS   ", info["bls"]["meta"]["label"], "· 마지막 수집",
              info["bls"]["last_ok"] or "없음", "·", info["bls"]["message"])
        print("Metals", info["metals"]["meta"]["label"], "· 마지막 수집",
              info["metals"]["last_ok"] or "없음", "·", info["metals"]["message"])
        print("       이번 달 호출 {used}/{cap}회".format(**info["metals"]["quota"]))
        for card in board()["cards"]:
            latest = card.get("latest")
            print("  {:<12} {:<12} {}".format(
                card["name"], card["status_meta"]["label"],
                "{} ({})".format(latest["value"], latest["period"]) if latest else "-"))
        sys.exit()

    force = "--force" in sys.argv
    print("포장재 가격 동향 수집 (BLS {}계열 + 알루미늄)".format(len(BLS_SERIES)))
    result = collect(force=force, verbose=True)

    for key in ("bls", "metals"):
        part = result[key]
        if part.get("skipped"):
            print("  {} 건너뜀 - {}".format(key, part.get("reason", "")))

    print()
    for card in board()["cards"]:
        latest = card.get("latest")
        line = "  {:<12} {:<12}".format(card["name"], card["status_meta"]["label"])
        if latest:
            line += " {:>10,.3f}  기준 {}".format(latest["value"], latest["period"])
            if card["changes"]:
                line += "  " + " / ".join(
                    "{} {:+.1f}%".format(c["label"], c["pct"]) for c in card["changes"])
        elif card.get("message"):
            line += " " + card["message"][:60]
        print(line)
