# -*- coding: utf-8 -*-
"""무역 도우미 - 규칙 기반 챗봇 (가안).

LLM 이 아니다. 질문에서 낱말을 찾아 담당 함수로 넘기는 **규칙 기반**이다.
화면에 그렇게 밝히고, 답 끝에는 근거가 된 화면으로 가는 링크를 붙인다.

다만 답은 지어내지 않는다. 이 프로젝트가 이미 들고 있는 값에서 꺼내 온다.

    "미국 수출 얼마나 늘었어?"   -> trade_store  (UN Comtrade 실데이터)
    "판지값 올랐어?"             -> packaging_store (BLS PPI 실데이터)
    "레티놀 EU 에서 돼?"         -> reg_store    (EU 법령 실데이터)
    "Glowtree 담당자 누구야?"    -> contact_store (실제 저장값)
    "요즘 뜨는 성분?"            -> trend_store
    "FOB 가 뭐야?"               -> 용어 사전

모르면 모른다고 한다. 비슷한 말로 둘러대지 않는다.

TODO: 실제 연동 (LLM 대화). 지금은 붙이는 자리만 만들어 둔 상태다.
"""

import re
import unicodedata

BOT_NAME = "무역 도우미"
BOT_KIND = "규칙 기반 (가안)"

# 처음 열었을 때 띄우는 인사와 추천 질문
GREETING = {
    "text": ("안녕하세요. 해외영업 업무를 옆에서 거드는 {}입니다.\n"
             "지금 이 화면들이 들고 있는 값에서 찾아 답합니다. "
             "모르는 건 모른다고 말씀드립니다.").format(BOT_NAME),
    "chips": [
        "아마존 순위 요약해줘",
        "미국 수출 얼마나 늘었어?",
        "판지값 올랐어?",
        "레티놀 EU 기준이 어떻게 돼?",
        "Glowtree 담당자 누구야?",
        "FOB랑 CIF 차이가 뭐야?",
    ],
}

# 프로젝트 화면에서 띄우는 추천 질문. 그 건의 값으로 답할 수 있는 것들이다.
PROJECT_CHIPS = [
    "이 건 어디까지 왔어?",
    "확인사항 뭐 남았어?",
    "샘플 어떻게 됐어?",
    "견적 대안 비교해줘",
]


def greeting(project_id=None):
    """처음 열었을 때 띄울 인사와 추천 질문."""
    if not project_id:
        return dict(GREETING)
    return {
        "text": GREETING["text"] + "\n지금 프로젝트를 열어 두셨네요. "
                                   "그 건에 대해서도 답합니다.",
        "chips": PROJECT_CHIPS + GREETING["chips"][:2],
    }


