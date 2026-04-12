"""
Phase 4: Civil NX에 Load Combination 적용 및 해석 실행
- Phase 3에서 생성한 조합을 Civil NX API로 POST
- Analysis Run 실행 후 완료 대기
"""

import time
from typing import List, Tuple
from phase1_connection import CivilNXClient, create_client
from phase3_en1990_engine import LoadCombination, EN1990Engine
from phase2_data_extraction import ModelExtractor


# ─────────────────────────────────────────────
# 1. Load Combination 적용기
# ─────────────────────────────────────────────
class CombinationApplicator:
    """Civil NX에 EN1990 Load Combination 적용"""

    def __init__(self, client: CivilNXClient):
        self.client = client

    # ── 기존 LC 목록 조회 ─────────────────────
    def get_existing_combos(self) -> List[str]:
        """현재 모델의 Load Combination 이름 목록"""
        try:
            raw = self.client.get("/civil/lcom")
            assign = raw.get("Assign", {})
            return list(assign.keys())
        except Exception:
            return []

    # ── 단일 조합 적용 ────────────────────────
    def apply_combination(self, combo: LoadCombination) -> Tuple[bool, str]:
        """
        단일 Load Combination을 Civil NX에 POST
        반환: (성공여부, 메시지)
        """
        payload = combo.to_civil_nx_payload()
        try:
            result = self.client.post("/civil/lcom", payload)
            # Civil NX는 성공 시 {"Assign": {}} 또는 status 200 반환
            return True, f"✅ {combo.name} 생성 완료"
        except Exception as e:
            return False, f"❌ {combo.name} 실패: {e}"

    # ── 전체 조합 일괄 적용 ───────────────────
    def apply_all(self, combos: List[LoadCombination],
                  skip_existing: bool = True) -> dict:
        """
        모든 조합 적용
        skip_existing=True: 이미 존재하는 조합은 건너뜀
        """
        existing = self.get_existing_combos() if skip_existing else []
        success_count = 0
        skip_count    = 0
        fail_count    = 0
        failed_names  = []

        print(f"\n📤 Load Combination 적용 시작 (총 {len(combos)}개)\n")

        for combo in combos:
            if skip_existing and combo.name in existing:
                print(f"⏭️  {combo.name} — 이미 존재, 건너뜀")
                skip_count += 1
                continue

            ok, msg = self.apply_combination(combo)
            print(f"   {msg}")
            if ok:
                success_count += 1
            else:
                fail_count += 1
                failed_names.append(combo.name)

            time.sleep(0.05)  # API Rate 제한 방지

        summary = {
            "total"  : len(combos),
            "success": success_count,
            "skipped": skip_count,
            "failed" : fail_count,
            "failed_names": failed_names
        }

        print(f"\n{'='*50}")
        print(f"📊 적용 결과: 성공 {success_count} | 건너뜀 {skip_count} | 실패 {fail_count}")
        if failed_names:
            print(f"   실패 목록: {failed_names}")

        return summary

    # ── 조합 삭제 (초기화용) ──────────────────
    def delete_combination(self, combo_name: str) -> bool:
        """특정 Load Combination 삭제"""
        try:
            self.client.delete(f"/civil/lcom/{combo_name}")
            return True
        except Exception as e:
            print(f"❌ 삭제 실패 ({combo_name}): {e}")
            return False

    def delete_en1990_combos(self) -> int:
        """EN1990_ 접두사를 가진 조합 모두 삭제 (재실행 준비)"""
        existing = self.get_existing_combos()
        target   = [n for n in existing
                    if any(n.startswith(p) for p in ("ULS_", "SLS_"))]
        count    = 0
        for name in target:
            if self.delete_combination(name):
                count += 1
        print(f"🗑️  {count}개 기존 EN1990 조합 삭제됨")
        return count


