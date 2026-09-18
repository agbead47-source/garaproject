# -*- coding: utf-8 -*-
"""To-do Trade - 더미 데이터 (UI 가안)

실제 OCR/LLM/번역 연동 없이 화면만 확인하기 위한 가짜 데이터.
나중에 실제 로직으로 교체하기 쉽도록 전부 함수로 감싸 두었다.
"""

# ---------------------------------------------------------------------------
# 고객사 / 출력 언어
# ---------------------------------------------------------------------------

_CUSTOMERS = [
    {"id": "glowtree", "name": "Glowtree Beauty", "country": "미국"},
    {"id": "lumiere", "name": "Lumière Skin", "country": "프랑스"},
    {"id": "seoulglow", "name": "Seoul Glow SG", "country": "싱가포르"},
    {"id": "verde", "name": "Verde Botanics", "country": "독일"},
]

LANGUAGES = [
    {"code": "ko", "label": "한국어(기본)"},
    {"code": "en", "label": "English"},
    {"code": "zh", "label": "中文"},
    {"code": "vi", "label": "Tiếng Việt"},
]


def get_customers():
    """고객사 목록."""
    return [dict(row) for row in _CUSTOMERS]


def get_languages():
    """출력 언어 목록 (업로드 화면 / 변환 화면 드롭다운 공용)."""
    return [dict(row) for row in LANGUAGES]


# ---------------------------------------------------------------------------
# 샘플 개발요청서 원문 (영문)
#   아래 항목들의 source 문장은 이 원문의 부분 문자열이어야 한다.
#   (분석 결과 화면에서 형광펜 하이라이트에 사용)
# ---------------------------------------------------------------------------

SAMPLE_DOCUMENT = """Glowtree Beauty - Product Development Request

Date: September 4, 2026
From: Glowtree Beauty (Los Angeles, USA)
To: To-do Trade Co., Ltd. / Overseas Sales Team

1. Product Overview
We would like to request the development of a Vitamin C Brightening Serum for our 2027 spring line.
The product is a leave-on facial serum filled in a 30ml glass dropper bottle.
Our first launch market is the United States, and we plan to expand to the EU afterwards.

2. Texture and Sensory
The texture should be light and watery, absorbing quickly without any sticky finish.
The formula must be fragrance-free.
Package color and label design will be shared later.

3. Key Ingredients
Please include Vitamin C (Ascorbyl Glucoside), Niacinamide and Hyaluronic Acid as the core actives.
We also want Retinol at 0.5% for the night-care claim.

4. Free-from Requirements
The formula must be free from Parabens, Sulfates, Mineral oil and Synthetic fragrance.

5. Claims and Certification
We hope to use Vegan and Cruelty-free claims on the outer box.

6. Commercial Terms
MOQ is 5,000 units for the first order.
Our target unit price is 2.8 per piece.
Please send the first sample within 4 weeks, and mass production shipment is expected in January 2027.

Thank you,
Emily Park / Product Director, Glowtree Beauty
"""

# ---------------------------------------------------------------------------
# 추출 항목 14개
#   status: confirmed(확인됨) / check(확인 필요) / missing(누락)
# ---------------------------------------------------------------------------

_EXTRACTED_ITEMS = [
    {
        "key": "product_name",
        "label": "제품명",
        "value": "Vitamin C Brightening Serum (비타민C 브라이트닝 세럼)",
        "confidence": 98,
        "status": "confirmed",
        "source": "We would like to request the development of a Vitamin C Brightening Serum for our 2027 spring line.",
        "note": "",
    },
    {
        "key": "product_type",
        "label": "제품 유형",
        "value": "리브온 페이셜 세럼",
        "confidence": 95,
        "status": "confirmed",
        "source": "The product is a leave-on facial serum filled in a 30ml glass dropper bottle.",
        "note": "",
    },
    {
        "key": "volume",
        "label": "용량",
        "value": "30ml",
        "confidence": 97,
        "status": "confirmed",
        "source": "The product is a leave-on facial serum filled in a 30ml glass dropper bottle.",
        "note": "",
    },
    {
        "key": "container",
        "label": "용기",
        "value": "유리 스포이드 병",
        "confidence": 93,
        "status": "confirmed",
        "source": "The product is a leave-on facial serum filled in a 30ml glass dropper bottle.",
        "note": "",
    },
    {
        "key": "moq",
        "label": "MOQ",
        "value": "5,000개 (초도 물량)",
        "confidence": 96,
        "status": "confirmed",
        "source": "MOQ is 5,000 units for the first order.",
        "note": "",
    },
    {
        "key": "target_price",
        "label": "목표 단가",
        "value": "2.8 / 개",
        "confidence": 61,
        "status": "check",
        "source": "Our target unit price is 2.8 per piece.",
        "note": "통화 표기가 없고 FOB/CIF 등 거래 조건도 불명확 — 고객사 확인 필요",
    },
    {
        "key": "texture",
        "label": "텍스처",
        "value": "가벼운 워터리, 빠른 흡수 / 끈적임 없음",
        "confidence": 92,
        "status": "confirmed",
        "source": "The texture should be light and watery, absorbing quickly without any sticky finish.",
        "note": "",
    },
    {
        "key": "fragrance",
        "label": "향",
        "value": "무향 (fragrance-free)",
        "confidence": 99,
        "status": "confirmed",
        "source": "The formula must be fragrance-free.",
        "note": "",
    },
    {
        "key": "key_ingredients",
        "label": "핵심 성분",
        "value": "Vitamin C(Ascorbyl Glucoside), Niacinamide, Hyaluronic Acid, Retinol 0.5%",
        "confidence": 74,
        "status": "check",
        "source": "We also want Retinol at 0.5% for the night-care claim.",
        "note": "Retinol 0.5% — 판매 국가별 농도 기준 확인 필요",
    },
    {
        "key": "free_from",
        "label": "배제 성분",
        "value": "Parabens, Sulfates, Mineral oil, Synthetic fragrance",
        "confidence": 97,
        "status": "confirmed",
        "source": "The formula must be free from Parabens, Sulfates, Mineral oil and Synthetic fragrance.",
        "note": "",
    },
    {
        "key": "claims",
        "label": "인증·클레임",
        "value": "Vegan, Cruelty-free (외박스 표기)",
        "confidence": 90,
        "status": "confirmed",
        "source": "We hope to use Vegan and Cruelty-free claims on the outer box.",
        "note": "",
    },
    {
        "key": "target_country",
        "label": "판매 국가",
        "value": "미국(1차) → EU(확장 예정)",
        "confidence": 94,
        "status": "confirmed",
        "source": "Our first launch market is the United States, and we plan to expand to the EU afterwards.",
        "note": "",
    },
    {
        "key": "delivery",
        "label": "납기",
        "value": "샘플 4주 이내 / 본생산 선적 2027년 1월",
        "confidence": 68,
        "status": "check",
        "source": "Please send the first sample within 4 weeks, and mass production shipment is expected in January 2027.",
        "note": "선적 조건(FOB/CIF)과 도착 항구가 명시되지 않음 — 확인 필요",
    },
    {
        "key": "package_design",
        "label": "패키지 디자인",
        "value": "",
        "confidence": 0,
        "status": "missing",
        "source": "Package color and label design will be shared later.",
        "note": "원문에 '추후 전달'로만 적혀 있어 값 없음",
    },
]

# 상태 뱃지 (템플릿에서 사용)
STATUS_META = {
    "confirmed": {"label": "확인됨", "css": "confirmed"},
    "check": {"label": "확인 필요", "css": "check"},
    "missing": {"label": "누락", "css": "missing"},
}

# 규제 체크 미리보기
_REGULATION_NOTES = [
    {
        "level": "warning",
        "ingredient": "Retinol 0.5%",
        "message": "Retinol 요청 농도가 EU 기준 초과 가능성 — 국가별 규제 검색에서 확인 필요",
    },
]


def analyze_document(file=None):
    """업로드된 문서를 분석한 '척' 하고 더미 결과를 돌려준다.

    TODO: 실제 연동 (OCR + LLM 항목 추출)
    """
    items = [dict(item) for item in _EXTRACTED_ITEMS]
    return {
        "file_name": file or "Glowtree_Beauty_Development_Request.pdf",
        "customer": "Glowtree Beauty",
        "customer_country": "미국",
        "detected_language": "English",
        "source_text": SAMPLE_DOCUMENT,
        "items": items,
        "item_count": len(items),
        "check_count": sum(1 for i in items if i["status"] == "check"),
        "missing_count": sum(1 for i in items if i["status"] == "missing"),
        "regulation_notes": [dict(n) for n in _REGULATION_NOTES],
        "regulation_count": len(_REGULATION_NOTES),
    }


# ---------------------------------------------------------------------------
# 내부 전달 문서 (연구소용 / 공장용)
#   문서 구조는 한 번만 정의하고 언어별 사전에서 문구를 꺼내 쓴다.
#   ko/en 은 전부 번역, zh/vi 는 일부만 번역(없으면 en 으로 대체).
# ---------------------------------------------------------------------------

_LAB_STRUCTURE = [
    {"key": "overview", "rows": ["product_name", "product_type", "target_country"]},
    {"key": "sensory", "rows": ["texture", "fragrance", "color"]},
    {"key": "ingredients", "rows": ["key_ingredients", "free_from"]},
    {"key": "claims", "rows": ["claims"]},
    {"key": "tests", "rows": ["test_stability", "test_irritation"]},
    {"key": "regulation", "rows": ["regulation_note"]},
]

