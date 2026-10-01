"""
drawing.py — Vẽ knee lên tk.Canvas (mặt đứng + mặt bản đầu), theo hình minh hoạ:
cấu kiện màu xanh, panel / bản / sườn màu vàng, sườn chéo trong panel, bu lông, đường hàn,
mũi tên nội lực có hiệu ứng chạy nét, tô sáng bộ phận của kiểm tra đang chọn.
"""

from __future__ import annotations

import math
import tkinter as tk

# Bảng màu (theo hình minh hoạ RAM Connection)
C_STEEL = "#6FA8DC"; C_STEEL_L = "#2F5F8F"; C_WEB = "#A9CBEA"
C_PANEL = "#F6D58E"; C_PANEL_L = "#B7862B"; C_PLATE = "#F2B84B"; C_PLATE_L = "#9A6A18"
C_STIFF = "#F4C15D"; C_BOLT = "#2B2F36"; C_WELD = "#E8590C"
C_TEN = "#D23B3B"; C_COMP = "#1F6FEB"; C_DIM = "#5B6777"; C_HL = "#FF2D95"; C_TXT = "#18212F"


def V(x, y): return (x, y)
def add(a, b): return (a[0] + b[0], a[1] + b[1])
def sub(a, b): return (a[0] - b[0], a[1] - b[1])
def mul(a, k): return (a[0] * k, a[1] * k)
def ang(deg): return (math.cos(math.radians(deg)), math.sin(math.radians(deg)))
def perp(a): return (-a[1], a[0])
def nrm(a):
    L = math.hypot(*a) or 1.0
    return (a[0] / L, a[1] / L)
def inter(p, d, q, e):
    den = d[0] * e[1] - d[1] * e[0]
    if abs(den) < 1e-12: return p
    t = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / den
    return (p[0] + d[0] * t, p[1] + d[1] * t)


class Scene:
    def __init__(self):
        self.items = []
        self.bbox_pts = []

    def poly(self, pts, fill, outline, width=1, tags=(), bbox=True, z=None):
        """z: danh sách khoảng bề dày ngoài mặt phẳng [(z0, z1), …] (mm) cho hình 3D; None = không dựng 3D."""
        self.items.append(dict(k="poly", pts=list(pts), fill=fill, outline=outline, width=width, tags=tags, z=z))
        if bbox: self.bbox_pts += list(pts)

    def line(self, pts, color, width=1, dash=None, arrow=None, tags=(), anim=False, bbox=True):
        self.items.append(dict(k="line", pts=list(pts), color=color, width=width, dash=dash, arrow=arrow, tags=tags, anim=anim))
        if bbox: self.bbox_pts += list(pts)

    def text(self, p, s, color=C_TXT, size=9, bold=False, anchor="center", angle=0, tags=()):
        self.items.append(dict(k="text", p=p, s=s, color=color, size=size, bold=bold, anchor=anchor, angle=angle, tags=tags))

    def circle(self, c, r, fill, outline, tags=()):
        self.items.append(dict(k="circle", c=c, r=r, fill=fill, outline=outline, tags=tags))
        self.bbox_pts += [(c[0] - r, c[1] - r), (c[0] + r, c[1] + r)]


