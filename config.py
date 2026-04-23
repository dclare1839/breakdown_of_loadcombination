"""
config.py — API 설정 단일 진입점
─────────────────────────────────
우선순위:
  1. 시스템 환경변수  (CI/서버 배포 시)
  2. .env 파일       (로컬 개발 시)
  3. 기본값          (fallback)

사용법:
  from config import CIVIL_NX_BASE_URL, CIVIL_NX_MAPI_KEY, get_client
"""

import os
from pathlib import Path


# ── .env 파일 로드 (python-dotenv 없어도 동작하는 경량 파서) ──
def _load_env(env_path: Path = Path(__file__).parent / ".env") -> None:
    """
    .env 파일을 읽어 os.environ에 등록.
    이미 환경변수가 설정되어 있으면 덮어쓰지 않음.
    """
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            # 환경변수가 이미 있으면 유지 (시스템 환경변수 우선)
            if key not in os.environ:
                os.environ[key] = val


_load_env()

# ── 공개 상수 ──────────────────────────────────────────────────
CIVIL_NX_BASE_URL: str = os.environ.get(
    "CIVIL_NX_BASE_URL", "http://127.0.0.1:8090"
)
CIVIL_NX_MAPI_KEY: str = os.environ.get(
    "CIVIL_NX_MAPI_KEY", "YOUR_MAPI_KEY_HERE"
)

# ── 설정값 유효성 경고 ─────────────────────────────────────────
def _warn_if_default() -> None:
    if CIVIL_NX_MAPI_KEY == "YOUR_MAPI_KEY_HERE":
        print("⚠️  CIVIL_NX_MAPI_KEY가 기본값입니다.")
        print("   .env 파일 또는 환경변수를 설정하세요:")
        print("   CIVIL_NX_MAPI_KEY=실제키값")


# ── 편의 팩토리 ────────────────────────────────────────────────
def get_client():
    """
    설정값으로 CivilNXClient를 바로 생성.

    사용 예:
        from config import get_client
        client = get_client()
    """
    from phase1_connection import create_client
    _warn_if_default()
    return create_client(CIVIL_NX_BASE_URL, CIVIL_NX_MAPI_KEY)


if __name__ == "__main__":
    print("=" * 50)
    print(" Civil NX API 설정 확인")
    print("=" * 50)
    print(f"  BASE_URL : {CIVIL_NX_BASE_URL}")
    key_display = (CIVIL_NX_MAPI_KEY[:6] + "****"
                   if len(CIVIL_NX_MAPI_KEY) > 6
                      and CIVIL_NX_MAPI_KEY != "YOUR_MAPI_KEY_HERE"
                   else CIVIL_NX_MAPI_KEY)
    print(f"  MAPI_KEY : {key_display}")
    _warn_if_default()
