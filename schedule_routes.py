# -*- coding: utf-8 -*-
"""일정관리 화면 (Blueprint).

흐름상 '개발요청을 넣은 뒤 ~ 고객사 관리로 넘어가기 전'을 담당한다.
값이 실제로 바뀌므로(SQLite) 상태 변경 요청에는 세션 CSRF 토큰을 건다.
"""

import secrets

from flask import (Blueprint, abort, redirect, render_template, request,
                   session, url_for)

import schedule_store as store

bp = Blueprint("schedule", __name__)

CSRF_KEY = "schedule_csrf"
VIEWS = [
    {"value": "agenda", "label": "할 일"},
    {"value": "timeline", "label": "타임라인"},
    {"value": "calendar", "label": "캘린더"},
]
VIEW_KEYS = {row["value"] for row in VIEWS}


def csrf_token():
    token = session.get(CSRF_KEY)
    if not token:
        token = secrets.token_urlsafe(24)
        session[CSRF_KEY] = token
    return token


@bp.before_request
def guard():
    store.init_db()
    if request.method == "POST":
        sent = request.form.get("csrf_token")
        if not sent or sent != session.get(CSRF_KEY):
            abort(400, "요청 토큰이 올바르지 않습니다. 화면을 새로고침한 뒤 다시 시도해 주세요.")
    return None


@bp.context_processor
def inject():
    return {
        "csrf_token": csrf_token(),
        "S": store,
        "timezone_label": store.TIMEZONE_LABEL,
        "today": store.today_iso(),
    }


def _flash(message, level="info"):
    session["schedule_flash"] = {"message": message, "level": level}


def _take_flash():
    return session.pop("schedule_flash", None)


def _back(project_id=None):
    nxt = request.form.get("next")
    # 우리 화면 안으로만 돌아간다 ('//host' 같은 외부 주소는 받지 않는다)
    if nxt and nxt.startswith("/") and not nxt.startswith("//"):
        return redirect(nxt)
    if project_id:
        return redirect(url_for("schedule.detail", project_id=project_id))
    return redirect(url_for("schedule.board"))


# ---------------------------------------------------------------------------
# 목록 (할 일 / 타임라인 / 캘린더)
# ---------------------------------------------------------------------------

@bp.route("/schedule")
def board():
    view = request.args.get("view", "agenda")
    if view not in VIEW_KEYS:
        view = "agenda"
    status = request.args.get("status", "active")
    owner = request.args.get("owner", "all")
    keyword = request.args.get("q", "")

    views = store.board(status=status, owner=owner, keyword=keyword)

    data = {}
    if view == "agenda":
        data["agenda"] = store.agenda(days=14)
    elif view == "timeline":
        data["timeline"] = store.timeline(views)
    else:
        year = request.args.get("year", type=int)
        month = request.args.get("month", type=int)
        data["calendar"] = store.calendar_month(year, month)

    return render_template(
        "schedule/board.html",
        page_title="일정관리",
        active_menu="schedule",
        view=view,
        views=VIEWS,
        projects=views,
        summary=store.summary(),
        data=data,
        selected={"status": status, "owner": owner, "q": keyword},
        flash=_take_flash(),
    )


# ---------------------------------------------------------------------------
# 건 등록
# ---------------------------------------------------------------------------