# ═══════════════════════════ MẶT ĐỨNG ═══════════════════════════
def elevation(inp: dict, R: dict, dem: dict | None, flow: bool = True) -> Scene:
    sc = Scene()
    G = R["G"]; T = G["type"]; tp = inp["plate"]["tp"]; sup = inp["sup"]
    M1, M2 = G["M1"], G["M2"]
    n = ang(G["thN"])
    t = (-n[1], n[0]) if T == "ngang" else (n[1], -n[0])
    C = lambda s: mul(t, s)
    a = G["a"]
    Ld = max(G["dp"], M2["d"]) * 2.0
    face = mul(n, tp)
    ts = M2["tfI"] if sup["useFlange"] else sup["t"]
    tf2 = M2["tfI"]; tfo2 = M2["tfE"]
    sEnd = G["sTop"] - float(sup.get("topOffset") or 0)
    fcE, fcI = G["tfe"] / 2, G["dp"] - G["tfi"] / 2
    stE_on, stI_on = sup["stE"].get("on"), sup["stI"].get("on")
    PZ = G["PZ"]
    Z = lambda w: [(-w / 2, w / 2)]
    zc_w, zp_w = Z(M2["tw"]), Z(PZ["tw"])
    zc_fo, zc_fi = Z(M2["bfE"]), Z(M2["bfI"])
    zm_w, zm_fE, zm_fI = Z(M1["tw"]), Z(M1["bfE"]), Z(M1["bfI"])
    z_pl = Z(G["bp"])
    z_sp = Z(PZ["bfI"] if sup["useFlange"] else sup["b"])
    def z_st(b): return [(PZ["tw"] / 2, PZ["tw"] / 2 + b), (-PZ["tw"] / 2 - b, -PZ["tw"] / 2)]
    pz_fo, pz_fi = PZ["tfE"], PZ["tfI"]
    flow_pts = {}

    if T == "ngang":
        uE = ang(-90 + (G["c_out_tilt"] if inp["col"].get("innerStraight") else 0))
        uI = ang(-90 - G["c_in_tilt"])
    else:
        uE, uI = ang(a), ang(G["b_in"])

    # ---------------- cấu kiện gối (M2) ----------------
    if T in ("dung", "xien"):
        dc = M2["d"]
        back = mul(n, -ts) if T == "xien" else (0.0, 0.0)          # mặt sau bản gối (knee xiên)
        top = add(C(G["sTop"] if T == "xien" else sEnd), back)
        x_in = add(C(G["sBot"]), back)[0] if T == "xien" else 0.0
        x_out = x_in - dc
        cap_dir = (-math.cos(math.radians(a)), -math.sin(math.radians(a)))
        top_out = inter(top, cap_dir, (x_out, 0.0), (0.0, 1.0))
        y_bot = C(G["sBot"])[1] - 1.4 * G["dp"]
        # đường sườn tại cao độ cánh kèo (theo phương cánh kèo)
        def st_line(s, u):
            P = add(add(C(s), back), (-tf2 if T == "dung" else 0.0, 0.0))
            E2 = inter(P, u, (x_out + tfo2, 0.0), (0.0, 1.0))
            return P, E2
        P1, E1 = st_line(fcE, uE)
        P2, E2 = st_line(fcI, uI)
        if T == "dung":
            inner_top = top
            web = [top, (x_in, y_bot), (x_out, y_bot), top_out]
        else:
            inner_top = (x_in, add(C(G["sBot"]), back)[1])
            web = [top, add(C(G["sBot"]), back), (x_in, y_bot), (x_out, y_bot), top_out]
        sc.poly(web, C_WEB, C_STEEL_L, 1, ("supEweb", "supIweb"), z=zc_w)
        # panel (vàng)
        pnl_top = [top, top_out] if not stE_on else [P1, E1]
        pnl = [pnl_top[0], add(C(G["sBot"]), back) if T == "xien" else P2, P2, E2, pnl_top[1]] if T == "xien" else [pnl_top[0], P2, E2, pnl_top[1]]
        if T == "xien":
            pnl = [top, add(C(fcI), back), E2, top_out]
        sc.poly(pnl, C_PANEL, C_PANEL_L, 1, ("panel",), z=zp_w)
        # CỘT (tiết diện SAP) bên dưới — PANEL ZONE (bề dày riêng) phía trên, tách tại cao độ sườn cánh trong
        y_po, y_pi = E2[1], P2[1]
        sc.poly([(x_out, y_bot), (x_out + tfo2, y_bot), (x_out + tfo2, y_po), (x_out, y_po)], C_STEEL, C_STEEL_L, 1, z=zc_fo)
        sc.poly([(x_out, y_po), (x_out + pz_fo, y_po), (x_out + pz_fo, top_out[1] - pz_fo), (x_out, top_out[1])], C_PANEL, C_PANEL_L, 1, ("panel",), z=zc_fo)
        if T == "dung":
            sc.poly([(x_in - tf2, y_bot), (x_in, y_bot), (x_in, y_pi), (x_in - tf2, y_pi)], C_STEEL, C_STEEL_L, 1, z=zc_fi)
            sc.poly([(x_in - pz_fi, y_pi), (x_in, y_pi), inner_top, (x_in - pz_fi, inner_top[1])], C_PANEL, C_PANEL_L, 1, ("supportE", "supportI"), z=z_sp)
        else:
            sc.poly([(x_in - tf2, y_bot), (x_in, y_bot), inner_top, (x_in - tf2, inner_top[1])], C_STEEL, C_STEEL_L, 1, z=zc_fi)
            sc.poly([C(G["sTop"]), C(G["sBot"]), add(C(G["sBot"]), back), add(C(G["sTop"]), back)], C_PLATE, C_PLATE_L, 1, ("supportE", "supportI"), z=z_sp)
        sc.line([(x_out, y_po), P2], C_PANEL_L, 1, dash=(4, 3), bbox=False)
        sc.text(((x_out + x_in) / 2, (top_out[1] + y_po) / 2 + G["dp"] * 0.05), "PANEL ZONE", color=C_PANEL_L, size=9, bold=True)
        # bản nắp theo dốc kèo
        tcap = max(float(sup.get("tcap") or 0), 8.0)
        nc = nrm(perp(cap_dir))
        nc = nc if nc[1] < 0 else (-nc[0], -nc[1])
        sc.poly([top, top_out, add(top_out, mul(nc, tcap)), add(top, mul(nc, tcap))], C_PANEL, C_PANEL_L, 1, ("supportE",), z=Z(PZ["bfE"]))
        # sườn + sườn chéo
        for on, P, Ex, tag, stp in ((stE_on, P1, E1, "supEstiff", sup["stE"]), (stI_on, P2, E2, "supIstiff", sup["stI"])):
            if on:
                w = stp["ts"]; nn = nrm(perp(sub(Ex, P)))
                sc.poly([add(P, mul(nn, w / 2)), add(Ex, mul(nn, w / 2)), add(Ex, mul(nn, -w / 2)), add(P, mul(nn, -w / 2))], C_STIFF, C_PANEL_L, 1, (tag,), z=z_st(stp["bs"]))
        if sup.get("diag", {}).get("on"):
            A0 = E1 if stE_on else top_out
            dvec = nrm(sub(P2, A0)); nn = perp(dvec); w = sup["diag"]["t"]
            sc.poly([add(A0, mul(nn, w / 2)), add(P2, mul(nn, w / 2)), add(P2, mul(nn, -w / 2)), add(A0, mul(nn, -w / 2))], C_STIFF, C_PANEL_L, 1, ("panel",), z=z_st(sup["diag"]["b"]))
        flow_pts = dict(T1=P1, T2=E1, C1=P2, C2=E2, out_bot=(x_out + tfo2 / 2, y_bot), in_bot=(x_in - tf2 / 2, y_bot), in_x=x_in - tf2 / 2)
        sc.text(((x_out + x_in) / 2, y_bot + G["dp"] * 0.45), "CỘT " + M2["sec"], size=9, bold=True, angle=90)
    else:
        # knee ngang: kèo nằm trên, đáy vai kèo nằm ngang
        xL = C(sEnd)[0] - 10
        H = M2["d"]
        xE, xI = C(fcE)[0], C(fcI)[0]
        xH = C(G["sBot"])[0] + 0.25 * G["dp"]
        Lr = Ld * 1.3
        ta = math.tan(math.radians(a))
        far_b = add((xH, ts), mul(ang(a), Lr))
        top_y = lambda x: H + (x - xL) * ta
        far_t = (far_b[0], top_y(far_b[0]))
        sc.poly([(xL, 0), (xH, 0), far_b, far_t, (xL, H)], C_WEB, C_STEEL_L, 1, ("supEweb", "supIweb"), z=zc_w)
        sc.poly([(xE, ts), (xI, ts), (xI, top_y(xI) - tfo2), (xE, top_y(xE) - tfo2)], C_PANEL, C_PANEL_L, 1, ("panel",), z=zp_w)
        sc.text(((xE + xI) / 2, (ts + top_y((xE + xI) / 2)) / 2), "PANEL ZONE", color=C_PANEL_L, size=9, bold=True)
        sc.poly([(xL, 0), (xH, 0), (xH, ts), (xL, ts)], C_PLATE if not sup["useFlange"] else C_STEEL, C_STEEL_L, 1, ("supportE", "supportI"), z=z_sp)
        sc.poly([(xH, 0), add((xH, 0), mul(ang(a), Lr)), far_b, (xH, ts)], C_STEEL, C_STEEL_L, 1, z=zc_fi)
        sc.poly([(xL, H), far_t, add(far_t, (0, -tfo2)), (xL, H - tfo2)], C_STEEL, C_STEEL_L, 1, z=zc_fo)
        sc.poly([(xL - 14, -5), (xL, -5), (xL, H + 5), (xL - 14, H + 5)], C_PANEL, C_PANEL_L, 1, z=Z(M2["bfE"]))
        for on, x, tag, stp in ((stE_on, xE, "supEstiff", sup["stE"]), (stI_on, xI, "supIstiff", sup["stI"])):
            if on:
                w = stp["ts"]
                sc.poly([(x - w / 2, ts), (x + w / 2, ts), (x + w / 2, top_y(x) - tfo2), (x - w / 2, top_y(x) - tfo2)], C_STIFF, C_PANEL_L, 1, (tag,), z=z_st(stp["bs"]))
        if sup.get("diag", {}).get("on"):
            A0, B0 = (xE, top_y(xE) - tfo2), (xI, ts); dvec = nrm(sub(B0, A0)); nn = perp(dvec); w = sup["diag"]["t"]
            sc.poly([add(A0, mul(nn, w / 2)), add(B0, mul(nn, w / 2)), add(B0, mul(nn, -w / 2)), add(A0, mul(nn, -w / 2))], C_STIFF, C_PANEL_L, 1, ("panel",), z=z_st(sup["diag"]["b"]))
        flow_pts = dict(T1=(xE, ts), T2=(xE, top_y(xE) - tfo2), C1=(xI, ts), C2=(xI, top_y(xI) - tfo2), rafter_far=far_t)
        sc.text((xL + (far_b[0] - xL) * 0.62, H * 0.55 + (far_b[0] - xL) * 0.62 * ta * 0.5), "KÈO " + M2["sec"], size=9, bold=True)

    # ---------------- cấu kiện có bản đầu (M1) ----------------
    A = add(C(0), face); B = add(C(G["dp"]), face)
    Ai = add(C(G["tfe"]), face); Bi = add(C(G["dp"] - G["tfi"]), face)
    A2 = add(A, mul(uE, Ld)); B2 = inter(B, uI, A2, perp(uE))
    Ai2 = add(Ai, mul(uE, Ld)); Bi2 = inter(Bi, uI, A2, perp(uE))
    sc.poly([A, A2, B2, B], C_WEB, C_STEEL_L, 1, ("m1web",), z=zm_w)
    sc.poly([A, A2, Ai2, Ai], C_STEEL, C_STEEL_L, 1, z=zm_fE)
    sc.poly([B, B2, Bi2, Bi], C_STEEL, C_STEEL_L, 1, z=zm_fI)
    mid0, mid1 = mul(add(A, B), 0.5), mul(add(A2, B2), 0.5)
    sc.line([mid0, mid1], C_DIM, 1, dash=(8, 3, 2, 3))
    lab = ("CỘT " if T == "ngang" else "KÈO ") + M1["sec"]
    sc.text(add(mul(add(mid0, mid1), 0.5), mul(nrm(perp(uE)), G["dp"] * 0.18)), lab, size=9, bold=True,
            angle=(-90 if T == "ngang" else a))
    # hàn
    sw = max(inp["weld"]["flE"].get("w", 8), 6) * 1.6
    def weld(p, alongP, alongM, tag):
        sc.poly([p, add(p, mul(alongP, sw)), add(p, mul(alongM, sw * 1.3))], C_WELD, C_WELD, 1, (tag,), bbox=False,
                z=zm_fE if tag.endswith("E") else zm_fI)
    weld(A, mul(t, -1), uE, "m1weldE"); weld(Ai, t, uE, "m1weldE")
    weld(B, t, uI, "m1weldI"); weld(Bi, mul(t, -1), uI, "m1weldI")
    sc.line([add(Ai, mul(t, 6)), add(Bi, mul(t, -6))], C_WELD, 3, tags=("m1webweld",))
    # bản đầu
    sc.poly([C(G["sTop"]), C(G["sBot"]), add(C(G["sBot"]), face), add(C(G["sTop"]), face)], C_PLATE, C_PLATE_L, 1, ("plate",), z=z_pl)
    for sd in ("E", "I"):
        st = inp["plate"]["stiffE" if sd == "E" else "stiffI"]; ext = inp["plate"]["extE" if sd == "E" else "extI"]
        if st.get("on") and ext:
            s0 = G["sTop"] if sd == "E" else G["sBot"]; s1 = 0.0 if sd == "E" else G["dp"]; u = uE if sd == "E" else uI
            sc.poly([add(C(s0), face), add(C(s1), face), add(add(C(s1), face), mul(u, st["L"]))], C_STIFF, C_PANEL_L, 1, ("plate",), z=Z(st["ts"]))
    # bu lông
    db = inp["bolt"]["d"]
    for sd, rows in (("E", G["rowsE"]), ("I", G["rowsI"])):
        for r in rows:
            c0 = C(r["s"])
            a1, a2 = add(c0, mul(n, -ts - 8)), add(c0, mul(n, tp + 10))
            w = mul(t, db / 2); hw = mul(t, db * 0.85)
            tg = ("bolts" + sd,)
            g2 = inp["plate"]["g"] / 2
            zb = [(g2 - db / 2, g2 + db / 2), (-g2 - db / 2, -g2 + db / 2)]
            zh = [(g2 - db * 0.85, g2 + db * 0.85), (-g2 - db * 0.85, -g2 + db * 0.85)]
            sc.poly([add(a1, w), add(a2, w), sub(a2, w), sub(a1, w)], C_BOLT, C_BOLT, 1, tg, z=zb)
            sc.poly([add(a2, hw), add(add(a2, hw), mul(n, db * 0.6)), sub(add(a2, mul(n, db * 0.6)), hw), sub(a2, hw)], C_BOLT, C_BOLT, 1, tg, z=zh)
            sc.poly([add(a1, hw), add(add(a1, hw), mul(n, -db * 0.6)), sub(add(a1, mul(n, -db * 0.6)), hw), sub(a1, hw)], C_BOLT, C_BOLT, 1, tg, z=zh)
    # kích thước dọc bản
    off = mul(n, tp + 60)
    ticks = sorted(set([G["sTop"], 0.0, G["dp"], G["sBot"]] + [r["s"] for r in G["rowsE"] + G["rowsI"]]))
    for s0, s1 in zip(ticks, ticks[1:]):
        if s1 - s0 < 0.5: continue
        p, q = add(C(s0), off), add(C(s1), off)
        sc.line([p, q], C_DIM, 1, bbox=False)
        for e in (p, q):
            sc.line([add(e, mul(n, -6)), add(e, mul(n, 6))], C_DIM, 1, bbox=False)
        sc.text(add(mul(add(p, q), 0.5), mul(n, 14)), f"{s1 - s0:.0f}", color=C_DIM, size=8)
    sc.bbox_pts += [add(C(G["sTop"]), mul(n, tp + 90)), add(C(G["sBot"]), mul(n, tp + 90))]

    # ---------------- dòng lực (cánh kèo → bản → panel → cột) ----------------
    if dem and flow and dem.get("side") and flow_pts:
        tE = dem["side"] == "E"
        fl = dict(width=2, dash=(3, 7), tags=("flow",), anim=True, bbox=False)
        pT = (A2, A) if tE else (B2, B)
        pC = (B2, B) if tE else (A2, A)
        sc.line([add(mul(pT[0], 0.4), mul(pT[1], 0.6)), pT[1]], C_TEN, **fl)
        sc.line([add(mul(pC[0], 0.4), mul(pC[1], 0.6)), pC[1]], C_COMP, **fl)
        fp = flow_pts
        (t1, t2) = (fp["T1"], fp["T2"]) if tE else (fp["C1"], fp["C2"])
        (c1, c2) = (fp["C1"], fp["C2"]) if tE else (fp["T1"], fp["T2"])
        if T in ("dung", "xien"):
            sc.line([t1, t2, fp["out_bot"]], C_TEN, **fl)
            sc.line([c1, (fp["in_x"], c1[1]), fp["in_bot"]], C_COMP, **fl)
        else:
            sc.line([t1, t2], C_TEN, **fl)
            sc.line([c1, c2], C_COMP, **fl)
        sc.line([t2, c1], "#8E44AD", **dict(fl, width=3))

    # ---------------- nội lực ----------------
    if dem:
        ax = nrm(sub(mid1, mid0))
        L0 = G["dp"] * 0.55
        pN = add(mid1, mul(ax, G["dp"] * 0.25))
        _force(sc, pN, ax, dem["N"], f"N = {dem['N']:.1f} kN", L0)
        pV = add(mid1, mul(ax, G["dp"] * 0.25 + L0 * 1.25))
        _force(sc, pV, perp(ax), dem["V"], f"V = {dem['V']:.1f} kN", L0 * 0.8)
        _moment(sc, mid1, G["dp"] * 0.42, dem["M"])
        mx = max(abs(dem["FnE"]), abs(dem["FnI"]), 1e-9)
        for F, p0, u, sg in ((dem["FnE"], mul(add(A, Ai), 0.5), uE, 1), (dem["FnI"], mul(add(B, Bi), 0.5), uI, -1)):
            if abs(F) < 1e-6: continue
            ln = min(abs(F) / mx, 1) * Ld * 0.22 + Ld * 0.05
            p = add(add(p0, mul(u, Ld * 0.08)), mul(nrm(perp(u)), sg * G["dp"] * 0.07))
            start = p if F > 0 else add(p, mul(u, ln))
            d = u if F > 0 else mul(u, -1)
            _arrow(sc, start, d, ln, F > 0, ("Kéo " if F > 0 else "Nén ") + f"{abs(F):.1f} kN")
    return sc


