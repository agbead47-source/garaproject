# -*- coding: utf-8 -*-
"""To-do Trade - 개발요청서 분석·변환 도구 (UI 가안)

3단계: 업로드 화면(6-1) + 로딩 연출까지.
"""

import os
import re
import uuid
from datetime import date, timedelta

from flask import (Flask, jsonify, redirect, render_template, request,
                   send_file, session, url_for)

import beauty_rank_store
import chat_bot
import company_store
import contact_log_store
import contact_store
import customer_excel
import customer_store
import doc_edit_store
import dummy_data
import fx_store
import mail_ai
import packaging_store
import project_store
import schedule_store
import regnews_store
import trade_store
import trend_store
import us_reg_store

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

# 고객사 연락 기록 (SQLite. 누구와 무슨 연락을 했는지 한 줄 메모)
contact_log_store.init_db()

# 자사 정보 (SQLite. 서류가 여기서 읽어 간다)
company_store.init_db()

# 포장재 가격 동향 (SQLite. 화면은 받아 둔 값만 읽는다)
packaging_store.init_db()

# 프로젝트 - 지금까지 만든 화면을 한 건으로 묶는 축 (SQLite)
project_store.init_db()

# 견적환율 (SQLite. 받아 둔 고시만 읽고, 조회는 담당자가 누를 때만 나간다)
fx_store._conn()

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
TREND_VIEWS = ("ingredient", "trade", "rank", "sns")

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
        # 무역 도우미 (모든 화면 우측 하단).
        #   프로젝트 화면이면 그 건에 맞는 추천 질문을 띄운다
        "bot_name": chat_bot.BOT_NAME,
        "bot_kind": chat_bot.BOT_KIND,
        "bot_greeting": chat_bot.greeting(
            (request.view_args or {}).get("project_id")
            or request.args.get("project", type=int)),
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
    # 화면이 프로젝트를 열어 두고 있으면 그 건의 값으로 답한다
    try:
        project_id = int(payload.get("project") or 0) or None
    except (TypeError, ValueError):
        project_id = None

    reply = chat_bot.answer(question, project_id=project_id)

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
    """3. 내부 전달 문서 변환.

    프로젝트에서 열면(`?project=`) 그 건의 고객사·제품으로 맞추고,
    문서를 만든 것으로 프로젝트 단계를 옮긴다.
    """
    project = None
    project_id = request.args.get("project", type=int)
    if project_id:
        project = project_store.get_project(project_id)

    options = dict(session.get("options", {}))
    if project:
        options["customer"] = project["customer_name"] or options.get("customer", "")
        if project["source_file"]:
            options["file_name"] = project["source_file"]
        project_store.update_project(project_id, {"stage": "handoff"})

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
        project=project,
        edited_count=(lab_doc["edited_count"] + factory_doc["edited_count"]
                      + sales_doc["edited_count"]),
    )


@app.route("/api/fx")
def api_fx():
    """견적환율 조회. (담당자가 '환율 불러오기'를 누를 때만 외부로 나간다)

    화면을 여는 것만으로는 부르지 않는다. 받아 둔 고시가 있으면 그것을 쓴다.
    """
    args = request.args
    return jsonify(fx_store.lookup(
        args.get("currency", "USD"),
        source=args.get("source", fx_store.DEFAULT_SOURCE),
        basis=args.get("basis", "latest"),
        day=args.get("day", ""),
        preset=args.get("preset", fx_store.DEFAULT_PRESET),
        start=args.get("start", ""),
        end=args.get("end", ""),
    ))


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

    # 미국 연방규정집(eCFR) 조문 받아오기. 화면을 열 때는 부르지 않는다
    if request.args.get("collect") == "us":
        out = us_reg_store.collect(force=True)
        session["contact_msg"] = (("ok" if out["ok"] else "error"), out["message"])
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
            us_source=dummy_data.get_us_reg_source(),
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
        us_source=dummy_data.get_us_reg_source(),
        selected={"country": country, "q": keyword, "status": status},
        country_detail=dummy_data.get_reg_country(country),
        counts={
            "total": len(rows),
            "warn": sum(1 for r in rows if r["status"] == "warn"),
            "ban": sum(1 for r in rows if r["status"] == "ban"),
        },
    )


