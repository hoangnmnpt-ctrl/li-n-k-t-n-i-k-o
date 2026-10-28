"""
base_drawing.py — Vẽ CHÂN CỘT lên tk.Canvas (mặt đứng theo phương N + mặt bằng bản đế) theo bảng màu của drawing.py:
gối bê tông, lớp vữa, bản đế, cột chữ I (kể lệch tâm), bu lông neo + long đen + đai ốc (+ đai ốc khoá), đường hàn, bản chắn cắt,
khối ứng suất ép dưới bản đế (đều / tuyến tính) và lực kéo neo (dòng lực), tô sáng bộ phận của kiểm tra đang chọn.

Tag bộ phận (khớp với tag trong base_engine): bp, conc, anchors, col, wflange, wweb, lug.
"""

from __future__ import annotations

import math

import drawing as D
from drawing import C_BOLT, C_DIM, C_PLATE, C_PLATE_L, C_STEEL, C_STEEL_L, C_STIFF, C_WEB, C_WELD, Scene, _arrow  # noqa: F401

C_CONC, C_CONC_L = "#D5D8DC", "#7B8794"
C_GROUT, C_GROUT_L = "#ECE5D3", "#A39A7F"


def _rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _dim_h(sc, x0, x1, y, txt):
    sc.line([(x0, y), (x1, y)], C_DIM, 1)
    for x in (x0, x1): sc.line([(x, y - 5), (x, y + 5)], C_DIM, 1)
    sc.text(((x0 + x1) / 2, y + 11), txt, color=C_DIM, size=8)


def _dim_v(sc, y0, y1, x, txt, anchor="w"):
    sc.line([(x, y0), (x, y1)], C_DIM, 1)
    for y in (y0, y1): sc.line([(x - 5, y), (x + 5, y)], C_DIM, 1)
    sc.text((x + (6 if anchor == "w" else -6), (y0 + y1) / 2), txt, color=C_DIM, size=8, anchor=anchor)


