# -*- coding: utf-8 -*-
"""고객사·담당자 엑셀 내보내기 / 가져오기.

해외영업은 고객사 명단을 엑셀로 들고 다닌다. 전시회에서 받아온 명함을 정리한
표, 전임자에게 넘겨받은 목록 같은 것들이다. 그걸 화면에서 한 명씩 다시 치게
하면 아무도 쓰지 않는다.

내보낸 파일과 가져오는 양식은 **같은 모양**이다. 내려받아 고치고 다시 올리면
그대로 반영된다. 새 양식을 따로 외울 필요가 없다.

가져오기는 곧바로 저장하지 않는다. 먼저 한 줄씩 판정해서 보여 주고, 사람이
확인한 다음에 저장한다. 명단은 잘못 들어가면 되돌리기가 번거롭다.
"""

import re
from io import BytesIO

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import contact_store
import customer_store

SHEET_NAME = "고객사·담당자"
GUIDE_SHEET = "작성 안내"

# 엑셀 열. header 가 그대로 첫 줄에 들어가고, 가져올 때도 이 이름으로 찾는다.
COLUMNS = [
    {"key": "customer_id", "header": "고객사 ID", "width": 14,
     "hint": "비워 두면 회사명으로 찾습니다. 새 회사는 자동으로 만들어집니다"},
    {"key": "company", "header": "회사명", "width": 24, "required": True,
     "hint": "필수. 대소문자·공백 차이는 같은 회사로 봅니다"},
    {"key": "country", "header": "국가", "width": 10,
     "hint": "예: 미국, 베트남 (국기는 자동)"},
    {"key": "city", "header": "도시", "width": 16, "hint": "예: Los Angeles, CA"},
    {"key": "grade", "header": "등급", "width": 8,
     "hint": "VIP / 일반 / 신규 (비우면 신규)"},
    {"key": "manager", "header": "담당 영업", "width": 12, "hint": "우리 쪽 담당자"},
    {"key": "name", "header": "담당자", "width": 14,
     "hint": "비워 두면 회사만 등록합니다"},
    {"key": "title", "header": "직급·직함", "width": 18,
     "hint": "예: Product Director, 구매팀 과장"},
    {"key": "role", "header": "역할", "width": 12,
     "hint": "구매·발주 / 개발·제형 / 품질·인증 / 물류·선적 / 대금·결제 / 기타"},
    {"key": "email", "header": "이메일", "width": 28,
     "hint": "같은 회사 안에서 같은 이메일이면 기존 담당자를 고칩니다"},
    {"key": "phone", "header": "전화", "width": 18, "hint": "예: +1 213-555-0148"},
    {"key": "timezone", "header": "시차", "width": 18, "hint": "예: PST (한국 −16시간)"},
    {"key": "language", "header": "사용 언어", "width": 12, "hint": "예: English"},
    {"key": "is_primary", "header": "대표", "width": 6,
     "hint": "대표 담당자면 Y. 회사마다 한 명"},
    {"key": "note", "header": "메모", "width": 34, "hint": "회신 습관, 주의할 점 등"},
]
HEADERS = [c["header"] for c in COLUMNS]
BY_HEADER = {c["header"]: c for c in COLUMNS}
BY_KEY = {c["key"]: c for c in COLUMNS}

# 담당자 쪽 열. 이게 하나도 없으면 회사 명단이라 한 회사 한 줄로 접는다.
CONTACT_KEYS = {"name", "title", "role", "email", "phone", "timezone",
                "language", "is_primary", "note"}
COMPANY_KEYS = {"customer_id", "company", "country", "city", "grade", "manager"}

