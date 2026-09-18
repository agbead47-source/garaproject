# -*- coding: utf-8 -*-
"""To-do Trade - 개발요청서 분석·변환 도구 (UI 가안)

3단계: 업로드 화면(6-1) + 로딩 연출까지.
"""

from datetime import date, timedelta

from flask import Flask, redirect, render_template, request, session, url_for

import dummy_data

app = Flask(__name__)
app.secret_key = "todo-trade-dev-only-secret"  # 가안용 임시 키

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


@app.route("/analyze", methods=["POST"])
def analyze():
    """업로드 화면의 선택값만 세션에 담고 분석 결과로 넘긴다.

    (파일 내용은 서버에서 사용하지 않는다.)
    """
    targets = request.form.getlist("targets")
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
    )


@app.route("/convert")
def convert():
    """3. 내부 전달 문서 변환."""
    options = session.get("options", {})
    analysis = dummy_data.analyze_document(options.get("file_name") or None)

    # 언어는 주소창(?lang=) 우선, 없으면 업로드 화면에서 고른 값
    lang = request.args.get("lang") or options.get("lang", "ko")
    tab = request.args.get("tab", "lab")

    return render_template(
        "convert.html",
        page_title="내부 전달 문서 변환",
        active_menu="analyze",
        active_step=3,
        options=options,
        analysis=analysis,
        languages=dummy_data.get_languages(),
        lang=lang,
        tab=tab,
        lab_doc=dummy_data.convert_for_lab(analysis, lang),
        factory_doc=dummy_data.convert_for_factory(analysis, lang),
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


@app.route("/regulation")
def regulation():
    """5. 국가별 규제 검색. (UI 가안 - 더미 규제 데이터 조회)"""
    country = request.args.get("country", "all")
    keyword = request.args.get("q", "")
    status = request.args.get("status", "all")

    rows = dummy_data.search_regulations(country, keyword, status)

    return render_template(
        "regulation.html",
        page_title="국가별 규제 검색",
        active_menu="regulation",
        rows=rows,
        countries=dummy_data.get_reg_countries(),
        status_meta=dummy_data.REG_STATUS_META,
        selected={"country": country, "q": keyword, "status": status},
        country_detail=dummy_data.get_reg_country(country),
        counts={
            "total": len(rows),
            "warn": sum(1 for r in rows if r["status"] == "warn"),
            "ban": sum(1 for r in rows if r["status"] == "ban"),
        },
    )


@app.route("/trends")
def trends():
    """6. 오늘의 트렌드. (UI 가안 - 더미 집계 데이터)"""
    category = request.args.get("category", "all")
    return render_template(
        "trends.html",
        page_title="오늘의 트렌드",
        active_menu="trends",
        data=dummy_data.get_trends(category),
        categories=dummy_data.TREND_CATEGORIES,
        selected_category=category,
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
