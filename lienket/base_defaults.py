"""Bộ thông số mặc định và các mẫu CHÂN CỘT (Column base — CB), trường nhập theo RAM Connection (Base plate)."""

from __future__ import annotations

import copy

BASE = {
    "name": "CB-01",
    # Analysis + Design criteria (như RAM)
    "gen": {"designCode": "AISC 2010 LRFD", "concCode": "ACI 318-11", "seismic": False, "bearCalc": "complete", "friction": False,
            "axis": "both", "pressure": "uniform", "compat": False},
    # cột tại chân (đầu I của phần tử SAP); ox / oz: lệch tâm cột so với tâm bản đế (Longitudinal / Transversal offset)
    "col": {"sec": "400.8-200.12", "mat": "Q345", "L": 6.0, "jointEnd": "I", "ox": 0.0, "oz": 0.0},
    # bản đế: N dọc chiều cao tiết diện cột (phương x, uốn M33), B theo bề rộng cánh (phương z, uốn M22)
    # pos: vị trí bản trên gối (center | custom: px, pz = lệch tâm bản so với tâm gối); A2A1: tỷ số A2/A1 tự nhập
    "plate": {"N": 650, "B": 350, "tp": 40, "mat": "Q345", "shape": "rect", "ctype": "unstiffened",
              "pos": "center", "px": 0.0, "pz": 0.0, "overA2": False, "A2A1": 4.0},
    # gối bê tông: bệ (pedestal) hoặc móng; mat → f'c (Custom: nhập f'c); lớp vữa
    "ped": {"isPed": True, "N2": 850, "B2": 550, "h": 800, "mat": "C25/30", "fc": 25.0, "groutOn": True, "grout": 50},
    # neo (Anchor position): longitudinal (hàng neo ở hai đầu theo phương N) | transversal (hai đầu theo phương B)
    "anchor": {"layout": "longitudinal", "nr": 1, "npr": 2, "sr": 80, "ex": 60, "ey": 60,
               "type": "headed", "head": "hex", "eh": 100, "lockNut": False,
               "grade": "Class 5.6", "d": 30, "hef": 400, "cracked": True, "brittle": False, "welded": False},
    # cốt thép neo: primary (anchor reinforcement — thay phá vỡ bê tông, báo As yêu cầu) | supplementary (Condition A, φ = 0.75)
    "reinf": {"type": "primary", "T": True, "barT": "no. 5", "fyT": 413.69, "nT": 8,
              "V": True, "barV": "no. 4", "fyV": 413.69, "nVx": 4, "nVy": 4},
    # một cỡ hàn D (1/16 in) như RAM; outerOnly: chỉ hàn mặt ngoài hai cánh
    "weld": {"electrode": "E70XX", "D": 5, "outerOnly": False, "fl": {"D": 5, "w": 7.9375}, "web": {"D": 5, "w": 7.9375}},
    "lug": {"on": False, "bl": 200, "H": 150, "tl": 20, "mat": "Q345", "D": 6, "w": 9.525},
    # Optimization criteria (như RAM)
    "opt": {"optTp": True, "tpMax": 45, "tpMin": 6, "colRole": "main",
            "optN": True, "pMaxN": 381, "pMinN": 38.1, "optB": True, "pMaxB": 381, "pMinB": 38.1, "dimInc": 25.4,
            "optD": True, "hefMin": 304.8, "keepPos": "initial", "vsaMax": 0.4},
    # N > 0 kéo (nhổ) · V2 dọc phương N · V3 dọc phương B · M33 > 0: mép +x chịu nén · M22 > 0: mép +z chịu nén
    "loads": [
        {"name": "N_max (nén)", "N": -650, "V2": 40, "V3": 0, "M33": 30, "M22": 0},
        {"name": "M_max", "N": -250, "V2": 70, "V3": 0, "M33": 160, "M22": 0},
        {"name": "Uplift", "N": 120, "V2": 35, "V3": 10, "M33": 20, "M22": 0},
    ],
}


def merge(base: dict, over: dict) -> dict:
    """Trộn sâu (giữ khóa mặc định khi file lưu thiếu)."""
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


