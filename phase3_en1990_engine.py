"""
Phase 3: Eurocode EN 1990 Load Combination Engine  (v3 — Annex A2 교량 추가)
═════════════════════════════════════════════════════════════════════════════
변경 내역 (v3):
  - EN 1990 Annex A2 (교량) 조합식 엔진 추가  ← NEW
    · Table A2.1  ψ 계수 (gr1a~gr5 교통 하중 그룹)
    · ULS STR/GEO : Eq.6.10 / 6.10a / 6.10b
    · ULS EQU     : Eq.6.10 (별도 γ)
    · SLS Char / Freq / QP
    · Fatigue     : Eq.6.9  (피로 조합)  ← 교량 전용
    · 교통 하중 그룹 (Load Group) gr1a~gr5 자동 처리
  - 구조물 유형 선택: structure_type = "building" / "bridge"
  - 기존 건물(Annex A1) 엔진 100% 하위 호환 유지

지원 조합:
  건물  │ ULS STR/GEO Eq.6.10 / 6.10a / 6.10b  │ SLS Char / Freq / QP
  교량  │ ULS STR/GEO Eq.6.10 / 6.10a / 6.10b  │ SLS Char / Freq / QP
        │ ULS EQU Eq.6.10                        │ Fatigue Eq.6.9

국가별 NA:  EN / UK / DE / PL / HU / RO / HR / AL
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import pandas as pd


# ═══════════════════════════════════════════════════════════════════════════
# 0.  공통 데이터 구조
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class PsiRow:
    """단일 하중 카테고리의 ψ₀ / ψ₁ / ψ₂"""
    category   : str
    action_type: str   # G / Qi / W / T / S / E / TR / FT
    psi_0: float
    psi_1: float
    psi_2: float
    note : str = ""


@dataclass
class LoadCombination:
    """단일 Load Combination 결과 컨테이너"""
    name        : str
    combo_type  : str    # ULS_6.10 / ULS_6.10a / ULS_6.10b / ULS_EQU /
                         # SLS_CHAR / SLS_FREQ / SLS_QP / FATIGUE
    limit_state : str    # ULS / SLS / FATIGUE
    factors     : Dict[str, float]   # {LC_Name: factor}
    description : str = ""
    load_group  : str = ""           # 교량 전용: gr1a, gr2, gr3 …

    def to_civil_nx_payload(self) -> dict:
        items = [
            {"LCNAME": lc, "FACTOR": round(f, 4)}
            for lc, f in self.factors.items() if abs(f) > 1e-9
        ]
        itype = 0 if self.limit_state == "ULS" else (
                2 if self.limit_state == "FATIGUE" else 1)
        return {
            "Assign": {
                self.name: {
                    "NAME"  : self.name,
                    "iTYPE" : itype,
                    "ACTIVE": "YES",
                    "ITEMS" : items,
                }
            }
        }


# ═══════════════════════════════════════════════════════════════════════════
# 1.  EN 1990 Annex A1 — 건물 ψ 계수 테이블 (Table A1.1)
# ═══════════════════════════════════════════════════════════════════════════

PSI_TABLE_BUILDING_EN: Dict[str, PsiRow] = {
    # Imposed Loads (EN 1991-1-1)
    "Cat_A": PsiRow("Cat. A – Domestic/residential",  "Qi", 0.7, 0.5, 0.3),
    "Cat_B": PsiRow("Cat. B – Office areas",          "Qi", 0.7, 0.5, 0.3),
    "Cat_C": PsiRow("Cat. C – Congregation areas",    "Qi", 0.7, 0.7, 0.6),
    "Cat_D": PsiRow("Cat. D – Shopping areas",        "Qi", 0.7, 0.7, 0.6),
    "Cat_E": PsiRow("Cat. E – Storage areas",         "Qi", 1.0, 0.9, 0.8),
    "Cat_F": PsiRow("Cat. F – Traffic ≤30 kN",        "Qi", 0.7, 0.7, 0.6),
    "Cat_G": PsiRow("Cat. G – Traffic 30–160 kN",     "Qi", 0.7, 0.5, 0.3),
    "Cat_H": PsiRow("Cat. H – Roofs (inaccessible)",  "Qi", 0.0, 0.0, 0.0),
    # Snow (EN 1991-1-3)
    "Snow_H1000_Nordic": PsiRow("Snow H>1000m (FI/IS/NO/SE)", "S", 0.70, 0.50, 0.20,
                                 "Finland, Iceland, Norway, Sweden"),
    "Snow_H1000": PsiRow("Snow H>1000m (other CEN)",  "S", 0.70, 0.50, 0.20),
    "Snow_Lo"   : PsiRow("Snow H≤1000m (other CEN)",  "S", 0.50, 0.20, 0.00),
    # Wind (EN 1991-1-4)
    "Wind": PsiRow("Wind loads on buildings",         "W", 0.6, 0.2, 0.0),
    # Temperature (EN 1991-1-5)
    "Temp": PsiRow("Temperature (non-fire)",          "T", 0.6, 0.5, 0.0,
                   "ψ₀ may→0 per NA"),
    # Fallback
    "Qi": PsiRow("Variable (generic)",                "Qi", 0.7, 0.5, 0.3),
    "W" : PsiRow("Wind (generic)",                    "W",  0.6, 0.2, 0.0),
    "T" : PsiRow("Temperature (generic)",             "T",  0.6, 0.5, 0.0),
    "S" : PsiRow("Snow (generic)",                    "S",  0.5, 0.2, 0.0),
}

PSI_TABLE_BUILDING_UK: Dict[str, PsiRow] = {
    **PSI_TABLE_BUILDING_EN,
    "Cat_H": PsiRow("Cat. H – Roofs (accessible, UK NA)", "Qi", 0.7, 0.0, 0.0,
                    "UK NA: accessible roof ψ₀=0.7"),
    "Wind" : PsiRow("Wind loads (UK NA)",                 "W",  0.5, 0.2, 0.0,
                    "UK NA: ψ₀=0.5"),
}

PSI_TABLE_BUILDING_DE: Dict[str, PsiRow] = {
    **PSI_TABLE_BUILDING_EN,
    "Cat_F": PsiRow("Cat. F – Traffic ≤30kN (DE NA)", "Qi", 0.7, 0.7, 0.5,
                    "DIN EN: ψ₂=0.5"),
    "Temp" : PsiRow("Temperature (DE NA)",             "T",  0.6, 0.5, 0.0),
}


# ═══════════════════════════════════════════════════════════════════════════
# 2.  EN 1990 Annex A2 — 교량 ψ 계수 테이블 (Table A2.1)
# ═══════════════════════════════════════════════════════════════════════════
#
#  교량 하중 그룹 (EN 1991-2 Table 4.4a):
#   gr1a  LM1 (TS+UDL) + 보행자   — 도로교 주 하중 그룹
#   gr1b  LM1 단독 (집중하중만)
#   gr2   LM1 + 수평력(제동·가속)
#   gr3   보행자/자전거 전용
#   gr4   LM4 군중 하중
#   gr5   특수 차량 (LM3)
#   FT    피로 하중 (LM3/LM4 — Fatigue)
#
#  EN1990 Table A2.1 ψ 값
#   action_type 코드:
#     TR_gr1a  = 도로교 LM1 gr1a
#     TR_gr1b  = 도로교 LM1 gr1b
#     TR_gr2   = 수평력 gr2
#     TR_gr3   = 보행자/자전거 gr3
#     TR_gr4   = 군중 gr4
#     TR_gr5   = 특수차량 gr5
#     TR_rail  = 철도 하중 (EN 1991-2)
#     Wind_Br  = 교량 풍하중 (교통 동시작용 시 ψ₀=0.5)
#     Temp_Br  = 교량 온도
#     Snow_Br  = 교량 적설
#     FT       = 피로 하중 (계수 단독 1.0)

PSI_TABLE_BRIDGE_EN: Dict[str, PsiRow] = {
    # ── 도로교 교통 하중 (EN 1991-2) ──────────────────────────────
    "TR_gr1a": PsiRow(
        "gr1a – LM1 (TS+UDL) + pedestrian", "TR",
        psi_0=0.75, psi_1=0.75, psi_2=0.0,
        note="EN1990 Table A2.1 – leading traffic group"),
    "TR_gr1b": PsiRow(
        "gr1b – LM1 single axle",            "TR",
        psi_0=0.75, psi_1=0.75, psi_2=0.0,
        note="EN1990 Table A2.1"),
    "TR_gr2": PsiRow(
        "gr2 – Horizontal forces",            "TR",
        psi_0=0.0,  psi_1=0.0,  psi_2=0.0,
        note="EN1990 Table A2.1 – ψ=0 when not governing"),
    "TR_gr3": PsiRow(
        "gr3 – Pedestrian/cycle loads",       "TR",
        psi_0=0.0,  psi_1=0.4,  psi_2=0.0,
        note="EN1990 Table A2.1"),
    "TR_gr4": PsiRow(
        "gr4 – Crowd loading (LM4)",          "TR",
        psi_0=0.0,  psi_1=0.0,  psi_2=0.0,
        note="EN1990 Table A2.1 – rare/transient"),
    "TR_gr5": PsiRow(
        "gr5 – Special vehicles (LM3)",       "TR",
        psi_0=0.0,  psi_1=0.0,  psi_2=0.0,
        note="EN1990 Table A2.1 – rare"),
    # ── 철도교 교통 하중 (EN 1991-2) ─────────────────────────────
    "TR_rail": PsiRow(
        "Rail traffic (LM71 / SW/0)",         "TR",
        psi_0=0.80, psi_1=0.80, psi_2=0.0,
        note="EN1990 Table A2.1 – railway bridge"),
    # ── 풍하중 (교량) ─────────────────────────────────────────────
    "Wind_Br": PsiRow(
        "Wind – bridge (with traffic)",       "W",
        psi_0=0.6,  psi_1=0.5,  psi_2=0.0,
        note="EN1990 Table A2.1 – ψ₀=0.6 alone; 0.5 with traffic"),
    "Wind_Br_no_traffic": PsiRow(
        "Wind – bridge (no traffic)",         "W",
        psi_0=0.6,  psi_1=0.5,  psi_2=0.0,
        note="EN1990 Table A2.1"),
    # ── 온도 (교량) ───────────────────────────────────────────────
    "Temp_Br": PsiRow(
        "Temperature – bridge",               "T",
        psi_0=0.6,  psi_1=0.6,  psi_2=0.5,
        note="EN1990 Table A2.1 – ψ₂=0.5 for QP"),
    # ── 적설 (교량) ───────────────────────────────────────────────
    "Snow_Br": PsiRow(
        "Snow – bridge",                      "S",
        psi_0=0.8,  psi_1=0.0,  psi_2=0.0,
        note="EN1990 Table A2.1"),
    # ── 피로 하중 ─────────────────────────────────────────────────
    "FT": PsiRow(
        "Fatigue load (LM3/LM4)",             "FT",
        psi_0=1.0,  psi_1=1.0,  psi_2=1.0,
        note="EN1990 Eq.6.9 – fatigue combination"),
    # ── Fallback ─────────────────────────────────────────────────
    "TR":  PsiRow("Traffic (generic)",        "TR", 0.75, 0.75, 0.0),
    "W":   PsiRow("Wind (generic)",           "W",  0.6,  0.5,  0.0),
    "T":   PsiRow("Temperature (generic)",    "T",  0.6,  0.6,  0.5),
    "S":   PsiRow("Snow (generic)",           "S",  0.8,  0.0,  0.0),
    "Qi":  PsiRow("Variable (generic)",       "Qi", 0.7,  0.5,  0.3),
}

# ── 교량 국가별 NA override (EN 기준, 필요 시 확장) ──────────────
PSI_TABLE_BRIDGE_UK: Dict[str, PsiRow] = {
    **PSI_TABLE_BRIDGE_EN,
    "TR_gr1a": PsiRow(
        "gr1a – LM1 (UK NA)", "TR", 0.75, 0.75, 0.0,
        "UK NA: same as EN default"),
    "Temp_Br": PsiRow(
        "Temperature – bridge (UK NA)", "T", 0.6, 0.6, 0.5,
        "UK NA BS EN 1990 NA.2.2.6"),
}


# ═══════════════════════════════════════════════════════════════════════════
# 3.  국가별 γ + ψ 테이블 묶음 (건물 / 교량 분리)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class NAFactors:
    """국가별 National Annex 계수 컨테이너"""
    country        : str
    # ── 건물 γ (Annex A1) ─────────────────────────────
    gamma_G        : float = 1.35
    gamma_G_fav    : float = 1.00
    gamma_Q        : float = 1.50
    xi             : float = 0.85   # Eq.6.10b 감소계수
    # ── 교량 γ (Annex A2 Table A2.4) ─────────────────
    gamma_G_br     : float = 1.35   # 교량 고정하중 (불리)
    gamma_G_br_fav : float = 1.00   # 교량 고정하중 (유리)
    gamma_Q_br_tr  : float = 1.35   # 교량 교통하중
    gamma_Q_br_oth : float = 1.50   # 교량 기타변수하중 (풍, 온도)
    xi_br          : float = 0.85   # 교량 Eq.6.10b
    # ── EQU 전용 γ (Annex A1 Table A1.2A) ────────────
    gamma_G_equ    : float = 1.10   # EQU 불리
    gamma_G_equ_fav: float = 0.90   # EQU 유리
    gamma_Q_equ    : float = 1.50   # EQU 변수
    # ── ψ 테이블 ──────────────────────────────────────
    psi_table_bldg : Dict[str, PsiRow] = field(default_factory=dict)
    psi_table_br   : Dict[str, PsiRow] = field(default_factory=dict)

    def __post_init__(self):
        if not self.psi_table_bldg:
            self.psi_table_bldg = PSI_TABLE_BUILDING_EN
        if not self.psi_table_br:
            self.psi_table_br   = PSI_TABLE_BRIDGE_EN

    def psi(self, category: str, which: str,
            structure: str = "building") -> float:
        tbl = self.psi_table_br if structure == "bridge" else self.psi_table_bldg
        row = tbl.get(category) or tbl.get("Qi")
        return getattr(row, which, 0.7)

    def psi_0(self, cat: str, structure: str = "building") -> float:
        return self.psi(cat, "psi_0", structure)
    def psi_1(self, cat: str, structure: str = "building") -> float:
        return self.psi(cat, "psi_1", structure)
    def psi_2(self, cat: str, structure: str = "building") -> float:
        return self.psi(cat, "psi_2", structure)


NA_DATABASE: Dict[str, NAFactors] = {
    "EN": NAFactors(
        country="EN (Eurocode default)",
        psi_table_bldg=PSI_TABLE_BUILDING_EN,
        psi_table_br  =PSI_TABLE_BRIDGE_EN),
    "UK": NAFactors(
        country="United Kingdom (BS EN)",
        psi_table_bldg=PSI_TABLE_BUILDING_UK,
        psi_table_br  =PSI_TABLE_BRIDGE_UK),
    "DE": NAFactors(
        country="Germany (DIN EN)",
        gamma_G=1.35, gamma_Q=1.50, xi=0.85,
        psi_table_bldg=PSI_TABLE_BUILDING_DE,
        psi_table_br  =PSI_TABLE_BRIDGE_EN),
    "PL": NAFactors(country="Poland (PN-EN)",
                    psi_table_bldg=PSI_TABLE_BUILDING_EN,
                    psi_table_br  =PSI_TABLE_BRIDGE_EN),
    "HU": NAFactors(country="Hungary (MSZ EN)",
                    psi_table_bldg=PSI_TABLE_BUILDING_EN,
                    psi_table_br  =PSI_TABLE_BRIDGE_EN),
    "RO": NAFactors(country="Romania (SR EN)",
                    psi_table_bldg=PSI_TABLE_BUILDING_EN,
                    psi_table_br  =PSI_TABLE_BRIDGE_EN),
    "HR": NAFactors(country="Croatia (HRN EN)",
                    psi_table_bldg=PSI_TABLE_BUILDING_EN,
                    psi_table_br  =PSI_TABLE_BRIDGE_EN),
    "AL": NAFactors(country="Albania (KTP EN)",
                    psi_table_bldg=PSI_TABLE_BUILDING_EN,
                    psi_table_br  =PSI_TABLE_BRIDGE_EN),
}


# ═══════════════════════════════════════════════════════════════════════════
# 4.  교량 하중 그룹 정의 (EN 1991-2 Table 4.4a)
# ═══════════════════════════════════════════════════════════════════════════
#
#  LoadGroup은 어떤 LC들이 동시에 작용하는 "하나의 교통하중 사건"을 정의한다.
#  엔진은 각 그룹을 하나의 Leading Variable로 취급하여 조합을 생성한다.

@dataclass
class BridgeLoadGroup:
    """교량 교통 하중 그룹 (EN 1991-2 Table 4.4a)"""
    name       : str          # gr1a, gr2, …
    lc_names   : List[str]    # 이 그룹에 속하는 LC 이름 목록
    category   : str          # ψ 테이블 키 (TR_gr1a, TR_gr2 …)
    description: str = ""
    is_fatigue : bool = False  # 피로 조합 전용 여부


# ═══════════════════════════════════════════════════════════════════════════
# 5.  기반 엔진 (건물 / 교량 공통 조합식)
# ═══════════════════════════════════════════════════════════════════════════

class _BaseEngine:
    """건물·교량 공통 조합식 생성 기반 클래스"""

    STRUCTURE = "building"   # 서브클래스에서 override

    def __init__(self, load_cases: pd.DataFrame,
                 country: str, eq_method: str):
        if "EN1990_Category" not in load_cases.columns:
            load_cases = load_cases.copy()
            load_cases["EN1990_Category"] = load_cases["EN1990_Action"]
        self.lc_df     = load_cases.reset_index(drop=True)
        self.na        = NA_DATABASE.get(country, NA_DATABASE["EN"])
        self.eq_method = eq_method
        self.country   = country
        self.G_cases   = self._filter("G")
        self.Q_cases   = [r for r in self.lc_df.to_dict("records")
                          if r["EN1990_Action"] != "G"]

    def _filter(self, action: str) -> List[dict]:
        return self.lc_df[self.lc_df["EN1990_Action"] == action].to_dict("records")

    def _cat(self, lc: dict) -> str:
        return lc.get("EN1990_Category", lc.get("EN1990_Action", "Qi"))

    def _p0(self, lc: dict) -> float:
        return self.na.psi_0(self._cat(lc), self.STRUCTURE)
    def _p1(self, lc: dict) -> float:
        return self.na.psi_1(self._cat(lc), self.STRUCTURE)
    def _p2(self, lc: dict) -> float:
        return self.na.psi_2(self._cat(lc), self.STRUCTURE)

    # ── γ 선택 (건물 vs 교량) ────────────────────────────────────
    @property
    def _gG(self)    -> float: return self.na.gamma_G
    @property
    def _gG_fav(self)-> float: return self.na.gamma_G_fav
    @property
    def _gQ(self)    -> float: return self.na.gamma_Q
    @property
    def _xi(self)    -> float: return self.na.xi

    def _g_factors(self, unfav: bool = True) -> Dict[str, float]:
        γ = self._gG if unfav else self._gG_fav
        return {lc["Name"]: γ for lc in self.G_cases}

    # ── ULS Eq.6.10 ─────────────────────────────────────────────
    def _uls_610(self, lead: dict, others: List[dict],
                 idx: int, prefix: str = "ULS") -> LoadCombination:
        f = self._g_factors(unfav=True)
        f[lead["Name"]] = self._gQ
        for q in others:
            f[q["Name"]] = self._gQ * self._p0(q)
        return LoadCombination(
            name        = f"{prefix}_6.10_{idx:02d}_Lead_{lead['Name']}",
            combo_type  = "ULS_6.10",
            limit_state = "ULS",
            factors     = f,
            description = (f"ULS Eq.6.10 │ Lead:{lead['Name']} "
                           f"│ γG={self._gG} γQ={self._gQ}"),
        )

    # ── ULS Eq.6.10a ────────────────────────────────────────────
    def _uls_610a(self, qs: List[dict], idx: int,
                  prefix: str = "ULS") -> LoadCombination:
        f = self._g_factors(unfav=True)
        for q in qs:
            f[q["Name"]] = self._gQ * self._p0(q)
        return LoadCombination(
            name        = f"{prefix}_6.10a_{idx:02d}",
            combo_type  = "ULS_6.10a",
            limit_state = "ULS",
            factors     = f,
            description = "ULS Eq.6.10a │ All Q with γQ·ψ₀",
        )

    # ── ULS Eq.6.10b ────────────────────────────────────────────
    def _uls_610b(self, lead: dict, others: List[dict],
                  idx: int, prefix: str = "ULS") -> LoadCombination:
        f = {lc["Name"]: self._xi * self._gG for lc in self.G_cases}
        f[lead["Name"]] = self._gQ
        for q in others:
            f[q["Name"]] = self._gQ * self._p0(q)
        return LoadCombination(
            name        = f"{prefix}_6.10b_{idx:02d}_Lead_{lead['Name']}",
            combo_type  = "ULS_6.10b",
            limit_state = "ULS",
            factors     = f,
            description = (f"ULS Eq.6.10b │ ξ={self._xi} "
                           f"│ Lead:{lead['Name']}"),
        )

    # ── SLS Characteristic Eq.6.14 ──────────────────────────────
    def _sls_char(self, lead: dict, others: List[dict],
                  idx: int, prefix: str = "SLS") -> LoadCombination:
        f = {lc["Name"]: 1.0 for lc in self.G_cases}
        f[lead["Name"]] = 1.0
        for q in others:
            f[q["Name"]] = self._p0(q)
        return LoadCombination(
            name        = f"{prefix}_CHAR_{idx:02d}_Lead_{lead['Name']}",
            combo_type  = "SLS_CHAR",
            limit_state = "SLS",
            factors     = f,
            description = f"SLS Characteristic Eq.6.14 │ Lead:{lead['Name']}",
        )

    # ── SLS Frequent Eq.6.15 ────────────────────────────────────
    def _sls_freq(self, lead: dict, others: List[dict],
                  idx: int, prefix: str = "SLS") -> LoadCombination:
        f = {lc["Name"]: 1.0 for lc in self.G_cases}
        f[lead["Name"]] = self._p1(lead)
        for q in others:
            f[q["Name"]] = self._p2(q)
        return LoadCombination(
            name        = f"{prefix}_FREQ_{idx:02d}_Lead_{lead['Name']}",
            combo_type  = "SLS_FREQ",
            limit_state = "SLS",
            factors     = f,
            description = f"SLS Frequent Eq.6.15 │ Lead:{lead['Name']}",
        )

    # ── SLS Quasi-permanent Eq.6.16 ─────────────────────────────
    def _sls_qp(self, prefix: str = "SLS") -> LoadCombination:
        f = {lc["Name"]: 1.0 for lc in self.G_cases}
        for q in self.Q_cases:
            f[q["Name"]] = self._p2(q)
        return LoadCombination(
            name        = f"{prefix}_QP_01",
            combo_type  = "SLS_QP",
            limit_state = "SLS",
            factors     = f,
            description = "SLS Quasi-permanent Eq.6.16 │ Σ ψ₂·Qki",
        )

    # ── 중복 제거 ────────────────────────────────────────────────
    @staticmethod
    def _dedup(combos: List[LoadCombination]) -> List[LoadCombination]:
        seen, out = set(), []
        for c in combos:
            if c.name not in seen:
                seen.add(c.name); out.append(c)
        return out

    def summary_df(self, combos: List[LoadCombination]) -> pd.DataFrame:
        rows = []
        for c in combos:
            row = {"Name": c.name, "Type": c.combo_type,
                   "LimitState": c.limit_state,
                   "LoadGroup" : c.load_group,
                   "Description": c.description}
            row.update({f"F_{k}": v for k, v in c.factors.items()})
            rows.append(row)
        return pd.DataFrame(rows)

    @staticmethod
    def psi_reference_df(country: str = "EN",
                         structure: str = "building") -> pd.DataFrame:
        na  = NA_DATABASE.get(country, NA_DATABASE["EN"])
        tbl = na.psi_table_br if structure == "bridge" else na.psi_table_bldg
        return pd.DataFrame([
            {"Category"   : k, "Description": v.category,
             "ActionType" : v.action_type,
             "ψ₀": v.psi_0, "ψ₁": v.psi_1, "ψ₂": v.psi_2,
             "Note": v.note}
            for k, v in tbl.items()
        ])


# ═══════════════════════════════════════════════════════════════════════════
# 6.  건물 엔진  (Annex A1)
# ═══════════════════════════════════════════════════════════════════════════

class EN1990Engine(_BaseEngine):
    """
    EN 1990 Annex A1 — 건물 하중 조합 엔진  (하위 호환 유지)

    Parameters
    ----------
    load_cases : pd.DataFrame  (필수: ID, Name, EN1990_Action
                                선택: EN1990_Category)
    country    : str           NA 코드 (EN/UK/DE/PL/HU/RO/HR/AL)
    eq_method  : str           "6.10" / "6.10ab" / "all"
    """

    STRUCTURE = "building"

    def __init__(self, load_cases: pd.DataFrame,
                 country: str = "EN", eq_method: str = "6.10ab"):
        super().__init__(load_cases, country, eq_method)
        print(f"🔧 EN1990 건물 엔진 v3 │ {self.na.country}")
        self._print_psi()

    def _print_psi(self):
        print(f"   {'LC':<12} {'Category':<22} {'ψ₀':>5} {'ψ₁':>5} {'ψ₂':>5}")
        print("   " + "─" * 50)
        for lc in self.Q_cases:
            cat = self._cat(lc)
            print(f"   {lc['Name']:<12} {cat:<22} "
                  f"{self.na.psi_0(cat,'building'):>5.2f} "
                  f"{self.na.psi_1(cat,'building'):>5.2f} "
                  f"{self.na.psi_2(cat,'building'):>5.2f}")
        print()

    def generate_all(self) -> List[LoadCombination]:
        combos: List[LoadCombination] = []

        if not self.Q_cases:
            combos.append(LoadCombination(
                "ULS_G_only","ULS_6.10","ULS",
                self._g_factors(unfav=True),
                "ULS – Permanent loads only"))
            return combos

        for idx, lead in enumerate(self.Q_cases, 1):
            others = [q for q in self.Q_cases if q["Name"] != lead["Name"]]
            if self.eq_method in ("6.10","all"):
                combos.append(self._uls_610(lead, others, idx))
            if self.eq_method in ("6.10ab","all"):
                combos.append(self._uls_610a(self.Q_cases, idx))
                combos.append(self._uls_610b(lead, others, idx))
            combos.append(self._sls_char(lead, others, idx))
            combos.append(self._sls_freq(lead, others, idx))

        combos.append(self._sls_qp())
        unique = self._dedup(combos)
        print(f"✅ 건물 조합 {len(unique)}개 생성")
        return unique


# ═══════════════════════════════════════════════════════════════════════════
# 7.  교량 엔진  (Annex A2)
# ═══════════════════════════════════════════════════════════════════════════

class EN1990BridgeEngine(_BaseEngine):
    """
    EN 1990 Annex A2 — 교량 하중 조합 엔진

    Parameters
    ----------
    load_cases   : pd.DataFrame
        필수 컬럼: ID, Name, EN1990_Action
        선택 컬럼: EN1990_Category  (TR_gr1a … FT 등)
    country      : str      NA 코드
    eq_method    : str      "6.10" / "6.10ab" / "all"
    load_groups  : List[BridgeLoadGroup]
        교통 하중 그룹 정의. None이면 EN1990_Category 기반 자동 구성.
    include_fatigue : bool  피로 조합(Eq.6.9) 생성 여부 (기본: True)
    include_equ     : bool  EQU 조합 생성 여부 (기본: False)

    교통 하중 처리 방식
    ------------------
    교량에서 EN 1991-2는 복수의 LC를 하나의 '하중 그룹(gr1a 등)'으로 묶어
    하나의 Leading Variable로 취급하도록 규정합니다.
    BridgeLoadGroup으로 그룹을 정의하면 그룹 전체에 동일한 γ·ψ를 적용합니다.
    """

    STRUCTURE = "bridge"

    def __init__(self,
                 load_cases     : pd.DataFrame,
                 country        : str = "EN",
                 eq_method      : str = "6.10ab",
                 load_groups    : Optional[List[BridgeLoadGroup]] = None,
                 include_fatigue: bool = True,
                 include_equ    : bool = False):
        super().__init__(load_cases, country, eq_method)

        self.include_fatigue = include_fatigue
        self.include_equ     = include_equ

        # 교통 LC 분리
        self.TR_cases  = [lc for lc in self.Q_cases
                          if lc["EN1990_Action"] in ("TR",)]
        self.FT_cases  = [lc for lc in self.lc_df.to_dict("records")
                          if lc["EN1990_Action"] == "FT"]
        self.NON_TR_Q  = [lc for lc in self.Q_cases
                          if lc["EN1990_Action"] not in ("TR","FT")]

        # 하중 그룹: 사용자 정의 우선, 없으면 자동 구성
        self.load_groups = load_groups or self._auto_groups()

        print(f"🔧 EN1990 교량 엔진 v3 │ {self.na.country}")
        print(f"   Annex A2 적용 │ eq_method={eq_method}")
        print(f"   G  (영구)    : {[lc['Name'] for lc in self.G_cases]}")
        print(f"   TR (교통)    : {[lc['Name'] for lc in self.TR_cases]}")
        print(f"   Non-TR Q     : {[lc['Name'] for lc in self.NON_TR_Q]}")
        print(f"   FT (피로)    : {[lc['Name'] for lc in self.FT_cases]}")
        print(f"   하중 그룹    : {[g.name for g in self.load_groups]}")
        self._print_psi()

    # ── 교통 γ 사용 ─────────────────────────────────────────────
    @property
    def _gQ(self) -> float:
        return self.na.gamma_Q_br_tr   # 교통: 1.35

    @property
    def _gQ_other(self) -> float:
        return self.na.gamma_Q_br_oth  # 풍/온도: 1.50

    def _gQ_for(self, lc: dict) -> float:
        """LC 유형에 따라 적절한 γ_Q 반환"""
        return self._gQ if lc["EN1990_Action"] == "TR" else self._gQ_other

    def _print_psi(self):
        all_q = self.TR_cases + self.NON_TR_Q
        if not all_q: return
        print(f"\n   {'LC':<12} {'Category':<28} {'ψ₀':>5} {'ψ₁':>5} {'ψ₂':>5}")
        print("   " + "─" * 58)
        for lc in all_q:
            cat = self._cat(lc)
            print(f"   {lc['Name']:<12} {cat:<28} "
                  f"{self.na.psi_0(cat,'bridge'):>5.2f} "
                  f"{self.na.psi_1(cat,'bridge'):>5.2f} "
                  f"{self.na.psi_2(cat,'bridge'):>5.2f}")
        print()

    # ── 하중 그룹 자동 구성 ──────────────────────────────────────
    def _auto_groups(self) -> List[BridgeLoadGroup]:
        """
        EN1990_Category 값이 TR_gr* 형태인 LC를
        그룹명별로 자동 묶음
        """
        groups: Dict[str, List[str]] = {}
        for lc in self.TR_cases:
            cat = self._cat(lc)
            grp = cat if cat.startswith("TR_") else "TR_gr1a"
            groups.setdefault(grp, []).append(lc["Name"])

        result = []
        for cat, names in groups.items():
            grp_name = cat.replace("TR_", "")
            result.append(BridgeLoadGroup(
                name=grp_name, lc_names=names,
                category=cat,
                description=f"Auto group: {cat}",
            ))

        # 피로 그룹
        if self.FT_cases:
            result.append(BridgeLoadGroup(
                name="Fatigue",
                lc_names=[lc["Name"] for lc in self.FT_cases],
                category="FT",
                description="Fatigue load (EN1990 Eq.6.9)",
                is_fatigue=True,
            ))

        # 그룹 없으면 TR 전체를 gr1a 하나로
        if not result and self.TR_cases:
            result.append(BridgeLoadGroup(
                name="gr1a",
                lc_names=[lc["Name"] for lc in self.TR_cases],
                category="TR_gr1a",
                description="Default: all TR as gr1a",
            ))
        return result

    # ── 그룹 딕셔너리 헬퍼 ──────────────────────────────────────
    def _group_lc_dict(self, grp: BridgeLoadGroup) -> List[dict]:
        """그룹 내 LC 이름 → lc_df row 딕셔너리 변환"""
        name_set = set(grp.lc_names)
        return [r for r in self.lc_df.to_dict("records")
                if r["Name"] in name_set]

    # ─────────────────────────────────────────────────────────────
    # 교량 전용 조합 빌더
    # 교통 하중 그룹을 Leading Variable로 취급하고
    # γ_Q_br_tr (1.35) 적용 / Non-TR은 γ_Q_br_oth (1.50) 적용
    # ─────────────────────────────────────────────────────────────

    def _br_uls_610(self, lead_grp: BridgeLoadGroup,
                    other_grps: List[BridgeLoadGroup],
                    non_tr_qs : List[dict],
                    idx: int) -> LoadCombination:
        """
        교량 ULS Eq.6.10
        Σ γG·Gk + γQ_tr·(gr_lead) + Σ γQ_tr·ψ₀·(gr_i) + Σ γQ_oth·ψ₀·(Qk_j)
        """
        f = self._g_factors(unfav=True)
        # leading 그룹 전체 LC → γ_Q_tr (ψ₀ 없음)
        for lc in self._group_lc_dict(lead_grp):
            f[lc["Name"]] = self._gQ
        # 동반 교통 그룹 → γ_Q_tr · ψ₀
        for grp in other_grps:
            p0 = self.na.psi_0(grp.category, "bridge")
            for lc in self._group_lc_dict(grp):
                f[lc["Name"]] = self._gQ * p0
        # Non-TR 변수하중 → γ_Q_oth · ψ₀
        for q in non_tr_qs:
            f[q["Name"]] = self._gQ_other * self._p0(q)

        return LoadCombination(
            name        = f"BR_ULS_6.10_{idx:02d}_Lead_{lead_grp.name}",
            combo_type  = "ULS_6.10",
            limit_state = "ULS",
            factors     = f,
            load_group  = lead_grp.name,
            description = (f"Bridge ULS Eq.6.10 │ Lead:{lead_grp.name} "
                           f"│ γG={self._gG} γQ_tr={self._gQ} "
                           f"γQ_oth={self._gQ_other}"),
        )

    def _br_uls_610a(self, lead_grp: BridgeLoadGroup,
                     other_grps: List[BridgeLoadGroup],
                     non_tr_qs : List[dict],
                     idx: int) -> LoadCombination:
        """교량 ULS Eq.6.10a: 모든 Q에 ψ₀ 적용"""
        f = self._g_factors(unfav=True)
        for grp in [lead_grp] + other_grps:
            p0 = self.na.psi_0(grp.category, "bridge")
            for lc in self._group_lc_dict(grp):
                f[lc["Name"]] = self._gQ * p0
        for q in non_tr_qs:
            f[q["Name"]] = self._gQ_other * self._p0(q)
        return LoadCombination(
            name        = f"BR_ULS_6.10a_{idx:02d}_Ref_{lead_grp.name}",
            combo_type  = "ULS_6.10a",
            limit_state = "ULS",
            factors     = f,
            load_group  = lead_grp.name,
            description = "Bridge ULS Eq.6.10a │ All groups with γQ·ψ₀",
        )

    def _br_uls_610b(self, lead_grp: BridgeLoadGroup,
                     other_grps: List[BridgeLoadGroup],
                     non_tr_qs : List[dict],
                     idx: int) -> LoadCombination:
        """교량 ULS Eq.6.10b: ξ·γG + leading(full) + others(ψ₀)"""
        f = {lc["Name"]: self._xi * self._gG for lc in self.G_cases}
        for lc in self._group_lc_dict(lead_grp):
            f[lc["Name"]] = self._gQ
        for grp in other_grps:
            p0 = self.na.psi_0(grp.category, "bridge")
            for lc in self._group_lc_dict(grp):
                f[lc["Name"]] = self._gQ * p0
        for q in non_tr_qs:
            f[q["Name"]] = self._gQ_other * self._p0(q)
        return LoadCombination(
            name        = f"BR_ULS_6.10b_{idx:02d}_Lead_{lead_grp.name}",
            combo_type  = "ULS_6.10b",
            limit_state = "ULS",
            factors     = f,
            load_group  = lead_grp.name,
            description = (f"Bridge ULS Eq.6.10b │ ξ={self._xi} "
                           f"│ Lead:{lead_grp.name}"),
        )

    def _br_uls_equ(self, lead_grp: BridgeLoadGroup,
                    other_grps: List[BridgeLoadGroup],
                    non_tr_qs : List[dict],
                    idx: int) -> LoadCombination:
        """
        교량 ULS EQU (전도/부상 검토) — Annex A2 Table A2.4(A)
        γG_equ_unfav·Gk_sup + γG_equ_fav·Gk_inf + γQ_equ·(leading) + …
        """
        f = {}
        for lc in self.G_cases:
            # 간략화: 모든 G를 unfav 취급 (실제로는 부위별 분리 필요)
            f[lc["Name"]] = self.na.gamma_G_equ
        for lc in self._group_lc_dict(lead_grp):
            f[lc["Name"]] = self.na.gamma_Q_equ
        for grp in other_grps:
            p0 = self.na.psi_0(grp.category, "bridge")
            for lc in self._group_lc_dict(grp):
                f[lc["Name"]] = self.na.gamma_Q_equ * p0
        for q in non_tr_qs:
            f[q["Name"]] = self.na.gamma_Q_equ * self._p0(q)
        return LoadCombination(
            name        = f"BR_ULS_EQU_{idx:02d}_Lead_{lead_grp.name}",
            combo_type  = "ULS_EQU",
            limit_state = "ULS",
            factors     = f,
            load_group  = lead_grp.name,
            description = (f"Bridge ULS EQU │ γG={self.na.gamma_G_equ} "
                           f"│ γQ={self.na.gamma_Q_equ} │ Lead:{lead_grp.name}"),
        )

    # ── SLS (교량) ───────────────────────────────────────────────
    def _br_sls_char(self, lead_grp: BridgeLoadGroup,
                     other_grps: List[BridgeLoadGroup],
                     non_tr_qs : List[dict],
                     idx: int) -> LoadCombination:
        """교량 SLS Characteristic Eq.6.14"""
        f = {lc["Name"]: 1.0 for lc in self.G_cases}
        for lc in self._group_lc_dict(lead_grp):
            f[lc["Name"]] = 1.0
        for grp in other_grps:
            p0 = self.na.psi_0(grp.category, "bridge")
            for lc in self._group_lc_dict(grp):
                f[lc["Name"]] = p0
        for q in non_tr_qs:
            f[q["Name"]] = self._p0(q)
        return LoadCombination(
            name        = f"BR_SLS_CHAR_{idx:02d}_Lead_{lead_grp.name}",
            combo_type  = "SLS_CHAR",
            limit_state = "SLS",
            factors     = f,
            load_group  = lead_grp.name,
            description = f"Bridge SLS Characteristic │ Lead:{lead_grp.name}",
        )

    def _br_sls_freq(self, lead_grp: BridgeLoadGroup,
                     other_grps: List[BridgeLoadGroup],
                     non_tr_qs : List[dict],
                     idx: int) -> LoadCombination:
        """교량 SLS Frequent Eq.6.15"""
        f = {lc["Name"]: 1.0 for lc in self.G_cases}
        p1_lead = self.na.psi_1(lead_grp.category, "bridge")
        for lc in self._group_lc_dict(lead_grp):
            f[lc["Name"]] = p1_lead
        for grp in other_grps:
            p2 = self.na.psi_2(grp.category, "bridge")
            for lc in self._group_lc_dict(grp):
                f[lc["Name"]] = p2
        for q in non_tr_qs:
            f[q["Name"]] = self._p2(q)
        return LoadCombination(
            name        = f"BR_SLS_FREQ_{idx:02d}_Lead_{lead_grp.name}",
            combo_type  = "SLS_FREQ",
            limit_state = "SLS",
            factors     = f,
            load_group  = lead_grp.name,
            description = f"Bridge SLS Frequent │ Lead:{lead_grp.name}",
        )

    def _br_sls_qp(self, non_tr_qs: List[dict]) -> LoadCombination:
        """교량 SLS Quasi-permanent Eq.6.16 (교통 하중 제외)"""
        f = {lc["Name"]: 1.0 for lc in self.G_cases}
        # 교통 하중: ψ₂=0 → 사실상 미적용
        for grp in self.load_groups:
            if not grp.is_fatigue:
                p2 = self.na.psi_2(grp.category, "bridge")
                for lc in self._group_lc_dict(grp):
                    f[lc["Name"]] = p2
        for q in non_tr_qs:
            f[q["Name"]] = self._p2(q)
        return LoadCombination(
            name        = "BR_SLS_QP_01",
            combo_type  = "SLS_QP",
            limit_state = "SLS",
            factors     = f,
            description = "Bridge SLS Quasi-permanent Eq.6.16 │ TR ψ₂=0",
        )

    # ── 피로 조합 Eq.6.9 ────────────────────────────────────────
    def _fatigue_combo(self, ft_grp: BridgeLoadGroup,
                       idx: int) -> LoadCombination:
        """
        EN 1990 Eq.6.9 Fatigue combination:
        Σ Gk + P + ψ₁·Qk1 + Σ ψ₂·Qki + Qfat
        여기서 Qfat = 피로하중 (계수 1.0)
        비피로 변수하중은 ψ₁ 또는 ψ₂ 적용
        """
        f = {lc["Name"]: 1.0 for lc in self.G_cases}

        # 비피로 교통 그룹: ψ₁ (Leading이 있으면) or ψ₂
        non_fat_grps = [g for g in self.load_groups if not g.is_fatigue]
        for gi, grp in enumerate(non_fat_grps):
            p = (self.na.psi_1(grp.category, "bridge") if gi == 0
                 else self.na.psi_2(grp.category, "bridge"))
            for lc in self._group_lc_dict(grp):
                f[lc["Name"]] = p

        # Non-TR Q: ψ₂
        for q in self.NON_TR_Q:
            f[q["Name"]] = self._p2(q)

        # 피로 하중: 1.0 (γ_Ff·ΔF는 별도 피로 검토에서 적용)
        for lc_name in ft_grp.lc_names:
            f[lc_name] = 1.0

        return LoadCombination(
            name        = f"BR_FATIGUE_{idx:02d}_{ft_grp.name}",
            combo_type  = "FATIGUE",
            limit_state = "FATIGUE",
            factors     = f,
            load_group  = ft_grp.name,
            description = (f"Fatigue Eq.6.9 │ Gk + ψ₁·Qk1 + Σψ₂·Qki + Qfat "
                           f"│ Fatigue LC:{ft_grp.lc_names}"),
        )

    # ── 전체 조합 생성 ──────────────────────────────────────────
    def generate_all(self) -> List[LoadCombination]:
        """모든 교량 ULS / SLS / Fatigue 조합 생성"""
        combos: List[LoadCombination] = []

        # 비피로 교통 그룹 + Non-TR 변수하중 준비
        active_grps = [g for g in self.load_groups if not g.is_fatigue]
        fat_grps    = [g for g in self.load_groups if g.is_fatigue]

        if not active_grps and not self.NON_TR_Q:
            # G-only
            combos.append(LoadCombination(
                "BR_ULS_G_only","ULS_6.10","ULS",
                self._g_factors(unfav=True),
                "Bridge ULS – Permanent loads only"))
            return combos

        # ── ULS + SLS: 각 교통 그룹을 순서대로 Leading ──────────
        all_q_grps = active_grps  # 교통 그룹
        for idx, lead_grp in enumerate(all_q_grps, 1):
            other_grps = [g for g in all_q_grps if g.name != lead_grp.name]

            if self.eq_method in ("6.10", "all"):
                combos.append(self._br_uls_610(lead_grp, other_grps,
                                               self.NON_TR_Q, idx))
            if self.eq_method in ("6.10ab", "all"):
                combos.append(self._br_uls_610a(lead_grp, other_grps,
                                                self.NON_TR_Q, idx))
                combos.append(self._br_uls_610b(lead_grp, other_grps,
                                                self.NON_TR_Q, idx))
            if self.include_equ:
                combos.append(self._br_uls_equ(lead_grp, other_grps,
                                               self.NON_TR_Q, idx))

            combos.append(self._br_sls_char(lead_grp, other_grps,
                                            self.NON_TR_Q, idx))
            combos.append(self._br_sls_freq(lead_grp, other_grps,
                                            self.NON_TR_Q, idx))

        # Non-TR만 있는 경우 (풍/온도 Leading)
        for idx2, lead_q in enumerate(self.NON_TR_Q, len(all_q_grps)+1):
            others_q = [q for q in self.NON_TR_Q if q["Name"] != lead_q["Name"]]
            if self.eq_method in ("6.10", "all"):
                combos.append(self._uls_610(lead_q, others_q, idx2, "BR"))
            if self.eq_method in ("6.10ab", "all"):
                combos.append(self._uls_610a(self.NON_TR_Q, idx2, "BR"))
                combos.append(self._uls_610b(lead_q, others_q, idx2, "BR"))
            combos.append(self._sls_char(lead_q, others_q, idx2, "BR_SLS"))
            combos.append(self._sls_freq(lead_q, others_q, idx2, "BR_SLS"))

        # SLS QP
        combos.append(self._br_sls_qp(self.NON_TR_Q))

        # ── 피로 조합 Eq.6.9 ─────────────────────────────────────
        if self.include_fatigue and fat_grps:
            for idx3, fat_grp in enumerate(fat_grps, 1):
                combos.append(self._fatigue_combo(fat_grp, idx3))

        unique = self._dedup(combos)
        print(f"✅ 교량 조합 {len(unique)}개 생성 "
              f"(ULS/SLS + {'피로 포함' if self.include_fatigue and fat_grps else '피로 없음'})")
        return unique


# ═══════════════════════════════════════════════════════════════════════════
# 8.  통합 팩토리 함수
# ═══════════════════════════════════════════════════════════════════════════

def create_engine(load_cases    : pd.DataFrame,
                  structure_type: str = "building",
                  country       : str = "EN",
                  eq_method     : str = "6.10ab",
                  **kwargs) -> "_BaseEngine":
    """
    구조물 유형에 따라 적절한 엔진 반환

    structure_type : "building"  → EN1990Engine      (Annex A1)
                     "bridge"    → EN1990BridgeEngine (Annex A2)
    kwargs         : 교량 전용 옵션 (load_groups, include_fatigue, include_equ)
    """
    if structure_type == "bridge":
        return EN1990BridgeEngine(load_cases, country, eq_method, **kwargs)
    return EN1990Engine(load_cases, country, eq_method)


# ═══════════════════════════════════════════════════════════════════════════
# 9.  실행 예시
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("\n" + "═"*68)
    print("  [A]  건물 예제 (Annex A1)")
    print("═"*68)

    bldg_lc = pd.DataFrame([
        {"ID":1,"Name":"SW",   "Type":"ST","EN1990_Action":"G", "EN1990_Category":"G"},
        {"ID":2,"Name":"SDL",  "Type":"ST","EN1990_Action":"G", "EN1990_Category":"G"},
        {"ID":3,"Name":"LL",   "Type":"LV","EN1990_Action":"Qi","EN1990_Category":"Cat_B"},
        {"ID":4,"Name":"WL_X", "Type":"WL","EN1990_Action":"W", "EN1990_Category":"Wind"},
        {"ID":5,"Name":"TMP",  "Type":"TL","EN1990_Action":"T", "EN1990_Category":"Temp"},
    ])
    bldg_engine = EN1990Engine(bldg_lc, country="EN", eq_method="6.10ab")
    bldg_combos = bldg_engine.generate_all()
    bldg_sum    = bldg_engine.summary_df(bldg_combos)
    f_cols      = [c for c in bldg_sum.columns if c.startswith("F_")]
    print(bldg_sum[["Name","Type","LimitState"]+f_cols].to_string(index=False))


    print("\n" + "═"*68)
    print("  [B]  교량 예제 (Annex A2) — 도로교, 하중 그룹 수동 정의")
    print("═"*68)

    # ── 교량 Load Case 정의 ──────────────────────────────────────
    #  EN1990_Action 코드:
    #    G  = 영구하중
    #    TR = 교통하중  (EN1990_Category로 그룹 구분)
    #    FT = 피로하중
    #    W  = 풍하중
    #    T  = 온도하중
    #    S  = 적설하중

    bridge_lc = pd.DataFrame([
        # ── 영구하중 ──────────────────────────────────────────
        {"ID": 1,"Name":"SW",    "Type":"ST","EN1990_Action":"G", "EN1990_Category":"G"},
        {"ID": 2,"Name":"SDL",   "Type":"ST","EN1990_Action":"G", "EN1990_Category":"G"},
        {"ID": 3,"Name":"PS",    "Type":"PS","EN1990_Action":"G", "EN1990_Category":"G"},
        # ── 교통 하중 그룹 gr1a (LM1 TS + UDL) ──────────────
        {"ID": 4,"Name":"LM1_TS","Type":"LV","EN1990_Action":"TR","EN1990_Category":"TR_gr1a"},
        {"ID": 5,"Name":"LM1_UDL","Type":"LV","EN1990_Action":"TR","EN1990_Category":"TR_gr1a"},
        # ── 교통 하중 그룹 gr2 (수평력) ──────────────────────
        {"ID": 6,"Name":"Brake", "Type":"LV","EN1990_Action":"TR","EN1990_Category":"TR_gr2"},
        # ── 교통 하중 그룹 gr3 (보행자) ──────────────────────
        {"ID": 7,"Name":"Ped",   "Type":"LV","EN1990_Action":"TR","EN1990_Category":"TR_gr3"},
        # ── 피로 하중 ─────────────────────────────────────────
        {"ID": 8,"Name":"LM3_Fat","Type":"FT","EN1990_Action":"FT","EN1990_Category":"FT"},
        # ── 기타 변수하중 ─────────────────────────────────────
        {"ID": 9,"Name":"WL",    "Type":"WL","EN1990_Action":"W", "EN1990_Category":"Wind_Br"},
        {"ID":10,"Name":"TMP",   "Type":"TL","EN1990_Action":"T", "EN1990_Category":"Temp_Br"},
    ])

    # ── 하중 그룹 수동 정의 (자동 구성도 가능) ───────────────────
    groups = [
        BridgeLoadGroup(
            name="gr1a", lc_names=["LM1_TS","LM1_UDL"],
            category="TR_gr1a",
            description="LM1 Tandem System + UDL"),
        BridgeLoadGroup(
            name="gr2",  lc_names=["Brake"],
            category="TR_gr2",
            description="Horizontal forces (braking/acceleration)"),
        BridgeLoadGroup(
            name="gr3",  lc_names=["Ped"],
            category="TR_gr3",
            description="Pedestrian loads"),
        BridgeLoadGroup(
            name="Fatigue", lc_names=["LM3_Fat"],
            category="FT",
            description="Fatigue load model",
            is_fatigue=True),
    ]

    br_engine = EN1990BridgeEngine(
        bridge_lc,
        country         = "EN",
        eq_method       = "6.10ab",
        load_groups     = groups,
        include_fatigue = True,
        include_equ     = False,
    )
    br_combos = br_engine.generate_all()
    br_sum    = br_engine.summary_df(br_combos)

    print("\n조합 요약:")
    f_cols_br = [c for c in br_sum.columns if c.startswith("F_")]
    print(br_sum[["Name","Type","LimitState","LoadGroup"]+f_cols_br].to_string(index=False))

    print("\n" + "═"*68)
    print("  [C]  교량 예제 (Annex A2) — 자동 그룹 구성")
    print("═"*68)

    br_auto = EN1990BridgeEngine(bridge_lc, country="EN", eq_method="6.10ab",
                                  include_fatigue=True)
    br_auto_combos = br_auto.generate_all()
    print(f"  자동 생성 조합 수: {len(br_auto_combos)}")

    print("\n" + "═"*68)
    print("  [D]  ψ 계수 참조 테이블 (교량, EN)")
    print("═"*68)
    psi_df = _BaseEngine.psi_reference_df("EN", "bridge")
    print(psi_df[["Category","Description","ψ₀","ψ₁","ψ₂","Note"]].to_string(index=False))

    print("\n" + "═"*68)
    print("  [E]  통합 팩토리 사용 예시")
    print("═"*68)
    engine_any = create_engine(bridge_lc, structure_type="bridge",
                                country="EN", eq_method="6.10ab",
                                include_fatigue=True)
    print(f"  생성 엔진 유형: {type(engine_any).__name__}")
