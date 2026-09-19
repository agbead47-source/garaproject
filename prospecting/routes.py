# -*- coding: utf-8 -*-
"""신규 바이어 발굴 - Flask Blueprint (명세 4절)."""

import csv
import io
import json
import secrets

from flask import (Blueprint, Response, abort, redirect, render_template,
                   request, send_file, session, url_for)

from . import (analytics, collectors, matching, models, pipeline, proposals,
               report, repository, seed_demo)

bp = Blueprint("prospecting", __name__)

MODE_KEY = "prospect_data_mode"
CSRF_KEY = "prospect_csrf"


# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------

def csrf_token():
    token = session.get(CSRF_KEY)
    if not token:
        token = secrets.token_urlsafe(24)
        session[CSRF_KEY] = token
    return token


@bp.before_request
def guard():
    repository.init_db()
    if request.method == "POST":
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not sent or sent != session.get(CSRF_KEY):
            abort(400, "요청 토큰이 올바르지 않습니다. 화면을 새로고침한 뒤 다시 시도해 주세요.")
    return None


@bp.context_processor
def inject():
    return {
        "csrf_token": csrf_token(),
        "data_mode": current_mode(),
        "M": models,
        "timezone_label": models.TIMEZONE_LABEL,
        "today": models.today_iso(),
    }


def current_mode():
    mode = request.args.get("data_mode") or session.get(MODE_KEY) or "real"
    if mode not in ("real", "demo"):
        mode = "real"
    session[MODE_KEY] = mode
    return mode


def current_fit_mode():
    mode = request.args.get("mode") or "oem"
    return mode if mode in ("oem", "odm") else "oem"


def _flash(message, level="info"):
    session["prospect_flash"] = {"message": message, "level": level}


def _take_flash():
    return session.pop("prospect_flash", None)


# ---------------------------------------------------------------------------
# 4.1 후보 목록
# ---------------------------------------------------------------------------

@bp.route("/prospects")
def prospect_list():
    data_mode = current_mode()
    fit_mode = current_fit_mode()

    filters = {key: request.args.get(key, "all")
               for key in ("hq", "market", "btype", "stage", "owner")}
    filters["q"] = request.args.get("q", "")

    rows = repository.list_prospects(data_mode, **filters)
    scores = repository.all_scores(fit_mode)
    products = repository.all_products(data_mode)
    summaries = pipeline.aggregate_products(products)

    for row in rows:
        score = scores.get(row["id"])
        summary = summaries.get(row["id"], {})
        row["summary"] = summary
        row["score"] = {
            "fit_score": score["fit_score"] if score else None,
            "coverage": score["coverage"] if score else 0.0,
            "blocking": bool(score["blocking"]) if score else False,
            "reason": score["reason"] if score else "아직 채점하지 않았습니다.",
            "insufficient": (not score) or (score["coverage"] or 0) < models.COVERAGE_THRESHOLD,
        }

    sort = request.args.get("sort", "fit")
    if sort == "recent":
        rows.sort(key=lambda r: r["updated_at"], reverse=True)
    elif sort == "due":
        due = {f["prospect_id"]: f["due_date"]
               for f in repository.list_followups(data_mode=data_mode)
               if f["status"] == "open"}
        rows.sort(key=lambda r: (due.get(r["id"]) is None, due.get(r["id"]) or ""))
    else:
        rows.sort(key=matching.sort_key)

    today = models.today_iso()
    followups = repository.list_followups(data_mode=data_mode)
    next_due = {}
    for item in followups:
        if item["status"] != "open":
            continue
        key = item["prospect_id"]
        if key not in next_due or item["due_date"] < next_due[key]:
            next_due[key] = item["due_date"]
    for row in rows:
        row["next_due"] = next_due.get(row["id"])

    return render_template(
        "prospecting/list.html",
        page_title="신규 바이어 발굴",
        active_menu="prospecting",
        rows=rows,
        fit_mode=fit_mode,
        sort=sort,
        selected=filters,
        duplicates=pipeline.duplicate_candidates(rows),
        counts=repository.counts_by_mode(),
        summary={
            "total": len(rows),
            "reviewable": sum(1 for r in rows
                              if r["score"]["fit_score"] is not None
                              and not r["score"]["insufficient"]),
            "due_today": sum(1 for f in followups
                             if f["status"] == "open" and f["due_date"] == today),
            "overdue": sum(1 for f in followups
                           if f["status"] == "open" and f["due_date"] < today),
        },
        flash=_take_flash(),
    )