def _project_handoff(args):
    """프로젝트에서 넘어온 값. 단가 화면이 그 건의 조건으로 열린다."""
    project_id = args.get("project", type=int)
    if not project_id:
        return None, None

    project = project_store.get_project(project_id)
    if project is None:
        return None, None

    fields = project_store.raw_fields(project_id)

    def _v(key):
        return (fields.get(key) or {}).get("value", "")

    return project, {
        "customer": project["customer_name"],
        "product": _v("product_name") or project["title"],
        "country": project["country"],
        "moq": _v("moq"),
        "currency": _v("currency"),
        "trade_terms": _v("trade_terms"),
        "target_price": _v("target_price"),
    }


def _quote_customers():
    """견적서 만들기 창에서 고를 고객사 + 담당자.

    수신처를 손으로 타이핑하면 이름·철자가 매번 달라진다.
    거래처 관리에 등록된 담당자를 그대로 고를 수 있게 내려준다.
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

    # 프로젝트에서 열면 그 건의 고객사·제품·수량·통화로 맞춘다
    project, handoff = _project_handoff(request.args)
    defaults = dummy_data.get_pricing_defaults(file_name or None, {
        "customer": (handoff or {}).get("customer") or request.args.get("customer", ""),
        "product": (handoff or {}).get("product") or request.args.get("product", ""),
    })

    if handoff:
        qty = re.sub(r"[^0-9]", "", handoff.get("moq") or "")
        if qty:
            defaults["cost_sheet"]["quantity"] = int(qty)
        code = (handoff.get("currency") or "").strip().upper()[:3]
        if code in dummy_data.CURRENCY_MAP:
            defaults["currency"] = code
            defaults["fx"] = dummy_data.CURRENCY_MAP[code]["fx"]
        term = (handoff.get("trade_terms") or "").upper()
        for row in dummy_data.INCOTERMS:
            if row["code"] in term:
                defaults["selected_incoterm"] = row["code"]
                break
        try:
            target = float(re.sub(r"[^0-9.]", "", handoff.get("target_price") or "") or 0)
            if target:
                defaults["target_price"] = target
        except ValueError:
            pass

    # 받아 둔 고시가 있으면 그 값으로 시작한다.
    #   화면을 여는 것만으로 외부 API 를 부르지는 않는다(allow_network=False).
    #   받아 둔 게 없으면 내장 기본값을 그대로 두고 "내장 기본값"이라고 적는다.
    fx = fx_store.lookup(defaults["currency"], allow_network=False)
    if fx["ok"] and fx["rate"]:
        defaults["fx"] = fx["rate"]
        defaults["fx_date"] = fx["day"]
    else:
        fx = dict(fx, state="builtin",
                  state_meta=fx_store.state_meta("builtin"),
                  rate=defaults["fx"], day=defaults["fx_date"],
                  label="화면 기본값",
                  detail=["아직 받아 둔 고시가 없습니다. "
                          "'환율 불러오기'를 누르면 조회합니다."])

    return render_template(
        "pricing.html",
        page_title="영업단가 계산",
        active_menu="pricing",
        loaded=loaded,
        fx=fx,
        fx_opt=fx_store.options(),
        quote_terms=dummy_data.QUOTE_TERMS,
        quote_customers=_quote_customers(),
        project=project,
        d=defaults,
    )


# 견적서 세션에 담을 값 (쿠키 세션이라 필요한 것만, 길이도 잘라서 넣는다)
QUOTE_FIELDS = {
    "customer": 120, "attn": 80, "attn_email": 120,
    "product": 160, "product_en": 160, "port": 60,
    "qty": 16, "incoterm": 8, "fx": 16, "fx_basis": 80, "currency": 4,
    "price_unit": 16, "price_krw": 16,
    "target_price": 16, "terms": 600, "remark": 400,
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
    rank_cat = request.args.get("cat", "beauty")
    rank_day = request.args.get("day", "")

    # 한 화면에 다 쌓으면 끝없이 내려야 한다. 묶음 하나씩 본다.
    view = request.args.get("view", "ingredient")
    if view not in TREND_VIEWS:
        view = "ingredient"

    trade_page = request.args.get("trade_page", type=int)

    keep = {"view": view, "category": category, "hs": hs,
            "trade_year": trade_year, "cat": rank_cat}

    # 수출입 통계 수집 - 한 번에 6블록씩 받는다. (24블록이면 네 번)
    # 화장품 랭킹·업계 소식 수집 (아마존은 .env 에서 켜야 돈다)
    if request.args.get("collect") == "rank":
        result = beauty_rank_store.collect(force=request.args.get("force") == "1")
        amazon, magazine = result["amazon"], result["magazine"]
        parts = []
        if amazon.get("skipped"):
            parts.append("아마존 건너뜀({})".format(amazon.get("reason", "")))
        elif amazon.get("blocked"):
            parts.append("아마존이 자동 수집을 막아 멈췄습니다")
        else:
            parts.append("아마존 순위 {}건".format(amazon.get("rows", 0)))
        parts.append("업계 소식 새 글 {}건".format(magazine.get("new", 0))
                     if not magazine.get("skipped")
                     else "소식 건너뜀({})".format(magazine.get("reason", "")))
        session["trade_msg"] = ("ok", " / ".join(parts))
        return redirect(url_for("trends", **keep))

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
        rank=beauty_rank_store.rank_board(rank_cat, rank_day or None),
        brief=beauty_rank_store.brief(rank_cat),
        rank_articles=beauty_rank_store.articles(12),
        rank_sources=beauty_rank_store.status_summary(),
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

    # 프로젝트에서 열면 그 건에 저장해 둔 포장 구성으로 맞춘다
    project = None
    project_id = request.args.get("project", type=int)
    if project_id:
        project = project_store.get_project(project_id)
        if project and not parts and not preset:
            parts = [p for p in project["parts"] if p in packaging_store.PART_MAP]

    keep = {"preset": preset} if preset and not parts else {}
    if project:
        keep["project"] = project["id"]

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
        project=project,
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


def _all_profiles(keyword="", grade="all", kind="all"):
    """거래처 카드 = 예시 카드 + 화면·엑셀에서 등록한 회사."""
    return (dummy_data.get_customer_profiles(keyword, grade, kind)
            + customer_store.profiles(keyword, grade, kind))


def _find_profile(customer_id):
    """고객사 한 곳. 더미에 없으면 엑셀로 올린 쪽에서 찾는다."""
    return (dummy_data.get_customer_profile(customer_id)
            or customer_store.profile(customer_id))


@app.route("/company", methods=["GET", "POST"])
def company():
    """자사 정보. 모든 서류가 같은 값을 읽어 가는 자리."""
    if request.method == "POST":
        changed = company_store.save(request.form.to_dict(),
                                     who=session.get("user", DEFAULT_USER))
        if changed:
            names = [company_store.FIELD_MAP[k]["label"] for k in changed]
            session["contact_msg"] = ("ok", "{}개 칸을 고쳤습니다 ({}).".format(
                len(changed), " · ".join(names[:4])
                + (" 외" if len(names) > 4 else "")))
        else:
            session["contact_msg"] = ("ok", "바뀐 값이 없습니다.")
        return redirect(url_for("company"))

    return render_template("company.html", page_title="자사 정보",
                           active_menu="customers", d=company_store.board())


@app.route("/customers/new", methods=["POST"])
def customer_new():
    """거래처 한 곳을 화면에서 바로 등록한다.

    전에는 엑셀로 올리는 길밖에 없었다. 전시회에서 명함 한 장 받아 온 걸
    넣으려고 엑셀을 만들게 하면 아무도 안 쓴다.
    """
    name = (request.form.get("name") or "").strip()
    if not name:
        session["contact_msg"] = ("error", "회사명을 적어 주세요.")
        return redirect(url_for("customers", new="1"))

    # 이름이 같은 곳이 이미 있으면 새로 만들지 않고 그쪽으로 보낸다.
    # 표기만 다른 같은 회사가 둘로 갈리면 연락 기록이 쪼개진다.
    existing = customer_store.find_by_name(name)
    if existing:
        session["contact_msg"] = ("error", "이미 등록된 회사입니다: " + existing["name"])
        return redirect(url_for("customer_detail", customer_id=existing["id"]))
    for row in dummy_data.get_customer_profiles():
        if customer_store.norm_name(row["name"]) == customer_store.norm_name(name):
            session["contact_msg"] = ("error", "이미 등록된 회사입니다: " + row["name"])
            return redirect(url_for("customer_detail", customer_id=row["id"]))

    data = request.form.to_dict()
    data["source"] = "manual"
    customer_id = customer_store.create(
        data, taken_ids=[row["id"] for row in dummy_data.get_customer_profiles()])
    session["contact_msg"] = (
        "ok", "{} 을(를) 등록했습니다. 담당자를 이어서 넣어 주세요.".format(name))
    return redirect(url_for("customer_detail", customer_id=customer_id, tab="contacts"))


@app.route("/customers")
def customers():
    """8. 거래처 관리 - 목록. (UI 가안. 담당자·연락 기록은 실제 저장값)"""
    keyword = request.args.get("q", "")
    grade = request.args.get("grade", "all")
    kind = request.args.get("kind", "all")

    grouped = contact_store.contacts_by_customer()
    logged = contact_log_store.counts()
    rows = []
    for row in _all_profiles("", grade, kind):
        item = _with_contacts(row, grouped.get(row["id"], []))
        item["log_count"] = logged.get(row["id"], 0)
        rows.append(item)

    # 회사명·국가뿐 아니라 담당자 이름·이메일로도 찾을 수 있어야 한다
    needle = (keyword or "").strip().lower()
    if needle:
        rows = [row for row in rows if needle in " ".join(
            [row["name"], row["country"]] +
            [" ".join([c["name"], c["email"] or "", c["title"] or ""])
             for c in row["contacts"]]).lower()]

    summary = dummy_data.get_customer_summary()
    summary["contacts"] = sum(len(v) for v in grouped.values())
    # 화면·엑셀에서 등록한 회사도 거래처다. 요약 숫자에 같이 센다
    imported = customer_store.profiles()
    summary["total"] += len(imported)
    summary["vip"] += sum(1 for row in imported if row["grade"] == "vip")
    summary["imported"] = sum(1 for row in imported if row["source"] != "manual")
    summary["manual"] = sum(1 for row in imported if row["source"] == "manual")

    # 유형별 건수. 예시 카드는 전부 고객사다
    counted = customer_store.count_by_kind()
    for row in dummy_data.get_customer_profiles():
        key = row.get("kind", customer_store.DEFAULT_KIND)
        counted[key] = counted.get(key, 0) + 1
    # 파는 쪽 / 사는 쪽. 같은 거래처라도 챙기는 게 다르다
    summary["sell"] = sum(n for k, n in counted.items()
                          if customer_store.kind_meta(k)["side"] == "sell")
    summary["buy"] = sum(n for k, n in counted.items()
                         if customer_store.kind_meta(k)["side"] == "buy")

    return render_template(
        "customers.html",
        page_title="거래처 관리",
        active_menu="customers",
        rows=rows,
        summary=summary,
        grade_meta=dummy_data.CUSTOMER_GRADE_META,
        kinds=customer_store.kinds(),
        kind_counts=counted,
        show_new=request.args.get("new") == "1",
        selected={"q": keyword, "grade": grade, "kind": kind},
    )


@app.route("/customers/<customer_id>")
def customer_detail(customer_id):
    """8-1. 거래처 관리 - 상세. (UI 가안. 담당자·연락 기록은 실제 저장값)"""
    profile = _find_profile(customer_id)
    if profile is None:
        return redirect(url_for("customers"))

    profile = _with_contacts(profile)
    # 연락 기록은 담당자 목록에서 고르게 한다. 이름을 매번 타이핑하면
    # 철자가 조금씩 달라져서 나중에 사람별로 묶이지 않는다.
    profile["log"] = contact_log_store.of_customer(customer_id)
    profile["saved_notes"] = contact_log_store.notes_of(customer_id)

    # 진행 건은 더미가 아니라 실제 프로젝트를 읽는다.
    # 카드에 박아 둔 예시 목록과 실제 건이 따로 놀면 어느 쪽을 믿어야 할지 모른다.
    live = [row for row in project_store.list_projects()
            if row["customer_id"] == customer_id
            or (row["customer_name"] or "") == profile["name"]]
    profile["live_projects"] = live
    profile["signals"] = project_store.customer_signals(customer_id, profile["name"])

    return render_template(
        "customer_detail.html",
        page_title=profile["name"],
        active_menu="customers",
        c=profile,
        kinds=customer_store.kinds(),
        log_channels=contact_log_store.channels(),
        today=contact_log_store.today_iso(),
        tab=request.args.get("tab", "requests"),
        grade_meta=dummy_data.CUSTOMER_GRADE_META,
        request_meta=dummy_data.REQUEST_TYPE_META,
        priority_meta=dummy_data.PRIORITY_META,
        status_meta=dummy_data.HISTORY_STATUS_META,
        contact_roles=contact_store.ROLES,
        edit_contact=request.args.get("edit", type=int),
    )


@app.route("/customers/<customer_id>/update", methods=["POST"])
def customer_update(customer_id):
    """거래처 정보 고치기."""
    if _find_profile(customer_id) is None:
        return redirect(url_for("customers"))

    if customer_store.update(customer_id, request.form.to_dict()):
        session["contact_msg"] = ("ok", "거래처 정보를 고쳤습니다.")
    else:
        # 예시 카드는 저장할 곳이 없다
        session["contact_msg"] = ("error", "예시 카드는 고칠 수 없습니다.")
    return redirect(url_for("customer_detail", customer_id=customer_id,
                            tab=request.form.get("tab", "requests")))


@app.route("/customers/<customer_id>/notes", methods=["POST"])
def customer_notes(customer_id):
    """내부 메모. 전에는 화면에서만 붙고 새로고침하면 사라졌다."""
    if _find_profile(customer_id) is None:
        return redirect(url_for("customers"))

    back = url_for("customer_detail", customer_id=customer_id, tab="notes")
    if request.form.get("action") == "delete":
        contact_log_store.remove_note(request.form.get("note_id", type=int),
                                      customer_id)
        session["contact_msg"] = ("ok", "메모를 지웠습니다.")
        return redirect(back)

    ok = contact_log_store.add_note(customer_id, request.form.get("text", ""),
                                    session.get("user", DEFAULT_USER))
    session["contact_msg"] = (("ok", "메모를 남겼습니다.") if ok
                              else ("error", "메모 내용을 적어 주세요."))
    return redirect(back)


@app.route("/customers/<customer_id>/log", methods=["POST"])
def customer_log(customer_id):
    """고객사 연락 기록 한 줄. (누구와 · 어떤 방법으로 · 무슨 얘기)

    메일 원문은 여기 두지 않는다. 그건 그 건(프로젝트)에서 본다.
    여기는 "이 회사와 최근에 무슨 얘기가 오갔나" 를 한눈에 보는 자리다.
    """
    if _find_profile(customer_id) is None:
        return redirect(url_for("customers"))

    back = url_for("customer_detail", customer_id=customer_id, tab="log")
    form = request.form.to_dict()

    if form.get("action") == "delete":
        contact_log_store.remove(request.form.get("log_id", type=int), customer_id)
        session["contact_msg"] = ("ok", "기록을 지웠습니다.")
        return redirect(back)

    # 담당자를 목록에서 골랐으면 그때의 이름·역할을 같이 적어 둔다.
    # 나중에 그 담당자가 명단에서 빠져도 기록은 남아야 한다.
    contact_id = request.form.get("contact_id", type=int)
    if contact_id:
        for row in contact_store.list_contacts(customer_id):
            if row["id"] == contact_id:
                form["person"] = row["name"]
                form["role"] = row["role_meta"]["label"]
                break

    form["owner"] = session.get("user", DEFAULT_USER)
    ok = contact_log_store.add(customer_id, form)
    session["contact_msg"] = (("ok", "연락 기록을 남겼습니다.") if ok
                               else ("error", "무슨 얘기였는지 한 줄 적어 주세요."))
    return redirect(back)


# ---------------------------------------------------------------------------
# 프로젝트 - 한 건을 처음부터 끝까지 묶는 축
# ---------------------------------------------------------------------------

def _project_or_404(project_id):
    project = project_store.get_project(project_id)
    return project


def _project_profile(project):
    """고객사 프로필. 과거 요청사항과 대조할 때 쓴다."""
    if not project or not project.get("customer_id"):
        return None
    return _find_profile(project["customer_id"])


@app.route("/projects")
def projects():
    """프로젝트 목록. 지금 무엇이 몇 건 돌고 있는지."""
    status = request.args.get("status", "all")
    rows = project_store.list_projects(status)

    return render_template(
        "projects.html",
        page_title="프로젝트",
        active_menu="projects",
        rows=rows,
        status=status,
        status_meta=project_store.STATUS_META,
        stages=project_store.STAGES,
        states=[project_store.state_meta(k) for k in project_store.STATE_ORDER],
        customers=_all_profiles(),
        drops=project_store.drop_stats(),
        flash_msg=session.pop("project_msg", None),
    )


@app.route("/projects/new", methods=["POST"])
def project_new():
    """프로젝트를 연다.

    '샘플 요청서로 시작'을 고르면 요청서 분석 결과를 그대로 제품 조건으로 옮기고,
    빠진 항목을 바이어 확인사항으로 만든다. 흐름은 여기서 시작된다.
    """
    customer_id = (request.form.get("customer_id") or "").strip()
    profile = _find_profile(customer_id) if customer_id else None
    with_analysis = request.form.get("with_analysis") == "1"

    analysis = dummy_data.analyze_document() if with_analysis else None
    title = (request.form.get("title") or "").strip()
    if not title and analysis:
        title = next((i["value"] for i in analysis["items"]
                      if i["key"] == "product_name"), "")

    buyer_name = (request.form.get("buyer_name") or "").strip()
    buyer_email = (request.form.get("buyer_email") or "").strip()
    if profile and not buyer_name:
        contacts = contact_store.list_contacts(profile["id"], include_inactive=False)
        primary = contact_store.primary_of(contacts)
        if primary:
            buyer_name = primary["name"]
            buyer_email = buyer_email or (primary["email"] or "")

    project_id = project_store.create_project({
        "title": title or "새 프로젝트",
        "customer_id": customer_id,
        "customer_name": profile["name"] if profile else
                         (request.form.get("customer_name") or "").strip(),
        "buyer_name": buyer_name,
        "buyer_email": buyer_email,
        "country": profile["country"] if profile else
                   (request.form.get("country") or "").strip(),
        "owner": session.get("user", DEFAULT_USER).replace("해외영업팀 ", ""),
    }, analysis=analysis, profile=profile)

    session["project_msg"] = ("ok", "프로젝트를 열었습니다." + (
        " 요청서 분석 결과를 제품 조건으로 옮겼습니다." if with_analysis else ""))
    return redirect(url_for("project_hub", project_id=project_id))


@app.route("/projects/<int:project_id>")
def project_hub(project_id):
    """프로젝트 통합 화면. 한 건에 딸린 모든 것을 여기서 본다."""
    data = project_store.hub(project_id)
    if data is None:
        return redirect(url_for("projects"))

    project = data["project"]
    profile = _project_profile(project)
    grouped = contact_store.contacts_by_customer()

    # 일정은 기존 일정관리 모듈에 붙여 둔 건을 그대로 읽는다
    schedule = None
    if project["schedule_id"]:
        row = schedule_store.get_project(project["schedule_id"])
        if row:
            schedule = schedule_store.project_view(row)

    return render_template(
        "project.html",
        page_title=project["title"],
        active_menu="projects",
        d=data,
        # 이 고객사와 지금까지 어땠는지. 한 건만 보면 안 보인다
        signals=project_store.customer_signals(
            project["customer_id"], project["customer_name"] or "",
            skip_project_id=None),
        profile=profile,
        contacts=grouped.get(project["customer_id"], []),
        schedule=schedule,
        parts=packaging_store.PARTS,
        packaging=packaging_store.board(parts=project["parts"]) if project["parts"] else None,
        sample_specs=project_store.SAMPLE_SPECS,
        status_meta=project_store.STATUS_META,
        flash_msg=session.pop("project_msg", None),
    )


@app.route("/projects/<int:project_id>/update", methods=["POST"])
def project_update(project_id):
    if _project_or_404(project_id) is None:
        return redirect(url_for("projects"))

    action = request.form.get("action", "info")
    back = request.form.get("back") or url_for("project_hub", project_id=project_id)

    if action == "delete":
        project_store.delete_project(project_id)
        session["project_msg"] = ("ok", "프로젝트를 지웠습니다.")
        return redirect(url_for("projects"))

    if action == "field":
        key = request.form.get("key", "")
        if key in project_store.FIELD_LABELS:
            state = request.form.get("state", "user")
            project_store.set_field(project_id, key, request.form.get("value", ""),
                                    state, source="담당자 입력")
            profile = _project_profile(project_store.get_project(project_id))
            project_store.rebuild_questions(project_id, profile=profile)
            session["project_msg"] = ("ok", "{} 값을 고쳤습니다.".format(
                project_store.FIELD_LABELS[key]))
        return redirect(back)

    if action == "close":
        # 왜 안 갔는지를 안 적으면 내년에 같은 일을 처음부터 다시 한다
        reason = request.form.get("reason", "")
        if project_store.close_project(project_id, reason,
                                       request.form.get("closed_note", "")):
            session["project_msg"] = (
                "ok", "{} 사유로 무산 처리했습니다. 지우지 않았으니 다시 열 수 있습니다."
                .format(project_store.DROP_MAP[reason]["label"]))
        else:
            session["project_msg"] = ("error", "무산 사유를 골라 주세요.")
        return redirect(back)

    if action == "reopen":
        project_store.reopen_project(project_id)
        session["project_msg"] = ("ok", "다시 열었습니다. 무산 사유는 지웠습니다.")
        return redirect(back)

    if action == "parts":
        parts = [p for p in request.form.getlist("part")
                 if p in packaging_store.PART_MAP]
        project_store.set_parts(project_id, parts)
        session["project_msg"] = ("ok", "포장 구성을 저장했습니다. 관련 소재값만 보여 줍니다.")
        return redirect(back)

    if action == "schedule":
        project = project_store.get_project(project_id)
        if project["schedule_id"]:
            session["project_msg"] = ("ok", "이미 일정이 걸려 있습니다.")
            return redirect(back)

        schedule_id = schedule_store.create_project({
            "title": project["title"],
            "account": project["customer_name"],
            "account_kind": "customer",
            "country": project["country"],
            "owner": "해외영업",
            "customer_id": project["customer_id"],
            "origin": "project",
            "start_date": request.form.get("start_date") or project_store.today_iso(),
            "pace": request.form.get("pace", "standard"),
        })
        project_store.set_schedule(project_id, schedule_id)
        session["project_msg"] = ("ok", "샘플·생산·선적 일정을 만들어 붙였습니다.")
        return redirect(back)

    project_store.update_project(project_id, request.form.to_dict())
    session["project_msg"] = ("ok", "프로젝트 정보를 고쳤습니다.")
    return redirect(back)


@app.route("/projects/<int:project_id>/questions", methods=["GET", "POST"])
def project_questions(project_id):
    """바이어 확인사항과 영문 회신 초안."""
    project = _project_or_404(project_id)
    if project is None:
        return redirect(url_for("projects"))

    back = url_for("project_questions", project_id=project_id)

    if request.method == "POST":
        action = request.form.get("action", "draft")
        keys = request.form.getlist("key")

        if action == "answer":
            project_store.update_question(request.form.get("question_id", type=int), {
                "status": "answered",
                "answer": request.form.get("answer", ""),
            })
            session["project_msg"] = ("ok", "회신을 반영했습니다. 제품 조건에 확정값으로 올렸습니다.")
            return redirect(back)

        if action == "ask":
            n = project_store.mark_questions(project_id, keys, "asked")
            session["project_msg"] = ("ok", "{}건을 문의함으로 표시했습니다.".format(n))
            return redirect(back)

        if action == "close":
            n = project_store.mark_questions(project_id, keys, "closed")
            session["project_msg"] = ("ok", "{}건을 정리했습니다.".format(n))
            return redirect(back)

        if action == "rebuild":
            profile = _project_profile(project)
            made = project_store.rebuild_questions(project_id, profile=profile)
            session["project_msg"] = ("ok", "다시 훑었습니다. 새 확인사항 {}건.".format(made))
            return redirect(back)

        # 기본: 메일 초안 만들기
        session["q_draft"] = keys
        return redirect(back)

    picked = session.pop("q_draft", None)
    draft = project_store.draft_email(project_id, picked) if picked is not None else None

    return render_template(
        "project_questions.html",
        page_title="바이어 확인사항",
        active_menu="projects",
        p=project,
        rows=project_store.questions_of(project_id),
        draft=draft,
        picked=set(picked or []),
        progress=project_store.progress(project_id),
        flash_msg=session.pop("project_msg", None),
    )


@app.route("/projects/<int:project_id>/samples", methods=["GET", "POST"])
def project_samples(project_id):
    """샘플 버전과 피드백."""
    project = _project_or_404(project_id)
    if project is None:
        return redirect(url_for("projects"))

    back = url_for("project_samples", project_id=project_id)

    if request.method == "POST":
        action = request.form.get("action", "add")
        data = request.form.to_dict()

        if action == "add":
            project_store.add_sample(project_id, data)
            session["project_msg"] = ("ok", "샘플을 추가했습니다.")
        elif action == "update":
            project_store.update_sample(request.form.get("sample_id", type=int), data)
            session["project_msg"] = ("ok", "샘플을 고쳤습니다.")
        elif action == "feedback":
            ok = project_store.add_feedback(request.form.get("sample_id", type=int), data)
            session["project_msg"] = (("ok", "피드백을 저장했습니다.") if ok
                                      else ("error", "내용을 적어 주세요."))
        elif action == "delete":
            project_store.delete_sample(request.form.get("sample_id", type=int))
            session["project_msg"] = ("ok", "샘플을 지웠습니다.")
        return redirect(back)

    return render_template(
        "project_samples.html",
        page_title="샘플 · 피드백",
        active_menu="projects",
        p=project,
        rows=project_store.samples_of(project_id),
        specs=project_store.SAMPLE_SPECS,
        status_meta=project_store.SAMPLE_STATUS,
        status_order=project_store.SAMPLE_STATUS_ORDER,
        sides=project_store.FEEDBACK_SIDES,
        verdicts=project_store.FEEDBACK_VERDICTS,
        progress=project_store.progress(project_id),
        flash_msg=session.pop("project_msg", None),
    )


@app.route("/projects/<int:project_id>/quotes", methods=["GET", "POST"])
def project_quotes(project_id):
    """견적 대안 비교. 조건을 바꿔 가며 나란히 본다."""
    project = _project_or_404(project_id)
    if project is None:
        return redirect(url_for("projects"))

    back = url_for("project_quotes", project_id=project_id)

    if request.method == "POST":
        action = request.form.get("action", "add")
        if action == "add":
            project_store.add_quote(project_id, request.form.to_dict())
            session["project_msg"] = ("ok", "견적 대안을 넣었습니다.")
        elif action == "delete":
            project_store.delete_quote(request.form.get("quote_id", type=int))
            session["project_msg"] = ("ok", "대안을 지웠습니다.")
        elif action == "choose":
            project_store.choose_quote(project_id, request.form.get("quote_id", type=int))
            session["project_msg"] = ("ok", "이 대안을 골랐습니다. 수량·조건·통화를 제품 조건에 확정값으로 올렸습니다.")
        elif action == "seed":
            sheet = dummy_data.parse_cost_sheet()
            made = project_store.seed_quotes(
                project_id, unit_cost=sheet["total"], basis="example")
            session["project_msg"] = ("ok", "비교용 대안 {}개를 깔았습니다. 원가는 예시값입니다.".format(made))
        return redirect(back)

    sheet = dummy_data.parse_cost_sheet()
    return render_template(
        "project_quotes.html",
        page_title="견적 대안 비교",
        active_menu="projects",
        p=project,
        rows=project_store.quote_rows(project_id),
        tiers=project_store.CONTAINER_TIERS,
        basis_meta=project_store.QUOTE_BASIS,
        incoterms=dummy_data.INCOTERMS,
        currencies=dummy_data.CURRENCIES,
        sheet=sheet,
        progress=project_store.progress(project_id),
        flash_msg=session.pop("project_msg", None),
    )


def _project_people(project):
    """이 건의 고객사 담당자. 연락 기록에서 고르게 내려준다."""
    if not project or not project.get("customer_id"):
        return []
    return [row for row in contact_store.list_contacts(project["customer_id"])
            if row["is_active"]]


@app.route("/projects/<int:project_id>/contacts", methods=["GET", "POST"])
def project_contacts(project_id):
    """바이어 연락.

    연락 기록(누구와 · 어떻게 · 무슨 얘기)과 주고받은 메일이 같이 있다.
    고객사 화면에는 한 줄 메모만 두고, 메일 원문은 그 건인 여기서 읽는다.
    """
    project = _project_or_404(project_id)
    if project is None:
        return redirect(url_for("projects"))

    back = url_for("project_contacts", project_id=project_id)

    if request.method == "POST":
        if request.form.get("action") == "delete":
            project_store.remove_contact(project_id,
                                         request.form.get("log_id", type=int))
            session["project_msg"] = ("ok", "기록을 지웠습니다.")
            return redirect(request.form.get("back") or back)

        form = request.form.to_dict()
        contact_id = request.form.get("contact_id", type=int)
        if contact_id:
            for row in _project_people(project):
                if row["id"] == contact_id:
                    form["person"] = row["name"]
                    form["role"] = row["role_meta"]["label"]
                    break
        form["owner"] = session.get("user", DEFAULT_USER)

        ok = project_store.add_contact(project_id, form)
        session["project_msg"] = (("ok", "연락 기록을 남겼습니다.") if ok
                                  else ("error", "무슨 얘기였는지 한 줄 적어 주세요."))
        return redirect(request.form.get("back") or back)

    profile = _project_profile(project)
    return render_template(
        "project_contacts.html",
        page_title="바이어 연락",
        active_menu="projects",
        p=project,
        progress=project_store.progress(project_id),
        contacts=project_store.contacts_of(project_id),
        people=_project_people(project),
        # 메일 이력은 아직 고객사 예시 데이터다. 화면에 그렇게 적는다
        mails=(profile or {}).get("emails") or [],
        profile=profile,
        channels=[dict(project_store.CONTACT_CHANNELS[k], value=k)
                  for k in project_store.CONTACT_CHANNEL_ORDER],
        today=project_store.today_iso(),
        msg=session.pop("project_msg", None),
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
    """거래처·담당자를 엑셀로 내려받는다. 어떤 값을 받을지 고를 수 있다.

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
        label = "거래처_담당자"
    name = "{}_{}.xlsx".format(label, date.today().strftime("%Y%m%d"))
    return _xlsx(customer_excel.build_workbook(
        rows, with_guide=opt["guide"], columns=opt["columns"]), name)


@app.route("/customers/template")
def customers_template():
    """빈 양식. 예시 두 줄과 작성 안내가 들어 있다."""
    return _xlsx(customer_excel.build_template(), "거래처_담당자_양식.xlsx")


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
    """엑셀 명단을 올려 거래처·담당자를 한 번에 등록한다.

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