def _arrow(sc, start, d, ln, tension, label):
    end = add(start, mul(d, ln))
    col = C_TEN if tension else C_COMP
    sc.line([start, end], col, 3, dash=(10, 6), arrow="last", tags=("force",), anim=True, bbox=True)
    sc.text(add(mul(add(start, end), 0.5), mul(perp(d), 18)), label, color=col, size=8, bold=True)


def _force(sc, p, d, val, label, ln):
    if abs(val) < 1e-6: return
    if val > 0: _arrow(sc, p, d, ln, True, label)
    else: _arrow(sc, add(p, mul(d, ln)), mul(d, -1), ln, False, label)


def _moment(sc, c, r, M):
    if abs(M) < 1e-6: return
    col = C_TEN if M < 0 else C_COMP
    a0, a1 = (200, -20) if M < 0 else (-20, 200)
    pts = []
    steps = 28
    for i in range(steps + 1):
        th = math.radians(a0 + (a1 - a0) * i / steps + (0 if M < 0 else 0))
        pts.append((c[0] + r * math.cos(th), c[1] + r * math.sin(th)))
    if M < 0:  # đi qua phía trên (chiều kim đồng hồ)
        pts = [(c[0] + r * math.cos(math.radians(200 - 220 * i / steps)), c[1] + r * math.sin(math.radians(200 - 220 * i / steps))) for i in range(steps + 1)]
    else:
        pts = [(c[0] + r * math.cos(math.radians(-20 + 220 * i / steps)), c[1] + r * math.sin(math.radians(-20 + 220 * i / steps))) for i in range(steps + 1)]
    sc.line(pts, col, 3, dash=(10, 6), arrow="last", tags=("force",), anim=True)
    sc.text((c[0], c[1] + r + 26), f"M = {M:.1f} kN·m", color=col, size=9, bold=True)