def elevation(inp: dict, R: dict, dem: dict | None, flow: bool = True) -> Scene:
    """Mặt đứng nhìn dọc phương B: x theo phương N (gốc tại tâm bản đế), y hướng lên; mặt trên bản đế ở y = tp."""
    sc = Scene()
    G = R["G"]; c = G["col"]; an = inp["anchor"]
    N, N2, tp, gr = G["N"], G["N2"], G["tp"], G["grout"]
    d = G["d"]; da = float(an["d"]); hef = float(an["hef"])
    ox, sx = G["ox"], -G["px"]                                # tâm cột, tâm gối (toạ độ bản đế)
    hdraw = min(G["ha"], hef + 0.35 * N)
    # gối + vữa + bản đế
    sc.poly(_rect(sx - N2 / 2, -gr - hdraw, sx + N2 / 2, -gr), C_CONC, C_CONC_L, 1, ("conc",))
    if G["ha"] > hdraw:
        for x in (sx - N2 / 2, sx + N2 / 2):
            sc.line([(x - 12, -gr - hdraw + 14), (x + 12, -gr - hdraw - 14)], C_CONC_L, 1)
    if gr > 0:
        sc.poly(_rect(-N / 2 - 25, -gr, N / 2 + 25, 0.0), C_GROUT, C_GROUT_L, 1, ("conc",))
    sc.poly(_rect(-N / 2, 0.0, N / 2, tp), C_PLATE, C_PLATE_L, 1, ("bp",))
    # cột: cánh +x (cánh trên SAP) và cánh −x, bụng giữa
    Hc = max(1.5 * d, 450.0)
    tfE, tfI = c["tfE"], c["tfI"]
    sc.poly(_rect(ox - d / 2 + tfI, tp, ox + d / 2 - tfE, tp + Hc), C_WEB, C_STEEL_L, 1, ("col", "wweb"))
    sc.poly(_rect(ox + d / 2 - tfE, tp, ox + d / 2, tp + Hc), C_STEEL, C_STEEL_L, 1, ("col", "wflange"))
    sc.poly(_rect(ox - d / 2, tp, ox - d / 2 + tfI, tp + Hc), C_STEEL, C_STEEL_L, 1, ("col", "wflange"))
    w = float(inp["weld"]["fl"]["w"])
    welds = ((d / 2, 1), (-d / 2, -1)) if inp["weld"].get("outerOnly") else ((d / 2, 1), (-d / 2, -1), (d / 2 - tfE, -1), (-d / 2 + tfI, 1))
    for x, s in welds:
        sc.poly([(ox + x, tp), (ox + x + s * w, tp), (ox + x, tp + w)], C_WELD, C_WELD, 1, ("wflange",), bbox=False)
    # bản chắn cắt (dưới tâm cột)
    if inp["lug"].get("on"):
        lg = inp["lug"]; tl = float(lg["tl"])
        sc.poly(_rect(ox - tl / 2, -float(lg["H"]), ox + tl / 2, 0.0), C_STIFF, C_PLATE_L, 1, ("lug",))
    # bu lông neo (mỗi vị trí x một thanh nhìn thấy)
    wB, wT = G["washer"]
    nuts = 2 if an.get("lockNut") else 1
    hooked = an.get("type") == "hooked"
    for x in sorted(set(round(a["x"], 3) for a in G["anchors"])):
        top = tp + wT + nuts * 0.9 * da + 0.6 * da
        sc.poly(_rect(x - da / 2, -gr - hef, x + da / 2, top), C_BOLT, C_BOLT, 1, ("anchors",))
        sc.poly(_rect(x - wB / 2, tp, x + wB / 2, tp + wT), "#8B8F96", C_BOLT, 1, ("anchors",))
        for k in range(nuts):
            y0 = tp + wT + k * 0.9 * da
            sc.poly(_rect(x - 0.85 * da, y0, x + 0.85 * da, y0 + 0.9 * da), "#3B4048", C_BOLT, 1, ("anchors",))
        if hooked:
            eh = float(an.get("eh") or 3 * da); s = 1 if x < 0 else -1
            sc.poly(_rect(min(x, x + s * eh), -gr - hef - da, max(x, x + s * eh), -gr - hef), C_BOLT, C_BOLT, 1, ("anchors",))
        else:
            hs = G["head"] / 2
            sc.poly(_rect(x - hs, -gr - hef - 0.9 * da, x + hs, -gr - hef), "#3B4048", C_BOLT, 1, ("anchors",))
    # kích thước, nhãn
    gap = 0.07 * N2
    _dim_h(sc, -N / 2, N / 2, -gr - hdraw - gap, f"N = {N:g}")
    _dim_h(sc, sx - N2 / 2, sx + N2 / 2, -gr - hdraw - 2.2 * gap, f"N2 = {N2:g}")
    xa = G["ax"]
    _dim_v(sc, -gr - hef, -gr, xa + 0.6 * (sx + N2 / 2 - xa) + 4, f"hef = {hef:g}")
    _dim_v(sc, 0.0, tp, sx - N2 / 2 - 20, f"tp = {tp:g}", anchor="e")
    if gr > 0: _dim_v(sc, -gr, 0.0, sx - N2 / 2 - 60, f"vữa {gr:g}", anchor="e")
    sc.text((ox, tp + Hc * 0.55), "CỘT", color=C_STEEL_L, size=10, bold=True)
    sc.text((sx, -gr - hdraw * 0.55), f"{'BỆ' if inp['ped'].get('isPed', True) else 'MÓNG'} {inp['ped'].get('mat', '')} f'c = {float(inp['ped']['fc']):g} MPa",
            color=C_CONC_L, size=9, bold=True)
    sc.text((0, -gr - hdraw - 3.4 * gap), f"Bản đế {G['N']:g}×{G['B']:g}×{tp:g} — {len(G['anchors'])} neo M{da:g} cấp {G['am']['name']}"
            f" — {c['sec']}", size=9, bold=True)
    sc.bbox_pts += [(sx - N2 / 2 - 120, tp + Hc + 190), (sx + N2 / 2 + 120, -gr - hdraw - 3.8 * gap)]

    # ---- dòng lực ----
    if dem and flow:
        sg = dem.get("sM33", 1)
        Y, fp = dem.get("Y33"), dem.get("q33", 0.0)
        if fp > 0 and Y and dem["case33"] not in ("nosol", "tension", "—"):
            hq = min(0.18 * N, 120.0)
            y0 = -gr - 8
            lin = dem.get("prof33") == "linear"
            Yd = min(Y if not math.isinf(Y) else 1e18, N)
            if dem["case33"] == "axial" and not lin:
                Yd = N
            e0 = N / 2 if sg > 0 else -N / 2                 # mép ép lớn nhất
            e1 = e0 - sg * Yd
            h1 = hq * (1 - Yd / Y) if lin and not math.isinf(Y) else (0.0 if lin else hq)
            if lin and math.isinf(Y): h1 = hq
            sc.poly([(e0, y0), (e1, y0), (e1, y0 - h1), (e0, y0 - hq)], "#9EC5FE", D.C_COMP, 1, ("conc", "force"), bbox=False)
            for k in range(5):
                t = (k + 0.5) / 5
                xx = e0 + (e1 - e0) * t
                hh = hq + (h1 - hq) * t
                if hh > 8:
                    sc.line([(xx, y0 - hh + 6), (xx, y0 - 2)], D.C_COMP, 2, arrow="last", tags=("force",), anim=True, bbox=False)
            sc.text((sx + N2 / 2 + 14, y0 - hq / 2), f"fp = {fp:.2f} MPa\nY = {'∞' if math.isinf(Y) else format(Y, '.0f')} mm",
                    color=D.C_COMP, size=8, bold=True, anchor="w")
        lines = {}
        for a, t in zip(G["anchors"], dem["T"]):
            if t > 1e-6: lines[round(a["x"], 3)] = lines.get(round(a["x"], 3), 0.0) + t
        for x, t in lines.items():
            sc.line([(x, -gr - 0.45 * hef), (x, -gr - 0.45 * hef - 90)], D.C_TEN, 3, dash=(10, 6), arrow="last", tags=("force",), anim=True, bbox=False)
            sc.text((x + 14, -gr - 0.45 * hef - 45), f"T = {t:.1f} kN", color=D.C_TEN, size=8, bold=True, anchor="w")
        top = tp + Hc
        if abs(dem["N"]) > 1e-6:
            if dem["N"] < 0:
                _arrow(sc, (ox, top + 170), (0.0, -1.0), 140, False, f"N = {dem['N']:.1f} kN")
            else:
                _arrow(sc, (ox, top + 30), (0.0, 1.0), 140, True, f"N = {dem['N']:.1f} kN")
        if abs(dem["V2"]) > 1e-6:
            s = 1 if dem["V2"] > 0 else -1
            x0 = ox - d / 2 - 230 if s > 0 else ox + d / 2 + 230
            _arrow(sc, (x0, top - 90), (s, 0.0), 180, True, f"V2 = {dem['V2']:.1f} kN")
        if abs(dem["M33"]) > 1e-6:
            sc.text((ox + d / 2 + 30, top + 20), f"M33 = {dem['M33']:.1f} kN·m", color=D.C_TEN, size=8, bold=True, anchor="w")
    return sc