PRESETS = {
    "Mẫu chân cột ngàm — 4 neo hai đầu": {},
    "Mẫu chân cột ngàm — 6 neo + bản chắn cắt": {
        "name": "CB-02",
        "col": {"sec": "500.8-250.14"},
        "plate": {"N": 760, "B": 400, "tp": 45},
        "ped": {"N2": 1000, "B2": 650, "h": 900},
        "anchor": {"d": 30, "npr": 3, "ex": 65, "ey": 60, "hef": 450},
        "lug": {"on": True, "bl": 250, "H": 180, "tl": 28, "D": 8},
        "loads": [
            {"name": "N_max (nén)", "N": -900, "V2": 60, "V3": 0, "M33": 60, "M22": 0},
            {"name": "M_max", "N": -320, "V2": 120, "V3": 0, "M33": 280, "M22": 0},
            {"name": "Uplift", "N": 150, "V2": 60, "V3": 15, "M33": 40, "M22": 0},
        ],
    },
    "Mẫu chân cột khớp — 4 neo trong cánh": {
        "name": "CB-03",
        "col": {"sec": "350.6-180.10"},
        "plate": {"N": 470, "B": 230, "tp": 20},
        "ped": {"N2": 600, "B2": 400, "h": 700},
        "anchor": {"d": 22, "ex": 160, "ey": 65, "hef": 450, "welded": True},
        "loads": [
            {"name": "N_max (nén)", "N": -420, "V2": 35, "V3": 0, "M33": 0, "M22": 0},
            {"name": "Uplift", "N": 90, "V2": 20, "V3": 8, "M33": 0, "M22": 0},
        ],
    },
    "Mẫu chân cột hai phương — biaxial, phân bố tam giác": {
        "name": "CB-04",
        "gen": {"axis": "biaxial", "pressure": "triangular", "compat": True},
        "col": {"sec": "400.8-250.14"},
        "plate": {"N": 650, "B": 450, "tp": 40},
        "ped": {"N2": 900, "B2": 700, "h": 900},
        "anchor": {"npr": 3, "ex": 60, "ey": 60, "d": 27, "hef": 450, "welded": True},
        "weld": {"D": 8},
        "loads": [
            {"name": "Biaxial 1", "N": -400, "V2": 60, "V3": 30, "M33": 150, "M22": 40},
            {"name": "Biaxial 2", "N": 80, "V2": 40, "V3": 25, "M33": 60, "M22": 25},
        ],
    },
    "RAM CB 1 — Pinned BP (I 300x215x5x10)": {
        "name": "Pinned BP", "desc": "COT KHUNG CHINH: 4M27 (4.6), PL.16mm",
        "gen": {"designCode": "AISC 2010 LRFD", "concCode": "ACI 318-08", "seismic": False, "bearCalc": "complete", "friction": False,
                "axis": "biaxial", "pressure": "uniform", "compat": True},
        "opt": {"pMinB": 50},
        "col": {"sec": "I 300x215x5x10", "mat": "Q345", "ox": 0.0, "oz": 0.0},
        "plate": {"N": 350, "B": 220, "tp": 16, "mat": "Q345", "pos": "center", "overA2": False},
        "ped": {"isPed": False, "N2": 1000, "B2": 1000, "h": 2000, "mat": "C30", "groutOn": True, "grout": 50},
        "anchor": {"layout": "longitudinal", "nr": 1, "npr": 2, "ex": 115, "ey": 50, "type": "headed", "head": "hex",
                   "lockNut": False, "d": 27, "hef": 800, "grade": "Class 4.6", "cracked": False, "brittle": False, "welded": False},
        "reinf": {"type": "primary", "T": True, "barT": "no. 10", "fyT": 275.79, "nT": 50,
                  "V": True, "barV": "no. 18", "fyV": 275.79, "nVx": 10, "nVy": 10},
        "weld": {"electrode": "E70XX", "D": 5, "outerOnly": False},
        "lug": {"on": False},
        "loads": [
            {"name": "Mmax", "N": 0, "V2": 0, "V3": 0, "M22": 0, "M33": 0},
            {"name": "Pmax", "N": -214, "V2": 60, "V3": 0, "M22": 0, "M33": 0},
            {"name": "Vmax", "N": -195, "V2": 70, "V3": 10, "M22": 0, "M33": 0},
            {"name": "Mmin", "N": 0, "V2": 0, "V3": 0, "M22": 0, "M33": 0},
            {"name": "Pmin", "N": 110, "V2": 23, "V3": 10, "M22": 0, "M33": 0},
        ],
    },
}