@bp.route("/prospects/new", methods=["POST"])
def prospect_new():
    data_mode = current_mode()
    url = (request.form.get("official_url") or "").strip()
    name = (request.form.get("company_name") or "").strip()

    if not name:
        _flash("회사명을 입력해 주세요.", "error")
        return redirect(url_for("prospecting.prospect_list"))
    if not models.is_valid_http_url(url):
        _flash("공식 사이트 주소는 http:// 또는 https:// 로 시작해야 합니다.", "error")
        return redirect(url_for("prospecting.prospect_list"))

    domain = models.canonical_domain(url)
    if repository.find_by_domain(domain, data_mode):
        _flash("같은 도메인({})의 후보가 이미 있습니다. 중복 후보로 표시됩니다.".format(domain), "warn")

    prospect_id = repository.create_prospect({
        "company_name": name,
        "brand_name": request.form.get("brand_name"),
        "official_url": url,
        "contact_url": request.form.get("contact_url"),
        "headquarters_country": pipeline.normalize_country(
            request.form.get("headquarters_country")),
        "sales_country": pipeline.normalize_country(request.form.get("sales_country")),
        "business_type": request.form.get("business_type") or "unknown",
        "source_channel": request.form.get("source_channel"),
        "owner": request.form.get("owner"),
        "data_mode": data_mode,
    })
    for mode in ("oem", "odm"):
        matching.rescore_prospect(repository, prospect_id, mode)
    return redirect(url_for("prospecting.prospect_detail", prospect_id=prospect_id))


@bp.route("/prospects/<int:prospect_id>/delete", methods=["POST"])
def prospect_delete(prospect_id):
    repository.delete_prospect(prospect_id)
    _flash("후보를 삭제했습니다.", "info")
    return redirect(url_for("prospecting.prospect_list"))


@bp.route("/prospects/<int:prospect_id>/edit", methods=["POST"])
def prospect_edit(prospect_id):
    repository.update_prospect(prospect_id, {
        "company_name": request.form.get("company_name"),
        "brand_name": request.form.get("brand_name"),
        "official_url": request.form.get("official_url"),
        "contact_url": request.form.get("contact_url"),
        "headquarters_country": pipeline.normalize_country(
            request.form.get("headquarters_country")),
        "sales_country": pipeline.normalize_country(request.form.get("sales_country")),
        "business_type": request.form.get("business_type"),
        "source_channel": request.form.get("source_channel"),
        "owner": request.form.get("owner"),
        "notes": request.form.get("notes"),
    })
    _flash("기업 정보를 저장했습니다.", "info")
    return redirect(url_for("prospecting.prospect_detail", prospect_id=prospect_id, tab="overview"))


@bp.route("/prospects/<int:prospect_id>/stage", methods=["POST"])
def prospect_stage(prospect_id):
    to_stage = request.form.get("stage")
    reason = request.form.get("reason", "")
    if to_stage not in models.STAGE_LABELS:
        abort(400, "알 수 없는 단계입니다.")

    repository.change_stage(prospect_id, to_stage, reason)
    if to_stage in ("on_hold", "closed"):
        repository.update_prospect(prospect_id, {
            "hold_reason": reason,
            "review_date": request.form.get("review_date"),
        })
    return redirect(url_for("prospecting.prospect_detail", prospect_id=prospect_id, tab="contacts"))


# ---------------------------------------------------------------------------
# 4.2 후보 상세
# ---------------------------------------------------------------------------

