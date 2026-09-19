# -*- coding: utf-8 -*-
"""To-do Trade - 개발요청서 분석·변환 도구 (UI 가안)

3단계: 업로드 화면(6-1) + 로딩 연출까지.
"""

from datetime import date, timedelta

from flask import (Flask, jsonify, redirect, render_template, request,
                   session, url_for)

import dummy_data
import mail_ai
import trend_store

app = Flask(__name__)
app.secret_key = "todo-trade-dev-only-secret"  # 가안용 임시 키

# 신규 바이어 발굴 모듈 (SQLite + pandas 사용. 기존 화면의 범위와 다름)
from prospecting.routes import bp as prospecting_bp  # noqa: E402
app.register_blueprint(prospecting_bp)

# 일정관리 모듈 (SQLite 사용. 날짜가 실제로 저장된다)
from schedule_routes import bp as schedule_bp  # noqa: E402
app.register_blueprint(schedule_bp)

# 로그인하지 않았을 때 쓰는 기본 사용자명 (가안용)
DEFAULT_USER = "해외영업팀 홍길동"

# 로그인 없이 열 수 있는 엔드포인트
PUBLIC_ENDPOINTS = {"login", "static"}

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
    return {"current_user": session.get("user", DEFAULT_USER)}


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
        lab_doc=dummy_data.convert_for_lab(analysis, lang, overrides),
        factory_doc=dummy_data.convert_for_factory(analysis, lang, overrides),
    )


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
        )

    country = request.args.get("country", "all")
    keyword = request.args.get("q", "")
    status = request.args.get("status", "all")

    parsed = dummy_data.analyze_ingredient_file(session.get("reg_file") or None)
    rows = dummy_data.search_regulations(country, keyword, status)

    return render_template(
        "regulation.html",
        page_title="국가별 규제 검색",
        active_menu="regulation",
        ready=True,
        parsed=parsed,
        rows=rows,
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
        d=dummy_data.get_pricing_defaults(file_name or None, {
            "customer": request.args.get("customer", ""),
            "product": request.args.get("product", ""),
        }),
    )


# 견적서 세션에 담을 값 (쿠키 세션이라 필요한 것만, 길이도 잘라서 넣는다)
QUOTE_FIELDS = {
    "customer": 120, "attn": 80, "product": 160, "product_en": 160, "port": 60,
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

    live = trend_store.get_ingredient_trends(force=force)
    if force:
        return redirect(url_for("trends", category=category))

    return render_template(
        "trends.html",
        page_title="오늘의 트렌드",
        active_menu="trends",
        data=dummy_data.get_trends(category),
        categories=dummy_data.TREND_CATEGORIES,
        selected_category=category,
        trend_live=live,
    )


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


@app.route("/customers")
def customers():
    """8. 고객사 관리 - 목록. (UI 가안)"""
    keyword = request.args.get("q", "")
    grade = request.args.get("grade", "all")

    return render_template(
        "customers.html",
        page_title="고객사 관리",
        active_menu="customers",
        rows=dummy_data.get_customer_profiles(keyword, grade),
        summary=dummy_data.get_customer_summary(),
        grade_meta=dummy_data.CUSTOMER_GRADE_META,
        selected={"q": keyword, "grade": grade},
    )


@app.route("/customers/<customer_id>")
def customer_detail(customer_id):
    """8-1. 고객사 관리 - 상세. (UI 가안)"""
    profile = dummy_data.get_customer_profile(customer_id)
    if profile is None:
        return redirect(url_for("customers"))

    return render_template(
        "customer_detail.html",
        page_title=profile["name"],
        active_menu="customers",
        c=profile,
        tab=request.args.get("tab", "requests"),
        grade_meta=dummy_data.CUSTOMER_GRADE_META,
        request_meta=dummy_data.REQUEST_TYPE_META,
        priority_meta=dummy_data.PRIORITY_META,
        status_meta=dummy_data.HISTORY_STATUS_META,
    )


if __name__ == "__main__":
    app.run(debug=True)