# ═══════════════════════════ MẶT BẢN ĐẦU ═══════════════════════════
def plate_face(inp: dict, R: dict, dem: dict | None) -> Scene:
    """Hệ toạ độ: x ngang, y = −s (s dọc bản hướng xuống)."""
    sc = Scene()
    G = R["G"]; P = inp["plate"]; M1 = G["M1"]
    bp, g = G["bp"], P["g"]
    Y = lambda s: -s
    rect = lambda x0, s0, w, h: [(x0, Y(s0)), (x0 + w, Y(s0)), (x0 + w, Y(s0 + h)), (x0, Y(s0 + h))]
    sc.poly(rect(-bp / 2, G["sTop"], bp, G["sBot"] - G["sTop"]), C_PLATE, C_PLATE_L, 1, ("plate",))
    sc.poly(rect(-M1["bfE"] / 2, 0, M1["bfE"], G["tfe"]), C_STEEL, C_STEEL_L, 1, ("m1weldE",))
    sc.poly(rect(-M1["bfI"] / 2, G["dp"] - G["tfi"], M1["bfI"], G["tfi"]), C_STEEL, C_STEEL_L, 1, ("m1weldI",))
    sc.poly(rect(-M1["tw"] / 2, G["tfe"], M1["tw"], G["dp"] - G["tfe"] - G["tfi"]), C_STEEL, C_STEEL_L, 1, ("m1webweld",))
    if P["extE"] and P["stiffE"].get("on"):
        sc.poly(rect(-P["stiffE"]["ts"] / 2, G["sTop"], P["stiffE"]["ts"], -G["sTop"]), C_STIFF, C_PANEL_L, 1, ("plate",))
    if P["extI"] and P["stiffI"].get("on"):
        sc.poly(rect(-P["stiffI"]["ts"] / 2, G["dp"], P["stiffI"]["ts"], G["sBot"] - G["dp"]), C_STIFF, C_PANEL_L, 1, ("plate",))
    side = dem["side"] if dem else None
    S = R["sides"].get(side) if side else None
    if S and "error" not in S:
        sg = 1 if side == "E" else -1
        fIn = G["tfe"] if side == "E" else G["dp"] - G["tfi"]
        fOut = 0.0 if side == "E" else G["dp"]
        last = S["inner"][-1]
        sYL = last["s"] + sg * S["Yr"]["s"]
        yl = dict(color=C_TEN, width=2, dash=(7, 4), tags=("plate", "yield"), anim=True, bbox=False)
        sc.line([(-bp / 2, Y(fIn)), (bp / 2, Y(fIn))], **yl)
        sc.line([(-bp / 2, Y(sYL)), (bp / 2, Y(sYL))], **yl)
        for x in (-g / 2, g / 2):
            sc.line([(x, Y(fIn)), (x, Y(sYL))], **yl)
        sm = last["s"] + sg * S["Yr"]["s"] * 0.55
        sc.line([(-g / 2, Y(sYL)), (-bp / 2, Y(sm))], **yl); sc.line([(g / 2, Y(sYL)), (bp / 2, Y(sm))], **yl)
        if S["ext"]:
            sc.line([(-bp / 2, Y(fOut)), (bp / 2, Y(fOut))], **yl)
            so = S["outer"]["s"] - sg * P["Lev"] * 0.2
            sc.line([(-g / 2, Y(fOut)), (-bp / 2, Y(so))], **yl); sc.line([(g / 2, Y(fOut)), (bp / 2, Y(so))], **yl)
        sc.text((bp / 2 + 10, Y(sYL)), "đường chảy (minh hoạ)", color=C_TEN, size=8, anchor="w")
    dh = R["bolt"]["dh"]; db = inp["bolt"]["d"]
    for sd, rows in (("E", G["rowsE"]), ("I", G["rowsI"])):
        for r in rows:
            for x in (-g / 2, g / 2):
                sc.circle((x, Y(r["s"])), dh / 2, "#FFFFFF", C_BOLT, ("bolts" + sd,))
                sc.circle((x, Y(r["s"])), db / 2 * 0.8, C_BOLT, C_BOLT, ("bolts" + sd,))
    # kích thước
    def dim_h(x0, x1, s, txt):
        sc.line([(x0, Y(s)), (x1, Y(s))], C_DIM, 1)
        sc.text(((x0 + x1) / 2, Y(s) + 10), txt, color=C_DIM, size=8)
    def dim_v(s0, s1, x, txt):
        sc.line([(x, Y(s0)), (x, Y(s1))], C_DIM, 1)
        for s in (s0, s1): sc.line([(x - 5, Y(s)), (x + 5, Y(s))], C_DIM, 1)
        sc.text((x + 6, Y((s0 + s1) / 2)), txt, color=C_DIM, size=8, anchor="w")
    dim_h(-bp / 2, bp / 2, G["sTop"] - 45, f"bp = {bp:.0f}")
    dim_h(-g / 2, g / 2, G["sTop"] - 22, f"g = {g:g}")
    ticks = sorted(set([G["sTop"], 0.0, G["tfe"], G["dp"] - G["tfi"], G["dp"], G["sBot"]] + [r["s"] for r in G["rowsE"] + G["rowsI"]]))
    for s0, s1 in zip(ticks, ticks[1:]):
        if s1 - s0 > 0.5: dim_v(s0, s1, bp / 2 + 20, f"{s1 - s0:.0f}")
    dim_v(G["sTop"], G["sBot"], -bp / 2 - 30, f"L = {G['sBot'] - G['sTop']:.0f}")
    sc.text((0, Y(G["sBot"] + 40)), f"MẶT BẢN ĐẦU {bp:.0f}×{P['tp']:g}×{G['sBot'] - G['sTop']:.0f} — {R['bolt']['bg']['label']} M{db}", size=9, bold=True)
    sc.bbox_pts += [(-bp / 2 - 110, Y(G["sTop"] - 60)), (bp / 2 + 170, Y(G["sBot"] + 60))]
    return sc


