# -*- coding: utf-8 -*-
"""인증서 관리 - 만료되기 전에 알아야 하는 것들.

인증서가 일정관리에 들어가 있는 이유는 하나다. **인증서는 만료된다.**
그리고 만료된 걸 선적 직전에 알면 그때는 이미 늦다.

여기서 진짜 기한은 만료일이 아니라 **갱신 착수일**이다.
할랄은 갱신 심사에 두세 달이 걸리고, ISO 22716 재심사는 실사 일정을 잡는 데만
몇 주가 든다. 만료일 D-7 에 알아차리면 인증서가 끊긴 채로 선적을 맞이한다.
그래서 `착수 권고일 = 만료일 - 준비기간` 을 따로 계산해 그날을 기한으로 본다.

인증서는 세 갈래다.
  공장·시스템  우리 공장이 받는 것. 한 번 받으면 모든 수출 건에 공통으로 쓴다
  현지 등록    파는 나라에서 제품마다 받는 것. 이게 없으면 통관이 안 된다
  수출 서류    선적할 때 붙이는 증명서. 유효기간이 짧다

지켜야 할 것:
  - 만료일을 모르면 지어내지 않는다. `만료일 미확인` 으로 두고 D-day 를 계산하지 않는다
  - 유효기간이 없는 등록(중국 비안, EU CPNP 등)을 만료 임박으로 몰지 않는다
  - 미리 넣어 둔 유효기간·준비기간은 **업계 통상값**이다. 인증기관이 정한 값이 아니다.
    화면에 그렇게 적고, 실제 인증서에 적힌 날짜로 고쳐 쓰게 한다
  - 인증서 파일을 여기 올리지 않는다. 파일명만 적어 둔다 (가안이다)
"""

import os
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    SEOUL = ZoneInfo("Asia/Seoul")
except Exception:                                    # noqa: BLE001
    SEOUL = timezone.utc

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "certs.db")

_local = threading.local()

# 만료 임박으로 볼 기간
SOON_DAYS = 60


# ---------------------------------------------------------------------------
# 갈래
# ---------------------------------------------------------------------------

KINDS = [
    {"key": "factory", "label": "공장·시스템", "icon": "🏭",
     "desc": "우리 공장·회사가 받는 인증. 건마다 다시 받지 않고 모든 수출에 공통으로 씁니다"},
    {"key": "local", "label": "현지 등록·허가", "icon": "🌍",
     "desc": "파는 나라에서 제품마다 받아야 하는 등록·허가. 이게 없으면 통관이 안 됩니다"},
    {"key": "doc", "label": "수출 서류", "icon": "📄",
     "desc": "선적할 때 붙이는 증명서. 유효기간이 짧고 발급일을 따지는 곳이 많습니다"},
]
KIND_MAP = {row["key"]: row for row in KINDS}
KIND_ORDER = [row["key"] for row in KINDS]


# ---------------------------------------------------------------------------
# 미리 넣어 둔 인증서
# ---------------------------------------------------------------------------
#   valid_months : 통상 유효기간 (0 이면 유효기간이 따로 없는 등록)
#   lead_days    : 갱신에 걸리는 기간. 만료일에서 이만큼 앞이 착수 권고일이다
#   note         : 실무에서 자주 걸리는 지점
#
#   **업계 통상값이다.** 인증기관·국가가 정한 값이 아니다.
#   실제 인증서에 적힌 날짜를 보고 고쳐 써야 한다.