@bp.route("/prospects/<int:prospect_id>")
def prospect_detail(prospect_id):
    prospect = repository.get_prospect(prospect_id)
    if not prospect:
        abort(404)

    fit_mode = current_fit_mode()
    products = repository.list_products(prospect_id)
    summary = pipeline.aggregate_products(
        [dict(p, prospect_id=prospect_id) for p in products]).get(prospect_id, {})
    requirements = repository.list_requirements(prospect_id)
    checks, score = matching.evaluate(
        repository.get_capabilities(), summary, requirements, fit_mode)
    repository.save_checks(prospect_id, fit_mode, checks, score)

    ingredient_rows = repository.rows(
        "SELECT i.inci_name FROM product_ingredients i"
        " JOIN products p ON p.id = i.product_id WHERE p.prospect_id = ?", (prospect_id,))

    return render_template(
        "prospecting/detail.html",
        page_title=prospect["company_name"],
        active_menu="prospecting",
        p=prospect,
        tab=request.args.get("tab", "overview"),
        fit_mode=fit_mode,
        products=products,
        summary=summary,
        ingredients=pipeline.ingredient_frequency(products, ingredient_rows),
        requirements=requirements,
        checks=checks,
        score=score,
        hypotheses=proposals.HYPOTHESES,
        saved_proposals=repository.list_proposals(prospect_id),
        interactions=repository.list_interactions(prospect_id),
        followups=repository.list_followups(prospect_id, data_mode=prospect["data_mode"]),
        stage_events=repository.stage_events(prospect_id),
        runs=repository.list_runs(prospect_id),
        duplicates=repository.find_by_domain(prospect["canonical_domain"],
                                             prospect["data_mode"]),
        flash=_take_flash(),
    )


@bp.route("/prospects/<int:prospect_id>/requirements", methods=["POST"])
def add_requirement(prospect_id):
    field = request.form.get("field_name")
    value = (request.form.get("value") or "").strip()
    if not field or not value:
        _flash("항목과 값을 모두 입력해 주세요.", "error")
    else:
        repository.add_requirement(
            prospect_id, field, value, request.form.get("unit", ""),
            request.form.get("verification_status", "unverified"),
            request.form.get("note", ""))
        for mode in ("oem", "odm"):
            matching.rescore_prospect(repository, prospect_id, mode)
    return redirect(url_for("prospecting.prospect_detail", prospect_id=prospect_id, tab="fit"))


@bp.route("/prospects/<int:prospect_id>/requirements/<int:req_id>/delete", methods=["POST"])
def delete_requirement(prospect_id, req_id):
    repository.delete_requirement(req_id)
    for mode in ("oem", "odm"):
        matching.rescore_prospect(repository, prospect_id, mode)
    return redirect(url_for("prospecting.prospect_detail", prospect_id=prospect_id, tab="fit"))


# ---------------------------------------------------------------------------
# 수집 (명세 5.2) - 실패를 더미로 덮지 않는다
# ---------------------------------------------------------------------------

