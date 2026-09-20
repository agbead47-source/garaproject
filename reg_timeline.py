# -*- coding: utf-8 -*-
"""규제 시행일과 유예기간.

"지금 기준으로는 적합" 이 안심의 근거가 못 되는 경우가 있다.
규정이 이미 공포됐고 시행일만 남아 있으면, 지금 개발을 시작한 처방이
출시 시점에는 못 팔린다. 화장품은 개발부터 출시까지 6개월~1년이 걸려서
**개발 기간 안에 시행일이 들어와 버린다.**

유예기간도 두 개로 나뉜다. 이걸 뭉뚱그리면 생산 일정이 어긋난다.
  - 신규 출시 금지일 : 이날부터 그 처방으로 **새로 시장에 내놓을 수 없다**
  - 시장 철수일     : 이날부터 이미 나가 있던 재고도 **거둬들여야 한다**

**이 표는 수기로 정리한 것이다.** 공보를 자동으로 긁어 오지 않는다.
공포된 규정의 시행일은 기계가 읽기 어려운 자리에 적혀 있고, 잘못 읽으면
"안 된다" 를 "된다" 로 바꿔 버린다. 그래서 사람이 원문을 보고 적고,
**확인한 날짜와 원문 링크를 같이 남긴다.** 화면에도 그렇게 적는다.

새 규정이 나오면 CHANGES 에 한 줄 더하고 REVIEWED_ON 을 고치면 된다.
"""

import re
from datetime import date, datetime, timezone

try:
    from zoneinfo import ZoneInfo
    SEOUL = ZoneInfo("Asia/Seoul")
except Exception:                                    # noqa: BLE001
    SEOUL = timezone.utc

# 이 표를 사람이 마지막으로 원문과 대조한 날.
#   화면에 그대로 띄운다. 오래됐으면 오래됐다고 보여야 한다.
REVIEWED_ON = "2026-09-20"
REVIEWED_BY = "해외영업팀 (수기 정리)"

# 시행일이 이만큼 안 남으면 지금 개발하는 처방이 위험하다.
#   화장품 개발~출시가 보통 6개월~1년이다.
SOON_DAYS = 365


# ---------------------------------------------------------------------------
# 다가오거나 최근에 바뀐 규정
# ---------------------------------------------------------------------------
#   words   : 성분표에서 이 낱말이 보이면 해당 규정을 붙인다
#   new_ban : 이날부터 신규 출시 금지
#   pull    : 이날부터 시장 철수 (이미 나간 재고도 거둬들임)
#   둘 중 하나만 있는 규정도 있다.

CHANGES = [
    {
        "key": "eu_2024_996_retinol",
        "region": "EU", "flag": "🇪🇺",
        "title": "비타민 A (레티놀류) 농도 제한",
        "rule": "Regulation (EU) 2024/996",
        "words": ["retinol", "retinyl acetate", "retinyl palmitate", "레티놀"],
        "what": "바디 로션 0.05% RE, 그 밖의 제품 0.3% RE 로 제한됩니다.",
        "new_ban": "2025-11-01",
        "pull": "2027-05-01",
        "url": "https://eur-lex.europa.eu/eli/reg/2024/996/oj",
    },
    {
        "key": "eu_2024_996_arbutin",
        "region": "EU", "flag": "🇪🇺",
        "title": "알부틴·알파알부틴 농도 제한",
        "rule": "Regulation (EU) 2024/996",
        "words": ["arbutin", "알부틴"],
        "what": "알파알부틴 페이스 크림 2%·바디 로션 0.5%, 알부틴 페이스 크림 7%.",
        "new_ban": "2025-11-01",
        "pull": "2027-05-01",
        "url": "https://eur-lex.europa.eu/eli/reg/2024/996/oj",
    },
    {
        "key": "eu_2024_996_kojic",
        "region": "EU", "flag": "🇪🇺",
        "title": "코직산 농도 제한",
        "rule": "Regulation (EU) 2024/996",
        "words": ["kojic acid", "코직산", "코지산"],
        "what": "얼굴·손 제품 1% 로 제한됩니다.",
        "new_ban": "2025-11-01",
        "pull": "2027-05-01",
        "url": "https://eur-lex.europa.eu/eli/reg/2024/996/oj",
    },
    {
        "key": "eu_2024_996_genistein",
        "region": "EU", "flag": "🇪🇺",
        "title": "제니스테인·다이드제인 농도 제한",
        "rule": "Regulation (EU) 2024/996",
        "words": ["genistein", "daidzein", "제니스테인", "다이드제인"],
        "what": "제니스테인 0.007%, 다이드제인 0.02%.",
        "new_ban": "2025-11-01",
        "pull": "2027-05-01",
        "url": "https://eur-lex.europa.eu/eli/reg/2024/996/oj",
    },
    {
        "key": "eu_2022_1176_bp3",
        "region": "EU", "flag": "🇪🇺",
        "title": "벤조페논-3 · 옥토크릴렌 농도 조정",
        "rule": "Regulation (EU) 2022/1176",
        "words": ["benzophenone-3", "oxybenzone", "octocrylene", "벤조페논"],
        "what": "자외선차단 용도 한도가 낮아졌습니다 (BP-3 얼굴·손 6%, 그 밖 2.2% 등).",
        "new_ban": "2023-03-17",
        "pull": "2023-07-17",
        "url": "https://eur-lex.europa.eu/eli/reg/2022/1176/oj",
    },
    {
        "key": "eu_2022_1181_lilial",
        "region": "EU", "flag": "🇪🇺",
        "title": "부틸페닐메틸프로피오날(Lilial) 사용 금지",
        "rule": "Regulation (EU) 2021/1902 (CMR Omnibus V)",
        "words": ["butylphenyl methylpropional", "lilial", "bmhca"],
        "what": "화장품 사용이 금지됐습니다.",
        "new_ban": "2022-03-01",
        "pull": "2022-03-01",
        "url": "https://eur-lex.europa.eu/eli/reg/2021/1902/oj",
    },
    {
        "key": "us_mocra_listing",
        "region": "미국", "flag": "🇺🇸",
        "title": "MoCRA 시설 등록 · 제품 리스팅 의무",
        "rule": "Modernization of Cosmetics Regulation Act of 2022",
        # 성분이 아니라 제품·시설에 걸리는 의무라 낱말 대조를 하지 않는다
        "words": [],
        "product_level": True,
        "what": "미국에 수출하는 제조소는 FDA 등록, 제품은 리스팅을 해야 합니다. "
                "시설 등록은 2년마다, 제품 리스팅은 연 1회 갱신합니다.",
        "new_ban": "2023-12-29",
        "pull": "",
        "url": "https://www.fda.gov/cosmetics/cosmetics-laws-regulations/"
               "modernization-cosmetics-regulation-act-2022-mocra",
    },
]


