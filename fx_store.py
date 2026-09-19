# -*- coding: utf-8 -*-
"""환율 조회 - 영업단가 계산의 견적환율.

견적환율을 손으로 적으면 두 가지가 늘 어긋난다.
  - 어제 값을 그대로 쓰다가 오늘 단가가 틀어진다
  - "그때 환율로 계산한 겁니다" 라고 말해도 그때가 언제인지 서로 다르게 안다

그래서 **어느 기관의, 언제 자 환율인지**를 값과 같이 들고 다닌다.

기준은 세 가지다.
  - 최근 고시   : 가장 최근 고시일의 환율
  - 특정 날짜   : 계약일·발주일·선적일 기준 (과거 날짜)
  - 기간 평균   : 그 기간에 실제 고시된 날만 평균 (월평균환율처럼 쓴다)

출처 두 곳:

  1) ECB 참고환율 (Frankfurter) - 키 없이 된다. 과거·시계열까지 준다
     https://frankfurter.dev/
     **은행 고시환율이 아니다.** 유럽중앙은행이 매 영업일 한 번 내는 참고값이다.

  2) 한국수출입은행 고시환율 - API 키 필요 (무료 신청)
     https://www.koreaexim.go.kr/ir/HPHKIR019M01
     실무에서 말하는 매매기준율·전신환매입률(TTB)이 여기서 나온다.

지켜야 할 것:
  - 화면을 열기만 할 때는 외부를 부르지 않는다. 받아 둔 값만 보여 준다
  - 고시가 없는 날(주말·공휴일)을 지어내지 않는다. 직전 영업일 값이라고 밝힌다
  - 고시일과 우리가 받아 온 시각을 따로 적는다
  - 평균은 실제 고시된 날만 평균 낸다. 빠진 날을 보간하지 않는다
  - 실패하면 0 이나 지어낸 값으로 채우지 않는다. 상태만 바꾼다
  - 월간·일간 참고환율을 "실시간 시세" 라고 부르지 않는다
  - API 키는 화면·로그·오류 메시지에 싣지 않는다

    python fx_store.py            # 오늘 자 환율을 미리 받아 둔다
    python fx_store.py --status   # 받아 둔 상태만 보기
"""

import json
import os
import sqlite3
import ssl
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
DB_PATH = os.path.join(DATA_DIR, "fx.db")

_local = threading.local()

USER_AGENT = "todo-trade-fx/1.0 (quotation exchange rate; educational prototype)"

ECB_BASE = "https://api.frankfurter.dev/v1/"
KEB_URL = "https://www.koreaexim.go.kr/site/program/financial/exchangeJSON"

# 가장 최근 고시를 다시 확인하는 주기.
#   ECB 는 유럽시간 16시께 하루 한 번, 수출입은행은 11시 이후 여러 차례 고시한다.
#   화면을 열 때마다 부르지 않으려고 세 시간 동안은 받아 둔 값을 쓴다.
LATEST_TTL_MIN = 180

# 수출입은행 한도는 하루 1,000회다. 다 쓰지 않고 여유를 남긴다.
KEB_DAILY_CAP = 300
# 주말·공휴일이면 직전 영업일을 찾아 거슬러 올라간다. 연휴를 생각해 열흘까지만.
WALK_BACK_DAYS = 10

# 이보다 앞선 날짜는 받아 봐야 비어 온다
ECB_MIN_DAY = date(1999, 1, 4)
KEB_MIN_DAY = date(2016, 1, 4)


# ---------------------------------------------------------------------------
# 출처
# ---------------------------------------------------------------------------

