"""
Phase 1: 환경 세팅 및 MIDAS Civil NX API 연결
- Civil NX 실행 후 API Settings에서 Base URL 및 MAPI-Key 발급 필요
- Civil NX 버전: 2024 이상 권장
"""

import requests
import json
from dataclasses import dataclass
from typing import Optional


# ─────────────────────────────────────────────
# 1. API 설정
# ─────────────────────────────────────────────
@dataclass
class CivilNXConfig:
    """Civil NX API 연결 설정"""
    base_url: str = "http://127.0.0.1:8090"   # Civil NX API Settings에서 확인
    mapi_key: str = "YOUR_MAPI_KEY_HERE"        # Civil NX API Settings에서 발급
    timeout: int = 30


class CivilNXClient:
    """MIDAS Civil NX REST API 클라이언트"""

    def __init__(self, config: CivilNXConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "MAPI-Key": config.mapi_key
        })

    def _url(self, endpoint: str) -> str:
        return f"{self.config.base_url}{endpoint}"

    # ── GET 요청 ──────────────────────────────
    def get(self, endpoint: str) -> dict:
        resp = self.session.get(
            self._url(endpoint),
            timeout=self.config.timeout
        )
        resp.raise_for_status()
        return resp.json()

    # ── POST 요청 ─────────────────────────────
    def post(self, endpoint: str, payload: dict) -> dict:
        resp = self.session.post(
            self._url(endpoint),
            data=json.dumps(payload),
            timeout=self.config.timeout
        )
        resp.raise_for_status()
        return resp.json()

    # ── PUT 요청 ──────────────────────────────
    def put(self, endpoint: str, payload: dict) -> dict:
        resp = self.session.put(
            self._url(endpoint),
            data=json.dumps(payload),
            timeout=self.config.timeout
        )
        resp.raise_for_status()
        return resp.json()

    # ── DELETE 요청 ───────────────────────────
    def delete(self, endpoint: str) -> dict:
        resp = self.session.delete(
            self._url(endpoint),
            timeout=self.config.timeout
        )
        resp.raise_for_status()
        return resp.json()


# ─────────────────────────────────────────────
# 2. 연결 테스트
# ─────────────────────────────────────────────
def test_connection(client: CivilNXClient) -> bool:
    """
    Civil NX 연결 테스트
    GET /civil/db → 모델 기본 정보 반환
    """
    try:
        result = client.get("/civil/db")
        print("✅ Civil NX 연결 성공")
        print(f"   모델명  : {result.get('Assign', {}).get('NAME', 'N/A')}")
        print(f"   단위계  : {result.get('Assign', {}).get('UNIT', 'N/A')}")
        return True

    except requests.exceptions.ConnectionError:
        print("❌ 연결 실패: Civil NX가 실행 중인지 확인하세요.")
        print("   → Civil NX > Tools > API Settings > Enable API Server")
        return False

    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP 오류: {e}")
        print("   → MAPI-Key가 올바른지 확인하세요.")
        return False

    except Exception as e:
        print(f"❌ 예상치 못한 오류: {e}")
        return False


def get_model_info(client: CivilNXClient) -> Optional[dict]:
    """모델 기본 정보 조회"""
    try:
        db_info   = client.get("/civil/db")
        unit_info = client.get("/civil/unit")
        return {
            "name"  : db_info.get("Assign", {}).get("NAME", ""),
            "unit"  : unit_info.get("Assign", {}),
            "raw_db": db_info
        }
    except Exception as e:
        print(f"모델 정보 조회 실패: {e}")
        return None


# ─────────────────────────────────────────────
# 3. 실행 진입점
# ─────────────────────────────────────────────
def create_client(base_url: str = "http://127.0.0.1:8090",
                  mapi_key: str = "YOUR_MAPI_KEY_HERE") -> CivilNXClient:
    """클라이언트 팩토리 함수 (다른 Phase에서 재사용)"""
    config = CivilNXConfig(base_url=base_url, mapi_key=mapi_key)
    return CivilNXClient(config)


if __name__ == "__main__":
    # ── 설정값 입력 ──────────────────────────
    BASE_URL = "http://127.0.0.1:8090"   # Civil NX API Settings에서 확인
    MAPI_KEY = "YOUR_MAPI_KEY_HERE"      # Civil NX API Settings에서 복사

    client = create_client(BASE_URL, MAPI_KEY)

    print("=" * 50)
    print(" MIDAS Civil NX API 연결 테스트")
    print("=" * 50)

    if test_connection(client):
        info = get_model_info(client)
        if info:
            print(f"\n📋 모델 정보")
            print(f"   이름 : {info['name']}")
            print(f"   단위 : {info['unit']}")
