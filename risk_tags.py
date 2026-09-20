# -*- coding: utf-8 -*-
"""리스크 사전 경고 - 연구소에 넘기기 전에 영업이 알아야 할 것.

요청서를 그대로 연구소에 넘기고 나서 "이 배합은 안정도가 안 나옵니다",
"이 함량이면 단가가 두 배입니다" 를 들으면 이미 바이어에게 일정과 단가를
말해 버린 뒤다. 그때부터는 말을 바꾸는 협상이 된다.

그래서 **넘기기 전에** 붙인다. 영업이 미리 버퍼를 잡거나 협상을 준비할 수 있게.

세 갈래를 본다.
  단가   고단가 기능성 원료가 몇 개, 얼마나 들어가나
  안정도 같이 넣으면 서로 깨지는 조합이 있나
  일정   시험·인증이 더 붙는 조건인가

**이건 경고지 판정이 아니다.** 실제 단가는 구매팀이, 안정도는 연구소가 낸다.
여기서는 "이 지점을 미리 물어보라" 고 짚어 줄 뿐이다. 화면에도 그렇게 적는다.

이 표는 수기로 정리한 것이다. 처방 DB 가 붙으면 그쪽 값으로 바꿔야 한다.
"""

import re

REVIEWED_ON = "2026-09-20"

LEVELS = {
    "high": {"label": "높음", "css": "high"},
    "mid": {"label": "보통", "css": "mid"},
    "info": {"label": "참고", "css": "info"},
}

KINDS = {
    "cost": {"label": "단가", "icon": "💰"},
    "stability": {"label": "안정도", "icon": "🧪"},
    "schedule": {"label": "일정·시험", "icon": "🗓"},
}


# ---------------------------------------------------------------------------
# 고단가 기능성 원료
# ---------------------------------------------------------------------------
#   tier 3 = 매우 비쌈, 2 = 비쌈, 1 = 보통보다 위
#   화장품 원료 단가는 등급·공급사·로트에 따라 몇 배씩 갈린다.
#   그래서 금액을 적지 않는다. 적으면 그 숫자를 믿어 버린다.

COSTLY = [
    {"words": ["egf", "epidermal growth factor", "sh-oligopeptide"],
     "name": "성장인자(EGF)류", "tier": 3,
     "note": "원료 단가가 매우 높고 나라에 따라 화장품 사용 가부가 갈립니다."},
    {"words": ["exosome", "엑소좀"], "name": "엑소좀", "tier": 3,
     "note": "단가와 규제 양쪽에서 걸립니다. 판매국 기준을 먼저 보세요."},
    {"words": ["astaxanthin", "아스타잔틴"], "name": "아스타잔틴", "tier": 3,
     "note": "색이 강해 제형 색까지 잡아야 합니다."},
    {"words": ["ectoin", "엑토인"], "name": "엑토인", "tier": 3, "note": ""},
    {"words": ["peptide", "펩타이드", "palmitoyl tripeptide",
               "acetyl hexapeptide"],
     "name": "펩타이드류", "tier": 2,
     "note": "0.1% 미만으로도 단가에 크게 붙습니다. 함량을 꼭 확인하세요."},
    {"words": ["ceramide np", "ceramide ns", "ceramide ap", "세라마이드"],
     "name": "세라마이드", "tier": 2,
     "note": "용해가 까다로워 가용화 공정이 추가될 수 있습니다."},
    {"words": ["bakuchiol", "바쿠치올"], "name": "바쿠치올", "tier": 2, "note": ""},
    {"words": ["hydroxypinacolone retinoate", "granactive"],
     "name": "HPR (그래낙티브)", "tier": 2, "note": ""},
    {"words": ["centella", "madecassoside", "asiaticoside", "teca"],
     "name": "센텔라 정제물(TECA·마데카소사이드)", "tier": 2,
     "note": "추출물과 정제물의 단가 차이가 큽니다. 어느 쪽인지 확인하세요."},
    {"words": ["tranexamic acid", "트라넥사믹"], "name": "트라넥사믹애씨드",
     "tier": 2, "note": ""},
    {"words": ["retinol", "레티놀"], "name": "레티놀", "tier": 1,
     "note": "원료 자체보다 안정화(용기·질소 충전·저온 보관) 비용이 붙습니다."},
    {"words": ["squalane", "스쿠알란"], "name": "스쿠알란", "tier": 1,
     "note": "올리브 유래는 사탕수수 유래보다 비쌉니다."},
]