# 받는 쪽에서 자주 쓰는 조합. 열뿐 아니라 "누구를 받을지"까지 같이 정해 둔다.
PRESETS = [
    {"key": "all", "label": "전부", "desc": "모든 담당자 · 모든 열",
     "cols": [c["key"] for c in COLUMNS], "filters": {}},
    {"key": "mailing", "label": "메일 발송용",
     "desc": "이메일이 있는 담당자만 · 이름 · 이메일 · 언어",
     "cols": ["company", "name", "email", "language"],
     "filters": {"email": "1", "empty": "0"}},
    {"key": "buyer", "label": "구매 담당",
     "desc": "발주·단가 창구만 · 연락처",
     "cols": ["company", "country", "name", "title", "email", "phone"],
     "filters": {"role": ["buyer"], "empty": "0"}},
    {"key": "qa", "label": "품질·인증 담당",
     "desc": "성분표·인증서를 요구하는 담당만",
     "cols": ["company", "country", "name", "title", "email", "phone"],
     "filters": {"role": ["qa"], "empty": "0"}},
    {"key": "logistics", "label": "물류 담당",
     "desc": "선적 일정·서류 담당만",
     "cols": ["company", "country", "name", "title", "email", "phone"],
     "filters": {"role": ["logistics"], "empty": "0"}},
    {"key": "primary", "label": "대표 담당자만",
     "desc": "회사마다 한 명 · 연락처",
     "cols": ["company", "country", "name", "title", "role", "email", "phone"],
     "filters": {"primary": "1", "empty": "0"}},
    {"key": "company", "label": "회사만", "desc": "담당자 없이 회사 목록만",
     "cols": ["customer_id", "company", "country", "city", "grade", "manager"],
     "filters": {}},
]
PRESET_MAP = {p["key"]: p for p in PRESETS}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TRUE = {"y", "yes", "예", "o", "ㅇ", "true", "1", "대표", "v"}

GRADE_WORDS = {"vip": "vip", "VIP": "vip", "일반": "regular", "regular": "regular",
               "신규": "new", "new": "new", "": ""}

# 행 판정. 화면에서 색으로 가른다.
PLAN_META = {
    "new": {"label": "담당자 추가", "css": "ok"},
    "update": {"label": "담당자 갱신", "css": "warn"},
    "company": {"label": "회사만 등록", "css": "ok"},
    "company_update": {"label": "회사 정보 갱신", "css": "warn"},
    "skip": {"label": "변경 없음", "css": "none"},
    "error": {"label": "오류", "css": "missing"},
}
PLAN_ORDER = ["new", "update", "company", "company_update", "skip", "error"]

HEAD_FILL = PatternFill("solid", fgColor="F4F5F7")
HEAD_FONT = Font(bold=True, size=10)
THIN = Side(style="thin", color="D9DCE1")
BORDER = Border(bottom=THIN)


# ---------------------------------------------------------------------------
# 내보내기
# ---------------------------------------------------------------------------

def pick_columns(keys):
    """받을 열을 고른다.

    회사명은 늘 넣는다 - 내보낸 파일을 다시 올릴 수 있어야 하는데, 회사명이
    없으면 어느 회사 얘기인지 알 길이 없다.
    """
    chosen = [k for k in (keys or []) if k in BY_KEY]
    if not chosen:
        return list(COLUMNS)
    if "company" not in chosen:
        chosen.append("company")
    return [c for c in COLUMNS if c["key"] in chosen]


def collapse_companies(rows):
    """담당자 열을 하나도 안 골랐으면 회사 단위로 접는다.

    담당자가 셋이라고 같은 회사가 세 줄 나오면 그건 회사 명단이 아니다.
    """
    seen, out = set(), []
    for row in rows:
        key = row.get("customer_id") or row.get("company")
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _sheet(wb, title, columns):
    ws = wb.active if wb.active.max_row == 1 and wb.active.max_column == 1 else wb.create_sheet()
    ws.title = title
    ws.append([c["header"] for c in columns])
    for idx, col in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=idx)
        cell.fill = HEAD_FILL
        cell.font = HEAD_FONT
        cell.alignment = Alignment(vertical="center")
        cell.border = BORDER
        ws.column_dimensions[get_column_letter(idx)].width = col["width"]
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = "A1:{}1".format(get_column_letter(len(columns)))
    return ws


def _guide(wb, columns):
    """양식 설명 시트. 파일만 받아도 어떻게 쓰는지 알 수 있어야 한다."""
    ws = wb.create_sheet(GUIDE_SHEET)
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 72
    ws.append(["항목", "설명"])
    for cell in (ws["A1"], ws["B1"]):
        cell.fill = HEAD_FILL
        cell.font = HEAD_FONT

    for col in columns:
        ws.append([col["header"], col.get("hint", "")])
        ws.cell(row=ws.max_row, column=2).alignment = Alignment(wrap_text=True)

    ws.append([])
    for line in [
        "· 한 줄 = 담당자 한 명입니다. 같은 회사에 담당자가 여러 명이면 회사명을 반복해 적으세요.",
        "· 담당자 칸을 비우면 회사만 등록됩니다.",
        "· 같은 회사 + 같은 이메일이면 기존 담당자를 고칩니다. 새로 만들지 않습니다.",
        "· 빈 칸은 지우라는 뜻이 아닙니다. 적지 않은 값은 원래대로 둡니다.",
        "· 올리면 먼저 한 줄씩 판정만 보여 주고, 확인을 눌러야 저장됩니다.",
    ]:
        ws.append(["", line])
    return ws


