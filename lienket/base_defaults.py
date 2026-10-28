"""Bộ thông số mặc định và các mẫu CHÂN CỘT (Column base — CB), trường nhập theo RAM Connection (Base plate)."""

from __future__ import annotations

import copy

BASE = {
    "name": "CB-01",
    "gen": {"designCode": "AISC 2010 LRFD"},
    # cột tại chân (đầu I của phần tử SAP); tiết diện I tổ hợp theo quy cách của tool
    "col": {"sec": "400.8-200.12", "mat": "Q345", "L": 6.0, "jointEnd": "I"},
    # bản đế: N dọc chiều cao tiết diện cột (phương x, uốn M33), B theo bề rộng cánh (phương z, uốn M22)
    "plate": {"N": 650, "B": 350, "tp": 40, "mat": "Q345"},
    # bệ bê tông (đồng tâm với bản đế) + lớp vữa
    "ped": {"N2": 850, "B2": 550, "h": 800, "fc": 25.0, "grout": 50, "cracked": True, "lw": 1.0,
            "reinf": True, "fyr": 400, "AsN": 1608, "AsV": 804},       # cốt thép neo: As kéo (8Ø16), As cắt (4Ø16)
    # neo: lưới nx × ny (chỉ các neo trên chu vi lưới), khoảng cách từ tâm neo tới mép bản ex (phương N) / ey (phương B)
    "anchor": {"grade": "5.6", "d": 24, "nx": 2, "ny": 2, "ex": 60, "ey": 60, "hef": 400, "head": "hex", "plateB": 60,
               "washer": 76, "washerT": 10, "thread": "N", "shearAll": True, "torqued": False},
    # cỡ hàn nhập theo RAM: D (1/16 in); engine dùng w (mm) = D × 1.5875
    "weld": {"electrode": "E70XX", "fl": {"D": 5, "w": 7.9375}, "web": {"D": 4, "w": 6.35}},
    # truyền lực cắt: friction (ma sát) · anchors (neo) · lug (bản chắn cắt)
    "shear": {"mode": "anchors", "mu": 0.55},
    "lug": {"bl": 200, "H": 150, "tl": 20, "mat": "Q345", "D": 6, "w": 9.525},
    "opt": {"aci": True, "bear": True, "sheared": True},
    # N > 0 kéo (nhổ) · V2 dọc phương N (cánh cột) · V3 dọc phương B · M33 > 0: mép +x (phải) chịu nén · M22 > 0: mép +z chịu nén
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
    "Mẫu chân cột ngàm — 4 neo góc": {},
    "Mẫu chân cột ngàm — 6 neo + bản chắn cắt": {
        "name": "CB-02",
        "col": {"sec": "500.8-250.14"},
        "plate": {"N": 760, "B": 400, "tp": 45},
        "ped": {"N2": 1000, "B2": 650, "h": 900},
        "anchor": {"d": 30, "nx": 2, "ny": 3, "ex": 65, "ey": 60, "hef": 450, "washer": 76, "washerT": 13},
        "shear": {"mode": "lug"},
        "lug": {"bl": 250, "H": 180, "tl": 28, "D": 8},
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
        "anchor": {"d": 22, "nx": 2, "ny": 2, "ex": 160, "ey": 65, "hef": 450, "washer": 64, "washerT": 8},
        "loads": [
            {"name": "N_max (nén)", "N": -420, "V2": 35, "V3": 0, "M33": 0, "M22": 0},
            {"name": "Uplift", "N": 90, "V2": 20, "V3": 8, "M33": 0, "M22": 0},
        ],
    },
}