@bp.route("/prospects/<int:prospect_id>/collect", methods=["POST"])
def collect(prospect_id):
    prospect = repository.get_prospect(prospect_id)
    if not prospect:
        abort(404)

    target = (request.form.get("url") or prospect["official_url"] or "").strip()
    source_id = repository.add_source(target, "official_site", "unknown",
                                      "담당자가 등록한 공식 페이지")
    run_id = repository.start_run(source_id, prospect_id)

    try:
        result = collectors.collect_product_page(target)
    except (collectors.CollectionError, models.UnsafeUrl) as exc:
        repository.finish_run(run_id, "failed", 0, str(exc)[:300])
        repository.run("UPDATE sources SET collection_allowed = 'denied' WHERE id = ?",
                       (source_id,))
        _flash("수집하지 못했습니다: {} (기존 데이터는 그대로 둡니다)".format(exc), "error")
        return redirect(url_for("prospecting.prospect_detail",
                                prospect_id=prospect_id, tab="products"))

    repository.run("UPDATE sources SET collection_allowed = 'allowed',"
                   " evidence_excerpt = ? WHERE id = ?",
                   (result["robots_note"][:300], source_id))
    repository.touch_source(source_id, result["content_hash"])

    added = updated = 0
    for item in result["products"]:
        product_id, created = repository.upsert_product(prospect_id, {
            "product_name": item["product_name"],
            "product_category": item["product_category"],
            "size_value": item["size_value"],
            "size_unit": item["size_unit"],
            "retail_price": item["retail_price"],
            "currency": item["currency"],
            "source_url": item["source_url"],
            "collected_at": models.now_iso(),
            "source_id": source_id,
            "raw_price": item["raw_price"],
            "raw_size": item["raw_size"],
        })
        added += 1 if created else 0
        updated += 0 if created else 1

    status = "success" if result["products"] else "empty"
    repository.finish_run(run_id, status, len(result["products"]), result["note"])

    if result["products"]:
        _flash("제품 {}건 수집 (신규 {} · 갱신 {}). {}".format(
            len(result["products"]), added, updated, result["robots_note"]), "info")
        for mode in ("oem", "odm"):
            matching.rescore_prospect(repository, prospect_id, mode)
    else:
        _flash("접근은 됐지만 제품 정보를 찾지 못했습니다: {}".format(result["note"]), "warn")

    return redirect(url_for("prospecting.prospect_detail",
                            prospect_id=prospect_id, tab="products"))


# ---------------------------------------------------------------------------
# CSV 가져오기 / 내보내기 (명세 7절)
# ---------------------------------------------------------------------------

@bp.route("/prospects/import", methods=["GET", "POST"])
def csv_import():
    data_mode = current_mode()
    preview = None

    if request.method == "POST" and request.form.get("step") == "save":
        payload = json.loads(request.form.get("payload") or "[]")
        created = skipped = 0
        for record in payload:
            if repository.find_by_domain(record.get("canonical_domain"), data_mode):
                skipped += 1
                continue
            prospect_id = repository.create_prospect({
                "company_name": record.get("company_name"),
                "brand_name": record.get("brand_name"),
                "official_url": record.get("official_url"),
                "contact_url": record.get("contact_url"),
                "headquarters_country": record.get("headquarters_country"),
                "sales_country": record.get("sales_country"),
                "business_type": record.get("business_type") or "unknown",
                "source_channel": record.get("source_channel"),
                "data_mode": data_mode,
            })
            for mode in ("oem", "odm"):
                matching.rescore_prospect(repository, prospect_id, mode)
            created += 1
        _flash("{}건 등록, {}건은 같은 도메인이 이미 있어 건너뛰었습니다.".format(created, skipped),
               "info")
        return redirect(url_for("prospecting.prospect_list"))

    if request.method == "POST":
        upload = request.files.get("file")
        if not upload or not upload.filename:
            _flash("CSV 파일을 선택해 주세요.", "error")
        elif not upload.filename.lower().endswith(".csv"):
            _flash("확장자가 .csv 인 파일만 올릴 수 있습니다.", "error")
        else:
            raw = upload.read(models.MAX_CSV_BYTES + 1)
            if len(raw) > models.MAX_CSV_BYTES:
                _flash("파일이 너무 큽니다 (최대 2MB).", "error")
            else:
                preview = pipeline.read_csv_preview(raw)
                preview["payload"] = json.dumps(preview["accepted"], ensure_ascii=False)

    return render_template(
        "prospecting/import.html",
        page_title="후보 CSV 가져오기",
        active_menu="prospecting",
        preview=preview,
        flash=_take_flash(),
    )


@bp.route("/prospects/export.csv")
def csv_export():
    data_mode = current_mode()
    fit_mode = current_fit_mode()
    rows = repository.list_prospects(data_mode)
    scores = repository.all_scores(fit_mode)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["company_name", "brand_name", "canonical_domain",
                     "headquarters_country", "sales_country", "business_type",
                     "stage", "source_channel", "owner", "data_mode",
                     "fit_mode", "fit_score", "coverage", "blocking"])
    for row in rows:
        score = scores.get(row["id"]) or {}
        writer.writerow([models.csv_safe(row.get(key)) for key in
                         ("company_name", "brand_name", "canonical_domain",
                          "headquarters_country", "sales_country", "business_type",
                          "stage", "source_channel", "owner", "data_mode")] +
                        [fit_mode,
                         "" if score.get("fit_score") is None else round(score["fit_score"], 1),
                         score.get("coverage", ""),
                         "Y" if score.get("blocking") else ""])

    return Response(
        buffer.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition":
                 'attachment; filename="prospects_{}_{}.csv"'.format(
                     data_mode, models.today_iso())},
    )


