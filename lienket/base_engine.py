"""
base_engine.py — Lõi tính CHÂN CỘT bản đế + bu lông neo (Column base — CB), tương đương RAM Connection "Base plate"
================================================================================================================
AISC 360-10 (LRFD) J8, J3, J2 + AISC Design Guide 1, 2nd ed. (2006) + ACI 318-11 Appendix D (neo trong bê tông)
+ ACI 349-06 D.4.6 (bản chắn cắt).

Mô hình:
  • Cột chữ I (tiết diện tổ hợp theo quy cách của tool) hàn lên bản đế N × B × tp, đặt trên lớp vữa và bệ bê tông
    N2 × B2 × h (đồng tâm). Neo đặt theo lưới nx × ny, chỉ các neo trên chu vi lưới, cách mép bản ex / ey.
  • Nén + mô men mỗi phương: phương pháp ứng suất đều của DG1 §3.3 (mô men nhỏ: không kéo neo; mô men lớn: neo chịu kéo).
    Mô men hai phương (M33 và M22): kiểm tra độc lập từng phương, lực neo góc cộng tuyến tính (có cảnh báo).
  • Kéo (nhổ) chiếm ưu thế — không còn vùng ép: nhóm neo đàn hồi quanh tâm bản.
  • Bản đế: uốn phía ép (DG1 Eq. 3.3.14/15, nén đúng tâm theo §3.1 với λn'), uốn phía kéo (DG1 §3.3 / §3.2.2, mỗi neo).
  • Neo: AISC J3 (thanh ren: Fnt = 0.75Fu, Fnv = 0.40Fu / 0.50Fu), J3.7 kéo + cắt; ACI 318-11 App. D: thép,
    phá vỡ hình nón khi kéo, nhổ tuột, nổ mặt bên, phá vỡ khi cắt, cạy (pryout), tương tác D.7.
  • Cắt chân cột: ma sát (DG1 §3.5.1), neo, hoặc bản chắn cắt (ép mặt ACI 349-06, uốn, cắt, hàn).
  • Hàn cột – bản đế: phương pháp đàn hồi trên chu vi hàn (cánh + bụng), lực nén truyền bằng tì ép khi chọn "finished to bear".

Quy ước dấu: N > 0 kéo (nhổ) · V2 theo phương N (x) · V3 theo phương B (z) · M33 > 0 → mép +x chịu nén ·
M22 > 0 → mép +z chịu nén. Đơn vị nội bộ: N, mm, MPa. Nhập / xuất: kN, kN·m.
"""

from __future__ import annotations

import copy
import math
from typing import Callable, Optional

import engine as K

IN16 = K.IN / 16.0
isnan = K.isnan
material, edge_min, weld_min = K.material, K.edge_min, K.weld_min
member_at_joint = K.member_at_joint
ELECTRODES = K.ELECTRODES
kN, kNm, f1, f2 = K.kN, K.kNm, K.f1, K.f2

# bu lông neo: Fy, Fu (MPa)
ANCHOR_GRADES = {
    "4.6": (240, 400), "5.6": (300, 500), "6.6": (360, 600), "8.8": (640, 800),
    "F1554 Gr36": (248, 400), "F1554 Gr55": (380, 517), "F1554 Gr105": (724, 862), "A307": (248, 414),
}
ANCHOR_DIAS = [16, 20, 22, 24, 27, 30, 33, 36, 42, 48]
PITCH = {16: 2.0, 20: 2.5, 22: 2.5, 24: 3.0, 27: 3.0, 30: 3.5, 33: 3.5, 36: 4.0, 42: 4.5, 48: 5.0}
# DG1 Table 2.3 (quy đổi mm): lỗ bản đế, long đen tấm (cạnh × dày) tối thiểu
HOLE_DG1 = {16: 30, 20: 33, 22: 40, 24: 46, 27: 48, 30: 52, 33: 56, 36: 59, 42: 70, 48: 83}
WASHER_DG1 = {16: (50, 6), 20: (51, 6), 22: (64, 8), 24: (76, 10), 27: (76, 10), 30: (76, 13), 33: (89, 13),
              36: (89, 13), 42: (102, 16), 48: (127, 19)}
BP_TP = [12, 14, 16, 18, 20, 22, 25, 28, 30, 32, 35, 36, 40, 45, 50, 55, 60]
SHEAR_MODE = {"friction": "Ma sát bản đế – vữa", "anchors": "Bu lông neo", "lug": "Bản chắn cắt"}
DIR_NAME = {"33": "phương N (M33)", "22": "phương B (M22)"}


def anchor_hole(d): return HOLE_DG1.get(int(d), d + 20)
def washer_min(d): return WASHER_DG1.get(int(d), (2.5 * d, d / 3))
def anchor_ase(d): return math.pi / 4 * (d - 0.9382 * PITCH.get(int(d), 0.125 * d)) ** 2


def anchor_mat(grade):
    fy, fu = ANCHOR_GRADES.get(grade, ANCHOR_GRADES["5.6"])
    return dict(name=grade if grade in ANCHOR_GRADES else "5.6", Fy=float(fy), Fu=float(fu))


# ─────────────────────────── chuẩn hoá input ───────────────────────────
def normalize(inp: dict) -> dict:
    """Đồng bộ cỡ hàn D (1/16 in) → w (mm); số neo nguyên (sửa tại chỗ, trả về inp)."""
    wd = inp.get("weld", {})
    for k in ("fl", "web"):
        if k in wd and "D" in wd[k]:
            wd[k]["w"] = float(wd[k]["D"]) * IN16
    lug = inp.get("lug", {})
    if "D" in lug:
        lug["w"] = float(lug["D"]) * IN16
    an = inp["anchor"]
    for k in ("nx", "ny", "d"):
        an[k] = int(float(an[k]))
    return inp


# ─────────────────────────── hình học ───────────────────────────
def build_geometry(inp: dict) -> dict:
    W: list[str] = []
    c = member_at_joint(dict(inp["col"], topIsOuter=True), "cột")
    pl, ped, an = inp["plate"], inp["ped"], inp["anchor"]
    N, B, tp = float(pl["N"]), float(pl["B"]), float(pl["tp"])
    N2, B2 = float(ped["N2"]), float(ped["B2"])
    if N <= 0 or B <= 0 or tp <= 0:
        raise ValueError("Kích thước bản đế N, B, tp phải > 0.")
    if N2 < N or B2 < B:
        raise ValueError(f"Bệ bê tông {N2:g} × {B2:g} nhỏ hơn bản đế {N:g} × {B:g}.")
    nx, ny = max(int(an["nx"]), 2), max(int(an["ny"]), 2)
    ax, ay = N / 2 - float(an["ex"]), B / 2 - float(an["ey"])
    if ax <= 0 or ay <= 0:
        raise ValueError("Khoảng cách mép neo ex, ey phải nhỏ hơn N/2, B/2.")
    xs = [-ax + 2 * ax * i / (nx - 1) for i in range(nx)]
    ys = [-ay + 2 * ay * j / (ny - 1) for j in range(ny)]
    anchors = [dict(x=x, y=y) for x in xs for y in ys if i_edge(x, xs) or i_edge(y, ys)]
    d, bf = c["d"], max(c["bfE"], c["bfI"])
    tf = max(c["tfE"], c["tfI"])
    for a in anchors:
        a["cx"], a["cy"] = N2 / 2 - abs(a["x"]), B2 / 2 - abs(a["y"])
        a["ca"] = min(a["cx"], a["cy"])
        ax_, ay_ = abs(a["x"]), abs(a["y"])
        if ax_ >= d / 2:                                     # ngoài cánh cột (DG1: tay đòn tới tâm cánh, b = B / số neo của hàng)
            a["zone"], a["arm"] = "out", ax_ - d / 2 + tf / 2
            a["clear"] = ax_ - d / 2
        elif ay_ >= bf / 2:                                  # cạnh mép cánh, trong chiều cao tiết diện
            a["zone"], a["arm"] = "tip", ay_ - bf / 2
            a["clear"] = ay_ - bf / 2
        elif ax_ <= d / 2 - tf:                              # giữa hai cánh: tay đòn tới bụng / cánh gần nhất (45°)
            a["zone"], a["arm"] = "in", min(ay_ - c["tw"] / 2, d / 2 - tf - ax_)
            a["clear"] = a["arm"]
        else:                                                # trùng cánh cột
            a["zone"], a["arm"], a["clear"] = "clash", 0.0, -1.0
    m = (N - 0.95 * d) / 2
    n = (B - 0.80 * bf) / 2
    ratio = min(N2 / N, B2 / B)
    sq = min(max(ratio, 1.0), 2.0)
    return dict(W=W, col=c, d=d, bf=bf, tf=tf, N=N, B=B, tp=tp, N2=N2, B2=B2, ha=float(ped["h"]), grout=float(ped.get("grout") or 0),
                nx=nx, ny=ny, ax=ax, ay=ay, xs=xs, ys=ys, anchors=anchors, m=m, n=n, sqA=sq, A1=N * B, A2=N * B * sq * sq)


