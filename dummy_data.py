# -*- coding: utf-8 -*-
"""To-do Trade - 더미 데이터 (UI 가안)

실제 OCR/LLM/번역 연동 없이 화면만 확인하기 위한 가짜 데이터.
나중에 실제 로직으로 교체하기 쉽도록 전부 함수로 감싸 두었다.

예외: 국가별 규제 검색의 EU 판정은 reg_store 를 통해 실제 법령 데이터를 쓴다.
(regdata/sync_eu.py 로 수집. DB가 없으면 자동으로 더미로 돌아간다.)
"""

import json
import zlib
from datetime import date

import company_store
import customer_store
import mix_store
import reg_store
import reg_timeline
import retail_std
import us_reg_store

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

# ---------------------------------------------------------------------------
# 개발요청서 양식
# ---------------------------------------------------------------------------
#   개발요청서는 대부분 **엑셀 양식**으로 온다. 줄글로 써 보내는 곳은 드물다.
#   항목(Item) | 내용(Content) 두 칸짜리 표에 구획이 몇 개 나뉜 모양이 표준에 가깝다.
#   그래서 '원문 미리보기' 도 줄글이 아니라 표로 보여 준다.
#
#   key 가 있으면 우리 항목 목록에 대응되는 줄이고,
#   key 가 비어 있으면 **목록에 없는 줄**이다.
#   그런 줄이 늘 몇 개씩 있는데, 지금까지는 읽고도 버렸다.
#   버리면 바이어가 적어 보낸 요구가 통째로 사라진다. 그래서 '기타' 로 모은다.

SAMPLE_FORM = [
    {"section": "1. Product Overview", "rows": [
        {"no": "1-1", "label": "Product Name", "key": "product_name"},
        {"no": "1-2", "label": "Product Type", "key": "product_type"},
        {"no": "1-3", "label": "Volume", "key": "volume"},
        {"no": "1-4", "label": "Primary Container", "key": "container"},
        {"no": "1-5", "label": "Launch Market", "key": "target_country"},
        {"no": "1-6", "label": "Launch Season",
         "value": "2027 Spring (March)"},
        {"no": "1-7", "label": "Brand Concept",
         "value": "Clean, dermatologist-tested daily brightening"},
        {"no": "1-8", "label": "Target Consumer",
         "value": "Women 25-34, sensitive skin, US West Coast"},
    ]},
    {"section": "2. Texture & Sensory", "rows": [
        {"no": "2-1", "label": "Texture", "key": "texture"},
        {"no": "2-2", "label": "Fragrance", "key": "fragrance"},
        {"no": "2-3", "label": "Benchmark Product", "key": "benchmark"},
    ]},
    {"section": "3. Formula", "rows": [
        {"no": "3-1", "label": "Key Actives", "key": "key_ingredients"},
        {"no": "3-2", "label": "Free-from", "key": "free_from"},
        {"no": "3-3", "label": "Shelf Life (requested)",
         "value": "36 months unopened / 12M PAO"},
        {"no": "3-4", "label": "pH Range (requested)",
         "value": "5.0 - 6.0"},
    ]},
    {"section": "4. Claims & Certification", "rows": [
        {"no": "4-1", "label": "Claims", "key": "claims"},
        {"no": "4-2", "label": "Required Documents", "key": "documents"},
        {"no": "4-3", "label": "Animal Testing Policy",
         "value": "No animal testing at any stage, including raw materials. "
                  "Written declaration required."},
    ]},
    {"section": "5. Packaging", "rows": [
        {"no": "5-1", "label": "Container Supply", "key": "container_supply"},
        {"no": "5-2", "label": "Color / Artwork", "key": "package_design"},
        {"no": "5-3", "label": "Artwork Due Date",
         "value": "To be shared by 2026-11-15"},
    ]},
    {"section": "6. Commercial Terms", "rows": [
        {"no": "6-1", "label": "Order Quantity (MOQ)", "key": "moq"},
        {"no": "6-2", "label": "Target Unit Price", "key": "target_price"},
        {"no": "6-3", "label": "Incoterms", "key": "trade_terms"},
        {"no": "6-4", "label": "Delivery", "key": "delivery"},
        {"no": "6-5", "label": "Target Retail Price (RRP)",
         "value": "USD 32.00"},
        {"no": "6-6", "label": "Sample Quantity",
         "value": "3 pcs per round, DHL collect (acct. 9xxxxx)"},
    ]},
    {"section": "7. Contact", "rows": [
        {"no": "7-1", "label": "Requested By", "key": "responsible_person"},
        {"no": "7-2", "label": "Remarks",
         "value": "Please quote filling and secondary packaging only. "
                  "We will confirm the EU expansion plan after the US launch."},
    ]},
]


def _form_rows(items):
    """양식을 화면에 뿌릴 모양으로 편다.

    표의 줄 하나가 우리 항목 하나에 대응되면 그 값을 가져다 쓰고,
    대응되는 항목이 없으면 **그대로 둔 채 '목록에 없음' 으로 표시**한다.
    """
    by_key = {row["key"]: row for row in items}
    sections = []
    extra = []
    for block in SAMPLE_FORM:
        rows = []
        for raw in block["rows"]:
            key = raw.get("key", "")
            item = by_key.get(key) if key else None
            row = {
                "no": raw["no"],
                "label": raw["label"],
                "key": key,
                "mapped": bool(item),
                "value": (item["value"] if item else raw.get("value", "")),
                "item_label": item["label"] if item else "",
                "status": item["status"] if item else "extra",
            }
            rows.append(row)
            if not item:
                extra.append(row)
        sections.append({"section": block["section"], "rows": rows})
    return sections, extra


def _form_as_text(sections):
    """표를 글자로. 전달 문서·프로젝트에 원문으로 남길 때 쓴다."""
    lines = []
    for block in sections:
        lines.append(block["section"])
        for row in block["rows"]:
            lines.append("  {}  {} : {}".format(
                row["no"], row["label"], row["value"] or "(빈칸)"))
        lines.append("")
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# 요청 성분 (행 단위)
#   "핵심 성분" 한 칸에 문자열로 뭉쳐 두면 규제 판정에 넘길 수 없다.
#   성분명 / INCI / 함량 을 따로 들고 있어야 reg_store 로 국가별 판정을 걸 수 있다.
#   TODO: 실제 연동 (LLM 성분·함량 추출)
# ---------------------------------------------------------------------------

_CORE_ACTIVES_SOURCE = (
    "Please include Ascorbyl Glucoside at 2.0%, Niacinamide at 5.0% "
    "and Sodium Hyaluronate at 1.0% as the core actives."
)

_REQUEST_INGREDIENTS = [
    {
        "name": "비타민C 유도체",
        "inci": "Ascorbyl Glucoside",
        "amount": "2.0%",
        "role": "브라이트닝",
        "source": _CORE_ACTIVES_SOURCE,
    },
    {
        "name": "나이아신아마이드",
        "inci": "Niacinamide",
        "amount": "5.0%",
        "role": "브라이트닝·장벽",
        "source": _CORE_ACTIVES_SOURCE,
    },
    {
        "name": "히알루론산",
        "inci": "Sodium Hyaluronate",
        "amount": "1.0%",
        "role": "보습",
        "source": _CORE_ACTIVES_SOURCE,
    },
    {
        "name": "레티놀",
        "inci": "Retinol",
        "amount": "0.5%",
        "role": "나이트케어",
        "source": "We also want Retinol at 0.5% for the night-care claim.",
    },
    {
        "name": "페녹시에탄올",
        "inci": "Phenoxyethanol",
        "amount": "0.8%",
        "role": "방부",
        "source": "Please use Phenoxyethanol at 0.8% as the preservative system.",
    },
]

# 실데이터가 없을 때 쓰는 규제 판정 (가안 더미)
_FALLBACK_VERDICTS = {
    "Retinol": {
        "status": "ban",
        "limit": "리브온 0.3% 이하",
        "rule": "Regulation (EU) 2024/996",
        "note": "요청 0.5%는 EU 기준 초과 가능성 — 규제 데이터를 수집하면 실제 기준으로 판정합니다.",
    },
}


def analyze_ingredients():
    """요청 성분에 EU 판정을 붙여 돌려준다.

    regdata/regulation.db 가 있으면 실제 법령으로 판정하고,
    없으면 더미 판정으로 돌아간다.
    """
    live = reg_store.is_available()
    rows = []

    for ing in _REQUEST_INGREDIENTS:
        verdict = reg_store.judge(ing["name"], ing["inci"], None, ing["amount"])
        if verdict is None:
            verdict = dict(_FALLBACK_VERDICTS.get(ing["inci"], {
                "status": "ok",
                "limit": "-",
                "rule": "-",
                "note": "규제 데이터가 아직 수집되지 않았습니다.",
            }))
            verdict.setdefault("annex", "")

        row = dict(ing)
        row.update({
            "status": verdict["status"],
            "limit": verdict["limit"],
            "rule": verdict["rule"],
            "note": verdict["note"],
            "annex": verdict.get("annex", ""),
            "live": live,
        })
        rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# 추출 항목 19개
#   status: confirmed(확인됨) / check(확인 필요) / missing(누락)
# ---------------------------------------------------------------------------