# ---------------------------------------------------------------------------
# 4.3 자사 역량
# ---------------------------------------------------------------------------

@bp.route("/company-capabilities", methods=["GET", "POST"])
def capabilities():
    if request.method == "POST":
        moq_rows = []
        for category, value, unit in zip(request.form.getlist("moq_category"),
                                         request.form.getlist("moq_value"),
                                         request.form.getlist("moq_unit")):
            if not category.strip():
                continue
            amount, _ = models.parse_amount(value)
            moq_rows.append({"product_category": category.strip(),
                             "moq_value": amount, "moq_unit": unit.strip()})

        cert_rows = []
        verified = set(request.form.getlist("cert_verified"))
        for index, (name, scope, until) in enumerate(zip(request.form.getlist("cert_name"),
                                                         request.form.getlist("cert_scope"),
                                                         request.form.getlist("cert_until"))):
            if not name.strip():
                continue
            cert_rows.append({"name": name.strip(), "scope": scope.strip(),
                              "valid_until": until.strip(),
                              "internally_verified": str(index) in verified})

        repository.save_capabilities({
            "mode": request.form.get("mode", "both"),
            "product_categories": request.form.get("product_categories", ""),
            "formulations": request.form.get("formulations", ""),
            "countries": request.form.get("countries", ""),
            "regulatory_support": request.form.get("regulatory_support", ""),
            "sample_lead_time": request.form.get("sample_lead_time", ""),
            "mass_lead_time": request.form.get("mass_lead_time", ""),
            "lead_time_note": request.form.get("lead_time_note", ""),
            "contact_person": request.form.get("contact_person", ""),
        }, moq_rows, cert_rows)

        for row in repository.list_prospects(current_mode()):
            for mode in ("oem", "odm"):
                matching.rescore_prospect(repository, row["id"], mode)

        _flash("자사 역량을 저장하고 후보 점수를 다시 계산했습니다.", "info")
        return redirect(url_for("prospecting.capabilities"))

    cap = repository.get_capabilities()
    data_mode = current_mode()
    prospects = repository.list_prospects(data_mode)
    scores = repository.all_scores(current_fit_mode())

    return render_template(
        "prospecting/capabilities.html",
        page_title="자사 역량",
        active_menu="prospecting",
        cap=cap,
        # 이 화면이 왜 있는지를 숫자로 보여 준다
        ready=matching.readiness(cap),
        fit_mode=current_fit_mode(),
        data_mode=data_mode,
        prospect_count=len(prospects),
        scored_count=sum(
            1 for row in prospects
            if (scores.get(row["id"]) or {}).get("fit_score") is not None),
        flash=_take_flash(),
    )


# ---------------------------------------------------------------------------
# 4.4 제안 초안
# ---------------------------------------------------------------------------

def _build_proposal(prospect_id, mode, language, hypothesis):
    prospect = repository.get_prospect(prospect_id)
    if not prospect:
        abort(404)
    products = repository.list_products(prospect_id)
    summary = pipeline.aggregate_products(
        [dict(p, prospect_id=prospect_id) for p in products]).get(prospect_id, {})
    requirements = repository.list_requirements(prospect_id)
    checks, score = matching.evaluate(
        repository.get_capabilities(), summary, requirements, mode)
    draft = proposals.build(prospect, products, summary, checks,
                            repository.get_capabilities(), mode, language, hypothesis)
    return prospect, draft, checks, score