CATALOG = [
    # --- 공장·시스템 ---
    {"key": "iso22716", "kind": "factory", "name": "ISO 22716 (화장품 GMP)",
     "issuer": "인증기관 (심사)", "valid_months": 36, "lead_days": 120,
     "note": "3년 주기지만 연 1회 사후심사가 따로 있습니다. 사후심사를 놓치면 인증이 정지됩니다"},
    {"key": "cgmp", "kind": "factory", "name": "CGMP (우수화장품 제조·품질관리기준)",
     "issuer": "식품의약품안전처", "valid_months": 36, "lead_days": 120,
     "note": "국내 기준입니다. 해외에서 ISO 22716 을 따로 요구하는 곳이 많습니다"},
    {"key": "iso9001", "kind": "factory", "name": "ISO 9001 (품질경영)",
     "issuer": "인증기관 (심사)", "valid_months": 36, "lead_days": 90, "note": ""},
    {"key": "iso14001", "kind": "factory", "name": "ISO 14001 (환경경영)",
     "issuer": "인증기관 (심사)", "valid_months": 36, "lead_days": 90, "note": ""},
    {"key": "halal", "kind": "factory", "name": "할랄 (HALAL)",
     "issuer": "KMF / JAKIM / MUI 등", "valid_months": 12, "lead_days": 90,
     "note": "나라마다 인정하는 인증기관이 다릅니다. 말레이시아 JAKIM 을 인도네시아가 "
             "그대로 받아주지 않습니다. 파는 나라가 인정하는 기관인지 먼저 확인하세요"},
    {"key": "vegan", "kind": "factory", "name": "비건 (V-Label / EVE)",
     "issuer": "인증기관", "valid_months": 12, "lead_days": 60,
     "note": "원료가 바뀌면 유효기간과 무관하게 다시 봐야 합니다"},
    {"key": "cosmos", "kind": "factory", "name": "COSMOS / ECOCERT (유기농)",
     "issuer": "ECOCERT 등", "valid_months": 12, "lead_days": 90,
     "note": "원료 배합비가 기준이라 처방을 바꾸면 인증도 다시 받습니다"},
    {"key": "cruelty", "kind": "factory", "name": "Leaping Bunny (동물실험 미실시)",
     "issuer": "Cruelty Free International", "valid_months": 12, "lead_days": 60, "note": ""},

    # --- 현지 등록·허가 ---
    {"key": "cn_beian", "kind": "local", "name": "중국 NMPA 비안 (일반화장품 등록)",
     "country": "중국", "issuer": "NMPA", "valid_months": 0, "lead_days": 0,
     "note": "유효기간은 따로 없지만 처방·표시가 바뀌면 변경 등록을 해야 합니다. "
             "중국 내 경내책임자(대리인)가 있어야 합니다"},
    {"key": "cn_xuke", "kind": "local", "name": "중국 NMPA 허가 (특수화장품)",
     "country": "중국", "issuer": "NMPA", "valid_months": 60, "lead_days": 180,
     "note": "자외선차단·염모·미백 등은 허가 대상입니다. 5년마다 연장 신청을 해야 하고 "
             "만료 전 30~90일 사이에만 신청을 받습니다"},
    {"key": "eu_cpnp", "kind": "local", "name": "EU CPNP 등록",
     "country": "EU", "issuer": "European Commission", "valid_months": 0, "lead_days": 0,
     "note": "유효기간은 없습니다. 다만 EU 역내 책임자(RP)가 있어야 하고 "
             "PIF 를 최신 상태로 보관해야 합니다"},
    {"key": "eu_cpsr", "kind": "local", "name": "EU CPSR (안전성 평가 보고서)",
     "country": "EU", "issuer": "안전성 평가자", "valid_months": 0, "lead_days": 60,
     "note": "처방·원료·용기가 바뀌면 다시 받아야 합니다. 날짜가 아니라 변경이 기준입니다"},
    {"key": "us_mocra_fac", "kind": "local", "name": "미국 MoCRA 시설 등록",
     "country": "미국", "issuer": "FDA", "valid_months": 24, "lead_days": 60,
     "note": "2년마다 갱신합니다. 제품 리스팅과 별개입니다"},
    {"key": "us_mocra_prd", "kind": "local", "name": "미국 MoCRA 제품 리스팅",
     "country": "미국", "issuer": "FDA", "valid_months": 12, "lead_days": 45,
     "note": "연 1회 갱신합니다. 제품이 늘면 그때그때 추가해야 합니다"},
    {"key": "jp_import", "kind": "local", "name": "일본 화장품 제조판매업 허가",
     "country": "일본", "issuer": "후생노동성 / 도도부현", "valid_months": 60, "lead_days": 120,
     "note": "수입자(일본 법인)가 가진 허가입니다. 품목별 수입 신고는 따로입니다"},
    {"key": "asean_acd", "kind": "local", "name": "아세안 ACD 통보 (Notification)",
     "country": "아세안", "issuer": "각국 보건당국", "valid_months": 36, "lead_days": 90,
     "note": "베트남·태국·인도네시아 등 나라마다 유효기간이 다릅니다 "
             "(보통 3~5년). 실제 승인서에 적힌 날짜로 고쳐 주세요"},
    {"key": "tw_tfda", "kind": "local", "name": "대만 TFDA 등록 / PIF",
     "country": "대만", "issuer": "TFDA", "valid_months": 0, "lead_days": 60, "note": ""},
    {"key": "sa_sfda", "kind": "local", "name": "사우디 SFDA 제품 등록",
     "country": "사우디", "issuer": "SFDA", "valid_months": 60, "lead_days": 120, "note": ""},
    {"key": "eac", "kind": "local", "name": "EAEU 적합성 선언 (EAC)",
     "country": "러시아·EAEU", "issuer": "인증기관", "valid_months": 60, "lead_days": 90,
     "note": "러시아·카자흐스탄 등 관세동맹 공통입니다"},

    # --- 수출 서류 ---
    {"key": "cfs", "kind": "doc", "name": "자유판매증명서 (CFS)",
     "issuer": "식품의약품안전처 / 대한화장품협회", "valid_months": 12, "lead_days": 30,
     "note": "중국 등 일부 국가는 **발급 6개월 이내** 분만 받습니다. "
             "유효기간이 남아 있어도 다시 떼야 할 수 있습니다"},
    {"key": "coa", "kind": "doc", "name": "시험성적서 (CoA)",
     "issuer": "제조사 품질팀 / 시험기관", "valid_months": 0, "lead_days": 0,
     "note": "배치(Lot)별로 나옵니다. 날짜가 아니라 생산 배치가 기준입니다"},
    {"key": "msds", "kind": "doc", "name": "물질안전보건자료 (MSDS/SDS)",
     "issuer": "제조사", "valid_months": 36, "lead_days": 30,
     "note": "처방이 바뀌면 유효기간과 무관하게 다시 만듭니다"},
    {"key": "noanimal", "kind": "doc", "name": "동물실험 미실시 선언서",
     "issuer": "제조사", "valid_months": 12, "lead_days": 30, "note": ""},
    {"key": "co", "kind": "doc", "name": "원산지증명서 (C/O)",
     "issuer": "상공회의소 / 세관", "valid_months": 0, "lead_days": 0,
     "note": "선적 건별로 뗍니다. FTA 특혜세율을 쓰려면 양식이 따로 있습니다"},
    {"key": "ingredient", "kind": "doc", "name": "전성분표 (Full Ingredient List)",
     "issuer": "제조사 연구소", "valid_months": 0, "lead_days": 0,
     "note": "INCI 명으로 적어야 합니다. 처방이 바뀌면 같이 바뀝니다"},
]
CATALOG_MAP = {row["key"]: row for row in CATALOG}


