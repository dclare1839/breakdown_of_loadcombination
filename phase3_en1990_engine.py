"""
Phase 3: Eurocode EN 1990 Load Combination Engine  (v2 — Table A1.1 통합)
─────────────────────────────────────────────────────────────────────────
변경 내역 (v2):
  - EN 1990 Table A1.1의 Cat.A~H 세분화 ψ 계수 내장
  - 고도별 적설하중 구분 (Snow_H1000 / Snow_Lo)
  - NA_DATABASE에 UK(BS EN) 추가, DE 계수 정밀화
  - Load Case에 EN1990_Category 컬럼 추가 지원
    (미지정 시 EN1990_Action 기반 fallback 유지)

지원 조합:
  ULS  │ STR/GEO  │ Eq. 6.10 / 6.10a / 6.10b
  SLS  │ Characteristic / Frequent / Quasi-permanent

국가별 NA:  EN / UK / DE / PL / HU / RO / HR / AL
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import pandas as pd


# ═══════════════════════════════════════════════════════════════
# 1.  EN 1990 Table A1.1 ─ ψ 계수 마스터 테이블
#     key: EN1990_Category  (Load Case 정의 시 사용)
# ═══════════════════════════════════════════════════════════════

@dataclass
class PsiRow:
    """단일 하중 카테고리의 ψ₀ / ψ₁ / ψ₂ 값"""
    category   : str
    action_type: str   # G / Qi / W / T / S / E  (엔진 내부 분류)
    psi_0: float
    psi_1: float
    psi_2: float
    note : str = ""


# ── EN 1990 Table A1.1 기본값 (국가별 override 전) ──────────────
PSI_TABLE_EN: Dict[str, PsiRow] = {
    # ── Imposed Loads (EN 1991-1-1) ─────────────────────────────
    "Cat_A": PsiRow("Cat. A – Domestic/residential",  "Qi", 0.7, 0.5, 0.3),
    "Cat_B": PsiRow("Cat. B – Office areas",          "Qi", 0.7, 0.5, 0.3),
    "Cat_C": PsiRow("Cat. C – Congregation areas",    "Qi", 0.7, 0.7, 0.6),
    "Cat_D": PsiRow("Cat. D – Shopping areas",        "Qi", 0.7, 0.7, 0.6),
    "Cat_E": PsiRow("Cat. E – Storage areas",         "Qi", 1.0, 0.9, 0.8),
    "Cat_F": PsiRow("Cat. F – Traffic ≤30 kN",        "Qi", 0.7, 0.7, 0.6),
    "Cat_G": PsiRow("Cat. G – Traffic 30–160 kN",     "Qi", 0.7, 0.5, 0.3),
    "Cat_H": PsiRow("Cat. H – Roofs (inaccessible)",  "Qi", 0.0, 0.0, 0.0),
    # ── Snow (EN 1991-1-3) ───────────────────────────────────────
    "Snow_H1000_Nordic": PsiRow(
        "Snow H>1000m (FI/IS/NO/SE)", "S", 0.70, 0.50, 0.20,
        "Finland, Iceland, Norway, Sweden"),
    "Snow_H1000": PsiRow(
        "Snow H>1000m (other CEN)",   "S", 0.70, 0.50, 0.20),
    "Snow_Lo": PsiRow(
        "Snow H≤1000m (other CEN)",   "S", 0.50, 0.20, 0.00),
    # ── Wind (EN 1991-1-4) ───────────────────────────────────────
    "Wind": PsiRow(
        "Wind loads on buildings",    "W", 0.6, 0.2, 0.0),
    # ── Temperature (EN 1991-1-5) ────────────────────────────────
    "Temp": PsiRow(
        "Temperature (non-fire)",     "T", 0.6, 0.5, 0.0,
        "ψ₀ may→0 for EQU/STR/GEO per NA"),
    # ── Fallback (카테고리 미지정 시) ────────────────────────────
    "Qi":   PsiRow("Variable (generic)",  "Qi", 0.7, 0.5, 0.3),
    "W":    PsiRow("Wind (generic)",      "W",  0.6, 0.2, 0.0),
    "T":    PsiRow("Temperature (generic)","T", 0.6, 0.5, 0.0),
    "S":    PsiRow("Snow (generic)",      "S",  0.5, 0.2, 0.0),
}

# ── UK National Annex 차이 적용 ─────────────────────────────────
# (EN 대비 변경되는 항목만 재정의)
PSI_TABLE_UK: Dict[str, PsiRow] = {
    **PSI_TABLE_EN,
    "Cat_H": PsiRow("Cat. H – Roofs (accessible, UK NA)", "Qi", 0.7, 0.0, 0.0,
                    "UK NA: accessible roof ψ₀=0.7"),
    "Wind":  PsiRow("Wind loads (UK NA)", "W", 0.5, 0.2, 0.0,
                    "UK NA: ψ₀=0.5"),
}

# ── DE National Annex 차이 적용 ─────────────────────────────────
PSI_TABLE_DE: Dict[str, PsiRow] = {
    **PSI_TABLE_EN,
    "Cat_F": PsiRow("Cat. F – Traffic ≤30kN (DE NA)", "Qi", 0.7, 0.7, 0.5,
                    "DIN EN: ψ₂=0.5"),
    "Temp":  PsiRow("Temperature (DE NA)", "T", 0.6, 0.5, 0.0),
}


# ═══════════════════════════════════════════════════════════════
# 2.  국가별 γ (Gamma) 부분안전계수 + ψ 테이블 묶음
# ═══════════════════════════════════════════════════════════════

@dataclass
class NAFactors:
    """EN 1990 국가별 National Annex 계수 컨테이너"""
    country    : str
    gamma_G    : float = 1.35   # Permanent – unfavourable  (Table A1.2B)
    gamma_G_fav: float = 1.00   # Permanent – favourable
    gamma_Q    : float = 1.50   # Variable action
    xi         : float = 0.85   # Reduction factor ξ (Eq. 6.10b)
    psi_table  : Dict[str, PsiRow] = field(default_factory=dict)

    def __post_init__(self):
        if not self.psi_table:
            self.psi_table = PSI_TABLE_EN

    # ── 카테고리 키로 ψ 조회 ────────────────────────────────────
    def psi(self, category: str, which: str) -> float:
        """
        category : EN1990_Category 컬럼 값 (예: "Cat_B", "Wind", "Snow_Lo")
                   또는 EN1990_Action 값 (예: "Qi", "W", "T") — fallback
        which    : "psi_0" / "psi_1" / "psi_2"
        """
        row = self.psi_table.get(category) or self.psi_table.get("Qi")
        return getattr(row, which, 0.7)

    def psi_0(self, cat: str) -> float: return self.psi(cat, "psi_0")
    def psi_1(self, cat: str) -> float: return self.psi(cat, "psi_1")
    def psi_2(self, cat: str) -> float: return self.psi(cat, "psi_2")

    def action_type(self, cat: str) -> str:
        """카테고리의 내부 액션 유형 반환 (G/Qi/W/T/S/E)"""
        row = self.psi_table.get(cat)
        return row.action_type if row else "Qi"


# ── NA 데이터베이스 ─────────────────────────────────────────────
NA_DATABASE: Dict[str, NAFactors] = {
    "EN": NAFactors(country="EN (Eurocode default)",
                    psi_table=PSI_TABLE_EN),
    "UK": NAFactors(country="United Kingdom (BS EN)",
                    gamma_G=1.35, gamma_Q=1.50, xi=0.85,
                    psi_table=PSI_TABLE_UK),
    "DE": NAFactors(country="Germany (DIN EN)",
                    gamma_G=1.35, gamma_Q=1.50, xi=0.85,
                    psi_table=PSI_TABLE_DE),
    "PL": NAFactors(country="Poland (PN-EN)",
                    gamma_G=1.35, gamma_Q=1.50, xi=0.85,
                    psi_table=PSI_TABLE_EN),
    "HU": NAFactors(country="Hungary (MSZ EN)",
                    gamma_G=1.35, gamma_Q=1.50, xi=0.85,
                    psi_table=PSI_TABLE_EN),
    "RO": NAFactors(country="Romania (SR EN)",
                    gamma_G=1.35, gamma_Q=1.50, xi=0.85,
                    psi_table=PSI_TABLE_EN),
    "HR": NAFactors(country="Croatia (HRN EN)",
                    gamma_G=1.35, gamma_Q=1.50, xi=0.85,
                    psi_table=PSI_TABLE_EN),
    "AL": NAFactors(country="Albania (KTP EN)",
                    gamma_G=1.35, gamma_Q=1.50, xi=0.85,
                    psi_table=PSI_TABLE_EN),
}


# ═══════════════════════════════════════════════════════════════
# 3.  Load Combination 결과 컨테이너
# ═══════════════════════════════════════════════════════════════

@dataclass
class LoadCombination:
    """단일 Load Combination"""
    name       : str
    combo_type : str          # ULS_6.10 / ULS_6.10a / ULS_6.10b / SLS_CHAR / SLS_FREQ / SLS_QP
    limit_state: str          # ULS / SLS
    factors    : Dict[str, float]   # {LC_Name: factor}
    description: str = ""

    def to_civil_nx_payload(self) -> dict:
        """Civil NX POST /lcom 페이로드 생성"""
        items = [
            {"LCNAME": lc, "FACTOR": round(f, 4)}
            for lc, f in self.factors.items() if abs(f) > 1e-9
        ]
        return {
            "Assign": {
                self.name: {
                    "NAME"  : self.name,
                    "iTYPE" : 0 if self.limit_state == "ULS" else 1,
                    "ACTIVE": "YES",
                    "ITEMS" : items,
                }
            }
        }


# ═══════════════════════════════════════════════════════════════
# 4.  EN 1990 조합식 엔진
# ═══════════════════════════════════════════════════════════════

class EN1990Engine:
    """
    EN 1990 하중 조합식 자동 생성 엔진  (v2)

    Parameters
    ----------
    load_cases : pd.DataFrame
        필수 컬럼 : ID, Name, EN1990_Action  (G / Qi / W / T / S / E)
        선택 컬럼 : EN1990_Category          (Cat_A … Cat_H, Wind, Snow_Lo, Temp …)
                    지정하면 Table A1.1 정밀 ψ 계수 자동 적용
    country    : str    NA 국가 코드 (EN / UK / DE / PL / HU / RO / HR / AL)
    eq_method  : str    ULS 방정식: "6.10" / "6.10ab" / "all"
    """

    def __init__(self,
                 load_cases: pd.DataFrame,
                 country   : str = "EN",
                 eq_method : str = "6.10ab"):

        # EN1990_Category 컬럼이 없으면 EN1990_Action으로 채움 (하위 호환)
        if "EN1990_Category" not in load_cases.columns:
            load_cases = load_cases.copy()
            load_cases["EN1990_Category"] = load_cases["EN1990_Action"]

        self.lc_df     = load_cases.reset_index(drop=True)
        self.na        = NA_DATABASE.get(country, NA_DATABASE["EN"])
        self.eq_method = eq_method

        # 액션 분류 (G=영구, 나머지=변수)
        self.G_cases = self._filter("G")
        self.Q_cases = [
            lc for lc in self.lc_df.to_dict("records")
            if lc["EN1990_Action"] != "G"
        ]

        print(f"🔧 EN1990 엔진 v2 초기화: {self.na.country}")
        print(f"   국가별 NA 적용: {country}")
        print(f"   G  (영구하중): {[lc['Name'] for lc in self.G_cases]}")
        print(f"   Q  (변수하중): {[lc['Name'] for lc in self.Q_cases]}")
        print(f"   ψ 테이블 카테고리 수: {len(self.na.psi_table)}")
        self._print_lc_psi_table()

    # ── 내부 유틸 ──────────────────────────────────────────────
    def _filter(self, action: str) -> List[dict]:
        mask = self.lc_df["EN1990_Action"] == action
        return self.lc_df[mask].to_dict("records")

    def _cat(self, lc: dict) -> str:
        """Load Case의 EN1990_Category 반환"""
        return lc.get("EN1990_Category", lc.get("EN1990_Action", "Qi"))

    def _g_factors(self, unfav: bool = True) -> Dict[str, float]:
        γ = self.na.gamma_G if unfav else self.na.gamma_G_fav
        return {lc["Name"]: γ for lc in self.G_cases}

    def _print_lc_psi_table(self):
        """초기화 시 각 LC의 ψ 계수 출력"""
        print(f"\n   {'LC Name':<12} {'Category':<22} {'ψ₀':>5} {'ψ₁':>5} {'ψ₂':>5}")
        print("   " + "-" * 52)
        for lc in self.Q_cases:
            cat = self._cat(lc)
            print(f"   {lc['Name']:<12} {cat:<22} "
                  f"{self.na.psi_0(cat):>5.2f} "
                  f"{self.na.psi_1(cat):>5.2f} "
                  f"{self.na.psi_2(cat):>5.2f}")
        print()

    # ── ULS Eq. 6.10 ───────────────────────────────────────────
    def _uls_610(self, lead: dict, others: List[dict],
                 idx: int) -> LoadCombination:
        f = self._g_factors(unfav=True)
        f[lead["Name"]] = self.na.gamma_Q
        for q in others:
            f[q["Name"]] = self.na.gamma_Q * self.na.psi_0(self._cat(q))
        return LoadCombination(
            name        = f"ULS_6.10_{idx:02d}_Lead_{lead['Name']}",
            combo_type  = "ULS_6.10",
            limit_state = "ULS",
            factors     = f,
            description = (f"ULS Eq.6.10 │ Lead: {lead['Name']} "
                           f"│ γG={self.na.gamma_G} γQ={self.na.gamma_Q}"),
        )

    # ── ULS Eq. 6.10a ──────────────────────────────────────────
    def _uls_610a(self, qs: List[dict], idx: int) -> LoadCombination:
        f = self._g_factors(unfav=True)
        for q in qs:
            f[q["Name"]] = self.na.gamma_Q * self.na.psi_0(self._cat(q))
        return LoadCombination(
            name        = f"ULS_6.10a_{idx:02d}",
            combo_type  = "ULS_6.10a",
            limit_state = "ULS",
            factors     = f,
            description = "ULS Eq.6.10a │ All Q with γQ·ψ₀",
        )

    # ── ULS Eq. 6.10b ──────────────────────────────────────────
    def _uls_610b(self, lead: dict, others: List[dict],
                  idx: int) -> LoadCombination:
        f = {lc["Name"]: self.na.xi * self.na.gamma_G for lc in self.G_cases}
        f[lead["Name"]] = self.na.gamma_Q
        for q in others:
            f[q["Name"]] = self.na.gamma_Q * self.na.psi_0(self._cat(q))
        return LoadCombination(
            name        = f"ULS_6.10b_{idx:02d}_Lead_{lead['Name']}",
            combo_type  = "ULS_6.10b",
            limit_state = "ULS",
            factors     = f,
            description = (f"ULS Eq.6.10b │ ξ={self.na.xi} "
                           f"│ Lead: {lead['Name']}"),
        )

    # ── SLS Characteristic  Eq. 6.14 ───────────────────────────
    def _sls_char(self, lead: dict, others: List[dict],
                  idx: int) -> LoadCombination:
        f = {lc["Name"]: 1.0 for lc in self.G_cases}
        f[lead["Name"]] = 1.0
        for q in others:
            f[q["Name"]] = self.na.psi_0(self._cat(q))
        return LoadCombination(
            name        = f"SLS_CHAR_{idx:02d}_Lead_{lead['Name']}",
            combo_type  = "SLS_CHAR",
            limit_state = "SLS",
            factors     = f,
            description = f"SLS Characteristic Eq.6.14 │ Lead: {lead['Name']}",
        )

    # ── SLS Frequent  Eq. 6.15 ─────────────────────────────────
    def _sls_freq(self, lead: dict, others: List[dict],
                  idx: int) -> LoadCombination:
        f = {lc["Name"]: 1.0 for lc in self.G_cases}
        f[lead["Name"]] = self.na.psi_1(self._cat(lead))
        for q in others:
            f[q["Name"]] = self.na.psi_2(self._cat(q))
        return LoadCombination(
            name        = f"SLS_FREQ_{idx:02d}_Lead_{lead['Name']}",
            combo_type  = "SLS_FREQ",
            limit_state = "SLS",
            factors     = f,
            description = f"SLS Frequent Eq.6.15 │ Lead: {lead['Name']}",
        )

    # ── SLS Quasi-permanent  Eq. 6.16 ──────────────────────────
    def _sls_qp(self) -> LoadCombination:
        f = {lc["Name"]: 1.0 for lc in self.G_cases}
        for q in self.Q_cases:
            f[q["Name"]] = self.na.psi_2(self._cat(q))
        return LoadCombination(
            name        = "SLS_QP_01",
            combo_type  = "SLS_QP",
            limit_state = "SLS",
            factors     = f,
            description = "SLS Quasi-permanent Eq.6.16 │ Σ ψ₂·Qki",
        )

    # ── 전체 조합 생성 ──────────────────────────────────────────
    def generate_all(self) -> List[LoadCombination]:
        """모든 ULS/SLS 조합 자동 생성"""
        combos: List[LoadCombination] = []

        if not self.Q_cases:
            print("⚠️  Variable load case 없음 → G-only ULS 조합 생성")
            combos.append(LoadCombination(
                name="ULS_G_only", combo_type="ULS_6.10",
                limit_state="ULS", factors=self._g_factors(unfav=True),
                description="ULS │ Permanent loads only",
            ))
            return combos

        for idx, lead in enumerate(self.Q_cases, start=1):
            others = [q for q in self.Q_cases if q["Name"] != lead["Name"]]

            if self.eq_method in ("6.10", "all"):
                combos.append(self._uls_610(lead, others, idx))

            if self.eq_method in ("6.10ab", "all"):
                combos.append(self._uls_610a(self.Q_cases, idx))
                combos.append(self._uls_610b(lead, others, idx))

            combos.append(self._sls_char(lead, others, idx))
            combos.append(self._sls_freq(lead, others, idx))

        combos.append(self._sls_qp())

        # 중복 제거
        seen, unique = set(), []
        for c in combos:
            if c.name not in seen:
                seen.add(c.name)
                unique.append(c)

        print(f"✅ 총 {len(unique)}개 조합 생성됨")
        return unique

    def summary_df(self, combos: List[LoadCombination]) -> pd.DataFrame:
        rows = []
        for c in combos:
            row = {"Name": c.name, "Type": c.combo_type,
                   "LimitState": c.limit_state, "Description": c.description}
            row.update({f"F_{k}": v for k, v in c.factors.items()})
            rows.append(row)
        return pd.DataFrame(rows)

    @staticmethod
    def psi_reference_df(country: str = "EN") -> pd.DataFrame:
        """지정 국가의 ψ 계수 테이블을 DataFrame으로 반환 (검토용)"""
        na = NA_DATABASE.get(country, NA_DATABASE["EN"])
        rows = [
            {
                "Category"   : k,
                "Description": v.category,
                "ActionType" : v.action_type,
                "ψ₀"        : v.psi_0,
                "ψ₁"        : v.psi_1,
                "ψ₂"        : v.psi_2,
                "Note"       : v.note,
            }
            for k, v in na.psi_table.items()
        ]
        return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════
# 5.  실행 예시
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":

    # ── 샘플 Load Case: EN1990_Category 컬럼 추가 ────────────────
    #    Category 미지정 시 EN1990_Action이 fallback으로 사용됨
    sample_lc = pd.DataFrame([
        # 영구하중 (G) — 카테고리 불필요
        {"ID": 1, "Name": "SW",    "Type": "ST", "EN1990_Action": "G",  "EN1990_Category": "G"},
        {"ID": 2, "Name": "SDL",   "Type": "ST", "EN1990_Action": "G",  "EN1990_Category": "G"},
        # 활하중 — Cat.B (오피스)로 세분화
        {"ID": 3, "Name": "LL",    "Type": "LV", "EN1990_Action": "Qi", "EN1990_Category": "Cat_B"},
        # 풍하중
        {"ID": 4, "Name": "WL_X",  "Type": "WL", "EN1990_Action": "W",  "EN1990_Category": "Wind"},
        # 적설 (고도 ≤ 1000m)
        {"ID": 5, "Name": "SL",    "Type": "SL", "EN1990_Action": "S",  "EN1990_Category": "Snow_Lo"},
        # 온도
        {"ID": 6, "Name": "TMP",   "Type": "TL", "EN1990_Action": "T",  "EN1990_Category": "Temp"},
    ])

    # ── EN 기본 ──────────────────────────────────────────────────
    print("=" * 65)
    print("[ EN 기본 NA ]")
    engine_en = EN1990Engine(sample_lc, country="EN", eq_method="6.10ab")
    combos_en = engine_en.generate_all()

    # ── UK NA 비교 ───────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("[ UK NA — Wind ψ₀: 0.6→0.5 ]")
    engine_uk = EN1990Engine(sample_lc, country="UK", eq_method="6.10ab")
    combos_uk = engine_uk.generate_all()

    # ── ψ 계수 테이블 출력 ───────────────────────────────────────
    print("\n" + "=" * 65)
    print("[ EN 기준 ψ 계수 전체 테이블 ]")
    psi_df = EN1990Engine.psi_reference_df("EN")
    print(psi_df[["Category", "Description", "ψ₀", "ψ₁", "ψ₂"]].to_string(index=False))

    # ── 조합 요약 출력 ───────────────────────────────────────────
    print("\n" + "=" * 65)
    print("[ 조합 요약 (EN, 6.10ab) ]")
    summary = engine_en.summary_df(combos_en)
    factor_cols = [c for c in summary.columns if c.startswith("F_")]
    print(summary[["Name", "Type", "LimitState"] + factor_cols].to_string(index=False))