# 무역 용어. 해외영업이 신입에게 매번 설명하게 되는 것들만 골랐다.
GLOSSARY = [
    {"terms": ["exw", "공장인도"], "title": "EXW (Ex Works · 공장 인도)",
     "body": "공장 문 앞까지가 우리 책임입니다. 싣는 것부터 바이어가 합니다. "
             "가장 싸 보이지만 바이어 쪽 물류비가 커서 최종 단가 비교가 안 됩니다."},
    {"terms": ["fob", "본선인도"], "title": "FOB (Free On Board · 본선 인도)",
     "body": "수출항에서 배에 싣는 순간까지가 우리 몫입니다. 한국 ODM 견적에서 "
             "가장 많이 쓰는 조건이고, 보통 'FOB 부산'처럼 항구를 같이 적습니다."},
    {"terms": ["cif", "운임보험료포함"], "title": "CIF (Cost, Insurance and Freight)",
     "body": "도착항까지의 운임과 적하보험까지 우리가 부담합니다. "
             "FOB보다 단가가 높게 보이는 게 정상입니다 - 운임이 들어 있으니까요. "
             "견적에 인코텀즈를 안 적으면 여기서 꼭 싸움이 납니다."},
    {"terms": ["ddp"], "title": "DDP (Delivered Duty Paid · 관세 포함 인도)",
     "body": "수입 통관과 관세까지 우리가 냅니다. 바이어는 편하지만 "
             "상대국 세율·통관 대리인까지 우리가 떠안는 조건이라 신중해야 합니다."},
    {"terms": ["moq", "최소주문", "최소 주문"], "title": "MOQ (최소 주문 수량)",
     "body": "생산을 걸 수 있는 최소 수량입니다. 용기 금형과 원료 최소 구매량에서 "
             "정해지는 경우가 많아, 바이어가 깎아 달라고 해도 공장이 못 내려 주는 일이 흔합니다."},
    {"terms": ["사급", "자급"], "title": "사급 / 자급",
     "body": "사급은 고객사가 용기·부자재를 직접 사서 공장에 넣어 주는 것, "
             "자급은 공장이 사서 단가에 포함하는 것입니다. 어느 쪽이냐에 따라 "
             "단가와 책임 소재가 통째로 달라집니다."},
    {"terms": ["coa", "성적서"], "title": "CoA (Certificate of Analysis · 시험성적서)",
     "body": "생산 로트별 시험 결과지입니다. 바이어 QA가 통관·판매 허가에 씁니다. "
             "로트가 바뀌면 다시 발급해야 합니다."},
    {"terms": ["msds", "sds"], "title": "MSDS / SDS (물질안전보건자료)",
     "body": "성분의 위험성과 취급법을 적은 문서입니다. 항공 운송과 일부 국가 통관에서 요구합니다."},
    {"terms": ["cpnp", "eu 등록"], "title": "CPNP (EU 화장품 신고 포털)",
     "body": "EU에 화장품을 팔려면 판매 전에 CPNP 신고가 있어야 합니다. "
             "책임자(RP)가 EU 역내에 있어야 하고, PIF(제품정보파일)를 갖춰 둬야 합니다."},
    {"terms": ["mocra", "fda"], "title": "MoCRA (미국 화장품 규제 현대화법)",
     "body": "미국은 시설 등록과 제품 리스팅, 안전성 입증 자료를 요구합니다. "
             "미국 내 책임자 이름과 주소를 라벨에 적어야 합니다."},
    {"terms": ["l/c", "lc", "신용장"], "title": "L/C (신용장)",
     "body": "은행이 대금 지급을 보증하는 방식입니다. 서류가 조건과 한 글자라도 다르면 "
             "지급이 막히기 때문에(하자), 선적 서류를 글자 단위로 맞춰야 합니다."},
    {"terms": ["t/t", "tt", "전신환"], "title": "T/T (전신환 송금)",
     "body": "가장 흔한 결제 방식입니다. 보통 계약금 30% 선입금 + 선적 전 잔금 70% 처럼 나눕니다. "
             "선적 후 결제(T/T after B/L)는 미수 위험이 있어 거래 이력을 보고 정합니다."},
    {"terms": ["리드타임", "lead time", "납기"], "title": "리드타임",
     "body": "발주부터 출고까지 걸리는 시간입니다. 화장품 ODM은 보통 "
             "처방 확정 → 용기 발주(4~6주) → 생산(2~3주) → 검사·출고 순인데, "
             "지연은 대개 용기에서 납니다."},
    {"terms": ["인코텀즈", "incoterms"], "title": "인코텀즈 (Incoterms)",
     "body": "비용과 위험이 어디서 넘어가는지 정한 국제 규칙입니다. "
             "EXW → FOB → CFR → CIF → DDP 순으로 우리 부담이 커집니다. "
             "견적서에는 조건과 지명(예: CIF Los Angeles)을 반드시 함께 적습니다."},
]

# 화면 안내. "어디서 하냐" 는 질문이 생각보다 많다.
SCREENS = [
    {"terms": ["견적", "견적서", "단가", "가격 계산", "마진"],
     "label": "영업단가 계산", "endpoint": "pricing",
     "hint": "원가·마진·인코텀즈를 넣으면 단가가 나오고, 거기서 견적서를 뽑습니다."},
    {"terms": ["개발요청서", "요청서", "변환", "연구소", "공장"],
     "label": "개발요청서 분석", "endpoint": "upload",
     "hint": "고객사 요청서를 올리면 연구소·공장이 쓰는 문서로 바꿔 줍니다."},
    {"terms": ["일정", "스케줄", "샘플 일정"],
     "label": "일정관리", "endpoint": "schedule.board",
     "hint": "건별로 샘플·생산·선적 일정을 잡아 둡니다."},
    {"terms": ["규제", "성분 규제", "허용", "배합한도"],
     "label": "국가별 규제 검색", "endpoint": "regulation",
     "hint": "성분표를 올리면 국가별 허용 기준과 대조합니다."},
    {"terms": ["고객사", "바이어", "담당자", "연락처"],
     "label": "고객사 관리", "endpoint": "customers",
     "hint": "고객사와 담당자, 요청사항·메일 이력을 봅니다."},
    {"terms": ["수출", "수입", "수출입", "시장", "통계"],
     "label": "오늘의 트렌드 · 국가별 수출입", "endpoint": "trends",
     "hint": "국가별 화장품 수출입 실적을 봅니다."},
    {"terms": ["포장", "용기", "부자재", "포장재"],
     "label": "포장재 가격 동향", "endpoint": "packaging",
     "hint": "용기·포장 소재값 추세를 봅니다."},
    {"terms": ["신규", "발굴", "바이어 찾기", "prospect"],
     "label": "신규 바이어 발굴", "endpoint": "prospecting.board",
     "hint": "조건에 맞는 신규 바이어 후보를 봅니다."},
]

