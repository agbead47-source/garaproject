# -*- coding: utf-8 -*-
"""대안 성분 - '사용 불가' 다음에 할 말.

판정만 던지면 영업은 바이어에게 "안 됩니다" 밖에 못 한다.
그 자리에서 "그럼 이걸로 잡아 보는 건 어떻겠습니까" 를 말할 수 있어야
협상이 이어진다. 연구소에도 빈손으로 가지 않는다.

**다만 이건 처방 대체가 아니다.** 우리가 할 수 있는 말은 딱 여기까지다.

  할 수 있는 말   "같은 목적으로 업계에서 쓰는 원료는 이런 것들이 있습니다.
                  이 중 A는 그 나라 기준에서 걸리지 않습니다"
  할 수 없는 말   "A로 바꾸면 됩니다"

효능 세기·배합 안정도·pH·용해도·단가가 전부 다르다. 그건 연구소가 잡는다.
화면에도 그렇게 적는다.

**후보를 그 시장 기준으로 다시 판정한다.** 이게 이 모듈의 핵심이다.
EU에서 걸린 성분의 대안이라고 내놨는데 그 대안도 EU에서 제한이면
같은 실수를 한 번 더 하는 것이다. 그래서 추천하기 전에 다시 대조하고,
걸리면 걸린다고 같이 적는다.
"""

import re

# ---------------------------------------------------------------------------
# 대안 표
# ---------------------------------------------------------------------------
#   words : 이 낱말이 걸린 성분에 보이면 이 묶음을 제안한다
#   why   : 왜 이 성분이 문제가 되나 (대안을 찾는 이유)
#   alts  : 같은 목적으로 업계에서 쓰는 원료
#           note 는 **실무에서 바로 걸리는 지점**을 적는다.
#           "좋다" 가 아니라 "이건 이래서 다르다" 를 적어야 쓸모가 있다.
#
#   이 표는 수기로 정리한 것이다. 자동으로 채워지지 않는다.

REVIEWED_ON = "2026-09-20"