# ---------------------------------------------------------------------------
# 상태
# ---------------------------------------------------------------------------
#   담당자가 고르는 상태(STATUSES)와, 날짜에서 계산되는 상태(ALERTS)는 다르다.
#   "갱신 중" 이라고 표시해 뒀어도 만료일은 만료일이다.

STATUSES = [
    {"value": "active", "label": "보유", "css": "ok"},
    {"value": "renewing", "label": "갱신 중", "css": "warn"},
    {"value": "preparing", "label": "취득 준비 중", "css": "info"},
    {"value": "dropped", "label": "사용 안 함", "css": "off"},
]
STATUS_MAP = {row["value"]: row for row in STATUSES}

ALERTS = {
    "expired": {"label": "만료됨", "css": "expired", "rank": 0,
                "desc": "유효기간이 지났습니다. 이 인증서로는 선적할 수 없습니다"},
    "due": {"label": "갱신 착수", "css": "due", "rank": 1,
            "desc": "지금 갱신을 시작해야 만료 전에 끝납니다"},
    "soon": {"label": "만료 임박", "css": "soon", "rank": 2,
             "desc": "{}일 안에 만료됩니다".format(SOON_DAYS)},
    "nodate": {"label": "만료일 미확인", "css": "nodate", "rank": 3,
               "desc": "만료일을 적지 않아 기한을 따질 수 없습니다"},
    "preparing": {"label": "취득 준비 중", "css": "prep", "rank": 4,
                  "desc": "아직 받지 않은 인증입니다"},
    "ok": {"label": "여유", "css": "ok", "rank": 5, "desc": "아직 여유가 있습니다"},
    "perpetual": {"label": "유효기간 없음", "css": "perp", "rank": 6,
                  "desc": "기간 만료가 없는 등록입니다. 내용이 바뀔 때 갱신합니다"},
    "dropped": {"label": "사용 안 함", "css": "off", "rank": 7, "desc": ""},
}

# 챙겨야 하는 것들. 할 일 목록 위에 따로 모은다.
ACTION_ALERTS = ("expired", "due", "soon")