def i_edge(v, vs):
    return abs(v - vs[0]) < 1e-9 or abs(v - vs[-1]) < 1e-9


# ─────────────────────────── DG1: một phương ───────────────────────────
def dg1_direction(Pc: float, M: float, L: float, Wd: float, f: float, fpmax: float) -> dict:
    """Pc: lực nén (> 0 nén), M ≥ 0 mô men theo phương có chiều dài bản L, bề rộng Wd, neo kéo cách tâm f.
    Trả về: case ∈ axial | small | large | nosol | tension; Y, q (N/mm), Tu (tổng lực kéo hàng neo, N)."""
    qmax = fpmax * Wd
    if M < 1e-6 and Pc > 0:
        return dict(case="axial", e=0.0, Y=L, q=Pc / L, qmax=qmax, Tu=0.0, f=f)
    if Pc > 0:
        e = M / Pc
        ecrit = L / 2 - Pc / (2 * qmax)
        if e <= ecrit:
            Y = L - 2 * e
            return dict(case="small", e=e, ecrit=ecrit, Y=Y, q=Pc / Y, qmax=qmax, Tu=0.0, f=f)
    else:
        e, ecrit = math.inf, L / 2 - Pc / (2 * qmax)
    Kf = M + Pc * f                                         # mô men quanh hàng neo kéo
    if Kf <= 0:
        return dict(case="tension", e=e, Y=0.0, q=0.0, qmax=qmax, Tu=None, f=f)
    a = f + L / 2
    disc = a * a - 2 * Kf / qmax
    qreq = 2 * Kf / (a * a)
    if disc < 0:
        return dict(case="nosol", e=e, ecrit=ecrit, Y=None, q=qmax, qmax=qmax, qreq=qreq, Tu=None, f=f)
    Y = a - math.sqrt(disc)
    return dict(case="large", e=e, ecrit=ecrit, Y=Y, q=qmax, qmax=qmax, qreq=qreq, Tu=qmax * Y - Pc, f=f)


# ─────────────────────────── ACI 318-11 App. D ───────────────────────────
def _proj_area(pts, r, X, Y):
    """Diện tích hình chiếu: hộp bao các neo mở rộng r mỗi phía, cắt bởi biên bệ [−X, X] × [−Y, Y]."""
    x0 = max(min(p[0] for p in pts) - r, -X); x1 = min(max(p[0] for p in pts) + r, X)
    y0 = max(min(p[1] for p in pts) - r, -Y); y1 = min(max(p[1] for p in pts) + r, Y)
    return max(x1 - x0, 0) * max(y1 - y0, 0)


def aci_breakout_tension(G, pts, forces, hef, fc, lam, cracked):
    """Phá vỡ bê tông khi kéo của nhóm neo (D.5.2). pts: [(x, y)], forces: lực kéo từng neo (N). Trả về dict."""
    X, Y = G["N2"] / 2, G["B2"] / 2
    edges = [X - max(p[0] for p in pts), X + min(p[0] for p in pts), Y - max(p[1] for p in pts), Y + min(p[1] for p in pts)]
    near = [c for c in edges if c < 1.5 * hef]
    smax = max([abs(a[0] - b[0]) for a in pts for b in pts] + [abs(a[1] - b[1]) for a in pts for b in pts] + [0.0])
    h = hef
    if len(near) >= 3:                                      # D.5.2.3
        h = min(hef, max(max(near) / 1.5, smax / 3))
    ANco = 9 * h * h
    ANc = min(_proj_area(pts, 1.5 * h, X, Y), len(pts) * ANco)
    camin = min(edges)
    psi_ed = 1.0 if camin >= 1.5 * h else 0.7 + 0.3 * camin / (1.5 * h)
    psi_c = 1.0 if cracked else 1.25
    Nb = 10 * lam * math.sqrt(fc) * h ** 1.5
    nb_txt = f"Nb = kc·λ·√f'c·hef^1.5 = 10·{lam:g}·√{fc:g}·{f1(h)}^1.5 = {f1(kN(Nb))} kN (D-6)"
    if 280 <= h <= 635:
        Nb2 = 3.9 * lam * math.sqrt(fc) * h ** (5 / 3)
        if Nb2 > Nb:
            Nb, nb_txt = Nb2, f"Nb = 3.9·λ·√f'c·hef^(5/3) = 3.9·{lam:g}·√{fc:g}·{f1(h)}^(5/3) = {f1(kN(Nb))} kN (D-7, 280 ≤ hef ≤ 635)"
    T = sum(forces)
    if T > 0:
        ex = abs(sum(f * p[0] for f, p in zip(forces, pts)) / T - sum(p[0] for p in pts) / len(pts))
        ey = abs(sum(f * p[1] for f, p in zip(forces, pts)) / T - sum(p[1] for p in pts) / len(pts))
    else:
        ex = ey = 0.0
    psi_ec = 1 / (1 + 2 * ex / (3 * h)) * 1 / (1 + 2 * ey / (3 * h))
    Ncbg = ANc / ANco * psi_ec * psi_ed * psi_c * Nb
    return dict(h=h, ANc=ANc, ANco=ANco, camin=camin, psi_ed=psi_ed, psi_c=psi_c, psi_ec=psi_ec, Nb=Nb, nb_txt=nb_txt,
                Ncbg=Ncbg, phiN=0.70 * Ncbg, ex=ex, ey=ey, n=len(pts))