# ═══════════════════════════ RENDER ═══════════════════════════
def heat_color(r: float) -> str:
    """Thang màu D/C: ≤0.6 xanh lá → 0.9 vàng → 1.0 cam → >1 đỏ."""
    stops = [(0.0, (46, 204, 113)), (0.6, (46, 204, 113)), (0.9, (241, 196, 15)), (1.0, (243, 156, 18)), (1.0001, (231, 76, 60)), (9e9, (192, 57, 43))]
    r = max(0.0, r if r == r else 0.0)
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if r <= b:
            t = 0 if b - a < 1e-9 else (r - a) / (b - a)
            c = tuple(int(ca[i] + (cb[i] - ca[i]) * min(max(t, 0), 1)) for i in range(3))
            return "#%02X%02X%02X" % c
    return "#C0392B"


def shade(hex_color: str, k: float) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    f = lambda v: max(0, min(255, int(v * k)))
    return "#%02X%02X%02X" % (f(r), f(g), f(b))


def item_ratio(it, heat):
    rs = [heat[t] for t in it.get("tags", ()) if t in heat]
    return max(rs) if rs else None


class _Tip:
    """Tooltip nhỏ cạnh con trỏ."""

    def __init__(self, master):
        self.master = master
        self.win = None

    def show(self, x, y, text):
        if not text:
            self.hide(); return
        if self.win is None:
            self.win = tk.Toplevel(self.master)
            self.win.wm_overrideredirect(True)
            self.win.attributes("-topmost", True)
            self.lbl = tk.Label(self.win, justify="left", background="#1F2933", foreground="#F5F7FA",
                                font=("Consolas", 9), padx=8, pady=5)
            self.lbl.pack()
        self.lbl.configure(text=text)
        self.win.geometry(f"+{x + 16}+{y + 14}")
        self.win.deiconify()

    def hide(self):
        if self.win is not None:
            self.win.withdraw()