# ---------------------------------------------------------------------------
# 같이 넣으면 서로 깨지는 조합
# ---------------------------------------------------------------------------
#   a 와 b 가 둘 다 보이면 경고한다.

CLASHES = [
    {
        "a": ["ascorbic acid", "l-ascorbic", "아스코빅"],
        "b": ["retinol", "레티놀"],
        "level": "high",
        "title": "순수 비타민C + 레티놀",
        "note": "요구 pH가 반대입니다(비타민C는 산성, 레티놀은 중성 쪽). "
                "한 제형에 같이 넣으면 둘 다 효능이 떨어집니다. "
                "주야 분리나 유도체 사용을 먼저 제안해 보세요.",
    },
    {
        "a": ["ascorbic acid", "l-ascorbic", "아스코빅"],
        "b": ["niacinamide", "나이아신아마이드"],
        "level": "mid",
        "title": "순수 비타민C + 나이아신아마이드",
        "note": "고온·고농도에서 반응해 변색·자극 보고가 있습니다. "
                "유도체(아스코빌글루코사이드 등)로 바꾸면 대부분 해결됩니다.",
    },
    {
        "a": ["retinol", "레티놀", "retinal"],
        "b": ["glycolic", "salicylic", "lactic acid", "aha", "bha", "만델릭"],
        "level": "high",
        "title": "레티놀 + 산(AHA·BHA)",
        "note": "산성에서 레티놀이 분해되고 자극도 겹칩니다. "
                "같은 제형이면 함량을 낮추거나 단계를 나눠야 합니다.",
    },
    {
        "a": ["ascorbic acid", "l-ascorbic", "아스코빅"],
        "b": ["copper", "zinc", "iron oxide", "구리", "아연"],
        "level": "mid",
        "title": "비타민C + 금속 이온",
        "note": "금속이 산화를 촉진해 갈변이 빨라집니다. "
                "킬레이트제(EDTA 등)와 용기 차광이 필요합니다.",
    },
    {
        "a": ["niacinamide", "나이아신아마이드"],
        "b": ["glycolic", "salicylic", "lactic acid", "만델릭"],
        "level": "info",
        "title": "나이아신아마이드 + 산",
        "note": "낮은 pH에서 니코틴산으로 일부 전환돼 홍조를 일으킬 수 있습니다. "
                "제형 pH를 5 이상으로 잡는 편이 안전합니다.",
    },
    {
        "a": ["retinol", "레티놀", "ascorbic", "아스코빅"],
        "b": ["fragrance-free", "무향", "unscented"],
        "level": "info",
        "title": "불안정 활성 + 무향",
        "note": "향으로 가릴 수 없어 원료취가 그대로 드러납니다. "
                "시간이 지나며 나는 냄새를 바이어가 '변질' 로 볼 수 있습니다. "
                "관능 기준을 미리 합의해 두세요.",
    },
]


# ---------------------------------------------------------------------------
# 일정·시험이 더 붙는 조건
# ---------------------------------------------------------------------------

