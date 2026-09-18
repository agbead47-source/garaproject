# -*- coding: utf-8 -*-
"""신규 바이어 발굴 - 제안 초안 템플릿 (명세 4.4).

원칙:
  - 확인되지 않은 인증·공급 실적·효능·납기·가격을 문장에 채워 넣지 않는다.
    값이 없으면 문장을 빼거나 '상담에서 확인' 항목으로 돌린다.
  - 사실(관찰)과 가설을 나눠서 적는다.
  - AI 생성이라고 표시하지 않는다. 템플릿 기반 초안이다.
  - 임의 문장 자동 번역은 하지 않는다. 한국어/영어 템플릿을 각각 둔다.
"""

import json

from . import models

LANGUAGES = [
    {"value": "ko", "label": "한국어"},
    {"value": "en", "label": "English"},
]

# 제안 가설 - 담당자가 고른다
HYPOTHESES = [
    {"value": "line_extension", "ko": "기존 라인 확장", "en": "Line extension",
     "ko_desc": "확인된 제품군 옆에 붙일 신제품 제안",
     "en_desc": "A new item next to the product line we could confirm"},
    {"value": "category_gap", "ko": "미확인 제품군 진입", "en": "Category we could not confirm",
     "ko_desc": "수집 범위에서 확인되지 않은 제품군 제안 (부재 단정 아님)",
     "en_desc": "A category not observed within our collected pages (not a claim of absence)"},
    {"value": "second_source", "ko": "복수 공급처", "en": "Second-source supply",
     "ko_desc": "기존 공급처와 병행할 대체 생산처 제안",
     "en_desc": "An additional manufacturing partner alongside the current one"},
    {"value": "market_entry", "ko": "신규 판매국 대응", "en": "New market support",
     "ko_desc": "확장 예정 판매국의 규제·서류 대응 제안",
     "en_desc": "Support for regulatory documents in a market they plan to enter"},
]
HYPOTHESIS_BY_KEY = {row["value"]: row for row in HYPOTHESES}


def _as_list(raw):
    if not raw:
        return []
    try:
        value = json.loads(raw)
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
    except (TypeError, ValueError):
        pass
    return [p.strip() for p in str(raw).replace("\n", ",").split(",") if p.strip()]


def _bullet(lines):
    return "\n".join("- {}".format(line) for line in lines if line)


# ---------------------------------------------------------------------------
# 근거 정리
# ---------------------------------------------------------------------------

def gather_facts(prospect, products, summary, checks, language="ko"):
    """확인된 사실만 모은다. 출처를 같이 남긴다."""
    facts = []
    ko = language == "ko"

    if prospect.get("headquarters_country"):
        facts.append(("본사 소재국: {}" if ko else "Headquarters: {}").format(
            prospect["headquarters_country"]))
    if prospect.get("sales_country"):
        facts.append(("확인된 판매국: {}" if ko else "Sales market on record: {}").format(
            prospect["sales_country"]))

    count = (summary or {}).get("product_count") or 0
    if count:
        labels = ", ".join(models.CATEGORY_LABELS.get(c, c) if ko else c
                           for c in (summary.get("category_list") or []))
        facts.append(
            ("공식 사이트에서 수집한 제품 {}건, 확인된 제품군: {}" if ko else
             "{} products collected from the official site; categories observed: {}"
             ).format(count, labels or ("미확인" if ko else "not identified")))
        if summary.get("price_min") is not None and summary.get("currencies"):
            facts.append(
                ("관찰된 소매가 범위: {} {:,.2f} ~ {:,.2f} (제조 견적가가 아님)" if ko else
                 "Observed retail price range: {} {:,.2f}-{:,.2f} (not a manufacturing quote)"
                 ).format(summary["currencies"][0], summary["price_min"], summary["price_max"]))
    else:
        facts.append("수집된 제품 정보가 아직 없습니다." if ko
                     else "No product records have been collected yet.")

    for check in checks or []:
        if check["outcome"] == "match":
            facts.append("{}: {}".format(check["label"] if ko else check["criterion"],
                                         check["evidence"]))
    return facts