_FACTORY_STRUCTURE = [
    {"key": "spec", "rows": ["product_name", "volume", "container", "accessory"]},
    {"key": "commercial", "rows": ["moq", "target_price"]},
    {"key": "delivery", "rows": ["sample_due", "mass_shipment", "shipping_terms"]},
    {"key": "packaging", "rows": ["package_design", "label"]},
]

_DOC_TITLES = {
    "lab": {
        "ko": "연구소 전달용 개발 의뢰서",
        "en": "Product Development Brief for R&D Lab",
        "zh": "研究所开发委托书",
        "vi": "Phiếu yêu cầu phát triển (Phòng R&D)",
    },
    "factory": {
        "ko": "공장 전달용 생산 의뢰서",
        "en": "Production Brief for Factory",
        "zh": "工厂生产委托书",
        "vi": "Phiếu yêu cầu sản xuất (Nhà máy)",
    },
}

_SECTION_HEADINGS = {
    "ko": {
        "overview": "제품 개요",
        "sensory": "제형·사용감 요청",
        "ingredients": "성분 요구사항",
        "claims": "인증·클레임 요구",
        "tests": "시험 요청",
        "regulation": "규제 주의사항",
        "spec": "제품 사양",
        "commercial": "수량·단가",
        "delivery": "납기·선적",
        "packaging": "포장·라벨 요구사항",
    },
    "en": {
        "overview": "Product Overview",
        "sensory": "Texture & Sensory Requirements",
        "ingredients": "Ingredient Requirements",
        "claims": "Claims & Certification",
        "tests": "Requested Tests",
        "regulation": "Regulatory Notes",
        "spec": "Product Specification",
        "commercial": "Quantity & Price",
        "delivery": "Lead Time & Shipping",
        "packaging": "Packaging & Label",
    },
    "zh": {
        "overview": "产品概要",
        "sensory": "质地·肤感要求",
        "ingredients": "成分要求",
        "claims": "认证·宣称",
        "tests": "测试要求",
        "regulation": "法规注意事项",
        "spec": "产品规格",
        "commercial": "数量·单价",
        "delivery": "交期·出货",
        "packaging": "包装·标签",
    },
    "vi": {
        "overview": "Tổng quan sản phẩm",
        "sensory": "Yêu cầu kết cấu · cảm giác",
        "ingredients": "Yêu cầu thành phần",
        "claims": "Chứng nhận · công bố",
        "tests": "Yêu cầu kiểm nghiệm",
        "regulation": "Lưu ý pháp lý",
        "spec": "Thông số sản phẩm",
        "commercial": "Số lượng · đơn giá",
        "delivery": "Thời hạn · giao hàng",
        "packaging": "Đóng gói · nhãn",
    },
}

_FIELD_LABELS = {
    "ko": {
        "product_name": "제품명",
        "product_type": "제품 유형",
        "target_country": "타깃 국가",
        "texture": "텍스처",
        "fragrance": "향",
        "color": "색상",
        "key_ingredients": "필수 성분",
        "free_from": "배제 성분 (Free-from)",
        "claims": "클레임",
        "test_stability": "안정성 시험",
        "test_irritation": "피부자극 시험",
        "regulation_note": "규제 확인",
        "volume": "용량",
        "container": "용기",
        "accessory": "부자재",
        "moq": "MOQ",
        "target_price": "목표 단가",
        "sample_due": "샘플 납기",
        "mass_shipment": "본생산 선적",
        "shipping_terms": "선적 조건",
        "package_design": "패키지 디자인",
        "label": "라벨 요구사항",
    },
    "en": {
        "product_name": "Product Name",
        "product_type": "Product Type",
        "target_country": "Target Market",
        "texture": "Texture",
        "fragrance": "Fragrance",
        "color": "Color",
        "key_ingredients": "Required Actives",
        "free_from": "Free-from",
        "claims": "Claims",
        "test_stability": "Stability Test",
        "test_irritation": "Skin Irritation Test",
        "regulation_note": "Regulatory Check",
        "volume": "Volume",
        "container": "Container",
        "accessory": "Accessories",
        "moq": "MOQ",
        "target_price": "Target Unit Price",
        "sample_due": "Sample Due",
        "mass_shipment": "Mass Production Shipment",
        "shipping_terms": "Shipping Terms",
        "package_design": "Package Design",
        "label": "Label Requirements",
    },
    "zh": {
        "product_name": "产品名称",
        "product_type": "产品类型",
        "target_country": "目标市场",
        "texture": "质地",
        "fragrance": "香型",
        "color": "颜色",
        "key_ingredients": "必需成分",
        "free_from": "禁用成分",
        "claims": "宣称",
        "volume": "容量",
        "container": "容器",
        "moq": "起订量",
        "target_price": "目标单价",
    },
    "vi": {
        "product_name": "Tên sản phẩm",
        "product_type": "Loại sản phẩm",
        "target_country": "Thị trường mục tiêu",
        "texture": "Kết cấu",
        "fragrance": "Hương",
        "color": "Màu sắc",
        "key_ingredients": "Thành phần bắt buộc",
        "free_from": "Thành phần loại trừ",
        "claims": "Công bố",
        "volume": "Dung tích",
        "container": "Bao bì",
        "moq": "MOQ",
        "target_price": "Đơn giá mục tiêu",
    },
}

_FIELD_VALUES = {
    "ko": {
        "product_name": "비타민C 브라이트닝 세럼 (Vitamin C Brightening Serum)",
        "product_type": "리브온 페이셜 세럼",
        "target_country": "미국 우선 출시, 이후 EU 확장 예정",
        "texture": "가볍고 워터리한 제형, 빠른 흡수 / 끈적임 없을 것",
        "fragrance": "무향 (fragrance-free)",
        "color": "미정 — 고객사가 추후 전달 예정",
        "key_ingredients": "Vitamin C (Ascorbyl Glucoside), Niacinamide, Hyaluronic Acid, Retinol 0.5%",
        "free_from": "Parabens, Sulfates, Mineral oil, Synthetic fragrance",
        "claims": "Vegan, Cruelty-free (외박스 표기 희망)",
        "test_stability": "가속 안정성 시험 요청 (45도 4주 기준)",
        "test_irritation": "인체적용 피부자극 시험 결과 요청",
        "regulation_note": "Retinol 0.5% — EU 확장 시 농도 기준 초과 가능성, 규제 확인 필요",
        "volume": "30ml",
        "container": "유리 스포이드 병 (30ml)",
        "accessory": "스포이드 캡, 외박스 — 사양 협의 필요",
        "moq": "5,000개 (초도 물량)",
        "target_price": "2.8 / 개 — 통화·거래 조건 확인 필요",
        "sample_due": "요청일로부터 4주 이내",
        "mass_shipment": "2027년 1월 선적 예정",
        "shipping_terms": "미정 (FOB/CIF 미기재) — 확인 필요",
        "package_design": "미정 — 색상·라벨 디자인 추후 전달 예정",
        "label": "Vegan / Cruelty-free 표기, 미국 라벨 규정 준수",
    },
    "en": {
        "product_name": "Vitamin C Brightening Serum",
        "product_type": "Leave-on facial serum",
        "target_country": "United States first, EU expansion planned",
        "texture": "Light watery texture, fast absorbing, no sticky finish",
        "fragrance": "Fragrance-free",
        "color": "TBD - to be shared by the customer later",
        "key_ingredients": "Vitamin C (Ascorbyl Glucoside), Niacinamide, Hyaluronic Acid, Retinol 0.5%",
        "free_from": "Parabens, Sulfates, Mineral oil, Synthetic fragrance",
        "claims": "Vegan, Cruelty-free (to be printed on the outer box)",
        "test_stability": "Accelerated stability test requested (45C, 4 weeks)",
        "test_irritation": "Human skin irritation test report requested",
        "regulation_note": "Retinol 0.5% - may exceed EU limits on expansion; regulatory check required",
        "volume": "30ml",
        "container": "Glass dropper bottle (30ml)",
        "accessory": "Dropper cap, outer box - specification to be confirmed",
        "moq": "5,000 units (first order)",
        "target_price": "2.8 per piece - currency and trade terms to be confirmed",
        "sample_due": "Within 4 weeks from request",
        "mass_shipment": "Shipment expected in January 2027",
        "shipping_terms": "TBD (FOB/CIF not stated) - confirmation required",
        "package_design": "TBD - color and label design to be shared later",
        "label": "Vegan / Cruelty-free marking, US labeling rules to be followed",
    },
    "zh": {
        "product_name": "维生素C亮白精华",
        "product_type": "驻留型面部精华",
        "target_country": "优先美国市场，之后扩展至欧盟",
        "texture": "轻盈水感质地，吸收快，不黏腻",
        "fragrance": "无香 (fragrance-free)",
        "key_ingredients": "Vitamin C (Ascorbyl Glucoside), Niacinamide, Hyaluronic Acid, Retinol 0.5%",
        "free_from": "Parabens, Sulfates, Mineral oil, Synthetic fragrance",
        "volume": "30ml",
        "moq": "5,000 支（首单）",
    },
    "vi": {
        "product_name": "Serum dưỡng sáng Vitamin C",
        "product_type": "Serum dưỡng da dạng leave-on",
        "target_country": "Ưu tiên thị trường Mỹ, sau đó mở rộng sang EU",
        "texture": "Kết cấu mỏng nhẹ, thấm nhanh, không nhờn dính",
        "fragrance": "Không hương liệu (fragrance-free)",
        "key_ingredients": "Vitamin C (Ascorbyl Glucoside), Niacinamide, Hyaluronic Acid, Retinol 0.5%",
        "free_from": "Parabens, Sulfates, Mineral oil, Synthetic fragrance",
        "volume": "30ml",
        "moq": "5.000 sản phẩm (đơn đầu tiên)",
    },
}

