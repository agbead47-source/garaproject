# -*- coding: utf-8 -*-
"""신규 바이어 발굴 - 설명 가능한 적합도 (명세 8절).

값은 일치 / 불일치 / 미확인 셋뿐이다.

    확인 가중치 = 일치 및 불일치 기준의 가중치 합
    정보 확인율 = 확인 가중치 / 전체 가중치 x 100
    적합도     = 일치 기준 가중치 합 / 확인 가중치 x 100

확인 가중치가 0이면 적합도는 None(정보 부족)이다.
수주 확률이나 구매 의향이 아니라 내부 규칙에 따른 참고값이다.
"""

import json

from . import models, pipeline


def _weight(criterion, mode):
    return models.CRITERIA_BY_KEY[criterion][mode]


def _as_list(raw):
    if not raw:
        return []
    try:
        value = json.loads(raw)
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
    except (TypeError, ValueError):
        pass
    return [part.strip() for part in str(raw).replace("\n", ",").split(",") if part.strip()]


def _requirement(requirements, field):
    for row in requirements:
        if row["field_name"] == field and (row.get("value") or "").strip():
            return row
    return None


# ---------------------------------------------------------------------------
# 기준별 판정
# ---------------------------------------------------------------------------

def _check_category(capabilities, summary, requirements):
    """고객이 파는(또는 요구한) 제품군을 우리가 만들 수 있는가."""
    ours = {c.lower() for c in _as_list(capabilities.get("product_categories"))}
    if not ours:
        return "unknown", "자사 제조 가능 제품군이 등록되지 않았습니다."

    wanted = _as_list((_requirement(requirements, "product_category") or {}).get("value"))
    observed = list((summary or {}).get("category_list") or [])
    targets = [t for t in (wanted or observed) if t and t != "other"]

    if not targets:
        return "unknown", "고객 제품군을 확인할 수 있는 제품 정보가 없습니다."

    hit = [t for t in targets if t.lower() in ours]
    source = "고객이 밝힌 요구" if wanted else "수집한 제품 {}건 관찰".format(
        (summary or {}).get("product_count", 0))
    labels = lambda keys: ", ".join(models.CATEGORY_LABELS.get(k, k) for k in keys)

    if hit:
        return "match", "{}: {} → 자사 대응 가능 ({})".format(
            source, labels(targets), labels(hit))
    return "mismatch", "{}: {} → 자사 제조 가능 목록에 없음".format(source, labels(targets))


def _check_spec(capabilities, summary, requirements, mode):
    """OEM은 확정 사양, ODM은 개발 요구 대응."""
    field = "spec" if mode == "oem" else "development_request"
    row = _requirement(requirements, field)
    if not row:
        return "unknown", ("고객의 확정 사양이 확인되지 않았습니다."
                           if mode == "oem" else
                           "고객의 개발 요구가 확인되지 않았습니다.")

    ours = " ".join(_as_list(capabilities.get("formulations"))).lower()
    if not ours:
        return "unknown", "자사 개발 가능 제형이 등록되지 않았습니다."

    wanted = (row.get("value") or "").lower()
    tokens = [t for t in wanted.replace(",", " ").split() if len(t) > 1]
    hit = [t for t in tokens if t in ours]
    if hit:
        return "match", "요구 '{}' 중 자사 제형과 겹침: {}".format(
            row["value"][:60], ", ".join(hit[:4]))
    return "mismatch", "요구 '{}' 를 자사 등록 제형에서 찾지 못했습니다.".format(row["value"][:60])


def _check_moq(capabilities, summary, requirements):
    """고객이 밝힌 주문량이 우리 MOQ 이상인가."""
    row = _requirement(requirements, "order_quantity")
    if not row:
        return "unknown", "고객이 주문량을 밝히지 않았습니다."

    quantity, _ = models.parse_amount(row.get("value"))
    if quantity is None:
        return "unknown", "주문량 '{}' 에서 숫자를 읽지 못했습니다.".format(row.get("value"))

    moq_rows = capabilities.get("moq") or []
    if not moq_rows:
        return "unknown", "자사 MOQ 가 등록되지 않았습니다."

    lowest = min((r["moq_value"] for r in moq_rows if r["moq_value"] is not None), default=None)
    if lowest is None:
        return "unknown", "자사 MOQ 값이 비어 있습니다."

    if quantity >= lowest:
        return "match", "고객 주문량 {:,.0f} ≥ 자사 최소 MOQ {:,.0f}".format(quantity, lowest)
    return "mismatch", "고객 주문량 {:,.0f} < 자사 최소 MOQ {:,.0f}".format(quantity, lowest)