SCHEMA = """
CREATE TABLE IF NOT EXISTS certs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT NOT NULL DEFAULT 'factory',
    catalog_key  TEXT NOT NULL DEFAULT '',
    name         TEXT NOT NULL,
    country      TEXT NOT NULL DEFAULT '',
    scope        TEXT NOT NULL DEFAULT '',   -- 어느 공장 / 어느 제품에 걸린 인증인가
    issuer       TEXT NOT NULL DEFAULT '',
    number       TEXT NOT NULL DEFAULT '',
    issued_date  TEXT NOT NULL DEFAULT '',
    expiry_date  TEXT NOT NULL DEFAULT '',
    lead_days    INTEGER NOT NULL DEFAULT 60,
    status       TEXT NOT NULL DEFAULT 'active',
    owner        TEXT NOT NULL DEFAULT '',
    file_name    TEXT NOT NULL DEFAULT '',
    note         TEXT NOT NULL DEFAULT '',
    customer_id  TEXT NOT NULL DEFAULT '',
    is_demo      INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_certs_expiry ON certs(expiry_date);
"""


# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------

def _conn():
    conn = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        conn.commit()
        _local.conn = conn
    return conn


def init_db():
    _conn()


def today():
    return datetime.now(SEOUL).date()


def today_iso():
    return today().isoformat()


def now_iso():
    return datetime.now(SEOUL).strftime("%Y-%m-%d %H:%M:%S")


def parse_date(text):
    """YYYY-MM-DD. 못 읽으면 None (0 이나 오늘로 때우지 않는다)."""
    text = (text or "").strip()[:10]
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _clean(value, limit):
    return (str(value or "").strip())[:limit]


def add_months(day, months):
    """통상 유효기간으로 만료일을 추천한다. 추천일 뿐이다."""
    if not day or not months:
        return None
    year = day.year + (day.month - 1 + months) // 12
    month = (day.month - 1 + months) % 12 + 1
    # 2월 31일 같은 날짜가 안 나오게 그 달의 마지막 날로 맞춘다
    last = [31, 29 if (year % 4 == 0 and year % 100 != 0) or year % 400 == 0 else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(day.day, last))


def catalog_for(kind=None):
    rows = [dict(row) for row in CATALOG if not kind or row["kind"] == kind]
    for row in rows:
        row.setdefault("country", "")
    return rows


# ---------------------------------------------------------------------------
# 상태 계산
# ---------------------------------------------------------------------------

def decorate(row, ref=None):
    """인증서 한 건에 기한 정보를 붙인다.

    핵심은 `start_by` 다. 만료일이 아니라 **갱신을 시작해야 하는 날**이 기한이다.
    """
    ref = ref or today()
    item = dict(row)
    item["kind_meta"] = KIND_MAP.get(item["kind"], KIND_MAP["factory"])
    item["status_meta"] = STATUS_MAP.get(item["status"], STATUS_MAP["active"])

    expiry = parse_date(item.get("expiry_date"))
    item["expiry"] = expiry
    item["days"] = (expiry - ref).days if expiry else None

    lead = int(item.get("lead_days") or 0)
    start_by = expiry - timedelta(days=lead) if (expiry and lead) else None
    item["start_by"] = start_by.isoformat() if start_by else ""
    item["start_days"] = (start_by - ref).days if start_by else None

    if item["status"] == "dropped":
        alert = "dropped"
    elif item["status"] == "preparing":
        alert = "preparing"
    elif not expiry:
        # 유효기간이 없는 등록과, 날짜를 안 적은 것은 다르다.
        # 앞은 정상이고 뒤는 확인이 필요하다.
        catalog = CATALOG_MAP.get(item.get("catalog_key") or "")
        alert = "perpetual" if (catalog and catalog["valid_months"] == 0) else "nodate"
    elif item["days"] < 0:
        alert = "expired"
    elif start_by and ref >= start_by:
        alert = "due"
    elif item["days"] <= SOON_DAYS:
        alert = "soon"
    else:
        alert = "ok"

    item["alert"] = alert
    item["alert_meta"] = dict(ALERTS[alert], key=alert)

    if expiry is None:
        item["d_label"] = "—"
    elif item["days"] < 0:
        item["d_label"] = "D+{}".format(-item["days"])
    elif item["days"] == 0:
        item["d_label"] = "오늘"
    else:
        item["d_label"] = "D-{}".format(item["days"])

    # 화면에 적을 한 줄. 왜 지금 챙겨야 하는지가 여기 들어간다.
    if alert == "expired":
        item["why"] = "{}에 만료됐습니다. 이 인증서로는 선적할 수 없습니다.".format(
            item["expiry_date"])
    elif alert == "due":
        item["why"] = ("만료 {} · 갱신에 {}일이 걸립니다. 착수 권고일({})이 지났습니다."
                       .format(item["expiry_date"], lead, item["start_by"]))
    elif alert == "soon":
        item["why"] = "{}에 만료됩니다 ({}).".format(item["expiry_date"], item["d_label"])
    elif alert == "nodate":
        item["why"] = "만료일을 적지 않아 기한을 따질 수 없습니다. 인증서에 적힌 날짜를 넣어 주세요."
    elif alert == "perpetual":
        item["why"] = "기간 만료가 없는 등록입니다. 처방·표시가 바뀌면 변경 등록을 해야 합니다."
    elif alert == "preparing":
        item["why"] = "아직 받지 않은 인증입니다."
    else:
        item["why"] = "{}까지 유효합니다.".format(item["expiry_date"]) if expiry else ""

    catalog = CATALOG_MAP.get(item.get("catalog_key") or "")
    item["catalog_note"] = (catalog or {}).get("note", "")
    return item