# 나라 이름 -> 규제 검색 코드 / 수출입 통계 이름
COUNTRY_WORDS = {
    "미국": {"reg": "us", "trade": "미국"},
    "eu": {"reg": "eu", "trade": ""},
    "유럽": {"reg": "eu", "trade": ""},
    "중국": {"reg": "cn", "trade": "중국"},
    "일본": {"reg": "jp", "trade": "일본"},
    "베트남": {"reg": "vn", "trade": "베트남"},
    "홍콩": {"reg": "", "trade": "홍콩"},
    "태국": {"reg": "", "trade": "태국"},
    "러시아": {"reg": "", "trade": "러시아"},
    "폴란드": {"reg": "", "trade": "폴란드"},
    "영국": {"reg": "", "trade": "영국"},
    "캐나다": {"reg": "", "trade": "캐나다"},
    "인도네시아": {"reg": "", "trade": "인도네시아"},
    "호주": {"reg": "", "trade": "호주"},
    "싱가포르": {"reg": "", "trade": "싱가포르"},
    "말레이시아": {"reg": "", "trade": "말레이시아"},
    "아랍에미리트": {"reg": "", "trade": "아랍에미리트"},
}


# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------

def _norm(text):
    """비교용 표기.

    악센트를 떼어 낸다 - "Lumiere" 로 쳐도 "Lumière Skin" 을 찾아야 한다.
    한글 음절은 NFD 로 풀었다가 NFC 로 다시 합쳐지므로 그대로 남는다.
    """
    text = unicodedata.normalize("NFKC", (text or "")).strip().lower()
    stripped = "".join(ch for ch in unicodedata.normalize("NFD", text)
                       if not unicodedata.combining(ch))
    return unicodedata.normalize("NFC", stripped)


def _reply(text, chips=None, links=None, rows=None, source=""):
    """답 한 덩어리. 근거가 된 화면 링크를 같이 돌려준다."""
    return {
        "text": text.strip(),
        "chips": chips or [],
        "links": links or [],
        "rows": rows or [],
        "source": source,
    }


def _country_in(text):
    for word, meta in COUNTRY_WORDS.items():
        if word in text:
            return word, meta
    return "", None


def _pct(value):
    return "{}{:.1f}%".format("+" if value > 0 else "", value)


# ---------------------------------------------------------------------------
# 답변 - 국가별 수출입 (UN Comtrade 실데이터)
# ---------------------------------------------------------------------------