def filter_contacts(contacts, opt):
    """받을 담당자만 고른다.

    직무(역할)가 이 필터의 핵심이다. 인증서 재발급 공지를 구매 담당에게 보내면
    품질 담당에게 다시 돌아오고, 선적 지연 안내를 품질 담당이 받으면 아무 일도
    일어나지 않는다. 명단은 보낼 사람 단위로 뽑아야 쓸모가 있다.
    """
    out = []
    for row in contacts:
        if opt.get("active_only") and not row["is_active"]:
            continue
        if opt.get("roles") and row["role"] not in opt["roles"]:
            continue
        if opt.get("has_email") and not (row["email"] or "").strip():
            continue
        if opt.get("has_phone") and not (row["phone"] or "").strip():
            continue
        if opt.get("primary_only") and not row["is_primary"]:
            continue
        if opt.get("language") and opt["language"].lower() not in (
                row["language"] or "").lower():
            continue
        out.append(row)
    return out


def narrows_contacts(opt):
    """담당자를 좁히는 조건이 하나라도 걸려 있는가."""
    return any(opt.get(key) for key in
               ("roles", "has_email", "has_phone", "primary_only",
                "active_only", "language"))


def export_rows(profiles, grouped, opt=None):
    """고객사 카드 + 담당자를 엑셀 한 줄씩으로 편다."""
    opt = opt or {}
    include_empty = opt.get("include_empty", True)
    narrowed = narrows_contacts(opt)

    rows = []
    for profile in profiles:
        if opt.get("country") and profile.get("country", "") != opt["country"]:
            continue

        contacts = filter_contacts(grouped.get(profile["id"], []), opt)

        # 담당자를 좁혀 놓고 한 명도 안 걸린 회사를 빈 줄로 내보내면,
        # "이 회사엔 품질 담당이 있다"는 착각을 준다. 아예 뺀다.
        if not contacts and (narrowed or not include_empty):
            continue
        base = {
            "customer_id": profile["id"],
            "company": profile["name"],
            "country": profile.get("country", ""),
            "city": profile.get("city", ""),
            "grade": customer_store.GRADES and {
                "vip": "VIP", "regular": "일반", "new": "신규"
            }.get(profile.get("grade", ""), ""),
            "manager": profile.get("manager", ""),
        }
        if not contacts:
            rows.append(dict(base, name="", title="", role="", email="",
                             phone="", timezone="", language="",
                             is_primary="", note=""))
            continue

        for contact in contacts:
            rows.append(dict(
                base,
                name=contact["name"],
                title=contact["title"] or "",
                role=contact["role_meta"]["label"],
                email=contact["email"] or "",
                phone=contact["phone"] or "",
                timezone=contact["timezone"] or "",
                language=contact["language"] or "",
                is_primary="Y" if contact["is_primary"] else "",
                note=contact["note"] or "",
            ))
    return rows


def build_workbook(rows, with_guide=True, columns=None):
    """행 목록을 xlsx 바이트로. (내보내기·양식 공용)"""
    columns = columns or list(COLUMNS)
    wb = Workbook()
    ws = _sheet(wb, SHEET_NAME, columns)

    for row in rows:
        ws.append([row.get(col["key"], "") for col in columns])

    if with_guide:
        _guide(wb, columns)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def build_template():
    """빈 양식. 예시 두 줄을 넣어 둔다 - 빈 표만 받으면 어떻게 쓰는지 모른다."""
    return build_workbook([
        {"customer_id": "", "company": "Glowtree Beauty", "country": "미국",
         "city": "Los Angeles, CA", "grade": "VIP", "manager": "홍길동",
         "name": "Emily Park", "title": "Product Director", "role": "구매·발주",
         "email": "emily.park@example.com", "phone": "+1 213-555-0148",
         "timezone": "PST (한국 −16시간)", "language": "English",
         "is_primary": "Y", "note": "회신 빠름. 무향 제품만 취급"},
        {"customer_id": "", "company": "Glowtree Beauty", "country": "", "city": "",
         "grade": "", "manager": "", "name": "Daniel Kim", "title": "QA Manager",
         "role": "품질·인증", "email": "daniel.kim@example.com", "phone": "",
         "timezone": "", "language": "English", "is_primary": "",
         "note": "인증서 원본을 매 건 요구"},
    ])


