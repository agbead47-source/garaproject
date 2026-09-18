# -*- coding: utf-8 -*-
"""신규 바이어 발굴 - 상수, 검증, 공용 헬퍼.

명세 8절(적합도)·5.2절(수집 안전)·4.5절(단계)을 여기에 모아 둔다.
"""

import ipaddress
import re
import socket
import urllib.parse
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
    SEOUL = ZoneInfo("Asia/Seoul")
except Exception:                                    # noqa: BLE001
    SEOUL = timezone.utc

TIMEZONE_LABEL = "Asia/Seoul"

# ---------------------------------------------------------------------------
# 영업 단계 (명세 4.5)
# ---------------------------------------------------------------------------

STAGES = [
    {"value": "discovered", "label": "후보 발굴", "order": 1},
    {"value": "researched", "label": "조사 완료", "order": 2},
    {"value": "contacted", "label": "첫 연락", "order": 3},
    {"value": "replied", "label": "회신", "order": 4},
    {"value": "meeting", "label": "상담", "order": 5},
    {"value": "sample_quote", "label": "샘플·견적", "order": 6},
    {"value": "won", "label": "수주", "order": 7},
]

# 진행 단계와 별개로 관리하는 상태
SIDE_STAGES = [
    {"value": "on_hold", "label": "보류", "order": 0},
    {"value": "closed", "label": "종료", "order": 0},
]

ALL_STAGES = STAGES + SIDE_STAGES
STAGE_LABELS = {row["value"]: row["label"] for row in ALL_STAGES}
STAGE_ORDER = {row["value"]: row["order"] for row in ALL_STAGES}

CONTACTED_ORDER = 3      # '첫 연락' 이상이면 접촉한 것으로 본다
MEETING_ORDER = 5        # '상담' 이상이면 상담에 도달한 것으로 본다


# ---------------------------------------------------------------------------
# 분류
# ---------------------------------------------------------------------------

BUSINESS_TYPES = [
    {"value": "brand", "label": "브랜드사"},
    {"value": "manufacturer", "label": "제조사"},
    {"value": "distributor", "label": "유통사"},
    {"value": "unknown", "label": "미확인"},
]
BUSINESS_TYPE_LABELS = {row["value"]: row["label"] for row in BUSINESS_TYPES}

PRODUCT_CATEGORIES = [
    {"value": "serum", "label": "세럼"},
    {"value": "cream", "label": "크림"},
    {"value": "cleanser", "label": "클렌저"},
    {"value": "other", "label": "기타"},
]
CATEGORY_LABELS = {row["value"]: row["label"] for row in PRODUCT_CATEGORIES}

DATA_MODES = [
    {"value": "real", "label": "실제"},
    {"value": "demo", "label": "데모"},
]

MODES = [
    {"value": "oem", "label": "OEM"},
    {"value": "odm", "label": "ODM"},
]

OUTCOMES = [
    {"value": "match", "label": "일치"},
    {"value": "mismatch", "label": "불일치"},
    {"value": "unknown", "label": "미확인"},
]

REVIEW_STATUS = [
    {"value": "draft", "label": "검토 전"},
    {"value": "reviewed", "label": "검토 완료"},
]

FOLLOWUP_STATUS = [
    {"value": "open", "label": "예정"},
    {"value": "done", "label": "완료"},
]

CHANNELS = ["이메일", "전화", "화상회의", "대면", "전시회", "기타"]


# ---------------------------------------------------------------------------
# 적합도 기준 (명세 8절) - 팀이 설정한 가설이며 수정 가능
# ---------------------------------------------------------------------------

RULE_VERSION = "2026-09-19.v1"

CRITERIA = [
    {"key": "category", "label": "제품군 대응", "oem": 30, "odm": 25,
     "hint": "고객이 파는 제품군을 우리가 만들 수 있는가"},
    {"key": "spec", "label": "생산 사양 / 개발 요구 대응", "oem": 20, "odm": 30,
     "hint": "확정 사양(OEM) 또는 개발 요구(ODM)를 맞출 수 있는가"},
    {"key": "moq", "label": "주문량과 MOQ", "oem": 20, "odm": 15,
     "hint": "고객이 밝힌 주문량이 우리 MOQ 이상인가"},
    {"key": "certification", "label": "명시된 인증 요구 대응", "oem": 15, "odm": 15,
     "hint": "고객이 요구한 인증을 보유했는가 (요구가 없으면 미확인)"},
    {"key": "lead_time", "label": "명시된 납기 요구 대응", "oem": 15, "odm": 15,
     "hint": "고객이 밝힌 납기를 맞출 수 있는가"},
]
CRITERIA_BY_KEY = {row["key"]: row for row in CRITERIA}