# ─────────────────────────────────────────────
# 2. 해석 실행기
# ─────────────────────────────────────────────
class AnalysisRunner:
    """Civil NX 해석 실행 및 상태 모니터링"""

    POLL_INTERVAL = 3    # 상태 확인 간격 (초)
    MAX_WAIT      = 600  # 최대 대기 시간 (초)

    def __init__(self, client: CivilNXClient):
        self.client = client

    def run_analysis(self) -> bool:
        """
        Civil NX 해석 실행
        POST /civil/analysis/run
        """
        print("\n🔄 해석 실행 중...")
        try:
            result = self.client.post("/civil/analysis/run", {})
            print("✅ 해석 명령 전송 완료")
            return self._wait_for_completion()
        except Exception as e:
            print(f"❌ 해석 실행 실패: {e}")
            return False

    def _wait_for_completion(self) -> bool:
        """해석 완료까지 대기 (폴링)"""
        elapsed = 0
        while elapsed < self.MAX_WAIT:
            status = self._get_analysis_status()
            if status == "DONE":
                print(f"\n✅ 해석 완료! (소요 시간: {elapsed}초)")
                return True
            elif status == "ERROR":
                print("\n❌ 해석 오류 발생")
                return False
            else:
                print(f"   ⏳ 해석 중... ({elapsed}s)", end="\r")
                time.sleep(self.POLL_INTERVAL)
                elapsed += self.POLL_INTERVAL

        print(f"\n⚠️  해석 타임아웃 ({self.MAX_WAIT}초 초과)")
        return False

    def _get_analysis_status(self) -> str:
        """
        GET /civil/analysis/status
        반환: "IDLE" / "RUNNING" / "DONE" / "ERROR"
        """
        try:
            raw = self.client.get("/civil/analysis/status")
            return raw.get("STATUS", "IDLE").upper()
        except Exception:
            return "IDLE"

    def get_analysis_log(self) -> str:
        """해석 로그 조회"""
        try:
            raw = self.client.get("/civil/analysis/log")
            return raw.get("LOG", "로그 없음")
        except Exception:
            return "로그 조회 실패"


# ─────────────────────────────────────────────
# 3. 통합 실행 (Phase 2→3→4 파이프라인)
# ─────────────────────────────────────────────
def run_phase4(client: CivilNXClient,
               country: str = "EN",
               eq_method: str = "6.10ab",
               run_analysis: bool = True,
               clean_existing: bool = False) -> List[LoadCombination]:
    """
    Phase 4 통합 실행
    1. Phase 2: 모델 데이터 추출
    2. Phase 3: EN1990 조합 생성
    3. Civil NX에 조합 적용
    4. (선택) 해석 실행
    """

    # ── Step 1: 데이터 추출 ──────────────────
    extractor = ModelExtractor(client)
    model     = extractor.extract_all()

    # ── Step 2: 조합 생성 ────────────────────
    engine = EN1990Engine(model.load_cases, country=country, eq_method=eq_method)
    combos = engine.generate_all()

    # ── Step 3: Civil NX 적용 ────────────────
    applicator = CombinationApplicator(client)

    if clean_existing:
        applicator.delete_en1990_combos()

    result = applicator.apply_all(combos, skip_existing=not clean_existing)

    # ── Step 4: 해석 실행 ────────────────────
    if run_analysis and result["success"] > 0:
        runner = AnalysisRunner(client)
        success = runner.run_analysis()
        if not success:
            print("⚠️  해석 실패. 결과 추출을 건너뜁니다.")

    return combos


# ─────────────────────────────────────────────
# 4. 실행
# ─────────────────────────────────────────────
if __name__ == "__main__":
    client = create_client(
        base_url="http://127.0.0.1:8090",
        mapi_key="YOUR_MAPI_KEY_HERE"
    )

    combos = run_phase4(
        client       = client,
        country      = "EN",       # 국가 코드 (EN / DE / PL / HU / RO / HR / AL)
        eq_method    = "6.10ab",   # "6.10" / "6.10ab" / "all"
        run_analysis = True,       # True: 해석 자동 실행
        clean_existing = False     # True: 기존 EN1990 조합 삭제 후 재생성
    )

    print(f"\n📋 생성된 조합 수: {len(combos)}")
