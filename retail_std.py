# -*- coding: utf-8 -*-
"""리테일러 입점 기준 - 법이 아니라 **매장이 정한 구매 조건**이다.

규제(us_reg_store)와 이 모듈은 성격이 전혀 다르다. 한 화면에 나란히 띄우되
절대로 섞어 적으면 안 된다.

  규제        어기면 통관이 막히고 회수 대상이 된다. 출처가 법령이다
  입점 기준   어겨도 불법이 아니다. 다만 **그 매장에 못 들어간다**.
              출처가 리테일러의 자체 기준이고, 바뀌면 공지 없이 바뀐다

해외영업에서 이게 왜 필요한가. 바이어가 "세포라에 넣을 건데 가능해요?" 라고
물으면 성분표를 보고 그 자리에서 답해야 한다. 나중에 배합 다 끝내고
"이 성분 때문에 안 된다" 를 알면 처방을 다시 짠다.

지켜야 할 것:
  - **법이 아니라고 화면에 적는다.** 규제 판정과 같은 색·같은 말을 쓰지 않는다
  - 리테일러 사이트를 긁지 않는다. 공개 API 가 없고 이용약관이 자동 수집을
    제한한다. 우리가 공개 문서를 보고 정리해 둔 **참고 목록**이고,
    기준일을 같이 적는다
  - 목록에 없다고 "적합" 이라고 단정하지 않는다. 전체 기준에는 성분 말고도
    포장·시험·표시 요건이 있다. 우리가 보는 건 **성분 배제 목록**뿐이다
  - 최종 확인은 리테일러가 준 최신 문서로 한다고 적는다
"""

import re

# ---------------------------------------------------------------------------
# 기준
# ---------------------------------------------------------------------------
#   as_of : 우리가 공개 문서를 보고 정리한 날. 리테일러가 고친 날이 아니다.
#   groups: 배제 성분 묶음. 이름 하나가 여러 표기로 온다

STANDARDS = [
    {
        "key": "sephora",
        "name": "Clean at Sephora",
        "org": "Sephora",
        "icon": "🧼",
        "as_of": "2026-09",
        "url": "https://www.sephora.com/beauty/clean-beauty-products",
        "note": "세포라 매장·온라인의 자체 표시 기준입니다. 법적 기준이 아닙니다. "
                "성분 배제 목록 외에 표시·시험 요건이 따로 있습니다.",
        "groups": [
            {"label": "파라벤", "words": ["paraben", "파라벤"]},
            {"label": "황산염 계면활성제 (SLS·SLES)",
             "words": ["sodium lauryl sulfate", "sodium laureth sulfate",
                       "ammonium lauryl sulfate", "ammonium laureth sulfate"]},
            {"label": "프탈레이트", "words": ["phthalate", "프탈레이트", "dbp", "dehp"]},
            {"label": "포름알데하이드·방출물질",
             "words": ["formaldehyde", "dmdm hydantoin", "imidazolidinyl urea",
                       "diazolidinyl urea", "quaternium-15", "포름알데하이드"]},
            {"label": "옥시벤존·옥티노세이트",
             "words": ["oxybenzone", "benzophenone-3", "octinoxate",
                       "ethylhexyl methoxycinnamate"]},
            {"label": "하이드로퀴논", "words": ["hydroquinone", "하이드로퀴논"]},
            {"label": "트리클로산·트리클로카반",
             "words": ["triclosan", "triclocarban"]},
            {"label": "BHA · BHT",
             "words": ["butylated hydroxyanisole", "butylated hydroxytoluene",
                       "bht", "bha"]},
            {"label": "콜타르", "words": ["coal tar"]},
            {"label": "미네랄오일·석유계",
             "words": ["mineral oil", "petrolatum", "paraffinum liquidum",
                       "미네랄오일"]},
            {"label": "레조르시놀", "words": ["resorcinol"]},
            {"label": "톨루엔", "words": ["toluene"]},
            {"label": "레티닐 팔미테이트", "words": ["retinyl palmitate"]},
            {"label": "스티렌", "words": ["styrene"]},
            {"label": "PFAS · PTFE",
             "words": ["ptfe", "perfluor", "polyfluor", "pfas"]},
            {"label": "알루미늄 염 (제한)", "words": ["aluminum chlorohydrate",
                                                   "aluminium chlorohydrate"]},
            {"label": "미공개 향료 (Fragrance)",
             "words": ["fragrance (parfum)"],
             "soft": True,
             "why": "향료를 쓰면 구성 성분을 밝혀야 합니다. 배제는 아니고 "
                    "공개 요건입니다"},
        ],
    },
]
STANDARD_MAP = {row["key"]: row for row in STANDARDS}

