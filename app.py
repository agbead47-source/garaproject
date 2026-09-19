# -*- coding: utf-8 -*-
"""To-do Trade - 개발요청서 분석·변환 도구 (UI 가안)

3단계: 업로드 화면(6-1) + 로딩 연출까지.
"""

import os
import uuid
from datetime import date, timedelta

from flask import (Flask, jsonify, redirect, render_template, request,
                   send_file, session, url_for)

import chat_bot
import contact_store
import customer_excel
import customer_store
import doc_edit_store
import dummy_data
import mail_ai
import packaging_store
import regnews_store
import trade_store
import trend_store

app = Flask(__name__)
app.secret_key = "todo-trade-dev-only-secret"  # 가안용 임시 키

# 신규 바이어 발굴 모듈 (SQLite + pandas 사용. 기존 화면의 범위와 다름)
from prospecting.routes import bp as prospecting_bp  # noqa: E402
app.register_blueprint(prospecting_bp)

# 일정관리 모듈 (SQLite 사용. 날짜가 실제로 저장된다)
from schedule_routes import bp as schedule_bp  # noqa: E402
app.register_blueprint(schedule_bp)

# 고객사 담당자 저장소 (SQLite 사용. 화면에서 넣은 담당자가 실제로 남는다)
contact_store.init_db()
contact_store.seed_from_profiles(dummy_data.get_customer_profiles())

# 엑셀로 올린 고객사 저장소 (더미 카드에 없는 회사가 여기 담긴다)
customer_store.init_db()

# 포장재 가격 동향 (SQLite. 화면은 받아 둔 값만 읽는다)
packaging_store.init_db()

# 올린 엑셀을 잠시 두는 자리. 미리보기 -> 확인 사이에만 쓴다
IMPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "data", "imports")
# 명단 파일이 5MB 를 넘는 일은 없다
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

# 전달 문서에서 고친 값 저장소 (SQLite. 새로고침해도 수정이 남는다)
doc_edit_store.init_db()

# 로그인하지 않았을 때 쓰는 기본 사용자명 (가안용)
DEFAULT_USER = "해외영업팀 홍길동"

# 로그인 없이 열 수 있는 엔드포인트
PUBLIC_ENDPOINTS = {"login", "static"}

# 표 한 쪽에 몇 줄씩 보여 줄지
PAGE_SIZE = 20