class _BaseView(tk.Canvas):
    def __init__(self, master, **kw):
        super().__init__(master, background="#FFFFFF", highlightthickness=0, **kw)
        self._scene = None
        self._hl = set()
        self._heat = None
        self._offset = 0
        self._n = 0
        self._blink = False
        self.zoom = 1.0
        self.pan = [0.0, 0.0]
        self.tipfn = None
        self.on_pick = None
        self._tip = _Tip(self)
        self._drag = None
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Double-Button-1>", lambda e: self.reset_view())
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda e: self._tip.hide())
        self.after(70, self._tick)

    def show(self, scene, hl_tags=(), heat=None):
        self._scene = scene; self._hl = set(hl_tags or ()); self._heat = heat; self.redraw()

    def set_highlight(self, tags):
        self._hl = set(tags or ()); self.redraw()

    def reset_view(self):
        self.zoom = 1.0; self.pan = [0.0, 0.0]; self.redraw()

    def _wheel(self, e):
        f = 1.15 if e.delta > 0 else 1 / 1.15
        W, H = self.winfo_width(), self.winfo_height()
        cx, cy = e.x - W / 2 - self.pan[0], e.y - H / 2 - self.pan[1]
        self.pan[0] -= cx * (f - 1); self.pan[1] -= cy * (f - 1)
        self.zoom = min(max(self.zoom * f, 0.3), 12)
        self.redraw()

    def _motion(self, e):
        if not self.tipfn:
            return
        ids = self.find_overlapping(e.x - 2, e.y - 2, e.x + 2, e.y + 2)
        tags = set()
        for i in reversed(ids):
            ts = [t[2:] for t in self.gettags(i) if t.startswith("t_")]
            if ts:
                tags.update(ts); break
        txt = self.tipfn(tags) if tags else ""
        if txt:
            self._tip.show(e.x_root, e.y_root, txt)
        else:
            self._tip.hide()

    def _tick(self):
        self._offset = (self._offset - 2) % 64
        self._n += 1
        try:
            for i in self.find_withtag("anim"):
                self.itemconfigure(i, dashoffset=self._offset)
            if self._n % 7 == 0:
                self._blink = not self._blink
                for i in self.find_withtag("hl"):
                    self.itemconfigure(i, width=4 if self._blink else 2)
        except tk.TclError:
            return
        self.after(70, self._tick)

    def _bubbles(self, boxes):
        """Nhãn D/C nổi trên từng bộ phận (chế độ tô màu)."""
        placed = []
        for tag, (x0, y0, x1, y1, r) in sorted(boxes.items(), key=lambda kv: -kv[1][4]):
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            for _ in range(8):
                if all(abs(cx - px) > 46 or abs(cy - py) > 20 for px, py in placed): break
                cy += 20
            placed.append((cx, cy))
            col = heat_color(r)
            txt = "∞" if r == float("inf") else f"{r:.2f}"
            self.create_rectangle(cx - 21, cy - 9, cx + 21, cy + 9, fill=col, outline="#FFFFFF", width=2, tags=("bubble", "t_" + tag))
            self.create_text(cx, cy, text=txt, fill="#FFFFFF", font=("Segoe UI", 9, "bold"), tags=("bubble", "t_" + tag))