def _answer_trade(text):
    import trade_store

    data = trade_store.get_trade(top=0)
    if not data["ready"]:
        return _reply(
            "수출입 통계를 아직 받아 두지 않았습니다.\n"
            "오늘의 트렌드 → 국가별 수출입에서 '통계 수집'을 한 번 눌러 주세요.",
            links=[{"label": "국가별 수출입 열기", "endpoint": "trends",
                    "args": {"view": "trade"}}])

    word, meta = _country_in(text)
    name = (meta or {}).get("trade", "")
    if name:
        row = next((r for r in data["rows"] if r["name"] == name), None)
        if row is None:
            return _reply("{} 은(는) {}년 통계에서 찾지 못했습니다.".format(word, data["year"]),
                          source="UN Comtrade")

        export = row["X"]
        lines = ["{} {} — {}년 화장품 수출 실적입니다.".format(
            row["flag"], row["name"], data["year"])]
        if export["value"] is not None:
            lines.append("· 수출 {:,.1f}백만 USD (전체의 {:.1f}%)".format(
                export["value"] / 1e6, row.get("share") or 0))
        if export["growth"] is not None:
            lines.append("· 전년비 {}".format(_pct(export["growth"])))
        else:
            lines.append("· 전년비는 비교할 실측값이 없어 내지 않았습니다")
        if export["unit_price"]:
            lines.append("· kg당 {:,.1f} USD".format(export["unit_price"]))
        if row["M"]["value"]:
            lines.append("· 같은 해 우리 수입은 {:,.1f}백만 USD".format(row["M"]["value"] / 1e6))
        lines.append("\nHS 3303·3304·3305·3307 합계, 대한민국 신고 기준입니다.")

        return _reply("\n".join(lines),
                      chips=["kg당 단가가 높은 시장은?", "수출 상위 5개국 알려줘"],
                      links=[{"label": "국가별 수출입에서 보기", "endpoint": "trends",
                              "args": {"view": "trade"}}],
                      source="UN Comtrade · {}년".format(data["year"]))

    if "단가" in text or "kg" in text:
        rows = [r for r in data["rows"][:40] if r["X"]["unit_price"]]
        rows.sort(key=lambda r: r["X"]["unit_price"], reverse=True)
        top = rows[:5]
        lines = ["{}년 기준, 수출 상위권에서 kg당 단가가 높은 시장입니다.".format(data["year"])]
        for r in top:
            lines.append("· {} {} — {:,.1f} USD/kg (수출 {:,.0f}백만 USD)".format(
                r["flag"], r["name"], r["X"]["unit_price"], (r["X"]["value"] or 0) / 1e6))
        lines.append("\n단가가 높다고 좋은 시장은 아닙니다. 고가 라인 위주로 나가는 "
                     "시장일 수도, 물량이 적어 튄 값일 수도 있습니다.")
        return _reply("\n".join(lines),
                      links=[{"label": "국가별 수출입 열기", "endpoint": "trends",
                              "args": {"view": "trade"}}],
                      source="UN Comtrade · {}년".format(data["year"]))

    top = data["rows"][:5]
    totals = data["totals"]
    lines = ["{}년 화장품 수출은 모두 {:,.0f}백만 USD".format(
        data["year"], totals["export"] / 1e6)]
    if totals["export_growth"] is not None:
        lines[-1] += " ({} 전년비)".format(_pct(totals["export_growth"]))
    lines.append("상위 시장입니다.")
    for r in top:
        growth = (" {}".format(_pct(r["X"]["growth"]))
                  if r["X"]["growth"] is not None else " (비교 불가)")
        lines.append("· {} {} — {:,.0f}백만 USD{}".format(
            r["flag"], r["name"], (r["X"]["value"] or 0) / 1e6, growth))

    return _reply("\n".join(lines),
                  chips=["미국 수출 얼마나 늘었어?", "kg당 단가가 높은 시장은?"],
                  links=[{"label": "국가별 수출입 열기", "endpoint": "trends",
                          "args": {"view": "trade"}}],
                  source="UN Comtrade · {}년".format(data["year"]))


# ---------------------------------------------------------------------------
# 답변 - 포장재 (BLS PPI 실데이터)
# ---------------------------------------------------------------------------

_PACK_WORDS = {
    "판지": "paperboard", "종이": "paperboard", "단상자": "paperboard",
    "펄프": "pulp", "라벨": "pulp",
    "유리": "glass", "유리병": "glass",
    "플라스틱": "plastic_resin", "수지": "plastic_resin", "레진": "plastic_resin",
    "페트": "plastic_bottle", "플라스틱 병": "plastic_bottle",
    "고무": "synthetic_rubber", "개스킷": "synthetic_rubber", "오링": "synthetic_rubber",
    "알루미늄": "aluminum",
    "실리콘": "silicone",
}


def _answer_packaging(text):
    import packaging_store

    wanted = [key for word, key in _PACK_WORDS.items() if word in text]
    keys = wanted or [m["key"] for m in packaging_store.MATERIALS
                      if m["source"] == "bls"]

    cards = [packaging_store.material_view(k) for k in dict.fromkeys(keys)]
    lines, rows = [], []
    for card in cards:
        if card["status"] == "unsupported":
            lines.append("· {} — 무료로 쓸 수 있는 가격 출처를 찾지 못해 넣지 않았습니다. "
                         "합성고무 지수로 대신하지 않습니다(다른 재질입니다).".format(card["name"]))
            continue
        if card["status"] == "needs_key":
            lines.append("· {} — Metals.Dev API 키가 설정되지 않았습니다.".format(card["name"]))
            continue
        if not card["latest"]:
            lines.append("· {} — 아직 수집하지 않았습니다.".format(card["name"]))
            continue

        change = next((c for c in card["changes"] if c["label"] == "전년 동월 대비"), None)
        month = next((c for c in card["changes"] if c["label"] == "전월 대비"), None)
        piece = "· {} {} — {} {}".format(
            card["icon"], card["name"],
            "{:,.1f}".format(card["latest"]["value"]), card["unit"])
        if month:
            piece += " · 전월 {}".format(_pct(month["pct"]))
        if change:
            piece += " · 전년 동월 {}".format(_pct(change["pct"]))
        lines.append(piece)
        rows.append({"label": card["name"], "value": _pct(change["pct"]) if change else "—"})

    head = ("물어보신 소재의 최근 값입니다." if wanted
            else "포장재 소재값 최근 상황입니다.")

    # 주의 문구는 실제로 보여 준 값에만 붙인다. 값도 없는데 지수 설명만 달리면 군더더기다
    shown = [c for c in cards if c["latest"]]
    tail = ""
    if any(c["source"] == "bls" for c in shown):
        tail += ("\n미국 생산자물가지수(BLS PPI)라 미국 시장 참고지수이고, 화장품 전용 "
                 "지수가 아닙니다. 지수이지 가격이 아니어서 국내 용기 단가와 바로 "
                 "이어지지 않습니다.")
    if len(shown) > 1:
        tail += ("\n소재마다 용기에서 차지하는 비중이 달라, 이 숫자들을 평균 내어 "
                 "'포장비 몇 % 인상'으로 쓰면 틀립니다.")

    return _reply("\n".join([head] + lines) + tail,
                  chips=["유리병 값은 어때?", "알루미늄은?"],
                  links=[{"label": "포장재 가격 동향 열기", "endpoint": "packaging"}],
                  rows=rows,
                  source="BLS 생산자물가지수")