def gather_open_questions(checks, capabilities, language="ko"):
    """미확인 항목을 상담 질문으로 바꾼다."""
    ko = language == "ko"
    questions = []
    templates = {
        "category": ("어떤 제품군의 생산·개발을 검토하고 계신지 알려 주실 수 있을까요?",
                     "Which product categories are you currently looking to develop or source?"),
        "spec": ("확정된 사양서가 있으신지, 아니면 콘셉트 단계인지 궁금합니다.",
                 "Do you have a finalized specification, or is this still at the concept stage?"),
        "moq": ("초도 주문 수량은 어느 정도로 보고 계신가요?",
                "What order quantity are you considering for the first run?"),
        "certification": ("필요하신 인증이나 서류가 있으신가요?",
                          "Are there certifications or documents you require?"),
        "lead_time": ("희망하시는 샘플·양산 일정이 있으신가요?",
                      "Do you have a target timeline for samples and mass production?"),
    }
    for check in checks or []:
        if check["outcome"] == "unknown":
            pair = templates.get(check["criterion"])
            if pair:
                questions.append(pair[0] if ko else pair[1])

    if not (capabilities or {}).get("certs"):
        questions.append(
            "요구 인증이 있으실 경우 알려 주시면 보유 현황을 확인해 회신드리겠습니다." if ko else
            "If you have certification requirements, we will confirm our status and reply.")
    return questions


# ---------------------------------------------------------------------------
# 본문 작성
# ---------------------------------------------------------------------------

def _capability_lines(capabilities, language):
    """등록된 값만 적는다. 비어 있으면 그 줄을 빼 버린다."""
    ko = language == "ko"
    cap = capabilities or {}
    lines = []

    categories = _as_list(cap.get("product_categories"))
    if categories:
        labels = [models.CATEGORY_LABELS.get(c, c) if ko else c for c in categories]
        lines.append(("제조 가능 제품군: {}" if ko else
                      "Product categories we manufacture: {}").format(", ".join(labels)))

    formulations = _as_list(cap.get("formulations"))
    if formulations:
        lines.append(("개발 가능 제형·특징: {}" if ko else
                      "Formulation types we develop: {}").format(", ".join(formulations)))

    for row in (cap.get("moq") or []):
        if row.get("moq_value"):
            lines.append(("{} MOQ: {:,.0f}{}" if ko else
                          "{} MOQ: {:,.0f}{}").format(
                models.CATEGORY_LABELS.get(row["product_category"], row["product_category"])
                if ko else row["product_category"],
                row["moq_value"], " " + (row.get("moq_unit") or "")))

    verified = [c for c in (cap.get("certs") or []) if c.get("internally_verified")]
    if verified:
        lines.append(("보유 인증(내부 확인 완료): {}" if ko else
                      "Certifications (internally verified): {}").format(
            ", ".join("{}{}".format(c["name"], " / " + c["scope"] if c.get("scope") else "")
                      for c in verified)))

    if cap.get("sample_lead_time"):
        lines.append(("통상 샘플 소요기간: {}" if ko else
                      "Typical sample lead time: {}").format(cap["sample_lead_time"]))
    if cap.get("mass_lead_time"):
        lines.append(("통상 양산 소요기간: {}" if ko else
                      "Typical mass production lead time: {}").format(cap["mass_lead_time"]))
    if cap.get("lead_time_note"):
        lines.append(("일정 전제조건: {}" if ko else
                      "Lead time assumptions: {}").format(cap["lead_time_note"]))
    return lines


