# -*- coding: utf-8 -*-
"""고객사 메일 번역·요약.

번역: MyMemory Translation API (Open API, 키 불필요)
      https://api.mymemory.translated.net/get?q=...&langpair=en|ko

요약: 외부 호출 없이 로컬에서 처리한다.
      무료로 쓸 수 있는 키 없는 요약 API가 없어서, 문장 점수 기반 추출 요약 +
      규칙 기반 항목 추출로 만들었다. 성분은 EU 규제 실데이터(reg_store)로 대조한다.
      화면에도 "번역=외부 API / 요약=자체 처리"로 구분해 표시한다.

주의:
  - MyMemory 는 한 번에 500자까지라 문장 단위로 쪼개 보낸다.
  - 무료 쿼터가 있어서 번역 결과를 디스크에 캐시한다.
"""

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "apicache")
CACHE_PATH = os.path.join(CACHE_DIR, "translations.json")

TRANSLATE_API = "https://api.mymemory.translated.net/get"
USER_AGENT = "todo-trade-mail/1.0 (cosmetics trade dashboard; educational prototype)"

MAX_CHARS = 480        # MyMemory 한 번 요청 한도(500자)보다 살짝 낮게
REQUEST_DELAY = 0.2    # 연속 호출 간격
TIMEOUT = 20

TRANSLATE_SOURCE = {
    "name": "MyMemory Translation API",
    "url": "https://mymemory.translated.net/",
    "auth": "불필요",
}

LANGUAGES = [
    {"code": "ko", "label": "한국어"},
    {"code": "en", "label": "English"},
]


# ---------------------------------------------------------------------------
# 캐시
# ---------------------------------------------------------------------------

def _load_cache():
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_cache(cache):
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, CACHE_PATH)