@bp.route("/schedule/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        if not title:
            _flash("제품명을 입력해 주세요.", "error")
            return redirect(url_for("schedule.new"))

        project_id = store.create_project({
            "title": title,
            "account": request.form.get("account"),
            "account_kind": request.form.get("account_kind"),
            "country": request.form.get("country"),
            "owner": request.form.get("owner"),
            "start_date": request.form.get("start_date"),
            "pace": request.form.get("pace"),
            "note": request.form.get("note"),
            "origin": request.form.get("origin") or "manual",
            "prospect_id": request.form.get("prospect_id", type=int),
            "customer_id": request.form.get("customer_id"),
        }, with_tasks=request.form.get("with_tasks") != "0")
        _flash("일정을 만들었습니다. 날짜는 단계별로 바꿀 수 있습니다.", "success")
        return redirect(url_for("schedule.detail", project_id=project_id))

    start = store.parse_date(request.args.get("start"), store.today())
    pace = request.args.get("pace") if request.args.get("pace") in store.PACE_MAP else "standard"
    prefill = {
        "title": request.args.get("title", ""),
        "account": request.args.get("account", ""),
        "account_kind": request.args.get("kind", "customer"),
        "country": request.args.get("country", ""),
        "owner": request.args.get("owner", ""),
        "note": request.args.get("note", ""),
        "start_date": start.isoformat(),
        "pace": pace,
        "origin": request.args.get("origin", "manual"),
        "prospect_id": request.args.get("prospect_id", ""),
        "customer_id": request.args.get("customer_id", ""),
    }
    if prefill["account_kind"] not in store.ACCOUNT_KIND_LABELS:
        prefill["account_kind"] = "customer"

    return render_template(
        "schedule/new.html",
        page_title="일정 등록",
        active_menu="schedule",
        prefill=prefill,
        plan=store.default_plan(start, pace),
        came_from=request.args.get("origin"),
        flash=_take_flash(),
    )


# ---------------------------------------------------------------------------
# 건 상세
# ---------------------------------------------------------------------------

@bp.route("/schedule/<int:project_id>")
def detail(project_id):
    project = store.get_project(project_id)
    if project is None:
        return redirect(url_for("schedule.board"))

    view = store.project_view(project)
    return render_template(
        "schedule/detail.html",
        page_title=project["title"],
        active_menu="schedule",
        p=view,
        flash=_take_flash(),
    )


@bp.route("/schedule/<int:project_id>/edit", methods=["POST"])
def edit(project_id):
    store.update_project(project_id, {
        "title": request.form.get("title"),
        "account": request.form.get("account"),
        "account_kind": request.form.get("account_kind"),
        "country": request.form.get("country"),
        "owner": request.form.get("owner"),
        "note": request.form.get("note"),
    })
    _flash("건 정보를 저장했습니다.", "success")
    return _back(project_id)


@bp.route("/schedule/<int:project_id>/status", methods=["POST"])
def status(project_id):
    store.set_status(project_id, request.form.get("status", ""))
    return _back(project_id)


@bp.route("/schedule/<int:project_id>/delete", methods=["POST"])
def delete(project_id):
    store.delete_project(project_id)
    _flash("건과 일정을 삭제했습니다.", "success")
    return redirect(url_for("schedule.board"))


# ---------------------------------------------------------------------------
# 일정(할 일)
# ---------------------------------------------------------------------------

@bp.route("/schedule/<int:project_id>/tasks", methods=["POST"])
def task_add(project_id):
    if store.get_project(project_id) is None:
        return redirect(url_for("schedule.board"))
    store.add_task(project_id, {
        "phase": request.form.get("phase"),
        "title": request.form.get("title"),
        "owner": request.form.get("owner"),
        "plan_date": request.form.get("plan_date"),
        "note": request.form.get("note"),
    })
    return _back(project_id)


@bp.route("/schedule/tasks/<int:task_id>/done", methods=["POST"])
def task_done(task_id):
    task = store.get_task(task_id)
    if task is None:
        return _back()
    store.complete_task(task_id, request.form.get("done_date"))
    return _back(task["project_id"])


@bp.route("/schedule/tasks/<int:task_id>/reopen", methods=["POST"])
def task_reopen(task_id):
    task = store.get_task(task_id)
    if task is None:
        return _back()
    store.reopen_task(task_id)
    return _back(task["project_id"])


@bp.route("/schedule/tasks/<int:task_id>/reschedule", methods=["POST"])
def task_reschedule(task_id):
    task = store.get_task(task_id)
    if task is None:
        return _back()

    new_date = request.form.get("plan_date", "")
    plan = store.parse_date(new_date)
    if plan is None:
        _flash("날짜 형식(YYYY-MM-DD)을 확인해 주세요.", "error")
        return _back(task["project_id"])

    old = store.parse_date(task["plan_date"], plan)
    shift = (plan - old).days
    store.reschedule_task(task_id, new_date)

    if request.form.get("cascade") == "1" and shift:
        moved = store.shift_from(task_id, shift)
        if moved:
            _flash("이후 단계 {}건도 {:+d}일 함께 옮겼습니다.".format(moved, shift), "info")
    return _back(task["project_id"])


@bp.route("/schedule/tasks/<int:task_id>/delete", methods=["POST"])
def task_delete(task_id):
    task = store.get_task(task_id)
    if task is None:
        return _back()
    store.delete_task(task_id)
    return _back(task["project_id"])


# ---------------------------------------------------------------------------
# 예시 데이터
# ---------------------------------------------------------------------------

@bp.route("/schedule/demo", methods=["POST"])
def demo():
    if request.form.get("action") == "clear":
        removed = store.clear_demo()
        _flash("예시 건 {}개를 지웠습니다.".format(removed), "success")
    else:
        made = store.seed_demo(reset=True)
        _flash("예시 건 {}개를 넣었습니다. 실제 건이 아니라 화면 확인용입니다.".format(made),
               "info")
    return redirect(url_for("schedule.board"))
