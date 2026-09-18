# -*- coding: utf-8 -*-
"""신규 바이어 발굴 - 데모 데이터 (명세 2절, 11절 1단계).

모든 레코드는 data_mode='demo' 로 저장한다. 실제 조회·집계와 섞이지 않는다.
여기 나오는 회사·도메인·제품은 **가상의 예시**다.
실제 기업 정보나 수집 성공 결과로 표시하지 않는다.

    python -m prospecting.seed_demo          # 데모 데이터 생성(이미 있으면 유지)
    python -m prospecting.seed_demo --reset  # 데모 데이터만 지우고 다시 생성
"""

import sys
from datetime import timedelta

from . import matching, models, repository

DEMO_MARK = "demo"

# 가상의 미국 스킨케어 브랜드 (example.com 계열 도메인만 사용한다)
_COMPANIES = [
    {
        "company_name": "Northlight Skin Labs (데모)", "brand_name": "Northlight",
        "official_url": "https://northlight-demo.example.com",
        "headquarters_country": "United States", "sales_country": "United States",
        "business_type": "brand", "source_channel": "전시회 디렉터리",
        "stage": "contacted", "owner": "홍길동",
        "products": [
            ("Barrier Repair Serum", "serum", 30, "ml", 48.0, "USD"),
            ("Daily Calm Cream", "cream", 50, "ml", 52.0, "USD"),
            ("Gentle Gel Cleanser", "cleanser", 150, "ml", 28.0, "USD"),
        ],
        "requirements": [
            ("order_quantity", "8,000 units", "units", "verified"),
            ("lead_time", "12 weeks", "weeks", "verified"),
            ("product_category", "serum, cream", "", "verified"),
            ("development_request", "fragrance-free, barrier, ceramide", "", "verified"),
        ],
        "interactions": [
            (-21, "이메일", "out", "회사 소개와 대응 제품군 안내", "발송"),
            (-14, "이메일", "in", "세럼 라인 MOQ와 일정 문의", "회신"),
        ],
        "followup": (3, "샘플 일정 회신", "홍길동"),
        "reach": ["researched", "contacted", "replied"],
    },
    {
        "company_name": "Harborrow Beauty (데모)", "brand_name": "Harborrow",
        "official_url": "https://harborrow-demo.example.com",
        "headquarters_country": "United States", "sales_country": "United States, Canada",
        "business_type": "brand", "source_channel": "브랜드 홈페이지",
        "stage": "meeting", "owner": "홍길동",
        "products": [
            ("Vitamin Glow Serum", "serum", 30, "ml", 62.0, "USD"),
            ("Overnight Recovery Cream", "cream", 50, "ml", 78.0, "USD"),
        ],
        "requirements": [
            ("order_quantity", "5,000 units", "units", "verified"),
            ("certification", "ISO 22716, Vegan", "", "verified"),
            ("lead_time", "16 weeks", "weeks", "verified"),
            ("product_category", "serum", "", "verified"),
            ("spec", "watery serum, niacinamide", "", "verified"),
        ],
        "interactions": [
            (-35, "이메일", "out", "첫 제안 메일 발송", "발송"),
            (-28, "이메일", "in", "샘플 가능 여부 문의", "회신"),
            (-10, "화상회의", "out", "제품군·MOQ 상담 진행", "상담 완료"),
        ],
        "followup": (-2, "상담 후 견적 초안 전달", "홍길동"),
        "reach": ["researched", "contacted", "replied", "meeting"],
    },
    {
        "company_name": "Pinegrove Naturals (데모)", "brand_name": "Pinegrove",
        "official_url": "https://pinegrove-demo.example.com",
        "headquarters_country": "United States", "sales_country": "United States",
        "business_type": "brand", "source_channel": "전시회 디렉터리",
        "stage": "researched", "owner": "홍길동",
        "products": [
            ("Herbal Cleansing Foam", "cleanser", 120, "ml", 24.0, "USD"),
            ("Soothing Day Cream", "cream", 50, "ml", 38.0, "USD"),
        ],
        "requirements": [],          # 요구가 없으면 전부 미확인 -> 정보 부족
        "interactions": [],
        "followup": None,
        "reach": ["researched"],
    },
    {
        "company_name": "Vermilion Supply Co. (데모)", "brand_name": "Vermilion",
        "official_url": "https://vermilion-demo.example.com",
        "headquarters_country": "United States", "sales_country": "United States",
        "business_type": "distributor", "source_channel": "전시회 디렉터리",
        "stage": "on_hold", "owner": "홍길동",
        "products": [("Assorted Skincare Set", "other", None, None, None, None)],
        "requirements": [
            ("order_quantity", "500 units", "units", "verified"),
            ("certification", "COSMOS Organic", "", "verified"),
        ],
        "interactions": [(-40, "이메일", "out", "초기 문의", "무응답")],
        "followup": None,
        "reach": ["researched"],
        "hold_reason": "유통사라 제조 수요가 불분명함. 3개월 뒤 재검토.",
    },
]

