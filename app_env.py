# -*- coding: utf-8 -*-
"""`.env` 읽기.

API 키를 코드에 적어 두지 않으려고 쓴다. 외부 라이브러리(python-dotenv)를
깔지 않아도 되게 필요한 만큼만 직접 읽는다.

  - `.env` 는 Git 에서 제외한다 (`.gitignore`)
  - `.env.example` 에는 이름과 설명만 적는다. 실제 키는 넣지 않는다
  - 이미 설정된 환경변수가 있으면 그것을 우선한다 (`.env` 가 덮지 않는다)
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")

_cache = None


def _load():
    """`.env` 를 한 번만 읽어 둔다."""
    global _cache
    if _cache is not None:
        return _cache

    values = {}
    try:
        with open(ENV_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                value = value.strip()
                # KEY="값" / KEY='값' 둘 다 받는다
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                values[name.strip()] = value
    except OSError:
        pass                                   # .env 가 없어도 정상이다

    _cache = values
    return values


def get(name, default=""):
    """환경변수 → `.env` → 기본값 순서로 찾는다."""
    found = os.environ.get(name)
    if found:
        return found.strip()
    return (_load().get(name) or default).strip()


def has(name):
    return bool(get(name))


def masked(name):
    """키가 설정됐는지만 보여 준다. 값은 화면·로그에 내보내지 않는다."""
    value = get(name)
    if not value:
        return ""
    return "설정됨 ({}자리)".format(len(value))
