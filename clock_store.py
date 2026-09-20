# -*- coding: utf-8 -*-
"""바이어 현지 시간과 공휴일.

메일을 새벽 3시에 보내면 아침에 받은 메일 더미 맨 밑에 깔린다.
전화는 아예 못 건다. 그런데 매번 시차를 세는 건 번거롭고,
서머타임 때문에 "미국은 13시간" 같은 암기가 1년에 두 번 틀린다.

그래서 **세지 않고 보여 준다.** `zoneinfo` 가 서머타임까지 알아서 본다.

공휴일은 다르다. 계산으로 안 나오고 나라마다 매년 바뀐다.
  출처: Nager.Date (https://date.nager.at) - 공개 API, 키 불필요

지켜야 할 것:
  - 화면을 열 때마다 외부를 부르지 않는다. 연 단위로 받아 둔다
  - **지역 공휴일을 전국 공휴일이라고 말하지 않는다.**
    독일 세계 어린이날은 튀링겐 주에서만 쉰다. 그걸 "독일 휴일" 이라고 적으면
    베를린 바이어에게 "오늘 쉬시죠?" 라고 헛소리를 하게 된다
  - 나라를 모르면 시간을 지어내지 않는다. 비워 둔다
  - 업무시간은 통상값(09~18시)이다. 그 회사 실제 근무시간이 아니다
"""

import json
import os
import sqlite3
import sys
import threading
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except Exception:                                    # noqa: BLE001
    ZoneInfo = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "holidays.db")

_local = threading.local()

USER_AGENT = "todo-trade-clock/1.0 (overseas sales prototype)"
NAGER = "https://date.nager.at/api/v3"

SEOUL = ZoneInfo("Asia/Seoul") if ZoneInfo else timezone(timedelta(hours=9))

# 통상 업무시간. **그 회사의 실제 근무시간이 아니다.**
WORK_START = 9
WORK_END = 18


# ---------------------------------------------------------------------------
# 나라 -> 시간대 · 국가코드
# ---------------------------------------------------------------------------
#   화장품 수출에서 실제로 자주 나오는 나라만 적는다.
#   미국·중국처럼 시간대가 여러 개인 나라는 **가장 거래가 잦은 쪽**을 쓰고
#   화면에 어느 도시 기준인지 적는다. 그래야 "동부인데 왜 서부 시간?" 이 안 나온다.

COUNTRIES = {
    "미국": {"tz": "America/Los_Angeles", "code": "US", "city": "로스앤젤레스",
             "note": "미국은 시간대가 여러 개입니다. 서부(PT) 기준으로 보여 줍니다"},
    "캐나다": {"tz": "America/Toronto", "code": "CA", "city": "토론토"},
    "멕시코": {"tz": "America/Mexico_City", "code": "MX", "city": "멕시코시티"},
    "브라질": {"tz": "America/Sao_Paulo", "code": "BR", "city": "상파울루"},
    "EU": {"tz": "Europe/Brussels", "code": "BE", "city": "브뤼셀",
           "note": "EU는 나라마다 시간대·휴일이 다릅니다. 중부유럽 기준입니다"},
    "프랑스": {"tz": "Europe/Paris", "code": "FR", "city": "파리"},
    "독일": {"tz": "Europe/Berlin", "code": "DE", "city": "베를린"},
    "이탈리아": {"tz": "Europe/Rome", "code": "IT", "city": "로마"},
    "스페인": {"tz": "Europe/Madrid", "code": "ES", "city": "마드리드"},
    "네덜란드": {"tz": "Europe/Amsterdam", "code": "NL", "city": "암스테르담"},
    "폴란드": {"tz": "Europe/Warsaw", "code": "PL", "city": "바르샤바"},
    "영국": {"tz": "Europe/London", "code": "GB", "city": "런던"},
    "러시아": {"tz": "Europe/Moscow", "code": "RU", "city": "모스크바"},
    "튀르키예": {"tz": "Europe/Istanbul", "code": "TR", "city": "이스탄불"},
    "중국": {"tz": "Asia/Shanghai", "code": "CN", "city": "상하이"},
    "홍콩": {"tz": "Asia/Hong_Kong", "code": "HK", "city": "홍콩"},
    "대만": {"tz": "Asia/Taipei", "code": "TW", "city": "타이베이"},
    "일본": {"tz": "Asia/Tokyo", "code": "JP", "city": "도쿄"},
    "베트남": {"tz": "Asia/Ho_Chi_Minh", "code": "VN", "city": "호찌민"},
    "태국": {"tz": "Asia/Bangkok", "code": "TH", "city": "방콕"},
    "싱가포르": {"tz": "Asia/Singapore", "code": "SG", "city": "싱가포르"},
    "말레이시아": {"tz": "Asia/Kuala_Lumpur", "code": "MY", "city": "쿠알라룸푸르"},
    "인도네시아": {"tz": "Asia/Jakarta", "code": "ID", "city": "자카르타"},
    "필리핀": {"tz": "Asia/Manila", "code": "PH", "city": "마닐라"},
    "인도": {"tz": "Asia/Kolkata", "code": "IN", "city": "뭄바이"},
    "호주": {"tz": "Australia/Sydney", "code": "AU", "city": "시드니"},
    "뉴질랜드": {"tz": "Pacific/Auckland", "code": "NZ", "city": "오클랜드"},
    "아랍에미리트": {"tz": "Asia/Dubai", "code": "AE", "city": "두바이"},
    "사우디아라비아": {"tz": "Asia/Riyadh", "code": "SA", "city": "리야드"},
    "이스라엘": {"tz": "Asia/Jerusalem", "code": "IL", "city": "텔아비브"},
    "대한민국": {"tz": "Asia/Seoul", "code": "KR", "city": "서울"},
    "한국": {"tz": "Asia/Seoul", "code": "KR", "city": "서울"},
}