GROUPS = [
    {
        "key": "retinoid",
        "label": "주름·안티에이징 (레티노이드)",
        "words": ["retinol", "retinyl palmitate", "retinyl acetate", "레티놀"],
        "why": "EU는 농도 제한, 임신부 경고 문구 요구가 붙고 나라마다 한도가 다릅니다.",
        "alts": [
            {"inci": "Bakuchiol", "name": "바쿠치올",
             "note": "레티놀 대체로 가장 많이 쓰입니다. 광분해가 덜해 낮 제품에도 "
                     "넣습니다. 다만 레티놀과 작용 기전이 달라 효능 문구를 그대로 "
                     "쓸 수 없습니다."},
            {"inci": "Hydroxypinacolone Retinoate", "name": "HPR (그래낙티브 레티노이드)",
             "note": "레티노이드 계열이라 나라에 따라 레티놀과 같은 규제를 받는지 "
                     "따로 확인해야 합니다. 자극은 덜합니다."},
            {"inci": "Acetyl Hexapeptide-8", "name": "아세틸헥사펩타이드-8",
             "note": "표정 주름 쪽입니다. 단가가 높고 함량 대비 체감이 느립니다."},
            {"inci": "Adenosine", "name": "아데노신",
             "note": "한국 주름개선 기능성 고시 성분(0.04%)입니다. "
                     "수출 시에는 그 나라에서 기능성으로 인정되는지 별개입니다."},
        ],
    },
    {
        "key": "whitening",
        "label": "미백·잡티",
        "words": ["hydroquinone", "하이드로퀴논", "kojic acid", "코직산",
                  "arbutin", "알부틴"],
        "why": "하이드로퀴논은 EU 금지·미국 화장품 불가이고, 코직산·알부틴은 "
               "EU에서 농도 제한이 새로 붙었습니다.",
        "alts": [
            {"inci": "Niacinamide", "name": "나이아신아마이드",
             "note": "가장 무난합니다. 2~5%가 흔하고 단가도 낮습니다. "
                     "고농도에서 홍조를 호소하는 소비자가 있습니다."},
            {"inci": "Tranexamic Acid", "name": "트라넥사믹애씨드",
             "note": "의약품 성분이기도 해서 나라에 따라 화장품 사용 가부가 갈립니다. "
                     "일본·한국은 쓰지만 판매국 기준을 먼저 보세요."},
            {"inci": "Ascorbyl Glucoside", "name": "아스코빌글루코사이드",
             "note": "비타민C 유도체라 순수 아스코빅애씨드보다 안정합니다. "
                     "효능 발현이 느립니다."},
            {"inci": "Azelaic Acid", "name": "아젤라익애씨드",
             "note": "여드름 효능을 같이 표방하면 미국에서 OTC 의약품으로 갈립니다."},
        ],
    },
    {
        "key": "uv",
        "label": "자외선 차단",
        "words": ["oxybenzone", "benzophenone-3", "octinoxate",
                  "ethylhexyl methoxycinnamate", "벤조페논"],
        "why": "EU 한도가 낮아졌고, 하와이·팔라우 등은 산호 보호를 이유로 "
               "판매를 금지했습니다.",
        "alts": [
            {"inci": "Zinc Oxide", "name": "징크옥사이드",
             "note": "무기 자외선차단제입니다. 백탁과 사용감이 관건이고, "
                     "미국에서는 SPF를 표시하는 순간 OTC 의약품이 됩니다."},
            {"inci": "Titanium Dioxide", "name": "티타늄디옥사이드",
             "note": "나노 입자는 EU에서 별도 조건이 붙습니다. 흡입 위험 때문에 "
                     "파우더·스프레이 제형은 제한됩니다."},
            {"inci": "Bis-Ethylhexyloxyphenol Methoxyphenyl Triazine",
             "name": "티노소브 S",
             "note": "광안정성이 좋습니다. 미국 OTC 모노그래프에 없어 "
                     "미국에서는 쓸 수 없습니다. EU·아시아용입니다."},
            {"inci": "Diethylamino Hydroxybenzoyl Hexyl Benzoate",
             "name": "유비눌 A 플러스",
             "note": "UVA 쪽입니다. 역시 미국 모노그래프에 없습니다."},
        ],
    },
    {
        "key": "preservative",
        "label": "방부",
        "words": ["paraben", "파라벤", "formaldehyde", "dmdm hydantoin",
                  "imidazolidinyl urea", "diazolidinyl urea", "quaternium-15",
                  "methylisothiazolinone", "triclosan"],
        "why": "파라벤·포름알데하이드 방출 물질은 규제와 별개로 "
               "리테일러 배제 목록에 거의 다 올라 있습니다.",
        "alts": [
            {"inci": "Phenoxyethanol", "name": "페녹시에탄올",
             "note": "가장 흔합니다. EU 1%, 일본 1% 한도. 일부 clean 기준은 "
                     "이것도 꺼립니다."},
            {"inci": "1,2-Hexanediol", "name": "1,2-헥산다이올",
             "note": "방부 보조입니다. 단독으로는 약해서 보통 카프릴릴글라이콜과 "
                     "같이 씁니다. 함량이 높으면 단가가 올라갑니다."},
            {"inci": "Caprylyl Glycol", "name": "카프릴릴글라이콜",
             "note": "보습 겸 방부 보조. 단독 방부력은 부족합니다."},
            {"inci": "Sodium Benzoate", "name": "소듐벤조에이트",
             "note": "산성(pH 5 이하)에서만 듣습니다. 제형 pH를 먼저 확인해야 "
                     "합니다. 포타슘소르베이트와 짝으로 씁니다."},
            {"inci": "Ethylhexylglycerin", "name": "에틸헥실글리세린",
             "note": "방부 증강제입니다. 단독 방부제가 아닙니다."},
        ],
    },
    {
        "key": "surfactant",
        "label": "세정 계면활성제",
        "words": ["sodium lauryl sulfate", "sodium laureth sulfate",
                  "ammonium lauryl sulfate", "sls", "sles"],
        "why": "규제 위반은 아니지만 리테일러 배제 목록과 'sulfate-free' 마케팅 "
               "요구에 걸립니다.",
        "alts": [
            {"inci": "Sodium Cocoyl Isethionate", "name": "소듐코코일이세치오네이트",
             "note": "저자극 세정. 고체 바에 많이 씁니다. 단가가 SLS보다 높습니다."},
            {"inci": "Cocamidopropyl Betaine", "name": "코카미도프로필베타인",
             "note": "보조 계면활성제입니다. 단독으로는 세정력이 부족하고, "
                     "접촉성 알레르기 보고가 있어 clean 기준에서 꺼리는 곳도 있습니다."},
            {"inci": "Coco-Glucoside", "name": "코코글루코사이드",
             "note": "식물 유래. 거품이 약해 사용감 불만이 나올 수 있습니다."},
            {"inci": "Sodium Lauroyl Methyl Isethionate", "name": "SLMI",
             "note": "거품과 저자극을 같이 잡습니다. 단가가 높습니다."},
        ],
    },
    {
        "key": "emollient",
        "label": "유성 기제",
        "words": ["mineral oil", "petrolatum", "paraffinum liquidum",
                  "미네랄오일"],
        "why": "규제 위반은 아니지만 clean 기준과 '석유계 프리' 요구에 걸립니다.",
        "alts": [
            {"inci": "Squalane", "name": "스쿠알란",
             "note": "올리브·사탕수수 유래가 있습니다. 상어 유래인지 바이어가 "
                     "묻는 경우가 많으니 원료사 확인서를 받아 두세요."},
            {"inci": "Caprylic/Capric Triglyceride", "name": "카프릴릭/카프릭트라이글리세라이드",
             "note": "가볍고 안정합니다. 가장 무난한 대체입니다."},
            {"inci": "Simmondsia Chinensis Seed Oil", "name": "호호바 오일",
             "note": "천연 유래라 로트별 색·향 편차가 있습니다."},
        ],
    },
    {
        "key": "antioxidant",
        "label": "산화 방지",
        "words": ["butylated hydroxytoluene", "butylated hydroxyanisole",
                  "bht", "bha"],
        "why": "clean 기준 배제 목록에 올라 있습니다.",
        "alts": [
            {"inci": "Tocopherol", "name": "토코페롤 (비타민 E)",
             "note": "가장 흔한 대체입니다. 산패한 로트는 오히려 냄새가 납니다."},
            {"inci": "Rosmarinus Officinalis Leaf Extract", "name": "로즈마리 추출물",
             "note": "색과 향이 제형에 묻어납니다. 무향 제품에는 주의하세요."},
        ],
    },
    {
        "key": "exfoliant",
        "label": "각질 관리",
        "words": ["salicylic acid", "살리실릭"],
        "why": "미국에서 여드름 효능을 표방하면 OTC 의약품으로 갈립니다.",
        "alts": [
            {"inci": "Gluconolactone", "name": "글루코노락톤 (PHA)",
             "note": "분자가 커서 자극이 덜합니다. 각질 제거력은 약합니다."},
            {"inci": "Lactobionic Acid", "name": "락토바이오닉애씨드",
             "note": "보습을 같이 잡습니다. 단가가 높습니다."},
            {"inci": "Mandelic Acid", "name": "만델릭애씨드",
             "note": "AHA 계열입니다. 자외선 민감도 문구가 필요할 수 있습니다."},
        ],
    },
]
GROUP_MAP = {row["key"]: row for row in GROUPS}