# 원문 대비 보기에서 각 항목 아래에 보여줄 원문 문장
_FIELD_SOURCES = {
    "product_name": "We would like to request the development of a Vitamin C Brightening Serum for our 2027 spring line.",
    "product_type": "The product is a leave-on facial serum filled in a 30ml glass dropper bottle.",
    "target_country": "Our first launch market is the United States, and we plan to expand to the EU afterwards.",
    "texture": "The texture should be light and watery, absorbing quickly without any sticky finish.",
    "fragrance": "The formula must be fragrance-free.",
    "color": "Package color and label design will be shared later.",
    "key_ingredients": "Please include Vitamin C (Ascorbyl Glucoside), Niacinamide and Hyaluronic Acid as the core actives. We also want Retinol at 0.5% for the night-care claim.",
    "free_from": "The formula must be free from Parabens, Sulfates, Mineral oil and Synthetic fragrance.",
    "claims": "We hope to use Vegan and Cruelty-free claims on the outer box.",
    "test_stability": "(원문에 명시 없음 — 사내 기본 시험 항목)",
    "test_irritation": "(원문에 명시 없음 — 사내 기본 시험 항목)",
    "regulation_note": "We also want Retinol at 0.5% for the night-care claim.",
    "volume": "The product is a leave-on facial serum filled in a 30ml glass dropper bottle.",
    "container": "The product is a leave-on facial serum filled in a 30ml glass dropper bottle.",
    "accessory": "(원문에 명시 없음 — 확인 필요)",
    "moq": "MOQ is 5,000 units for the first order.",
    "target_price": "Our target unit price is 2.8 per piece.",
    "sample_due": "Please send the first sample within 4 weeks, and mass production shipment is expected in January 2027.",
    "mass_shipment": "Please send the first sample within 4 weeks, and mass production shipment is expected in January 2027.",
    "shipping_terms": "(원문에 명시 없음 — 확인 필요)",
    "package_design": "Package color and label design will be shared later.",
    "label": "We hope to use Vegan and Cruelty-free claims on the outer box.",
}

# 변환 문서에서 주황(확인 필요) / 회색(누락)으로 강조할 항목
_FIELD_FLAGS = {
    "key_ingredients": "check",
    "regulation_note": "check",
    "target_price": "check",
    "shipping_terms": "check",
    "color": "missing",
    "accessory": "missing",
    "package_design": "missing",
}


def _pick(table, lang, key):
    """해당 언어에 문구가 없으면 en → ko 순으로 대체한다."""
    for candidate in (lang, "en", "ko"):
        value = table.get(candidate, {}).get(key)
        if value:
            return value
    return key


def _build_document(structure, doc_kind, result, lang):
    lang = lang if lang in {row["code"] for row in LANGUAGES} else "ko"
    sections = []
    for block in structure:
        rows = [
            {
                "key": row_key,
                "label": _pick(_FIELD_LABELS, lang, row_key),
                "value": _pick(_FIELD_VALUES, lang, row_key),
                "source": _FIELD_SOURCES.get(row_key, ""),
                "flag": _FIELD_FLAGS.get(row_key, ""),
            }
            for row_key in block["rows"]
        ]
        sections.append(
            {
                "key": block["key"],
                "heading": _pick(_SECTION_HEADINGS, lang, block["key"]),
                "rows": rows,
            }
        )

    result = result or {}
    titles = _DOC_TITLES[doc_kind]
    return {
        "kind": doc_kind,
        "lang": lang,
        "title": titles.get(lang) or titles["en"],
        "customer": result.get("customer", "Glowtree Beauty"),
        "file_name": result.get("file_name", ""),
        "sections": sections,
    }


def convert_for_lab(result, lang="ko"):
    """분석 결과를 연구소용 문서로 변환한 척 한다.

    TODO: 실제 연동 (LLM 문서 변환 + 번역)
    """
    return _build_document(_LAB_STRUCTURE, "lab", result, lang)


def convert_for_factory(result, lang="ko"):
    """분석 결과를 공장용 문서로 변환한 척 한다.

    TODO: 실제 연동 (LLM 문서 변환 + 번역)
    """
    return _build_document(_FACTORY_STRUCTURE, "factory", result, lang)


# ---------------------------------------------------------------------------
# 처리 이력
# ---------------------------------------------------------------------------

_HISTORY = [
    {
        "id": 1,
        "date": "2026-09-16",
        "customer": "Glowtree Beauty",
        "file_name": "Glowtree_Beauty_Development_Request.pdf",
        "source_lang": "English",
        "targets": ["연구소", "공장"],
        "status": "check",
        "manager": "홍길동",
    },
    {
        "id": 2,
        "date": "2026-09-12",
        "customer": "Lumière Skin",
        "file_name": "Lumiere_Cream_Brief_FR.docx",
        "source_lang": "French",
        "targets": ["연구소"],
        "status": "delivered",
        "manager": "홍길동",
    },
    {
        "id": 3,
        "date": "2026-09-09",
        "customer": "Seoul Glow SG",
        "file_name": "SeoulGlow_Sunscreen_Spec.xlsx",
        "source_lang": "English",
        "targets": ["연구소", "공장"],
        "status": "delivered",
        "manager": "김수출",
    },
    {
        "id": 4,
        "date": "2026-09-05",
        "customer": "Verde Botanics",
        "file_name": "Verde_Shampoo_Request_DE.pdf",
        "source_lang": "German",
        "targets": ["공장"],
        "status": "analyzed",
        "manager": "김수출",
    },
    {
        "id": 5,
        "date": "2026-08-28",
        "customer": "Glowtree Beauty",
        "file_name": "Glowtree_Toner_Revision_v2.pdf",
        "source_lang": "English",
        "targets": ["연구소"],
        "status": "delivered",
        "manager": "홍길동",
    },
    {
        "id": 6,
        "date": "2026-08-21",
        "customer": "Lumière Skin",
        "file_name": "Lumiere_Packaging_Note.jpg",
        "source_lang": "French",
        "targets": ["공장"],
        "status": "check",
        "manager": "박무역",
    },
    {
        "id": 7,
        "date": "2026-08-14",
        "customer": "Seoul Glow SG",
        "file_name": "SeoulGlow_Cushion_Brief.docx",
        "source_lang": "English",
        "targets": ["연구소", "공장"],
        "status": "analyzed",
        "manager": "박무역",
    },
    {
        "id": 8,
        "date": "2026-08-03",
        "customer": "Verde Botanics",
        "file_name": "Verde_BodyOil_Request.pdf",
        "source_lang": "German",
        "targets": ["연구소"],
        "status": "delivered",
        "manager": "홍길동",
    },
]

# 이력 상태 뱃지
HISTORY_STATUS_META = {
    "analyzed": {"label": "분석 완료", "css": "analyzed"},
    "delivered": {"label": "전달 완료", "css": "delivered"},
    "check": {"label": "확인 필요", "css": "check"},
}


def get_history():
    """처리 이력 더미 (최신순 8건)."""
    return [dict(row) for row in _HISTORY]


# ---------------------------------------------------------------------------
# 국가별 규제 검색 (UI 가안)
#   국가별 성분 규제 더미. 실제로는 규제 DB / 공공 API 를 붙인다.
# ---------------------------------------------------------------------------

_REG_COUNTRIES = [
    {
        "code": "us",
        "name": "미국",
        "flag": "🇺🇸",
        "authority": "FDA (MoCRA)",
        "scheme": "사전 등록 불필요 / 시설·제품 등록 의무",
        "period": "등록 후 즉시 판매 가능",
        "documents": ["시설 등록(Facility Registration)", "제품 리스팅", "안전성 입증 자료", "전성분 표기"],
        "label": "전성분(INCI) 영문 표기, 용량, 제조사·유통사 정보, 경고 문구",
        "caution": "MoCRA 시행으로 안전성 입증 자료(Safety Substantiation) 보관 의무가 생겼습니다.",
    },
    {
        "code": "eu",
        "name": "EU",
        "flag": "🇪🇺",
        "authority": "EC Regulation 1223/2009",
        "scheme": "CPNP 사전 등록 + RP(책임자) 지정 필수",
        "period": "CPNP 등록 약 2~4주 / PIF 준비 6~10주",
        "documents": ["CPNP 등록", "PIF(제품정보파일)", "CPSR 안전성 평가서", "책임자(RP) 계약서"],
        "label": "전성분 INCI, 원산지, PAO 기호, 배치번호, RP 주소 표기",
        "caution": "성분 농도 제한이 가장 엄격합니다. 배합 확정 전 Annex 목록 대조가 필요합니다.",
    },
    {
        "code": "cn",
        "name": "중국",
        "flag": "🇨🇳",
        "authority": "NMPA",
        "scheme": "일반화장품 등록(备案) / 특수화장품 허가(注册)",
        "period": "일반 4~8주 / 특수 6~12개월",
        "documents": ["중국 내 책임회사 지정", "전성분 및 배합 비율", "제품 안전성 평가 자료", "중문 라벨"],
        "label": "중문 라벨 필수, 사용기한·제조사·등록번호 표기",
        "caution": "신원료 사용 시 별도 등록이 필요하며, 일부 기능성 표현은 특수화장품으로 분류됩니다.",
    },
    {
        "code": "jp",
        "name": "일본",
        "flag": "🇯🇵",
        "authority": "후생노동성 (의약품의료기기법)",
        "scheme": "제조판매업 허가 보유사를 통한 신고",
        "period": "화장품 신고 1~2주 / 의약부외품 4~6개월",
        "documents": ["제조판매업자 정보", "성분 표준화 명칭 대조표", "품질 규격서"],
        "label": "일본어 전성분 표기, 제조판매원 명칭·주소, 내용량",
        "caution": "성분 명칭을 일본 표준 명칭으로 변환해야 하며, 미승인 성분은 사용할 수 없습니다.",
    },
    {
        "code": "vn",
        "name": "베트남",
        "flag": "🇻🇳",
        "authority": "보건부 DAV (ASEAN Cosmetic Directive)",
        "scheme": "공표(Product Notification) 제도",
        "period": "공표 승인 약 3~6주",
        "documents": ["CFS(자유판매증명서)", "위임장(POA) 공증본", "전성분 및 함량", "제품 설명서"],
        "label": "베트남어 보조 라벨 부착, 수입사 정보, 제조일·유통기한",
        "caution": "ASEAN 기준을 따르므로 EU Annex 목록과 유사한 제한이 적용됩니다.",
    },
]