# ---------------------------------------------------------------------------
# 읽기
# ---------------------------------------------------------------------------

def _text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return re.sub(r"\s+", " ", str(value)).strip()


def read_rows(stream):
    """올린 파일에서 행을 읽는다. (행 목록, 오류 메시지)

    머리글 이름으로 열을 찾는다. 열 순서를 바꿔도, 모르는 열이 끼어 있어도 된다.
    """
    try:
        wb = load_workbook(stream, read_only=True, data_only=True)
    except Exception as exc:                          # noqa: BLE001
        return [], "엑셀 파일을 열지 못했습니다. (.xlsx 형식인지 확인해 주세요) {}".format(
            str(exc)[:60])

    ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not rows:
        return [], "빈 파일입니다."

    header = [_text(v) for v in rows[0]]
    index = {}
    for pos, name in enumerate(header):
        col = BY_HEADER.get(name)
        if col and col["key"] not in index:
            index[col["key"]] = pos

    if "company" not in index:
        return [], ("첫 줄에서 '회사명' 열을 찾지 못했습니다. "
                    "양식을 내려받아 머리글을 그대로 두고 채워 주세요.")

    parsed = []
    for line_no, raw in enumerate(rows[1:], start=2):
        values = {key: _text(raw[pos]) if pos < len(raw) else ""
                  for key, pos in index.items()}
        if not any(values.values()):
            continue                                  # 중간에 낀 빈 줄은 건너뛴다
        values["_line"] = line_no
        parsed.append(values)

    if not parsed:
        return [], "머리글만 있고 내용이 없습니다."
    return parsed, ""


def _role_of(text):
    """역할 칸을 코드로. 라벨('구매·발주')도 값('buyer')도 받는다."""
    word = (text or "").strip().lower()
    if not word:
        return contact_store.DEFAULT_ROLE
    if word in contact_store.ROLE_MAP:
        return word
    for row in contact_store.ROLES:
        label = row["label"].lower()
        if word == label or word in label or label.split("·")[0] in word:
            return row["value"]
    return contact_store.DEFAULT_ROLE


def _grade_of(text):
    word = (text or "").strip()
    return GRADE_WORDS.get(word, GRADE_WORDS.get(word.lower(), ""))


# ---------------------------------------------------------------------------
# 판정 - 저장하기 전에 한 줄씩 무슨 일이 일어날지 보여 준다
# ---------------------------------------------------------------------------