def plate_face(inp: dict, R: dict, dem: dict | None) -> Scene:
    """Mặt bằng bản đế: x theo phương N, y (trên hình) theo phương B; gốc tại tâm bản đế."""
    sc = Scene()
    G = R["G"]; c = G["col"]; an = inp["anchor"]
    N, B, N2, B2 = G["N"], G["B"], G["N2"], G["B2"]
    d, tw = G["d"], c["tw"]
    ox, oz, sx, sz = G["ox"], G["oz"], -G["px"], -G["pz"]
    da = float(an["d"]); wB = G["washer"][0]
    sc.poly(_rect(sx - N2 / 2, sz - B2 / 2, sx + N2 / 2, sz + B2 / 2), "#E9ECEF", C_CONC_L, 1)
    sc.poly(_rect(-N / 2, -B / 2, N / 2, B / 2), C_PLATE, C_PLATE_L, 1, ("bp",))
    if inp["lug"].get("on"):
        lg = inp["lug"]; tl, bl = float(lg["tl"]), float(lg["bl"])
        sc.line(_rect(ox - tl / 2, oz - bl / 2, ox + tl / 2, oz + bl / 2) + [(ox - tl / 2, oz - bl / 2)], C_PLATE_L, 2, dash=(6, 3), tags=("lug",))
    sc.poly(_rect(ox + d / 2 - c["tfE"], oz - c["bfE"] / 2, ox + d / 2, oz + c["bfE"] / 2), C_STEEL, C_STEEL_L, 1, ("col", "wflange"))
    sc.poly(_rect(ox - d / 2, oz - c["bfI"] / 2, ox - d / 2 + c["tfI"], oz + c["bfI"] / 2), C_STEEL, C_STEEL_L, 1, ("col", "wflange"))
    sc.poly(_rect(ox - d / 2 + c["tfI"], oz - tw / 2, ox + d / 2 - c["tfE"], oz + tw / 2), C_STEEL, C_STEEL_L, 1, ("col", "wweb"))
    w = float(inp["weld"]["fl"]["w"])
    bfm = max(c["bfE"], c["bfI"])
    sc.line(_rect(ox - d / 2 - w, oz - bfm / 2 - w, ox + d / 2 + w, oz + bfm / 2 + w) + [(ox - d / 2 - w, oz - bfm / 2 - w)],
            C_WELD, 1, dash=(3, 3), tags=("wflange", "wweb"), bbox=False)
    T = dem["T"] if dem else [0.0] * len(G["anchors"])
    for a, t in zip(G["anchors"], T):
        x, y = a["x"], a["y"]
        sc.poly(_rect(x - wB / 2, y - wB / 2, x + wB / 2, y + wB / 2), "#B8BCC2", C_BOLT, 1, ("anchors",))
        sc.circle((x, y), G["hole"] / 2, "#FFFFFF", C_BOLT, ("anchors",))
        sc.circle((x, y), da / 2, C_BOLT, C_BOLT, ("anchors",))
        if t > 1e-6:
            sc.text((x, y + wB / 2 + 12), f"T = {t:.1f}", color=D.C_TEN, size=8, bold=True)
    _dim_h(sc, -N / 2, N / 2, sz + B2 / 2 + 30, f"N = {N:g}")
    _dim_h(sc, sx - N2 / 2, sx + N2 / 2, sz + B2 / 2 + 62, f"N2 = {N2:g}")
    _dim_v(sc, -B / 2, B / 2, N / 2 + 20, f"B = {B:g}")
    _dim_v(sc, sz - B2 / 2, sz + B2 / 2, sx + N2 / 2 + 24, f"B2 = {B2:g}")
    _dim_h(sc, -N / 2, -G["ax"], sz - B2 / 2 - 24, f"ex = {float(an['ex']):g}")
    _dim_v(sc, -B / 2, -G["ay"], sx - N2 / 2 - 24, f"ey = {float(an['ey']):g}", anchor="e")
    sc.text((0, sz - B2 / 2 - 62), f"MẶT BẰNG BẢN ĐẾ {N:g}×{B:g}×{G['tp']:g} — {len(G['anchors'])} neo M{da:g} (lỗ {G['hole']:g})",
            size=9, bold=True)
    sc.bbox_pts += [(sx - N2 / 2 - 110, sz + B2 / 2 + 80), (sx + N2 / 2 + 170, sz - B2 / 2 - 80)]
    return sc