SOURCES = [
    {
        "key": "ecb",
        "label": "ECB 참고환율",
        "org": "유럽중앙은행 · Frankfurter",
        "env": "",
        "bases": ("latest", "date", "avg"),
        "note": "은행 고시환율이 아니라 중앙은행이 내는 참고값입니다. "
                "실제 입금 환율과는 차이가 납니다.",
        "link": "https://frankfurter.dev/",
    },
    {
        "key": "keb",
        "label": "한국수출입은행 고시환율",
        "org": "한국수출입은행",
        "env": "KOREAEXIM_API_KEY",
        # 하루치를 한 번에 주는 API 라 기간 평균을 내려면 날짜 수만큼 불러야 한다.
        # 한도를 그렇게 쓰지 않는다. 평균은 ECB 시계열로만 낸다.
        "bases": ("latest", "date"),
        "note": "실무에서 말하는 매매기준율입니다. 주말·공휴일에는 고시가 없습니다.",
        "link": "https://www.koreaexim.go.kr/ir/HPHKIR019M01",
    },
]
SOURCE_MAP = {row["key"]: row for row in SOURCES}
DEFAULT_SOURCE = "ecb"

BASES = [
    {"key": "latest", "label": "최근 고시", "desc": "가장 최근 고시일의 환율"},
    {"key": "date", "label": "특정 날짜", "desc": "계약일·발주일·선적일 기준"},
    {"key": "avg", "label": "기간 평균", "desc": "그 기간에 고시된 날만 평균"},
]
BASIS_MAP = {row["key"]: row for row in BASES}

AVG_PRESETS = [
    {"key": "m1", "label": "최근 1개월", "days": 30},
    {"key": "m3", "label": "최근 3개월", "days": 90},
    {"key": "m6", "label": "최근 6개월", "days": 180},
    {"key": "prev_month", "label": "전월 (1일~말일)", "days": 0},
    {"key": "custom", "label": "직접 지정", "days": 0},
]
AVG_MAP = {row["key"]: row for row in AVG_PRESETS}
DEFAULT_PRESET = "m1"


# ---------------------------------------------------------------------------
# 값의 상태
# ---------------------------------------------------------------------------
#   화면에 뜬 환율이 오늘 고시인지, 주말이라 금요일 값을 끌어온 건지,
#   손으로 적은 건지 구분이 안 되면 견적을 검증할 수가 없다.

RATE_STATES = {
    "quoted": {"label": "고시값", "css": "quoted",
               "desc": "요청한 날짜에 실제로 고시된 환율입니다"},
    "prev": {"label": "직전 영업일", "css": "prev",
             "desc": "그날은 고시가 없어(주말·공휴일) 직전 영업일 값을 가져왔습니다"},
    "avg": {"label": "기간 평균", "css": "avg",
            "desc": "기간 중 실제 고시된 날만 평균 낸 값입니다"},
    "fixed": {"label": "환산 없음", "css": "fixed",
              "desc": "원화로 결제하면 환산이 없습니다"},
    "manual": {"label": "수기 입력", "css": "manual",
               "desc": "담당자가 직접 적은 값입니다"},
    "builtin": {"label": "내장 기본값", "css": "builtin",
                "desc": "화면에 깔아 둔 값입니다. 조회해서 바꿔 쓰세요"},
    "nokey": {"label": "API 키 필요", "css": "off",
              "desc": ".env 에 키를 넣어야 이 출처를 쓸 수 있습니다"},
    "nodata": {"label": "고시 없음", "css": "off",
               "desc": "그 기간에 고시된 값을 찾지 못했습니다"},
    "error": {"label": "조회 실패", "css": "off",
              "desc": "외부 조회에 실패했습니다. 값을 지어내지 않고 비워 둡니다"},
}


def state_meta(key):
    return dict(RATE_STATES.get(key) or RATE_STATES["error"], key=key)


# ---------------------------------------------------------------------------
# 통화
# ---------------------------------------------------------------------------
#   수출입은행은 엔화를 100엔 단위로 고시한다. 그대로 쓰면 단가가 100배 틀어진다.
#   위안화는 코드가 CNH 다 (역외 위안).

KEB_CODE = {
    "USD": ("USD", 1),
    "EUR": ("EUR", 1),
    "JPY": ("JPY(100)", 100),
    "CNY": ("CNH", 1),
    "HKD": ("HKD", 1),
    "SGD": ("SGD", 1),
    "GBP": ("GBP", 1),
    "AUD": ("AUD", 1),
}
ECB_CODES = ("USD", "EUR", "JPY", "CNY", "HKD", "SGD", "GBP", "AUD")