# 규제 판정 상태 뱃지
REG_STATUS_META = {
    "ok": {"label": "적합", "css": "confirmed"},
    "warn": {"label": "주의", "css": "check"},
    "ban": {"label": "사용 불가", "css": "danger"},
}

_REG_INGREDIENTS = [
    {
        "key": "retinol",
        "name": "레티놀",
        "inci": "Retinol",
        "category": "활성 성분",
        "requested": "0.5%",
        "updated": "2026-08-30",
        "rules": {
            "us": {"status": "ok", "limit": "농도 제한 없음 (자율 규제)", "rule": "FDA / PCPC 자율 권고",
                   "note": "0.5% 사용 가능하나 자극 관련 경고 문구를 권장합니다."},
            "eu": {"status": "ban", "limit": "리브온 제품 0.05% 이하", "rule": "Regulation (EU) 2024/996",
                   "note": "요청 농도 0.5%는 기준 초과 — EU 판매 시 배합 변경이 필요합니다."},
            "cn": {"status": "warn", "limit": "0.3% 이하 권고", "rule": "화장품 안전기술규범(2015)",
                   "note": "농도 조정 후 특수화장품 분류 여부를 확인해야 합니다."},
            "jp": {"status": "warn", "limit": "표시 기준 준수 시 사용 가능", "rule": "의약품의료기기법",
                   "note": "주름 개선 표현을 쓰면 의약부외품 신고 대상입니다."},
            "vn": {"status": "ban", "limit": "리브온 제품 0.05% 이하", "rule": "ASEAN Cosmetic Directive Annex III",
                   "note": "EU 기준을 준용하므로 동일하게 초과합니다."},
        },
    },
    {
        "key": "ascorbyl_glucoside",
        "name": "아스코빌글루코사이드",
        "inci": "Ascorbyl Glucoside",
        "category": "미백·브라이트닝",
        "requested": "2.0%",
        "updated": "2026-07-14",
        "rules": {
            "us": {"status": "ok", "limit": "제한 없음", "rule": "FDA 일반 화장품 성분", "note": ""},
            "eu": {"status": "ok", "limit": "제한 없음", "rule": "Annex 미등재 (일반 성분)", "note": ""},
            "cn": {"status": "warn", "limit": "2.0% 이하", "rule": "NMPA 미백 기능성",
                   "note": "미백 표현 사용 시 특수화장품 허가 대상입니다."},
            "jp": {"status": "ok", "limit": "제한 없음", "rule": "화장품 기준", "note": ""},
            "vn": {"status": "ok", "limit": "제한 없음", "rule": "ACD 일반 성분", "note": ""},
        },
    },
    {
        "key": "niacinamide",
        "name": "나이아신아마이드",
        "inci": "Niacinamide",
        "category": "미백·브라이트닝",
        "requested": "5.0%",
        "updated": "2026-06-02",
        "rules": {
            "us": {"status": "ok", "limit": "제한 없음", "rule": "FDA 일반 화장품 성분", "note": ""},
            "eu": {"status": "ok", "limit": "제한 없음", "rule": "Annex 미등재 (일반 성분)", "note": ""},
            "cn": {"status": "ok", "limit": "5.0% 이하 권고", "rule": "화장품 안전기술규범", "note": ""},
            "jp": {"status": "warn", "limit": "의약부외품 기준 2~5%", "rule": "의약부외품 유효성분",
                   "note": "미백을 소구하려면 의약부외품 신고가 필요합니다."},
            "vn": {"status": "ok", "limit": "제한 없음", "rule": "ACD 일반 성분", "note": ""},
        },
    },
    {
        "key": "hyaluronic",
        "name": "히알루론산",
        "inci": "Sodium Hyaluronate",
        "category": "보습",
        "requested": "1.0%",
        "updated": "2026-05-21",
        "rules": {
            "us": {"status": "ok", "limit": "제한 없음", "rule": "FDA 일반 화장품 성분", "note": ""},
            "eu": {"status": "ok", "limit": "제한 없음", "rule": "Annex 미등재", "note": ""},
            "cn": {"status": "ok", "limit": "제한 없음", "rule": "기사용 원료 목록(IECIC) 등재", "note": ""},
            "jp": {"status": "ok", "limit": "제한 없음", "rule": "화장품 기준", "note": ""},
            "vn": {"status": "ok", "limit": "제한 없음", "rule": "ACD 일반 성분", "note": ""},
        },
    },
    {
        "key": "phenoxyethanol",
        "name": "페녹시에탄올",
        "inci": "Phenoxyethanol",
        "category": "방부제",
        "requested": "0.8%",
        "updated": "2026-04-08",
        "rules": {
            "us": {"status": "ok", "limit": "1.0% 이하 권고", "rule": "CIR 안전성 평가", "note": ""},
            "eu": {"status": "ok", "limit": "1.0% 이하", "rule": "Annex V, No.29", "note": "요청 농도 0.8%는 기준 이내입니다."},
            "cn": {"status": "ok", "limit": "1.0% 이하", "rule": "화장품 안전기술규범 방부제 목록", "note": ""},
            "jp": {"status": "ok", "limit": "1.0% 이하", "rule": "화장품 기준 별표3", "note": ""},
            "vn": {"status": "ok", "limit": "1.0% 이하", "rule": "ACD Annex VI", "note": ""},
        },
    },
    {
        "key": "parabens",
        "name": "파라벤류",
        "inci": "Methylparaben / Propylparaben",
        "category": "방부제",
        "requested": "미사용 (Free-from)",
        "updated": "2026-03-19",
        "rules": {
            "us": {"status": "ok", "limit": "혼합 0.8% 이하", "rule": "CIR 권고", "note": "고객사 요청으로 미사용합니다."},
            "eu": {"status": "warn", "limit": "단일 0.4% / 혼합 0.8%", "rule": "Annex V",
                   "note": "이소프로필파라벤 등 일부는 사용 금지 목록입니다."},
            "cn": {"status": "warn", "limit": "단일 0.4% / 혼합 0.8%", "rule": "화장품 안전기술규범", "note": ""},
            "jp": {"status": "ok", "limit": "1.0% 이하", "rule": "화장품 기준", "note": ""},
            "vn": {"status": "warn", "limit": "단일 0.4% / 혼합 0.8%", "rule": "ACD Annex VI", "note": ""},
        },
    },
    {
        "key": "salicylic",
        "name": "살리실릭애씨드",
        "inci": "Salicylic Acid",
        "category": "각질 관리",
        "requested": "0.5%",
        "updated": "2026-08-11",
        "rules": {
            "us": {"status": "warn", "limit": "2.0% 이하 (OTC 기준)", "rule": "FDA OTC Monograph",
                   "note": "여드름 소구 시 OTC 의약품으로 분류됩니다."},
            "eu": {"status": "warn", "limit": "리브온 2.0% 이하", "rule": "Annex III, No.98",
                   "note": "3세 미만 사용 금지 문구를 표기해야 합니다."},
            "cn": {"status": "warn", "limit": "2.0% 이하", "rule": "화장품 안전기술규범", "note": "3세 미만 사용 금지 표기."},
            "jp": {"status": "ok", "limit": "0.2% 이하 (화장품)", "rule": "화장품 기준",
                   "note": "요청 0.5%는 의약부외품 영역입니다."},
            "vn": {"status": "warn", "limit": "2.0% 이하", "rule": "ACD Annex III", "note": ""},
        },
    },
    {
        "key": "hydroquinone",
        "name": "하이드로퀴논",
        "inci": "Hydroquinone",
        "category": "미백·브라이트닝",
        "requested": "미사용",
        "updated": "2026-02-27",
        "rules": {
            "us": {"status": "warn", "limit": "OTC 2.0% 이하", "rule": "FDA / MoCRA",
                   "note": "일반 화장품에는 사용할 수 없고 OTC 의약품 등록이 필요합니다."},
            "eu": {"status": "ban", "limit": "사용 금지", "rule": "Annex II, No.1339", "note": "화장품 사용 전면 금지."},
            "cn": {"status": "ban", "limit": "사용 금지", "rule": "화장품 금지 원료 목록", "note": ""},
            "jp": {"status": "ban", "limit": "사용 금지", "rule": "화장품 기준 별표1", "note": ""},
            "vn": {"status": "ban", "limit": "사용 금지", "rule": "ACD Annex II", "note": ""},
        },
    },
    {
        "key": "titanium_dioxide",
        "name": "티타늄디옥사이드",
        "inci": "Titanium Dioxide",
        "category": "자외선 차단",
        "requested": "미사용",
        "updated": "2026-07-30",
        "rules": {
            "us": {"status": "ok", "limit": "25% 이하", "rule": "FDA OTC Sunscreen Monograph", "note": ""},
            "eu": {"status": "warn", "limit": "25% 이하 (분말 흡입 제형 제외)", "rule": "Annex VI, No.27",
                   "note": "나노 형태는 별도 표기(nano) 의무가 있습니다."},
            "cn": {"status": "warn", "limit": "25% 이하", "rule": "자외선차단제 목록", "note": "특수화장품 허가 대상입니다."},
            "jp": {"status": "ok", "limit": "제한 없음", "rule": "화장품 기준", "note": ""},
            "vn": {"status": "ok", "limit": "25% 이하", "rule": "ACD Annex VII", "note": ""},
        },
    },
    {
        "key": "fragrance_allergen",
        "name": "향료 알레르기 유발물질",
        "inci": "Limonene / Linalool 등 26종",
        "category": "향료",
        "requested": "미사용 (무향)",
        "updated": "2026-09-01",
        "rules": {
            "us": {"status": "ok", "limit": "표기 의무 없음", "rule": "FDA 라벨 규정", "note": ""},
            "eu": {"status": "warn", "limit": "리브온 0.001% 초과 시 개별 표기", "rule": "Regulation (EU) 2023/1545",
                   "note": "무향 처방이면 해당 없음. 향 추가 시 재검토가 필요합니다."},
            "cn": {"status": "warn", "limit": "개별 표기 권고", "rule": "라벨 관리 감독법", "note": ""},
            "jp": {"status": "ok", "limit": "표기 의무 없음", "rule": "화장품 기준", "note": ""},
            "vn": {"status": "warn", "limit": "EU 기준 준용", "rule": "ACD Annex III", "note": ""},
        },
    },
]