_CAPABILITIES = {
    "mode": "both",
    "product_categories": "serum, cream, cleanser",
    "formulations": "watery serum, gel cream, ceramide barrier, niacinamide, fragrance-free",
    "countries": "United States, EU, Japan",
    "regulatory_support": "성분 한도 검토 보조 및 서류 목록 안내 (수출 적법성 보장 아님)",
    "sample_lead_time": "4 weeks",
    "mass_lead_time": "10 weeks",
    "lead_time_note": "부자재 사급 기준, 디자인 확정일로부터 산정",
    "contact_person": "해외영업팀 홍길동",
}

_MOQ = [
    {"product_category": "serum", "moq_value": 5000, "moq_unit": "units"},
    {"product_category": "cream", "moq_value": 5000, "moq_unit": "units"},
    {"product_category": "cleanser", "moq_value": 10000, "moq_unit": "units"},
]

_CERTS = [
    {"name": "ISO 22716", "scope": "생산 공장 전체", "valid_until": "2028-03-31",
     "internally_verified": True},
    {"name": "Vegan (인증기관 심사)", "scope": "지정 처방에 한함", "valid_until": "2027-06-30",
     "internally_verified": True},
]


def clear_demo():
    """데모 레코드만 지운다. 실제 데이터는 건드리지 않는다."""
    repository.run("DELETE FROM prospects WHERE data_mode = ?", (DEMO_MARK,))


def has_demo():
    return repository.scalar(
        "SELECT COUNT(*) FROM prospects WHERE data_mode = ?", (DEMO_MARK,)) > 0


def seed(reset=False):
    repository.init_db()
    if reset:
        clear_demo()
    elif has_demo():
        return {"created": 0, "skipped": True}

    if not repository.get_capabilities():
        repository.save_capabilities(_CAPABILITIES, _MOQ, _CERTS)

    today = models.now_seoul().date()
    created = 0

    for spec in _COMPANIES:
        prospect_id = repository.create_prospect({
            "company_name": spec["company_name"],
            "brand_name": spec["brand_name"],
            "official_url": spec["official_url"],
            "headquarters_country": spec["headquarters_country"],
            "sales_country": spec["sales_country"],
            "business_type": spec["business_type"],
            "source_channel": spec["source_channel"],
            "owner": spec["owner"],
            "data_mode": DEMO_MARK,
            "stage": "discovered",
            "hold_reason": spec.get("hold_reason"),
            "notes": "데모 데이터입니다. 실제 기업 정보가 아닙니다.",
        })
        created += 1

        for name, category, size, unit, price, currency in spec["products"]:
            product_id, _ = repository.upsert_product(prospect_id, {
                "product_name": name,
                "product_category": category,
                "size_value": size,
                "size_unit": unit,
                "retail_price": price,
                "currency": currency,
                "source_url": "{}/products/{}".format(
                    spec["official_url"], name.lower().replace(" ", "-")),
                "collected_at": models.now_iso(),
                "source_id": None,
                "raw_price": ("{} {}".format(currency, price) if price else ""),
                "raw_size": ("{}{}".format(size, unit) if size else ""),
            })
            repository.replace_product_claims(product_id, ["데모 표기"])

        for field, value, unit, status in spec["requirements"]:
            repository.add_requirement(prospect_id, field, value, unit, status,
                                       note="데모 상담 기록")

        # 단계 이력을 날짜와 함께 남긴다 (전환율 계산의 근거)
        previous = "discovered"
        offsets = {"researched": -45, "contacted": -35, "replied": -25,
                   "meeting": -10, "sample_quote": -5, "won": -1}
        for stage in spec["reach"]:
            changed = (today + timedelta(days=offsets.get(stage, -1))).isoformat()
            repository.run(
                "INSERT INTO stage_events (prospect_id, from_stage, to_stage, changed_at, reason)"
                " VALUES (?,?,?,?,?)",
                (prospect_id, previous, stage, changed + "T09:00:00+09:00", "데모 진행"))
            previous = stage
        repository.run("UPDATE prospects SET stage = ? WHERE id = ?",
                       (spec["stage"], prospect_id))
        if spec["stage"] != previous:
            repository.add_stage_event(prospect_id, previous, spec["stage"], "데모 상태")

        last_interaction = None
        for offset, channel, direction, summary, outcome in spec["interactions"]:
            last_interaction = repository.add_interaction(prospect_id, {
                "occurred_at": (today + timedelta(days=offset)).isoformat(),
                "channel": channel, "direction": direction,
                "summary": summary, "outcome": outcome, "owner": spec["owner"],
            })

        if spec["followup"]:
            offset, task, owner = spec["followup"]
            repository.add_followup(prospect_id,
                                    (today + timedelta(days=offset)).isoformat(),
                                    task, owner, last_interaction)

        for mode in ("oem", "odm"):
            matching.rescore_prospect(repository, prospect_id, mode)

    return {"created": created, "skipped": False}


if __name__ == "__main__":
    result = seed(reset="--reset" in sys.argv)
    if result["skipped"]:
        print("데모 데이터가 이미 있습니다. 다시 만들려면 --reset 을 붙이세요.")
    else:
        print("데모 후보 {}건 생성 · DB: {}".format(result["created"], repository.DB_PATH))
