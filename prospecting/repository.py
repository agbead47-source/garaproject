# -*- coding: utf-8 -*-
"""신규 바이어 발굴 - SQLite 저장소.

모든 쿼리는 매개변수화한다. 스키마는 명세 6절을 따른다.
data_mode(real/demo)는 모든 조회에서 분리할 수 있어야 한다.
"""

import os
import sqlite3
import threading

from . import models

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "prospecting.db")

_local = threading.local()

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS prospects (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name         TEXT NOT NULL,
    brand_name           TEXT,
    canonical_domain     TEXT,
    headquarters_country TEXT,
    sales_country        TEXT,
    business_type        TEXT NOT NULL DEFAULT 'unknown',
    official_url         TEXT,
    contact_url          TEXT,
    source_channel       TEXT,
    stage                TEXT NOT NULL DEFAULT 'discovered',
    owner                TEXT,
    data_mode            TEXT NOT NULL DEFAULT 'real',
    notes                TEXT,
    hold_reason          TEXT,
    review_date          TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    customer_id          TEXT
);

CREATE TABLE IF NOT EXISTS sources (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    url                TEXT NOT NULL,
    source_type        TEXT,
    access_review_date TEXT,
    collection_allowed TEXT NOT NULL DEFAULT 'unknown',
    evidence_excerpt   TEXT,
    retrieved_at       TEXT,
    content_hash       TEXT,
    note               TEXT
);

CREATE TABLE IF NOT EXISTS collection_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id     INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    prospect_id   INTEGER REFERENCES prospects(id) ON DELETE CASCADE,
    started_at    TEXT,
    finished_at   TEXT,
    status        TEXT,
    record_count  INTEGER DEFAULT 0,
    error_summary TEXT
);

CREATE TABLE IF NOT EXISTS products (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id      INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    product_name     TEXT NOT NULL,
    product_category TEXT,
    size_value       REAL,
    size_unit        TEXT,
    retail_price     REAL,
    currency         TEXT,
    source_url       TEXT,
    collected_at     TEXT,
    source_id        INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    raw_price        TEXT,
    raw_size         TEXT
);

CREATE TABLE IF NOT EXISTS product_ingredients (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    inci_name  TEXT,
    raw_name   TEXT
);

CREATE TABLE IF NOT EXISTS product_claims (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    claim      TEXT
);

CREATE TABLE IF NOT EXISTS requirements (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id         INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    field_name          TEXT NOT NULL,
    value               TEXT,
    unit                TEXT,
    source_id           INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    verified_at         TEXT,
    note                TEXT
);

CREATE TABLE IF NOT EXISTS capability_checks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    mode        TEXT NOT NULL,
    criterion   TEXT NOT NULL,
    outcome     TEXT NOT NULL,
    weight      INTEGER NOT NULL,
    evidence    TEXT,
    scored_at   TEXT,
    rule_version TEXT
);

CREATE TABLE IF NOT EXISTS prospect_scores (
    prospect_id  INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    mode         TEXT NOT NULL,
    fit_score    REAL,
    coverage     REAL,
    blocking     INTEGER NOT NULL DEFAULT 0,
    reason       TEXT,
    scored_at    TEXT,
    rule_version TEXT,
    PRIMARY KEY (prospect_id, mode)
);

CREATE TABLE IF NOT EXISTS proposals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id   INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    mode          TEXT NOT NULL,
    language      TEXT NOT NULL,
    hypothesis    TEXT,
    subject       TEXT,
    body          TEXT,
    review_status TEXT NOT NULL DEFAULT 'draft',
    created_at    TEXT,
    updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS interactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    occurred_at TEXT NOT NULL,
    channel     TEXT,
    direction   TEXT,
    summary     TEXT,
    outcome     TEXT,
    owner       TEXT
);

CREATE TABLE IF NOT EXISTS followups (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id    INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    interaction_id INTEGER REFERENCES interactions(id) ON DELETE SET NULL,
    due_date       TEXT NOT NULL,
    task           TEXT NOT NULL,
    owner          TEXT,
    status         TEXT NOT NULL DEFAULT 'open',
    completed_at   TEXT
);

CREATE TABLE IF NOT EXISTS stage_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    from_stage  TEXT,
    to_stage    TEXT NOT NULL,
    changed_at  TEXT NOT NULL,
    reason      TEXT
);

CREATE TABLE IF NOT EXISTS capabilities (
    id                 INTEGER PRIMARY KEY CHECK (id = 1),
    mode               TEXT NOT NULL DEFAULT 'both',
    product_categories TEXT,
    formulations       TEXT,
    countries          TEXT,
    regulatory_support TEXT,
    sample_lead_time   TEXT,
    mass_lead_time     TEXT,
    lead_time_note     TEXT,
    contact_person     TEXT,
    updated_at         TEXT
);

