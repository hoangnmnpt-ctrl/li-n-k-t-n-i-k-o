"""
splice_drawing.py — Vẽ liên kết nối dầm lên tk.Canvas (mặt đứng + mặt bản đầu) theo bảng màu của knee_app/drawing.py:
dầm màu xanh, hai bản đầu màu vàng cam, bu lông, đường hàn, sườn bản đầu (4ES), mũi tên lực chạy nét,
tô sáng bộ phận của kiểm tra đang chọn. Dùng lại Scene / canvas / thang màu D/C của knee_app.

Tag bộ phận (khớp với tag trong splice_engine): plate1, plate2, boltsT, boltsB, m{k}weldT, m{k}weldB, m{k}webweld, m{k}web.
"""

from __future__ import annotations

import math

from _knee import K  # noqa: F401
import drawing as D
from drawing import (C_BOLT, C_DIM, C_PLATE, C_PLATE_L, C_STEEL, C_STEEL_L, C_STIFF, C_TXT, C_WEB, C_WELD, KneeCanvas, Scene,  # noqa: F401
                     _arrow, add, ang, heat_color, mul, perp, shade)

Scene = Scene
KneeCanvas = KneeCanvas
heat_color = heat_color


def _beam_dirs(G: dict) -> tuple[tuple, tuple]:
    """Hướng trục (đơn vị) đi ra xa mặt nối của dầm 1 (trái) và dầm 2 (phải)."""
    a = G["alpha"]
    if G["type"] == "apex":
        return ang(180 + a), ang(-a)          # đỉnh mái: cả hai dầm hạ thấp dần ra xa bản
    return (-1.0, 0.0), (1.0, 0.0)