def aci_breakout_shear(G, an_pts, axis, sign, hef, da, fc, lam, cracked):
    """Phá vỡ bê tông khi cắt về phía mép (D.6.2) — hàng neo trước chịu toàn bộ lực cắt (thiên an toàn).
    axis 0: lực cắt theo x (V2); 1: theo z (V3). sign: hướng lực cắt."""
    X, Y = G["N2"] / 2, G["B2"] / 2
    E1, E2 = (X, Y) if axis == 0 else (Y, X)
    o = 1 - axis
    front_v = max(sign * p[axis] for p in an_pts)
    front = [p for p in an_pts if abs(sign * p[axis] - front_v) < 1e-6]
    ca1 = E1 - front_v
    lo, hi = min(p[o] for p in front), max(p[o] for p in front)
    c2a, c2b = E2 + lo, E2 - hi
    ha = G["ha"]
    ca1e = ca1
    if c2a < 1.5 * ca1 and c2b < 1.5 * ca1 and ha < 1.5 * ca1:          # D.6.2.4 cấu kiện hẹp
        ca1e = max(max(c2a, c2b) / 1.5, ha / 1.5, (hi - lo) / 3)
    AVco = 4.5 * ca1e ** 2
    AVc = (min(1.5 * ca1e, c2a) + (hi - lo) + min(1.5 * ca1e, c2b)) * min(1.5 * ca1e, ha)
    AVc = min(AVc, len(front) * AVco)
    c2min = min(c2a, c2b)
    psi_ed = 1.0 if c2min >= 1.5 * ca1e else 0.7 + 0.3 * c2min / (1.5 * ca1e)
    psi_c = 1.0 if cracked else 1.4
    psi_h = max(1.0, math.sqrt(1.5 * ca1e / ha))
    le = min(hef, 8 * da)
    Vb = min(0.6 * (le / da) ** 0.2 * math.sqrt(da) * lam * math.sqrt(fc) * ca1e ** 1.5, 3.7 * lam * math.sqrt(fc) * ca1e ** 1.5)
    Vcbg = AVc / AVco * psi_ed * psi_c * psi_h * Vb
    return dict(ca1=ca1, ca1e=ca1e, c2a=c2a, c2b=c2b, AVc=AVc, AVco=AVco, psi_ed=psi_ed, psi_c=psi_c, psi_h=psi_h, le=le, Vb=Vb,
                Vcbg=Vcbg, phiV=0.70 * Vcbg, n=len(front))