def _norm(text):
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def group_for(name, inci=None):
    """이 성분이 어느 묶음에 걸리나."""
    text = _norm(" ".join(filter(None, [name, inci])))
    if not text:
        return None
    for group in GROUPS:
        if any(word in text for word in group["words"]):
            return group
    return None


def suggest(name, inci=None, country="eu", judge=None):
    """대안 후보. **후보를 같은 시장 기준으로 다시 판정해서** 돌려준다.

    judge: (name, inci) -> 판정 dict. 없으면 재판정 없이 후보만 준다.
           EU면 reg_store.judge, 미국이면 us_reg_store.judge 를 넘긴다.
    """
    group = group_for(name, inci)
    if not group:
        return None

    alts = []
    for alt in group["alts"]:
        row = dict(alt)
        row["verdict"] = None
        row["status"] = "unknown"
        row["blocked"] = False
        if judge:
            # 함량을 모르니 함량 조건은 걸지 않는다. **금지 여부만** 본다
            verdict = judge(alt["name"], alt["inci"])
            if verdict:
                row["verdict"] = verdict
                row["status"] = verdict["status"]
                row["blocked"] = verdict["status"] == "ban"
        alts.append(row)

    # 그 시장에서 막히지 않는 것부터 보여 준다.
    # 대안이랍시고 또 걸리는 걸 맨 위에 두면 같은 실수를 반복한다.
    #
    # '적합' 을 기준으로 가르면 안 된다. 미국은 일반 성분에 사전 허가 목록이
    # 없어서 무엇을 넣어도 '적합' 이 안 나온다(늘 '주의'다).
    # 그래서 **금지인가 아닌가**로만 가른다.
    order = {"ok": 0, "warn": 1, "unknown": 2, "ban": 3}
    alts.sort(key=lambda r: order.get(r["status"], 2))

    clean = [a for a in alts if not a["blocked"]]
    return {
        "key": group["key"],
        "label": group["label"],
        "why": group["why"],
        "alts": alts,
        # '적합' 이 아니라 '금지 조문에 걸리지 않는' 후보 수다
        "clean_count": len(clean),
        "blocked_count": len(alts) - len(clean),
        "country": country,
        "reviewed_on": REVIEWED_ON,
    }