def supports(source, currency):
    """그 출처가 이 통화를 주는가."""
    if currency == "KRW":
        return True
    if source == "keb":
        return currency in KEB_CODE
    return currency in ECB_CODES


# ---------------------------------------------------------------------------
# 저장소
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS rate (
    source     TEXT NOT NULL,
    currency   TEXT NOT NULL,
    day        TEXT NOT NULL,          -- 고시일 (YYYY-MM-DD)
    rate       REAL NOT NULL,          -- 원/1단위
    ttb        REAL,                   -- 전신환 매입률 (수출대금 받을 때)
    tts        REAL,                   -- 전신환 매도율
    fetched_at TEXT NOT NULL,          -- 우리가 받아 온 시각
    PRIMARY KEY (source, currency, day)
);

CREATE TABLE IF NOT EXISTS miss (
    source     TEXT NOT NULL,
    currency   TEXT NOT NULL,
    day        TEXT NOT NULL,          -- 물어봤는데 고시가 없던 날
    resolved   TEXT,                   -- 대신 쓴 직전 영업일 (없으면 빈칸)
    checked_at TEXT NOT NULL,
    PRIMARY KEY (source, currency, day)
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


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


def _now():
    return datetime.now(SEOUL)


def _today():
    return _now().date()


def _iso():
    return _now().replace(microsecond=0).isoformat()


def _meta_get(key):
    row = _conn().execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else ""


def _meta_set(key, value):
    conn = _conn()
    conn.execute("INSERT INTO meta (key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (key, value))
    conn.commit()


def _save_rate(source, currency, day, rate, ttb=None, tts=None):
    conn = _conn()
    conn.execute(
        "INSERT INTO rate (source, currency, day, rate, ttb, tts, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(source, currency, day) DO UPDATE SET "
        "rate = excluded.rate, ttb = excluded.ttb, tts = excluded.tts, "
        "fetched_at = excluded.fetched_at",
        (source, currency, day, float(rate), ttb, tts, _iso()))
    conn.commit()


def _read_rate(source, currency, day):
    return _conn().execute(
        "SELECT * FROM rate WHERE source = ? AND currency = ? AND day = ?",
        (source, currency, day)).fetchone()


def _save_miss(source, currency, day, resolved):
    conn = _conn()
    conn.execute(
        "INSERT INTO miss (source, currency, day, resolved, checked_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(source, currency, day) DO UPDATE SET "
        "resolved = excluded.resolved, checked_at = excluded.checked_at",
        (source, currency, day, resolved or "", _iso()))
    conn.commit()


def _read_miss(source, currency, day):
    return _conn().execute(
        "SELECT * FROM miss WHERE source = ? AND currency = ? AND day = ?",
        (source, currency, day)).fetchone()


# ---------------------------------------------------------------------------
# 날짜 도우미
# ---------------------------------------------------------------------------

def as_date(text):
    """YYYY-MM-DD 를 날짜로. 못 읽으면 None."""
    text = (text or "").strip()[:10]
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _ymd(day):
    return day.strftime("%Y-%m-%d")


def prev_month_range(today=None):
    """전월 1일 ~ 말일."""
    today = today or _today()
    last = today.replace(day=1) - timedelta(days=1)
    return last.replace(day=1), last


def resolve_range(preset, start=None, end=None, today=None):
    """기간 평균에서 쓸 시작·끝 날짜를 정한다."""
    today = today or _today()
    preset = preset if preset in AVG_MAP else DEFAULT_PRESET

    if preset == "custom":
        s = as_date(start) or (today - timedelta(days=30))
        e = as_date(end) or today
    elif preset == "prev_month":
        s, e = prev_month_range(today)
    else:
        s = today - timedelta(days=AVG_MAP[preset]["days"])
        e = today

    if e > today:
        e = today
    if s > e:
        s = e
    if s < ECB_MIN_DAY:
        s = ECB_MIN_DAY
    # 너무 긴 기간은 응답이 커진다. 3년까지만 받는다.
    if (e - s).days > 1100:
        s = e - timedelta(days=1100)
    return s, e


# ---------------------------------------------------------------------------
# 외부 조회
# ---------------------------------------------------------------------------

class FxError(Exception):
    """조회 실패. 메시지는 화면에 그대로 뜨므로 키를 싣지 않는다."""


def _get_json(url, timeout=12):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise FxError("그 날짜의 자료가 없습니다.")
        raise FxError("조회에 실패했습니다 (HTTP {}).".format(exc.code))
    except ssl.SSLError:
        # 인증서 검증은 끄지 않는다. 끄면 중간에서 값을 바꿔치기해도 모른다.
        raise FxError("인증서 검증에 실패했습니다. 검증을 끄지 않고 그대로 뒀습니다.")
    except urllib.error.URLError as exc:
        raise FxError("서버에 닿지 못했습니다 ({}).".format(
            getattr(exc, "reason", "연결 실패")))
    except Exception:                                # noqa: BLE001
        raise FxError("조회 중 오류가 났습니다.")

    try:
        return json.loads(raw)
    except ValueError:
        raise FxError("받은 응답을 읽지 못했습니다.")


# --- ECB (Frankfurter) -----------------------------------------------------

def _ecb_day(currency, day):
    """하루치. 그날 고시가 없으면 직전 영업일 것을 돌려준다.

    Frankfurter 는 주말·공휴일을 물으면 직전 영업일 값을 주면서
    `date` 에 그 영업일을 적어 준다. 그래서 요청일과 응답일을 비교하면
    "그날 고시가 있었는지" 를 알 수 있다.
    """
    url = "{}{}?base={}&symbols=KRW".format(ECB_BASE, _ymd(day), currency)
    data = _get_json(url)
    rates = (data or {}).get("rates") or {}
    value = rates.get("KRW")
    got = as_date((data or {}).get("date"))
    if not value or not got:
        raise FxError("환율 값이 비어 있습니다.")
    return got, float(value)


def _ecb_range(currency, start, end):
    """기간. 고시된 날만 들어 있다 (주말·공휴일은 애초에 없다).

    시작일이 주말이면 그 앞 영업일이 하나 딸려 온다.
    8월 1일이 토요일이면 7월 31일이 같이 온다. 그대로 평균 내면
    "8월 평균" 에 7월이 섞인다. 받아서 저장은 하되, 평균은 SQL 에서
    날짜로 걸러 낸 것만 쓴다 (_average 의 day >= ? AND day <= ?).
    """
    url = "{}{}..{}?base={}&symbols=KRW".format(
        ECB_BASE, _ymd(start), _ymd(end), currency)
    data = _get_json(url, timeout=20)
    rates = (data or {}).get("rates") or {}
    out = []
    for key in sorted(rates):
        value = (rates[key] or {}).get("KRW")
        if value:
            out.append((key, float(value)))
    if not out:
        raise FxError("그 기간에 고시된 값이 없습니다.")
    return out


# --- 한국수출입은행 --------------------------------------------------------

def keb_ready():
    return bool(app_env.get("KOREAEXIM_API_KEY"))


def _keb_calls_today():
    return int(_meta_get("keb:calls:" + _ymd(_today())) or 0)


def _keb_count():
    key = "keb:calls:" + _ymd(_today())
    _meta_set(key, str(int(_meta_get(key) or 0) + 1))


def _keb_day(currency, day):
    """하루치 고시. 고시가 없는 날이면 None 을 돌려준다 (예외가 아니다)."""
    auth = app_env.get("KOREAEXIM_API_KEY")
    if not auth:
        raise FxError("API 키가 없습니다.")
    if _keb_calls_today() >= KEB_DAILY_CAP:
        raise FxError("오늘 조회 한도({}회)를 다 썼습니다. 내일 다시 받습니다."
                      .format(KEB_DAILY_CAP))

    url = "{}?{}".format(KEB_URL, urllib.parse.urlencode({
        "authkey": auth, "searchdate": day.strftime("%Y%m%d"), "data": "AP01",
    }))
    _keb_count()
    data = _get_json(url, timeout=15)

    if not isinstance(data, list):
        raise FxError("받은 응답을 읽지 못했습니다.")
    if not data:
        return None                     # 주말·공휴일, 또는 그날 고시 전(11시 이전)

    code, divisor = KEB_CODE.get(currency, (currency, 1))
    for row in data:
        result = row.get("result")
        if result == 3:
            raise FxError("API 키가 올바르지 않습니다. .env 를 확인해 주세요.")
        if result == 4:
            raise FxError("일일 조회 한도를 넘었습니다.")
        if row.get("cur_unit") != code:
            continue

        def _num(name):
            text = str(row.get(name) or "").replace(",", "").strip()
            try:
                return float(text) / divisor
            except ValueError:
                return None

        base = _num("deal_bas_r")
        if not base:
            raise FxError("매매기준율이 비어 있습니다.")
        return base, _num("ttb"), _num("tts")

    raise FxError("{} 고시가 응답에 없습니다.".format(currency))


# ---------------------------------------------------------------------------
# 하루치 가져오기 (받아 둔 값 우선)
# ---------------------------------------------------------------------------

def _day_rate(source, currency, day, allow_network=True):
    """하루치를 돌려준다. (고시일, 값, ttb, tts) 또는 None.

    고시일이 요청일과 다르면 주말·공휴일이라 거슬러 올라간 것이다.
    """
    key = _ymd(day)

    row = _read_rate(source, currency, key)
    if row:
        return key, row["rate"], row["ttb"], row["tts"]

    seen = _read_miss(source, currency, key)
    if seen and seen["resolved"]:
        got = _read_rate(source, currency, seen["resolved"])
        if got:
            return seen["resolved"], got["rate"], got["ttb"], got["tts"]

    if not allow_network:
        return None

    if source == "ecb":
        got, value = _ecb_day(currency, day)
        _save_rate("ecb", currency, _ymd(got), value)
        if got != day:
            _save_miss("ecb", currency, key, _ymd(got))
        return _ymd(got), value, None, None

    # 수출입은행은 없는 날에 빈 배열을 준다. 직전 영업일을 찾아 거슬러 올라간다.
    for back in range(WALK_BACK_DAYS + 1):
        here = day - timedelta(days=back)
        if here < KEB_MIN_DAY:
            break
        cached = _read_rate("keb", currency, _ymd(here))
        if cached:
            found = (cached["rate"], cached["ttb"], cached["tts"])
        else:
            found = _keb_day(currency, here)
            if found:
                _save_rate("keb", currency, _ymd(here), found[0], found[1], found[2])
        if found:
            if here != day:
                _save_miss("keb", currency, key, _ymd(here))
            return _ymd(here), found[0], found[1], found[2]
        _save_miss("keb", currency, _ymd(here), "")
    return None


# ---------------------------------------------------------------------------
# 조회
# ---------------------------------------------------------------------------

def _blank(currency, source, basis, state, message):
    """값을 못 구했을 때. 0 이나 지어낸 숫자를 넣지 않는다."""
    return {
        "ok": False,
        "currency": currency,
        "source": source,
        "source_label": (SOURCE_MAP.get(source) or {}).get("label", source),
        "basis": basis,
        "basis_label": (BASIS_MAP.get(basis) or {}).get("label", basis),
        "rate": None,
        "state": state,
        "state_meta": state_meta(state),
        "day": "",
        "label": RATE_STATES[state]["label"],
        "message": message,
        "detail": [],
        "series": [],
        "fetched_at": "",
    }


def lookup(currency, source=DEFAULT_SOURCE, basis="latest", day="",
           preset=DEFAULT_PRESET, start="", end="", allow_network=True):
    """견적환율 한 건.

    allow_network=False 면 받아 둔 값만 본다. 화면을 여는 것만으로
    외부 API 를 부르지 않으려고 쓴다.
    """
    currency = (currency or "").strip().upper()[:3]
    source = source if source in SOURCE_MAP else DEFAULT_SOURCE
    basis = basis if basis in BASIS_MAP else "latest"
    meta = SOURCE_MAP[source]

    # 원화 결제는 환산 자체가 없다. 외부를 부를 이유도 없다.
    if currency == "KRW":
        out = _blank(currency, source, basis, "fixed", "원화로 결제하면 환산이 없습니다.")
        out.update(ok=True, rate=1.0, label="1 : 1")
        return out

    if not supports(source, currency):
        return _blank(currency, source, basis, "nodata",
                      "{} 은 {} 를 고시하지 않습니다.".format(meta["label"], currency))

    if basis not in meta["bases"]:
        return _blank(currency, source, basis, "nodata",
                      "{} 은 '{}' 기준을 지원하지 않습니다.".format(
                          meta["label"], BASIS_MAP[basis]["label"]))

    if source == "keb" and not keb_ready():
        return _blank(currency, source, basis, "nokey",
                      "한국수출입은행 API 키가 없습니다. "
                      ".env 에 KOREAEXIM_API_KEY 를 넣어 주세요.")

    if basis == "avg":
        return _average(currency, source, preset, start, end, allow_network)
    return _single(currency, source, basis, day, allow_network)


def _single(currency, source, basis, day, allow_network):
    """최근 고시 / 특정 날짜."""
    meta = SOURCE_MAP[source]
    today = _today()

    if basis == "latest":
        want = today
    else:
        want = as_date(day)
        if not want:
            return _blank(currency, source, basis, "nodata",
                          "날짜를 YYYY-MM-DD 로 넣어 주세요.")
        if want > today:
            return _blank(currency, source, basis, "nodata",
                          "아직 오지 않은 날짜입니다. 미래 환율은 알 수 없습니다.")
        floor = KEB_MIN_DAY if source == "keb" else ECB_MIN_DAY
        if want < floor:
            return _blank(currency, source, basis, "nodata",
                          "{} 이전 자료는 받아 오지 않습니다.".format(_ymd(floor)))

    # 최근 고시는 세 시간 동안 받아 둔 값을 쓴다 (화면을 열 때마다 부르지 않으려고)
    fresh_key = "latest:{}:{}".format(source, currency)
    if basis == "latest" and allow_network:
        try:
            stamp = json.loads(_meta_get(fresh_key) or "{}")
        except ValueError:
            stamp = {}
        at = stamp.get("at")
        if at:
            try:
                age = (_now() - datetime.fromisoformat(at)).total_seconds() / 60
                if age < LATEST_TTL_MIN and _read_rate(source, currency, stamp.get("day", "")):
                    allow_network = False
            except ValueError:
                pass

    got = None
    error = ""
    try:
        got = _day_rate(source, currency, want, allow_network)
    except FxError as exc:
        error = str(exc)

    if not got:
        if basis == "latest" and not allow_network:
            # 받아 둔 값 중 가장 최근 것이라도 보여 준다
            row = _conn().execute(
                "SELECT * FROM rate WHERE source = ? AND currency = ? "
                "ORDER BY day DESC LIMIT 1", (source, currency)).fetchone()
            if row:
                got = (row["day"], row["rate"], row["ttb"], row["tts"])
        if not got:
            if error:
                return _blank(currency, source, basis, "error", error)
            return _blank(currency, source, basis, "nodata",
                          "아직 받아 둔 환율이 없습니다. '환율 불러오기'를 눌러 주세요.")

    quoted_day, value, ttb, tts = got
    if basis == "latest":
        _meta_set(fresh_key, json.dumps({"day": quoted_day, "at": _iso()}))

    state = "quoted" if (basis == "latest" or quoted_day == _ymd(want)) else "prev"
    row = _read_rate(source, currency, quoted_day)

    detail = ["{} · {} 고시".format(meta["label"], quoted_day)]
    if state == "prev":
        detail.append("{} 은 고시가 없어(주말·공휴일) 직전 영업일 값을 가져왔습니다."
                      .format(_ymd(want)))
    if ttb:
        detail.append("전신환 매입률(TTB) {:,.2f}원 · 매도율(TTS) {:,.2f}원"
                      .format(ttb, tts or 0))
        detail.append("수출대금은 매매기준율이 아니라 TTB 로 들어옵니다. "
                      "입금액을 따질 때는 TTB 를 보세요.")
    if source == "ecb":
        detail.append("은행 고시환율이 아니라 중앙은행 참고환율입니다.")
    if currency == "JPY":
        detail.append("시장은 100엔 단위로 고시하지만 여기서는 1엔 기준으로 적습니다.")

    return {
        "ok": True,
        "currency": currency,
        "source": source,
        "source_label": meta["label"],
        "basis": basis,
        "basis_label": BASIS_MAP[basis]["label"],
        "rate": round(value, 4),
        "ttb": round(ttb, 4) if ttb else None,
        "tts": round(tts, 4) if tts else None,
        "state": state,
        "state_meta": state_meta(state),
        "day": quoted_day,
        "label": "{} 고시".format(quoted_day),
        "message": "",
        "detail": detail,
        "series": [],
        "fetched_at": row["fetched_at"] if row else "",
    }


def _average(currency, source, preset, start, end, allow_network):
    """기간 평균. 고시된 날만 평균 낸다. 빠진 날을 채우지 않는다."""
    meta = SOURCE_MAP[source]
    s, e = resolve_range(preset, start, end)

    marker = "range:{}:{}:{}:{}".format(source, currency, _ymd(s), _ymd(e))
    fresh = _meta_get(marker)
    if not fresh:
        need = True
    elif e < _today():
        # 지나간 기간은 값이 더 바뀌지 않는다. 다시 받을 이유가 없다
        need = False
    else:
        # 오늘까지 걸친 기간은 새 고시가 붙는다. 주기만큼 지났으면 다시 받는다
        try:
            need = (_now() - datetime.fromisoformat(fresh)).total_seconds() / 60 >= LATEST_TTL_MIN
        except ValueError:
            need = True

    error = ""
    # 기간 평균을 지원하는 출처는 시계열을 주는 ECB 뿐이다 (SOURCES 의 bases 로 막아 둔다)
    if need and allow_network and source == "ecb":
        try:
            for key, value in _ecb_range(currency, s, e):
                _save_rate(source, currency, key, value)
            _meta_set(marker, _iso())
        except FxError as exc:
            error = str(exc)

    rows = _conn().execute(
        "SELECT day, rate FROM rate WHERE source = ? AND currency = ? "
        "AND day >= ? AND day <= ? ORDER BY day",
        (source, currency, _ymd(s), _ymd(e))).fetchall()

    if not rows:
        if error:
            return _blank(currency, source, "avg", "error", error)
        return _blank(currency, source, "avg", "nodata",
                      "그 기간에 받아 둔 고시가 없습니다. '환율 불러오기'를 눌러 주세요.")

    values = [row["rate"] for row in rows]
    avg = sum(values) / len(values)
    low = min(values)
    high = max(values)

    # 영업일이 얼추 몇 날이어야 하는지. 절반도 안 되면 그렇다고 밝힌다.
    weekdays = sum(1 for i in range((e - s).days + 1)
                   if (s + timedelta(days=i)).weekday() < 5)
    thin = weekdays and len(rows) < weekdays * 0.6

    detail = [
        "{} · {} ~ {}".format(meta["label"], rows[0]["day"], rows[-1]["day"]),
        "이 기간에 고시된 {}일치를 평균했습니다 (주말·공휴일은 애초에 고시가 없습니다).".format(len(rows)),
        "기간 중 최저 {:,.2f}원 · 최고 {:,.2f}원 (차이 {:,.2f}원)".format(
            low, high, high - low),
        "빠진 날을 채워 넣지 않았습니다. 보간도 하지 않습니다.",
    ]
    if thin:
        detail.append("평일 {}일 중 {}일치뿐입니다. 아직 덜 받아 왔을 수 있습니다."
                      .format(weekdays, len(rows)))
    if error:
        detail.append("최신분을 더 받아 오지 못했습니다: " + error)
    detail.append("평균환율은 실제 입금 환율이 아닙니다. "
                  "단가를 잡는 기준으로만 쓰고, 정산은 입금일 환율로 다시 보세요.")

    label = AVG_MAP.get(preset, AVG_MAP[DEFAULT_PRESET])["label"]

    return {
        "ok": True,
        "currency": currency,
        "source": source,
        "source_label": meta["label"],
        "basis": "avg",
        "basis_label": BASIS_MAP["avg"]["label"],
        "rate": round(avg, 4),
        "ttb": None,
        "tts": None,
        "state": "avg",
        "state_meta": state_meta("avg"),
        "day": "{} ~ {}".format(rows[0]["day"], rows[-1]["day"]),
        "label": "{} 평균 ({}일)".format(label, len(rows)),
        "message": "",
        "detail": detail,
        "days": len(rows),
        "low": round(low, 4),
        "high": round(high, 4),
        "start": _ymd(s),
        "end": _ymd(e),
        # 화면에 추세선을 그릴 만큼만 (너무 길면 응답이 커진다)
        "series": [{"day": row["day"], "rate": round(row["rate"], 4)}
                   for row in rows[-90:]],
        "fetched_at": _meta_get(marker),
    }


# ---------------------------------------------------------------------------
# 화면에 내려보낼 선택지
# ---------------------------------------------------------------------------

def options():
    """출처·기준 목록. 쓸 수 있는지까지 같이 내려준다."""
    rows = []
    for meta in SOURCES:
        ready = True
        why = ""
        if meta["env"] and not app_env.has(meta["env"]):
            ready = False
            why = "{} 를 .env 에 넣어야 켜집니다".format(meta["env"])
        rows.append({
            "key": meta["key"],
            "label": meta["label"],
            "org": meta["org"],
            "note": meta["note"],
            "link": meta["link"],
            "bases": list(meta["bases"]),
            "ready": ready,
            "why": why,
            # 키 값은 내려보내지 않는다. 설정됐는지만 적는다.
            "key_state": app_env.masked(meta["env"]) if meta["env"] else "",
        })
    return {
        "sources": rows,
        "bases": [dict(row) for row in BASES],
        "presets": [dict(row) for row in AVG_PRESETS],
        "default_source": DEFAULT_SOURCE,
        "default_preset": DEFAULT_PRESET,
        "today": _ymd(_today()),
        "states": {key: dict(value, key=key) for key, value in RATE_STATES.items()},
    }


def status():
    """받아 둔 상태."""
    rows = _conn().execute(
        "SELECT source, currency, COUNT(*) AS n, MAX(day) AS last "
        "FROM rate GROUP BY source, currency ORDER BY source, currency").fetchall()
    return {
        "db": DB_PATH,
        "rows": [dict(row) for row in rows],
        "keb_ready": keb_ready(),
        "keb_calls_today": _keb_calls_today(),
        "keb_cap": KEB_DAILY_CAP,
    }


def warm(currencies=ECB_CODES):
    """오늘 자 환율을 미리 받아 둔다 (화면이 기다리지 않게)."""
    done = []
    for code in currencies:
        got = lookup(code, "ecb", "latest")
        done.append((code, got["rate"], got["day"], got["state"]))
        if keb_ready():
            got = lookup(code, "keb", "latest")
            done.append((code, got["rate"], got["day"], got["state"]))
    return done


if __name__ == "__main__":
    if "--status" in sys.argv:
        info = status()
        print("DB:", info["db"])
        for row in info["rows"]:
            print("  {source:5} {currency}  {n:4}일치  마지막 {last}".format(**row))
        print("수출입은행 키:", "설정됨" if info["keb_ready"] else "없음",
              "· 오늘 {}/{}회".format(info["keb_calls_today"], info["keb_cap"]))
    else:
        for code, value, day, state in warm():
            print("{:4} {:>12}  {}  {}".format(
                code, value if value is not None else "—", day or "—", state))