@bp.route("/prospects/<int:prospect_id>/proposal", methods=["GET", "POST"])
def proposal(prospect_id):
    mode = current_fit_mode()
    language = request.values.get("language", "ko")
    if language not in ("ko", "en"):
        language = "ko"
    hypothesis = request.values.get("hypothesis", proposals.HYPOTHESES[0]["value"])

    if request.method == "POST":
        repository.save_proposal(
            prospect_id, mode, language, hypothesis,
            request.form.get("subject", ""), request.form.get("body", ""),
            request.form.get("review_status", "draft"))
        _flash("제안 초안을 저장했습니다.", "info")
        return redirect(url_for("prospecting.proposal", prospect_id=prospect_id,
                                mode=mode, language=language, hypothesis=hypothesis))

    prospect, draft, checks, score = _build_proposal(prospect_id, mode, language, hypothesis)
    saved = repository.get_proposal(prospect_id, mode, language)

    return render_template(
        "prospecting/proposal.html",
        page_title="{} 제안 초안".format(prospect["company_name"]),
        active_menu="prospecting",
        p=prospect,
        draft=draft,
        saved=saved,
        checks=checks,
        score=score,
        mode=mode,
        language=language,
        hypothesis=hypothesis,
        hypotheses=proposals.HYPOTHESES,
        languages=proposals.LANGUAGES,
        flash=_take_flash(),
    )


@bp.route("/prospects/<int:prospect_id>/proposal/download")
def proposal_download(prospect_id):
    mode = current_fit_mode()
    language = request.args.get("language", "ko")
    hypothesis = request.args.get("hypothesis", proposals.HYPOTHESES[0]["value"])
    fmt = request.args.get("format", "txt")

    saved = repository.get_proposal(prospect_id, mode, language)
    if saved and saved["body"]:
        subject, body = saved["subject"], saved["body"]
        prospect = repository.get_prospect(prospect_id)
    else:
        prospect, draft, _, _ = _build_proposal(prospect_id, mode, language, hypothesis)
        subject, body = draft["subject"], draft["body"]

    if fmt == "md":
        content = "# {}\n\n{}\n".format(subject, body)
        extension, mimetype = "md", "text/markdown"
    else:
        content = "{}\n\n{}\n".format(subject, body)
        extension, mimetype = "txt", "text/plain"

    filename = "proposal_{}_{}_{}.{}".format(
        (prospect["canonical_domain"] or "prospect").replace(".", "_"),
        mode, language, extension)
    return Response(content.encode("utf-8-sig"), mimetype=mimetype + "; charset=utf-8",
                    headers={"Content-Disposition":
                             'attachment; filename="{}"'.format(filename)})


# ---------------------------------------------------------------------------
# 4.5 연락 / 후속 업무
# ---------------------------------------------------------------------------

@bp.route("/prospects/<int:prospect_id>/interactions", methods=["POST"])
def add_interaction(prospect_id):
    interaction_id = repository.add_interaction(prospect_id, {
        "occurred_at": request.form.get("occurred_at") or models.today_iso(),
        "channel": request.form.get("channel"),
        "direction": request.form.get("direction"),
        "summary": request.form.get("summary"),
        "outcome": request.form.get("outcome"),
        "owner": request.form.get("owner"),
    })

    due = (request.form.get("due_date") or "").strip()
    task = (request.form.get("task") or "").strip()
    if due and task:
        repository.add_followup(prospect_id, due, task,
                                request.form.get("owner"), interaction_id)

    _flash("연락 기록을 저장했습니다. 단계는 자동으로 바뀌지 않습니다.", "info")
    return redirect(url_for("prospecting.prospect_detail",
                            prospect_id=prospect_id, tab="contacts"))


