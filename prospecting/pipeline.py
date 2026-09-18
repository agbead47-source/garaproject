# -*- coding: utf-8 -*-
"""신규 바이어 발굴 - pandas 정리·중복 제거·집계 (명세 7절).

원칙:
  - 원문 값을 버리지 않는다. 표준화 결과는 별도 열로 만든다.
  - 이름 유사성만으로 회사를 합치지 않는다. 도메인처럼 명확한 기준만 쓴다.
  - 변환 못 한 값은 0이나 기본 통화로 채우지 않고 오류 목록에 남긴다.
"""

import io
import re

import pandas as pd

from . import models

# 제품군 추정용 키워드 (표준화 힌트일 뿐, 확정 분류가 아니다)
_CATEGORY_HINTS = [
    ("serum", ["serum", "ampoule", "essence", "booster", "세럼", "앰플", "에센스"]),
    ("cream", ["cream", "moisturizer", "balm", "lotion", "크림", "로션", "밤"]),
    ("cleanser", ["cleanser", "cleansing", "foam", "wash", "클렌저", "클렌징", "폼"]),
]

_CURRENCY_SIGNS = {"$": "USD", "₩": "KRW", "€": "EUR", "£": "GBP", "¥": "JPY"}
_CURRENCY_CODES = {"USD", "KRW", "EUR", "GBP", "JPY", "CNY", "SGD", "VND"}

_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(ml|g|oz|fl\s?oz|мл)\b", re.I)
_PRICE_RE = re.compile(r"([$₩€£¥]|USD|KRW|EUR|GBP|JPY|CNY|SGD|VND)?\s*"
                       r"(\d[\d,]*(?:\.\d+)?)\s*"
                       r"([$₩€£¥]|USD|KRW|EUR|GBP|JPY|CNY|SGD|VND)?", re.I)


# ---------------------------------------------------------------------------
# 표준화
# ---------------------------------------------------------------------------