def _sort_key(item):
    # 챙길 게 급한 순. 같은 등급이면 만료일이 가까운 것부터.
    return (item["alert_meta"]["rank"],
            item["days"] if item["days"] is not None else 99999,
            item["name"])


# ---------------------------------------------------------------------------
# 읽기 · 쓰기
# ---------------------------------------------------------------------------

def list_certs(kind="all", alert="all", keyword="", ref=None):
    rows = [decorate(row, ref) for row in
            _conn().execute("SELECT * FROM certs ORDER BY id DESC")]

    if kind != "all":
        rows = [r for r in rows if r["kind"] == kind]
    if alert == "action":
        rows = [r for r in rows if r["alert"] in ACTION_ALERTS]
    elif alert != "all":
        rows = [r for r in rows if r["alert"] == alert]

    keyword = (keyword or "").strip().lower()
    if keyword:
        rows = [r for r in rows if keyword in " ".join(
            str(r.get(f) or "") for f in
            ("name", "country", "scope", "issuer", "number", "note")).lower()]

    rows.sort(key=_sort_key)
    return rows


def get_cert(cert_id):
    row = _conn().execute("SELECT * FROM certs WHERE id = ?", (cert_id,)).fetchone()
    return decorate(row) if row else None


FIELDS = {
    "kind": 20, "catalog_key": 40, "name": 120, "country": 40, "scope": 160,
    "issuer": 120, "number": 80, "issued_date": 10, "expiry_date": 10,
    "status": 20, "owner": 40, "file_name": 160, "note": 500, "customer_id": 60,
}


def _payload(data):
    out = {key: _clean(data.get(key), limit) for key, limit in FIELDS.items()}
    if out["kind"] not in KIND_MAP:
        out["kind"] = "factory"
    if out["status"] not in STATUS_MAP:
        out["status"] = "active"
    # 날짜는 읽히는 것만 저장한다. 못 읽으면 비워 둔다 (오늘로 때우지 않는다)
    for key in ("issued_date", "expiry_date"):
        out[key] = out[key] if parse_date(out[key]) else ""
    try:
        lead = int(str(data.get("lead_days") or 0).strip() or 0)
    except ValueError:
        lead = 0
    out["lead_days"] = max(0, min(lead, 400))
    return out


def add_cert(data):
    out = _payload(data)
    if not out["name"]:
        return None
    cur = _conn().execute(
        "INSERT INTO certs ({}, is_demo, created_at, updated_at) "
        "VALUES ({}, ?, ?, ?)".format(
            ", ".join(out), ", ".join("?" * len(out))),
        list(out.values()) + [1 if data.get("is_demo") else 0, now_iso(), now_iso()])
    _conn().commit()
    return cur.lastrowid


def update_cert(cert_id, data):
    out = _payload(data)
    if not out["name"]:
        return False
    _conn().execute(
        "UPDATE certs SET {}, updated_at = ? WHERE id = ?".format(
            ", ".join("{} = ?".format(k) for k in out)),
        list(out.values()) + [now_iso(), cert_id])
    _conn().commit()
    return True


def set_status(cert_id, status):
    if status not in STATUS_MAP:
        return False
    _conn().execute("UPDATE certs SET status = ?, updated_at = ? WHERE id = ?",
                    (status, now_iso(), cert_id))
    _conn().commit()
    return True