class KneeCanvas(_BaseView):
    """Hình 2D: kéo chuột trái để di chuyển, lăn chuột để zoom, nhấp đúp để về mặc định."""

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag_move)

    def _press(self, e):
        self._drag = (e.x, e.y, self.pan[0], self.pan[1])

    def _drag_move(self, e):
        if self._drag:
            x0, y0, px, py = self._drag
            self.pan = [px + e.x - x0, py + e.y - y0]; self.redraw()

    def redraw(self):
        self.delete("all")
        sc = self._scene
        if not sc or not sc.bbox_pts:
            return
        W, H = max(self.winfo_width(), 50), max(self.winfo_height(), 50)
        xs = [p[0] for p in sc.bbox_pts]; ys = [p[1] for p in sc.bbox_pts]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        pad = 30
        k = min((W - 2 * pad) / max(x1 - x0, 1), (H - 2 * pad) / max(y1 - y0, 1)) * self.zoom
        cxw, cyw = (x0 + x1) / 2, (y0 + y1) / 2
        ox, oy = W / 2 + self.pan[0], H / 2 + self.pan[1]
        M = lambda p: (ox + k * (p[0] - cxw), oy - k * (p[1] - cyw))
        hl, heat = self._hl, self._heat
        boxes = {}
        for it in sc.items:
            tags = tuple("t_" + t for t in it.get("tags", ()))
            on = bool(hl & set(it.get("tags", ())))
            if it["k"] == "poly":
                pts = [c for p in it["pts"] for c in M(p)]
                fill = it["fill"]
                if heat is not None:
                    r = item_ratio(it, heat)
                    fill = heat_color(r) if r is not None else "#E6EAEF"
                    if r is not None:
                        for t in it.get("tags", ()):
                            if t in heat:
                                xs_, ys_ = pts[0::2], pts[1::2]
                                b = boxes.get(t)
                                bb = (min(xs_), min(ys_), max(xs_), max(ys_))
                                boxes[t] = (min(bb[0], b[0]), min(bb[1], b[1]), max(bb[2], b[2]), max(bb[3], b[3]), heat[t]) if b else bb + (heat[t],)
                self.create_polygon(*pts, fill=fill, outline=C_HL if on else it["outline"],
                                    width=3 if on else it["width"], tags=tags + (("hl",) if on else ()))
            elif it["k"] == "line":
                pts = [c for p in it["pts"] for c in M(p)]
                kw = dict(fill=C_HL if on and "force" not in it["tags"] else it["color"], width=it["width"] + (2 if on else 0),
                          tags=tags + (("anim",) if it.get("anim") else ()))
                if it.get("dash"): kw["dash"] = it["dash"]
                if it.get("arrow"): kw.update(arrow=it["arrow"], arrowshape=(12, 14, 5))
                self.create_line(*pts, **kw)
            elif it["k"] == "circle":
                cx, cy = M(it["c"]); r = it["r"] * k
                fill = it["fill"]
                if heat is not None and it["fill"] != "#FFFFFF":
                    rr = item_ratio(it, heat); fill = heat_color(rr) if rr is not None else fill
                self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=fill, outline=C_HL if on else it["outline"],
                                 width=3 if on else 1, tags=tags + (("hl",) if on else ()))
            elif it["k"] == "text":
                x, y = M(it["p"])
                self.create_text(x, y, text=it["s"], fill=it["color"], anchor=it["anchor"], angle=it["angle"],
                                 font=("Segoe UI", it["size"], "bold" if it["bold"] else "normal"), tags=tags)
        if heat is not None:
            self._bubbles(boxes)
        self.create_text(8, H - 8, anchor="sw", text="Lăn chuột: zoom · kéo: di chuyển · nhấp đúp: về mặc định",
                         fill="#9AA5B1", font=("Segoe UI", 8))