# ---------------------------------------------------------------------------
# 답변 - 규제
# ---------------------------------------------------------------------------

def _answer_regulation(text):
    import dummy_data

    word, meta = _country_in(text)
    country = (meta or {}).get("reg") or "all"

    # 성분명 추리기: 사전에 있는 성분 이름이 문장에 들어 있는지 본다
    rows = dummy_data.search_regulations(country, "", "all")
    hit_name = ""
    for row in rows:
        for candidate in (row["name"], row["inci"]):
            if candidate and _norm(candidate) in text:
                hit_name = row["name"]
                break
        if hit_name:
            break

    if not hit_name:
        return _reply(
            "어떤 성분인지 알려 주시면 국가별 허용 기준을 찾아보겠습니다.\n"
            "(예: \"레티놀 EU 기준\", \"나이아신아마이드 중국에서 돼?\")\n"
            "성분표 파일이 있으면 규제 검색 화면에 올리는 쪽이 빠릅니다.",
            chips=["레티놀 EU 기준이 어떻게 돼?", "나이아신아마이드 미국 기준은?"],
            links=[{"label": "국가별 규제 검색 열기", "endpoint": "regulation"}])

    picked = [r for r in rows if r["name"] == hit_name]
    if country != "all":
        picked = [r for r in picked if r["country_code"] == country] or picked

    lines = ["{} 판정입니다.".format(hit_name)]
    live = False
    for row in picked[:5]:
        badge = {"ok": "적합", "warn": "주의", "ban": "사용 불가"}.get(row["status"], row["status"])
        lines.append("· {} {} — {} / {}".format(
            row["country_flag"], row["country_name"], badge, row["limit"]))
        live = live or row.get("live")

    if live:
        lines.append("\nEU 는 실제 법령(Regulation (EC) No 1223/2009 통합본)으로 판정한 값입니다. "
                     "나머지 국가는 아직 더미입니다.")
    else:
        lines.append("\n표시된 국가는 아직 더미 데이터입니다. EU 만 실제 법령으로 판정합니다.")
    lines.append("판정은 참고용입니다. 최종 확인은 규제 담당과 하셔야 합니다.")

    return _reply("\n".join(lines),
                  chips=["성분표 올려서 한 번에 보려면?"],
                  links=[{"label": "국가별 규제 검색 열기", "endpoint": "regulation"}],
                  source="EU 화장품 규정 실데이터" if live else "가안 더미")


# ---------------------------------------------------------------------------
# 답변 - 고객사·담당자
# ---------------------------------------------------------------------------