def elevation(inp: dict, R: dict, dem: dict | None, flow: bool = True) -> Scene:
    sc = Scene()
    G = R["G"]; pl = inp["plate"]
    dp, tfT, tfB = G["dp"], G["tfT"], G["tfB"]
    tp1, tp2 = float(pl["tp1"]), float(pl["tp2"])
    sTop, sBot = G["sTop"], G["sBot"]
    Lb = max(1.8 * dp, 520.0)
    u1, u2 = _beam_dirs(G)
    x0 = {1: -tp1, 2: tp2}
    u = {1: u1, 2: u2}
    db = float(inp["bolt"]["d"])
    wT = inp["weld"]["flT"]["w"] if inp["weld"]["flT"]["type"] == "fillet" else 0.0
    wB = inp["weld"]["flB"]["w"] if inp["weld"]["flB"]["type"] == "fillet" else 0.0

    # ---- hai bản đầu ----
    for k, (xa, xb) in ((1, (-tp1, 0.0)), (2, (0.0, tp2))):
        sc.poly([(xa, -sTop), (xb, -sTop), (xb, -sBot), (xa, -sBot)], C_PLATE, C_PLATE_L, 1, (f"plate{k}",))

    # ---- hai dầm ----
    for k in (1, 2):
        xs, uu = x0[k], u[k]
        P = lambda y: (xs, y)
        off = lambda pt: add(pt, mul(uu, Lb))
        webp = [P(-tfT), P(-(dp - tfB)), off(P(-(dp - tfB))), off(P(-tfT))]
        sc.poly(webp, C_WEB, C_STEEL_L, 1, (f"m{k}webweld", f"m{k}web"))
        sc.poly([P(0.0), P(-tfT), off(P(-tfT)), off(P(0.0))], C_STEEL, C_STEEL_L, 1, (f"m{k}weldT",))
        sc.poly([P(-(dp - tfB)), P(-dp), off(P(-dp)), off(P(-(dp - tfB)))], C_STEEL, C_STEEL_L, 1, (f"m{k}weldB",))
        # đường hàn góc ở 4 góc cánh–bản (tam giác)
        for (py, vy, w, tag) in ((0.0, 1, wT, f"m{k}weldT"), (-tfT, -1, wT, f"m{k}weldT"),
                                 (-dp, -1, wB, f"m{k}weldB"), (-(dp - tfB), 1, wB, f"m{k}weldB")):
            if w > 0:
                sc.poly([P(py), (xs, py + vy * w), add(P(py), mul(uu, w))], C_WELD, C_WELD, 1, (tag,), bbox=False)
        # sườn bản đầu 4ES (tam giác trên phần nhô)
        for side, ext_y, py, sgn in (("T", sTop, 0.0, 1), ("B", sBot, -dp, -1)):
            st = pl["stiffT"] if side == "T" else pl["stiffB"]
            S = R["sides"].get(side)
            if S and "error" not in S and S["stiff"] and st.get("on"):
                Ls = float(st["L"])
                sc.poly([(xs, -ext_y), P(py), add(P(py), mul(uu, Ls))], C_STIFF, C_PLATE_L, 1, (f"plate{k}",))

    # ---- bu lông xuyên hai bản ----
    for sd, rows in (("T", G["rowsT"]), ("B", G["rowsB"])):
        for r in rows:
            y = -r["s"]
            sc.poly([(-tp1 - 0.7 * db, y - 0.85 * db), (-tp1, y - 0.85 * db), (-tp1, y + 0.85 * db), (-tp1 - 0.7 * db, y + 0.85 * db)],
                    C_BOLT, C_BOLT, 1, ("bolts" + sd,))
            sc.poly([(tp2, y - 0.85 * db), (tp2 + 0.8 * db, y - 0.85 * db), (tp2 + 0.8 * db, y + 0.85 * db), (tp2, y + 0.85 * db)],
                    C_BOLT, C_BOLT, 1, ("bolts" + sd,))
            sc.poly([(-tp1, y - db / 2), (tp2, y - db / 2), (tp2, y + db / 2), (-tp1, y + db / 2)], "#6B7280", C_BOLT, 1, ("bolts" + sd,))

    # ---- nhãn ----
    for k in (1, 2):
        sc.text(add((x0[k], 0.0), add(mul(u[k], 0.6 * Lb), (0, 0.11 * dp))), f"DẦM {k}", color=C_STEEL_L, size=10, bold=True)
    sc.text((0, -sBot - 0.34 * dp), f"{G['bp']:.0f} × {sBot - sTop:.0f} × {tp1:g}/{tp2:g} — M{db:g} {R['bolt']['bg']['label']}"
            + (f" — Apex {G['alpha']:g}°" if G["type"] == "apex" else ""), size=9, bold=True)
    sc.bbox_pts += [(0, -sTop + 0.2 * dp), (0, -sBot - 0.45 * dp)]

    # ---- dòng lực ----
    if dem and flow:
        ln = max(0.30 * Lb, 120.0)
        for k in (1, 2):
            uu = u[k]
            for f, py, sg in (("T", 0.0, 1), ("B", -dp, -1)):
                Fn = dem["FnT"] if f == "T" else dem["FnB"]
                if abs(Fn) < 1e-6:
                    continue
                base = add((x0[k], py + sg * 0.09 * dp), mul(uu, 0.16 * Lb))
                if Fn > 0:
                    _arrow(sc, base, uu, ln, True, f"Kéo {abs(Fn):.1f} kN")
                else:
                    _arrow(sc, add(base, mul(uu, ln)), mul(uu, -1), ln, False, f"Nén {abs(Fn):.1f} kN")
    return sc


