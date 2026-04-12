"""
Phase 2: Civil NX 모델 데이터 추출
- Load Cases, Nodes, Elements, Sections, Materials, Boundary Conditions
"""

import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List
from phase1_connection import CivilNXClient, create_client


# ─────────────────────────────────────────────
# 1. 데이터 컨테이너
# ─────────────────────────────────────────────
@dataclass
class ModelData:
    """Civil NX 모델 전체 데이터 컨테이너"""
    load_cases  : pd.DataFrame = field(default_factory=pd.DataFrame)
    nodes       : pd.DataFrame = field(default_factory=pd.DataFrame)
    elements    : pd.DataFrame = field(default_factory=pd.DataFrame)
    sections    : pd.DataFrame = field(default_factory=pd.DataFrame)
    materials   : pd.DataFrame = field(default_factory=pd.DataFrame)
    boundaries  : pd.DataFrame = field(default_factory=pd.DataFrame)
    node_loads  : pd.DataFrame = field(default_factory=pd.DataFrame)
    beam_loads  : pd.DataFrame = field(default_factory=pd.DataFrame)


# ─────────────────────────────────────────────
# 2. 데이터 추출기
# ─────────────────────────────────────────────
class ModelExtractor:
    """Civil NX REST API에서 모델 데이터 추출"""

    # Eurocode 하중 유형 매핑
    # Civil NX 내부 타입 코드 → EN1990 액션 분류
    LOAD_TYPE_MAP = {
        "ST": "G",   # Static (Dead)      → Permanent
        "CS": "G",   # Construction Stage → Permanent
        "LV": "Qi",  # Live               → Variable
        "WL": "W",   # Wind Load          → Variable (Wind)
        "EL": "E",   # Earthquake         → Accidental
        "TL": "T",   # Temperature        → Variable (Thermal)
        "PS": "G",   # Prestress          → Permanent
        "RS": "G",   # Settlement         → Permanent
    }

    def __init__(self, client: CivilNXClient):
        self.client = client

    # ── Load Cases ────────────────────────────
    def get_load_cases(self) -> pd.DataFrame:
        """
        GET /civil/lcase
        반환: ID, Name, Type, EN1990_Action
        """
        raw = self.client.get("/civil/lcase")
        assign = raw.get("Assign", {})

        rows = []
        for lc_id, props in assign.items():
            lc_type = props.get("TYPE", "ST")
            rows.append({
                "ID"           : int(lc_id),
                "Name"         : props.get("NAME", f"LC{lc_id}"),
                "Type"         : lc_type,
                "EN1990_Action": self.LOAD_TYPE_MAP.get(lc_type, "Qi"),
                "Description"  : props.get("DESC", "")
            })

        df = pd.DataFrame(rows).sort_values("ID").reset_index(drop=True)
        print(f"✅ Load Cases: {len(df)}개 로드됨")
        return df

    # ── Nodes ─────────────────────────────────
    def get_nodes(self) -> pd.DataFrame:
        """
        GET /civil/node
        반환: NodeID, X, Y, Z
        """
        raw = self.client.get("/civil/node")
        assign = raw.get("Assign", {})

        rows = []
        for node_id, props in assign.items():
            coord = props.get("COORD", [0, 0, 0])
            rows.append({
                "NodeID": int(node_id),
                "X"     : coord[0] if len(coord) > 0 else 0.0,
                "Y"     : coord[1] if len(coord) > 1 else 0.0,
                "Z"     : coord[2] if len(coord) > 2 else 0.0,
            })

        df = pd.DataFrame(rows).sort_values("NodeID").reset_index(drop=True)
        print(f"✅ Nodes: {len(df)}개 로드됨")
        return df

    # ── Elements ──────────────────────────────
    def get_elements(self) -> pd.DataFrame:
        """
        GET /civil/elem
        반환: ElemID, Type, MatID, SecID, NodeI, NodeJ
        """
        raw = self.client.get("/civil/elem")
        assign = raw.get("Assign", {})

        rows = []
        for elem_id, props in assign.items():
            node_list = props.get("NODE", [0, 0])
            rows.append({
                "ElemID": int(elem_id),
                "Type"  : props.get("TYPE", "BEAM"),
                "MatID" : props.get("MATID", 0),
                "SecID" : props.get("SECID", 0),
                "NodeI" : node_list[0] if len(node_list) > 0 else 0,
                "NodeJ" : node_list[1] if len(node_list) > 1 else 0,
            })

        df = pd.DataFrame(rows).sort_values("ElemID").reset_index(drop=True)
        print(f"✅ Elements: {len(df)}개 로드됨")
        return df

    # ── Sections ──────────────────────────────
    def get_sections(self) -> pd.DataFrame:
        """GET /civil/sect"""
        raw = self.client.get("/civil/sect")
        assign = raw.get("Assign", {})

        rows = []
        for sec_id, props in assign.items():
            rows.append({
                "SecID" : int(sec_id),
                "Name"  : props.get("NAME", f"SEC{sec_id}"),
                "Type"  : props.get("SHAPE", ""),
                "Area"  : props.get("SECT", {}).get("AX", 0.0),
                "Iy"    : props.get("SECT", {}).get("IY", 0.0),
                "Iz"    : props.get("SECT", {}).get("IZ", 0.0),
            })

        df = pd.DataFrame(rows).sort_values("SecID").reset_index(drop=True)
        print(f"✅ Sections: {len(df)}개 로드됨")
        return df

    # ── Materials ─────────────────────────────
    def get_materials(self) -> pd.DataFrame:
        """GET /civil/matl"""
        raw = self.client.get("/civil/matl")
        assign = raw.get("Assign", {})

        rows = []
        for mat_id, props in assign.items():
            rows.append({
                "MatID"  : int(mat_id),
                "Name"   : props.get("NAME", f"MAT{mat_id}"),
                "Type"   : props.get("TYPE", ""),
                "E"      : props.get("ELAST", 0.0),   # Young's Modulus
                "GAMMA"  : props.get("GAMMA", 0.0),   # Unit Weight
                "POISSON": props.get("POISS", 0.3),
            })

        df = pd.DataFrame(rows).sort_values("MatID").reset_index(drop=True)
        print(f"✅ Materials: {len(df)}개 로드됨")
        return df

    # ── Boundary Conditions ───────────────────
    def get_boundaries(self) -> pd.DataFrame:
        """GET /civil/bndr"""
        raw = self.client.get("/civil/bndr")
        assign = raw.get("Assign", {})

        rows = []
        for bnd_id, props in assign.items():
            cond = props.get("ITEMS", [0, 0, 0, 0, 0, 0])
            rows.append({
                "BndID": int(bnd_id),
                "NodeID": props.get("NODE", 0),
                "Dx"  : bool(cond[0]) if len(cond) > 0 else False,
                "Dy"  : bool(cond[1]) if len(cond) > 1 else False,
                "Dz"  : bool(cond[2]) if len(cond) > 2 else False,
                "Rx"  : bool(cond[3]) if len(cond) > 3 else False,
                "Ry"  : bool(cond[4]) if len(cond) > 4 else False,
                "Rz"  : bool(cond[5]) if len(cond) > 5 else False,
            })

        df = pd.DataFrame(rows).sort_values("NodeID").reset_index(drop=True)
        print(f"✅ Boundaries: {len(df)}개 로드됨")
        return df

    # ── Node Loads ────────────────────────────
    def get_node_loads(self) -> pd.DataFrame:
        """GET /civil/nload → 노드 집중하중"""
        raw = self.client.get("/civil/nload")
        assign = raw.get("Assign", {})

        rows = []
        for lc_name, load_data in assign.items():
            for item in load_data if isinstance(load_data, list) else [load_data]:
                rows.append({
                    "LCName": lc_name,
                    "NodeID": item.get("NODE", 0),
                    "Fx"    : item.get("FX", 0.0),
                    "Fy"    : item.get("FY", 0.0),
                    "Fz"    : item.get("FZ", 0.0),
                    "Mx"    : item.get("MX", 0.0),
                    "My"    : item.get("MY", 0.0),
                    "Mz"    : item.get("MZ", 0.0),
                })

        df = pd.DataFrame(rows) if rows else pd.DataFrame()
        print(f"✅ Node Loads: {len(df)}개 로드됨")
        return df

    # ── Beam Loads ────────────────────────────
    def get_beam_loads(self) -> pd.DataFrame:
        """GET /civil/bload → 보 분포하중"""
        raw = self.client.get("/civil/bload")
        assign = raw.get("Assign", {})

        rows = []
        for lc_name, load_list in assign.items():
            items = load_list if isinstance(load_list, list) else [load_list]
            for item in items:
                rows.append({
                    "LCName": lc_name,
                    "ElemID": item.get("ELEM", 0),
                    "Dir"   : item.get("DIR", "GZ"),
                    "W1"    : item.get("W1", 0.0),
                    "W2"    : item.get("W2", 0.0),
                    "D1"    : item.get("D1", 0.0),
                    "D2"    : item.get("D2", 1.0),
                })

        df = pd.DataFrame(rows) if rows else pd.DataFrame()
        print(f"✅ Beam Loads: {len(df)}개 로드됨")
        return df

    # ── 전체 모델 한번에 추출 ─────────────────
    def extract_all(self) -> ModelData:
        """모든 모델 데이터를 일괄 추출"""
        print("\n📥 Civil NX 모델 데이터 추출 시작...\n")
        data = ModelData(
            load_cases = self.get_load_cases(),
            nodes      = self.get_nodes(),
            elements   = self.get_elements(),
            sections   = self.get_sections(),
            materials  = self.get_materials(),
            boundaries = self.get_boundaries(),
            node_loads = self.get_node_loads(),
            beam_loads = self.get_beam_loads(),
        )
        print("\n✅ 데이터 추출 완료\n")
        return data


# ─────────────────────────────────────────────
# 3. 실행
# ─────────────────────────────────────────────
if __name__ == "__main__":
    client = create_client(
        base_url="http://127.0.0.1:8090",
        mapi_key="YOUR_MAPI_KEY_HERE"
    )

    extractor = ModelExtractor(client)
    model     = extractor.extract_all()

    # ── 결과 미리보기 ─────────────────────────
    print("=" * 50)
    print("📋 Load Cases 목록")
    print("=" * 50)
    print(model.load_cases.to_string(index=False))

    print("\n" + "=" * 50)
    print("📋 Element 개수:", len(model.elements))
    print("📋 Node 개수   :", len(model.nodes))