def get_reg_countries():
    """규제 검색 대상 국가 목록."""
    return [dict(row) for row in _REG_COUNTRIES]


def get_reg_country(code):
    """국가 코드로 규제 개요 한 건을 찾는다. 없으면 None."""
    for row in _REG_COUNTRIES:
        if row["code"] == code:
            return dict(row)
    return None


def search_regulations(country="all", keyword="", status="all"):
    """국가 / 성분명 / 상태로 규제 더미를 검색한다.

    TODO: 실제 연동 (규제 DB 또는 공공 API 조회)
    """
    keyword = (keyword or "").strip().lower()
    codes = [country] if country != "all" else [row["code"] for row in _REG_COUNTRIES]

    rows = []
    for item in _REG_INGREDIENTS:
        haystack = " ".join([item["name"], item["inci"], item["category"]]).lower()
        if keyword and keyword not in haystack:
            continue
        for code in codes:
            rule = item["rules"].get(code)
            if not rule:
                continue
            if status != "all" and rule["status"] != status:
                continue
            country_row = get_reg_country(code) or {}
            rows.append(
                {
                    "key": "{}-{}".format(item["key"], code),
                    "name": item["name"],
                    "inci": item["inci"],
                    "category": item["category"],
                    "requested": item["requested"],
                    "updated": item["updated"],
                    "country_code": code,
                    "country_name": country_row.get("name", code),
                    "country_flag": country_row.get("flag", ""),
                    "status": rule["status"],
                    "limit": rule["limit"],
                    "rule": rule["rule"],
                    "note": rule["note"],
                }
            )

    return rows


# ---------------------------------------------------------------------------
# 오늘의 트렌드 (UI 가안)
#   실제로는 SNS/커머스 데이터 수집 + 집계 결과가 들어갈 자리.
# ---------------------------------------------------------------------------

TREND_DATE = "2026-09-18"
TREND_SOURCE = "Instagram · TikTok · Amazon · Olive Young Global (더미 집계)"

TREND_CATEGORIES = [
    {"value": "all", "label": "전체"},
    {"value": "skincare", "label": "스킨케어"},
    {"value": "suncare", "label": "선케어"},
    {"value": "makeup", "label": "메이크업"},
    {"value": "haircare", "label": "헤어·바디"},
]

_TREND_KEYWORDS = [
    {
        "rank": 1, "prev": 3, "keyword": "글라스 스킨 세럼", "en": "Glass Skin Serum",
        "category": "skincare", "volume": 184200, "growth": 62,
        "markets": ["미국", "싱가포르"],
        "note": "K-뷰티 리부트 영향으로 미국 20대 여성 언급량이 2주째 급등",
    },
    {
        "rank": 2, "prev": 2, "keyword": "비건 선스틱", "en": "Vegan Sun Stick",
        "category": "suncare", "volume": 158700, "growth": 28,
        "markets": ["미국", "독일"],
        "note": "휴대성 + 비건 인증 조합 제품 리뷰가 꾸준히 증가",
    },
    {
        "rank": 3, "prev": 8, "keyword": "저자극 레티날", "en": "Gentle Retinal",
        "category": "skincare", "volume": 142300, "growth": 91,
        "markets": ["미국", "프랑스"],
        "note": "레티놀 대비 자극이 적다는 후기 확산 — 농도 규제 확인 필요",
    },
    {
        "rank": 4, "prev": 0, "keyword": "쌀겨 앰플", "en": "Rice Bran Ampoule",
        "category": "skincare", "volume": 121900, "growth": 143,
        "markets": ["싱가포르", "베트남"],
        "note": "신규 진입 키워드. 동남아 인플루언서 중심으로 확산 중",
    },
    {
        "rank": 5, "prev": 4, "keyword": "모공 프라이머", "en": "Pore Blurring Primer",
        "category": "makeup", "volume": 98400, "growth": 12,
        "markets": ["미국", "일본"],
        "note": "메이크업 베이스 카테고리에서 재구매율 상위",
    },
    {
        "rank": 6, "prev": 5, "keyword": "두피 스케일러", "en": "Scalp Scaler",
        "category": "haircare", "volume": 86100, "growth": 9,
        "markets": ["독일", "프랑스"],
        "note": "유럽 드럭스토어 채널 입점 문의가 늘어나는 카테고리",
    },
    {
        "rank": 7, "prev": 6, "keyword": "PDRN 크림", "en": "PDRN Cream",
        "category": "skincare", "volume": 77500, "growth": 18,
        "markets": ["싱가포르", "미국"],
        "note": "시술 후 홈케어 수요. 원료 수급 리드타임 확인 필요",
    },
    {
        "rank": 8, "prev": 15, "keyword": "워터리 틴트 밤", "en": "Watery Tint Balm",
        "category": "makeup", "volume": 64800, "growth": 74,
        "markets": ["일본", "베트남"],
        "note": "촉촉한 틴트 제형 수요 상승 — 용기 사양 문의 다수",
    },
    {
        "rank": 9, "prev": 7, "keyword": "무향 바디로션", "en": "Fragrance-free Body Lotion",
        "category": "haircare", "volume": 51200, "growth": -6,
        "markets": ["독일", "미국"],
        "note": "성장세는 둔화했으나 민감성 타깃 문의는 유지",
    },
    {
        "rank": 10, "prev": 9, "keyword": "미네랄 선크림", "en": "Mineral Sunscreen",
        "category": "suncare", "volume": 47600, "growth": -3,
        "markets": ["미국", "프랑스"],
        "note": "티타늄디옥사이드 나노 표기 이슈로 문의 증가",
    },
]

_TREND_INGREDIENTS = [
    {"name": "레티날 (Retinaldehyde)", "growth": 118, "signal": "up", "note": "저자극 안티에이징 소재로 문의 급증"},
    {"name": "PDRN / 폴리뉴클레오타이드", "growth": 84, "signal": "up", "note": "시술 후 케어 라인 확장 중"},
    {"name": "쌀 발효 추출물", "growth": 67, "signal": "up", "note": "동남아 시장 신규 수요"},
    {"name": "엑소좀", "growth": 41, "signal": "up", "note": "프리미엄 라인 위주, 국가별 표현 규제 확인 필요"},
    {"name": "나이아신아마이드", "growth": 8, "signal": "flat", "note": "성숙 단계 — 기본 배합으로 정착"},
    {"name": "알코올 데나트", "growth": -22, "signal": "down", "note": "무알코올 선호로 회피 성분화"},
]

_TREND_MARKETS = [
    {"country": "미국", "flag": "🇺🇸", "top": "글라스 스킨 세럼", "growth": 46,
     "note": "K-뷰티 전문 리테일 채널 확대, 단가 2.5~3.5 USD 구간 문의 집중"},
    {"country": "프랑스", "flag": "🇫🇷", "top": "저자극 레티날", "growth": 33,
     "note": "클린뷰티 인증 요구가 기본값. 성분 서류 준비 기간을 길게 잡아야 함"},
    {"country": "싱가포르", "flag": "🇸🇬", "top": "쌀겨 앰플", "growth": 58,
     "note": "동남아 허브 시장. 소용량 트래블 키트 문의 증가"},
    {"country": "독일", "flag": "🇩🇪", "top": "비건 선스틱", "growth": 21,
     "note": "비건·크루얼티프리 인증서 원본 요구 비율이 높음"},
]

_TREND_NEWS = [
    {"date": "2026-09-18", "tag": "경쟁사", "css": "rival",
     "title": "미국 인디 브랜드 3곳, 레티날 라인 동시 출시",
     "summary": "0.05% 저농도 레티날 세럼을 30ml 30달러대로 출시. EU 확장 계획도 함께 공개했습니다."},
    {"date": "2026-09-17", "tag": "규제", "css": "rule",
     "title": "EU, 향료 알레르기 유발물질 표기 전환 기간 종료 임박",
     "summary": "2026년 말까지 개별 표기로 전환해야 합니다. 향 포함 제품은 라벨 재작업이 필요합니다."},
    {"date": "2026-09-16", "tag": "원료", "css": "material",
     "title": "쌀 발효 추출물 공급가 12% 상승",
     "summary": "동남아 수요 증가로 리드타임이 4주에서 7주로 늘었습니다. 견적 시 반영이 필요합니다."},
    {"date": "2026-09-15", "tag": "채널", "css": "channel",
     "title": "싱가포르 대형 리테일러, K-뷰티 전용관 확대",
     "summary": "소용량 트래블 키트 위주로 입점 제안을 받고 있습니다. MOQ 3,000개 수준 협의가 가능합니다."},
]