def _check_certification(capabilities, summary, requirements):
    """고객이 '요구한' 인증만 본다. 요구가 없으면 미확인이다."""
    row = _requirement(requirements, "certification")
    if not row:
        return "unknown", "고객이 요구한 인증이 확인되지 않았습니다."

    wanted = [w.lower() for w in _as_list(row.get("value"))]
    ours = {(c["name"] or "").lower(): c for c in (capabilities.get("certs") or [])}
    if not ours:
        return "mismatch", "고객 요구 인증 '{}' 에 대응할 자사 인증이 등록되지 않았습니다.".format(
            row["value"][:60])

    missing = [w for w in wanted if not any(w in name for name in ours)]
    if missing:
        return "mismatch", "요구 인증 중 미보유: {}".format(", ".join(missing))

    unverified = [c["name"] for c in capabilities["certs"] if not c["internally_verified"]]
    note = "요구 인증 {} 보유".format(", ".join(wanted))
    if unverified:
        note += " (내부 확인 안 된 인증 있음: {})".format(", ".join(unverified[:3]))
    return "match", note


def _check_lead_time(capabilities, summary, requirements):
    row = _requirement(requirements, "lead_time")
    if not row:
        return "unknown", "고객이 납기를 밝히지 않았습니다."

    wanted, _ = models.parse_amount(row.get("value"))
    ours, _ = models.parse_amount(capabilities.get("mass_lead_time"))
    if wanted is None or ours is None:
        return "unknown", "납기 값을 숫자로 읽지 못했습니다. (고객 '{}' / 자사 '{}')".format(
            row.get("value"), capabilities.get("mass_lead_time"))

    if ours <= wanted:
        return "match", "자사 통상 납기 {:.0f} ≤ 고객 요구 {:.0f}".format(ours, wanted)
    return "mismatch", "자사 통상 납기 {:.0f} > 고객 요구 {:.0f}".format(ours, wanted)


_CHECKERS = {
    "category": lambda cap, sm, req, mode: _check_category(cap, sm, req),
    "spec": _check_spec,
    "moq": lambda cap, sm, req, mode: _check_moq(cap, sm, req),
    "certification": lambda cap, sm, req, mode: _check_certification(cap, sm, req),
    "lead_time": lambda cap, sm, req, mode: _check_lead_time(cap, sm, req),
}


# ---------------------------------------------------------------------------
# 점수
# ---------------------------------------------------------------------------

def evaluate(capabilities, summary, requirements, mode):
    """기준별 판정과 점수를 함께 돌려준다."""
    capabilities = capabilities or {}
    checks = []

    for criterion in models.CRITERIA:
        key = criterion["key"]
        weight = criterion[mode]
        if not capabilities:
            outcome, evidence = "unknown", "자사 역량이 등록되지 않았습니다."
        else:
            outcome, evidence = _CHECKERS[key](capabilities, summary, requirements, mode)
        checks.append({
            "criterion": key,
            "label": criterion["label"],
            "hint": criterion["hint"],
            "outcome": outcome,
            "weight": weight,
            "evidence": evidence,
        })

    total_weight = sum(c["weight"] for c in checks)
    confirmed = sum(c["weight"] for c in checks if c["outcome"] in ("match", "mismatch"))
    matched = sum(c["weight"] for c in checks if c["outcome"] == "match")

    coverage = (confirmed / total_weight * 100) if total_weight else 0.0
    fit_score = (matched / confirmed * 100) if confirmed else None

    blocking = [c for c in checks
                if c["outcome"] == "mismatch" and c["criterion"] in models.BLOCKING_CRITERIA]

    if fit_score is None:
        reason = "확인된 기준이 없어 점수를 낼 수 없습니다 (정보 부족)."
    else:
        hits = [c["label"] for c in checks if c["outcome"] == "match"]
        reason = "일치 {}개: {}".format(len(hits), ", ".join(hits)) if hits else "일치 기준 없음"
        if blocking:
            reason += " · 필수조건 불일치: {}".format(
                ", ".join(c["label"] for c in blocking))

    score = {
        "fit_score": fit_score,
        "coverage": round(coverage, 1),
        "blocking": bool(blocking),
        "blocking_labels": [c["label"] for c in blocking],
        "reason": reason,
        "insufficient": coverage < models.COVERAGE_THRESHOLD,
        "rule_version": models.RULE_VERSION,
        "total_weight": total_weight,
        "confirmed_weight": confirmed,
        "matched_weight": matched,
    }
    return checks, score


def sort_key(row):
    """기본 순위: 필수조건 충돌 없음 → 확인율 기준 충족 → 적합도 → 확인율.

    점수 미산출 기업은 숫자 점수 뒤로 보낸다.
    """
    score = row.get("score") or {}
    has_score = score.get("fit_score") is not None
    return (
        1 if score.get("blocking") else 0,
        0 if (has_score and not score.get("insufficient")) else 1,
        -(score.get("fit_score") or 0),
        -(score.get("coverage") or 0),
    )


def rescore_prospect(repository, prospect_id, mode):
    """한 후보를 다시 채점하고 DB에 저장한다."""
    capabilities = repository.get_capabilities()
    products = repository.list_products(prospect_id)
    summary = pipeline.aggregate_products(
        [dict(p, prospect_id=prospect_id) for p in products]).get(prospect_id, {})
    requirements = repository.list_requirements(prospect_id)

    checks, score = evaluate(capabilities, summary, requirements, mode)
    repository.save_checks(prospect_id, mode, checks, score)
    return checks, score