SCHEDULE_FLAGS = [
    {"words": ["vegan", "비건"], "title": "비건 인증",
     "note": "원료 단위 증빙을 원료사마다 받아야 합니다. 보통 4~8주 더 걸립니다."},
    {"words": ["cruelty-free", "cruelty free", "동물실험"],
     "title": "동물실험 미실시 인증",
     "note": "원료사 선언서를 전부 모아야 합니다. 중국 일반무역 수출과 충돌할 수 있습니다."},
    {"words": ["halal", "할랄"], "title": "할랄 인증",
     "note": "원료·공정·설비까지 심사합니다. 3개월 이상 봅니다."},
    {"words": ["cosmos", "ecocert", "organic", "유기농"], "title": "유기농 인증",
     "note": "원료 배합비가 기준이라 처방이 거의 고정됩니다."},
    {"words": ["spf", "자외선차단", "sunscreen"], "title": "자외선차단 표시",
     "note": "in-vivo SPF 시험이 붙습니다(6~10주). 미국은 OTC 의약품으로 갈립니다."},
]


def _norm(text):
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _percent(text):
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", str(text or ""))
    return float(m.group(1).replace(",", ".")) if m else None


def scan(ingredients, extras=""):
    """성분 목록과 요청 문구를 훑어 경고 태그를 만든다.

    ingredients: [{"name":…, "inci":…, "amount"/"requested":…}, …]
    extras: 클레임·자유 문구 (무향, 비건 등이 적혀 오는 자리)
    """
    rows = ingredients or []
    blob = _norm(" ".join(
        [" ".join(filter(None, [r.get("name"), r.get("inci")])) for r in rows]
        + [extras or ""]))

    tags = []

    # ---- 단가
    hits = []
    for item in COSTLY:
        if any(word in blob for word in item["words"]):
            hits.append(item)
    if hits:
        top = max(h["tier"] for h in hits)
        level = "high" if top >= 3 or len(hits) >= 3 else "mid"
        tags.append({
            "kind": "cost",
            "level": level,
            "title": "단가 급등 위험",
            "why": "고단가 기능성 원료가 {}건 들어 있습니다 — {}.".format(
                len(hits), " · ".join(h["name"] for h in hits)),
            "todo": "구매팀에 원료 견적을 먼저 받아 보세요. "
                    "목표 단가를 바이어에게 말하기 전에 확인해야 합니다.",
            "details": [h["note"] for h in hits if h["note"]],
        })

    # ---- 총 활성 함량
    total = 0.0
    counted = 0
    for row in rows:
        value = _percent(row.get("amount") or row.get("requested"))
        if value is not None and value < 50:      # 정제수·기제는 빼고 본다
            total += value
            counted += 1
    if counted and total >= 15:
        tags.append({
            "kind": "stability",
            "level": "high" if total >= 25 else "mid",
            "title": "활성 총합 과다",
            "why": "읽어낸 활성 성분 {}건의 합이 {:.1f}% 입니다.".format(counted, total),
            "todo": "점도·안정도·자극이 한꺼번에 걸립니다. "
                    "우선순위를 정해 함량을 조정할 여지를 미리 받아 두세요.",
            "details": [],
        })

    # ---- 서로 깨지는 조합
    for clash in CLASHES:
        if any(w in blob for w in clash["a"]) and any(w in blob for w in clash["b"]):
            tags.append({
                "kind": "stability",
                "level": clash["level"],
                "title": "안정도 주의 — " + clash["title"],
                "why": clash["note"],
                "todo": "연구소에 넘기기 전에 이 조합을 유지할지 바이어와 정리하세요.",
                "details": [],
            })

    # ---- 일정·시험
    for flag in SCHEDULE_FLAGS:
        if any(word in blob for word in flag["words"]):
            tags.append({
                "kind": "schedule",
                "level": "mid",
                "title": "일정 추가 — " + flag["title"],
                "why": flag["note"],
                "todo": "샘플·본생산 일정에 이 기간을 얹어 두세요.",
                "details": [],
            })

    order = {"high": 0, "mid": 1, "info": 2}
    tags.sort(key=lambda t: order[t["level"]])
    for tag in tags:
        tag["level_meta"] = dict(LEVELS[tag["level"]], key=tag["level"])
        tag["kind_meta"] = dict(KINDS[tag["kind"]], key=tag["kind"])

    return {
        "tags": tags,
        "count": len(tags),
        "high": sum(1 for t in tags if t["level"] == "high"),
        "reviewed_on": REVIEWED_ON,
    }