@bp.route("/prospect-followups")
def followups():
    data_mode = current_mode()
    view = request.args.get("view", "open")
    today = models.today_iso()
    rows = repository.list_followups(data_mode=data_mode)

    def keep(item):
        if view == "today":
            return item["status"] == "open" and item["due_date"] == today
        if view == "overdue":
            return item["status"] == "open" and item["due_date"] < today
        if view == "done":
            return item["status"] == "done"
        if view == "open":
            return item["status"] == "open"
        return True

    filtered = [r for r in rows if keep(r)]
    for item in filtered:
        item["overdue"] = item["status"] == "open" and item["due_date"] < today

    return render_template(
        "prospecting/followups.html",
        page_title="후속 연락",
        active_menu="prospecting",
        rows=filtered,
        view=view,
        counts={
            "today": sum(1 for r in rows if r["status"] == "open" and r["due_date"] == today),
            "overdue": sum(1 for r in rows if r["status"] == "open" and r["due_date"] < today),
            "open": sum(1 for r in rows if r["status"] == "open"),
            "done": sum(1 for r in rows if r["status"] == "done"),
        },
        flash=_take_flash(),
    )


@bp.route("/prospect-followups/<int:followup_id>/done", methods=["POST"])
def followup_done(followup_id):
    repository.complete_followup(followup_id)
    return redirect(request.form.get("next") or url_for("prospecting.followups"))


@bp.route("/prospect-followups/<int:followup_id>/reschedule", methods=["POST"])
def followup_reschedule(followup_id):
    due = (request.form.get("due_date") or "").strip()
    if due:
        repository.reschedule_followup(followup_id, due)
    return redirect(request.form.get("next") or url_for("prospecting.followups"))


# ---------------------------------------------------------------------------
# 4.6 분석
# ---------------------------------------------------------------------------

def current_days():
    """집계 기간. 화면과 내려받기가 같은 값을 써야 한다."""
    try:
        days = int(request.args.get("days", 90))
    except (TypeError, ValueError):
        days = 90
    return days if days in (30, 90, 180, 365) else 90


@bp.route("/prospects/analytics")
def analytics_view():
    data_mode = current_mode()
    fit_mode = current_fit_mode()
    days = current_days()

    return render_template(
        "prospecting/analytics.html",
        page_title="발굴 분석",
        active_menu="prospecting",
        data=analytics.overview(repository, data_mode, days, fit_mode),
        fit_mode=fit_mode,
        days=days,
        flash=_take_flash(),
    )


@bp.route("/prospects/analytics.xlsx")
def analytics_export():
    """분석 화면 그대로를 엑셀로. 회사에 보고할 때 쓴다.

    숫자만 옮겨 적히지 않게 집계 조건과 지표 정의를 같은 파일에 담는다.
    화면에서 고른 기간·기준·데이터 구분을 그대로 따른다.
    """
    data_mode = current_mode()
    fit_mode = current_fit_mode()
    days = current_days()

    data = analytics.overview(repository, data_mode, days, fit_mode)
    buffer = io.BytesIO(report.build_analytics(data, fit_mode))
    return send_file(
        buffer, as_attachment=True,
        download_name=report.analytics_filename(data_mode, days),
        mimetype="application/vnd.openxmlformats-officedocument."
                 "spreadsheetml.sheet")


# ---------------------------------------------------------------------------
# 데모 모드
# ---------------------------------------------------------------------------

@bp.route("/prospects/demo", methods=["POST"])
def demo():
    action = request.form.get("action")
    if action == "seed":
        result = seed_demo.seed(reset=True)
        session[MODE_KEY] = "demo"
        _flash("데모 후보 {}건을 만들었습니다. 실제 데이터와 분리해 집계합니다.".format(
            result["created"]), "info")
    elif action == "clear":
        seed_demo.clear_demo()
        session[MODE_KEY] = "real"
        _flash("데모 데이터를 삭제했습니다.", "info")
    return redirect(url_for("prospecting.prospect_list"))


@bp.route("/prospects/link-customer/<int:prospect_id>", methods=["POST"])
def link_customer(prospect_id):
    """명시적인 '고객사로 연결'. 이름만으로 자동 병합하지 않는다."""
    customer_id = (request.form.get("customer_id") or "").strip()
    repository.update_prospect(prospect_id, {"customer_id": customer_id or None})
    _flash("고객사와 연결했습니다. 상담을 수주로 처리하지는 않습니다.", "info")
    return redirect(url_for("prospecting.prospect_detail",
                            prospect_id=prospect_id, tab="overview"))
