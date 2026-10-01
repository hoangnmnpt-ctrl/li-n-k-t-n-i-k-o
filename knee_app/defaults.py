"""Bộ thông số mặc định và các mẫu knee (trường nhập theo RAM Connection)."""

from __future__ import annotations

import copy

BASE = {
    "name": "K-01", "type": "dung",
    "gen": {"designCode": "AISC 2010 LRFD", "frameStab": False},
    "beam": {"sec": "(580-380).6-200.10", "mat": "Q345", "L": 6.0, "jointEnd": "I", "slope": 10.0, "topIsOuter": True,
             "flangeStiff": {"on": False, "t": 8}},
    "col": {"sec": "(280-570).8-250.16", "mat": "Q345", "L": 7.0, "jointEnd": "J", "topIsOuter": True, "innerStraight": False},
    "plate": {"extension": "external", "alignment": "vertical", "holeType": "STD",
              "tp": 20, "mat": "Q345", "g": 110, "Leh": 45, "Lev": 45, "flushExt": 25.4, "mitre": "perp", "theta": 45,
              "extE": True, "pfoE": 50, "pfiE": 50, "nE": 1, "pbE": 75, "stiffE": {"on": False, "ts": 10, "L": 200, "mat": "Q345"},
              "extI": False, "pfoI": 50, "pfiI": 50, "nI": 1, "pbI": 75, "stiffI": {"on": False, "ts": 10, "L": 200, "mat": "Q345"}},
    "bolt": {"grade": "8.8", "d": 24, "thread": "N", "snug": False, "holeType": "STD"},
    # cỡ hàn nhập theo RAM: D (1/16 in); engine dùng w (mm) = D × 1.5875
    "weld": {"electrode": "E70XX", "flE": {"type": "fillet", "D": 5, "w": 7.94, "electrode": "E70XX"},
             "flI": {"type": "fillet", "D": 5, "w": 7.94, "electrode": "E70XX"}, "web": {"D": 4, "w": 6.35, "electrode": "E70XX"}},
    "sup": {"useFlange": False, "bAuto": True, "t": 20, "b": 200, "mat": "Q345", "condE": "top_cap", "condI": "cont_stiff",
            "topOffset": 0, "tcap": 14, "kw": 6,
            "stE": {"on": True, "bs": 110, "ts": 12, "clip": 15, "mat": "Q345", "wf": 8, "ww": 8, "fullDepth": True},
            "stI": {"on": True, "bs": 110, "ts": 12, "clip": 15, "mat": "Q345", "wf": 8, "ww": 8, "fullDepth": True},
            "doubler": 0, "diag": {"on": True, "b": 80, "t": 10, "mat": "Q345"}},
    # một bộ sườn ngang như RAM (Transverse stiffeners); 'at' = both | external | internal
    "stiff": {"on": True, "at": "both", "fullDepth": True, "bs": 110, "cc": 15, "ts": 12, "mat": "Q345",
              "weldType": "Fillet", "electrode": "E70XX", "D": 5},
    "pz": {"on": False, "tw": 10, "tfo": 16, "tfi": 20, "mat": "Q345"},
    "opt": {"axialRelief": True, "directional": True, "shearAll": False, "flangeWeldMin": False,
            "webBuckling": True, "pzSubtractShear": False, "sheared": True, "holeDef": True},
    "loads": [
        {"name": "M_min", "Vb": 85, "Nb": -45, "Mb": -240, "Vc": 45, "Nc": -95, "Mc": -240},
        {"name": "M_max", "Vb": -35, "Nb": 25, "Mb": 115, "Vc": -20, "Nc": 40, "Mc": 115},
        {"name": "V2_max", "Vb": 60, "Nb": -30, "Mb": -185, "Vc": 52, "Nc": -70, "Mc": -185},
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
    "Mẫu knee đứng (Vertical)": {},
    "Mẫu knee ngang (Horizontal)": {
        "name": "K-02",
        "beam": {"sec": "(680-380).6-200.10"},
        "col": {"sec": "(230-480).6-200.10"},
        "plate": {"alignment": "horizontal"},
        "sup": {"condE": "cont_stiff", "condI": "cont_stiff", "tcap": 0},
        "stiff": {"bs": 95, "ts": 20},
    },
    "Mẫu knee xiên (Perpendicular)": {
        "name": "K-03",
        "plate": {"alignment": "perpendicular"},
    },
    "Đối chứng RAM #11": {
        "name": "RAM #11",
        "beam": {"sec": "600.5-150.8", "L": 5.0, "jointEnd": "I", "slope": 5.71, "topIsOuter": True},
        "col": {"sec": "(388-588).8-225.14", "L": 3.0, "jointEnd": "J", "topIsOuter": True},
        "plate": {"extension": "external", "alignment": "perpendicular", "tp": 16, "g": 125, "Leh": 50, "Lev": 50, "flushExt": 25.4,
                  "pfoE": 50, "pfiE": 50, "nE": 1, "pfiI": 50, "nI": 1},
        "weld": {"flE": {"type": "cjp", "D": 8, "w": 12.7}, "flI": {"type": "fillet", "D": 8, "w": 12.7}, "web": {"D": 8, "w": 12.7}},
        "sup": {"t": 16, "condE": "cont_unstiff", "condI": "cont_stiff", "topOffset": 600, "tcap": 0, "kw": 25.4,
                "diag": {"on": False}},
        "stiff": {"on": True, "at": "internal", "fullDepth": True, "bs": 82.5, "cc": 10, "ts": 16, "electrode": "AS E41XX", "D": 8},
        "opt": {"webBuckling": False},
        "loads": [
            {"name": "M_max", "Vb": 32.01, "Nb": -3.57, "Mb": 145.16, "Vc": 0, "Nc": 0, "Mc": 0},
            {"name": "M_min", "Vb": -42.97, "Nb": 28.29, "Mb": -183.09, "Vc": 0, "Nc": 0, "Mc": 0},
            {"name": "P_max", "Vb": -53.78, "Nb": 2.55, "Mb": -112.62, "Vc": 0, "Nc": 0, "Mc": 0},
            {"name": "P_min", "Vb": -12.83, "Nb": -25.8, "Mb": 11.66, "Vc": 0, "Nc": 0, "Mc": 0},
            {"name": "V2_max", "Vb": 26.16, "Nb": 37.97, "Mb": -92.86, "Vc": 0, "Nc": 0, "Mc": 0},
            {"name": "V3_max", "Vb": -12.99, "Nb": 1.38, "Mb": 11.88, "Vc": 0, "Nc": 0, "Mc": 0},
        ],
    },
}