# ─────────────────────────── tính chính ───────────────────────────
def compute(inp: dict) -> dict:
    normalize(inp)
    G = build_geometry(inp)
    W = G["W"]
    pl, ped, an, opt = inp["plate"], inp["ped"], inp["anchor"], inp["opt"]
    col = G["col"]
    pm = material(pl["mat"])
    Fy = pm["Fy"]
    fc, lam, cracked = float(ped["fc"]), float(ped.get("lw") or 1.0), bool(ped.get("cracked", True))
    reinf = bool(ped.get("reinf"))
    fyr, AsN, AsV = float(ped.get("fyr") or 400), float(ped.get("AsN") or 0), float(ped.get("AsV") or 0)
    tp = G["tp"]
    am = anchor_mat(an["grade"])
    da = float(an["d"])
    Ab = math.pi * da * da / 4
    Ase = anchor_ase(da)
    v16 = "2016" in inp.get("gen", {}).get("designCode", "")
    Fnt = 0.75 * am["Fu"]
    Fnv = (0.563 if an.get("thread") == "X" else 0.45) * am["Fu"] if v16 else (0.50 if an.get("thread") == "X" else 0.40) * am["Fu"]
    futa = min(am["Fu"], 1.9 * am["Fy"], 860.0)
    hef = float(an["hef"])
    if an.get("head") == "plate":
        Abrg = float(an.get("plateB") or 2 * da) ** 2 - Ab
        head_sz = float(an.get("plateB") or 2 * da)
    else:
        F = 1.5 * da + 5                                    # đai ốc lục giác nặng (cạnh – cạnh)
        Abrg = 0.866 * F * F - Ab
        head_sz = 1.155 * F
    weldF = ELECTRODES.get(inp["weld"]["electrode"], 482.6)
    phiC = 0.65
    fpmax = phiC * 0.85 * fc * G["sqA"]
    pts = [(a["x"], a["y"]) for a in G["anchors"]]
    nA = len(pts)
    G.update(Fy=Fy, fpmax=fpmax, Ab=Ab, Ase=Ase, Abrg=Abrg, head=head_sz, hole=anchor_hole(da), am=am, Fnt=Fnt, Fnv=Fnv)
    mode = inp["shear"]["mode"]

    checks: dict[str, dict] = {}
    order: list[str] = []

    def add(cid, grp, name, unit, ref, cap, dem, combo, detail, tags=(), info=False):
        ratio = abs(dem) / cap if cap and cap > 0 else (math.inf if abs(dem) > 0 or isnan(cap) else 0.0)
        if isnan(ratio): ratio = math.inf
        c = checks.get(cid)
        if c is None:
            c = checks[cid] = dict(id=cid, grp=grp, name=name, unit=unit, ref=ref, cap=cap, dem=dem, ratio=-1.0,
                                   combo=combo, detail=[], tags=list(tags), info=info)
            order.append(cid)
        if ratio > c["ratio"]:
            c.update(cap=cap, dem=dem, ratio=ratio, combo=combo, detail=detail() if callable(detail) else list(detail or []))

    m_, n_ = G["m"], G["n"]
    Mcap = 0.9 * Fy * tp * tp / 4                           # φMn của bản trên đơn vị bề rộng (N·mm/mm)
    sx2 = sum(p[0] ** 2 for p in pts) or 1.0
    sy2 = sum(p[1] ** 2 for p in pts) or 1.0
    d, bf, tf, tw = G["d"], G["bf"], G["tf"], col["tw"]

    # chu vi hàn cột – bản đế (đường, bề dày họng đơn vị)
    hw = d - col["tfE"] - col["tfI"]
    Lf = (2 * col["bfE"] - tw) + (2 * col["bfI"] - tw)
    Lw = 2 * hw
    Lt = Lf + Lw
    I33 = sum(L * x * x for L, x in ((col["bfE"], d / 2), (col["bfE"] - tw, d / 2 - col["tfE"]),
                                     (col["bfI"], d / 2), (col["bfI"] - tw, d / 2 - col["tfI"]))) + 2 * hw ** 3 / 12
    I22 = sum((b ** 3 - (tw ** 3 if inner else 0)) / 12 for b, inner in ((col["bfE"], False), (col["bfE"], True),
                                                                           (col["bfI"], False), (col["bfI"], True))) + 2 * hw * (tw / 2) ** 2
    G.update(Lf=Lf, Lw=Lw, Lt=Lt, I33=I33, I22=I22)
    wfl, wweb = float(inp["weld"]["fl"]["w"]), float(inp["weld"]["web"]["w"])
    qfl, qweb = 0.75 * 0.6 * weldF * 0.707 * wfl, 0.75 * 0.6 * weldF * 0.707 * wweb

    demands = []
    for ci, cb in enumerate(inp.get("loads", [])):
        g = lambda key: float(cb.get(key) or 0.0)
        Nt, V2, V3, M33, M22 = g("N") * 1e3, g("V2") * 1e3, g("V3") * 1e3, g("M33") * 1e6, g("M22") * 1e6
        nm = cb.get("name") or f"TH{ci + 1}"
        Pc = -Nt
        Vr = math.hypot(V2, V3)
        dirs = {}
        if abs(M33) > 1e-6 or (abs(M22) <= 1e-6 and Pc > 0):
            dirs["33"] = dg1_direction(Pc, abs(M33), G["N"], G["B"], G["ax"], fpmax)
        if abs(M22) > 1e-6:
            dirs["22"] = dg1_direction(Pc, abs(M22), G["B"], G["N"], G["ay"], fpmax)
        if len(dirs) == 2:
            W.append(f"{nm}: mô men hai phương — kiểm tra ép mặt / bản đế độc lập từng phương, lực neo góc cộng tuyến tính (gần đúng).")

        # ---------- lực kéo từng neo ----------
        T = [0.0] * nA
        tens_all = all(r["case"] == "tension" for r in dirs.values()) and dirs
        if not dirs:                                         # kéo đúng tâm (hoặc không tải)
            T = [max(Nt, 0.0) / nA] * nA
        elif tens_all:                                       # không còn vùng ép: nhóm neo đàn hồi quanh tâm bản
            for i, (x, y) in enumerate(pts):
                T[i] = max(Nt / nA - M33 * x / sx2 - M22 * y / sy2, 0.0)
        else:
            for key, r in dirs.items():
                ax_ = 0 if key == "33" else 1
                Mk = M33 if key == "33" else M22
                if r["case"] == "large":
                    far = -math.copysign(G["ax"] if key == "33" else G["ay"], Mk)
                    line = [i for i, p in enumerate(pts) if abs(p[ax_] - far) < 1e-6]
                    for i in line: T[i] += r["Tu"] / len(line)
                elif r["case"] == "tension":
                    s2 = sx2 if key == "33" else sy2
                    for i, p in enumerate(pts):
                        T[i] += max(Nt / nA - Mk * p[ax_] / s2, 0.0)
        Tmax = max(T) if T else 0.0
        Tsum = sum(T)

        # ---------- ép mặt bê tông + uốn bản phía ép ----------
        for key, r in dirs.items():
            L, Wd = (G["N"], G["B"]) if key == "33" else (G["B"], G["N"])
            Mk = abs(M33 if key == "33" else M22)
            dn = DIR_NAME[key]
            head = lambda r=r, L=L, Wd=Wd, Mk=Mk: [
                f"A1 = N·B = {G['N']:g}·{G['B']:g} = {f1(G['A1'])} mm²;  √(A2/A1) = min(N2/N; B2/B; 2) = {f2(G['sqA'])}",
                f"fp,max = φc·0.85·f'c·√(A2/A1) = 0.65·0.85·{fc:g}·{f2(G['sqA'])} = {f2(fpmax)} MPa (J8-2);  qmax = fp,max·{Wd:g} = {f1(r['qmax'])} N/mm",
                f"Pu (nén) = {f1(kN(Pc))} kN;  Mu = {f2(kNm(Mk))} kN·m;  e = Mu/Pu = " + ("∞" if math.isinf(r["e"]) else f"{f1(r['e'])} mm")
                + (f";  e_crit = {L:g}/2 − Pu/(2qmax) = {f1(r['ecrit'])} mm" if "ecrit" in r else ""),
            ]
            if r["case"] in ("axial", "small"):
                add(f"conc_bear_{key}", "Bê tông (ép mặt)", f"Ép mặt bê tông dưới bản đế — {dn}", "MPa", "AISC J8 / DG1 §3.1, 3.3",
                    fpmax, r["q"] / Wd, nm, lambda r=r, head=head, L=L: head() + [
                        ("Nén đúng tâm: Y = N" if r["case"] == "axial" else f"Mô men nhỏ (e ≤ e_crit): Y = {L:g} − 2e = {f1(r['Y'])} mm"),
                        f"fp = Pu/(Y·B) = {f2(r['q'] / (G['B'] if key == '33' else G['N']))} MPa ≤ fp,max = {f2(fpmax)} MPa"], ("conc", "bp"))
            elif r["case"] in ("large", "nosol"):
                add(f"bp_size_{key}", "Bê tông (ép mặt)", f"Kích thước bản đế — mô men lớn, {dn}", "N/mm", "DG1 Eq. 3.4.4",
                    r["qmax"], r["qreq"], nm, lambda r=r, head=head, L=L: head() + [
                        f"Mô men lớn (e > e_crit): neo chịu kéo, f = {f1(r['f'])} mm",
                        f"Điều kiện có nghiệm: (f + N/2)² ≥ 2·Pu·(e + f)/qmax ⇔ q,req = 2(Mu + Pu·f)/(f + N/2)² = {f1(r['qreq'])} ≤ qmax = {f1(r['qmax'])} N/mm",
                        (f"Y = (f + N/2) − √[(f + N/2)² − 2(Mu + Pu·f)/qmax] = {f1(r['Y'])} mm;  Tu = qmax·Y − Pu = {f1(kN(r['Tu']))} kN"
                         if r["case"] == "large" else "Không có nghiệm → tăng kích thước bản đế (N) hoặc cường độ bê tông.")], ("conc", "bp"))
            if r["case"] in ("axial", "small", "large"):
                fp = r["q"] / Wd
                Y = r["Y"]
                lam_n, X, lamb = 0.0, 0.0, 0.0
                if r["case"] == "axial":
                    X = min(4 * d * bf / (d + bf) ** 2 * Pc / (fpmax * G["A1"]), 1.0)
                    lamb = min(2 * math.sqrt(X) / (1 + math.sqrt(max(1 - X, 0.0))), 1.0)
                    lam_n = lamb * math.sqrt(d * bf) / 4
                l = max(m_, n_, lam_n)
                Mpl = fp * l * l / 2 if Y >= l else fp * Y * (l - Y / 2)
                tpreq = math.sqrt(4 * Mpl / (0.9 * Fy)) if Mpl > 0 else 0.0
                add(f"bp_comp_{key}", "Bản đế", f"Uốn bản đế phía ép — {dn}", "kN·m/m", "DG1 Eq. 3.3.14, 3.3.15 / 3.1.3",
                    Mcap / 1e3, Mpl / 1e3, nm, lambda l=l, fp=fp, Y=Y, Mpl=Mpl, tpreq=tpreq, X=X, lamb=lamb, lam_n=lam_n, r=r: [
                        f"m = (N − 0.95d)/2 = ({G['N']:g} − 0.95·{f1(d)})/2 = {f1(m_)} mm;  n = (B − 0.8bf)/2 = ({G['B']:g} − 0.8·{f1(bf)})/2 = {f1(n_)} mm",
                    ] + ([f"X = 4·d·bf/(d + bf)²·Pu/(φc·Pp) = {f2(X)};  λ = 2√X/(1 + √(1 − X)) = {f2(lamb)};  λn' = λ·√(d·bf)/4 = {f1(lam_n)} mm"]
                         if r["case"] == "axial" else []) + [
                        f"l = max(m; n{'; λn' if r['case'] == 'axial' else ''}) = {f1(l)} mm;  fp = {f2(fp)} MPa;  Y = {f1(Y)} mm",
                        ("Mpl = fp·l²/2" if Y >= l else "Mpl = fp·Y·(l − Y/2)") + f" = {f2(Mpl / 1e3)} kN·m/m",
                        f"φMn = 0.9·Fy·tp²/4 = 0.9·{Fy:g}·{tp:g}²/4 = {f2(Mcap / 1e3)} kN·m/m",
                        f"tp,req = √(4Mpl/(0.9Fy)) = {f1(tpreq)} mm  (tp = {tp:g} mm)"], ("bp",))

        # ---------- uốn bản phía kéo (mỗi neo) ----------
        if Tmax > 0:
            best = None
            for i, a in enumerate(G["anchors"]):
                if T[i] <= 0 or a["zone"] == "clash": continue
                arm = max(a["arm"], 0.0)
                if a["zone"] == "out":
                    beff = G["B"] / G["ny"] if abs(abs(a["x"]) - G["ax"]) < 1e-6 else 2 * arm
                else:
                    beff = 2 * arm
                Mpl = T[i] * arm / beff if beff > 0 else 0.0
                if best is None or Mpl > best[0]: best = (Mpl, i, arm, beff)
            if best:
                Mpl, i, arm, beff = best
                a = G["anchors"][i]
                tpreq = math.sqrt(4 * Mpl / (0.9 * Fy))
                add("bp_ten", "Bản đế", "Uốn bản đế phía kéo (neo chịu kéo)", "kN·m/m", "DG1 Eq. 3.3.13 / §3.2.2", Mcap / 1e3, Mpl / 1e3, nm,
                    lambda Mpl=Mpl, a=a, arm=arm, beff=beff, Ti=T[i], tpreq=tpreq: [
                        f"Neo bất lợi tại (x = {f1(a['x'])}; z = {f1(a['y'])}) mm, Tu,neo = {f2(kN(Ti))} kN",
                        ("Neo ngoài cánh: tay đòn tới tâm cánh x = f − d/2 + tf/2 = " if a["zone"] == "out" else
                         "Neo cạnh mép cánh: tay đòn tới mép cánh = " if a["zone"] == "tip" else
                         "Neo giữa hai cánh: tay đòn tới bụng / cánh gần nhất = ") + f"{f1(arm)} mm",
                        (f"Bề rộng làm việc b = B/ny = {f1(beff)} mm (DG1 §3.3)" if a["zone"] == "out" and beff != 2 * arm
                         else f"Bề rộng làm việc b = 2·tay đòn = {f1(beff)} mm (phân bố 45°, DG1 §3.2.2)"),
                        f"Mpl = Tu,neo·x/b = {f2(Mpl / 1e3)} kN·m/m;  φMn = 0.9·Fy·tp²/4 = {f2(Mcap / 1e3)} kN·m/m",
                        f"tp,req = 2.11·√(Tu·x/(b·Fy)) = {f1(tpreq)} mm  (tp = {tp:g} mm)"], ("bp", "anchors"))

        # ---------- cắt chân cột ----------
        Va = 0.0                                             # lực cắt một neo
        nv = nA if an.get("shearAll", True) else max(nA // 2, 1)
        if mode == "friction":
            mu = float(inp["shear"].get("mu") or 0.55)
            cap = 0.75 * mu * max(Pc, 0.0)
            add("shear_fric", "Truyền lực cắt", "Ma sát bản đế – vữa", "kN", "DG1 §3.5.1", kN(cap), kN(Vr), nm, lambda cap=cap, mu=mu: [
                f"Vu = √(V2² + V3²) = {f2(kN(Vr))} kN;  Pu (nén) = {f2(kN(max(Pc, 0)))} kN" + ("  — có lực nhổ: không có ma sát" if Pc <= 0 else ""),
                f"φVn = φ·μ·Pu = 0.75·{mu:g}·{f2(kN(max(Pc, 0)))} = {f2(kN(cap))} kN"], ("bp", "conc"))
        elif mode == "anchors":
            Va = Vr / nv
            if G["grout"] > 50 and Vr > 0:
                W.append(f"Lớp vữa {G['grout']:g} mm > 50 mm, neo chịu cắt: chưa xét uốn neo qua lớp vữa (DG1 §3.5.2).")
        else:
            lg = inp["lug"]
            bl, H, tl = float(lg["bl"]), float(lg["H"]), float(lg["tl"])
            lm = material(lg.get("mat", "Q345"))
            demb = max(H - G["grout"], 0.0)
            Abr = bl * demb
            capB = 0.65 * 1.3 * fc * Abr
            add("lug_bear", "Bản chắn cắt", "Ép mặt bê tông lên bản chắn cắt", "kN", "ACI 349-06 D.4.6.2 (DG1 §3.5.3)", kN(capB), kN(Vr), nm,
                lambda Abr=Abr, demb=demb, capB=capB, bl=bl: [
                    f"Chiều sâu chôn trong bê tông = H − vữa = {f1(demb)} mm;  A_brg = bl·(H − G) = {bl:g}·{f1(demb)} = {f1(Abr)} mm²",
                    f"φVn = 0.65·1.3·f'c·A_brg = {f2(kN(capB))} kN  (Vu = √(V2² + V3²), bản chắn chịu toàn bộ lực cắt)"], ("lug", "conc"))
            arm = G["grout"] + demb / 2
            Mu = Vr * arm
            capM = 0.9 * lm["Fy"] * bl * tl * tl / 4
            add("lug_flex", "Bản chắn cắt", "Uốn bản chắn cắt tại chân hàn", "kN·m", "DG1 §3.5.3; AISC F11", kNm(capM), kNm(Mu), nm,
                lambda Mu=Mu, capM=capM, arm=arm: [
                    f"Mu = Vu·(G + (H − G)/2) = {f2(kN(Vr))}·{f1(arm)}/1000 = {f2(kNm(Mu))} kN·m",
                    f"φMn = 0.9·Fy·bl·tl²/4 = 0.9·{lm['Fy']:g}·{bl:g}·{tl:g}²/4 = {f2(kNm(capM))} kN·m"], ("lug",))
            capV = 1.0 * 0.6 * lm["Fy"] * bl * tl
            add("lug_v", "Bản chắn cắt", "Chảy cắt bản chắn cắt", "kN", "AISC Eq. J4-3", kN(capV), kN(Vr), nm,
                lambda capV=capV: [f"φVn = 1.0·0.6·Fy·bl·tl = {f2(kN(capV))} kN"], ("lug",))
            wl = float(lg["w"])
            armw = tl + 2 * wl / 3
            fv, fn = Vr / (2 * bl), Mu / (armw * bl)
            fr = math.hypot(fv, fn)
            capw = 0.75 * 0.6 * weldF * 0.707 * wl
            add("lug_w", "Bản chắn cắt", "Hàn bản chắn cắt vào bản đế", "kN/m", "AISC Eq. J2-4", capw, fr, nm,
                lambda fv=fv, fn=fn, fr=fr, capw=capw, wl=wl, armw=armw: [
                    f"Hai đường hàn góc w = {wl:g} mm dài bl = {bl:g} mm;  cánh tay đòn cặp lực = tl + 2w/3 = {f1(armw)} mm",
                    f"fv = Vu/(2bl) = {f1(fv)} N/mm;  fn = Mu/(arm·bl) = {f1(fn)} N/mm;  fr = √(fv² + fn²) = {f1(fr)} N/mm",
                    f"φRn = 0.75·0.6·FEXX·0.707·w = {f1(capw)} N/mm"], ("lug",))

        # ---------- neo: AISC J3 ----------
        rT = 0.75 * Fnt * Ab
        add("anc_t", "Bu lông neo (AISC)", "Neo chịu kéo", "kN", "AISC J3.6 (Table J3.2, threaded parts)", kN(rT), kN(Tmax), nm,
            lambda rT=rT: [f"Lực kéo neo lớn nhất Tu = {f2(kN(Tmax))} kN (tổng nhóm {f2(kN(Tsum))} kN)",
                           f"Neo M{da:g} cấp {am['name']}: Fu = {am['Fu']:g} MPa;  Fnt = 0.75Fu = {f1(Fnt)} MPa;  Ab = {f1(Ab)} mm²",
                           f"φRn = 0.75·Fnt·Ab = {f2(kN(rT))} kN"], ("anchors",))
        if mode == "anchors":
            rV = 0.75 * Fnv * Ab
            add("anc_v", "Bu lông neo (AISC)", "Neo chịu cắt", "kN", "AISC J3.6 (Table J3.2)", kN(rV), kN(Va), nm,
                lambda rV=rV, nv=nv: [f"Vu = √(V2² + V3²) = {f2(kN(Vr))} kN chia cho {nv} neo → Vu,neo = {f2(kN(Va))} kN",
                                      f"Fnv = {Fnv / am['Fu']:.3f}Fu = {f1(Fnv)} MPa;  φRn = 0.75·Fnv·Ab = {f2(kN(rV))} kN"], ("anchors",))
            frv = Va / Ab
            Fp = min(1.3 * Fnt - Fnt / (0.75 * Fnv) * frv, Fnt)
            capTV = 0.75 * max(Fp, 0.0) * Ab
            add("anc_tv", "Bu lông neo (AISC)", "Neo chịu kéo + cắt đồng thời", "kN", "AISC Eq. J3-3a", kN(capTV), kN(Tmax), nm,
                lambda Fp=Fp, frv=frv, capTV=capTV: [
                    f"frv = Vu,neo/Ab = {f1(frv)} MPa;  F'nt = 1.3Fnt − Fnt/(φFnv)·frv = {f1(Fp)} ≤ Fnt = {f1(Fnt)} MPa",
                    f"φRn = 0.75·F'nt·Ab = {f2(kN(capTV))} kN"], ("anchors",))

        # ---------- neo: ACI 318-11 App. D ----------
        if opt.get("aci", True):
            tN, tV = [], []                                  # tỷ số nhóm kéo / cắt cho tương tác D.7
            if Tmax > 0:
                cap = 0.75 * Ase * futa
                add("aci_sa", "Neo – bê tông (ACI 318-11)", "Bền thép neo khi kéo", "kN", "ACI 318-11 D.5.1", kN(cap), kN(Tmax), nm,
                    lambda cap=cap: [f"Ase,N = π/4·(d − 0.9382p)² = {f1(Ase)} mm²;  futa = min(Fu; 1.9Fy; 860) = {f1(futa)} MPa",
                                     f"φNsa = 0.75·Ase·futa = {f2(kN(cap))} kN"], ("anchors",))
                tN.append(Tmax / cap)
                tp_ = [p for p, t in zip(pts, T) if t > 0]
                tf_ = [t for t in T if t > 0]
                if reinf:
                    capR = 0.75 * fyr * AsN
                    add("aci_rt", "Neo – bê tông (ACI 318-11)", "Cốt thép neo chịu kéo (thay phá vỡ bê tông)", "kN", "ACI 318-11 D.5.2.9",
                        kN(capR), kN(Tsum), nm, lambda capR=capR: [
                            "Có cốt thép neo (anchor reinforcement) quanh nhóm neo kéo: không xét phá vỡ hình nón bê tông (D.5.2.9)",
                            f"As = {AsN:g} mm², fy = {fyr:g} MPa → φNn = 0.75·As·fy = {f2(kN(capR))} kN;  Nua = {f2(kN(Tsum))} kN",
                            "Cốt thép phải được neo đủ chiều dài phát triển về hai phía mặt phá hoại giả định (kiểm tra riêng)."], ("conc", "anchors"))
                    tN.append(Tsum / capR if capR > 0 else math.inf)
                else:
                    br = aci_breakout_tension(G, tp_, tf_, hef, fc, lam, cracked)
                    add("aci_cb", "Neo – bê tông (ACI 318-11)", "Phá vỡ bê tông khi kéo (nhóm neo)", "kN", "ACI 318-11 D.5.2", kN(br["phiN"]), kN(Tsum), nm,
                        lambda br=br: [
                            f"Nhóm {br['n']} neo chịu kéo, tổng Nua = {f2(kN(Tsum))} kN;  hef = {hef:g} mm" + (f" → h'ef = {f1(br['h'])} mm (D.5.2.3)" if br["h"] < hef else ""),
                            br["nb_txt"],
                            f"ANc = {f1(br['ANc'])} mm²;  ANco = 9·hef² = {f1(br['ANco'])} mm²",
                            f"ψec = {f2(br['psi_ec'])} (e'N = {f1(br['ex'])}; {f1(br['ey'])} mm);  ψed = {f2(br['psi_ed'])} (ca,min = {f1(br['camin'])} mm);  "
                            f"ψc = {br['psi_c']:g} ({'nứt' if cracked else 'không nứt'});  ψcp = 1.0",
                            f"φNcbg = 0.70·ANc/ANco·ψec·ψed·ψc·ψcp·Nb = {f2(kN(br['phiN']))} kN"], ("conc", "anchors"))
                    tN.append(Tsum / br["phiN"] if br["phiN"] > 0 else math.inf)
                psi_cp = 1.0 if cracked else 1.4
                Np = 8 * Abrg * fc
                capP = 0.70 * psi_cp * Np
                add("aci_pn", "Neo – bê tông (ACI 318-11)", "Nhổ tuột neo (pullout)", "kN", "ACI 318-11 D.5.3", kN(capP), kN(Tmax), nm,
                    lambda Np=Np, capP=capP, psi_cp=psi_cp: [
                        f"Abrg = {f1(Abrg)} mm² ({'bản đầu neo' if an.get('head') == 'plate' else 'đai ốc lục giác nặng'});  Np = 8·Abrg·f'c = {f2(kN(Np))} kN",
                        f"φNpn = 0.70·ψc,P·Np = 0.70·{psi_cp:g}·{f2(kN(Np))} = {f2(kN(capP))} kN"], ("anchors", "conc"))
                tN.append(Tmax / capP)
                # nổ mặt bên: theo từng mép bệ, nhóm neo gần mép đó
                for edge, (axis, sgn) in {"+x": (0, 1), "-x": (0, -1), "+z": (1, 1), "-z": (1, -1)}.items():
                    E = G["N2"] / 2 if axis == 0 else G["B2"] / 2
                    grp = [(p, t) for p, t in zip(pts, T) if t > 0 and sgn * p[axis] > 0]
                    grp = [(p, t) for p, t in grp if E - abs(p[axis]) <= min(G["N2"] / 2 - abs(p[0]), G["B2"] / 2 - abs(p[1])) + 1e-6]
                    if not grp: continue
                    ca1 = min(E - abs(p[axis]) for p, _t in grp)
                    if hef <= 2.5 * ca1: continue
                    o = 1 - axis
                    E2 = G["B2"] / 2 if axis == 0 else G["N2"] / 2
                    ca2 = min(E2 - abs(p[o]) for p, _t in grp)
                    Nsb = 13 * ca1 * math.sqrt(Abrg) * lam * math.sqrt(fc)
                    if ca2 < 3 * ca1:
                        Nsb *= (1 + min(max(ca2 / ca1, 1.0), 3.0)) / 4
                    s = max(p[o] for p, _t in grp) - min(p[o] for p, _t in grp)
                    Nsbg = (1 + s / (6 * ca1)) * Nsb if len(grp) > 1 and s < 6 * ca1 else len(grp) * Nsb
                    dem = sum(t for _p, t in grp)
                    add(f"aci_sb{edge}", "Neo – bê tông (ACI 318-11)", f"Nổ mặt bên bê tông (mép {edge})", "kN", "ACI 318-11 D.5.4",
                        kN(0.70 * Nsbg), kN(dem), nm, lambda ca1=ca1, ca2=ca2, Nsb=Nsb, Nsbg=Nsbg, s=s, grp=grp: [
                            f"hef = {hef:g} > 2.5·ca1 = {f1(2.5 * ca1)} mm → xét nổ mặt bên;  ca1 = {f1(ca1)} mm, ca2 = {f1(ca2)} mm",
                            "Nsb = 13·ca1·√Abrg·λ·√f'c" + (" ·(1 + ca2/ca1)/4" if ca2 < 3 * ca1 else "") + f" = {f2(kN(Nsb))} kN",
                            (f"Nhóm {len(grp)} neo, s = {f1(s)} mm < 6ca1: Nsbg = (1 + s/(6ca1))·Nsb = {f2(kN(Nsbg))} kN" if len(grp) > 1 and s < 6 * ca1
                             else f"Nsbg = {len(grp)}·Nsb = {f2(kN(Nsbg))} kN"),
                            f"φNsbg = 0.70·Nsbg = {f2(kN(0.70 * Nsbg))} kN"], ("conc", "anchors"))
                    tN.append(dem / (0.70 * Nsbg))
            if mode == "anchors" and Vr > 0:
                Vsa = 0.6 * Ase * futa * (0.8 if G["grout"] > 0 else 1.0)
                add("aci_vsa", "Neo – bê tông (ACI 318-11)", "Bền thép neo khi cắt", "kN", "ACI 318-11 D.6.1", kN(0.65 * Vsa), kN(Va), nm,
                    lambda Vsa=Vsa: ["Vsa = 0.6·Ase,V·futa" + (" ·0.8 (có lớp vữa, D.6.1.3)" if G["grout"] > 0 else "") + f" = {f2(kN(Vsa))} kN",
                                     f"φVsa = 0.65·Vsa = {f2(kN(0.65 * Vsa))} kN;  Vu,neo = {f2(kN(Va))} kN"], ("anchors",))
                tV.append(Va / (0.65 * Vsa))
                for axis, Vc, lab in ((0, V2, "V2 — phương N"), (1, V3, "V3 — phương B")):
                    if abs(Vc) < 1e-6: continue
                    if reinf:
                        capR = 0.75 * fyr * AsV
                        add(f"aci_rv_{axis}", "Neo – bê tông (ACI 318-11)", f"Cốt thép neo chịu cắt ({lab})", "kN", "ACI 318-11 D.6.2.9",
                            kN(capR), kN(abs(Vc)), nm, lambda capR=capR, Vc=Vc: [
                                "Có cốt thép neo (đai / thép chữ U ôm neo): không xét phá vỡ bê tông khi cắt (D.6.2.9)",
                                f"As = {AsV:g} mm², fy = {fyr:g} MPa → φVn = 0.75·As·fy = {f2(kN(capR))} kN;  |V| = {f2(kN(abs(Vc)))} kN"], ("conc", "anchors"))
                        tV.append(abs(Vc) / capR if capR > 0 else math.inf)
                        continue
                    sb = aci_breakout_shear(G, pts, axis, 1 if Vc > 0 else -1, hef, da, fc, lam, cracked)
                    add(f"aci_vcb_{axis}", "Neo – bê tông (ACI 318-11)", f"Phá vỡ bê tông khi cắt ({lab})", "kN", "ACI 318-11 D.6.2",
                        kN(sb["phiV"]), kN(abs(Vc)), nm, lambda sb=sb, Vc=Vc: [
                            f"Hàng neo trước ({sb['n']} neo) chịu toàn bộ |V| = {f2(kN(abs(Vc)))} kN;  ca1 = {f1(sb['ca1'])} mm"
                            + (f" → c'a1 = {f1(sb['ca1e'])} mm (D.6.2.4)" if sb["ca1e"] < sb["ca1"] else ""),
                            f"Vb = min[0.6(le/da)^0.2·√da·λ·√f'c·ca1^1.5; 3.7·λ·√f'c·ca1^1.5] = {f2(kN(sb['Vb']))} kN  (le = {f1(sb['le'])} mm)",
                            f"AVc = {f1(sb['AVc'])} mm²;  AVco = 4.5·ca1² = {f1(sb['AVco'])} mm²;  ψed = {f2(sb['psi_ed'])};  ψc = {sb['psi_c']:g};  ψh = {f2(sb['psi_h'])}",
                            f"φVcbg = 0.70·AVc/AVco·ψed·ψc·ψh·Vb = {f2(kN(sb['phiV']))} kN"], ("conc", "anchors"))
                    tV.append(abs(Vc) / sb["phiV"] if sb["phiV"] > 0 else math.inf)
                ball = aci_breakout_tension(G, pts, [1.0] * nA, hef, fc, lam, cracked)
                kcp = 1.0 if hef < 65 else 2.0
                capCP = 0.70 * kcp * ball["Ncbg"]
                add("aci_cp", "Neo – bê tông (ACI 318-11)", "Cạy bê tông (pryout)", "kN", "ACI 318-11 D.6.3", kN(capCP), kN(Vr), nm,
                    lambda capCP=capCP, ball=ball, kcp=kcp: [
                        f"Ncpg = Ncbg của toàn nhóm {nA} neo = {f2(kN(ball['Ncbg']))} kN;  kcp = {kcp:g}",
                        f"φVcpg = 0.70·kcp·Ncpg = {f2(kN(capCP))} kN;  Vu = {f2(kN(Vr))} kN"], ("conc", "anchors"))
                tV.append(Vr / capCP)
            if tN and tV:
                rn, rv = max(tN), max(tV)
                if rv <= 0.2: val, how = rn, "Vua/φVn ≤ 0.2 → chỉ kiểm tra kéo"
                elif rn <= 0.2: val, how = rv, "Nua/φNn ≤ 0.2 → chỉ kiểm tra cắt"
                else: val, how = (rn + rv) / 1.2, "Nua/φNn + Vua/φVn ≤ 1.2"
                add("aci_int", "Neo – bê tông (ACI 318-11)", "Tương tác kéo – cắt (neo / bê tông)", "", "ACI 318-11 D.7", 1.0, val, nm,
                    lambda rn=rn, rv=rv, how=how, val=val: [f"Nua/φNn (lớn nhất) = {f2(rn)};  Vua/φVn (lớn nhất) = {f2(rv)}", how,
                                                           f"Tỷ số = {f2(val)}"], ("anchors", "conc"))

        # ---------- hàn cột – bản đế ----------
        Nw = max(Nt, 0.0) if opt.get("bear", True) else abs(Nt)
        fn_f = Nw / Lt + abs(M33) * (d / 2) / I33 + abs(M22) * (bf / 2) / I22
        fn_w = Nw / Lt + abs(M33) * (hw / 2) / I33 + abs(M22) * (tw / 2) / I22
        fv = Vr / Lt
        for key, fn, cap, wsz, lab, tag in (("w_fl", fn_f, qfl, wfl, "Hàn cánh cột vào bản đế", "wflange"),
                                            ("w_web", fn_w, qweb, wweb, "Hàn bụng cột vào bản đế", "wweb")):
            fr = math.hypot(fn, fv)
            add(key, "Hàn cột – bản đế", lab, "kN/m", "AISC Eq. J2-4 (phương pháp đàn hồi)", cap, fr, nm,
                lambda fn=fn, fr=fr, cap=cap, wsz=wsz: [
                    f"Chu vi hàn: cánh Lf = {f1(Lf)} mm, bụng Lw = 2·hw = {f1(Lw)} mm, tổng L = {f1(Lt)} mm;  I33 = {f1(I33 / 1e6)}·10⁶ mm³, I22 = {f1(I22 / 1e6)}·10⁶ mm³",
                    f"Lực dọc đưa vào hàn = {f2(kN(Nw))} kN" + ("  (nén truyền bằng tì ép — finished to bear)" if opt.get("bear", True) else ""),
                    f"fn = N/L + M33·c/I33 + M22·c/I22 = {f1(fn)} N/mm;  fv = Vu/L = {f1(fv)} N/mm;  fr = √(fn² + fv²) = {f1(fr)} N/mm",
                    f"φRn = 0.75·0.6·FEXX·0.707·w = 0.75·0.6·{weldF:g}·0.707·{wsz:g} = {f1(cap)} N/mm"], (tag,))

        demands.append(dict(name=nm, N=kN(Nt), V2=kN(V2), V3=kN(V3), M33=kNm(M33), M22=kNm(M22), Pc=kN(Pc),
                            case33=dirs.get("33", {}).get("case", "—"), case22=dirs.get("22", {}).get("case", "—"),
                            Y33=dirs.get("33", {}).get("Y"), q33=(dirs.get("33", {}).get("q") or 0.0) / G["B"],
                            Tmax=kN(Tmax), Tsum=kN(Tsum), T=[kN(t) for t in T], sM33=1 if M33 >= 0 else -1, sM22=1 if M22 >= 0 else -1))

    # ---------- kiểm tra cấu tạo ----------
    geo = []
    def gchk(grp, name, val, mn=None, mx=None, ref="", unit="mm"):
        ok = (mn is None or val >= mn - 1e-6) and (mx is None or val <= mx + 1e-6)
        geo.append(dict(grp=grp, name=name, val=val, min=mn, max=mx, ref=ref, unit=unit, ok=ok))
    gchk("Bản đế", "Phần bản nhô theo phương N", (G["N"] - d) / 2, 0.0, None, "DG1 §2.10")
    gchk("Bản đế", "Phần bản nhô theo phương B", (G["B"] - bf) / 2, 0.0, None, "DG1 §2.10")
    if min(G["N"] - d, G["B"] - bf) / 2 < 25:
        W.append("Bản đế nhô ra ngoài cột < 25 mm: khó hàn và đặt neo (DG1 §2.10).")
    emin = edge_min(int(da), opt.get("sheared", True))
    gchk("Bu lông neo", "Khoảng cách mép bản ex (phương N)", float(an["ex"]), emin, None, "AISC J3.4")
    gchk("Bu lông neo", "Khoảng cách mép bản ey (phương B)", float(an["ey"]), emin, None, "AISC J3.4")
    if G["nx"] > 1: gchk("Bu lông neo", "Bước neo phương N", 2 * G["ax"] / (G["nx"] - 1), 4 * da, None, "ACI 318-11 D.8.1")
    if G["ny"] > 1: gchk("Bu lông neo", "Bước neo phương B", 2 * G["ay"] / (G["ny"] - 1), 4 * da, None, "ACI 318-11 D.8.1")
    clr = min(a["clear"] for a in G["anchors"])
    wmin = max(float(an.get("washer") or 0), anchor_hole(da)) / 2 + max(wfl, wweb)
    gchk("Bu lông neo", "Khoảng hở tâm neo – mặt thép cột", clr, wmin, None, "DG1 §2.10 (đặt long đen + hàn)")
    wsz, wt = washer_min(da)
    gchk("Bu lông neo", "Cạnh long đen tấm", float(an.get("washer") or 0), wsz, None, "DG1 Table 2.3")
    gchk("Bu lông neo", "Bề dày long đen tấm", float(an.get("washerT") or 0), wt, None, "DG1 Table 2.3")
    camin = min(a["ca"] for a in G["anchors"])
    if an.get("torqued"):
        gchk("Bê tông", "Khoảng cách neo tới mép bệ", camin, 6 * da, None, "ACI 318-11 D.8.2 (neo được siết)")
    else:
        gchk("Bê tông", "Khoảng cách neo tới mép bệ", camin, 50 + head_sz / 2, None, "ACI 318-11 D.8.2, 7.7 (lớp bảo vệ 50 mm)")
    gchk("Bê tông", "Chiều sâu chôn hef ≤ h bệ − 50", hef, None, G["ha"] - 50, "ACI 318-11 D.8.5")
    gchk("Bê tông", "Bệ nhô ra ngoài bản đế", min(G["N2"] - G["N"], G["B2"] - G["B"]) / 2, 0.0, None, "AISC J8")
    gchk("Hàn", "Hàn góc cánh cột ≥ min", wfl, weld_min(min(tf, tp)), None, "Table J2.4")
    gchk("Hàn", "Hàn góc bụng cột ≥ min", wweb, weld_min(min(tw, tp)), None, "Table J2.4")
    if mode == "lug":
        lg = inp["lug"]
        gchk("Bản chắn cắt", "Chiều cao chôn H − vữa", float(lg["H"]) - G["grout"], 50.0, None, "DG1 §3.5.3")
        gchk("Bản chắn cắt", "Hàn bản chắn ≥ min", float(lg["w"]), weld_min(min(float(lg["tl"]), tp)), None, "Table J2.4")
        W.append("Bản chắn cắt: chưa xét phá vỡ bê tông về phía mép bệ do bản chắn (ACI 349-06 D.11.2) — kiểm tra riêng nếu bệ hẹp.")
    if any(a["zone"] == "clash" for a in G["anchors"]):
        W.append("Có neo trùng vị trí cánh cột — đổi ex / ey hoặc số neo.")
    if reinf and opt.get("aci", True):
        W.append("Có cốt thép neo: kiểm tra chiều dài neo của cốt thép về hai phía mặt phá hoại (ACI 318-11 D.5.2.9, D.6.2.9) — ngoài phạm vi tool.")
    if not opt.get("aci", True):
        W.append("Chưa kiểm tra neo trong bê tông theo ACI 318 App. D (tắt tuỳ chọn).")
    if mode == "friction" and any(dm["Pc"] <= 0 for dm in demands):
        W.append("Có tổ hợp nhổ (N ≥ 0): ma sát bằng 0 — chọn neo hoặc bản chắn cắt để truyền lực cắt.")

    lst = [checks[i] for i in order]
    gov = None
    for c in lst:
        if not c["info"] and (gov is None or c["ratio"] > gov["ratio"]):
            gov = c
    return dict(G=G, checks=lst, geo=geo, demands=demands, gov=gov, W=W, geoFail=sum(1 for x in geo if not x["ok"]), weldF=weldF,
                bolt=dict(db=int(da), grade=am["name"]))


# ─────────────────────────── Tự chọn tp / neo ───────────────────────────
def auto_design(inp: dict, dias=tuple(ANCHOR_DIAS), tps=tuple(BP_TP), progress: Optional[Callable] = None):
    """Chọn tp nhỏ nhất đạt các kiểm tra bản đế, rồi đường kính neo nhỏ nhất đạt các kiểm tra neo (và cấu tạo neo).
    Trả về dict(tp, d, ratio[, fail]) hoặc None nếu không tính được."""
    def run(tp, d):
        t = copy.deepcopy(inp); t["plate"]["tp"] = tp; t["anchor"]["d"] = d
        try:
            return compute(t)
        except Exception:  # noqa: BLE001
            return None
    pick = lambda r, pre: max((c["ratio"] for c in r["checks"] if c["id"].startswith(pre)), default=0.0)
    d0 = int(inp["anchor"]["d"])
    best_tp = None
    for tp in tps:
        r = run(tp, d0)
        if r is None: continue
        mx = pick(r, ("bp_comp", "bp_ten"))
        if best_tp is None or mx < best_tp[1]: best_tp = (tp, mx)
        if mx <= 1.0: best_tp = (tp, mx); break
        if progress: progress(tp)
    if best_tp is None: return None
    tp = best_tp[0]
    best_d = None
    for d in dias:
        r = run(tp, d)
        if r is None: continue
        mx = pick(r, ("anc_", "aci_"))
        gfail = [g for g in r["geo"] if not g["ok"] and g["grp"] == "Bu lông neo" and "long đen" not in g["name"]]
        if best_d is None or mx < best_d[1]: best_d = (d, mx)
        if mx <= 1.0 and not gfail: best_d = (d, mx); break
    if best_d is None: return None
    res = dict(tp=tp, d=best_d[0], ratio=max(best_tp[1], best_d[1]))
    if res["ratio"] > 1.0: res["fail"] = True
    return res