def normalize_company(name):
    """비교용 회사명. 원문은 따로 보존한다."""
    text = models.clean_text(name, 200).lower()
    text = re.sub(r"[,.]", " ", text)
    text = re.sub(r"\b(co|inc|ltd|llc|corp|corporation|company|limited|gmbh|sarl|s\.a|kk)\b",
                  " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_country(value):
    text = models.clean_text(value, 60)
    if not text:
        return ""
    table = {
        "us": "United States", "usa": "United States", "u.s.": "United States",
        "united states of america": "United States", "미국": "United States",
        "kr": "South Korea", "korea": "South Korea", "한국": "South Korea",
        "eu": "EU", "유럽": "EU", "france": "France", "프랑스": "France",
        "germany": "Germany", "독일": "Germany", "singapore": "Singapore",
        "싱가포르": "Singapore", "japan": "Japan", "일본": "Japan",
    }
    return table.get(text.lower(), text)


def guess_category(*texts):
    blob = " ".join(models.clean_text(t, 200) for t in texts if t).lower()
    for value, keywords in _CATEGORY_HINTS:
        if any(word in blob for word in keywords):
            return value
    return "other"


def normalize_inci(name):
    text = models.clean_text(name, 120)
    text = re.sub(r"\s*\(.*?\)\s*", " ", text)
    return re.sub(r"\s+", " ", text).strip().title()


def parse_size(raw):
    """'30 ml' -> (30.0, 'ml'). 못 읽으면 (None, None)."""
    match = _SIZE_RE.search(models.clean_text(raw, 80))
    if not match:
        return None, None
    unit = match.group(2).lower().replace(" ", "")
    return float(match.group(1)), unit


def parse_price(raw):
    """'$42.00' -> (42.0, 'USD'). 통화를 못 찾으면 (값, None) 으로 남긴다."""
    text = models.clean_text(raw, 80)
    if not text:
        return None, None
    match = _PRICE_RE.search(text)
    if not match:
        return None, None

    amount = float(match.group(2).replace(",", ""))
    currency = None
    for token in (match.group(1), match.group(3)):
        if not token:
            continue
        token = token.strip().upper()
        currency = _CURRENCY_SIGNS.get(token) or (token if token in _CURRENCY_CODES else None)
        if currency:
            break
    return amount, currency


# ---------------------------------------------------------------------------
# CSV 가져오기 (미리보기 -> 오류 확인 -> 저장)
# ---------------------------------------------------------------------------

def read_csv_preview(raw_bytes):
    """CSV를 읽어 수용/거절 행을 나눈다.

    돌려주는 값: {"accepted": [...], "rejected": [...], "columns": [...],
                 "total": n, "error": 치명적 오류 메시지}
    수용 + 거절 = 전체 이어야 한다.
    """
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw_bytes.decode("cp949")
        except UnicodeDecodeError:
            return {"accepted": [], "rejected": [], "columns": [], "total": 0,
                    "error": "파일 인코딩을 읽지 못했습니다. UTF-8로 저장해 주세요."}

    try:
        frame = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    except Exception as exc:                          # noqa: BLE001
        return {"accepted": [], "rejected": [], "columns": [], "total": 0,
                "error": "CSV를 읽지 못했습니다: {}".format(str(exc)[:160])}

    frame.columns = [str(c).strip().lower() for c in frame.columns]
    missing = [col for col in models.CSV_REQUIRED if col not in frame.columns]
    if missing:
        return {"accepted": [], "rejected": [], "columns": list(frame.columns),
                "total": int(len(frame)),
                "error": "필수 열이 없습니다: {}".format(", ".join(missing))}

    for column in models.CSV_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""

    frame = frame[models.CSV_COLUMNS].fillna("")
    for column in models.CSV_COLUMNS:
        frame[column] = frame[column].map(lambda v: models.clean_text(v, 300))

    frame["row_no"] = range(2, len(frame) + 2)        # 헤더가 1행
    frame["norm_company"] = frame["company_name"].map(normalize_company)
    frame["canonical_domain"] = frame["official_url"].map(models.canonical_domain)
    frame["headquarters_country"] = frame["headquarters_country"].map(normalize_country)
    frame["sales_country"] = frame["sales_country"].map(normalize_country)

    accepted, rejected = [], []
    for record in frame.to_dict("records"):
        reasons = []
        if not record["company_name"]:
            reasons.append("company_name 이 비었습니다")
        if not record["official_url"]:
            reasons.append("official_url 이 비었습니다")
        elif not models.is_valid_http_url(record["official_url"]):
            reasons.append("official_url 형식이 http/https 가 아닙니다")
        elif not record["canonical_domain"]:
            reasons.append("official_url 에서 도메인을 읽지 못했습니다")
        if not record["source_channel"]:
            reasons.append("source_channel 이 비었습니다")
        if record["business_type"] and record["business_type"] not in models.BUSINESS_TYPE_LABELS:
            reasons.append("business_type 값이 목록에 없습니다")

        if reasons:
            record["reasons"] = reasons
            rejected.append(record)
        else:
            accepted.append(record)

    # 파일 안에서 도메인이 겹치는 행은 한 번만 넣는다 (명확한 기준)
    seen, deduped, duplicates = set(), [], []
    for record in accepted:
        domain = record["canonical_domain"]
        if domain in seen:
            record["reasons"] = ["파일 안에 같은 도메인이 이미 있습니다: {}".format(domain)]
            duplicates.append(record)
            continue
        seen.add(domain)
        deduped.append(record)

    return {
        "accepted": deduped,
        "rejected": rejected + duplicates,
        "columns": list(frame.columns),
        "total": int(len(frame)),
        "error": "",
    }


# ---------------------------------------------------------------------------
# 집계 (명세 7절 5번)
# ---------------------------------------------------------------------------

def aggregate_products(product_rows):
    """기업별 제품 수·제품군·관찰 성분/클레임을 집계한다."""
    if not product_rows:
        return {}

    frame = pd.DataFrame(product_rows)
    frame["product_category"] = frame["product_category"].fillna("other")

    summary = {}
    for prospect_id, group in frame.groupby("prospect_id"):
        categories = (group["product_category"].value_counts().to_dict())
        prices = group["retail_price"].dropna()
        sizes = group["size_value"].dropna()
        summary[int(prospect_id)] = {
            "product_count": int(len(group)),
            "categories": {str(k): int(v) for k, v in categories.items()},
            "category_list": sorted({str(c) for c in group["product_category"]}),
            "price_min": float(prices.min()) if len(prices) else None,
            "price_max": float(prices.max()) if len(prices) else None,
            "currencies": sorted({c for c in group["currency"].dropna() if c}),
            "missing_price": int(group["retail_price"].isna().sum()),
            "missing_size": int(group["size_value"].isna().sum()),
            "size_range": ([float(sizes.min()), float(sizes.max())] if len(sizes) else None),
        }
    return summary


def ingredient_frequency(product_rows, ingredient_rows):
    """관찰된 성분 빈도. '이 브랜드가 쓰는 성분'이라고 단정하지 않는다."""
    if not ingredient_rows:
        return []
    frame = pd.DataFrame(ingredient_rows)
    frame["inci_name"] = frame["inci_name"].map(normalize_inci)
    frame = frame[frame["inci_name"] != ""]
    if frame.empty:
        return []
    counts = frame.groupby("inci_name").size().sort_values(ascending=False)
    return [{"inci_name": name, "count": int(n)} for name, n in counts.items()]


def duplicate_candidates(prospect_rows):
    """도메인이 같은 묶음만 '중복 후보'로 표시한다. 자동 병합은 하지 않는다."""
    if not prospect_rows:
        return []
    frame = pd.DataFrame(prospect_rows)
    frame["canonical_domain"] = frame["canonical_domain"].fillna("")
    frame = frame[frame["canonical_domain"] != ""]
    if frame.empty:
        return []

    groups = []
    for domain, group in frame.groupby("canonical_domain"):
        if len(group) > 1:
            groups.append({
                "domain": domain,
                "prospects": group[["id", "company_name", "created_at"]].to_dict("records"),
            })
    return groups