CREATE TABLE IF NOT EXISTS capability_moq (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    product_category TEXT NOT NULL,
    moq_value        REAL,
    moq_unit         TEXT
);

CREATE TABLE IF NOT EXISTS capability_certs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    scope               TEXT,
    valid_until         TEXT,
    internally_verified INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_prospects_mode ON prospects(data_mode);
CREATE INDEX IF NOT EXISTS idx_prospects_domain ON prospects(canonical_domain);
CREATE INDEX IF NOT EXISTS idx_products_prospect ON products(prospect_id);
CREATE INDEX IF NOT EXISTS idx_products_srcurl ON products(prospect_id, source_url);
CREATE INDEX IF NOT EXISTS idx_interactions_prospect ON interactions(prospect_id);
CREATE INDEX IF NOT EXISTS idx_followups_due ON followups(status, due_date);
CREATE INDEX IF NOT EXISTS idx_stage_events_prospect ON stage_events(prospect_id);
"""


def connect():
    """스레드별 커넥션. Flask 개발 서버가 멀티스레드라 분리한다."""
    con = getattr(_local, "con", None)
    if con is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        con = sqlite3.connect(DB_PATH, check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        _local.con = con
    return con


def init_db():
    con = connect()
    con.executescript(SCHEMA)
    con.commit()
    return con


def rows(sql, params=()):
    return [dict(r) for r in connect().execute(sql, params).fetchall()]


def one(sql, params=()):
    row = connect().execute(sql, params).fetchone()
    return dict(row) if row else None


def run(sql, params=()):
    con = connect()
    cur = con.execute(sql, params)
    con.commit()
    return cur


def scalar(sql, params=(), default=0):
    row = connect().execute(sql, params).fetchone()
    return (row[0] if row and row[0] is not None else default)


# ---------------------------------------------------------------------------
# 후보 기업
# ---------------------------------------------------------------------------

_PROSPECT_FIELDS = [
    "company_name", "brand_name", "canonical_domain", "headquarters_country",
    "sales_country", "business_type", "official_url", "contact_url",
    "source_channel", "stage", "owner", "data_mode", "notes",
    "hold_reason", "review_date", "customer_id",
]


def create_prospect(data):
    payload = {key: data.get(key) for key in _PROSPECT_FIELDS}
    payload["company_name"] = models.clean_text(payload.get("company_name"), 200)
    payload["canonical_domain"] = models.canonical_domain(
        payload.get("canonical_domain") or payload.get("official_url"))
    payload["business_type"] = payload.get("business_type") or "unknown"
    payload["stage"] = payload.get("stage") or "discovered"
    payload["data_mode"] = payload.get("data_mode") or "real"
    stamp = models.now_iso()

    columns = _PROSPECT_FIELDS + ["created_at", "updated_at"]
    values = [payload[key] for key in _PROSPECT_FIELDS] + [stamp, stamp]
    cur = run(
        "INSERT INTO prospects ({}) VALUES ({})".format(
            ", ".join(columns), ", ".join("?" * len(columns))),
        values,
    )
    prospect_id = cur.lastrowid
    add_stage_event(prospect_id, None, payload["stage"], "등록")
    return prospect_id


def update_prospect(prospect_id, data):
    fields = [key for key in _PROSPECT_FIELDS if key in data]
    if not fields:
        return
    if "canonical_domain" in fields or "official_url" in data:
        data = dict(data)
        data["canonical_domain"] = models.canonical_domain(
            data.get("canonical_domain") or data.get("official_url"))
        if "canonical_domain" not in fields:
            fields.append("canonical_domain")

    sets = ", ".join("{} = ?".format(key) for key in fields)
    values = [data.get(key) for key in fields] + [models.now_iso(), prospect_id]
    run("UPDATE prospects SET {}, updated_at = ? WHERE id = ?".format(sets), values)


def delete_prospect(prospect_id):
    run("DELETE FROM prospects WHERE id = ?", (prospect_id,))


def get_prospect(prospect_id):
    return one("SELECT * FROM prospects WHERE id = ?", (prospect_id,))


def list_prospects(data_mode="real", **filters):
    sql = "SELECT * FROM prospects WHERE 1=1"
    params = []
    if data_mode in ("real", "demo"):
        sql += " AND data_mode = ?"
        params.append(data_mode)

    keyword = (filters.get("q") or "").strip()
    if keyword:
        sql += (" AND (company_name LIKE ? OR IFNULL(brand_name,'') LIKE ?"
                " OR IFNULL(canonical_domain,'') LIKE ?)")
        like = "%{}%".format(keyword)
        params += [like, like, like]

    for column, key in (("headquarters_country", "hq"), ("sales_country", "market"),
                        ("business_type", "btype"), ("stage", "stage"),
                        ("owner", "owner")):
        value = filters.get(key)
        if value and value != "all":
            sql += " AND {} = ?".format(column)
            params.append(value)

    sql += " ORDER BY updated_at DESC"
    return rows(sql, params)


def find_by_domain(domain, data_mode="real"):
    domain = models.canonical_domain(domain)
    if not domain:
        return []
    return rows(
        "SELECT * FROM prospects WHERE canonical_domain = ? AND data_mode = ?",
        (domain, data_mode))


def find_similar_names(name, data_mode="real"):
    """이름이 비슷한 후보. 자동 병합하지 않고 '중복 후보'로만 보여준다."""
    key = models.clean_text(name, 60).lower()
    if len(key) < 3:
        return []
    return rows(
        "SELECT * FROM prospects WHERE data_mode = ? AND LOWER(company_name) LIKE ?",
        (data_mode, "%{}%".format(key)))


# ---------------------------------------------------------------------------
# 단계 이력
# ---------------------------------------------------------------------------

def add_stage_event(prospect_id, from_stage, to_stage, reason=""):
    run("INSERT INTO stage_events (prospect_id, from_stage, to_stage, changed_at, reason)"
        " VALUES (?,?,?,?,?)",
        (prospect_id, from_stage, to_stage, models.now_iso(), reason))


def change_stage(prospect_id, to_stage, reason=""):
    current = get_prospect(prospect_id)
    if not current or current["stage"] == to_stage:
        return False
    run("UPDATE prospects SET stage = ?, updated_at = ? WHERE id = ?",
        (to_stage, models.now_iso(), prospect_id))
    add_stage_event(prospect_id, current["stage"], to_stage, reason)
    return True


def stage_events(prospect_id):
    return rows("SELECT * FROM stage_events WHERE prospect_id = ? ORDER BY changed_at DESC",
                (prospect_id,))


# ---------------------------------------------------------------------------
# 제품
# ---------------------------------------------------------------------------

def upsert_product(prospect_id, data):
    """같은 후보 + 같은 제품 URL 이면 갱신한다. (재수집 시 중복 증가 방지)"""
    source_url = data.get("source_url") or ""
    existing = None
    if source_url:
        existing = one(
            "SELECT id FROM products WHERE prospect_id = ? AND IFNULL(source_url,'') = ?",
            (prospect_id, source_url))
    else:
        existing = one(
            "SELECT id FROM products WHERE prospect_id = ? AND product_name = ?"
            " AND IFNULL(source_url,'') = ''",
            (prospect_id, data.get("product_name")))

    columns = ["product_name", "product_category", "size_value", "size_unit",
               "retail_price", "currency", "source_url", "collected_at",
               "source_id", "raw_price", "raw_size"]
    values = [data.get(key) for key in columns]

    if existing:
        sets = ", ".join("{} = ?".format(key) for key in columns)
        run("UPDATE products SET {} WHERE id = ?".format(sets), values + [existing["id"]])
        return existing["id"], False

    cur = run("INSERT INTO products (prospect_id, {}) VALUES ({})".format(
        ", ".join(columns), ", ".join("?" * (len(columns) + 1))),
        [prospect_id] + values)
    return cur.lastrowid, True


def replace_product_ingredients(product_id, names):
    run("DELETE FROM product_ingredients WHERE product_id = ?", (product_id,))
    for raw in names:
        run("INSERT INTO product_ingredients (product_id, inci_name, raw_name) VALUES (?,?,?)",
            (product_id, models.clean_text(raw, 120), raw))


def replace_product_claims(product_id, claims):
    run("DELETE FROM product_claims WHERE product_id = ?", (product_id,))
    for claim in claims:
        run("INSERT INTO product_claims (product_id, claim) VALUES (?,?)",
            (product_id, models.clean_text(claim, 120)))


def list_products(prospect_id):
    items = rows("SELECT * FROM products WHERE prospect_id = ? ORDER BY product_name",
                 (prospect_id,))
    for item in items:
        item["ingredients"] = [r["inci_name"] for r in rows(
            "SELECT inci_name FROM product_ingredients WHERE product_id = ?", (item["id"],))]
        item["claims"] = [r["claim"] for r in rows(
            "SELECT claim FROM product_claims WHERE product_id = ?", (item["id"],))]
    return items


def all_products(data_mode="real"):
    return rows(
        "SELECT p.*, pr.company_name, pr.canonical_domain, pr.headquarters_country,"
        "       pr.sales_country, pr.data_mode"
        " FROM products p JOIN prospects pr ON pr.id = p.prospect_id"
        " WHERE pr.data_mode = ?", (data_mode,))


# ---------------------------------------------------------------------------
# 고객 요구 / 점수
# ---------------------------------------------------------------------------

def list_requirements(prospect_id):
    return rows("SELECT * FROM requirements WHERE prospect_id = ? ORDER BY field_name",
                (prospect_id,))


def add_requirement(prospect_id, field_name, value, unit="", status="unverified", note=""):
    run("INSERT INTO requirements (prospect_id, field_name, value, unit,"
        " verification_status, verified_at, note) VALUES (?,?,?,?,?,?,?)",
        (prospect_id, field_name, value, unit, status,
         models.now_iso() if status == "verified" else None, note))


def delete_requirement(req_id):
    run("DELETE FROM requirements WHERE id = ?", (req_id,))


def save_checks(prospect_id, mode, checks, score):
    run("DELETE FROM capability_checks WHERE prospect_id = ? AND mode = ?",
        (prospect_id, mode))
    stamp = models.now_iso()
    for check in checks:
        run("INSERT INTO capability_checks (prospect_id, mode, criterion, outcome,"
            " weight, evidence, scored_at, rule_version) VALUES (?,?,?,?,?,?,?,?)",
            (prospect_id, mode, check["criterion"], check["outcome"], check["weight"],
             check["evidence"], stamp, models.RULE_VERSION))

    run("INSERT INTO prospect_scores (prospect_id, mode, fit_score, coverage, blocking,"
        " reason, scored_at, rule_version) VALUES (?,?,?,?,?,?,?,?)"
        " ON CONFLICT(prospect_id, mode) DO UPDATE SET"
        " fit_score=excluded.fit_score, coverage=excluded.coverage,"
        " blocking=excluded.blocking, reason=excluded.reason,"
        " scored_at=excluded.scored_at, rule_version=excluded.rule_version",
        (prospect_id, mode, score["fit_score"], score["coverage"],
         1 if score["blocking"] else 0, score["reason"], stamp, models.RULE_VERSION))


def get_score(prospect_id, mode):
    return one("SELECT * FROM prospect_scores WHERE prospect_id = ? AND mode = ?",
               (prospect_id, mode))


def get_checks(prospect_id, mode):
    return rows("SELECT * FROM capability_checks WHERE prospect_id = ? AND mode = ?"
                " ORDER BY id", (prospect_id, mode))


def all_scores(mode):
    return {row["prospect_id"]: row for row in
            rows("SELECT * FROM prospect_scores WHERE mode = ?", (mode,))}


# ---------------------------------------------------------------------------
# 자사 역량
# ---------------------------------------------------------------------------

def get_capabilities():
    row = one("SELECT * FROM capabilities WHERE id = 1")
    if not row:
        return None
    row["moq"] = rows("SELECT * FROM capability_moq ORDER BY product_category")
    row["certs"] = rows("SELECT * FROM capability_certs ORDER BY name")
    return row


def save_capabilities(data, moq_rows, cert_rows):
    columns = ["mode", "product_categories", "formulations", "countries",
               "regulatory_support", "sample_lead_time", "mass_lead_time",
               "lead_time_note", "contact_person"]
    values = [data.get(key) for key in columns] + [models.now_iso()]
    run("INSERT INTO capabilities (id, {}, updated_at) VALUES (1, {}, ?)"
        " ON CONFLICT(id) DO UPDATE SET {}, updated_at = excluded.updated_at".format(
            ", ".join(columns), ", ".join("?" * len(columns)),
            ", ".join("{0} = excluded.{0}".format(key) for key in columns)),
        values)

    run("DELETE FROM capability_moq")
    for row in moq_rows:
        run("INSERT INTO capability_moq (product_category, moq_value, moq_unit)"
            " VALUES (?,?,?)", (row["product_category"], row["moq_value"], row["moq_unit"]))

    run("DELETE FROM capability_certs")
    for row in cert_rows:
        run("INSERT INTO capability_certs (name, scope, valid_until, internally_verified)"
            " VALUES (?,?,?,?)",
            (row["name"], row["scope"], row["valid_until"],
             1 if row["internally_verified"] else 0))


# ---------------------------------------------------------------------------
# 제안 / 연락 / 후속
# ---------------------------------------------------------------------------

def save_proposal(prospect_id, mode, language, hypothesis, subject, body, review_status):
    stamp = models.now_iso()
    existing = one("SELECT id FROM proposals WHERE prospect_id = ? AND mode = ? AND language = ?",
                   (prospect_id, mode, language))
    if existing:
        run("UPDATE proposals SET hypothesis=?, subject=?, body=?, review_status=?,"
            " updated_at=? WHERE id=?",
            (hypothesis, subject, body, review_status, stamp, existing["id"]))
        return existing["id"]
    cur = run("INSERT INTO proposals (prospect_id, mode, language, hypothesis, subject,"
              " body, review_status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
              (prospect_id, mode, language, hypothesis, subject, body, review_status,
               stamp, stamp))
    return cur.lastrowid


def get_proposal(prospect_id, mode, language):
    return one("SELECT * FROM proposals WHERE prospect_id = ? AND mode = ? AND language = ?",
               (prospect_id, mode, language))


def list_proposals(prospect_id):
    return rows("SELECT * FROM proposals WHERE prospect_id = ? ORDER BY updated_at DESC",
                (prospect_id,))


def add_interaction(prospect_id, data):
    cur = run("INSERT INTO interactions (prospect_id, occurred_at, channel, direction,"
              " summary, outcome, owner) VALUES (?,?,?,?,?,?,?)",
              (prospect_id, data.get("occurred_at"), data.get("channel"),
               data.get("direction"), data.get("summary"), data.get("outcome"),
               data.get("owner")))
    return cur.lastrowid


def list_interactions(prospect_id):
    return rows("SELECT * FROM interactions WHERE prospect_id = ? ORDER BY occurred_at DESC",
                (prospect_id,))


def add_followup(prospect_id, due_date, task, owner, interaction_id=None):
    cur = run("INSERT INTO followups (prospect_id, interaction_id, due_date, task, owner)"
              " VALUES (?,?,?,?,?)", (prospect_id, interaction_id, due_date, task, owner))
    return cur.lastrowid


def complete_followup(followup_id):
    run("UPDATE followups SET status='done', completed_at=? WHERE id=?",
        (models.now_iso(), followup_id))


def reschedule_followup(followup_id, due_date):
    run("UPDATE followups SET due_date=?, status='open', completed_at=NULL WHERE id=?",
        (due_date, followup_id))


def list_followups(prospect_id=None, data_mode="real"):
    sql = ("SELECT f.*, p.company_name, p.data_mode, p.stage FROM followups f"
           " JOIN prospects p ON p.id = f.prospect_id WHERE 1=1")
    params = []
    if data_mode in ("real", "demo"):
        sql += " AND p.data_mode = ?"
        params.append(data_mode)
    if prospect_id:
        sql += " AND f.prospect_id = ?"
        params.append(prospect_id)
    sql += " ORDER BY f.status, f.due_date"
    return rows(sql, params)


# ---------------------------------------------------------------------------
# 수집원 / 실행 기록
# ---------------------------------------------------------------------------

def add_source(url, source_type, allowed, evidence, note=""):
    cur = run("INSERT INTO sources (url, source_type, access_review_date,"
              " collection_allowed, evidence_excerpt, note) VALUES (?,?,?,?,?,?)",
              (url, source_type, models.today_iso(), allowed, evidence, note))
    return cur.lastrowid


def list_sources():
    return rows("SELECT * FROM sources ORDER BY id DESC")


def get_source(source_id):
    return one("SELECT * FROM sources WHERE id = ?", (source_id,))


def touch_source(source_id, content_hash):
    run("UPDATE sources SET retrieved_at = ?, content_hash = ? WHERE id = ?",
        (models.now_iso(), content_hash, source_id))


def start_run(source_id, prospect_id):
    cur = run("INSERT INTO collection_runs (source_id, prospect_id, started_at, status)"
              " VALUES (?,?,?,'running')", (source_id, prospect_id, models.now_iso()))
    return cur.lastrowid


def finish_run(run_id, status, record_count=0, error_summary=""):
    run("UPDATE collection_runs SET finished_at=?, status=?, record_count=?,"
        " error_summary=? WHERE id=?",
        (models.now_iso(), status, record_count, error_summary, run_id))


def list_runs(prospect_id=None, limit=20):
    sql = "SELECT * FROM collection_runs"
    params = []
    if prospect_id:
        sql += " WHERE prospect_id = ?"
        params.append(prospect_id)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return rows(sql, params)


def counts_by_mode():
    return {row["data_mode"]: row["n"] for row in
            rows("SELECT data_mode, COUNT(*) AS n FROM prospects GROUP BY data_mode")}