def renew(cert_id, issued_date, expiry_date):
    """갱신 완료. 새 날짜로 갈아 끼우고 상태를 보유로 되돌린다."""
    issued = parse_date(issued_date)
    expiry = parse_date(expiry_date)
    if not expiry:
        return False
    _conn().execute(
        "UPDATE certs SET issued_date = ?, expiry_date = ?, status = 'active', "
        "updated_at = ? WHERE id = ?",
        (issued.isoformat() if issued else "", expiry.isoformat(), now_iso(), cert_id))
    _conn().commit()
    return True


def delete_cert(cert_id):
    _conn().execute("DELETE FROM certs WHERE id = ?", (cert_id,))
    _conn().commit()
    return True


# ---------------------------------------------------------------------------
# 일정에 섞어 보여주기
# ---------------------------------------------------------------------------

def summary(ref=None):
    rows = list_certs(ref=ref)
    counts = {}
    for row in rows:
        counts[row["alert"]] = counts.get(row["alert"], 0) + 1
    return {
        "total": len(rows),
        "counts": counts,
        "expired": counts.get("expired", 0),
        "due": counts.get("due", 0),
        "soon": counts.get("soon", 0),
        "nodate": counts.get("nodate", 0),
        # 지금 손대야 하는 건수. 일정 화면 맨 위에 띄운다
        "action": sum(counts.get(k, 0) for k in ACTION_ALERTS),
    }


def alerts(ref=None, limit=None):
    """일정 화면에 끼워 넣을 줄. 급한 것부터."""
    rows = [r for r in list_certs(ref=ref) if r["alert"] in ACTION_ALERTS]
    return rows[:limit] if limit else rows


def by_kind(ref=None):
    rows = list_certs(ref=ref)
    return [{"kind": KIND_MAP[key],
             "rows": [r for r in rows if r["kind"] == key]}
            for key in KIND_ORDER]


# ---------------------------------------------------------------------------
# 예시 데이터
# ---------------------------------------------------------------------------

DEMO = [
    # 만료가 지난 것 · 갱신을 시작해야 하는 것 · 여유 있는 것을 섞어 둔다
    ("halal", "공장 전체 (1·2공장)", "KMF-2024-0182", -400, ""),
    ("iso22716", "1공장 (스킨케어 라인)", "KR-22716-0451", -1020, ""),
    ("cgmp", "1공장", "CGMP-2025-0077", -300, ""),
    ("us_mocra_prd", "Vitamin C Brightening Serum 30ml", "", -330, "미국"),
    ("cn_beian", "Vitamin C Brightening Serum 30ml", "국妆网备진字2025...", None, "중국"),
    ("eu_cpnp", "Nuit Retinal Serum 30ml", "CPNP-2612345", None, "EU"),
    ("cfs", "Vitamin C Brightening Serum 30ml", "CFS-2026-1134", -60, ""),
    ("asean_acd", "Sunscreen SPF50+ 50ml", "", -200, "베트남"),
    ("vegan", "비건 라인 3품목", "", None, ""),
]


def seed_demo(reset=True):
    """예시 인증서. 기한이 다양하게 섞이도록 오늘을 기준으로 날짜를 만든다."""
    conn = _conn()
    if reset:
        conn.execute("DELETE FROM certs WHERE is_demo = 1")
        conn.commit()

    ref = today()
    made = 0
    for key, scope, number, issued_offset, country in DEMO:
        row = CATALOG_MAP[key]
        issued = ref + timedelta(days=issued_offset) if issued_offset is not None else None
        expiry = add_months(issued, row["valid_months"]) if issued else None
        add_cert({
            "kind": row["kind"],
            "catalog_key": key,
            "name": row["name"],
            "country": country or row.get("country", ""),
            "scope": scope,
            "issuer": row["issuer"],
            "number": number,
            "issued_date": issued.isoformat() if issued else "",
            "expiry_date": expiry.isoformat() if expiry else "",
            "lead_days": row["lead_days"],
            "status": "active",
            "owner": "품질팀",
            "note": "",
            "is_demo": True,
        })
        made += 1
    return made


def clear_demo():
    _conn().execute("DELETE FROM certs WHERE is_demo = 1")
    _conn().commit()


def has_demo():
    return bool(_conn().execute(
        "SELECT 1 FROM certs WHERE is_demo = 1 LIMIT 1").fetchone())
