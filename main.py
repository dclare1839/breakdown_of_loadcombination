"""
MIDAS Civil NX EN 1990 Plugin — 통합 실행 스크립트
Phase 1 → 2 → 3 → 4 → 5 → 6 전체 파이프라인 실행
"""

import sys

# ─── 설정 ─────────────────────────────────────
CONFIG = {
    # Phase 1: API 연결 (.env 또는 환경변수로 관리 — config.py 참조)
    # "base_url" / "mapi_key" 항목 제거: config.py에서 자동 로드

    # Phase 3: EN 1990 엔진
    "country"       : "EN",       # EN / DE / PL / HU / RO / HR / AL
    "eq_method"     : "6.10ab",   # "6.10" / "6.10ab" / "all"

    # Phase 4: 해석
    "run_analysis"  : True,
    "clean_existing": False,      # True: 기존 EN1990 조합 삭제 후 재생성

    # Phase 5-6: 출력
    "output_dir"    : "./output",
    "project_info"  : {
        "project_name": "My Project",
        "structure"   : "Bridge / Building",
        "country_na"  : "EN (Eurocode default)",
        "prepared_by" : "Engineer Name",
    }
}


def main():
    print("=" * 60)
    print("  MIDAS Civil NX  │  EN 1990 Load Combination Plugin")
    print("=" * 60)

    # ── Phase 1: 연결 ─────────────────────────
    print("\n[Phase 1] API 연결")
    from phase1_connection import create_client, test_connection
    from config import get_client
    client = get_client()
    if not test_connection(client):
        print("Civil NX 연결 실패. 프로그램을 종료합니다.")
        sys.exit(1)

    # ── Phase 2: 데이터 추출 ──────────────────
    print("\n[Phase 2] 모델 데이터 추출")
    from phase2_data_extraction import ModelExtractor
    model = ModelExtractor(client).extract_all()

    # ── Phase 3: EN 1990 조합 생성 ───────────
    print("\n[Phase 3] EN 1990 조합식 생성")
    from phase3_en1990_engine import EN1990Engine
    engine = EN1990Engine(model.load_cases,
                          country   = CONFIG["country"],
                          eq_method = CONFIG["eq_method"])
    combos = engine.generate_all()

    # ── Phase 4: Civil NX 적용 + 해석 ─────────
    print("\n[Phase 4] Load Combination 적용 및 해석 실행")
    from phase4_apply_and_run import CombinationApplicator, AnalysisRunner
    applicator = CombinationApplicator(client)
    if CONFIG["clean_existing"]:
        applicator.delete_en1990_combos()
    applicator.apply_all(combos, skip_existing=not CONFIG["clean_existing"])

    if CONFIG["run_analysis"]:
        runner = AnalysisRunner(client)
        ok = runner.run_analysis()
        if not ok:
            print("⚠️  해석 실패. 결과 추출을 건너뜁니다.")
            sys.exit(1)

    # ── Phase 5: 결과 추출 ────────────────────
    print("\n[Phase 5] 결과 추출 및 Breakdown 분석")
    from phase5_results_visualization import ResultExtractor, BreakdownAnalyzer
    extractor = ResultExtractor(client)
    results   = extractor.extract_all_combos(combos)
    analyzer  = BreakdownAnalyzer(results)

    # ── Phase 6: 리포트 생성 ──────────────────
    print("\n[Phase 6] 리포트 자동 생성")
    from phase6_report_generator import generate_reports
    output = generate_reports(
        combos       = combos,
        analyzer     = analyzer,
        output_dir   = CONFIG["output_dir"],
        project_info = CONFIG["project_info"]
    )

    print("\n" + "=" * 60)
    print("  ✅ 전체 파이프라인 완료")
    print(f"  📄 Word  : {output['word']}")
    print(f"  📊 Excel : {output['excel']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