# 업무 상태
STATES = {
    "work": {"label": "업무 시간", "css": "work", "icon": "🟢"},
    "early": {"label": "아직 출근 전", "css": "early", "icon": "🌙"},
    "late": {"label": "퇴근 뒤", "css": "late", "icon": "🌙"},
    "weekend": {"label": "주말", "css": "off", "icon": "🛌"},
    "holiday": {"label": "공휴일", "css": "off", "icon": "🎌"},
    "unknown": {"label": "국가 미확인", "css": "none", "icon": "—"},
}


SCHEMA = """
CREATE TABLE IF NOT EXISTS holiday (
    code       TEXT NOT NULL,
    year       INTEGER NOT NULL,
    day        TEXT NOT NULL,
    name       TEXT NOT NULL,
    local_name TEXT NOT NULL DEFAULT '',
    nationwide INTEGER NOT NULL DEFAULT 1,   -- 0 이면 일부 지역만 쉰다
    counties   TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (code, day, name)
);

CREATE TABLE IF NOT EXISTS fetched (
    code       TEXT NOT NULL,
    year       INTEGER NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, year)
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


def init_db():
    _conn()


def country_of(name):
    """국가 이름을 표에서 찾는다. 못 찾으면 None (시간을 지어내지 않는다)."""
    text = (name or "").strip()
    if not text:
        return None
    if text in COUNTRIES:
        return dict(COUNTRIES[text], country=text)
    # "미국(1차) → EU(확장 예정)" 처럼 적혀 오는 자리가 있다
    for key, row in COUNTRIES.items():
        if key in text:
            return dict(row, country=key)
    return None


# ---------------------------------------------------------------------------
# 공휴일
# ---------------------------------------------------------------------------

def fetch_holidays(code, year, force=False):
    """한 나라·한 해를 받아 둔다. 실패하면 이전 값을 지우지 않는다."""
    conn = _conn()
    if not force:
        row = conn.execute("SELECT 1 FROM fetched WHERE code = ? AND year = ?",
                           (code, year)).fetchone()
        if row:
            return 0

    url = "{}/PublicHolidays/{}/{}".format(NAGER, year, code)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as res:
            rows = json.loads(res.read().decode("utf-8"))
    except Exception:                                # noqa: BLE001
        return 0                                     # 조용히 넘어간다. 없으면 없는 대로

    made = 0
    for row in rows or []:
        conn.execute(
            "INSERT OR REPLACE INTO holiday "
            "(code, year, day, name, local_name, nationwide, counties) "
            "VALUES (?,?,?,?,?,?,?)",
            (code, year, row.get("date", ""), row.get("name", ""),
             row.get("localName", ""),
             1 if row.get("global") else 0,
             ", ".join(row.get("counties") or [])))
        made += 1
    conn.execute("INSERT OR REPLACE INTO fetched (code, year, fetched_at) "
                 "VALUES (?,?,?)",
                 (code, year, datetime.now(SEOUL).strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    return made


def holidays_between(code, start, end):
    return [dict(r) for r in _conn().execute(
        "SELECT * FROM holiday WHERE code = ? AND day >= ? AND day <= ? "
        "ORDER BY day", (code, start.isoformat(), end.isoformat()))]


# ---------------------------------------------------------------------------
# 지금 몇 시인가
# ---------------------------------------------------------------------------

def now_for(country_name, fetch=False):
    """그 나라 현지 시각과 업무 상태. 나라를 모르면 None."""
    meta = country_of(country_name)
    if not meta or ZoneInfo is None:
        return None

    try:
        tz = ZoneInfo(meta["tz"])
    except Exception:                                # noqa: BLE001
        return None

    here = datetime.now(SEOUL)
    there = datetime.now(tz)

    # 시차는 날짜가 갈리는 경우가 있어 분 단위로 계산한다
    gap_min = round((there.utcoffset() - here.utcoffset()).total_seconds() / 60)
    gap_h = gap_min / 60.0

    if fetch:
        fetch_holidays(meta["code"], there.year)
        if there.month == 12:
            fetch_holidays(meta["code"], there.year + 1)

    today = there.date()
    rows = holidays_between(meta["code"], today, today + timedelta(days=45))
    today_rows = [r for r in rows if r["day"] == today.isoformat()]
    # 전국 휴일과 지역 휴일을 가른다. 지역 휴일로 "오늘 쉬시죠?" 하면 헛소리다
    today_national = [r for r in today_rows if r["nationwide"]]
    upcoming = [r for r in rows if r["day"] > today.isoformat()][:3]

    if today_national:
        state = "holiday"
    elif there.weekday() >= 5:
        state = "weekend"
    elif there.hour < WORK_START:
        state = "early"
    elif there.hour >= WORK_END:
        state = "late"
    else:
        state = "work"

    if state == "work":
        advice = "지금 보내면 오늘 안에 읽습니다."
    elif state == "early":
        advice = "아직 출근 전입니다. {}시쯤 열립니다.".format(WORK_START)
    elif state == "late":
        advice = "퇴근 뒤입니다. 지금 보내면 내일 아침 메일 더미에 깔립니다."
    elif state == "weekend":
        advice = "주말입니다. 월요일 아침에 읽습니다."
    else:
        advice = "{} 입니다. 오늘은 응답을 기대하기 어렵습니다.".format(
            today_national[0]["local_name"] or today_national[0]["name"])

    return {
        "country": meta["country"],
        "city": meta["city"],
        "tz": meta["tz"],
        "note": meta.get("note", ""),
        "time": there.strftime("%H:%M"),
        "date": there.strftime("%Y-%m-%d"),
        "weekday": ["월", "화", "수", "목", "금", "토", "일"][there.weekday()],
        "gap": gap_h,
        "gap_label": _gap_label(gap_h),
        "state": state,
        "state_meta": dict(STATES[state], key=state),
        "advice": advice,
        "today_holidays": today_rows,
        "today_national": today_national,
        # 지역만 쉬는 날. 전국 휴일과 따로 적는다
        "today_local_only": [r for r in today_rows if not r["nationwide"]],
        "upcoming": upcoming,
        "best_window": _best_window(tz, here),
    }


def _gap_label(gap):
    if abs(gap) < 0.01:
        return "시차 없음"
    sign = "빠름" if gap > 0 else "느림"
    value = abs(gap)
    text = "{:g}".format(value)
    return "한국보다 {}시간 {}".format(text, sign)


def _best_window(tz, here):
    """한국 시각으로 몇 시에 보내면 현지 업무시간에 닿나.

    하루치만 세면 시차가 큰 나라에서 빈칸이 나온다.
    한국 월요일 하루를 아무리 훑어도 로스앤젤레스는 계속 일요일이다.
    (시차 16시간이라 한국 화요일 새벽이 되어야 LA 월요일 오전에 닿는다)
    그래서 **이틀치**를 훑고, 한국 날짜가 넘어가면 그렇게 적는다.
    """
    day = here.date()
    while day.weekday() >= 5:
        day += timedelta(days=1)

    hits = []
    for offset in range(48):
        moment = (datetime(day.year, day.month, day.day, 0, tzinfo=here.tzinfo)
                  + timedelta(hours=offset))
        local = moment.astimezone(tz)
        if local.weekday() < 5 and WORK_START <= local.hour < WORK_END:
            hits.append(offset)
    if not hits:
        return ""

    # 이어진 구간 중 가장 긴 것
    runs, run = [], [hits[0]]
    for offset in hits[1:]:
        if offset == run[-1] + 1:
            run.append(offset)
        else:
            runs.append(run)
            run = [offset]
    runs.append(run)
    best = max(runs, key=len)

    start_h, end_h = best[0] % 24, (best[-1] + 1) % 24
    text = "한국 {:02d}시~{:02d}시".format(start_h, end_h)
    if best[0] >= 24:
        text += " (다음 날)"
    elif best[-1] + 1 > 24:
        text += " (끝은 다음 날)"
    return text


def warm(names):
    """쓰는 나라의 공휴일을 미리 받아 둔다."""
    year = datetime.now(SEOUL).year
    done = []
    for name in names:
        meta = country_of(name)
        if not meta:
            continue
        made = fetch_holidays(meta["code"], year)
        made += fetch_holidays(meta["code"], year + 1)
        done.append((meta["country"], meta["code"], made))
    return done


if __name__ == "__main__":
    init_db()
    names = sys.argv[1:] or list(COUNTRIES)
    for country, code, made in warm(names):
        print("{:10} {}  {}건".format(country, code, made))