def plan(rows, profiles, grouped):
    """엑셀 행마다 무엇이 될지 미리 판정한다. (저장하지 않는다)

    profiles: 지금 있는 고객사 카드 전체 (더미 + 엑셀로 등록된 것)
    grouped : {고객사 id: [담당자, ...]}
    """
    by_id = {p["id"]: p for p in profiles}
    by_name = {customer_store.norm_name(p["name"]): p for p in profiles}

    # 파일 안에서 같은 회사가 여러 줄에 나오면 한 곳으로 모은다
    pending_company = {}
    # 이번 파일에서 이미 다룬 담당자 (같은 줄이 두 번 나오면 두 번 만들지 않는다)
    seen_contacts = set()

    planned = []
    for row in rows:
        item = {"line": row["_line"], "row": row, "reason": "",
                "company_new": False, "customer_id": "", "contact_id": None}

        company = row.get("company", "")
        if not company:
            item.update(action="error", reason="회사명이 비었습니다.")
            planned.append(item)
            continue

        key = customer_store.norm_name(company)
        given_id = row.get("customer_id", "")

        # 1) 고객사 찾기 - ID 가 있으면 ID 우선, 없으면 회사명
        target = None
        if given_id:
            target = by_id.get(given_id)
            if target is None:
                item.update(action="error",
                            reason="고객사 ID '{}' 를 찾지 못했습니다. ID 를 비우면 "
                                   "회사명으로 찾거나 새로 만듭니다.".format(given_id))
                planned.append(item)
                continue
        else:
            target = by_name.get(key)

        if target is not None:
            item["customer_id"] = target["id"]
            item["company_name"] = target["name"]
            item["imported"] = bool(target.get("imported"))
        else:
            # 파일 안에서 같은 회사가 여러 줄에 나와도 회사는 한 번만 만든다.
            # 이름 표기는 처음 나온 줄을 따른다 (대소문자만 다른 경우 대비)
            item["company_new"] = True
            item["company_name"] = pending_company.setdefault(key, company)

        # 2) 담당자가 없으면 회사만
        name = row.get("name", "")
        if not name:
            if item["company_new"]:
                item["action"] = "company"
            elif item.get("imported"):
                item.update(action="company_update",
                            reason="담당자 칸이 비어 회사 정보만 갱신합니다.")
            else:
                # 더미 고객사 카드는 엑셀로 고치지 않는다. 바뀌는 게 없다고 밝힌다
                item.update(action="skip",
                            reason="이미 등록된 고객사이고 담당자 칸이 비어 바뀌는 것이 없습니다.")
            planned.append(item)
            continue

        # 3) 값 검사
        email = row.get("email", "")
        if email and not _EMAIL_RE.match(email):
            item.update(action="error",
                        reason="이메일 형식이 올바르지 않습니다: {}".format(email))
            planned.append(item)
            continue

        # 4) 기존 담당자와 맞춰 보기 - 같은 회사 + 같은 이메일(없으면 이름)
        existing = None
        if not item["company_new"]:
            for contact in grouped.get(item["customer_id"], []):
                if email and (contact["email"] or "").lower() == email.lower():
                    existing = contact
                    break
                if not email and contact["name"] == name:
                    existing = contact
                    break

        # 새 회사는 아직 id 가 없으니 회사명으로 묶는다
        dedupe = (item["customer_id"] or key, (email or name).lower())
        if dedupe in seen_contacts:
            item.update(action="error",
                        reason="같은 담당자가 파일 안에 두 번 있습니다.")
            planned.append(item)
            continue
        seen_contacts.add(dedupe)

        if existing:
            item.update(action="update", contact_id=existing["id"],
                        reason="이메일이 같아 기존 담당자를 고칩니다.")
        else:
            item["action"] = "new"
            if item["company_new"]:
                item["reason"] = "새 고객사로 등록하고 담당자를 넣습니다."
        planned.append(item)

    return planned


def summarize(planned):
    counts = {key: 0 for key in PLAN_ORDER}
    for item in planned:
        counts[item["action"]] = counts.get(item["action"], 0) + 1
    counts["companies"] = len({p["company_name"] for p in planned
                               if p.get("company_new")})
    counts["total"] = len(planned)
    counts["ok"] = counts["total"] - counts["error"] - counts["skip"]
    return counts


# ---------------------------------------------------------------------------
# 저장
# ---------------------------------------------------------------------------

def apply(planned):
    """판정 결과를 실제로 저장한다. 오류 줄은 건너뛴다."""
    created_company = {}
    result = {"companies": 0, "added": 0, "updated": 0, "skipped": 0}

    for item in planned:
        if item["action"] in ("error", "skip"):
            result["skipped"] += 1
            continue

        row = item["row"]
        key = customer_store.norm_name(row["company"])

        customer_id = item["customer_id"]
        if item["company_new"]:
            customer_id = created_company.get(key)
            if customer_id is None:
                customer_id = customer_store.create({
                    "name": row["company"],
                    "country": row.get("country", ""),
                    "city": row.get("city", ""),
                    "grade": _grade_of(row.get("grade", "")),
                    "manager": row.get("manager", ""),
                }, taken_ids=set(created_company.values()))
                created_company[key] = customer_id
                result["companies"] += 1
        elif customer_store.profile(customer_id):
            # 엑셀로 등록된 고객사면 비어 있던 칸을 채운다 (더미 카드는 건드리지 않는다)
            customer_store.update(customer_id, {
                "country": row.get("country", ""), "city": row.get("city", ""),
                "grade": _grade_of(row.get("grade", "")),
                "manager": row.get("manager", ""),
            })

        if item["action"] in ("company", "company_update"):
            continue

        data = {
            "name": row.get("name", ""), "title": row.get("title", ""),
            "role": _role_of(row.get("role", "")), "email": row.get("email", ""),
            "phone": row.get("phone", ""), "timezone": row.get("timezone", ""),
            "language": row.get("language", ""), "note": row.get("note", ""),
            "is_primary": (row.get("is_primary", "") or "").strip().lower() in _TRUE,
        }

        if item["action"] == "update" and item["contact_id"]:
            contact_store.update_contact(item["contact_id"], data)
            result["updated"] += 1
        else:
            contact_store.add_contact(customer_id, data)
            result["added"] += 1

    return result