_EXTRACTED_ITEMS = [
    {
        "key": "product_name",
        "label": "제품명",
        "value": "Vitamin C Brightening Serum (비타민C 브라이트닝 세럼)",
        "status": "confirmed",
        "source": "We would like to request the development of a Vitamin C Brightening Serum for our 2027 spring line.",
        "note": "",
    },
    {
        "key": "product_type",
        "label": "제품 유형",
        "value": "리브온 페이셜 세럼",
        "status": "confirmed",
        "source": "The product is a leave-on facial serum filled in a 30ml glass dropper bottle.",
        "note": "",
    },
    {
        "key": "volume",
        "label": "용량",
        "value": "30ml",
        "status": "confirmed",
        "source": "The product is a leave-on facial serum filled in a 30ml glass dropper bottle.",
        "note": "",
    },
    {
        "key": "container",
        "label": "용기",
        "value": "유리 스포이드 병",
        "status": "confirmed",
        "source": "The product is a leave-on facial serum filled in a 30ml glass dropper bottle.",
        "note": "",
    },
    {
        "key": "moq",
        "label": "MOQ",
        "value": "5,000개 (초도 물량)",
        "status": "confirmed",
        "source": "MOQ is 5,000 units for the first order.",
        "note": "",
    },
    {
        "key": "target_price",
        "label": "목표 단가",
        "value": "2.8 / 개",
        "status": "check",
        "source": "Our target unit price is 2.8 per piece.",
        "note": "통화 표기가 없고 FOB/CIF 등 거래 조건도 불명확 — 고객사 확인 필요",
    },
    {
        "key": "texture",
        "label": "텍스처",
        "value": "가벼운 워터리, 빠른 흡수 / 끈적임 없음",
        "status": "confirmed",
        "source": "The texture should be light and watery, absorbing quickly without any sticky finish.",
        "note": "",
    },
    {
        "key": "fragrance",
        "label": "향",
        "value": "무향 (fragrance-free)",
        "status": "confirmed",
        "source": "The formula must be fragrance-free.",
        "note": "",
    },
    {
        "key": "key_ingredients",
        "label": "핵심 성분",
        "value": "Ascorbyl Glucoside 2.0%, Niacinamide 5.0%, Sodium Hyaluronate 1.0%, Retinol 0.5%, Phenoxyethanol 0.8%",
        "status": "check",
        "source": _CORE_ACTIVES_SOURCE,
        "note": "성분별 판정은 아래 '성분별 규제 판정' 표를 확인하세요.",
    },
    {
        "key": "benchmark",
        "label": "벤치마크 제품",
        "value": 'Dewy Lab "Glow Drop Serum" (미국, 2025) — 슬립감·매트 마무리',
        "status": "confirmed",
        "source": 'For the overall sensory target, please benchmark Dewy Lab "Glow Drop Serum" (US, 2025) - we like its slip and matte finish.',
        "note": "",
    },
    {
        "key": "free_from",
        "label": "배제 성분",
        "value": "Parabens, Sulfates, Mineral oil, Synthetic fragrance",
        "status": "confirmed",
        "source": "The formula must be free from Parabens, Sulfates, Mineral oil and Synthetic fragrance.",
        "note": "",
    },
    {
        "key": "claims",
        "label": "인증·클레임",
        "value": "Vegan, Cruelty-free (외박스 표기)",
        "status": "confirmed",
        "source": "We hope to use Vegan and Cruelty-free claims on the outer box.",
        "note": "",
    },
    {
        "key": "target_country",
        "label": "판매 국가",
        "value": "미국(1차) → EU(확장 예정)",
        "status": "confirmed",
        "source": "Our first launch market is the United States, and we plan to expand to the EU afterwards.",
        "note": "",
    },
    {
        "key": "delivery",
        "label": "납기",
        "value": "샘플 4주 이내 / 본생산 선적 2027년 1월",
        "status": "check",
        "source": "Please send the first sample within 4 weeks, and mass production shipment is expected in January 2027.",
        "note": "선적 조건(FOB/CIF)과 도착 항구가 명시되지 않음 — 확인 필요",
    },
    {
        "key": "package_design",
        "label": "패키지 디자인",
        "value": "",
        "status": "missing",
        "source": "Package color and label design will be shared later.",
        "note": "원문에 '추후 전달'로만 적혀 있어 값 없음",
    },
    {
        "key": "container_supply",
        "label": "용기 사급/자급",
        "value": "사급 — 유리 스포이드 병·단상자를 고객사가 지급",
        "status": "confirmed",
        "source": "The glass dropper bottle and the outer box will be supplied by us, so please quote filling and secondary packaging only.",
        "note": "견적 범위가 충전·2차 포장으로 한정됩니다.",
    },
    {
        "key": "trade_terms",
        "label": "거래조건",
        "value": "결제 조건 '기존과 동일' / 통화·Incoterms 미기재",
        "status": "check",
        "source": "Payment will follow our standard terms as usual.",
        "note": "통화(USD 추정), Incoterms(FOB/CIF), 결제 조건을 문서로 확정해야 합니다.",
    },
    {
        "key": "documents",
        "label": "필요 서류",
        "value": "CoA, MSDS, 비동물실험 확인서 (초도 선적 시)",
        "status": "check",
        "source": "Please prepare CoA, MSDS and a non-animal testing statement together with the first shipment.",
        "note": "EU 확장 시 CPSR·PIF, 국가별 Free Sale Certificate가 추가로 필요합니다.",
    },
    {
        "key": "responsible_person",
        "label": "책임자 지정",
        "value": "",
        "status": "missing",
        "source": "",
        "note": "EU 역내 책임자(RP)와 미국 MoCRA 책임자 지정 여부가 원문에 없습니다. 미지정 시 판매 불가.",
    },
]

# 상태 뱃지 (템플릿에서 사용)
STATUS_META = {
    "confirmed": {"label": "확인됨", "css": "confirmed"},
    "check": {"label": "확인 필요", "css": "check"},
    "missing": {"label": "누락", "css": "missing"},
}

def analyze_document(file=None):
    """업로드된 문서를 분석한 '척' 하고 더미 결과를 돌려준다.

    항목 추출은 더미지만, 성분별 규제 판정은 reg_store 의 실데이터를 쓴다.

    TODO: 실제 연동 (OCR + LLM 항목 추출)
    """
    items = [dict(item) for item in _EXTRACTED_ITEMS]
    sections, extra = _form_rows(items)

    # 어느 줄에서 읽었는지를 양식 기준으로 다시 붙인다.
    # "6쪽 3번째 문장" 이 아니라 "6-2 Target Unit Price" 라고 말해야 찾는다.
    where = {row["key"]: row for block in sections for row in block["rows"]
             if row["key"]}
    for item in items:
        row = where.get(item["key"])
        item["row"] = row["no"] if row else ""
        item["source"] = ("{} · {}".format(row["no"], row["label"]) if row
                          else "양식에 해당 칸이 없습니다")

    ingredients = analyze_ingredients()
    flagged = [i for i in ingredients if i["status"] in ("warn", "ban")]

    return {
        "file_name": file or "Glowtree_Beauty_개발의뢰서.xlsx",
        "customer": "Glowtree Beauty",
        "customer_country": "미국",
        "detected_language": "English",
        "form": sections,
        "form_rows": sum(len(b["rows"]) for b in sections),
        # 읽었지만 항목 목록에 없는 줄. 버리지 않고 여기 모은다
        "extra": extra,
        "extra_count": len(extra),
        "source_text": _form_as_text(sections),
        "items": items,
        "item_count": len(items),
        "check_count": sum(1 for i in items if i["status"] == "check"),
        "missing_count": sum(1 for i in items if i["status"] == "missing"),
        "ingredients": ingredients,
        "ingredient_count": len(ingredients),
        "regulation_notes": flagged,
        "regulation_count": len(flagged),
        "regulation_live": reg_store.is_available(),
        "regulation_source": get_reg_source(),
    }


# ---------------------------------------------------------------------------
# 내부 전달 문서 (연구소용 / 공장용)
#   문서 구조는 한 번만 정의하고 언어별 사전에서 문구를 꺼내 쓴다.
#   ko/en 은 전부 번역, zh/vi 는 일부만 번역(없으면 en 으로 대체).
# ---------------------------------------------------------------------------

_LAB_STRUCTURE = [
    {"key": "overview", "rows": ["product_name", "product_type", "target_country", "background"]},
    {"key": "sensory", "rows": ["texture", "fragrance", "color", "benchmark"]},
    {"key": "ingredients", "rows": ["key_ingredients", "free_from"]},
    {"key": "claims", "rows": ["claims"]},
    {"key": "tests", "rows": ["test_stability", "test_irritation"]},
    {"key": "regulation", "rows": ["regulation_note"]},
]

# 공장은 '생산'이다. 만들 수 있는지 판단하는 데 필요한 것만 넣는다.
#   - 뺀 것: 목표 단가·거래조건·선적 조건
#     고객사와의 협상 조건이라 공장이 볼 이유가 없고, 목표 단가를 먼저 보여주면
#     원가 산출이 그 숫자에 끌려간다. 영업이 확정할 항목으로 옮겼다(_SALES_STRUCTURE).
#   - 남긴 것: 언제까지 만들어 출고해야 하는지(샘플 납기·본생산 선적)는 생산 일정이다.
_FACTORY_STRUCTURE = [
    {"key": "spec", "rows": ["product_name", "volume", "container", "accessory", "container_supply"]},
    {"key": "quantity", "rows": ["moq"]},
    {"key": "delivery", "rows": ["sample_due", "mass_shipment"]},
    {"key": "packaging", "rows": ["package_design", "label"]},
    {"key": "documents", "rows": ["documents", "responsible_person"]},
]

# 연구소에도 공장에도 보내지 않는 항목. 영업이 직접 확정해야 하는 거래 조건이다.
# (요청서에 모호하게 적혀 오는 자리라 '확인 필요' 가 붙어 있다)
_SALES_STRUCTURE = [
    {"key": "sales_terms", "rows": ["target_price", "trade_terms", "shipping_terms"]},
]

_DOC_TITLES = {
    "lab": {
        "ko": "연구소 전달용 개발 의뢰서",
        "en": "Product Development Brief for R&D Lab",
        "zh": "研究所开发委托书",
        "vi": "Phiếu yêu cầu phát triển (Phòng R&D)",
    },
    "sales": {
        "ko": "영업 확정 필요 항목",
        "en": "Items for Sales to Confirm",
        "zh": "营业需确认事项",
        "vi": "Hạng mục kinh doanh cần xác nhận",
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
        "quantity": "발주 수량",
        "delivery": "생산·출고 일정",
        "sales_terms": "영업이 확정할 거래 조건",
        "packaging": "포장·라벨 요구사항",
        "documents": "서류·책임자",
    },
    "en": {
        "overview": "Product Overview",
        "sensory": "Texture & Sensory Requirements",
        "ingredients": "Ingredient Requirements",
        "claims": "Claims & Certification",
        "tests": "Requested Tests",
        "regulation": "Regulatory Notes",
        "spec": "Product Specification",
        "quantity": "Order Quantity",
        "delivery": "Production & Shipment Schedule",
        "sales_terms": "Commercial Terms (Sales to confirm)",
        "packaging": "Packaging & Label",
        "documents": "Documents & Responsible Person",
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
        "documents": "文件·责任人",
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
        "documents": "Hồ sơ · Người chịu trách nhiệm",
    },
}