def _answer_customer(text):
    import contact_store
    import customer_store
    import dummy_data

    profiles = (dummy_data.get_customer_profiles()
                + customer_store.profiles())
    def _mentions(profile):
        """회사명 전체든 앞 낱말이든 들어 있으면 그 고객사로 본다."""
        name = _norm(profile["name"])
        if name and name in text:
            return True
        head = re.split(r"[\s.,]", name)[0]
        return len(head) >= 4 and head in text

    target = next((p for p in profiles if _mentions(p)), None)

    if target is None:
        names = ", ".join(p["name"] for p in profiles[:5])
        return _reply(
            "어느 고객사인지 알려 주세요.\n등록된 곳: {}{}".format(
                names, " 등" if len(profiles) > 5 else ""),
            chips=["Glowtree 담당자 누구야?"],
            links=[{"label": "고객사 관리 열기", "endpoint": "customers"}])

    contacts = contact_store.list_contacts(target["id"], include_inactive=False)
    lines = ["{} {} — {}".format(target["flag"], target["name"],
                                 target.get("city") or target.get("country", ""))]

    if contacts:
        lines.append("담당자 {}명입니다.".format(len(contacts)))
        for c in contacts:
            piece = "· {}{} — {}".format(
                c["name"], " (대표)" if c["is_primary"] else "",
                c["role_meta"]["label"])
            if c["title"]:
                piece += " · " + c["title"]
            if c["email"]:
                piece += "\n  " + c["email"]
            lines.append(piece)
    else:
        lines.append("등록된 담당자가 없습니다. 고객사 관리에서 넣거나 엑셀로 한 번에 올릴 수 있습니다.")

    wants = [r for r in target.get("requests", []) if r["priority"] == "high"][:2]
    if wants:
        lines.append("\n매번 요구하는 것:")
        for r in wants:
            lines.append("· {}".format(r["title"]))

    return _reply("\n".join(lines),
                  chips=["고객사 명단 엑셀로 받으려면?"],
                  links=[{"label": "{} 상세 열기".format(target["name"]),
                          "endpoint": "customer_detail",
                          "args": {"customer_id": target["id"]}}],
                  source="고객사 관리 저장값")


# ---------------------------------------------------------------------------
# 답변 - 성분 트렌드
# ---------------------------------------------------------------------------

def _answer_trend(text):
    import trend_store

    data = trend_store.get_ingredient_trends(auto_refresh=False)
    rising = data["rising"][:3]
    if not rising:
        return _reply("성분 관심도를 아직 수집하지 않았습니다. 오늘의 트렌드에서 새로고침해 주세요.",
                      links=[{"label": "오늘의 트렌드 열기", "endpoint": "trends"}])

    lines = ["최근 2주 사이 관심도가 오른 성분입니다."]
    for row in rising:
        piece = "· {} ({}) — {}".format(row["name"], row["category"], _pct(row["growth"]))
        if row.get("eu") and row["eu"]["level"] != "ok":
            piece += " · EU {}".format(row["eu"]["label"])
        lines.append(piece)

    lines.append("\n위키백과 문서 조회수를 관심도 대리 지표로 쓴 값입니다. "
                 "판매량이 아닙니다.")
    return _reply("\n".join(lines),
                  chips=["요즘 뜨는 성분으로 요청서 만들려면?"],
                  links=[{"label": "오늘의 트렌드 열기", "endpoint": "trends"}],
                  source="Wikimedia Pageviews")


# ---------------------------------------------------------------------------
# 답변 - 용어 / 화면 안내
# ---------------------------------------------------------------------------

def _answer_glossary(text):
    for item in GLOSSARY:
        if any(term in text for term in item["terms"]):
            # FOB 와 CIF 를 같이 물어보는 경우가 많다
            others = [g for g in GLOSSARY
                      if g is not item and any(t in text for t in g["terms"])]
            blocks = [item] + others[:1]
            body = "\n\n".join("{}\n{}".format(b["title"], b["body"]) for b in blocks)
            return _reply(body,
                          chips=["인코텀즈 전체가 궁금해", "결제 조건은 뭐가 있어?"],
                          links=[{"label": "영업단가 계산에서 적용해 보기",
                                  "endpoint": "pricing"}],
                          source="무역 용어")
    return None


def _answer_screen(text):
    for item in SCREENS:
        if any(term in text for term in item["terms"]):
            return _reply(
                "{} 화면에서 하실 수 있습니다.\n{}".format(item["label"], item["hint"]),
                links=[{"label": "{} 열기".format(item["label"]),
                        "endpoint": item["endpoint"]}])
    return None


# ---------------------------------------------------------------------------
# 라우팅
# ---------------------------------------------------------------------------

_TRADE_RE = re.compile(
    r"수출|수입|수출입|시장 규모|얼마나 (늘|줄)|comtrade|kg ?당|"
    r"상위.{0,4}(국|시장)|어느 (나라|시장)")
_PACK_RE = re.compile(r"포장|용기|부자재|단상자|판지|펄프|유리|플라스틱|알루미늄|고무|실리콘|자재값|원부자재")
_REG_RE = re.compile(r"규제|허용|기준|배합|금지|사용 가능|annex|cpnp|mocra")
_CUST_RE = re.compile(r"고객사|바이어|담당자|연락처|이메일 주소|거래처")
_TREND_RE = re.compile(r"트렌드|뜨는|인기|관심도|성분 추천")
_RANK_RE = re.compile(r"아마존|amazon|베스트셀러|순위|랭킹|잘 팔|많이 팔")