# 정보 확인율이 이 값보다 낮으면 '정보 부족'으로 표시하고 확정 추천에서 뺀다
COVERAGE_THRESHOLD = 50.0

# 고객이 명시한 필수조건이 어긋나면 총점과 별개로 강조한다
BLOCKING_CRITERIA = {"moq", "certification"}


# ---------------------------------------------------------------------------
# CSV (명세 7절)
# ---------------------------------------------------------------------------

CSV_REQUIRED = ["company_name", "official_url", "source_channel"]
CSV_OPTIONAL = ["brand_name", "headquarters_country", "sales_country",
                "business_type", "product_category", "contact_url"]
CSV_COLUMNS = CSV_REQUIRED + CSV_OPTIONAL

MAX_CSV_BYTES = 2 * 1024 * 1024        # 2MB
ALLOWED_UPLOAD_EXT = {".csv"}


# ---------------------------------------------------------------------------
# 시간
# ---------------------------------------------------------------------------

def now_seoul():
    return datetime.now(SEOUL)


def now_iso():
    return now_seoul().isoformat(timespec="seconds")


def today_iso():
    return now_seoul().date().isoformat()


# ---------------------------------------------------------------------------
# 값 정리
# ---------------------------------------------------------------------------

_DOMAIN_STRIP = re.compile(r"^(https?://)?(www\.)?", re.I)


def canonical_domain(url_or_domain):
    """공식 도메인만 남긴다. 회사 동일성 판단의 유일한 기계적 기준이다."""
    value = (url_or_domain or "").strip().lower()
    if not value:
        return ""
    if "://" in value:
        value = urllib.parse.urlsplit(value).netloc or value
    value = _DOMAIN_STRIP.sub("", value)
    return value.split("/")[0].split(":")[0].strip().strip(".")


def clean_text(value, limit=500):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def parse_amount(value):
    """'5,000 units' -> (5000.0, 'units'). 못 읽으면 (None, 원문)."""
    raw = clean_text(value, 80)
    if not raw:
        return None, ""
    match = re.search(r"(\d[\d,]*(?:\.\d+)?)", raw)
    if not match:
        return None, raw
    number = float(match.group(1).replace(",", ""))
    unit = raw.replace(match.group(1), "").strip(" ,")
    return number, unit


# ---------------------------------------------------------------------------
# 수집 URL 안전 검사 (명세 5.2)
# ---------------------------------------------------------------------------

ALLOWED_SCHEMES = {"http", "https"}


class UnsafeUrl(ValueError):
    """수집해서는 안 되는 URL."""


def validate_collect_url(url):
    """http/https + 공인 IP 호스트만 허용한다.

    localhost·사설 IP·링크 로컬·파일 URL을 막는다.
    리다이렉트 대상도 이 함수로 다시 검사해야 한다.
    """
    raw = (url or "").strip()
    if not raw:
        raise UnsafeUrl("URL이 비어 있습니다.")

    parts = urllib.parse.urlsplit(raw)
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeUrl("http/https 주소만 수집할 수 있습니다: {}".format(parts.scheme or "없음"))

    host = parts.hostname
    if not host:
        raise UnsafeUrl("호스트를 읽을 수 없습니다.")
    if host.lower() in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise UnsafeUrl("내부 호스트는 수집할 수 없습니다.")

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UnsafeUrl("호스트를 찾을 수 없습니다: {}".format(host)) from exc

    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (address.is_private or address.is_loopback or address.is_link_local
                or address.is_reserved or address.is_multicast):
            raise UnsafeUrl("내부망 주소로 연결됩니다: {}".format(address))

    return raw


def is_valid_http_url(url):
    """화면 입력 검증용 - DNS 조회 없이 형식만 본다."""
    parts = urllib.parse.urlsplit((url or "").strip())
    return parts.scheme.lower() in ALLOWED_SCHEMES and bool(parts.netloc)


# ---------------------------------------------------------------------------
# CSV 내보내기 안전 처리 (명세 7절)
# ---------------------------------------------------------------------------

_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value):
    """스프레드시트에서 수식으로 실행될 수 있는 셀 앞에 작은따옴표를 붙인다."""
    text = "" if value is None else str(value)
    if text.startswith(_FORMULA_START):
        return "'" + text
    return text