# 판정
VERDICTS = {
    "fail": {"label": "부적합", "css": "fail",
             "desc": "배제 목록에 걸리는 성분이 있습니다"},
    "check": {"label": "확인 필요", "css": "check",
              "desc": "조건부 항목이 걸립니다"},
    "pass": {"label": "걸리는 성분 없음", "css": "pass",
             "desc": "성분 배제 목록에서는 걸리는 것이 없습니다"},
    "unknown": {"label": "판정 불가", "css": "off",
                "desc": "대조할 성분이 없습니다"},
}

UNUSED_WORDS = ("미사용", "free-from", "free from", "미배합", "불검출")


def _norm(text):
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _is_unused(requested):
    return any(word in _norm(requested) for word in UNUSED_WORDS)


def check_ingredient(standard_key, name, inci=None, requested=None):
    """성분 하나가 그 기준의 배제 목록에 걸리는가.

    걸리지 않으면 None. "안 걸림" 은 뱃지를 띄우지 않는다 -
    화면이 초록 딱지로 뒤덮이면 정작 걸린 것이 안 보인다.
    """
    std = STANDARD_MAP.get(standard_key)
    if not std:
        return None

    text = _norm(" ".join(filter(None, [name, inci])))
    if not text:
        return None

    for group in std["groups"]:
        if not any(word in text for word in group["words"]):
            continue
        # 성분표에 '미사용' 으로 적혀 있으면 배합하지 않는다는 뜻이다
        if _is_unused(requested):
            return {"group": group["label"], "hit": True, "unused": True,
                    "soft": bool(group.get("soft")),
                    "why": "성분표에 미사용으로 표기돼 있어 걸리지 않습니다.",
                    "standard": std["name"]}
        return {"group": group["label"], "hit": True, "unused": False,
                "soft": bool(group.get("soft")),
                "why": group.get("why", "이 기준의 배제 목록에 있습니다."),
                "standard": std["name"]}
    return None


def product_verdict(standard_key, rows):
    """제품 단위 판정.

    rows: [{"name":…, "inci":…, "requested":…}, …]
    """
    std = STANDARD_MAP.get(standard_key)
    if not std:
        return None

    hits, softs, cleared = [], [], []
    for row in rows or []:
        found = check_ingredient(standard_key, row.get("name"),
                                 row.get("inci"), row.get("requested"))
        if not found:
            continue
        if found["unused"]:
            cleared.append(dict(found, name=row.get("name") or row.get("inci")))
        elif found["soft"]:
            softs.append(dict(found, name=row.get("name") or row.get("inci")))
        else:
            hits.append(dict(found, name=row.get("name") or row.get("inci")))

    if not rows:
        verdict = "unknown"
    elif hits:
        verdict = "fail"
    elif softs:
        verdict = "check"
    else:
        verdict = "pass"

    if verdict == "fail":
        why = "배제 성분 {}건이 걸립니다 — {}.".format(
            len(hits), " · ".join(h["group"] for h in hits))
    elif verdict == "check":
        why = "조건부 항목이 걸립니다 — {}.".format(
            " · ".join(s["group"] for s in softs))
    elif verdict == "pass":
        why = ("성분 {}건 중 배제 목록에 걸리는 것이 없습니다.".format(len(rows))
               + (" (미사용으로 표기된 {}건 포함)".format(len(cleared))
                  if cleared else ""))
    else:
        why = "대조할 성분이 없습니다."

    return {
        "key": std["key"], "name": std["name"], "org": std["org"],
        "icon": std["icon"], "as_of": std["as_of"], "url": std["url"],
        "note": std["note"],
        "verdict": verdict, "verdict_meta": dict(VERDICTS[verdict], key=verdict),
        "why": why, "hits": hits, "softs": softs, "cleared": cleared,
        "group_count": len(std["groups"]),
    }


def all_verdicts(rows):
    return [product_verdict(std["key"], rows) for std in STANDARDS]