def get_trends(category="all"):
    """오늘의 트렌드 더미를 돌려준다.

    TODO: 실제 연동 (SNS/커머스 데이터 수집 + 집계)
    """
    rows = [dict(row) for row in _TREND_KEYWORDS]
    if category != "all":
        rows = [row for row in rows if row["category"] == category]

    top_volume = max([row["volume"] for row in rows], default=1)
    category_labels = {row["value"]: row["label"] for row in TREND_CATEGORIES}

    for row in rows:
        row["ratio"] = round(row["volume"] * 100 / top_volume)
        row["category_label"] = category_labels.get(row["category"], row["category"])
        if not row["prev"]:
            row["move"] = "new"
            row["move_label"] = "NEW"
        elif row["prev"] > row["rank"]:
            row["move"] = "up"
            row["move_label"] = "▲ {}".format(row["prev"] - row["rank"])
        elif row["prev"] < row["rank"]:
            row["move"] = "down"
            row["move_label"] = "▼ {}".format(row["rank"] - row["prev"])
        else:
            row["move"] = "same"
            row["move_label"] = "—"

    return {
        "date": TREND_DATE,
        "source": TREND_SOURCE,
        "keywords": rows,
        "ingredients": [dict(row) for row in _TREND_INGREDIENTS],
        "markets": [dict(row) for row in _TREND_MARKETS],
        "news": [dict(row) for row in _TREND_NEWS],
        "rising_count": sum(1 for row in _TREND_KEYWORDS if row["growth"] >= 50),
        "new_count": sum(1 for row in _TREND_KEYWORDS if not row["prev"]),
        "post_count": "412,800",
        "hot_market": "미국",
    }


# ---------------------------------------------------------------------------
# AI 샘플 미리보기 (UI 가안)
#   개발요청서를 올리면 AI가 샘플 후보를 제안한 '척' 한다.
# ---------------------------------------------------------------------------

_SAMPLE_CANDIDATES = [
    {
        "id": "A",
        "name": "워터리 브라이트닝 세럼 (기본안)",
        "concept": "요청서 그대로 구현한 기준 처방. 가벼운 워터리 텍스처에 비타민C 유도체를 안정형으로 배합.",
        "match": 94,
        "recommended": True,
        "base": "수상 젤 (Water-based Gel)",
        "texture": "워터리 · 빠른 흡수",
        "finish": "산뜻한 무광 마무리",
        "ph": "5.5 ~ 6.0",
        "cost": "USD 1.92 / 개",
        "margin": "목표 단가 2.8 대비 원가율 69%",
        "lead_time": "샘플 제작 3주",
        "risk": "low",
        "risk_note": "안정성 리스크 낮음. 비타민C 유도체를 사용해 변색 가능성이 작습니다.",
        "actives": [
            {"name": "Ascorbyl Glucoside", "percent": "2.0%", "role": "브라이트닝"},
            {"name": "Niacinamide", "percent": "5.0%", "role": "톤 케어 · 피지"},
            {"name": "Sodium Hyaluronate", "percent": "1.0%", "role": "보습"},
            {"name": "Retinol", "percent": "0.5%", "role": "나이트 케어"},
        ],
        "sensory": [
            {"label": "가벼움", "score": 92},
            {"label": "흡수 속도", "score": 88},
            {"label": "촉촉함", "score": 71},
            {"label": "끈적임", "score": 12},
            {"label": "향 강도", "score": 0},
        ],
        "cautions": [
            "Retinol 0.5% — EU 확장 시 0.05% 기준 초과로 별도 처방이 필요합니다.",
            "비타민C 유도체와 레티놀 병용 시 사용 순서 안내 문구를 권장합니다.",
        ],
        "similar": [
            {"customer": "Seoul Glow SG", "product": "Daily Glow Serum 30ml", "year": "2025", "note": "동일 제형 베이스로 양산 진행"},
            {"customer": "Glowtree Beauty", "product": "Hydra Toner 150ml", "year": "2024", "note": "같은 고객사 무향 라인"},
        ],
    },
    {
        "id": "B",
        "name": "EU 대응 저농도 레티날 세럼",
        "concept": "EU 확장 계획을 반영해 레티놀을 저자극 레티날 0.05%로 교체한 규제 안전형 처방.",
        "match": 88,
        "recommended": False,
        "base": "수상 젤 (Water-based Gel)",
        "texture": "워터리 · 실키",
        "finish": "촉촉한 무광 마무리",
        "ph": "5.5 ~ 6.0",
        "cost": "USD 2.14 / 개",
        "margin": "목표 단가 2.8 대비 원가율 76%",
        "lead_time": "샘플 제작 4주",
        "risk": "low",
        "risk_note": "미국·EU 동시 판매 가능. 원료 단가가 기본안보다 높습니다.",
        "actives": [
            {"name": "Ascorbyl Glucoside", "percent": "2.0%", "role": "브라이트닝"},
            {"name": "Niacinamide", "percent": "5.0%", "role": "톤 케어 · 피지"},
            {"name": "Sodium Hyaluronate", "percent": "1.0%", "role": "보습"},
            {"name": "Retinal", "percent": "0.05%", "role": "저자극 안티에이징"},
        ],
        "sensory": [
            {"label": "가벼움", "score": 86},
            {"label": "흡수 속도", "score": 82},
            {"label": "촉촉함", "score": 78},
            {"label": "끈적임", "score": 18},
            {"label": "향 강도", "score": 0},
        ],
        "cautions": [
            "레티날 원료 리드타임이 6주로 길어 샘플 일정에 영향이 있습니다.",
            "원가 상승분(+0.22 USD)에 대한 고객사 협의가 필요합니다.",
        ],
        "similar": [
            {"customer": "Lumière Skin", "product": "Nuit Retinal Serum 30ml", "year": "2026", "note": "EU 등록 완료 사례"},
        ],
    },
    {
        "id": "C",
        "name": "원가 절감형 브라이트닝 에센스",
        "concept": "목표 단가를 맞추기 위해 활성 성분 농도를 조정하고 용기 사양을 단순화한 대안.",
        "match": 76,
        "recommended": False,
        "base": "수상 에센스 (Low-viscosity)",
        "texture": "워터리 · 묽음",
        "finish": "가벼운 무광 마무리",
        "ph": "5.0 ~ 5.5",
        "cost": "USD 1.48 / 개",
        "margin": "목표 단가 2.8 대비 원가율 53%",
        "lead_time": "샘플 제작 2주",
        "risk": "mid",
        "risk_note": "활성 성분 농도가 낮아 체감 효과에 대한 고객사 확인이 필요합니다.",
        "actives": [
            {"name": "Ascorbyl Glucoside", "percent": "1.0%", "role": "브라이트닝"},
            {"name": "Niacinamide", "percent": "2.0%", "role": "톤 케어"},
            {"name": "Sodium Hyaluronate", "percent": "0.5%", "role": "보습"},
        ],
        "sensory": [
            {"label": "가벼움", "score": 96},
            {"label": "흡수 속도", "score": 94},
            {"label": "촉촉함", "score": 54},
            {"label": "끈적임", "score": 8},
            {"label": "향 강도", "score": 0},
        ],
        "cautions": [
            "레티놀 미포함 — 나이트 케어 클레임을 사용할 수 없습니다.",
            "유리 스포이드 대신 플라스틱 펌프 용기를 전제로 한 원가입니다.",
        ],
        "similar": [
            {"customer": "Verde Botanics", "product": "Basic Essence 50ml", "year": "2025", "note": "동일 원가 구조"},
        ],
    },
]

# 처방표 (선택한 샘플 공통 뼈대 — 가안이므로 한 벌만 쓴다)
_SAMPLE_FORMULA = [
    {"phase": "A (수상)", "name": "Water", "percent": "to 100", "role": "용매"},
    {"phase": "A (수상)", "name": "Glycerin", "percent": "6.00", "role": "보습"},
    {"phase": "A (수상)", "name": "Butylene Glycol", "percent": "4.00", "role": "보습 · 용해 보조"},
    {"phase": "A (수상)", "name": "Niacinamide", "percent": "5.00", "role": "톤 케어"},
    {"phase": "B (활성)", "name": "Ascorbyl Glucoside", "percent": "2.00", "role": "브라이트닝"},
    {"phase": "B (활성)", "name": "Sodium Hyaluronate", "percent": "1.00", "role": "보습"},
    {"phase": "C (유상)", "name": "Caprylic/Capric Triglyceride", "percent": "1.50", "role": "에몰리언트"},
    {"phase": "C (유상)", "name": "Retinol (0.5% 기준)", "percent": "0.50", "role": "나이트 케어"},
    {"phase": "D (점증)", "name": "Ammonium Acryloyldimethyltaurate/VP Copolymer", "percent": "0.45", "role": "점증"},
    {"phase": "E (방부)", "name": "Phenoxyethanol", "percent": "0.80", "role": "방부"},
    {"phase": "E (방부)", "name": "Ethylhexylglycerin", "percent": "0.10", "role": "방부 보조"},
]

SAMPLE_RISK_META = {
    "low": {"label": "리스크 낮음", "css": "confirmed"},
    "mid": {"label": "확인 필요", "css": "check"},
    "high": {"label": "리스크 높음", "css": "danger"},
}