def _cache_key(text, pair):
    return hashlib.sha1((pair + "|" + text).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 번역
# ---------------------------------------------------------------------------

def split_sentences(text):
    """문장 단위로 나눈다. 너무 긴 문장은 길이로 한 번 더 자른다."""
    parts = []
    for block in (text or "").split("\n"):
        block = block.strip()
        if not block:
            continue
        for sentence in re.split(r"(?<=[.!?。？！])\s+", block):
            sentence = sentence.strip()
            while len(sentence) > MAX_CHARS:
                cut = sentence.rfind(" ", 0, MAX_CHARS)
                cut = cut if cut > 0 else MAX_CHARS
                parts.append(sentence[:cut].strip())
                sentence = sentence[cut:].strip()
            if sentence:
                parts.append(sentence)
    return parts


def _request(text, pair):
    url = TRANSLATE_API + "?" + urllib.parse.urlencode({"q": text, "langpair": pair})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        payload = json.loads(res.read().decode("utf-8"))

    if payload.get("responseStatus") not in (200, "200"):
        raise RuntimeError(payload.get("responseDetails") or "translation failed")
    return payload["responseData"]["translatedText"]


def translate(text, source="en", target="ko"):
    """문장 단위로 번역해 합쳐서 돌려준다.

    돌려주는 값:
      text      - 번역문 (실패한 문장은 원문 그대로)
      segments  - [{source, translated, cached, ok}]
      failed    - 번역 실패 문장 수
    """
    pair = "{}|{}".format(source, target)
    sentences = split_sentences(text)
    if not sentences:
        return {"text": "", "segments": [], "failed": 0, "cached": 0,
                "source_lang": source, "target_lang": target}

    cache = _load_cache()
    segments = []
    dirty = False
    failed = cached_count = 0

    for index, sentence in enumerate(sentences):
        key = _cache_key(sentence, pair)
        if key in cache:
            segments.append({"source": sentence, "translated": cache[key],
                             "cached": True, "ok": True})
            cached_count += 1
            continue

        try:
            translated = _request(sentence, pair)
            cache[key] = translated
            dirty = True
            segments.append({"source": sentence, "translated": translated,
                             "cached": False, "ok": True})
        except Exception:                                  # noqa: BLE001
            failed += 1
            segments.append({"source": sentence, "translated": sentence,
                             "cached": False, "ok": False})

        if index < len(sentences) - 1:
            time.sleep(REQUEST_DELAY)

    if dirty:
        _save_cache(cache)

    return {
        "text": "\n".join(s["translated"] for s in segments),
        "segments": segments,
        "failed": failed,
        "cached": cached_count,
        "source_lang": source,
        "target_lang": target,
        "provider": TRANSLATE_SOURCE["name"],
    }


def detect_language(text):
    """한글이 섞여 있으면 ko, 아니면 en 으로 본다. (간단 판별)"""
    hangul = len(re.findall(r"[가-힣]", text or ""))
    return "ko" if hangul > len(text or "") * 0.1 else "en"


# ---------------------------------------------------------------------------
# 요약 (로컬 처리)
# ---------------------------------------------------------------------------

# 무역·개발 메일에서 중요한 신호가 되는 낱말
_WEIGHTS = {
    "high": (3.0, ["moq", "price", "단가", "target", "deadline", "납기", "shipment", "선적",
                   "sample", "샘플", "approve", "approved", "승인", "urgent", "asap",
                   "reject", "cancel", "규제", "regulation", "compliance", "eu", "fda"]),
    "mid": (1.6, ["formula", "처방", "ingredient", "성분", "concentration", "농도", "%",
                  "package", "패키지", "label", "라벨", "certificate", "인증", "test", "시험",
                  "quotation", "견적", "order", "발주", "schedule", "일정"]),
}

_PATTERNS = [
    ("수량", re.compile(r"(?:MOQ|moq|최소\s*주문)\D{0,12}([\d,]{3,})\s*(?:units?|pcs?|개)?", re.I)),
    ("단가", re.compile(r"(USD|EUR|JPY|\$|₩)\s?([\d,]+(?:\.\d+)?)", re.I)),
    ("용량", re.compile(r"(\d+(?:\.\d+)?)\s?(ml|g|oz)\b", re.I)),
    ("기간", re.compile(r"(\d+)\s*(weeks?|days?|months?|주|일|개월)", re.I)),
    ("시점", re.compile(r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}|\d{4}년\s*\d{1,2}월)")),
]

# "... the Retinol 0.5% ..." 처럼 농도 앞에 오는 말을 넉넉히 잡아 두고,
# 뒤에서부터 1~3단어씩 줄여가며 규제 사전에 있는 이름을 찾는다.
_PERCENT_RE = re.compile(r"([A-Za-z][A-Za-z\-\s]{0,44}?)\s*(?:at\s+)?(\d+(?:[.,]\d+)?)\s?%")


# 인사말·맺음말·서명은 요약에서 뺀다
_BOILERPLATE = re.compile(
    r"^(hi|hello|dear|bonjour|good\s+(morning|afternoon)|안녕하세요|"
    r"best|regards|best\s+regards|kind\s+regards|sincerely|thanks|thank\s+you|"
    r"cordialement|감사합니다|드림|올림)\b",
    re.I)


def _is_boilerplate(sentence):
    text = sentence.strip().rstrip(",.!")
    if len(text) < 15:                       # "Hong", "Emily" 같은 서명 줄
        return True
    return bool(_BOILERPLATE.match(text))


def _score_sentence(sentence, position, total):
    if _is_boilerplate(sentence):
        return -10.0

    low = sentence.lower()
    score = 0.0
    for weight, words in _WEIGHTS.values():
        for word in words:
            if word in low:
                score += weight
    # 첫 문장과 마지막 문장은 결론이 담기는 경우가 많다
    if position == 0:
        score += 2.0
    elif position == total - 1:
        score += 1.0
    if re.search(r"\?\s*$", sentence):     # 질문은 대응이 필요하다
        score += 2.5
    score += min(len(sentence) / 120.0, 1.0)
    return score


def extract_facts(text):
    """본문에서 숫자·조건이 들어간 항목을 뽑는다."""
    facts = []
    seen = set()
    for label, pattern in _PATTERNS:
        for match in pattern.finditer(text or ""):
            value = " ".join(part for part in match.groups() if part).strip()
            value = re.sub(r"\s+", " ", value)
            key = (label, value.lower())
            if not value or key in seen:
                continue
            seen.add(key)
            facts.append({"label": label, "value": value,
                          "context": match.group(0).strip()})
    return facts


def check_ingredients(text):
    """본문에 나온 '성분 + 농도'를 EU 규제 실데이터로 대조한다.

    농도 앞의 말에서 뒤 1~3단어를 후보로 잡고, 규제 사전에 실제로 있는
    가장 긴 이름을 고른다. ("the Retinol 0.5%" -> Retinol)
    """
    try:
        import reg_store
    except ImportError:
        return []
    if not reg_store.is_available():
        return []

    found = []
    seen = set()
    for match in _PERCENT_RE.finditer(text or ""):
        words = [w for w in re.split(r"\s+", match.group(1).strip()) if w]
        amount = "{}%".format(match.group(2).replace(",", "."))

        name = None
        for size in (3, 2, 1):                    # 긴 이름을 먼저 시도한다
            if len(words) < size:
                continue
            candidate = " ".join(words[-size:])
            if reg_store.lookup(candidate):
                name = candidate
                break
        if not name or name.lower() in seen:
            continue

        verdict = reg_store.judge(name, name, None, amount)
        if verdict is None:
            continue
        seen.add(name.lower())
        found.append({"name": name, "amount": amount, "status": verdict["status"],
                      "limit": verdict["limit"], "rule": verdict["rule"],
                      "note": verdict["note"], "annex": verdict.get("annex", "")})
    return found


def summarize(text, max_sentences=3):
    """추출 요약 + 항목 추출 + 성분 규제 대조.

    TODO: 실제 연동 (요약 모델 API). 무료·키 없는 공개 API가 없어 로컬 처리로 둔다.
    """
    sentences = split_sentences(text)
    if not sentences:
        return {"sentences": [], "facts": [], "ingredients": [],
                "total_sentences": 0, "method": "local"}

    scored = [(_score_sentence(s, i, len(sentences)), i, s)
              for i, s in enumerate(sentences)]
    usable = [row for row in scored if row[0] > 0] or scored
    top = sorted(usable, key=lambda row: row[0], reverse=True)[:max_sentences]
    top.sort(key=lambda row: row[1])   # 원문 순서를 지킨다

    ingredients = check_ingredients(text)
    facts = extract_facts(text)
    # 성분·농도도 항목으로 같이 보여준다
    for row in ingredients:
        facts.insert(0, {"label": "농도", "value": "{} {}".format(row["name"], row["amount"]),
                         "context": row["limit"]})

    return {
        "sentences": [{"text": s, "index": i} for _, i, s in top],
        "facts": facts,
        "ingredients": ingredients,
        "total_sentences": len(sentences),
        "method": "local",
    }