_FIELD_LABELS = {
    "ko": {
        "product_name": "제품명",
        "product_type": "제품 유형",
        "target_country": "타깃 국가",
        "background": "요청·기획 배경",
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
        "benchmark": "벤치마크 제품",
        "container_supply": "용기 사급/자급",
        "trade_terms": "거래조건",
        "documents": "필요 서류",
        "responsible_person": "책임자 지정",
    },
    "en": {
        "product_name": "Product Name",
        "product_type": "Product Type",
        "target_country": "Target Market",
        "background": "Background",
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
        "benchmark": "Benchmark Product",
        "container_supply": "Packaging Supply",
        "trade_terms": "Trade Terms",
        "documents": "Required Documents",
        "responsible_person": "Responsible Person",
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
        "background": "고객사 2027년 봄 라인 신제품 요청",
        "texture": "가볍고 워터리한 제형, 빠른 흡수 / 끈적임 없을 것",
        "fragrance": "무향 (fragrance-free)",
        "color": "미정 — 고객사가 추후 전달 예정",
        "key_ingredients": "Ascorbyl Glucoside 2.0%, Niacinamide 5.0%, Sodium Hyaluronate 1.0%, Retinol 0.5%, Phenoxyethanol 0.8%",
        "free_from": "Parabens, Sulfates, Mineral oil, Synthetic fragrance",
        "claims": "Vegan, Cruelty-free (외박스 표기 희망)",
        "test_stability": "가속 안정성 시험 요청 (45도 4주 기준)",
        "test_irritation": "인체적용 피부자극 시험 결과 요청",
        "regulation_note": "Retinol 0.5% — EU Annex III No.376 기준(바디로션 0.05% / 그 외 리브온 0.3%) 초과. EU 확장 시 배합 변경 필요",
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
        "benchmark": "Dewy Lab \"Glow Drop Serum\" (미국, 2025) — 슬립감과 매트한 마무리를 기준으로 삼을 것",
        "container_supply": "사급 — 유리 스포이드 병·단상자는 고객사 지급, 견적 범위는 충전·2차 포장",
        "trade_terms": "결제 조건 '기존과 동일' 표기 / 통화·Incoterms 미기재 — 확정 필요",
        "documents": "CoA, MSDS, 비동물실험 확인서 (초도 선적 동봉) / EU 확장 시 CPSR·PIF 추가",
        "responsible_person": "미지정 — EU 역내 책임자(RP), 미국 MoCRA 책임자 확인 필요",
    },
    "en": {
        "product_name": "Vitamin C Brightening Serum",
        "product_type": "Leave-on facial serum",
        "target_country": "United States first, EU expansion planned",
        "background": "Customer request for the 2027 spring line",
        "texture": "Light watery texture, fast absorbing, no sticky finish",
        "fragrance": "Fragrance-free",
        "color": "TBD - to be shared by the customer later",
        "key_ingredients": "Ascorbyl Glucoside 2.0%, Niacinamide 5.0%, Sodium Hyaluronate 1.0%, Retinol 0.5%, Phenoxyethanol 0.8%",
        "free_from": "Parabens, Sulfates, Mineral oil, Synthetic fragrance",
        "claims": "Vegan, Cruelty-free (to be printed on the outer box)",
        "test_stability": "Accelerated stability test requested (45C, 4 weeks)",
        "test_irritation": "Human skin irritation test report requested",
        "regulation_note": "Retinol 0.5% - exceeds EU Annex III No.376 limit (0.05% body lotion / 0.3% other leave-on); reformulation needed for EU",
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
        "benchmark": "Dewy Lab \"Glow Drop Serum\" (US, 2025) - match its slip and matte finish",
        "container_supply": "Customer-supplied - glass dropper bottle and outer box; quote covers filling and secondary packaging only",
        "trade_terms": "Payment stated as 'standard terms' / currency and Incoterms not specified - to be confirmed",
        "documents": "CoA, MSDS, non-animal testing statement with first shipment / CPSR and PIF required for EU",
        "responsible_person": "Not assigned - EU Responsible Person and US MoCRA responsible person to be confirmed",
    },
    "zh": {
        "product_name": "维生素C亮白精华",
        "product_type": "驻留型面部精华",
        "target_country": "优先美国市场，之后扩展至欧盟",
        "texture": "轻盈水感质地，吸收快，不黏腻",
        "fragrance": "无香 (fragrance-free)",
        "key_ingredients": "Ascorbyl Glucoside 2.0%, Niacinamide 5.0%, Sodium Hyaluronate 1.0%, Retinol 0.5%, Phenoxyethanol 0.8%",
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
        "key_ingredients": "Ascorbyl Glucoside 2.0%, Niacinamide 5.0%, Sodium Hyaluronate 1.0%, Retinol 0.5%, Phenoxyethanol 0.8%",
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
    "key_ingredients": _CORE_ACTIVES_SOURCE + " We also want Retinol at 0.5% for the night-care claim.",
    "benchmark": 'For the overall sensory target, please benchmark Dewy Lab "Glow Drop Serum" (US, 2025) - we like its slip and matte finish.',
    "container_supply": "The glass dropper bottle and the outer box will be supplied by us, so please quote filling and secondary packaging only.",
    "trade_terms": "Payment will follow our standard terms as usual.",
    "documents": "Please prepare CoA, MSDS and a non-animal testing statement together with the first shipment.",
    "responsible_person": "(원문에 명시 없음 — 지정 필요)",
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
    "trade_terms": "check",
    "documents": "check",
    "color": "missing",
    "accessory": "missing",
    "package_design": "missing",
    "responsible_person": "missing",
}


def _pick(table, lang, key):
    """해당 언어에 문구가 없으면 en → ko 순으로 대체한다."""
    for candidate in (lang, "en", "ko"):
        value = table.get(candidate, {}).get(key)
        if value:
            return value
    return key


def _build_document(structure, doc_kind, result, lang, overrides=None):
    """문서 한 벌을 만든다.

    overrides 가 있으면(영업이 직접 작성한 요청서) 그 값을 우선 쓴다.
    직접 쓴 문장은 번역 사전에 없으므로 언어와 무관하게 그대로 싣는다.
    """
    lang = lang if lang in {row["code"] for row in LANGUAGES} else "ko"
    overrides = overrides or {}
    sections = []
    for block in structure:
        rows = []
        for row_key in block["rows"]:
            written = (overrides.get(row_key) or "").strip()
            rows.append({
                "key": row_key,
                "label": _pick(_FIELD_LABELS, lang, row_key),
                "value": written or _pick(_FIELD_VALUES, lang, row_key),
                "source": "(영업 담당자 직접 작성)" if written else _FIELD_SOURCES.get(row_key, ""),
                "flag": "" if written else _FIELD_FLAGS.get(row_key, ""),
                "written": bool(written),
            })
        sections.append(
            {
                "key": block["key"],
                "heading": _pick(_SECTION_HEADINGS, lang, block["key"]),
                "rows": rows,
            }
        )

    result = result or {}
    titles = _DOC_TITLES[doc_kind]
    customer = overrides.get("_requester") or result.get("customer", "Glowtree Beauty")
    return {
        "kind": doc_kind,
        "lang": lang,
        "title": titles.get(lang) or titles["en"],
        "customer": customer,
        # 받는 쪽은 고객사를 모른다. 문서 맨 앞에 소개를 붙인다.
        "brief": customer_brief(customer, doc_kind),
        "origin": overrides.get("_origin", ""),
        "background": overrides.get("background", ""),
        "file_name": result.get("file_name", ""),
        "sections": sections,
    }


# 문서를 받는 쪽이 알아야 할 고객사 요청 타입.
#   연구소는 단가·납기를 몰라도 되고, 공장은 처방 요구를 몰라도 된다.
_BRIEF_REQUEST_TYPES = {
    "lab": ("formula", "doc"),
    "factory": ("package", "delivery", "doc"),
}


def customer_brief(customer_name, doc_kind="lab"):
    """연구소·공장에 붙이는 고객사 소개.

    문서를 받는 쪽은 고객사를 모른다. 왜 무향을 고집하는지, 인증서를 왜 매번
    원본으로 요구하는지 모르면 같은 질문이 영업으로 다시 돌아온다.
    해외영업이 고객사를 설명해 주는 자리다.

    고객사 관리(12-4)에 등록된 곳이면 그 값을 끌어오고,
    등록되지 않은 곳이면 이름만 넣은 빈 소개를 돌려준다.
    """
    name = (customer_name or "").strip()
    profile = next((row for row in _CUSTOMER_PROFILES
                    if row["name"].lower() == name.lower()), None)

    if profile is None:
        return {
            "name": name or "(고객사 미지정)",
            "known": False,
            "summary": "",
            "tags": [],
            "notes": [],
        }

    grade = CUSTOMER_GRADE_META.get(profile["grade"], {}).get("label", "")
    summary = "{} {} · {} 등급 · {} 거래 시작 · 누적 발주 {}건({})".format(
        profile["flag"], profile["city"], grade, profile["since"],
        profile["stats"]["orders"], profile["stats"]["amount"])

    # 받는 쪽이 알아야 할 반복 요청만. 중요한 것부터.
    wanted = _BRIEF_REQUEST_TYPES.get(doc_kind, ())
    order = {"high": 0, "mid": 1, "low": 2}
    picked = sorted([r for r in profile["requests"] if r["type"] in wanted],
                    key=lambda r: order.get(r["priority"], 9))[:3]

    return {
        "name": profile["name"],
        "known": True,
        "id": profile["id"],
        "country": profile["country"],
        "flag": profile["flag"],
        "grade": grade,
        "summary": summary,
        "channel": profile["channel"],
        "manager": profile["manager"],
        "tags": list(profile["tags"]),
        "notes": [{"title": r["title"], "detail": r["detail"],
                   "type": REQUEST_TYPE_META.get(r["type"], {}).get("label", ""),
                   "icon": REQUEST_TYPE_META.get(r["type"], {}).get("icon", ""),
                   "priority": r["priority"]}
                  for r in picked],
    }


def convert_for_lab(result, lang="ko", overrides=None):
    """분석 결과를 연구소용 문서로 변환한 척 한다.

    TODO: 실제 연동 (LLM 문서 변환 + 번역)
    """
    return _build_document(_LAB_STRUCTURE, "lab", result, lang, overrides)


def convert_for_factory(result, lang="ko", overrides=None):
    """분석 결과를 공장용 문서로 변환한 척 한다.

    TODO: 실제 연동 (LLM 문서 변환 + 번역)
    """
    return _build_document(_FACTORY_STRUCTURE, "factory", result, lang, overrides)


def sales_terms(result, lang="ko", overrides=None):
    """연구소·공장 어디에도 안 보내고 영업이 직접 확정할 항목.

    단가·결제조건·선적조건은 고객사와의 협상 영역이다. 공장에 넘기면
    원가 산출이 목표 단가에 끌려가고, 연구소는 볼 이유가 없다.
    """
    return _build_document(_SALES_STRUCTURE, "sales", result, lang, overrides)


# ---------------------------------------------------------------------------
# 처리 이력
# ---------------------------------------------------------------------------

_HISTORY = [
    {
        "id": 1,
        "date": "2026-09-16",
        "customer": "Glowtree Beauty",
        "file_name": "Glowtree_Beauty_개발의뢰서.xlsx",
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


# 규정 변경 표는 지역 이름으로 적혀 있다 (EU / 미국)
TIMELINE_REGION = {"eu": "EU", "us": "미국"}


def get_reg_countries():
    """규제 검색 대상 국가 목록."""
    return [dict(row) for row in _REG_COUNTRIES]


def get_reg_country(code):
    """국가 코드로 규제 개요 한 건을 찾는다. 없으면 None."""
    for row in _REG_COUNTRIES:
        if row["code"] == code:
            return dict(row)
    return None


def reg_ingredient_rows():
    """규제 대조에 올릴 성분 줄.

    성분표에서 바로 읽은 것 + **복합 원료를 쪼개 넣은 것**.
    쪼개지 않으면 그 원료 몫(3%)이 대조에서 통째로 빠진다.
    안에 레티놀이 들어 있어도 모른 채 지나간다.
    """
    rows = [dict(item) for item in _REG_INGREDIENTS]
    for raw in _REG_UNMATCHED:
        rows.extend(mix_store.as_ingredients(raw["name"]))
    return rows


def search_regulations(country="all", keyword="", status="all"):
    """국가 / 성분명 / 상태로 규제를 검색한다.

    EU는 regdata/regulation.db 가 있으면 실제 법령(Regulation (EC) No 1223/2009
    통합본)으로 판정하고, 나머지 국가는 아직 더미다.

    TODO: 실제 연동 (한국 MFDS 오픈API, 일본 e-Gov 법령API, 중국·베트남 수기 테이블)
    """
    keyword = (keyword or "").strip().lower()
    codes = [country] if country != "all" else [row["code"] for row in _REG_COUNTRIES]
    eu_live = reg_store.is_available()
    eu_version = (reg_store.get_meta() or {}).get("version_date", "") if eu_live else ""
    us_live = us_reg_store.is_available()
    us_version = (us_reg_store.get_meta() or {}).get("cfr_date", "") if us_live else ""

    rows = []
    for item in reg_ingredient_rows():
        haystack = " ".join([item["name"], item["inci"], item["category"]]).lower()
        if keyword and keyword not in haystack:
            continue

        for code in codes:
            version = ""
            if code == "eu" and eu_live:
                rule = reg_store.judge(
                    item["name"], item["inci"], item.get("cas"), item["requested"]
                )
                live, version = True, eu_version
            elif code == "us" and us_live:
                # 미국은 연방규정집(eCFR) 원문으로 판정한다
                rule = us_reg_store.judge(
                    item["name"], item["inci"], item.get("cas"), item["requested"]
                )
                live, version = True, us_version
            else:
                rule = item["rules"].get(code)
                live = False

            if not rule:
                continue
            if status != "all" and rule["status"] != status:
                continue

            # 미국은 법 말고도 팔리느냐가 갈린다.
            #   OTC 로 갈리면 화장품으로 못 팔고,
            #   리테일러 배제 목록에 걸리면 그 매장에 못 들어간다.
            badges = []
            if code == "us":
                otc = us_reg_store.otc_of(item["name"], item["inci"],
                                          item["requested"])
                if otc:
                    meta = us_reg_store.OTC_LEVELS[otc["level"]]
                    badges.append({"kind": "otc", "css": meta["css"],
                                   "label": meta["label"], "why": otc["why"]})
                for std in retail_std.STANDARDS:
                    found = retail_std.check_ingredient(
                        std["key"], item["name"], item["inci"], item["requested"])
                    if found and not found["unused"]:
                        badges.append({
                            "kind": "retail",
                            "css": "soft" if found["soft"] else "fail",
                            "label": "{} {}".format(std["icon"], found["group"]),
                            "why": "{} — {}".format(std["name"], found["why"]),
                        })

            # 지금 적합해도 시행일이 남아 있으면 개발 기간 안에 걸린다.
            #   화장품은 개발~출시가 6개월~1년이라 그 사이에 시행일이 들어온다.
            timeline = reg_timeline.for_ingredient(
                item["name"], item["inci"],
                region=TIMELINE_REGION.get(code)) if code in TIMELINE_REGION else []

            country_row = get_reg_country(code) or {}
            rows.append(
                {
                    "key": "{}-{}".format(item["key"], code),
                    "name": item["name"],
                    "inci": item["inci"],
                    "category": item["category"],
                    "requested": item["requested"],
                    "updated": version if live else item["updated"],
                    "country_code": code,
                    "country_name": country_row.get("name", code),
                    "country_flag": country_row.get("flag", ""),
                    "status": rule["status"],
                    "limit": rule["limit"],
                    # 안 넣은 성분이면 화면에서 기준 칸을 흐리게 둔다
                    "unused": bool(rule.get("unused")),
                    "limit_if_used": rule.get("limit_if_used", ""),
                    "rule": rule["rule"],
                    "note": rule["note"],
                    "live": live,
                    "annex": rule.get("annex", ""),
                    "badges": badges,
                    "timeline": timeline,
                    # 복합 원료를 쪼개 넣은 줄이면 어디서 왔는지 적는다
                    "from_mix": item.get("from_mix", ""),
                    "mix_ratio": item.get("mix_ratio", ""),
                    "mix_dose": item.get("mix_dose", ""),
                }
            )

    return rows


def us_sales_board():
    """미국 판매 관점 요약. 규제와 매장 기준은 성격이 달라 따로 적는다."""
    rows = [{"name": r["name"], "inci": r["inci"], "requested": r["requested"]}
            for r in reg_ingredient_rows()]
    return {
        "rows": len(rows),
        "otc": us_reg_store.otc_verdict(rows),
        "retail": retail_std.all_verdicts(rows),
    }


def get_us_reg_source():
    """미국 규제 출처. (받아 둔 조문이 없으면 None)"""
    meta = us_reg_store.get_meta()
    if not meta:
        return None
    counted = us_reg_store.counts()
    return {
        "name": meta["source"],
        "url": meta["source_url"],
        "cfr_date": meta["cfr_date"],
        "amended_on": meta["amended_on"],
        "fetched_at": (meta["fetched_at"] or "")[:16].replace("T", " "),
        "count": meta["section_count"],
        "parts": meta["parts"],
        "kinds": [{"label": us_reg_store.KIND_LABEL.get(k, k), "count": n}
                  for k, n in sorted(counted.items())],
    }


def get_reg_source():
    """규제 데이터 출처 정보. (실데이터가 없으면 None)"""
    meta = reg_store.get_meta()
    if not meta:
        return None
    return {
        "name": meta.get("source", ""),
        "celex": meta.get("celex", ""),
        "version_date": meta.get("version_date", ""),
        "fetched_at": (meta.get("fetched_at", "") or "")[:10],
        "count": meta.get("substance_count", "0"),
        "url": meta.get("source_url", ""),
    }


# 성분표(샘플데이터) 업로드 - 파싱 결과 더미
REG_SAMPLE_FILE = "Glowtree_VitaminC_Serum_성분표.xlsx"

# INCI 사전에서 찾지 못해 사람이 확인해야 하는 행 (실제 파싱에서도 자주 생긴다)
_REG_UNMATCHED = [
    {
        "name": "Glowtree Complex GT-7",
        "raw": "GT-7 Brightening Complex 3.0%",
        "note": "자사 혼합 원료 — 구성 성분 명세가 있어야 국가별 판정이 가능합니다.",
    },
    {
        "name": "Natural Fruit Extract Blend",
        "raw": "Fruit Extract Blend 0.5%",
        "note": "INCI 명이 없어 성분을 특정하지 못했습니다. 원료사 사양서를 확인해 주세요.",
    },
]


def analyze_ingredient_file(file_name=None):
    """업로드한 성분표(샘플데이터)를 읽어 규제 대조 대상 성분을 뽑아낸 결과.

    TODO: 실제 연동 (XLSX/CSV 성분표 파싱 + INCI 사전 매칭)
    가안에서는 어떤 파일을 올려도 같은 더미 결과를 돌려준다.
    """
    ingredients = [
        {
            "key": item["key"],
            "name": item["name"],
            "inci": item["inci"],
            "category": item["category"],
            "requested": item["requested"],
        }
        for item in _REG_INGREDIENTS
    ]

    # 복합 원료를 쪼개 뒀으면 '해결됨' 으로 넘긴다. 목록에서 지우지는 않는다 -
    # 뭘 어떻게 쪼갰는지 다시 볼 수 있어야 한다.
    unmatched = []
    for row in _REG_UNMATCHED:
        item = dict(row)
        item["mix"] = mix_store.get(row["name"])
        item["resolved"] = bool(item["mix"])
        unmatched.append(item)

    split = [r for row in _REG_UNMATCHED
             for r in mix_store.as_ingredients(row["name"])]

    return {
        "file_name": file_name or REG_SAMPLE_FILE,
        "is_sample": not file_name,
        "customer": "Glowtree Beauty (미국)",
        "product": "비타민C 브라이트닝 세럼 · 30ml",
        "rows_read": len(ingredients) + len(unmatched),
        "matched": len(ingredients),
        "unmatched": unmatched,
        "open_unmatched": sum(1 for r in unmatched if not r["resolved"]),
        # 수동으로 쪼개 넣은 성분
        "split": split,
        "split_count": len(split),
        "ingredients": ingredients,
    }


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
        "file_name": file_name or "Glowtree_Beauty_개발의뢰서.xlsx",
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
             "attachments": ["Glowtree_Beauty_개발의뢰서.xlsx"],
             "body": "Hi, thank you for the quick review.\n\nOur legal team flagged the Retinol 0.5% for the EU expansion.\nCould you propose an alternative that works for both US and EU?\nAlso, please share how much the unit price would change.\n\nBest,\nEmily"},
            {"date": "2026-09-05", "direction": "out", "sender": "홍길동", "status": "회신 완료",
             "subject": "Sample schedule for Vitamin C Serum",
             "summary": "샘플 3주 일정과 필요 정보(패키지 사양) 안내.",
             "attachments": [],
             "body": "Dear Emily,\n\nWe received the development request. The first sample will be ready in 3 weeks.\nTo proceed, we need the container specification confirmed.\n\nBest regards,\nHong"},
            {"date": "2026-09-04", "direction": "in", "sender": "Emily Park", "status": "처리 완료",
             "subject": "Product Development Request - Vitamin C Brightening Serum",
             "summary": "2027 봄 라인 비타민C 세럼 개발요청서 전달. 30ml, MOQ 5,000개.",
             "attachments": ["Glowtree_Beauty_개발의뢰서.xlsx", "Reference_Texture.jpg"],
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


def _with_kind(row):
    """더미 카드는 전부 고객사(바이어)다. 유형 칸을 같은 모양으로 붙여 둔다."""
    data = dict(row)
    data.setdefault("kind", customer_store.DEFAULT_KIND)
    data["kind_meta"] = customer_store.kind_meta(data["kind"])
    data.setdefault("source", "sample")
    return data


def get_customer_profiles(keyword="", grade="all", kind="all"):
    """거래처 카드 목록. 회사명·바이어명·국가로 검색한다."""
    keyword = (keyword or "").strip().lower()
    rows = []
    for row in _CUSTOMER_PROFILES:
        if grade != "all" and row["grade"] != grade:
            continue
        if kind != "all" and row.get("kind", customer_store.DEFAULT_KIND) != kind:
            continue
        haystack = " ".join([row["name"], row["country"], row["buyer"]["name"]]).lower()
        if keyword and keyword not in haystack:
            continue
        rows.append(_with_kind(row))
    return rows


def get_customer_profile(customer_id):
    """거래처 상세 한 건. 없으면 None."""
    for row in _CUSTOMER_PROFILES:
        if row["id"] == customer_id:
            return _with_kind(row)
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


# ---------------------------------------------------------------------------
# 영업단가 계산 (UI 가안)
#   해외영업 실무 흐름을 그대로 따른다.
#     구매팀이 만든 원가표를 받아 → 선적 조건별 물류비·보험료를 얹고
#     → 영업마진을 붙여 → 환율로 USD 단가를 뽑는다.
#   계산 자체는 화면(JS)에서 실시간으로 하고, 여기서는 기본값만 내려준다.
# ---------------------------------------------------------------------------

# 구매팀에게 받는 원가표 (파일을 올리면 인식한 척 한다)
_COST_SHEET = {
    "file_name": "Glowtree_VitaminC_Serum_원가산출서.xlsx",
    "issued_by": "구매팀 이원가",
    "issued_at": "2026-09-15",
    "product": "비타민C 브라이트닝 세럼 30ml",
    "product_en": "Vitamin C Brightening Serum 30ml",
    "quantity": 5000,
    "currency": "KRW",
    "lines": [
        {"key": "bulk", "label": "내용물 (벌크)", "amount": 980,
         "note": "30ml × 비중 1.02 × 32,000원/kg"},
        {"key": "parts", "label": "용기·부자재", "amount": 0,
         "note": "사급 — 요청서 기준 고객사 지급"},
        {"key": "processing", "label": "임가공 (충전·포장)", "amount": 350,
         "note": "충전 + 2차 포장"},
        {"key": "overhead", "label": "부대비 (시험·인증)", "amount": 240,
         "note": "총 1,200,000원 ÷ 5,000개"},
    ],
    # 원가표에서 읽었지만 계산에 바로 못 쓰는 행 (실제 파싱에서도 늘 생긴다)
    "unmatched": [
        {"label": "환차손 충당 (별도 협의)", "note": "금액이 비어 있어 계산에서 제외했습니다."},
        {"label": "금형비 (1회성)", "note": "초도 1회 비용이라 개당 배분 여부를 확인해야 합니다."},
    ],
}

# 결제 통화 - 원가는 원화로 잡고, 파는 통화만 고른다.
#   미국만 상대하는 게 아니다. 일본은 엔화, 유럽 유통사는 유로로 달라는 곳이 있고,
#   국내 벤더를 통한 간접 수출이면 원화로 끊기도 한다.
#   fx 는 화면 기본값(수기 입력)이다. 실시간 고시환율이 아니다.
CURRENCIES = [
    {"code": "USD", "label": "USD · 미국 달러", "symbol": "$", "decimals": 2, "fx": 1385},
    {"code": "EUR", "label": "EUR · 유로", "symbol": "€", "decimals": 2, "fx": 1502},
    {"code": "JPY", "label": "JPY · 일본 엔", "symbol": "¥", "decimals": 0, "fx": 9.3,
     "note": "시장에서는 100엔 단위로 고시하지만 여기서는 1엔 기준으로 적습니다"},
    {"code": "CNY", "label": "CNY · 중국 위안", "symbol": "¥", "decimals": 2, "fx": 193},
    {"code": "HKD", "label": "HKD · 홍콩 달러", "symbol": "HK$", "decimals": 2, "fx": 178},
    {"code": "SGD", "label": "SGD · 싱가포르 달러", "symbol": "S$", "decimals": 2, "fx": 1078},
    {"code": "GBP", "label": "GBP · 영국 파운드", "symbol": "£", "decimals": 2, "fx": 1796},
    {"code": "AUD", "label": "AUD · 호주 달러", "symbol": "A$", "decimals": 2, "fx": 928},
    {"code": "KRW", "label": "KRW · 대한민국 원", "symbol": "₩", "decimals": 0, "fx": 1,
     "note": "원화로 끊으면 환율 변동 위험이 없습니다 (국내 벤더 경유 수출 등)"},
]
CURRENCY_MAP = {row["code"]: row for row in CURRENCIES}
DEFAULT_CURRENCY = "USD"

# 구매팀 원가에 덧붙이는 항목. 원가표에 없던 비용을 영업이 직접 얹을 때 쓴다.
#   (금형 상각처럼 1회성 비용을 수량으로 나눠 넣는 경우가 잦다)
COST_PRESETS = [
    {"key": "parts_self", "label": "용기·부자재 (자급)",
     "note": "공장이 사서 단가에 포함할 때"},
    {"key": "carton", "label": "단상자·라벨", "note": "2차 포장재"},
    {"key": "mould", "label": "금형 상각",
     "note": "1회성 금형비를 발주 수량으로 나눠 넣습니다"},
    {"key": "test", "label": "검사·시험비", "note": "안정성·미생물·중금속 등"},
    {"key": "inland", "label": "내륙 운송 (공장→창고)", "note": ""},
    {"key": "etc", "label": "기타", "note": ""},
]


# 선적 조건 - 뒤로 갈수록 판매자가 부담하는 범위가 넓어진다
INCOTERM_ORDER = ["EXW", "FCA", "FOB", "CFR", "CIF"]

INCOTERMS = [
    {"code": "EXW", "label": "EXW · 공장 인도", "desc": "공장 출고까지만 부담합니다."},
    {"code": "FCA", "label": "FCA · 운송인 인도", "desc": "내륙 운송과 수출 통관까지 부담합니다."},
    {"code": "FOB", "label": "FOB · 본선 인도", "desc": "선적항 본선에 올릴 때까지 부담합니다."},
    {"code": "CFR", "label": "CFR · 운임 포함", "desc": "도착항까지의 해상 운임을 포함합니다."},
    {"code": "CIF", "label": "CIF · 운임·보험 포함", "desc": "해상 운임에 적하보험까지 포함합니다."},
]

# 물류비 - from 에 적힌 조건부터 판매가에 포함된다 (총액, 원)
#   route 는 화면에서 고칠 수 있다. 내륙 운송이 늘 부산항인 것도 아니고
#   해상 운임이 늘 LA 로 가는 것도 아니다. 건마다 노선이 다르다.
_LOGISTICS = [
    {"key": "inland", "label": "내륙 운송", "route": "공장 → 부산항",
     "total": 380000, "from": "FCA"},
    {"key": "customs", "label": "수출 통관·서류", "route": "",
     "total": 120000, "from": "FCA"},
    {"key": "thc", "label": "THC·터미널 핸들링", "route": "부산항",
     "total": 210000, "from": "FOB"},
    {"key": "freight", "label": "해상 운임", "route": "부산 → LA",
     "total": 1050000, "from": "CFR"},
]

# 물류비에 덧붙이는 항목. 예상 못 한 부대비용이 늘 생긴다.
#   from 을 같이 잡는 게 중요하다. 어느 조건부터 판매가에 포함되는지가
#   안 맞으면 EXW 단가에 해상 운임이 얹히는 식으로 틀어진다.
LOGI_PRESETS = [
    {"key": "docs", "label": "서류·인증 발급", "from": "FCA",
     "note": "원산지증명(C/O)·FTA 증명 발급 수수료"},
    {"key": "pallet", "label": "팔레트·훈증 처리", "from": "FCA",
     "note": "목재 포장재는 훈증(IPPC) 대상입니다"},
    {"key": "storage", "label": "보세창고 보관료", "from": "FOB",
     "note": "선적이 밀리면 붙습니다"},
    {"key": "inspect", "label": "검량·검수·컨테이너 검사", "from": "FOB", "note": ""},
    {"key": "surcharge", "label": "유류·통화 할증료 (BAF·CAF)", "from": "CFR",
     "note": "운임에 따로 붙는 할증입니다"},
    {"key": "demurrage", "label": "체선·체화료 (Demurrage)", "from": "CFR",
     "note": "반출이 늦어지면 붙습니다"},
    # 이름을 비워 둔다. 골라 넣으면 빈 칸에 바로 커서가 가서 직접 적게 된다
    {"key": "etc", "label": "", "pick": "기타 (이름을 직접 적습니다)",
     "from": "FOB", "note": ""},
]

# 적하보험 - CIF 에서만 붙는다. 보험금액 = CFR 금액 × 부보율, 보험료 = 보험금액 × 요율
INSURANCE = {"rate": 0.12, "coverage": 110}

# 마진 계산 방식
MARGIN_MODES = [
    {"value": "margin", "label": "판매가 대비 (Margin)", "hint": "판매가 = 원가 ÷ (1 − 마진율)"},
    {"value": "markup", "label": "원가 대비 (Markup)", "hint": "판매가 = 원가 × (1 + 마크업율)"},
]

# 환율 변동 시나리오 (%)
FX_STEPS = [-10, -5, 0, 5, 10]


def parse_cost_sheet(file_name=None):
    """구매팀 원가표를 읽어낸 결과.

    TODO: 실제 연동 (XLSX/CSV 원가표 파싱 + 계정과목 매핑)
    가안에서는 어떤 파일을 올려도 같은 더미 결과를 돌려준다.
    """
    sheet = {key: value for key, value in _COST_SHEET.items()
             if key not in ("lines", "unmatched")}
    sheet["file_name"] = file_name or _COST_SHEET["file_name"]
    sheet["is_sample"] = not file_name
    sheet["lines"] = [dict(row) for row in _COST_SHEET["lines"]]
    sheet["unmatched"] = [dict(row) for row in _COST_SHEET["unmatched"]]
    sheet["total"] = sum(row["amount"] for row in sheet["lines"])
    return sheet


def get_pricing_defaults(file_name=None, handoff=None):
    """영업단가 계산 화면의 기본값.

    handoff 로 고객사·제품명을 넘기면 그 값으로 바꾼다
    (일정관리·신규 바이어 발굴에서 이어질 때). 원가 자체는 바뀌지 않는다.

    TODO: 실제 연동 (구매팀 원가 시스템, 포워더 운임표, 실시간 환율)
    """
    handoff = handoff or {}
    customer = (handoff.get("customer") or "").strip()
    product = (handoff.get("product") or "").strip()

    return {
        "customer": customer or "Glowtree Beauty",
        "handoff_product": product or None,
        "handoff": bool(customer or product),
        "source_doc": "Glowtree_Beauty_개발의뢰서.xlsx",
        "cost_sheet": parse_cost_sheet(file_name),
        "target_price": 2.8,
        "currency": DEFAULT_CURRENCY,
        "currencies": [dict(row) for row in CURRENCIES],
        "cost_presets": [dict(row) for row in COST_PRESETS],
        "fx": CURRENCY_MAP[DEFAULT_CURRENCY]["fx"],
        "fx_date": "2026-09-18",
        "margin": 25,
        "margin_mode": "margin",
        "selected_incoterm": "CIF",
        "quote_port": QUOTE_PORT,
        "quote_contact_en": QUOTE_CONTACT_EN,
        "logistics": [dict(row) for row in _LOGISTICS],
        "logi_presets": [dict(row) for row in LOGI_PRESETS],
        "insurance": dict(INSURANCE),
        "incoterms": [dict(row) for row in INCOTERMS],
        "incoterm_order": list(INCOTERM_ORDER),
        "margin_modes": [dict(row) for row in MARGIN_MODES],
        "fx_steps": list(FX_STEPS),
    }

# ---------------------------------------------------------------------------
# 견적서 (영업단가 계산 -> 고객사로 나가는 문서)
#   단가 계산은 화면(JS)에서 하므로, 여기서는 계산된 값을 받아
#   문서 형식(공급자·수신처·품목·거래조건·직인)으로 옮겨 담기만 한다.
#
#   문서는 두 벌로 나온다.
#     - 고객 발송용(customer) : 영문. 고객이 봐도 되는 값만 (USD 단가·합계)
#     - 사내 보관용(internal) : 국문. 원화 환산·견적환율·조건별 단가까지
#   원화 환산과 조건별 단가(EXW~CIF)는 우리 원가·마진이 드러나는 값이라
#   고객 발송용에는 절대 넣지 않는다.
# ---------------------------------------------------------------------------

# 공급자(자사) 정보 - 견적서 머리말과 하단 직인 옆에 들어간다.
#   실제 값은 company_store 가 들고 있다 (자사 정보 화면에서 고친다).
#   아래는 그 모듈이 없던 시절의 기본값이라 예비로만 남겨 둔다.
_SELLER_FALLBACK = {
    "name": "주식회사 투두트레이드",
    "name_en": "TO-DO TRADE CO., LTD.",
    "ceo": "김무역",
    "ceo_en": "Kim Moo-yeok",
    "biz_no": "123-45-67890",
    "address": "서울특별시 강남구 테헤란로 123, 8층",
    "address_en": "8F, 123 Teheran-ro, Gangnam-gu, Seoul 06234, Republic of Korea",
    "tel": "+82-2-1234-5678",
    "email": "sales@todotrade.co.kr",
    # static/ 안의 직인 이미지. 실제 운영에서는 스캔한 법인 직인으로 바꾼다.
    "seal_file": "seal.svg",
}

# 견적 조건 기본값 - 견적서 만들기 창에서 그대로 고칠 수 있다.
#   값은 고객에게 그대로 나가는 계약 문구라 영문으로 적고,
#   화면에는 무슨 뜻인지 한글 설명(hint)을 같이 보여준다.
QUOTE_TERMS = [
    {"key": "validity", "label": "견적 유효기간", "label_en": "Validity",
     "value": "30 days from the date of this quotation",
     "hint": "견적일로부터 30일"},
    {"key": "payment", "label": "결제 조건", "label_en": "Payment",
     "value": "T/T 30% with order, balance before shipment",
     "hint": "T/T 30% 선금, 잔금 선적 전"},
    {"key": "delivery", "label": "납기", "label_en": "Delivery",
     "value": "Within 45 days after order confirmation",
     "hint": "발주 확정 후 45일 이내 선적"},
    {"key": "origin", "label": "원산지", "label_en": "Country of Origin",
     "value": "Republic of Korea",
     "hint": "대한민국"},
    {"key": "packing", "label": "포장", "label_en": "Packing",
     "value": "Export standard carton",
     "hint": "수출 표준 포장"},
]

# 인도 장소 - 견적서에는 조건만 적으면 안 되고 지명까지 적어야 한다 (CIF Los Angeles)
QUOTE_PORT = "Los Angeles"

# 고객 발송본 서명란의 담당자. 사내 계정명("해외영업팀 홍길동")을 그대로 쓰면
# 영문 문서에 한글이 섞이므로, 영문 표기는 따로 받는다.
QUOTE_CONTACT_EN = "Overseas Sales Team"

# 문서 하단 안내 문구
QUOTE_NOTES = {
    "en": [
        "This quotation is based on the shipping terms and quantity stated above; "
        "any change may affect the unit price.",
        "Prices may be subject to review in case of significant currency fluctuation "
        "at the time of shipment.",
        "One-off costs such as mould and testing fees are quoted separately.",
    ],
    "ko": [
        "본 견적은 기재된 선적 조건·수량·환율을 전제로 하며, 조건이 바뀌면 단가도 달라집니다.",
        "환율 변동분은 선적 시점 기준으로 재협의할 수 있습니다.",
        "금형비·시험비 등 1회성 비용은 별도 협의 항목입니다.",
    ],
}

# 문서에 찍히는 고정 문구. 고객 발송용은 영문이라 라벨도 통째로 갈아 끼운다.
QUOTE_LABELS = {
    "en": {
        "title": "QUOTATION", "sub_title": "견 적 서",
        "no": "Quotation No.", "date": "Date",
        "to": "To (Messrs.)", "from": "Supplier",
        "attn": "Attn.", "attn_email": "E-mail",
        "intro": "We are pleased to quote you as follows.",
        "biz_no": "Business Reg. No.", "contact": "Contact",
        "th_no": "No", "th_desc": "Description", "th_term": "Terms",
        "th_qty": "Q'ty", "th_price": "Unit Price", "th_amount": "Amount",
        "unit": "pcs", "total": "Total Amount",
        "conditions": "Terms & Conditions", "shipment": "Shipment",
        "remark": "Remarks",
        "sign_intro": "For and on behalf of", "ceo": "CEO", "seal": "(Seal)",
    },
    "ko": {
        "title": "견 적 서", "sub_title": "QUOTATION",
        "no": "견적번호", "date": "견적일자",
        "to": "수신", "from": "공급자",
        "attn": "담당", "attn_email": "이메일",
        "intro": "아래와 같이 견적합니다.",
        "biz_no": "사업자등록번호", "contact": "담당",
        "th_no": "No", "th_desc": "품목", "th_term": "거래조건",
        "th_qty": "수량", "th_price": "단가", "th_amount": "금액",
        "unit": "개", "total": "합계 금액",
        "conditions": "거래 조건", "shipment": "선적 조건",
        "remark": "비고",
        "sign_intro": "", "ceo": "대표이사", "seal": "(인)",
        # 사내 보관용에만 나오는 것
        "krw": "원화 환산", "fx_note": "견적환율",
        "term_table": "조건별 단가", "term_table_sub": "사내 참고",
    },
}

# 견적서 화면 (고객 발송용 / 사내 보관용)
QUOTE_VIEWS = [
    {"value": "customer", "label": "고객 발송용 (영문)", "lang": "en"},
    {"value": "internal", "label": "사내 보관용 (국문)", "lang": "ko"},
]


def _quote_num(value, default=0.0):
    """폼으로 넘어온 숫자 문자열을 float 으로. (콤마·빈칸 허용)"""
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _quote_no(customer, product, today):
    """견적번호. 같은 날 같은 건이면 같은 번호가 나오도록 CRC 로 뒷자리를 만든다."""
    seed = "{}|{}".format(customer, product).encode("utf-8")
    return "QT-{}-{:04d}".format(today.strftime("%Y%m%d"), zlib.crc32(seed) % 10000)


def build_quote(form, view="customer"):
    """견적서 화면에 쓸 값. (form: 단가 계산 화면이 POST 한 값)

    계산은 이미 화면에서 끝났고, 여기서는 받은 값을 검증·정리해서
    문서 모양으로 만든다. 값이 비면 화면 기본값으로 메운다.

    view 가 'customer' 면 고객에게 나가는 영문 견적서,
    'internal' 이면 원화 환산·조건별 단가까지 붙은 사내 보관용이다.
    """
    defaults = get_pricing_defaults()
    sheet = defaults["cost_sheet"]

    internal = view == "internal"
    lang = "ko" if internal else "en"
    t = dict(QUOTE_LABELS[lang])

    customer = (form.get("customer") or "").strip() or defaults["customer"]
    attn = (form.get("attn") or "").strip()
    attn_email = (form.get("attn_email") or "").strip()

    # 품목명은 국문·영문을 따로 받는다. 고객 발송용에 국문 제품명이 나가면 안 된다.
    product_ko = (form.get("product") or "").strip() or sheet["product"]
    product_en = (form.get("product_en") or "").strip() or sheet.get("product_en", "")
    product = (product_en or product_ko) if lang == "en" else (product_ko or product_en)
    # 고객 발송용은 영문만 (국문 품목명이 같이 나가면 문서가 반쪽짜리가 된다).
    # 사내 보관용에는 영문명을 같이 적어 둔다.
    product_sub = "" if lang == "en" else product_en
    if product_sub == product:
        product_sub = ""

    qty = int(_quote_num(form.get("qty"), sheet["quantity"])) or 1
    fx = _quote_num(form.get("fx"), defaults["fx"]) or 1

    # 결제 통화. 모르는 코드가 오면 기본 통화로 돌린다
    currency = CURRENCY_MAP.get((form.get("currency") or "").upper(),
                                CURRENCY_MAP[DEFAULT_CURRENCY])
    digits = currency["decimals"]

    target_price = _quote_num(form.get("target_price"), defaults["target_price"])

    # 견적서에 적는 단가는 통화의 최소 단위로 확정한다.
    # (고객이 단가 x 수량을 계산해도 합계가 맞아야 한다)
    price_unit = round(_quote_num(form.get("price_unit")), digits)
    price_krw = round(_quote_num(form.get("price_krw"), price_unit * fx))

    incoterm = (form.get("incoterm") or "").strip() or defaults["selected_incoterm"]
    incoterm_label = next((i["label"] for i in INCOTERMS if i["code"] == incoterm), incoterm)
    incoterm_desc = next((i["desc"] for i in INCOTERMS if i["code"] == incoterm), "")
    # 조건만 적으면 견적이 성립하지 않는다. 지명까지 붙인다 (CIF Los Angeles)
    port = (form.get("port") or "").strip() or QUOTE_PORT
    incoterm_full = "{} {}".format(incoterm, port).strip()

    # 조건별 단가 (사내 참고용) - 화면에서 만든 JSON 을 그대로 받는다
    terms = []
    if internal:
        try:
            rows = json.loads(form.get("terms") or "[]")
        except ValueError:
            rows = []
        terms = [
            {
                "code": str(row.get("code", "")),
                "unit": _quote_num(row.get("unit")),
                "krw": _quote_num(row.get("krw")),
            }
            for row in rows if isinstance(row, dict)
        ]

    # 거래조건 - 창에서 고친 값이 있으면 그 값, 없으면 기본값
    conditions = [
        {"key": row["key"],
         "label": row["label_en"] if lang == "en" else row["label"],
         "value": (form.get("term_" + row["key"]) or "").strip() or row["value"]}
        for row in QUOTE_TERMS
    ]

    today = date.today()
    # 서류는 자사 정보에서 읽어 간다. 서류마다 회사 주소가 달라지면 안 된다
    seller = dict(_SELLER_FALLBACK, **{
        key: value for key, value in company_store.values().items() if value})
    return {
        "view": view,
        "internal": internal,
        "lang": lang,
        "t": t,
        "views": [dict(row) for row in QUOTE_VIEWS],
        "seller": seller,
        "seller_name": seller["name_en"] if lang == "en" else seller["name"],
        "seller_name_sub": seller["name"] if lang == "en" else seller["name_en"],
        "seller_ceo": seller["ceo_en"] if lang == "en" else seller["ceo"],
        "seller_address": seller["address_en"] if lang == "en" else seller["address"],
        "no": _quote_no(customer, product_ko, today),
        "issued_at": today.isoformat(),
        "issued_by": (form.get("issued_by_en") or QUOTE_CONTACT_EN) if lang == "en"
                     else (form.get("issued_by") or ""),
        "customer": customer,
        "attn": attn,
        "attn_email": attn_email,
        "product": product,
        "product_sub": product_sub,
        "quantity": qty,
        "incoterm": incoterm,
        "incoterm_full": incoterm_full,
        "incoterm_label": incoterm_label,
        "incoterm_desc": incoterm_desc if internal else "",
        "port": port,
        "currency": currency["code"],
        "currency_symbol": currency["symbol"],
        "decimals": digits,
        "unit_price": price_unit,
        "amount": price_unit * qty,
        # 아래 네 개는 사내 보관용에서만 쓴다 (환율·원가가 드러나는 값)
        "fx": fx if internal else 0,
        # 견적환율이 어디서 온 값인지. 사내 보관용에만 적는다
        "fx_basis": (form.get("fx_basis") or "").strip() if internal else "",
        "unit_price_krw": price_krw if internal else 0,
        "amount_krw": price_krw * qty if internal else 0,
        "target_price": target_price if internal else 0,
        "over_target": bool(internal and target_price and price_unit > target_price),
        "terms": terms,
        "conditions": conditions,
        "notes": list(QUOTE_NOTES[lang]),
        "remark": (form.get("remark") or "").strip(),
    }

# ---------------------------------------------------------------------------
# 개발요청서 직접 작성 (해외영업 -> 사내 개발팀)
#   고객사 요청이 늘 파일로 오는 건 아니라서(메일·전화·미팅),
#   담당자가 사내 양식에 직접 적어 연구소·공장으로 넘기는 경로를 둔다.
#   필드 key 는 내부 전달 문서(_FIELD_VALUES)와 같게 맞춰 그대로 변환된다.
# ---------------------------------------------------------------------------

# 요청이 어디서 시작됐는지. 고객사 요청만 있는 게 아니라
# 영업이 트렌드·시장조사를 보고 스스로 발의하는 경우도 많다.
REQUEST_ORIGINS = [
    {"value": "customer", "label": "고객사 요청",
     "desc": "받은 요청을 사내 양식으로 정리합니다.", "needs": "customer"},
    {"value": "inhouse", "label": "자사 기획",
     "desc": "트렌드·시장조사를 보고 영업이 직접 발의합니다.", "needs": "none"},
    {"value": "prospect", "label": "신규 고객 제안",
     "desc": "아직 거래가 없는 곳에 먼저 제안합니다.", "needs": "customer_new"},
]

# 고객사 자리에 넣을 표기 (고객사가 없는 경우)
ORIGIN_LABELS = {
    "inhouse": "자사 기획 (해외영업팀)",
    "prospect": "신규 제안 (고객사 미정)",
}


COMPOSE_SECTIONS = [
    {
        "key": "basic", "title": "기본 정보", "icon": "📌",
        "fields": [
            {"key": "request_origin", "label": "요청 구분", "type": "origin", "required": True,
             "hint": "고객사 요청이 아니어도 됩니다. 영업이 직접 발의한 건도 같은 양식으로 넘깁니다."},
            {"key": "customer", "label": "고객사", "type": "customer",
             "show_for": "customer"},
            {"key": "customer_new", "label": "제안할 회사", "type": "text",
             "show_for": "prospect", "placeholder": "예: Nordic Bloom (스웨덴) · 미정이면 비워 두세요"},
            {"key": "background", "label": "요청·기획 배경", "type": "textarea",
             "placeholder": "예: 트라넥사믹애씨드 관심도가 직전 7일 대비 상승, 브라이트닝 라인 확장 제안",
             "hint": "왜 이 제품인지 한두 줄로 적어 두면 연구소가 우선순위를 잡기 쉽습니다."},
            {"key": "product_name", "label": "제품명", "type": "text", "required": True,
             "placeholder": "예: 비타민C 브라이트닝 세럼"},
            {"key": "product_type", "label": "제품 유형", "type": "text", "required": True,
             "placeholder": "예: 리브온 페이셜 세럼"},
            {"key": "volume", "label": "용량", "type": "text", "placeholder": "예: 30ml"},
            {"key": "container", "label": "용기", "type": "text",
             "placeholder": "예: 유리 스포이드 병 (30ml)"},
            {"key": "container_supply", "label": "용기 사급/자급", "type": "select",
             "options": ["사급 (고객사 지급)", "자급 (우리가 조달)", "미정 — 확인 필요"],
             "hint": "단가와 납기가 통째로 달라지는 항목입니다."},
        ],
    },
    {
        "key": "formula", "title": "제형·사용감", "icon": "🧪",
        "fields": [
            {"key": "texture", "label": "텍스처", "type": "textarea",
             "placeholder": "예: 가벼운 워터리, 빠른 흡수 / 끈적임 없을 것"},
            {"key": "fragrance", "label": "향", "type": "text",
             "placeholder": "예: 무향 (fragrance-free)"},
            {"key": "color", "label": "색상", "type": "text", "placeholder": "예: 투명 / 미정"},
            {"key": "benchmark", "label": "벤치마크 제품", "type": "text",
             "placeholder": "예: Dewy Lab Glow Drop Serum (미국, 2025)",
             "hint": "연구소가 사용감을 잡는 데 가장 크게 참고하는 항목입니다."},
        ],
    },
    {
        "key": "claims", "title": "클레임·시험", "icon": "🏷",
        "fields": [
            {"key": "claims", "label": "인증·클레임", "type": "text",
             "placeholder": "예: Vegan, Cruelty-free"},
            {"key": "free_from", "label": "배제 성분 (Free-from)", "type": "text",
             "placeholder": "예: Parabens, Sulfates, Mineral oil"},
            {"key": "test_stability", "label": "안정성 시험", "type": "text",
             "placeholder": "예: 가속 안정성 45도 4주"},
            {"key": "test_irritation", "label": "피부자극 시험", "type": "text",
             "placeholder": "예: 인체적용 피부자극 시험"},
        ],
    },
    {
        "key": "commercial", "title": "수량·거래조건", "icon": "💰",
        "fields": [
            {"key": "moq", "label": "MOQ", "type": "text", "placeholder": "예: 5,000개"},
            {"key": "target_price", "label": "목표 단가", "type": "text",
             "placeholder": "예: USD 2.8 / 개"},
            {"key": "trade_terms", "label": "거래조건", "type": "text",
             "placeholder": "예: FOB 부산, T/T 30% 선금",
             "hint": "통화·Incoterms·결제조건을 같이 적어야 견적이 나옵니다."},
            {"key": "sample_due", "label": "샘플 납기", "type": "text",
             "placeholder": "예: 요청일로부터 4주"},
            {"key": "mass_shipment", "label": "본생산 선적", "type": "text",
             "placeholder": "예: 2027년 1월"},
            {"key": "shipping_terms", "label": "선적 조건", "type": "text",
             "placeholder": "예: FOB 부산항"},
        ],
    },
    {
        "key": "regulation", "title": "판매 국가·서류", "icon": "🌍",
        "fields": [
            {"key": "target_country", "label": "판매 국가", "type": "text", "required": True,
             "placeholder": "예: 미국(1차) → EU(확장 예정)"},
            {"key": "documents", "label": "필요 서류", "type": "text",
             "placeholder": "예: CoA, MSDS, 비동물실험 확인서"},
            {"key": "responsible_person", "label": "책임자 지정", "type": "text",
             "placeholder": "예: EU 역내 책임자(RP) 고객사 지정 예정",
             "hint": "EU·미국은 책임자가 없으면 판매 자체가 불가합니다."},
            {"key": "package_design", "label": "패키지 디자인", "type": "text",
             "placeholder": "예: 추후 전달"},
            {"key": "label", "label": "라벨 요구사항", "type": "text",
             "placeholder": "예: Vegan / Cruelty-free 표기"},
        ],
    },
]

# 성분 입력 행의 기본 개수
COMPOSE_INGREDIENT_ROWS = 5

# 트렌드에서 넘어왔을 때 쓰는 카테고리별 제형 힌트
_COMPOSE_TEMPLATES = {
    "브라이트닝": ("브라이트닝 세럼", "리브온 페이셜 세럼", "가벼운 워터리, 빠른 흡수 / 끈적임 없을 것"),
    "안티에이징": ("리뉴얼 나이트 세럼", "리브온 나이트 세럼", "부드러운 에멀전, 유분감 적은 마무리"),
    "보습": ("수분 앰플", "리브온 페이셜 앰플", "촉촉한 젤, 흡수 후 산뜻함"),
    "각질·트러블": ("포어 클리어링 세럼", "리브온 페이셜 세럼", "산뜻한 워터리, 무유분"),
    "장벽": ("배리어 리페어 크림", "리브온 페이셜 크림", "부드러운 크림, 밀착감 있는 마무리"),
    "진정": ("카밍 수딩 세럼", "리브온 페이셜 세럼", "묽은 젤, 빠른 흡수"),
}

# 규제 한도가 있는 성분은 한도 안쪽 함량을 제안한다
_COMPOSE_AMOUNT = {
    "salicylic": "0.5%", "retinol": "0.2%", "arbutin": "2.0%", "niacinamide": "5.0%",
    "azelaic": "10.0%", "tranexamic": "3.0%", "hyaluronic": "1.0%", "ceramide": "1.0%",
    "bakuchiol": "1.0%", "panthenol": "2.0%", "squalane": "5.0%", "centella": "5.0%",
}

_COMPOSE_PRESET = {
    "volume": "30ml",
    "container": "유리 스포이드 병 (30ml)",
    "container_supply": "미정 — 확인 필요",
    "fragrance": "무향 (fragrance-free)",
    "free_from": "Parabens, Sulfates, Mineral oil, Synthetic fragrance",
    "claims": "Vegan, Cruelty-free",
    "test_stability": "가속 안정성 45도 4주",
    "test_irritation": "인체적용 피부자극 시험",
    "moq": "5,000개",
    "documents": "CoA, MSDS, 비동물실험 확인서",
}


def get_compose_form(ingredient=None, trend_row=None, handoff=None):
    """작성 폼의 초기값.

    트렌드 성분을 넘기면 관련 칸을 미리 채우고,
    일정관리·신규 바이어 발굴에서 넘어온 값(handoff)이 있으면 그 값을 얹는다.
    """
    values = dict(_COMPOSE_PRESET)
    values["request_origin"] = "customer"
    ingredients = []
    prefilled = set(_COMPOSE_PRESET)
    origin = None

    if ingredient:
        # 트렌드에서 넘어온 건은 고객사 요청이 아니라 자사 기획이다
        values["request_origin"] = "inhouse"
        form_name, product_type, texture = _COMPOSE_TEMPLATES.get(
            ingredient["category"], _COMPOSE_TEMPLATES["보습"])
        values["product_name"] = "{} {}".format(ingredient["name"], form_name)
        values["product_type"] = product_type
        values["texture"] = texture
        values["target_country"] = "미국 · EU"
        prefilled |= {"product_name", "product_type", "texture", "target_country",
                      "background", "request_origin"}

        if trend_row and trend_row.get("status") != "pending":
            values["background"] = (
                "{} 관심도가 최근 7일 일평균 {:,.0f}회로 직전 대비 {:+.1f}% — "
                "{} 라인 확장 제안".format(
                    ingredient["name"], trend_row["recent_avg"],
                    trend_row["growth"], ingredient["category"]))
        else:
            values["background"] = "{} 기반 {} 제품 기획".format(
                ingredient["name"], ingredient["category"])

        ingredients.append({
            "name": ingredient["name"], "inci": ingredient["inci"],
            "amount": _COMPOSE_AMOUNT.get(ingredient["key"], "1.0%"), "role": "주 성분",
        })
        ingredients.append({"name": "페녹시에탄올", "inci": "Phenoxyethanol",
                            "amount": "0.8%", "role": "방부"})

        detail = "관심도 데이터 없음"
        if trend_row and trend_row.get("status") != "pending":
            detail = "관심도 {:,.0f}회/일 · 직전 7일 대비 {:+.1f}%".format(
                trend_row["recent_avg"], trend_row["growth"])
        origin = {
            "type": "trend",
            "label": "오늘의 트렌드 · {}".format(ingredient["name"]),
            "detail": detail,
        }

    if handoff:
        # 다른 화면에서 넘어온 값이 트렌드 프리셋보다 우선한다 (담당자가 직접 고른 건이라서)
        kind_map = {"prospect": "prospect", "inhouse": "inhouse", "customer": "customer"}
        kind = kind_map.get(handoff.get("kind") or "", None)
        if kind:
            values["request_origin"] = kind
            prefilled.add("request_origin")
        account = (handoff.get("account") or "").strip()
        if account:
            known = {row["name"] for row in get_customers()}
            if account in known:
                # 등록된 고객사면 드롭다운에서 고르고, 아니면 신규 제안으로 둔다
                values["request_origin"] = "customer"
                values["customer"] = account
                prefilled |= {"request_origin", "customer"}
            else:
                if values["request_origin"] == "customer":
                    values["request_origin"] = "prospect"
                values["customer_new"] = account
                prefilled |= {"request_origin", "customer_new"}
        if handoff.get("product"):
            values["product_name"] = handoff["product"]
            prefilled.add("product_name")
        if handoff.get("country"):
            values["target_country"] = handoff["country"]
            prefilled.add("target_country")

        labels = {"schedule": "일정관리", "prospect": "신규 바이어 발굴"}
        origin = {
            "type": handoff.get("src") or "handoff",
            "label": "{} 에서 이어짐".format(labels.get(handoff.get("src"), "다른 화면")),
            "detail": " · ".join(v for v in [account, handoff.get("product"),
                                             handoff.get("country")] if v) or "값 일부만 전달됨",
        }

    while len(ingredients) < COMPOSE_INGREDIENT_ROWS:
        ingredients.append({"name": "", "inci": "", "amount": "", "role": ""})

    return {
        "sections": [dict(sec) for sec in COMPOSE_SECTIONS],
        "form_values": values,
        "prefilled": sorted(prefilled),
        "ingredients": ingredients,
        "customers": get_customers(),
        "origins": [dict(row) for row in REQUEST_ORIGINS],
        "origin": origin,
    }


def resolve_requester(form):
    """요청 구분에 따라 문서에 찍을 '요청 주체'를 정한다."""
    origin = (form.get("request_origin") or "customer").strip()
    if origin == "customer":
        return form.get("customer", "").strip() or "고객사 미지정"
    if origin == "prospect":
        return (form.get("customer_new", "").strip()
                or ORIGIN_LABELS["prospect"])
    return ORIGIN_LABELS.get(origin, ORIGIN_LABELS["inhouse"])


def judge_ingredients(rows):
    """작성 중인 성분 목록에 EU 판정을 붙인다. (화면에서 실시간으로 호출한다)"""
    live = reg_store.is_available()
    result = []
    for row in rows:
        name = (row.get("name") or "").strip()
        inci = (row.get("inci") or "").strip()
        amount = (row.get("amount") or "").strip()
        if not (name or inci):
            continue

        verdict = reg_store.judge(name or inci, inci or name, None, amount) if live else None
        if verdict is None:
            verdict = {"status": "ok", "limit": "-", "rule": "-", "annex": "",
                       "note": "규제 데이터가 수집되지 않아 판정할 수 없습니다."}
        result.append({
            "name": name or inci, "inci": inci or name, "amount": amount,
            "role": (row.get("role") or "").strip(),
            "status": verdict["status"], "limit": verdict["limit"],
            "rule": verdict["rule"], "note": verdict["note"],
            "annex": verdict.get("annex", ""), "live": live,
        })
    return result


def build_compose_result(form, ingredients):
    """작성한 내용을 내부 전달 문서용 overrides 로 바꾼다."""
    overrides = {key: value.strip()
                 for key, value in form.items() if value and value.strip()}

    # 문서 머리말에 찍을 요청 주체 (고객사 / 자사 기획 / 신규 제안)
    requester = resolve_requester(form)
    overrides["_requester"] = requester
    overrides["_origin"] = (form.get("request_origin") or "customer").strip()

    judged = judge_ingredients(ingredients)
    if judged:
        overrides["key_ingredients"] = ", ".join(
            "{} {}".format(r["inci"], r["amount"]).strip() for r in judged)
        flagged = [r for r in judged if r["status"] in ("warn", "ban")]
        if flagged:
            overrides["regulation_note"] = " / ".join(
                "{} {} — {}".format(
                    r["inci"], r["amount"],
                    "EU 기준 초과" if r["status"] == "ban" else "기준 확인 필요")
                for r in flagged)
        else:
            overrides["regulation_note"] = "EU 기준에서 걸리는 성분 없음 (작성 시점 기준)"

    return {
        "overrides": overrides,
        "ingredients": judged,
        "flagged": [r for r in judged if r["status"] in ("warn", "ban")],
        "regulation_live": reg_store.is_available(),
    }