def generate_samples(file_name=None):
    """개발요청서를 읽고 샘플 후보를 만든 '척' 한다.

    TODO: 실제 연동 (LLM 처방 제안 + 사내 처방 DB 매칭)
    """
    return {
        "file_name": file_name or "Glowtree_Beauty_Development_Request.pdf",
        "customer": "Glowtree Beauty",
        "product": "Vitamin C Brightening Serum",
        "volume": "30ml",
        "target_price": "USD 2.8 / 개",
        "moq": "5,000개",
        "summary": "요청서에서 제형·성분·클레임 조건을 읽어 사내 처방 DB와 대조한 결과, 3개의 샘플 후보를 제안합니다.",
        "read_items": 14,
        "matched_formulas": 27,
        "candidates": [dict(row) for row in _SAMPLE_CANDIDATES],
        "formula": [dict(row) for row in _SAMPLE_FORMULA],
    }


def get_sample_candidate(sample_id):
    """샘플 후보 한 건을 찾는다. 없으면 첫 번째 후보를 돌려준다."""
    for row in _SAMPLE_CANDIDATES:
        if row["id"] == sample_id:
            return dict(row)
    return dict(_SAMPLE_CANDIDATES[0])


# ---------------------------------------------------------------------------
# 고객사 관리 (UI 가안)
#   메일, 바이어 요청사항, 진행 건, 메모를 한 곳에 모아 본다.
# ---------------------------------------------------------------------------

CUSTOMER_GRADE_META = {
    "vip": {"label": "VIP", "css": "vip"},
    "regular": {"label": "일반", "css": "regular"},
    "new": {"label": "신규", "css": "new"},
}

# 바이어 요청사항 분류
REQUEST_TYPE_META = {
    "formula": {"label": "제형·성분", "icon": "🧪"},
    "package": {"label": "패키지", "icon": "📦"},
    "price": {"label": "단가·수량", "icon": "💲"},
    "delivery": {"label": "납기·선적", "icon": "🚢"},
    "doc": {"label": "서류·인증", "icon": "📑"},
}

# 요청 중요도
PRIORITY_META = {
    "high": {"label": "필수", "css": "danger"},
    "mid": {"label": "권장", "css": "check"},
    "low": {"label": "참고", "css": "missing"},
}