STATES = {
    "upcoming": {"label": "시행 예정", "css": "upcoming", "icon": "⏳"},
    "soon": {"label": "시행 임박", "css": "soon", "icon": "⏳"},
    "new_banned": {"label": "신규 출시 금지", "css": "partial", "icon": "⚠️"},
    "in_force": {"label": "시행 중", "css": "inforce", "icon": "●"},
}


def _today():
    return datetime.now(SEOUL).date()


def _as_date(text):
    text = (text or "").strip()[:10]
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _state(change, ref=None):
    """오늘 기준으로 이 규정이 어디까지 왔나."""
    ref = ref or _today()
    new_ban = _as_date(change.get("new_ban"))
    pull = _as_date(change.get("pull"))

    if pull and ref >= pull:
        return "in_force", 0
    if new_ban and ref >= new_ban:
        # 새로 못 내놓지만 나가 있는 재고는 아직 팔 수 있는 구간
        days = (pull - ref).days if pull else 0
        return "new_banned", days
    if new_ban:
        days = (new_ban - ref).days
        return ("soon" if days <= SOON_DAYS else "upcoming"), days
    return "in_force", 0


def decorate(change, ref=None):
    state, days = _state(change, ref)
    item = dict(change)
    item["state"] = state
    item["state_meta"] = dict(STATES[state], key=state)
    item["days"] = days

    if state == "upcoming":
        item["why"] = ("{} 부터 신규 출시가 막힙니다 (D-{}). "
                       "지금 개발을 시작해도 출시 시점에는 이 처방으로 못 냅니다."
                       .format(change["new_ban"], days))
    elif state == "soon":
        item["why"] = ("{} 부터 신규 출시가 막힙니다 (D-{}). "
                       "화장품 개발·출시가 보통 6개월~1년이라 지금 잡는 처방이 걸립니다."
                       .format(change["new_ban"], days))
    elif state == "new_banned":
        item["why"] = ("{} 부터 새로 내놓을 수 없습니다. "
                       .format(change["new_ban"])
                       + ("나가 있는 재고도 {} 까지만 팔 수 있습니다 (D-{})."
                          .format(change["pull"], days) if change.get("pull")
                          else "재고 철수일은 정해지지 않았습니다."))
    else:
        item["why"] = "{} 부터 이미 시행 중입니다.".format(
            change.get("pull") or change.get("new_ban"))
    return item


def _norm(text):
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def for_ingredient(name, inci=None, region=None, ref=None):
    """성분 하나에 걸리는 규정 변경. 없으면 빈 목록."""
    text = _norm(" ".join(filter(None, [name, inci])))
    if not text:
        return []
    out = []
    for change in CHANGES:
        if change.get("product_level") or not change["words"]:
            continue
        if region and change["region"] != region:
            continue
        if any(word in text for word in change["words"]):
            out.append(decorate(change, ref))
    return out


def board(region=None, ref=None):
    """다가오는 변경 목록. 급한 순."""
    rows = [decorate(c, ref) for c in CHANGES
            if not region or c["region"] == region]
    order = {"soon": 0, "new_banned": 1, "upcoming": 2, "in_force": 3}
    rows.sort(key=lambda r: (order[r["state"]], r["days"]))
    return {
        "rows": rows,
        "pending": [r for r in rows if r["state"] != "in_force"],
        "reviewed_on": REVIEWED_ON,
        "reviewed_by": REVIEWED_BY,
        "today": _today().isoformat(),
    }
