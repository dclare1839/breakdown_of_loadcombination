"""
Phase 3: Eurocode EN 1990 Load Combination Engine
─────────────────────────────────────────────────
지원 조합:
  ULS  │ STR/GEO  │ Eq. 6.10 / 6.10a / 6.10b
  SLS  │ Characteristic / Frequent / Quasi-permanent

국가별 NA(National Annex) 계수 내장:
  EN (기본), DE (DIN EN), PL (PN-EN), HU (MSZ EN),
  RO (SR EN), HR (HRN EN), AL (KTP EN)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import itertools
import pandas as pd


# ─────────────────────────────────────────────
# 1. 국가별 NA 계수 테이블
# ─────────────────────────────────────────────
@dataclass
class NAFactors:
    """EN 1990 국가별 National Annex 계수"""
    country : str
    gamma_G : float = 1.35   # Permanent action (unfav)
    gamma_G_fav: float = 1.0 # Permanent action (fav)
    gamma_Q : float = 1.50   # Variable action
    xi      : float = 0.85   # Reduction factor (Eq. 6.10b)
    psi_0   : Dict[str, float] = field(default_factory=dict)  # 조합계수
    psi_1   : Dict[str, float] = field(default_factory=dict)  # 빈도계수
    psi_2   : Dict[str, float] = field(default_factory=dict)  # 준영구계수

    def __post_init__(self):
        if not self.psi_0:
            self.psi_0 = {"Qi": 0.7, "W": 0.6, "T": 0.6}
        if not self.psi_1:
            self.psi_1 = {"Qi": 0.5, "W": 0.2, "T": 0.5}
        if not self.psi_2:
            self.psi_2 = {"Qi": 0.3, "W": 0.0, "T": 0.0}


# 국가별 NA 데이터베이스
NA_DATABASE: Dict[str, NAFactors] = {
    "EN": NAFactors(country="EN (Eurocode default)"),
    "DE": NAFactors(country="Germany (DIN EN)",
                    gamma_G=1.35, gamma_Q=1.50, xi=0.85,
                    psi_0={"Qi": 0.7, "W": 0.6, "T": 0.6},
                    psi_1={"Qi": 0.5, "W": 0.2, "T": 0.5},
                    psi_2={"Qi": 0.3, "W": 0.0, "T": 0.0}),
    "PL": NAFactors(country="Poland (PN-EN)",
                    gamma_G=1.35, gamma_Q=1.50, xi=0.85,
                    psi_0={"Qi": 0.7, "W": 0.6, "T": 0.6},
                    psi_1={"Qi": 0.5, "W": 0.2, "T": 0.5},
                    psi_2={"Qi": 0.3, "W": 0.0, "T": 0.0}),
    "HU": NAFactors(country="Hungary (MSZ EN)",
                    gamma_G=1.35, gamma_Q=1.50, xi=0.85,
                    psi_0={"Qi": 0.7, "W": 0.6, "T": 0.6},
                    psi_1={"Qi": 0.5, "W": 0.2, "T": 0.5},
                    psi_2={"Qi": 0.3, "W": 0.0, "T": 0.0}),
    "RO": NAFactors(country="Romania (SR EN)",
                    gamma_G=1.35, gamma_Q=1.50, xi=0.85,
                    psi_0={"Qi": 0.7, "W": 0.6, "T": 0.6},
                    psi_1={"Qi": 0.5, "W": 0.2, "T": 0.5},
                    psi_2={"Qi": 0.3, "W": 0.0, "T": 0.0}),
    "HR": NAFactors(country="Croatia (HRN EN)",
                    gamma_G=1.35, gamma_Q=1.50, xi=0.85,
                    psi_0={"Qi": 0.7, "W": 0.6, "T": 0.6},
                    psi_1={"Qi": 0.5, "W": 0.2, "T": 0.5},
                    psi_2={"Qi": 0.3, "W": 0.0, "T": 0.0}),
    "AL": NAFactors(country="Albania (KTP EN)",
                    gamma_G=1.35, gamma_Q=1.50, xi=0.85,
                    psi_0={"Qi": 0.7, "W": 0.6, "T": 0.6},
                    psi_1={"Qi": 0.5, "W": 0.2, "T": 0.5},
                    psi_2={"Qi": 0.3, "W": 0.0, "T": 0.0}),
}


# ─────────────────────────────────────────────
# 2. 조합 결과 컨테이너
# ─────────────────────────────────────────────
@dataclass
class LoadCombination:
    """단일 Load Combination"""
    name    : str
    combo_type: str                        # ULS_6.10 / ULS_6.10a / ULS_6.10b / SLS_CHAR / SLS_FREQ / SLS_QP
    limit_state: str                       # ULS / SLS
    factors : Dict[str, float]             # {LC_Name: factor}
    description: str = ""

    def to_civil_nx_payload(self) -> dict:
        """Civil NX POST /lcom 페이로드 생성"""
        load_items = []
        for lc_name, factor in self.factors.items():
            if abs(factor) > 1e-9:
                load_items.append({
                    "LCNAME": lc_name,
                    "FACTOR": round(factor, 4)
                })
        return {
            "Assign": {
                self.name: {
                    "NAME"   : self.name,
                    "iTYPE"  : 0 if self.limit_state == "ULS" else 1,
                    "ACTIVE" : "YES",
                    "ITEMS"  : load_items
                }
            }
        }


# ─────────────────────────────────────────────
# 3. EN 1990 조합식 엔진
# ─────────────────────────────────────────────
class EN1990Engine:
    """
    EN 1990 하중 조합식 자동 생성 엔진

    Parameters
    ----------
    load_cases : pd.DataFrame  (Phase 2 결과, 컬럼: ID, Name, EN1990_Action)
    country    : str           NA 국가 코드 (기본: "EN")
    eq_method  : str           ULS 방정식 선택: "6.10" / "6.10ab" / "all"
    """

    def __init__(self,
                 load_cases: pd.DataFrame,
                 country: str = "EN",
                 eq_method: str = "6.10ab"):
        self.lc_df     = load_cases
        self.na        = NA_DATABASE.get(country, NA_DATABASE["EN"])
        self.eq_method = eq_method

        # 액션별 LC 목록 분류
        self.G_cases  = self._filter_lc("G")    # Permanent
        self.Qi_cases = self._filter_lc("Qi")   # Variable (imposed)
        self.W_cases  = self._filter_lc("W")    # Wind
        self.T_cases  = self._filter_lc("T")    # Temperature
        self.Q_cases  = self.Qi_cases + self.W_cases + self.T_cases  # All variable

        print(f"🔧 EN1990 엔진 초기화: {self.na.country}")
        print(f"   G (고정)   : {[lc['Name'] for lc in self.G_cases]}")
        print(f"   Qi (활하중): {[lc['Name'] for lc in self.Qi_cases]}")
        print(f"   W (풍하중) : {[lc['Name'] for lc in self.W_cases]}")
        print(f"   T (온도)   : {[lc['Name'] for lc in self.T_cases]}")

    def _filter_lc(self, action: str) -> List[dict]:
        mask = self.lc_df["EN1990_Action"] == action
        return self.lc_df[mask][["ID", "Name", "EN1990_Action"]].to_dict("records")

    def _psi_0(self, action: str) -> float:
        return self.na.psi_0.get(action, 0.7)

    def _psi_1(self, action: str) -> float:
        return self.na.psi_1.get(action, 0.5)

    def _psi_2(self, action: str) -> float:
        return self.na.psi_2.get(action, 0.3)

    # ── 공통: G 계수 계산 ─────────────────────
    def _g_factors(self, unfav: bool = True) -> Dict[str, float]:
        γ = self.na.gamma_G if unfav else self.na.gamma_G_fav
        return {lc["Name"]: γ for lc in self.G_cases}

    # ─────────────────────────────────────────
    # ULS STR/GEO  Eq. 6.10
    # Σ γG·Gk + γQ·Qk1 + Σ γQ·ψ0i·Qki
    # ─────────────────────────────────────────
    def _uls_610(self, leading_q: dict, other_qs: List[dict],
                 combo_idx: int) -> LoadCombination:
        factors = self._g_factors(unfav=True)
        # Leading Q
        factors[leading_q["Name"]] = self.na.gamma_Q
        # Accompanying Q
        for q in other_qs:
            if q["Name"] != leading_q["Name"]:
                factors[q["Name"]] = self.na.gamma_Q * self._psi_0(q["EN1990_Action"])
        name = f"ULS_6.10_{combo_idx:02d}_Lead_{leading_q['Name']}"
        return LoadCombination(
            name=name, combo_type="ULS_6.10", limit_state="ULS",
            factors=factors,
            description=f"ULS Eq.6.10 │ Leading: {leading_q['Name']}"
        )

    # ─────────────────────────────────────────
    # ULS STR/GEO  Eq. 6.10a
    # Σ γG·Gk + Σ γQ·ψ0i·Qki
    # (모든 변수하중이 동반 작용, leading 없음)
    # ─────────────────────────────────────────
    def _uls_610a(self, active_qs: List[dict], combo_idx: int) -> LoadCombination:
        factors = self._g_factors(unfav=True)
        for q in active_qs:
            factors[q["Name"]] = self.na.gamma_Q * self._psi_0(q["EN1990_Action"])
        name = f"ULS_6.10a_{combo_idx:02d}"
        return LoadCombination(
            name=name, combo_type="ULS_6.10a", limit_state="ULS",
            factors=factors,
            description="ULS Eq.6.10a │ All Q with ψ0"
        )

    # ─────────────────────────────────────────
    # ULS STR/GEO  Eq. 6.10b
    # ξ·Σ γG·Gk + γQ·Qk1 + Σ γQ·ψ0i·Qki
    # ─────────────────────────────────────────
    def _uls_610b(self, leading_q: dict, other_qs: List[dict],
                  combo_idx: int) -> LoadCombination:
        factors = {lc["Name"]: self.na.xi * self.na.gamma_G
                   for lc in self.G_cases}
        factors[leading_q["Name"]] = self.na.gamma_Q
        for q in other_qs:
            if q["Name"] != leading_q["Name"]:
                factors[q["Name"]] = self.na.gamma_Q * self._psi_0(q["EN1990_Action"])
        name = f"ULS_6.10b_{combo_idx:02d}_Lead_{leading_q['Name']}"
        return LoadCombination(
            name=name, combo_type="ULS_6.10b", limit_state="ULS",
            factors=factors,
            description=f"ULS Eq.6.10b │ ξ={self.na.xi} │ Leading: {leading_q['Name']}"
        )

    # ─────────────────────────────────────────
    # SLS Characteristic
    # Gk + Qk1 + Σ ψ0i·Qki
    # ─────────────────────────────────────────
    def _sls_char(self, leading_q: dict, other_qs: List[dict],
                  combo_idx: int) -> LoadCombination:
        factors = {lc["Name"]: 1.0 for lc in self.G_cases}
        factors[leading_q["Name"]] = 1.0
        for q in other_qs:
            if q["Name"] != leading_q["Name"]:
                factors[q["Name"]] = self._psi_0(q["EN1990_Action"])
        name = f"SLS_CHAR_{combo_idx:02d}_Lead_{leading_q['Name']}"
        return LoadCombination(
            name=name, combo_type="SLS_CHAR", limit_state="SLS",
            factors=factors,
            description=f"SLS Characteristic │ Leading: {leading_q['Name']}"
        )

    # ─────────────────────────────────────────
    # SLS Frequent
    # Gk + ψ1·Qk1 + Σ ψ2i·Qki
    # ─────────────────────────────────────────
    def _sls_freq(self, leading_q: dict, other_qs: List[dict],
                  combo_idx: int) -> LoadCombination:
        factors = {lc["Name"]: 1.0 for lc in self.G_cases}
        factors[leading_q["Name"]] = self._psi_1(leading_q["EN1990_Action"])
        for q in other_qs:
            if q["Name"] != leading_q["Name"]:
                factors[q["Name"]] = self._psi_2(q["EN1990_Action"])
        name = f"SLS_FREQ_{combo_idx:02d}_Lead_{leading_q['Name']}"
        return LoadCombination(
            name=name, combo_type="SLS_FREQ", limit_state="SLS",
            factors=factors,
            description=f"SLS Frequent │ Leading: {leading_q['Name']}"
        )

    # ─────────────────────────────────────────
    # SLS Quasi-permanent
    # Gk + Σ ψ2i·Qki
    # ─────────────────────────────────────────
    def _sls_qp(self) -> LoadCombination:
        factors = {lc["Name"]: 1.0 for lc in self.G_cases}
        for q in self.Q_cases:
            factors[q["Name"]] = self._psi_2(q["EN1990_Action"])
        return LoadCombination(
            name="SLS_QP_01", combo_type="SLS_QP", limit_state="SLS",
            factors=factors,
            description="SLS Quasi-permanent │ Σ ψ2·Qki"
        )

    # ─────────────────────────────────────────
    # 전체 조합 생성 (메인 함수)
    # ─────────────────────────────────────────
    def generate_all(self) -> List[LoadCombination]:
        """모든 ULS/SLS 조합 자동 생성"""
        combos: List[LoadCombination] = []

        if not self.Q_cases:
            print("⚠️  Variable load case가 없습니다. G-only 조합만 생성됩니다.")
            # G-only ULS
            factors = self._g_factors(unfav=True)
            combos.append(LoadCombination(
                name="ULS_G_only", combo_type="ULS_6.10",
                limit_state="ULS", factors=factors,
                description="ULS │ Permanent loads only"
            ))
            return combos

        # 각 변수하중을 순차적으로 leading으로
        for idx, leading_q in enumerate(self.Q_cases, start=1):
            other_qs = [q for q in self.Q_cases if q["Name"] != leading_q["Name"]]

            if self.eq_method in ("6.10", "all"):
                combos.append(self._uls_610(leading_q, other_qs, idx))

            if self.eq_method in ("6.10ab", "all"):
                combos.append(self._uls_610a(self.Q_cases, idx))
                combos.append(self._uls_610b(leading_q, other_qs, idx))

            # SLS
            combos.append(self._sls_char(leading_q, other_qs, idx))
            combos.append(self._sls_freq(leading_q, other_qs, idx))

        combos.append(self._sls_qp())

        # 중복 제거 (이름 기준)
        seen = set()
        unique = []
        for c in combos:
            if c.name not in seen:
                seen.add(c.name)
                unique.append(c)

        print(f"\n✅ 총 {len(unique)}개 조합 생성됨")
        return unique

    def summary_df(self, combos: List[LoadCombination]) -> pd.DataFrame:
        """조합 요약 DataFrame 반환"""
        rows = []
        for c in combos:
            row = {"Name": c.name, "Type": c.combo_type,
                   "LimitState": c.limit_state, "Description": c.description}
            row.update({f"F_{k}": v for k, v in c.factors.items()})
            rows.append(row)
        return pd.DataFrame(rows)


# ─────────────────────────────────────────────
# 4. 실행
# ─────────────────────────────────────────────
if __name__ == "__main__":
    # ── 샘플 Load Case 데이터 (Phase 2 대체용) ──
    sample_lc = pd.DataFrame([
        {"ID": 1, "Name": "SW",    "Type": "ST", "EN1990_Action": "G"},
        {"ID": 2, "Name": "SDL",   "Type": "ST", "EN1990_Action": "G"},
        {"ID": 3, "Name": "LL",    "Type": "LV", "EN1990_Action": "Qi"},
        {"ID": 4, "Name": "WL_X",  "Type": "WL", "EN1990_Action": "W"},
        {"ID": 5, "Name": "TMP",   "Type": "TL", "EN1990_Action": "T"},
    ])

    # 선택 가능한 국가: EN, DE, PL, HU, RO, HR, AL
    engine = EN1990Engine(sample_lc, country="EN", eq_method="6.10ab")
    combos = engine.generate_all()

    print("\n" + "=" * 65)
    summary = engine.summary_df(combos)
    cols = ["Name", "Type", "LimitState", "F_SW", "F_SDL", "F_LL", "F_WL_X", "F_TMP"]
    print(summary[[c for c in cols if c in summary.columns]].to_string(index=False))