def _answer_rank(text):
    """아마존 순위. 분석(데모)까지 같이 돌려준다."""
    import beauty_rank_store as store

    cat = "beauty"
    for row in store.AMAZON_CATEGORIES:
        if row["label"].replace(" ", "") in text.replace(" ", ""):
            cat = row["key"]
            break

    data = store.brief(cat)
    board = store.rank_board(cat)
    link = {"label": "아마존 순위 열기", "endpoint": "trends",
            "args": {"view": "rank", "cat": cat}}

    if not data["ready"]:
        if not board["enabled"]:
            return _reply(
                "아마존 순위를 아직 받아 두지 않았습니다.\n"
                "아마존 이용약관이 자동 수집을 제한해서 기본을 꺼 뒀습니다. "
                ".env 에 AMAZON_RANK_ENABLED=1 을 넣으면 켜집니다.",
                links=[link])
        return _reply("아마존 순위를 아직 받아 두지 않았습니다. "
                      "트렌드 화면에서 '지금 수집'을 눌러 주세요.", links=[link])

    lines = [data["headline"], ""]
    for row in board["rows"][:5]:
        mark = ""
        if row["move"] == "new":
            mark = " NEW"
        elif row["move"] in ("up", "down"):
            mark = " {}{}".format(row["move_meta"]["label"], row["delta"])
        lines.append("#{}{} {}{}".format(row["rank"], mark,
                                         "🇰🇷 " if row["k_brand"] else "",
                                         row["title"][:56]))

    lines.append("")
    for item in data["findings"][:2]:
        lines.append("{} {}".format(item["icon"], item["title"]))

    lines.append("")
    lines.append("미국 아마존 한 채널의 순위입니다. 분석은 규칙 기반 데모고 "
                 "근거는 화면에 같이 적혀 있습니다.")

    return _reply("\n".join(lines),
                  chips=["스킨케어 순위는?", "요즘 뜨는 성분 뭐야"],
                  links=[link],
                  source="아마존 베스트셀러 · {} 수집".format(data["day"]))


_PROJECT_RE = re.compile(
    r"이 ?(건|프로젝트)|현재 프로젝트|어디까지|진행 ?(상황|률)|남은 (일|것)|"
    r"확인사항|다음 (할|에 할)|샘플 어(때|떻)|견적 (대안|비교)|이 건")


def _answer_project(text, project_id):
    """지금 보고 있는 프로젝트의 값으로 답한다.

    화면에서 프로젝트를 열고 물어봐야 답할 수 있다. 어느 건인지 모르면
    아무 건이나 골라 답하지 않는다.
    """
    import project_store

    data = project_store.hub(project_id)
    if data is None:
        return _reply("그 프로젝트를 찾지 못했습니다.",
                      links=[{"label": "프로젝트 목록", "endpoint": "projects"}])

    p = data["project"]
    info = data["progress"]
    link = {"label": "프로젝트 열기", "endpoint": "project_hub",
            "args": {"project_id": p["id"]}}

    if "확인사항" in text:
        open_q = [q for q in data["questions"] if q["status"] == "open"]
        if not open_q:
            return _reply("확인이 필요한 항목은 없습니다. 조건이 모두 채워졌습니다.",
                          links=[link], source=p["code"])
        lines = ["{} — 바이어에게 확인할 항목 {}건입니다.".format(p["title"], len(open_q))]
        for q in open_q[:6]:
            piece = "· {}".format(q["label"])
            if q["conflict"]:
                piece += " ⚠ 과거 요청과 다릅니다"
            lines.append(piece)
        lines.append("\n확인사항 화면에서 고르면 영문 회신 초안을 만들어 드립니다.")
        return _reply("\n".join(lines),
                      links=[{"label": "확인사항 정리하기", "endpoint": "project_questions",
                              "args": {"project_id": p["id"]}}],
                      source=p["code"])

    if "샘플" in text:
        if not data["samples"]:
            return _reply("아직 샘플이 없습니다.",
                          links=[{"label": "샘플 관리", "endpoint": "project_samples",
                                  "args": {"project_id": p["id"]}}], source=p["code"])
        lines = ["{} — 샘플 {}건입니다.".format(p["title"], len(data["samples"]))]
        for s in data["samples"]:
            piece = "· {}차 {} — {}".format(s["round"], s["code"],
                                            s["status_meta"]["label"])
            if s["notes"]:
                piece += " · 최근 피드백 {}".format(s["notes"][0]["verdict_meta"]["label"])
            lines.append(piece)
        return _reply("\n".join(lines),
                      links=[{"label": "샘플 관리", "endpoint": "project_samples",
                              "args": {"project_id": p["id"]}}], source=p["code"])

    if "견적" in text:
        if not data["quotes"]:
            return _reply("아직 견적 대안이 없습니다.",
                          links=[{"label": "견적 비교", "endpoint": "project_quotes",
                                  "args": {"project_id": p["id"]}}], source=p["code"])
        lines = ["{} — 견적 대안 {}개입니다.".format(p["title"], len(data["quotes"]))]
        for q in data["quotes"]:
            lines.append("· {} — {} {:.2f}{}{}".format(
                q["label"], q["currency"], q["unit_price"],
                " (최저)" if q.get("best") else "",
                " ★선택" if q["chosen"] else ""))
        lines.append("\n값 출처: " + ", ".join(
            sorted({q["basis_meta"]["label"] for q in data["quotes"]})))
        return _reply("\n".join(lines),
                      links=[{"label": "견적 비교", "endpoint": "project_quotes",
                              "args": {"project_id": p["id"]}}], source=p["code"])

    # 기본: 어디까지 왔나
    lines = ["{} ({})".format(p["title"], p["code"])]
    if p["customer_name"]:
        lines[0] += " — {}".format(p["customer_name"])
    lines.append("진행 {}/{}단계 ({}%)".format(info["done"], info["total"], info["percent"]))
    for stage in info["stages"]:
        lines.append("{} {} — {}".format("✅" if stage["done"] else "⬜",
                                         stage["label"], stage["note"]))

    todo = data["next"]["items"]
    if todo:
        lines.append("\n다음 할 일: " + todo[0]["label"])
    return _reply("\n".join(lines), links=[link], source=p["code"])


