# -*- coding: utf-8 -*-
"""신규 바이어 발굴 - 영업 지표 (명세 4.6).

정의:
  상담 전환율 = 선택 기간에 최초 연락한 기업 중 기준일까지 상담에 도달한 고유 기업 수
                / 해당 기간에 최초 연락한 고유 기업 수
  분모가 0이면 '계산 불가'.

실제(real)와 데모(demo)는 절대 섞지 않는다. 항상 한 쪽만 집계한다.
"""

from datetime import date, timedelta

import pandas as pd

from . import models


def _stage_frame(repository, data_mode):
    rows = repository.rows(
        "SELECT s.prospect_id, s.from_stage, s.to_stage, s.changed_at"
        " FROM stage_events s JOIN prospects p ON p.id = s.prospect_id"
        " WHERE p.data_mode = ?", (data_mode,))
    if not rows:
        return pd.DataFrame(columns=["prospect_id", "from_stage", "to_stage",
                                     "changed_at", "day", "order"])
    frame = pd.DataFrame(rows)
    frame["day"] = frame["changed_at"].str.slice(0, 10)
    frame["order"] = frame["to_stage"].map(models.STAGE_ORDER).fillna(0).astype(int)
    return frame


def _first_reach(frame, min_order):
    """기업별로 해당 단계에 처음 도달한 날짜. (고유 기업 1건)"""
    if frame.empty:
        return pd.Series(dtype="object")
    hit = frame[frame["order"] >= min_order]
    if hit.empty:
        return pd.Series(dtype="object")
    return hit.groupby("prospect_id")["day"].min()


def funnel(repository, data_mode="real", days=90):
    """기간 내 최초 연락 기업 기준 퍼널."""
    since = (models.now_seoul().date() - timedelta(days=days)).isoformat()
    frame = _stage_frame(repository, data_mode)

    first_contact = _first_reach(frame, models.CONTACTED_ORDER)
    first_meeting = _first_reach(frame, models.MEETING_ORDER)

    in_window = set(first_contact[first_contact >= since].index) if len(first_contact) else set()
    reached = {pid for pid in in_window if pid in first_meeting.index}

    replied = set()
    if not frame.empty:
        replied_series = _first_reach(frame, models.STAGE_ORDER["replied"])
        replied = {pid for pid in in_window if pid in replied_series.index}

    total = len(in_window)
    return {
        "since": since,
        "days": days,
        "contacted": total,
        "replied": len(replied),
        "meetings": len(reached),
        "rate": (len(reached) / total * 100) if total else None,
        "rate_label": ("{:.1f}%".format(len(reached) / total * 100) if total else "계산 불가"),
        "no_reply": total - len(replied),
    }


def response_days(repository, data_mode="real"):
    """최초 연락 → 최초 회신까지 걸린 일수의 중앙값."""
    frame = _stage_frame(repository, data_mode)
    contact = _first_reach(frame, models.CONTACTED_ORDER)
    reply = _first_reach(frame, models.STAGE_ORDER["replied"])
    if contact.empty:
        return {"median": None, "samples": 0, "no_reply": 0}

    pairs = []
    for pid, day in contact.items():
        if pid in reply.index:
            delta = (date.fromisoformat(reply[pid]) - date.fromisoformat(day)).days
            if delta >= 0:
                pairs.append(delta)
    return {
        "median": float(pd.Series(pairs).median()) if pairs else None,
        "samples": len(pairs),
        "no_reply": int(len(contact) - len(pairs)),
    }


def by_channel(repository, data_mode="real"):
    """발굴 경로별 후보 수 / 첫 연락 / 회신 / 상담 (고유 기업 기준)."""
    prospects = repository.rows(
        "SELECT id, IFNULL(NULLIF(source_channel,''),'미기재') AS channel"
        " FROM prospects WHERE data_mode = ?", (data_mode,))
    if not prospects:
        return []

    frame = _stage_frame(repository, data_mode)
    contacted = set(_first_reach(frame, models.CONTACTED_ORDER).index)
    replied = set(_first_reach(frame, models.STAGE_ORDER["replied"]).index)
    meetings = set(_first_reach(frame, models.MEETING_ORDER).index)

    table = pd.DataFrame(prospects)
    out = []
    for channel, group in table.groupby("channel"):
        ids = set(group["id"])
        out.append({
            "channel": channel,
            "prospects": len(ids),
            "contacted": len(ids & contacted),
            "replied": len(ids & replied),
            "meetings": len(ids & meetings),
        })
    out.sort(key=lambda row: row["prospects"], reverse=True)
    return out


def score_distribution(repository, mode="oem", data_mode="real"):
    """국가·제품군별 적합도 분포와 미확인 비중."""
    rows = repository.rows(
        "SELECT p.id, p.headquarters_country, s.fit_score, s.coverage"
        " FROM prospects p LEFT JOIN prospect_scores s"
        "   ON s.prospect_id = p.id AND s.mode = ?"
        " WHERE p.data_mode = ?", (mode, data_mode))
    if not rows:
        return {"countries": [], "unscored": 0, "insufficient": 0, "scored": 0}

    frame = pd.DataFrame(rows)
    frame["headquarters_country"] = frame["headquarters_country"].fillna("미확인").replace("", "미확인")

    countries = []
    for country, group in frame.groupby("headquarters_country"):
        scored = group["fit_score"].dropna()
        countries.append({
            "country": country,
            "count": int(len(group)),
            "scored": int(len(scored)),
            "avg_fit": float(scored.mean()) if len(scored) else None,
            "avg_coverage": float(group["coverage"].dropna().mean())
                            if group["coverage"].notna().any() else None,
        })
    countries.sort(key=lambda row: row["count"], reverse=True)

    coverage = frame["coverage"].fillna(0)
    return {
        "countries": countries,
        "unscored": int(frame["fit_score"].isna().sum()),
        "scored": int(frame["fit_score"].notna().sum()),
        "insufficient": int(((coverage < models.COVERAGE_THRESHOLD)
                             & frame["fit_score"].notna()).sum()),
    }


def recent_warning(repository, data_mode="real", days=14):
    """최근 등록 후보는 관찰기간이 짧다는 안내를 위한 건수."""
    since = (models.now_seoul().date() - timedelta(days=days)).isoformat()
    return repository.scalar(
        "SELECT COUNT(*) FROM prospects WHERE data_mode = ? AND substr(created_at,1,10) >= ?",
        (data_mode, since))


def overview(repository, data_mode="real", days=90, mode="oem"):
    today = models.today_iso()
    scores = repository.all_scores(mode)
    prospects = repository.list_prospects(data_mode)
    ids = {row["id"] for row in prospects}

    reviewable = sum(
        1 for pid in ids
        if scores.get(pid) and scores[pid]["fit_score"] is not None
        and (scores[pid]["coverage"] or 0) >= models.COVERAGE_THRESHOLD)

    followups = repository.list_followups(data_mode=data_mode)
    return {
        "data_mode": data_mode,
        "timezone": models.TIMEZONE_LABEL,
        "today": today,
        "prospects": len(ids),
        "reviewable": reviewable,
        "due_today": sum(1 for f in followups
                         if f["status"] == "open" and f["due_date"] == today),
        "overdue": sum(1 for f in followups
                       if f["status"] == "open" and f["due_date"] < today),
        "funnel": funnel(repository, data_mode, days),
        "response": response_days(repository, data_mode),
        "channels": by_channel(repository, data_mode),
        "distribution": score_distribution(repository, mode, data_mode),
        "recent": recent_warning(repository, data_mode),
    }