def paginate(rows, page, size=PAGE_SIZE, window=2):
    """표를 끊어 준다. (그 쪽 행, 페이지 바에 필요한 값)

    행이 100개면 화면을 묶음으로 나눠도 표는 그대로 길다. 표는 끊어야 한다.
    합계·건수는 쪽이 아니라 **걸러낸 전체**를 기준으로 세야 한다.
    """
    total = len(rows)
    pages = max((total + size - 1) // size, 1)
    page = min(max(page or 1, 1), pages)
    start = (page - 1) * size

    # 1 … 4 5 [6] 7 8 … 20  - 양 끝과 현재 쪽 주변만
    numbers, last = [], 0
    for n in range(1, pages + 1):
        if n == 1 or n == pages or abs(n - page) <= window:
            if last and n - last > 1:
                numbers.append(None)          # 사이가 비면 … 로 접는다
            numbers.append(n)
            last = n

    return rows[start:start + size], {
        "page": page,
        "pages": pages,
        "total": total,
        "size": size,
        "start": start + 1 if total else 0,
        "end": min(start + size, total),
        "numbers": numbers,
        "has_prev": page > 1,
        "has_next": page < pages,
    }


# 오늘의 트렌드 화면의 묶음 (한 번에 하나씩 본다)
TREND_VIEWS = ("ingredient", "trade", "sns")

# 처리 이력 기간 필터 (value: 조회 일수)
PERIODS = [
    {"value": "all", "label": "전체 기간"},
    {"value": "7", "label": "최근 7일"},
    {"value": "30", "label": "최근 30일"},
    {"value": "90", "label": "최근 90일"},
]


@app.context_processor
def inject_globals():
    """모든 템플릿에서 공통으로 쓰는 값."""
    return {
        "current_user": session.get("user", DEFAULT_USER),
        # 무역 도우미 (모든 화면 우측 하단)
        "bot_name": chat_bot.BOT_NAME,
        "bot_kind": chat_bot.BOT_KIND,
        "bot_greeting": chat_bot.GREETING,
        # 담당자 등록 등 저장 결과 안내 (한 번 보여주고 지운다)
        "flash_msg": session.pop("contact_msg", None),
    }


@app.before_request
def require_login():
    """로그인하지 않으면 로그인 화면으로 보낸다. (가안: 값 검증은 하지 않음)"""
    if request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if "user" not in session:
        return redirect(url_for("login"))
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    """(선택) 가짜 로그인 - 아무 값이나 넣으면 통과한다."""
    if request.method == "POST":
        user_id = request.form.get("user_id", "").strip()
        session["user"] = "해외영업팀 {}".format(user_id) if user_id else DEFAULT_USER
        return redirect(url_for("upload"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("options", None)
    return redirect(url_for("login"))


@app.route("/")
def upload():
    """1. 문서 업로드."""
    return render_template(
        "upload.html",
        page_title="개발요청서 분석",
        active_menu="analyze",
        active_step=1,
        customers=dummy_data.get_customers(),
        languages=dummy_data.get_languages(),
    )


@app.route("/compose", methods=["GET", "POST"])
def compose():
    """1-B. 개발요청서 직접 작성.

    고객사 요청이 늘 파일로 오는 건 아니라서(메일·전화·미팅),
    해외영업 담당자가 사내 양식에 직접 적어 연구소·공장으로 넘기는 경로.
    """
    if request.method == "POST":
        form = {key: request.form.get(key, "")
                for section in dummy_data.COMPOSE_SECTIONS
                for key in [f["key"] for f in section["fields"]]}

        names = request.form.getlist("ing_name")
        rows = [
            {
                "name": names[i],
                "inci": request.form.getlist("ing_inci")[i],
                "amount": request.form.getlist("ing_amount")[i],
                "role": request.form.getlist("ing_role")[i],
            }
            for i in range(len(names))
        ]

        built = dummy_data.build_compose_result(form, rows)
        session["composed"] = built["overrides"]
        session["options"] = {
            "customer": built["overrides"].get("_requester", ""),
            "origin": built["overrides"].get("_origin", ""),
            "targets": request.form.getlist("targets") or ["연구소", "공장"],
            "lang": request.form.get("lang", "ko"),
            "file_name": "{} (직접 작성)".format(form.get("product_name") or "개발요청서"),
            "is_sample": False,
            "composed": True,
        }
        return redirect(url_for("convert"))

    # 다른 화면(일정관리·신규 바이어 발굴)에서 넘어온 값
    handoff = {
        "product": request.args.get("product", ""),
        "account": request.args.get("account", ""),
        "country": request.args.get("country", ""),
        "kind": request.args.get("kind", ""),
        "src": request.args.get("src", ""),
    }
    handoff = handoff if any(handoff.values()) else None

    ingredient = trend_store.get_ingredient(request.args.get("ingredient", ""))
    trend_row = None
    if ingredient:
        live = trend_store.get_ingredient_trends(auto_refresh=False)
        trend_row = next((r for r in live["rows"] if r["key"] == ingredient["key"]), None)

    return render_template(
        "compose.html",
        page_title="개발요청서 직접 작성",
        active_menu="analyze",
        active_step=1,
        d=dummy_data.get_compose_form(ingredient, trend_row, handoff),
        languages=dummy_data.get_languages(),
        reg_status_meta=dummy_data.REG_STATUS_META,
        reg_live=dummy_data.get_reg_source(),
    )


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """무역 도우미. 규칙 기반이고, 답은 이 프로젝트가 들고 있는 값에서만 꺼낸다.

    TODO: 실제 연동 (LLM 대화)
    """
    payload = request.get_json(silent=True) or {}
    question = (payload.get("q") or "")[:300]

    reply = chat_bot.answer(question)

    # 링크는 서버에서 주소로 바꿔 준다 (화면이 엔드포인트 이름을 알 필요가 없다)
    links = []
    for link in reply["links"]:
        try:
            links.append({"label": link["label"],
                          "href": url_for(link["endpoint"], **link.get("args", {}))})
        except Exception:                              # noqa: BLE001
            continue

    return jsonify({
        "text": reply["text"],
        "chips": reply["chips"],
        "links": links,
        "source": reply["source"],
        "bot": chat_bot.BOT_NAME,
    })


@app.route("/api/judge", methods=["POST"])
def api_judge():
    """작성 중인 성분에 EU 규제 판정을 붙여 돌려준다. (화면에서 실시간 호출)"""
    payload = request.get_json(silent=True) or {}
    rows = payload.get("ingredients") or []
    judged = dummy_data.judge_ingredients(rows)
    return jsonify({
        "ingredients": judged,
        "live": dummy_data.reg_store.is_available(),
        "flagged": sum(1 for r in judged if r["status"] in ("warn", "ban")),
    })


@app.route("/api/translate", methods=["POST"])
def api_translate():
    """메일 본문 번역. (MyMemory Translation API - Open API, 키 불필요)"""
    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    if not text:
        return jsonify({"text": "", "segments": [], "failed": 0, "cached": 0,
                        "provider": mail_ai.TRANSLATE_SOURCE["name"],
                        "source_lang": "", "target_lang": ""})

    source = payload.get("source") or mail_ai.detect_language(text)
    target = payload.get("target") or ("en" if source == "ko" else "ko")
    return jsonify(mail_ai.translate(text, source, target))


@app.route("/api/summarize", methods=["POST"])
def api_summarize():
    """메일 본문 요약 + 항목 추출 + 성분 EU 규제 대조. (외부 전송 없이 자체 처리)"""
    payload = request.get_json(silent=True) or {}
    return jsonify(mail_ai.summarize(payload.get("text") or ""))


@app.route("/analyze", methods=["POST"])
def analyze():
    """업로드 화면의 선택값만 세션에 담고 분석 결과로 넘긴다.

    (파일 내용은 서버에서 사용하지 않는다.)
    """
    targets = request.form.getlist("targets")
    session.pop("composed", None)   # 파일 업로드 경로에서는 직접 작성분을 쓰지 않는다
    session["options"] = {
        "customer": request.form.get("customer", ""),
        "targets": targets or ["연구소", "공장"],
        "lang": request.form.get("lang", "ko"),
        "file_name": request.form.get("file_name", ""),
        "is_sample": request.form.get("is_sample") == "1",
    }
    return redirect(url_for("result"))


@app.route("/result")
def result():
    """2. 분석 결과."""
    options = session.get("options", {})
    analysis = dummy_data.analyze_document(options.get("file_name") or None)
    return render_template(
        "result.html",
        page_title="분석 결과",
        active_menu="analyze",
        active_step=2,
        options=options,
        analysis=analysis,
        status_meta=dummy_data.STATUS_META,
        reg_status_meta=dummy_data.REG_STATUS_META,
    )


@app.route("/convert")
def convert():
    """3. 내부 전달 문서 변환."""
    options = session.get("options", {})
    analysis = dummy_data.analyze_document(options.get("file_name") or None)

    # 언어는 주소창(?lang=) 우선, 없으면 업로드 화면에서 고른 값
    lang = request.args.get("lang") or options.get("lang", "ko")
    tab = request.args.get("tab", "lab")

    # 직접 작성한 요청서가 있으면 그 내용이 우선한다
    overrides = session.get("composed") if options.get("composed") else None

    # 일정관리로 넘길 값 (요청을 넘겼으면 다음은 일정이다)
    def _item(key, fallback=""):
        if overrides and overrides.get(key):
            return overrides[key]
        return next((i["value"] for i in analysis["items"] if i["key"] == key), fallback)

    handoff = {
        "product": _item("product_name", analysis["file_name"]),
        "account": options.get("customer") or analysis["customer"],
        "country": _item("target_country", analysis["customer_country"]),
    }

    # 영업이 화면에서 고친 값을 자동 변환 결과 위에 덮는다
    file_name = analysis["file_name"]

    def _edited(doc, kind):
        return doc_edit_store.apply_to(
            doc, doc_edit_store.doc_key(file_name, kind, doc["lang"]))

    lab_doc = _edited(dummy_data.convert_for_lab(analysis, lang, overrides), "lab")
    factory_doc = _edited(dummy_data.convert_for_factory(analysis, lang, overrides), "factory")
    sales_doc = _edited(dummy_data.sales_terms(analysis, lang, overrides), "sales")

    return render_template(
        "convert.html",
        handoff=handoff,
        page_title="내부 전달 문서 변환",
        active_menu="analyze",
        active_step=3,
        options=options,
        analysis=analysis,
        languages=dummy_data.get_languages(),
        lang=lang,
        tab=tab,
        composed=bool(overrides),
        lab_doc=lab_doc,
        factory_doc=factory_doc,
        sales_doc=sales_doc,
        edited_count=(lab_doc["edited_count"] + factory_doc["edited_count"]
                      + sales_doc["edited_count"]),
    )


@app.route("/api/doc-edit", methods=["POST"])
def api_doc_edit():
    """전달 문서에서 고친 값 한 칸을 저장한다. (빈 값이면 자동 변환 값으로 되돌림)"""
    payload = request.get_json(silent=True) or {}
    saved = doc_edit_store.save_edit(
        payload.get("doc"), payload.get("field"), payload.get("value"))

    if saved is None:
        return jsonify({"ok": False, "error": "저장할 수 없는 항목입니다."}), 400
    return jsonify({"ok": True, "value": saved, "edited": bool(saved)})


@app.route("/api/doc-edit/reset", methods=["POST"])
def api_doc_edit_reset():
    """문서에서 고친 값을 모두 지운다. 자동 변환 결과로 돌아간다."""
    payload = request.get_json(silent=True) or {}
    keys = payload.get("docs") or []
    if not isinstance(keys, list):
        return jsonify({"ok": False, "error": "잘못된 요청입니다."}), 400

    removed = doc_edit_store.reset_docs(keys[:12])
    return jsonify({"ok": True, "removed": removed})


@app.route("/history")
def history():
    """4. 처리 이력."""
    period = request.args.get("period", "all")
    customer = request.args.get("customer", "all")
    status = request.args.get("status", "all")

    rows = dummy_data.get_history()

    if period != "all":
        limit = date.today() - timedelta(days=int(period))
        rows = [r for r in rows if date.fromisoformat(r["date"]) >= limit]

    if customer != "all":
        rows = [r for r in rows if r["customer"] == customer]

    if status != "all":
        rows = [r for r in rows if r["status"] == status]

    return render_template(
        "history.html",
        page_title="처리 이력",
        active_menu="history",
        rows=rows,
        total=len(dummy_data.get_history()),
        customers=dummy_data.get_customers(),
        status_meta=dummy_data.HISTORY_STATUS_META,
        periods=PERIODS,
        selected={"period": period, "customer": customer, "status": status},
    )


@app.route("/regulation", methods=["GET", "POST"])
def regulation():
    """5. 국가별 규제 검색.

    성분표(샘플데이터) 파일을 끌어다 놓으면 성분을 읽어 국가별로 대조한다.
    (UI 가안 - 파일 내용은 서버에서 사용하지 않고 더미 판정 결과를 보여준다)
    """
    if request.method == "POST":
        session["reg_file"] = request.form.get("file_name", "")
        return redirect(
            url_for("regulation", ready="1", country=request.form.get("country", "all"))
        )

    # '지금 수집' - 규제기관 공지를 받아온다. (사이트 3곳 도는 데 10초 남짓)
    if request.args.get("collect") == "1":
        regnews_store.collect()
        return redirect(url_for("regulation"))

    # 파일을 올리기 전에는 업로드 화면만 보여준다
    if request.args.get("ready") != "1":
        session.pop("reg_file", None)
        countries = dummy_data.get_reg_countries()
        # 일정관리 등에서 판매국을 넘겨주면 국가를 미리 골라 둔다 (이름이 맞을 때만)
        hint = (request.args.get("country_hint") or "").strip()
        preset = next((c["code"] for c in countries
                       if hint and (hint == c["name"] or hint.startswith(c["name"]))), "all")
        return render_template(
            "regulation.html",
            page_title="국가별 규제 검색",
            active_menu="regulation",
            ready=False,
            countries=countries,
            preset_country=preset,
            reg_source=dummy_data.get_reg_source(),
            news=regnews_store.get_news(),
        )

    country = request.args.get("country", "all")
    keyword = request.args.get("q", "")
    status = request.args.get("status", "all")

    parsed = dummy_data.analyze_ingredient_file(session.get("reg_file") or None)
    rows = dummy_data.search_regulations(country, keyword, status)

    # 건수는 걸러낸 전체 기준, 표만 끊는다
    # (검색 조건을 바꾸면 폼에 page 가 없어 1쪽으로 돌아온다)
    page_rows, pager = paginate(rows, request.args.get("page", type=int))

    return render_template(
        "regulation.html",
        page_title="국가별 규제 검색",
        active_menu="regulation",
        ready=True,
        parsed=parsed,
        rows=page_rows,
        pager=pager,
        countries=dummy_data.get_reg_countries(),
        status_meta=dummy_data.REG_STATUS_META,
        reg_source=dummy_data.get_reg_source(),
        selected={"country": country, "q": keyword, "status": status},
        country_detail=dummy_data.get_reg_country(country),
        counts={
            "total": len(rows),
            "warn": sum(1 for r in rows if r["status"] == "warn"),
            "ban": sum(1 for r in rows if r["status"] == "ban"),
        },
    )


def _quote_customers():
    """견적서 만들기 창에서 고를 고객사 + 담당자.

    수신처를 손으로 타이핑하면 이름·철자가 매번 달라진다.
    고객사 관리에 등록된 담당자를 그대로 고를 수 있게 내려준다.
    """
    grouped = contact_store.contacts_by_customer()
    rows = []
    for profile in _all_profiles():
        contacts = [c for c in grouped.get(profile["id"], []) if c["is_active"]]
        rows.append({
            "id": profile["id"],
            "name": profile["name"],
            # 대표 담당자가 맨 앞이라 창에서 기본값으로 쓴다
            "contacts": [{"id": c["id"], "name": c["name"], "title": c["title"] or "",
                          "email": c["email"] or "", "role": c["role_meta"]["label"]}
                         for c in contacts],
        })
    return rows


@app.route("/pricing", methods=["GET", "POST"])
def pricing():
    """6. 영업단가 계산.

    구매팀 원가표를 올리면 인식해서 값을 채우고,
    선적 조건별 물류비·보험료 + 영업마진 + 환율로 판매 단가를 뽑는다.
    계산은 화면(JS)에서 실시간으로 한다. 서버는 기본값만 내려준다.
    """
    if request.method == "POST":
        session["cost_file"] = request.form.get("file_name", "")
        return redirect(url_for("pricing", loaded="1"))

    loaded = request.args.get("loaded") == "1"
    file_name = session.get("cost_file") if loaded else None

    return render_template(
        "pricing.html",
        page_title="영업단가 계산",
        active_menu="pricing",
        loaded=loaded,
        quote_terms=dummy_data.QUOTE_TERMS,
        quote_customers=_quote_customers(),
        d=dummy_data.get_pricing_defaults(file_name or None, {
            "customer": request.args.get("customer", ""),
            "product": request.args.get("product", ""),
        }),
    )


# 견적서 세션에 담을 값 (쿠키 세션이라 필요한 것만, 길이도 잘라서 넣는다)
QUOTE_FIELDS = {
    "customer": 120, "attn": 80, "attn_email": 120,
    "product": 160, "product_en": 160, "port": 60,
    "qty": 16, "incoterm": 8, "fx": 16, "price_usd": 16, "price_krw": 16,
    "target_usd": 16, "terms": 600, "remark": 400,
    "issued_by": 60, "issued_by_en": 60,
}


@app.route("/pricing/quote", methods=["GET", "POST"])
def pricing_quote():
    """6-1. 견적서.

    단가 계산 화면에서 뽑은 값을 그대로 받아 고객사로 나가는 견적서 모양으로
    보여준다. (계산은 화면에서 끝났으니 여기서는 문서로 옮겨 담기만 한다)
    문서 하단에는 회사 직인(static/seal.svg)이 찍힌다.

    문서는 두 벌이다.
      - 고객 발송용(customer) : 영문. 고객이 봐도 되는 값만
      - 사내 보관용(internal) : 국문 + 원화 환산·견적환율·조건별 단가
    화면에서 두 벌을 오갈 수 있게 값은 세션에 담고 GET 으로 넘긴다.
    """
    if request.method == "POST":
        session["quote"] = {
            key: (request.form.get(key) or "")[:limit]
            for key, limit in QUOTE_FIELDS.items()
        }
        return redirect(url_for("pricing_quote", view=request.form.get("view", "customer")))

    form = session.get("quote")
    if not form:
        # 계산 화면을 거치지 않고 주소로 바로 들어온 경우
        return redirect(url_for("pricing"))

    form = dict(form)
    if not form.get("issued_by"):
        form["issued_by"] = session.get("user", DEFAULT_USER)

    view = request.args.get("view", "customer")
    if view not in ("customer", "internal"):
        view = "customer"

    return render_template(
        "quote.html",
        page_title="견적서",
        active_menu="pricing",
        q=dummy_data.build_quote(form, view),
    )


@app.route("/trends")
def trends():
    """7. 오늘의 트렌드.

    성분 관심도는 Wikimedia Pageviews API 실데이터(키 불필요),
    키워드 랭킹·시장 소식은 아직 더미다.
    """
    category = request.args.get("category", "all")
    force = request.args.get("refresh") == "1"
    hs = request.args.get("hs", "all")
    trade_year = request.args.get("trade_year", type=int)

    # 한 화면에 다 쌓으면 끝없이 내려야 한다. 묶음 하나씩 본다.
    view = request.args.get("view", "ingredient")
    if view not in TREND_VIEWS:
        view = "ingredient"

    trade_page = request.args.get("trade_page", type=int)

    keep = {"view": view, "category": category, "hs": hs,
            "trade_year": trade_year}

    # 수출입 통계 수집 - 한 번에 6블록씩 받는다. (24블록이면 네 번)
    if request.args.get("collect") == "trade":
        result = trade_store.collect()
        info = trade_store.status()
        session["trade_msg"] = (
            "수출입 통계 {}/{}건 수집{}. 남은 {}건은 한 번 더 누르면 됩니다.".format(
                info["collected"], info["total"],
                " · 미러 보완 {}건".format(result["mirrored"]) if result["mirrored"] else "",
                result["remaining"])
            if result["remaining"] else
            "수출입 통계 {}건을 모두 받았습니다.".format(info["total"]))
        return redirect(url_for("trends", **keep))

    # 보고 있지 않은 묶음 때문에 외부 API를 두드리지는 않는다
    live = trend_store.get_ingredient_trends(
        auto_refresh=(view == "ingredient"), force=force)
    if force:
        return redirect(url_for("trends", **keep))

    # 204개국을 상위 25곳만 잘라 보여 주면 정작 찾는 시장이 안 보인다. 끊어서 전부 준다.
    trade = trade_store.get_trade(hs=hs, year=trade_year, top=0)
    trade_rows, trade_pager = paginate(trade["rows"], trade_page)

    return render_template(
        "trends.html",
        page_title="오늘의 트렌드",
        active_menu="trends",
        data=dummy_data.get_trends(category),
        categories=dummy_data.TREND_CATEGORIES,
        selected_category=category,
        view=view,
        trend_live=live,
        trade=trade,
        trade_rows=trade_rows,
        trade_pager=trade_pager,
        trade_msg=session.pop("trade_msg", None),
    )


@app.route("/packaging")
def packaging():
    """포장재 가격 동향.

    화면을 열 때마다 외부 API 를 부르지 않는다. 서버가 주기대로 받아 둔 값을
    모두가 같이 본다. 수집은 아래 `?collect=1` 이나 `python packaging_store.py`.
    """
    parts = [p for p in request.args.getlist("part")
             if p in packaging_store.PART_MAP]
    preset = request.args.get("preset", "")
    keep = {"preset": preset} if preset and not parts else {}

    if request.args.get("collect") == "1":
        result = packaging_store.collect(force=request.args.get("force") == "1")
        session["packaging_msg"] = _collect_message(result)
        return redirect(url_for("packaging", part=parts, **keep))

    return render_template(
        "packaging.html",
        page_title="포장재 가격 동향",
        active_menu="packaging",
        board=packaging_store.board(parts=parts, preset=preset),
        status_meta=packaging_store.STATUS_META,
        collect_msg=session.pop("packaging_msg", None),
    )


def _collect_message(result):
    """수집 결과를 한 줄로. (키 값은 절대 넣지 않는다)"""
    parts = []
    for name, key in (("BLS 지수", "bls"), ("알루미늄", "metals")):
        item = result.get(key, {})
        if item.get("skipped"):
            parts.append("{} 건너뜀({})".format(name, item.get("reason", "")))
        elif item.get("error"):
            parts.append("{} 실패".format(name))
        else:
            parts.append("{} 새 값 {}개 · 수정 {}개".format(
                name, item.get("new", 0), item.get("revised", 0)))
    return ("ok", " / ".join(parts))


@app.route("/sample", methods=["GET", "POST"])
def sample():
    """7. AI 샘플 미리보기. (UI 가안 - 업로드하면 더미 샘플 후보를 보여준다)"""
    if request.method == "POST":
        session["sample_file"] = request.form.get("file_name", "")
        return redirect(url_for("sample", ready="1"))

    ready = request.args.get("ready") == "1"
    if not ready:
        return render_template(
            "sample.html",
            page_title="AI 샘플 미리보기",
            active_menu="sample",
            ready=False,
        )

    result = dummy_data.generate_samples(session.get("sample_file") or None)
    picked = dummy_data.get_sample_candidate(request.args.get("pick", "A"))

    return render_template(
        "sample.html",
        page_title="AI 샘플 미리보기",
        active_menu="sample",
        ready=True,
        result=result,
        picked=picked,
        risk_meta=dummy_data.SAMPLE_RISK_META,
    )


def _with_contacts(profile, contacts=None):
    """고객사 프로필에 담당자 목록을 붙인다. (담당자만 DB, 나머지는 더미)"""
    rows = contacts if contacts is not None else contact_store.list_contacts(profile["id"])
    profile["contacts"] = rows
    profile["primary_contact"] = contact_store.primary_of(rows)
    profile["active_contacts"] = [r for r in rows if r["is_active"]]
    return profile


def _all_profiles(keyword="", grade="all"):
    """고객사 카드 = 더미 카드 + 엑셀로 올린 회사."""
    return (dummy_data.get_customer_profiles(keyword, grade)
            + customer_store.profiles(keyword, grade))


def _find_profile(customer_id):
    """고객사 한 곳. 더미에 없으면 엑셀로 올린 쪽에서 찾는다."""
    return (dummy_data.get_customer_profile(customer_id)
            or customer_store.profile(customer_id))


@app.route("/customers")
def customers():
    """8. 고객사 관리 - 목록. (UI 가안. 담당자는 실제 저장값)"""
    keyword = request.args.get("q", "")
    grade = request.args.get("grade", "all")

    grouped = contact_store.contacts_by_customer()
    rows = [_with_contacts(row, grouped.get(row["id"], []))
            for row in _all_profiles("", grade)]

    # 회사명·국가뿐 아니라 담당자 이름·이메일로도 찾을 수 있어야 한다
    needle = (keyword or "").strip().lower()
    if needle:
        rows = [row for row in rows if needle in " ".join(
            [row["name"], row["country"]] +
            [" ".join([c["name"], c["email"] or "", c["title"] or ""])
             for c in row["contacts"]]).lower()]

    summary = dummy_data.get_customer_summary()
    summary["contacts"] = sum(len(v) for v in grouped.values())
    # 엑셀로 올린 회사도 고객사다. 요약 숫자에 같이 센다
    imported = customer_store.profiles()
    summary["total"] += len(imported)
    summary["vip"] += sum(1 for row in imported if row["grade"] == "vip")
    summary["imported"] = len(imported)

    return render_template(
        "customers.html",
        page_title="고객사 관리",
        active_menu="customers",
        rows=rows,
        summary=summary,
        grade_meta=dummy_data.CUSTOMER_GRADE_META,
        selected={"q": keyword, "grade": grade},
    )


@app.route("/customers/<customer_id>")
def customer_detail(customer_id):
    """8-1. 고객사 관리 - 상세. (UI 가안. 담당자는 실제 저장값)"""
    profile = _find_profile(customer_id)
    if profile is None:
        return redirect(url_for("customers"))

    return render_template(
        "customer_detail.html",
        page_title=profile["name"],
        active_menu="customers",
        c=_with_contacts(profile),
        tab=request.args.get("tab", "requests"),
        grade_meta=dummy_data.CUSTOMER_GRADE_META,
        request_meta=dummy_data.REQUEST_TYPE_META,
        priority_meta=dummy_data.PRIORITY_META,
        status_meta=dummy_data.HISTORY_STATUS_META,
        contact_roles=contact_store.ROLES,
        edit_contact=request.args.get("edit", type=int),
    )


# ---------------------------------------------------------------------------
# 고객사 엑셀 내보내기 / 가져오기
# ---------------------------------------------------------------------------

def _xlsx(buf, name):
    return send_file(buf, as_attachment=True, download_name=name,
                     mimetype="application/vnd.openxmlformats-officedocument."
                              "spreadsheetml.sheet")


def _export_options(args):
    """내보내기 조건을 주소에서 읽는다.

    두 가지를 따로 고른다.
      누구를 받을지 - 직무(역할), 이메일 보유, 대표 여부, 국가, 등급
      어떤 값을 받을지 - 엑셀 열
    조합(preset)을 고르면 둘 다 한 번에 정해진다.
    """
    preset = customer_excel.PRESET_MAP.get(args.get("preset", ""))
    filters = (preset or {}).get("filters", {})

    def pick(key, default=""):
        """주소에 값이 있으면 그것, 없으면 조합이 정해 둔 값."""
        return args.get(key) if key in args else filters.get(key, default)

    cols = args.getlist("cols") or (preset["cols"] if preset else [])
    columns = customer_excel.pick_columns(cols)
    roles = args.getlist("role") or list(filters.get("role", []))

    return {
        "columns": columns,
        "keys": set(c["key"] for c in columns),
        # --- 누구를
        "roles": set(r for r in roles if r in contact_store.ROLE_MAP),
        "has_email": pick("email", "0") == "1",
        "has_phone": pick("phone", "0") == "1",
        "primary_only": pick("primary", "0") == "1",
        # 그만둔 담당자(비활성)를 뺄지
        "active_only": pick("active", "0") == "1",
        "language": pick("lang", ""),
        # --- 어느 회사를
        "grade": pick("grade", "all"),
        "country": pick("country", ""),
        "q": pick("q", ""),
        # 담당자가 아직 없는 회사도 넣을지
        "include_empty": pick("empty", "1") != "0",
        "guide": pick("guide", "1") != "0",
        "preset": args.get("preset", ""),
    }


def _export_rows(opt):
    grouped = contact_store.contacts_by_customer()
    rows = customer_excel.export_rows(
        _all_profiles(opt["q"], opt["grade"]), grouped, opt)

    # 담당자 열을 하나도 안 골랐으면 회사 명단이다. 같은 회사를 여러 줄 내지 않는다
    if not (opt["keys"] & customer_excel.CONTACT_KEYS):
        rows = customer_excel.collapse_companies(rows)
    return rows


def _export_facets():
    """고를 수 있는 값과 각 직무에 몇 명이 있는지. (체크박스 옆에 숫자를 띄운다)"""
    grouped = contact_store.contacts_by_customer()
    everyone = [c for rows in grouped.values() for c in rows]

    roles = []
    for role in contact_store.ROLES:
        roles.append(dict(role, count=sum(1 for c in everyone
                                          if c["role"] == role["value"])))

    countries = sorted({p.get("country", "") for p in _all_profiles()
                        if p.get("country")})
    languages = sorted({(c["language"] or "").strip() for c in everyone
                        if (c["language"] or "").strip()})
    return {
        "roles": roles,
        "countries": countries,
        "languages": languages,
        "with_email": sum(1 for c in everyone if (c["email"] or "").strip()),
        "total": len(everyone),
    }


@app.route("/customers/export")
def customers_export():
    """고객사·담당자를 엑셀로 내려받는다. 어떤 값을 받을지 고를 수 있다.

    아무 조건 없이 부르면 전부 받는다. (목록 화면의 '엑셀로 받기' 버튼)
    """
    opt = _export_options(request.args)
    rows = _export_rows(opt)

    # 파일명에 무엇을 뽑은 건지 남긴다. 받은 사람이 파일 이름만 보고 알 수 있게
    if not (opt["keys"] & customer_excel.CONTACT_KEYS):
        label = "고객사"
    elif len(opt["roles"]) == 1:
        role = contact_store.ROLE_MAP[next(iter(opt["roles"]))]["label"]
        label = "고객사_" + role.replace("·", "")
    elif opt["primary_only"]:
        label = "고객사_대표담당자"
    else:
        label = "고객사_담당자"
    name = "{}_{}.xlsx".format(label, date.today().strftime("%Y%m%d"))
    return _xlsx(customer_excel.build_workbook(
        rows, with_guide=opt["guide"], columns=opt["columns"]), name)


@app.route("/customers/template")
def customers_template():
    """빈 양식. 예시 두 줄과 작성 안내가 들어 있다."""
    return _xlsx(customer_excel.build_template(), "고객사_담당자_양식.xlsx")


def _pending_import():
    """미리보기 중인 파일 경로. 없으면 None."""
    token = session.get("import_file")
    if not token:
        return None
    path = os.path.join(IMPORT_DIR, token)
    return path if os.path.exists(path) else None


def _drop_import():
    path = _pending_import()
    if path:
        try:
            os.remove(path)
        except OSError:
            pass
    session.pop("import_file", None)


def _plan_import(path):
    """올린 파일을 읽어 한 줄씩 판정한다. (판정, 오류 메시지)"""
    with open(path, "rb") as f:
        rows, error = customer_excel.read_rows(f)
    if error:
        return [], error

    grouped = contact_store.contacts_by_customer()
    return customer_excel.plan(rows, _all_profiles(), grouped), ""


@app.route("/customers/import", methods=["GET", "POST"])
def customers_import():
    """엑셀 명단을 올려 고객사·담당자를 한 번에 등록한다.

    올리자마자 저장하지 않는다. 한 줄씩 무엇이 될지 보여 주고, 확인을 눌러야
    들어간다. 명단은 잘못 들어가면 되돌리기가 번거롭다.
    """
    if request.method == "POST":
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            session["contact_msg"] = ("error", "엑셀 파일을 선택해 주세요.")
            return redirect(url_for("customers_import"))

        if not upload.filename.lower().endswith((".xlsx", ".xlsm")):
            session["contact_msg"] = (
                "error", "xlsx 파일만 읽을 수 있습니다. (xls 는 저장할 때 xlsx 로 바꿔 주세요)")
            return redirect(url_for("customers_import"))

        _drop_import()
        os.makedirs(IMPORT_DIR, exist_ok=True)
        token = "{}.xlsx".format(uuid.uuid4().hex)
        upload.save(os.path.join(IMPORT_DIR, token))
        session["import_file"] = token
        session["import_name"] = upload.filename[:120]
        return redirect(url_for("customers_import"))

    path = _pending_import()
    planned, error = _plan_import(path) if path else ([], "")
    if error:
        _drop_import()
        session["contact_msg"] = ("error", error)
        return redirect(url_for("customers_import"))

    # 내보내기 칸에 지금 무엇이 몇 줄 받아지는지 같이 보여 준다
    opt = _export_options(request.args)
    preview = _export_rows(opt)

    return render_template(
        "customer_import.html",
        page_title="고객사 엑셀 내보내기·가져오기",
        active_menu="customers",
        columns=customer_excel.COLUMNS,
        contact_keys=customer_excel.CONTACT_KEYS,
        presets=customer_excel.PRESETS,
        planned=planned,
        counts=customer_excel.summarize(planned) if planned else None,
        plan_meta=customer_excel.PLAN_META,
        file_name=session.get("import_name", "") if path else "",
        facets=_export_facets(),
        export={
            # 'keys' 라고 쓰면 템플릿에서 dict.keys 메서드로 잡힌다
            "cols": opt["keys"],
            "roles": opt["roles"],
            "has_email": opt["has_email"],
            "has_phone": opt["has_phone"],
            "primary_only": opt["primary_only"],
            "active_only": opt["active_only"],
            "language": opt["language"],
            "grade": opt["grade"],
            "country": opt["country"],
            "q": opt["q"],
            "include_empty": opt["include_empty"],
            "guide": opt["guide"],
            "preset": opt["preset"],
            "rows": len(preview),
            "companies": len({r["customer_id"] for r in preview}),
        },
        grade_meta=dummy_data.CUSTOMER_GRADE_META,
    )


@app.route("/customers/import/confirm", methods=["POST"])
def customers_import_confirm():
    """미리보기에서 확인을 누르면 그때 저장한다."""
    path = _pending_import()
    if path is None:
        session["contact_msg"] = ("error", "올린 파일이 없습니다. 다시 올려 주세요.")
        return redirect(url_for("customers_import"))

    if request.form.get("action") == "cancel":
        _drop_import()
        session["contact_msg"] = ("ok", "가져오기를 취소했습니다.")
        return redirect(url_for("customers_import"))

    # 미리보기 이후에 화면에서 담당자를 고쳤을 수 있으니 다시 판정하고 저장한다
    planned, error = _plan_import(path)
    if error:
        _drop_import()
        session["contact_msg"] = ("error", error)
        return redirect(url_for("customers_import"))

    result = customer_excel.apply(planned)
    _drop_import()

    parts = []
    if result["companies"]:
        parts.append("고객사 {}곳".format(result["companies"]))
    if result["added"]:
        parts.append("담당자 {}명 추가".format(result["added"]))
    if result["updated"]:
        parts.append("담당자 {}명 갱신".format(result["updated"]))
    if result["skipped"]:
        parts.append("오류 {}줄 건너뜀".format(result["skipped"]))

    session["contact_msg"] = ("ok", "엑셀에서 " + ", ".join(parts or ["변경 없음"])
                              + " 했습니다.")
    return redirect(url_for("customers"))


@app.route("/customers/<customer_id>/contacts", methods=["POST"])
def customer_contacts(customer_id):
    """8-2. 고객사 담당자 등록·수정·삭제.

    고객사 한 곳에 담당자는 보통 여러 명이다. 구매·품질·물류 담당이 따로 있고
    메일을 누구에게 보내느냐로 회신 속도가 갈린다. 여기서 넣은 값은
    더미가 아니라 SQLite(data/contacts.db)에 실제로 저장된다.
    """
    if _find_profile(customer_id) is None:
        return redirect(url_for("customers"))

    back = url_for("customer_detail", customer_id=customer_id, tab="contacts")
    action = request.form.get("action", "add")
    contact_id = request.form.get("contact_id", type=int)

    # 남의 고객사 담당자를 주소만 바꿔 건드리지 못하게 한다
    if contact_id is not None:
        target = contact_store.get_contact(contact_id)
        if target is None or target["customer_id"] != customer_id:
            session["contact_msg"] = ("error", "담당자를 찾지 못했습니다.")
            return redirect(back)

    if action == "add" or action == "update":
        errors = contact_store.validate(request.form)
        if errors:
            session["contact_msg"] = ("error", " ".join(errors))
            return redirect(back if action == "add" else
                            url_for("customer_detail", customer_id=customer_id,
                                    tab="contacts", edit=contact_id))

        data = request.form.to_dict()
        data["is_primary"] = request.form.get("is_primary") == "1"

        if action == "add":
            contact_store.add_contact(customer_id, data)
            session["contact_msg"] = ("ok", "담당자를 추가했습니다.")
        else:
            contact_store.update_contact(contact_id, data)
            session["contact_msg"] = ("ok", "담당자 정보를 수정했습니다.")

    elif action == "primary":
        ok = contact_store.set_primary(contact_id)
        session["contact_msg"] = (("ok", "대표 담당자를 바꿨습니다.") if ok else
                                  ("error", "비활성 담당자는 대표로 지정할 수 없습니다."))

    elif action in ("deactivate", "activate"):
        contact_store.set_active(contact_id, action == "activate")
        session["contact_msg"] = ("ok", "담당자를 {}했습니다.".format(
            "복구" if action == "activate" else "비활성 처리"))

    elif action == "delete":
        contact_store.delete_contact(contact_id)
        session["contact_msg"] = ("ok", "담당자를 삭제했습니다.")

    return redirect(back)


if __name__ == "__main__":
    app.run(debug=True)