def plate_face(inp: dict, R: dict, dem: dict | None) -> Scene:
    """Mặt bản đầu. Hệ toạ độ: x ngang, y = −s (s dọc bản hướng xuống)."""
    sc = Scene()
    G = R["G"]; P = inp["plate"]; m1 = G["b1"]
    bp, g = G["bp"], P["g"]
    Y = lambda s: -s
    rect = lambda x0, s0, w, h: [(x0, Y(s0)), (x0 + w, Y(s0)), (x0 + w, Y(s0 + h)), (x0, Y(s0 + h))]
    sc.poly(rect(-bp / 2, G["sTop"], bp, G["sBot"] - G["sTop"]), C_PLATE, C_PLATE_L, 1, ("plate1", "plate2"))
    sc.poly(rect(-m1["bfE"] / 2, 0, m1["bfE"], G["tfT"]), C_STEEL, C_STEEL_L, 1, ("m1weldT", "m2weldT"))
    sc.poly(rect(-m1["bfI"] / 2, G["dp"] - G["tfB"], m1["bfI"], G["tfB"]), C_STEEL, C_STEEL_L, 1, ("m1weldB", "m2weldB"))
    sc.poly(rect(-m1["tw"] / 2, G["tfT"], m1["tw"], G["dp"] - G["tfT"] - G["tfB"]), C_STEEL, C_STEEL_L, 1, ("m1webweld", "m2webweld"))
    for side, sy0, sy1 in (("T", G["sTop"], 0.0), ("B", G["dp"], G["sBot"])):
        st = P["stiffT"] if side == "T" else P["stiffB"]
        ext = P["extT"] if side == "T" else P["extB"]
        if ext and st.get("on"):
            sc.poly(rect(-st["ts"] / 2, sy0, st["ts"], sy1 - sy0), C_STIFF, C_PLATE_L, 1, ("plate1", "plate2"))
    side = dem["side"] if dem else None
    S = R["sides"].get(side) if side else None
    if S and "error" not in S:
        sg = 1 if side == "T" else -1
        fIn = G["tfT"] if side == "T" else G["dp"] - G["tfB"]
        fOut = 0.0 if side == "T" else G["dp"]
        last = S["inner"][-1]
        sYs = S["plates"][0]["Yr"]["s"]
        sYL = last["s"] + sg * sYs
        yl = dict(color=D.C_TEN, width=2, dash=(7, 4), tags=("plate1", "plate2", "yield"), anim=True, bbox=False)
        sc.line([(-bp / 2, Y(fIn)), (bp / 2, Y(fIn))], **yl)
        sc.line([(-bp / 2, Y(sYL)), (bp / 2, Y(sYL))], **yl)
        for x in (-g / 2, g / 2):
            sc.line([(x, Y(fIn)), (x, Y(sYL))], **yl)
        sm = last["s"] + sg * sYs * 0.55
        sc.line([(-g / 2, Y(sYL)), (-bp / 2, Y(sm))], **yl); sc.line([(g / 2, Y(sYL)), (bp / 2, Y(sm))], **yl)
        if S["ext"]:
            sc.line([(-bp / 2, Y(fOut)), (bp / 2, Y(fOut))], **yl)
            so = S["outer"]["s"] - sg * P["Lev"] * 0.2
            sc.line([(-g / 2, Y(fOut)), (-bp / 2, Y(so))], **yl); sc.line([(g / 2, Y(fOut)), (bp / 2, Y(so))], **yl)
        sc.text((bp / 2 + 10, Y(sYL)), "đường chảy (minh hoạ)", color=D.C_TEN, size=8, anchor="w")
    dh = R["bolt"]["dh"]; db = inp["bolt"]["d"]
    for sd, rows in (("T", G["rowsT"]), ("B", G["rowsB"])):
        for r in rows:
            for x in (-g / 2, g / 2):
                sc.circle((x, Y(r["s"])), dh / 2, "#FFFFFF", C_BOLT, ("bolts" + sd,))
                sc.circle((x, Y(r["s"])), db / 2 * 0.8, C_BOLT, C_BOLT, ("bolts" + sd,))

    def dim_h(x0, x1, s, txt):
        sc.line([(x0, Y(s)), (x1, Y(s))], C_DIM, 1)
        sc.text(((x0 + x1) / 2, Y(s) + 10), txt, color=C_DIM, size=8)

    def dim_v(s0, s1, x, txt):
        sc.line([(x, Y(s0)), (x, Y(s1))], C_DIM, 1)
        for s in (s0, s1): sc.line([(x - 5, Y(s)), (x + 5, Y(s))], C_DIM, 1)
        sc.text((x + 6, Y((s0 + s1) / 2)), txt, color=C_DIM, size=8, anchor="w")

    dim_h(-bp / 2, bp / 2, G["sTop"] - 45, f"bp = {bp:.0f}")
    dim_h(-g / 2, g / 2, G["sTop"] - 22, f"g = {g:g}")
    ticks = sorted(set([G["sTop"], 0.0, G["tfT"], G["dp"] - G["tfB"], G["dp"], G["sBot"]] + [r["s"] for r in G["rowsT"] + G["rowsB"]]))
    for s0, s1 in zip(ticks, ticks[1:]):
        if s1 - s0 > 0.5: dim_v(s0, s1, bp / 2 + 20, f"{s1 - s0:.0f}")
    dim_v(G["sTop"], G["sBot"], -bp / 2 - 30, f"L = {G['sBot'] - G['sTop']:.0f}")
    sc.text((0, Y(G["sBot"] + 40)), f"MẶT BẢN ĐẦU {bp:.0f}×{P['tp1']:g}/{P['tp2']:g}×{G['sBot'] - G['sTop']:.0f} — {R['bolt']['bg']['label']} M{db}", size=9, bold=True)
    sc.bbox_pts += [(-bp / 2 - 110, Y(G["sTop"] - 60)), (bp / 2 + 170, Y(G["sBot"] + 60))]
    return sc