_CUSTOMER_PROFILES = [
    {
        "id": "glowtree",
        "name": "Glowtree Beauty",
        "country": "미국",
        "flag": "🇺🇸",
        "city": "Los Angeles, CA",
        "grade": "vip",
        "manager": "홍길동",
        "since": "2024-03-11",
        "last_contact": "2026-09-16",
        "channel": "이메일 · 분기 화상회의",
        "buyer": {
            "name": "Emily Park",
            "title": "Product Director",
            "email": "emily.park@glowtree-beauty.com",
            "phone": "+1 213-555-0148",
            "timezone": "PST (한국 −16시간)",
            "language": "English",
        },
        "tags": ["무향 선호", "비건 인증 필수", "EU 확장 예정", "회신 빠름"],
        "stats": {"orders": 9, "amount": "USD 248,000", "active": 2, "avg_reply": "6시간"},
        "requests": [
            {"type": "formula", "priority": "high", "title": "전 제품 무향(fragrance-free) 유지",
             "detail": "브랜드 정체성 때문에 향료는 물론 향 마스킹 원료도 사용하지 않습니다. 원료 자체 냄새가 강하면 사전에 알려달라는 요청이 있었습니다.",
             "source": "2026-09-04 개발요청서"},
            {"type": "doc", "priority": "high", "title": "비건·크루얼티프리 인증서 원본 요구",
             "detail": "외박스에 클레임을 표기하므로 인증 기관 발행 원본 스캔본을 매 건 요구합니다.",
             "source": "2026-09-04 개발요청서"},
            {"type": "price", "priority": "high", "title": "단가는 FOB 부산 기준으로 제시",
             "detail": "과거 견적에서 조건이 달라 혼선이 있었습니다. 통화(USD)와 인코텀즈를 반드시 함께 적어달라는 요청입니다.",
             "source": "2026-06-21 이메일"},
            {"type": "package", "priority": "mid", "title": "패키지 디자인은 본사에서 별도 전달",
             "detail": "구조 사양(용기·부자재)만 먼저 확정하고 색상·라벨은 디자인팀에서 나중에 보냅니다. 통상 2~3주 늦게 옵니다.",
             "source": "2026-09-04 개발요청서"},
            {"type": "delivery", "priority": "mid", "title": "샘플은 4주 이내, 3개 이상 발송",
             "detail": "내부 품평용으로 동일 샘플을 3개씩 요청합니다. DHL 착불 계정을 사용합니다.",
             "source": "2025-11-02 이메일"},
        ],
        "emails": [
            {"date": "2026-09-16", "direction": "in", "sender": "Emily Park", "status": "확인 필요",
             "subject": "Re: Vitamin C Serum - development request",
             "summary": "레티놀 농도를 EU 기준에 맞출 수 있는지 문의. 단가 조정 폭도 함께 요청.",
             "attachments": ["Glowtree_Beauty_Development_Request.pdf"],
             "body": "Hi, thank you for the quick review.\n\nOur legal team flagged the Retinol 0.5% for the EU expansion.\nCould you propose an alternative that works for both US and EU?\nAlso, please share how much the unit price would change.\n\nBest,\nEmily"},
            {"date": "2026-09-05", "direction": "out", "sender": "홍길동", "status": "회신 완료",
             "subject": "Sample schedule for Vitamin C Serum",
             "summary": "샘플 3주 일정과 필요 정보(패키지 사양) 안내.",
             "attachments": [],
             "body": "Dear Emily,\n\nWe received the development request. The first sample will be ready in 3 weeks.\nTo proceed, we need the container specification confirmed.\n\nBest regards,\nHong"},
            {"date": "2026-09-04", "direction": "in", "sender": "Emily Park", "status": "처리 완료",
             "subject": "Product Development Request - Vitamin C Brightening Serum",
             "summary": "2027 봄 라인 비타민C 세럼 개발요청서 전달. 30ml, MOQ 5,000개.",
             "attachments": ["Glowtree_Beauty_Development_Request.pdf", "Reference_Texture.jpg"],
             "body": "Hello,\n\nPlease find attached our development request for the 2027 spring line.\nThe key points are a light watery texture and a fragrance-free formula.\n\nThanks,\nEmily"},
            {"date": "2026-08-28", "direction": "in", "sender": "Daniel Cho", "status": "처리 완료",
             "subject": "Toner revision v2 - approved",
             "summary": "토너 2차 수정본 승인. 양산 진행 요청.",
             "attachments": ["Glowtree_Toner_Revision_v2.pdf"],
             "body": "The revised toner sample was approved by our team.\nPlease proceed with mass production."},
        ],
        "projects": [
            {"name": "Vitamin C Brightening Serum 30ml", "stage": "분석·검토", "due": "2027-01 선적", "status": "check"},
            {"name": "Hydra Toner 150ml 리뉴얼", "stage": "양산 준비", "due": "2026-11 선적", "status": "delivered"},
            {"name": "Daily Cleansing Gel 200ml", "stage": "완료", "due": "2026-05 선적", "status": "analyzed"},
        ],
        "notes": [
            {"date": "2026-09-16", "author": "홍길동", "text": "EU 확장이 확정되면 레티날 대체안(샘플 B)을 먼저 제안하기로 함."},
            {"date": "2026-06-21", "author": "홍길동", "text": "견적은 항상 FOB 부산 기준으로 통일. 과거 CIF 혼선 있었음."},
            {"date": "2025-11-02", "author": "김수출", "text": "샘플은 3개씩 발송. DHL 착불 계정 사용."},
        ],
    },
    {
        "id": "lumiere",
        "name": "Lumière Skin",
        "country": "프랑스",
        "flag": "🇫🇷",
        "city": "Paris",
        "grade": "vip",
        "manager": "박무역",
        "since": "2023-09-05",
        "last_contact": "2026-09-12",
        "channel": "이메일 · 연 2회 방문",
        "buyer": {
            "name": "Camille Moreau",
            "title": "Sourcing Manager",
            "email": "c.moreau@lumiere-skin.fr",
            "phone": "+33 1 55 55 0192",
            "timezone": "CET (한국 −7시간)",
            "language": "French / English",
        },
        "tags": ["클린뷰티 인증", "CPNP 서류 요구", "프랑스어 자료 선호"],
        "stats": {"orders": 14, "amount": "EUR 412,000", "active": 1, "avg_reply": "1.5일"},
        "requests": [
            {"type": "doc", "priority": "high", "title": "CPNP 등록용 PIF 자료 사전 제공",
             "detail": "양산 전에 PIF(제품정보파일) 초안과 CPSR 안전성 평가서를 먼저 요구합니다. 통상 6주 전에 요청이 들어옵니다.",
             "source": "2026-04-10 이메일"},
            {"type": "formula", "priority": "high", "title": "EU Annex 기준 사전 대조 필수",
             "detail": "처방 확정 전에 성분별 EU 농도 제한 대조표를 보내달라고 매번 요청합니다.",
             "source": "2026-02-18 이메일"},
            {"type": "package", "priority": "mid", "title": "재활용 가능 용기 우선",
             "detail": "PCR 30% 이상 또는 유리 용기를 우선 검토합니다. 플라스틱 펌프는 사유 설명이 필요합니다.",
             "source": "2025-12-03 개발요청서"},
            {"type": "delivery", "priority": "low", "title": "8월 첫 3주는 응답 지연",
             "detail": "프랑스 하계 휴가 기간이라 회신이 늦습니다. 일정 수립 시 감안해야 합니다.",
             "source": "담당자 메모"},
        ],
        "emails": [
            {"date": "2026-09-12", "direction": "in", "sender": "Camille Moreau", "status": "회신 완료",
             "subject": "Nouvelle demande - crème nuit",
             "summary": "나이트 크림 개발요청서 전달. 레티날 저농도 사용 희망.",
             "attachments": ["Lumiere_Cream_Brief_FR.docx"],
             "body": "Bonjour,\n\nVeuillez trouver ci-joint notre demande pour une crème de nuit.\nNous souhaitons utiliser du rétinal à faible concentration.\n\nCordialement,\nCamille"},
            {"date": "2026-08-30", "direction": "out", "sender": "박무역", "status": "회신 완료",
             "subject": "PIF draft for Nuit Retinal Serum",
             "summary": "PIF 초안과 성분 대조표 송부.",
             "attachments": ["PIF_draft_v1.pdf", "EU_Annex_check.xlsx"],
             "body": "Dear Camille,\n\nPlease find the PIF draft and the EU Annex comparison sheet attached.\n\nBest regards,\nPark"},
            {"date": "2026-04-10", "direction": "in", "sender": "Camille Moreau", "status": "처리 완료",
             "subject": "CPNP documents required",
             "summary": "CPNP 등록 일정 공유 및 PIF 요청.",
             "attachments": [],
             "body": "We plan to register the product on CPNP in June.\nCould you send the PIF draft by the end of April?"},
        ],
        "projects": [
            {"name": "Nuit Retinal Serum 30ml", "stage": "샘플 확인", "due": "2026-12 선적", "status": "delivered"},
            {"name": "Crème de Nuit 50ml", "stage": "요청서 접수", "due": "미정", "status": "analyzed"},
        ],
        "notes": [
            {"date": "2026-08-30", "author": "박무역", "text": "PIF 초안은 양산 6주 전에 먼저 보내는 것이 관행으로 굳어짐."},
            {"date": "2026-02-18", "author": "박무역", "text": "성분 대조표 없이 견적만 보내면 회신이 늦어짐. 항상 같이 첨부할 것."},
        ],
    },
    {
        "id": "seoulglow",
        "name": "Seoul Glow SG",
        "country": "싱가포르",
        "flag": "🇸🇬",
        "city": "Singapore",
        "grade": "regular",
        "manager": "김수출",
        "since": "2025-01-20",
        "last_contact": "2026-09-09",
        "channel": "이메일 · 메신저",
        "buyer": {
            "name": "Wei Ling Tan",
            "title": "Category Buyer",
            "email": "weiling.tan@seoulglow.sg",
            "phone": "+65 6555 0177",
            "timezone": "SGT (한국 −1시간)",
            "language": "English / 中文",
        },
        "tags": ["소용량 키트 선호", "빠른 납기 요구", "가격 민감"],
        "stats": {"orders": 6, "amount": "USD 96,500", "active": 1, "avg_reply": "4시간"},
        "requests": [
            {"type": "package", "priority": "high", "title": "트래블 사이즈 옵션 항상 함께 제안",
             "detail": "본품과 함께 15ml 내외 소용량 버전 견적을 요구합니다. 리테일 전용관 입점 조건입니다.",
             "source": "2026-08-14 이메일"},
            {"type": "price", "priority": "high", "title": "MOQ 3,000개 조건 협의 요청",
             "detail": "초도 물량을 3,000개로 낮춰달라는 요청이 반복됩니다. 단가 상승분은 수용 가능하다는 입장입니다.",
             "source": "2026-09-09 이메일"},
            {"type": "delivery", "priority": "mid", "title": "선적 전 사진 검수 필요",
             "detail": "출고 전 포장 상태 사진을 이메일로 먼저 보내달라고 요청합니다.",
             "source": "2025-07-16 이메일"},
        ],
        "emails": [
            {"date": "2026-09-09", "direction": "in", "sender": "Wei Ling Tan", "status": "확인 필요",
             "subject": "Sunscreen spec - MOQ question",
             "summary": "선크림 사양서 전달. MOQ 3,000개 가능 여부 문의.",
             "attachments": ["SeoulGlow_Sunscreen_Spec.xlsx"],
             "body": "Hi,\n\nAttached is the spec sheet for the sunscreen.\nCan we start with 3,000 units instead of 5,000?\nWe can accept a higher unit price.\n\nThanks,\nWei Ling"},
            {"date": "2026-08-14", "direction": "in", "sender": "Wei Ling Tan", "status": "처리 완료",
             "subject": "Cushion brief + travel size",
             "summary": "쿠션 개발요청서와 트래블 사이즈 동시 견적 요청.",
             "attachments": ["SeoulGlow_Cushion_Brief.docx"],
             "body": "Please quote both the full size and a travel size (around 5g)."},
        ],
        "projects": [
            {"name": "Mineral Sunscreen 50ml", "stage": "견적 협의", "due": "2026-12 선적", "status": "check"},
            {"name": "Glow Cushion 15g", "stage": "완료", "due": "2026-07 선적", "status": "delivered"},
        ],
        "notes": [
            {"date": "2026-09-09", "author": "김수출", "text": "MOQ 3,000 조건은 단가 +8% 선에서 내부 승인 가능. 공장 확인 필요."},
            {"date": "2025-07-16", "author": "김수출", "text": "선적 전 포장 사진 검수는 필수 절차로 등록."},
        ],
    },
    {
        "id": "verde",
        "name": "Verde Botanics",
        "country": "독일",
        "flag": "🇩🇪",
        "city": "Hamburg",
        "grade": "new",
        "manager": "박무역",
        "since": "2026-06-30",
        "last_contact": "2026-09-05",
        "channel": "이메일",
        "buyer": {
            "name": "Jonas Weber",
            "title": "Purchasing Lead",
            "email": "j.weber@verde-botanics.de",
            "phone": "+49 40 5555 0133",
            "timezone": "CET (한국 −7시간)",
            "language": "German / English",
        },
        "tags": ["비건 인증 필수", "서류 꼼꼼함", "신규 거래처"],
        "stats": {"orders": 2, "amount": "EUR 38,000", "active": 1, "avg_reply": "2일"},
        "requests": [
            {"type": "doc", "priority": "high", "title": "성분별 원산지 증명 요구",
             "detail": "전 성분에 대해 원산지와 동물성 원료 미사용 확인서를 요구합니다. 준비에 2주 이상 걸립니다.",
             "source": "2026-09-05 개발요청서"},
            {"type": "formula", "priority": "mid", "title": "천연 유래 지수 90% 이상",
             "detail": "ISO 16128 기준 천연 유래 지수를 계산해 함께 제출해달라는 요청입니다.",
             "source": "2026-07-22 이메일"},
            {"type": "price", "priority": "low", "title": "견적 유효기간 명시",
             "detail": "견적서에 유효기간(통상 30일)을 반드시 적어달라고 요청했습니다.",
             "source": "2026-07-02 이메일"},
        ],
        "emails": [
            {"date": "2026-09-05", "direction": "in", "sender": "Jonas Weber", "status": "확인 필요",
             "subject": "Shampoo development request",
             "summary": "샴푸 개발요청서 전달. 천연 유래 지수 자료 함께 요청.",
             "attachments": ["Verde_Shampoo_Request_DE.pdf"],
             "body": "Sehr geehrte Damen und Herren,\n\nanbei unsere Anfrage für ein Shampoo.\nBitte senden Sie auch den Natural Origin Index nach ISO 16128.\n\nMit freundlichen Grüßen,\nJonas Weber"},
            {"date": "2026-07-22", "direction": "out", "sender": "박무역", "status": "회신 완료",
             "subject": "Body oil - certificate package",
             "summary": "바디오일 인증 서류 일괄 송부.",
             "attachments": ["Vegan_Certificate.pdf", "Origin_Declaration.pdf"],
             "body": "Dear Mr. Weber,\n\nPlease find the certificate package for the body oil attached.\n\nBest regards,\nPark"},
        ],
        "projects": [
            {"name": "Botanical Shampoo 300ml", "stage": "요청서 접수", "due": "미정", "status": "analyzed"},
            {"name": "Body Oil 100ml", "stage": "완료", "due": "2026-08 선적", "status": "delivered"},
        ],
        "notes": [
            {"date": "2026-09-05", "author": "박무역", "text": "신규 거래처. 서류 요구가 많아 리드타임을 2주 더 잡아야 함."},
        ],
    },
]


def get_customer_profiles(keyword="", grade="all"):
    """고객사 카드 목록. 회사명·바이어명·국가로 검색한다."""
    keyword = (keyword or "").strip().lower()
    rows = []
    for row in _CUSTOMER_PROFILES:
        if grade != "all" and row["grade"] != grade:
            continue
        haystack = " ".join([row["name"], row["country"], row["buyer"]["name"]]).lower()
        if keyword and keyword not in haystack:
            continue
        rows.append(dict(row))
    return rows


def get_customer_profile(customer_id):
    """고객사 상세 한 건. 없으면 None."""
    for row in _CUSTOMER_PROFILES:
        if row["id"] == customer_id:
            return dict(row)
    return None


def get_customer_summary():
    """고객사 관리 상단 요약 숫자."""
    profiles = _CUSTOMER_PROFILES
    return {
        "total": len(profiles),
        "vip": sum(1 for row in profiles if row["grade"] == "vip"),
        "active": sum(row["stats"]["active"] for row in profiles),
        "unread": sum(
            1
            for row in profiles
            for mail in row["emails"]
            if mail["status"] == "확인 필요"
        ),
    }
