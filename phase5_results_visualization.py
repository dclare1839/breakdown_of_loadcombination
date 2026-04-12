"""
Phase 5: 해석 결과 추출 및 Breakdown 시각화
- Internal Forces (Axial / Shear / Moment)
- Node Displacements
- Reactions
- pandas DataFrame으로 정리 → 조합별/부재별 Breakdown
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")   # GUI 없는 환경에서 렌더링
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from typing import List, Optional
from pathlib import Path
from phase1_connection import CivilNXClient, create_client
from phase3_en1990_engine import LoadCombination


# ─────────────────────────────────────────────
# 1. 결과 추출기
# ─────────────────────────────────────────────
class ResultExtractor:
    """Civil NX 해석 결과 추출"""

    RESULT_TYPES = {
        "forces"      : "/civil/post/beamforce",
        "displacements": "/civil/post/nodedisp",
        "reactions"   : "/civil/post/reaction",
    }

    def __init__(self, client: CivilNXClient):
        self.client = client

    # ── 부재력 추출 ───────────────────────────
    def get_beam_forces(self, combo_name: str) -> pd.DataFrame:
        """
        GET /civil/post/beamforce?LCNAME={combo_name}&POS=ENDI
        반환: ElemID, ComboName, Axial, ShearY, ShearZ, TorqueX, MomentY, MomentZ
        """
        try:
            raw = self.client.get(
                f"/civil/post/beamforce?LCNAME={combo_name}&POS=ENDI"
            )
            assign = raw.get("Assign", {})
            rows = []
            for elem_id, vals in assign.items():
                # vals 구조: {FORCE: [Fx, Fy, Fz, Mx, My, Mz], ...}
                force = vals.get("FORCE", [0]*6)
                rows.append({
                    "ElemID"  : int(elem_id),
                    "Combo"   : combo_name,
                    "Axial"   : force[0] if len(force) > 0 else 0.0,
                    "ShearY"  : force[1] if len(force) > 1 else 0.0,
                    "ShearZ"  : force[2] if len(force) > 2 else 0.0,
                    "Torque"  : force[3] if len(force) > 3 else 0.0,
                    "MomentY" : force[4] if len(force) > 4 else 0.0,
                    "MomentZ" : force[5] if len(force) > 5 else 0.0,
                })
            return pd.DataFrame(rows)
        except Exception as e:
            print(f"  부재력 추출 실패 ({combo_name}): {e}")
            return pd.DataFrame()

    # ── 변위 추출 ─────────────────────────────
    def get_displacements(self, combo_name: str) -> pd.DataFrame:
        """GET /civil/post/nodedisp"""
        try:
            raw = self.client.get(
                f"/civil/post/nodedisp?LCNAME={combo_name}"
            )
            assign = raw.get("Assign", {})
            rows = []
            for node_id, vals in assign.items():
                disp = vals.get("DISP", [0]*6)
                rows.append({
                    "NodeID": int(node_id),
                    "Combo" : combo_name,
                    "Dx"    : disp[0] if len(disp) > 0 else 0.0,
                    "Dy"    : disp[1] if len(disp) > 1 else 0.0,
                    "Dz"    : disp[2] if len(disp) > 2 else 0.0,
                    "Rx"    : disp[3] if len(disp) > 3 else 0.0,
                    "Ry"    : disp[4] if len(disp) > 4 else 0.0,
                    "Rz"    : disp[5] if len(disp) > 5 else 0.0,
                    "D_total": np.sqrt(sum(v**2 for v in disp[:3]))
                })
            return pd.DataFrame(rows)
        except Exception as e:
            print(f"  변위 추출 실패 ({combo_name}): {e}")
            return pd.DataFrame()

    # ── 반력 추출 ─────────────────────────────
    def get_reactions(self, combo_name: str) -> pd.DataFrame:
        """GET /civil/post/reaction"""
        try:
            raw = self.client.get(
                f"/civil/post/reaction?LCNAME={combo_name}"
            )
            assign = raw.get("Assign", {})
            rows = []
            for node_id, vals in assign.items():
                react = vals.get("REACT", [0]*6)
                rows.append({
                    "NodeID": int(node_id),
                    "Combo" : combo_name,
                    "Rx"    : react[0] if len(react) > 0 else 0.0,
                    "Ry"    : react[1] if len(react) > 1 else 0.0,
                    "Rz"    : react[2] if len(react) > 2 else 0.0,
                    "Mrx"   : react[3] if len(react) > 3 else 0.0,
                    "Mry"   : react[4] if len(react) > 4 else 0.0,
                    "Mrz"   : react[5] if len(react) > 5 else 0.0,
                })
            return pd.DataFrame(rows)
        except Exception as e:
            print(f"  반력 추출 실패 ({combo_name}): {e}")
            return pd.DataFrame()

    # ── 모든 조합 일괄 추출 ───────────────────
    def extract_all_combos(self, combos: List[LoadCombination]) -> dict:
        """
        모든 조합에 대한 결과 추출 → 통합 DataFrame 반환
        반환: {"forces": df, "displacements": df, "reactions": df}
        """
        all_forces = []
        all_disps  = []
        all_reacts = []

        print(f"\n📊 결과 추출 시작 ({len(combos)}개 조합)\n")

        for i, combo in enumerate(combos, 1):
            print(f"  [{i:3d}/{len(combos)}] {combo.name}", end=" ")

            f = self.get_beam_forces(combo.name)
            d = self.get_displacements(combo.name)
            r = self.get_reactions(combo.name)

            if not f.empty: all_forces.append(f)
            if not d.empty: all_disps.append(d)
            if not r.empty: all_reacts.append(r)

            # combo_type, limit_state 컬럼 추가
            for df_list in [all_forces, all_disps, all_reacts]:
                if df_list:
                    df_list[-1]["ComboType"]   = combo.combo_type
                    df_list[-1]["LimitState"]  = combo.limit_state

            print("✅")

        results = {
            "forces"       : pd.concat(all_forces, ignore_index=True) if all_forces else pd.DataFrame(),
            "displacements": pd.concat(all_disps,  ignore_index=True) if all_disps  else pd.DataFrame(),
            "reactions"    : pd.concat(all_reacts, ignore_index=True) if all_reacts else pd.DataFrame(),
        }

        print(f"\n✅ 결과 추출 완료")
        print(f"   부재력 행수: {len(results['forces'])}")
        print(f"   변위   행수: {len(results['displacements'])}")
        print(f"   반력   행수: {len(results['reactions'])}")
        return results


# ─────────────────────────────────────────────
# 2. Breakdown 분석기
# ─────────────────────────────────────────────
class BreakdownAnalyzer:
    """조합별/부재별 Breakdown 테이블 및 Envelope 생성"""

    def __init__(self, results: dict):
        self.forces = results.get("forces", pd.DataFrame())
        self.disps  = results.get("displacements", pd.DataFrame())
        self.reacts = results.get("reactions", pd.DataFrame())

    # ── 부재별 Envelope (최대/최소) ───────────
    def force_envelope(self, limit_state: str = "ULS") -> pd.DataFrame:
        """ULS 또는 SLS 기준 부재별 최대/최소 부재력"""
        if self.forces.empty:
            return pd.DataFrame()

        df = self.forces[self.forces["LimitState"] == limit_state]
        if df.empty:
            return pd.DataFrame()

        agg = df.groupby("ElemID").agg(
            Axial_max  =("Axial",   "max"),
            Axial_min  =("Axial",   "min"),
            ShearY_max =("ShearY",  "max"),
            ShearY_min =("ShearY",  "min"),
            ShearZ_max =("ShearZ",  "max"),
            ShearZ_min =("ShearZ",  "min"),
            Moment_max =("MomentZ", "max"),
            Moment_min =("MomentZ", "min"),
        ).reset_index()
        return agg

    # ── 조합별 최대 모멘트 부재 ───────────────
    def critical_elements(self, top_n: int = 10) -> pd.DataFrame:
        """모멘트 기준 상위 N개 임계 부재"""
        if self.forces.empty:
            return pd.DataFrame()
        df = self.forces.copy()
        df["AbsMoment"] = df["MomentZ"].abs()
        return (df.sort_values("AbsMoment", ascending=False)
                  .head(top_n)
                  [["ElemID", "Combo", "ComboType", "LimitState",
                    "Axial", "ShearZ", "MomentZ"]]
                  .reset_index(drop=True))

    # ── 최대 변위 노드 ────────────────────────
    def critical_displacements(self, top_n: int = 10) -> pd.DataFrame:
        """전체 변위 기준 상위 N개 노드"""
        if self.disps.empty:
            return pd.DataFrame()
        return (self.disps.sort_values("D_total", ascending=False)
                          .head(top_n)
                          [["NodeID", "Combo", "LimitState", "Dx", "Dy", "Dz", "D_total"]]
                          .reset_index(drop=True))

    # ── 반력 합계 (전역 평형 확인) ────────────
    def reaction_sum(self) -> pd.DataFrame:
        """조합별 반력 합계 (전역 평형 검증)"""
        if self.reacts.empty:
            return pd.DataFrame()
        return (self.reacts.groupby("Combo")[["Rx", "Ry", "Rz"]]
                            .sum().reset_index())


# ─────────────────────────────────────────────
# 3. 시각화
# ─────────────────────────────────────────────
class ResultVisualizer:
    """Breakdown 차트 생성 (matplotlib)"""

    COLORS = {
        "ULS_6.10" : "#E24B4A",
        "ULS_6.10a": "#BA7517",
        "ULS_6.10b": "#E85D24",
        "SLS_CHAR" : "#378ADD",
        "SLS_FREQ" : "#1D9E75",
        "SLS_QP"   : "#639922",
    }

    def __init__(self, analyzer: BreakdownAnalyzer, output_dir: str = "."):
        self.ana        = analyzer
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def plot_force_breakdown(self,
                             elem_ids: Optional[List[int]] = None,
                             save_path: Optional[str] = None) -> str:
        """선택 부재의 조합별 모멘트 Breakdown 바 차트"""
        if self.ana.forces.empty:
            print("⚠️  부재력 데이터 없음")
            return ""

        df = self.ana.forces.copy()
        if elem_ids:
            df = df[df["ElemID"].isin(elem_ids)]
        if df.empty:
            return ""

        # 부재별로 subplot
        elem_list = sorted(df["ElemID"].unique())[:6]  # 최대 6개
        n_elem    = len(elem_list)
        fig, axes = plt.subplots(1, n_elem, figsize=(4 * n_elem, 5),
                                 constrained_layout=True)
        if n_elem == 1:
            axes = [axes]

        fig.suptitle("Bending Moment Breakdown by Load Combination (EN 1990)",
                     fontsize=11, fontweight="bold", y=1.02)

        for ax, eid in zip(axes, elem_list):
            sub = df[df["ElemID"] == eid].copy()
            sub = sub.sort_values("MomentZ", key=abs, ascending=False)

            colors = [self.COLORS.get(ct, "#888") for ct in sub["ComboType"]]
            bars   = ax.barh(range(len(sub)), sub["MomentZ"],
                             color=colors, edgecolor="none", height=0.65)

            ax.set_yticks(range(len(sub)))
            ax.set_yticklabels(sub["Combo"], fontsize=7)
            ax.set_xlabel("Mz [kNm]", fontsize=8)
            ax.set_title(f"Element {eid}", fontsize=9, fontweight="bold")
            ax.axvline(0, color="black", linewidth=0.5)
            ax.tick_params(axis="x", labelsize=7)

        # 범례
        legend_patches = [
            mpatches.Patch(color=c, label=k)
            for k, c in self.COLORS.items()
        ]
        fig.legend(handles=legend_patches, loc="lower center",
                   ncol=3, fontsize=7, bbox_to_anchor=(0.5, -0.08))

        path = save_path or str(self.output_dir / "force_breakdown.png")
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"✅ 차트 저장: {path}")
        return path

    def plot_displacement_envelope(self, save_path: Optional[str] = None) -> str:
        """SLS 조합별 최대 변위 Envelope 차트"""
        if self.ana.disps.empty:
            return ""

        df = self.ana.disps[self.ana.disps["LimitState"] == "SLS"].copy()
        if df.empty:
            return ""

        pivot = (df.groupby(["NodeID", "ComboType"])["D_total"]
                   .max().unstack(fill_value=0))

        fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)
        pivot.plot(kind="bar", ax=ax, width=0.75,
                   color=[self.COLORS.get(c, "#aaa") for c in pivot.columns],
                   edgecolor="none")

        ax.set_xlabel("Node ID", fontsize=9)
        ax.set_ylabel("Total Displacement [m]", fontsize=9)
        ax.set_title("SLS Displacement Envelope by Combination Type (EN 1990)",
                     fontsize=10, fontweight="bold")
        ax.legend(fontsize=8)
        ax.tick_params(axis="x", labelsize=7, rotation=45)

        path = save_path or str(self.output_dir / "displacement_envelope.png")
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"✅ 차트 저장: {path}")
        return path

    def export_breakdown_excel(self, save_path: Optional[str] = None) -> str:
        """Breakdown 결과를 Excel로 내보내기"""
        path = save_path or str(self.output_dir / "breakdown_results.xlsx")

        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            if not self.ana.forces.empty:
                self.ana.forces.to_excel(writer, sheet_name="BeamForces", index=False)
                self.ana.force_envelope("ULS").to_excel(writer, sheet_name="ULS_Envelope", index=False)
                self.ana.force_envelope("SLS").to_excel(writer, sheet_name="SLS_Envelope", index=False)
                self.ana.critical_elements(20).to_excel(writer, sheet_name="Critical_Elements", index=False)

            if not self.ana.disps.empty:
                self.ana.disps.to_excel(writer, sheet_name="Displacements", index=False)
                self.ana.critical_displacements(20).to_excel(writer, sheet_name="Critical_Disp", index=False)

            if not self.ana.reacts.empty:
                self.ana.reacts.to_excel(writer, sheet_name="Reactions", index=False)
                self.ana.reaction_sum().to_excel(writer, sheet_name="ReactionSum", index=False)

        print(f"✅ Excel 저장: {path}")
        return path


# ─────────────────────────────────────────────
# 4. 실행
# ─────────────────────────────────────────────
if __name__ == "__main__":
    from phase4_apply_and_run import run_phase4

    client = create_client(
        base_url="http://127.0.0.1:8090",
        mapi_key="YOUR_MAPI_KEY_HERE"
    )

    # Phase 1~4 실행 후 조합 목록 받기
    combos = run_phase4(client, country="EN", run_analysis=True)

    # 결과 추출
    extractor = ResultExtractor(client)
    results   = extractor.extract_all_combos(combos)

    # Breakdown 분석
    analyzer  = BreakdownAnalyzer(results)

    print("\n" + "="*55)
    print("📋 임계 부재 (모멘트 상위 10개)")
    print("="*55)
    print(analyzer.critical_elements(10).to_string(index=False))

    print("\n" + "="*55)
    print("📋 최대 변위 노드 상위 10개")
    print("="*55)
    print(analyzer.critical_displacements(10).to_string(index=False))

    # 시각화 & Excel 내보내기
    viz = ResultVisualizer(analyzer, output_dir="./results")
    viz.plot_force_breakdown()
    viz.plot_displacement_envelope()
    viz.export_breakdown_excel()