def build(prospect, products, summary, checks, capabilities, mode, language, hypothesis_key):
    """제안 초안(제목 + 본문)을 만든다."""
    ko = language == "ko"
    hypothesis = HYPOTHESIS_BY_KEY.get(hypothesis_key) or HYPOTHESES[0]
    company = prospect.get("company_name") or ("고객사" if ko else "your company")
    brand = prospect.get("brand_name") or company
    mode_label = "OEM" if mode == "oem" else "ODM"

    facts = gather_facts(prospect, products, summary, checks, language)
    questions = gather_open_questions(checks, capabilities, language)
    capability_lines = _capability_lines(capabilities, language)
    matches = [c for c in (checks or []) if c["outcome"] == "match"]

    if ko:
        subject = "[{}] {} 제품 개발·생산 협업 제안".format(mode_label, brand)
        blocks = [
            "{} 담당자님께,".format(company),
            "",
            "안녕하세요. 화장품 {} 제조를 담당하는 해외영업팀입니다.".format(mode_label),
            "{} 의 공개 제품 정보를 살펴보고 협업 가능성을 검토해 연락드립니다.".format(brand),
            "",
            "■ 확인한 내용 (공개 정보 기준)",
            _bullet(facts),
            "",
            "■ 저희가 대응 가능한 범위",
            _bullet(capability_lines) or "- (등록된 자사 역량 정보가 없어 상담 시 안내드리겠습니다.)",
            "",
            "■ 제안 방향 — {} (가설)".format(hypothesis["ko"]),
            "- {}".format(hypothesis["ko_desc"]),
        ]
        if matches:
            blocks.append("- 일치 근거: {}".format(
                " / ".join("{} — {}".format(c["label"], c["evidence"]) for c in matches)))
        else:
            blocks.append("- 현재까지 공개 정보만으로는 일치 근거를 확정하지 못했습니다.")

        if mode == "oem":
            blocks += [
                "",
                "■ 상담에서 확인하고 싶은 사항 (OEM)",
                _bullet(["확정된 사양서 보유 여부",
                         "예상 주문 수량과 납기",
                         "요구 품질 기준 및 검사 항목",
                         "용기·부자재 조달 방식 (사급/자급)"] + questions),
            ]
        else:
            blocks += [
                "",
                "■ 상담에서 확인하고 싶은 사항 (ODM)",
                _bullet(["목표 제품 콘셉트와 사용감 방향",
                         "목표 판매국과 등록 일정",
                         "샘플 검토 일정",
                         "브랜드 포지셔닝상 피하고 싶은 성분"] + questions),
            ]

        blocks += [
            "",
            "회신 주시면 조건에 맞춰 검토 결과와 일정을 정리해 보내드리겠습니다.",
            "감사합니다.",
            "",
            "{}".format((capabilities or {}).get("contact_person") or "해외영업팀"),
        ]
    else:
        subject = "{} partnership for {} product development".format(mode_label, brand)
        blocks = [
            "Dear {} team,".format(company),
            "",
            "We are the overseas sales team of a cosmetics {} manufacturer.".format(mode_label),
            "We reviewed the publicly available product information on {} and would like to"
            " explore whether we can support your development.".format(brand),
            "",
            "What we could confirm (from public information)",
            _bullet(facts),
            "",
            "What we can support",
            _bullet(capability_lines) or "- (Our capability profile is not registered yet.)",
            "",
            "Proposed direction - {} (working hypothesis)".format(hypothesis["en"]),
            "- {}".format(hypothesis["en_desc"]),
        ]
        if matches:
            blocks.append("- Basis: {}".format(
                " / ".join("{}: {}".format(c["criterion"], c["evidence"]) for c in matches)))
        else:
            blocks.append("- We could not yet confirm a match from public information alone.")

        if mode == "oem":
            blocks += [
                "",
                "Questions for a first call (OEM)",
                _bullet(["Whether a finalized specification is available",
                         "Expected order quantity and delivery timeline",
                         "Quality standards and inspection items",
                         "How packaging components are sourced"] + questions),
            ]
        else:
            blocks += [
                "",
                "Questions for a first call (ODM)",
                _bullet(["Target concept and sensory direction",
                         "Target markets and registration timeline",
                         "Sample review schedule",
                         "Ingredients to avoid for brand positioning"] + questions),
            ]

        blocks += [
            "",
            "If this is of interest, we will prepare a summary based on your conditions.",
            "Thank you for your time.",
            "",
            "{}".format((capabilities or {}).get("contact_person") or "Overseas Sales Team"),
        ]

    body = "\n".join(blocks)
    return {"subject": subject, "body": body,
            "facts": facts, "questions": questions,
            "hypothesis": hypothesis, "mode": mode, "language": language}
