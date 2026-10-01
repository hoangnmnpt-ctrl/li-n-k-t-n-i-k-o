"""Bộ thông số mặc định và các mẫu liên kết nối dầm (trường nhập theo RAM Connection — Beam splice, moment end plate)."""

from __future__ import annotations

import copy

BASE = {
    "name": "BS-01", "type": "straight",          # straight = Beam splice · apex = Apex (hai dầm nghiêng đối xứng)
    "gen": {"designCode": "AISC 2010 LRFD"},
    # dầm 1 = dầm trái; dầm 2 = dầm phải. "same": dầm 2 giống dầm 1 (đầu nối ở phía đối diện)
    "beam1": {"sec": "500.8-200.12", "mat": "Q345", "L": 6.0, "jointEnd": "J"},
    "beam2": {"same": True, "sec": "500.8-200.12", "mat": "Q345", "L": 6.0, "jointEnd": "I"},
    "slope": 0.0,                                 # Apex: góc dốc của mỗi dầm so với phương ngang (độ)
    "plate": {"extension": "both", "holeType": "STD",
              "tp1": 20, "mat1": "Q345", "tp2": 20, "mat2": "Q345",
              "g": 110, "Leh": 45, "Lev": 45, "flushExt": 25.4,
              "extT": True, "pfoT": 50, "pfiT": 50, "nT": 1, "pbT": 75, "stiffT": {"on": False, "ts": 10, "L": 200, "mat": "Q345"},
              "extB": True, "pfoB": 50, "pfiB": 50, "nB": 1, "pbB": 75, "stiffB": {"on": False, "ts": 10, "L": 200, "mat": "Q345"}},
    "bolt": {"grade": "8.8", "d": 24, "thread": "N", "snug": False, "holeType": "STD"},
    # cỡ hàn nhập theo RAM: D (1/16 in); engine dùng w (mm) = D × 1.5875
    "weld": {"electrode": "E70XX",
             "flT": {"type": "fillet", "D": 6, "w": 9.525, "electrode": "E70XX"},
             "flB": {"type": "fillet", "D": 6, "w": 9.525, "electrode": "E70XX"},
             "web": {"D": 4, "w": 6.35, "electrode": "E70XX"}},
    "opt": {"axialRelief": True, "directional": True, "shearAll": False, "flangeWeldMin": False,
            "sheared": True, "holeDef": True, "hRef": "face"},
    # N > 0 kéo · M > 0 căng cánh DƯỚI (mô men dương) · M < 0 căng cánh TRÊN (mô men âm)
    "loads": [
        {"name": "M_max (+)", "N": -10, "V": 90, "M": 250},
        {"name": "M_min (−)", "N": 15, "V": -130, "M": -300},
        {"name": "V_max", "N": -5, "V": 150, "M": -60},
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
    "Mẫu nối dầm — bích mở rộng 2 phía (4E)": {},
    "Mẫu nối dầm — bích bằng (2FU)": {
        "name": "BS-02",
        "beam1": {"sec": "400.8-180.10"}, "beam2": {"sec": "400.8-180.10"},
        "plate": {"extension": "flush", "tp1": 22, "tp2": 22, "g": 100, "Leh": 40, "Lev": 40, "pfiT": 45, "pfiB": 45},
        "bolt": {"d": 22},
        "loads": [{"name": "M_max (+)", "N": 0, "V": 60, "M": 110}, {"name": "M_min (−)", "N": 0, "V": -60, "M": -100}],
    },
    "Mẫu Apex — đỉnh mái dốc 10°": {
        "name": "AP-01", "type": "apex", "slope": 10.0,
        "plate": {"extension": "both"},
        "loads": [
            {"name": "M_hogging", "N": -30, "V": 70, "M": -300},
            {"name": "M_uplift", "N": 40, "V": -50, "M": 170},
        ],
    },
    "Mẫu nối dầm — mô men 1 chiều (bích nhô cánh trên)": {
        "name": "BS-03",
        "plate": {"extension": "top"},
        "loads": [{"name": "M_hogging", "N": 0, "V": 100, "M": -280}],
    },
}