def answer(question, project_id=None):
    """질문 하나에 답 하나. (외부 API 를 부르지 않고 저장된 값만 읽는다)"""
    text = _norm(question)
    if not text:
        return _reply("무엇을 도와드릴까요?", chips=GREETING["chips"])

    # 프로젝트 화면에서 물으면 그 건의 값으로 답한다
    if project_id and _PROJECT_RE.search(text):
        try:
            return _answer_project(text, project_id)
        except Exception as exc:                      # noqa: BLE001
            return _reply("프로젝트 자료를 읽다가 막혔습니다. ({})".format(str(exc)[:60]))

    if re.search(r"^(안녕|하이|hi|hello|반가)", text):
        chips = list(GREETING["chips"])
        if project_id:
            chips = ["이 건 어디까지 왔어?", "확인사항 뭐 남았어?",
                     "샘플 어떻게 됐어?", "견적 대안 비교해줘"] + chips[:2]
        return _reply(GREETING["text"], chips=chips)

    if re.search(r"(뭐|무엇|뭘).*(할 수|가능|해줘|할수)|도움말|help|사용법", text):
        return _reply(
            "이런 것들을 찾아 드립니다.\n"
            "· 아마존 화장품 순위와 요약 (규칙 기반 분석 데모)\n"
        "· 국가별 수출입 실적 (UN Comtrade 실데이터)\n"
            "· 포장재 소재값 추세 (미국 BLS 생산자물가지수)\n"
            "· 성분별 국가 규제 (EU 는 실제 법령)\n"
            "· 고객사 담당자와 요청사항\n"
            "· 무역 용어 (인코텀즈·결제조건·서류)\n"
            "· \"○○은 어느 화면에서 하나요?\"\n\n"
            "저는 규칙 기반 도우미라, 적어 둔 것 밖의 질문은 답하지 못합니다.",
            chips=GREETING["chips"])

    # 용어 질문은 다른 것과 섞여도 먼저 잡는다 ("FOB 단가가 뭐야")
    for handler, pattern in ((_answer_rank, _RANK_RE),
                             (_answer_trade, _TRADE_RE),
                             (_answer_packaging, _PACK_RE),
                             (_answer_regulation, _REG_RE),
                             (_answer_customer, _CUST_RE),
                             (_answer_trend, _TREND_RE)):
        if pattern.search(text):
            glossary = _answer_glossary(text)
            if glossary and handler is not _answer_trade:
                return glossary
            try:
                return handler(text)
            except Exception as exc:                  # noqa: BLE001
                # 자료를 못 읽었다고 아무 말이나 지어내지 않는다
                return _reply(
                    "자료를 읽다가 막혔습니다. ({})\n"
                    "해당 화면에서 직접 확인해 주세요.".format(str(exc)[:80]))

    found = _answer_glossary(text)
    if found:
        return found

    found = _answer_screen(text)
    if found:
        return found

    return _reply(
        "제가 아직 모르는 질문입니다. 지어내서 답하지 않겠습니다.\n"
        "아래 중에 가까운 것이 있으면 눌러 보세요.",
        chips=GREETING["chips"])
