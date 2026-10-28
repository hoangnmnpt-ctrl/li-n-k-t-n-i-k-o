"""
base_engine.py — Lõi tính CHÂN CỘT bản đế + bu lông neo (Column base — CB), tương đương RAM Connection "Base plate"
================================================================================================================
AISC 360-10/16 (LRFD / ASD) J8, J3, J2 + AISC Design Guide 1, 2nd ed. (2006) + ACI 318-08/11 Appendix D, ACI 318-14 Ch. 17
(neo trong bê tông) + ACI 349-06 D.4.6 (bản chắn cắt).

Các mục như RAM Connection:
  • Analysis axis: Major (M33, V2) · Minor (M22, V3) · Both axes (từng phương độc lập, lực neo góc cộng) ·
    Biaxial (mặt phẳng biến dạng của bản cứng, giải số đồng thời hai mô men — phân bố ép tuyến tính).
  • Pressure distribution: Uniform (DG1 §3.3, khối ứng suất đều fp,max) · Triangular (tam giác / hình thang, fp ≤ fp,max).
    Consider strain compatibility (với Triangular): tương thích biến dạng bê tông – neo (Ec, Es, bản cứng) → giải số.
  • Bearing stress calculation: Complete area (DG1) · Effective area (diện tích hiệu quả quanh thép cột, c = tp·√(φFy/(2fp,max))).
  • Include friction: lực cắt neo / bản chắn giảm đi φ·μ·Pu.  Seismic provisions: ×0.75 sức kháng neo (ACI D.3.3).
  • Steel code LRFD / ASD (ASD: Rn/Ω = φRn/1.5; với bê tông dùng cùng hệ số chuyển đổi 1.5).
  • Lệch tâm cột trên bản (ox, oz), vị trí bản trên gối (px, pz), Override A2/A1, chỉ hàn mặt ngoài cánh, neo Headed / Hooked,
    đầu neo Hexagonal / Heavy hex / Square / Plate, Brittle steel, neo hàn vào bản đế, cốt thép neo Primary / Supplementary.
  • Tối ưu (Optimization criteria): tp, N, B (theo khoảng nhô min–max và bước), đường kính neo, hef tối thiểu, giữ vị trí neo.

Quy ước dấu: N > 0 kéo (nhổ) · V2 theo phương N (x) · V3 theo phương B (z) · M33 > 0 → mép +x chịu nén ·
M22 > 0 → mép +z chịu nén. Nội lực tại tâm cột. Đơn vị nội bộ: N, mm, MPa. Nhập / xuất: kN, kN·m.
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
ES = 200000.0

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
# bê tông: f'c (MPa) — C x-60 theo RAM (f'c x ksi, thép 60 ksi), B (TCVN, f'c ≈ 0.8·B), EN; Custom: nhập f'c
CONC_MATS = {"C 3-60": 20.7, "C 4-60": 27.6, "C 5-60": 34.5, "B20": 16.0, "B25": 20.0, "B30": 24.0, "B35": 28.0,
             "C25/30": 25.0, "C30/37": 30.0, "C35/45": 35.0}
STEEL_CODES = ["AISC 2010 LRFD", "AISC 2010 ASD", "AISC 2016 LRFD", "AISC 2016 ASD"]
CONC_CODES = ["ACI 318-08", "ACI 318-11", "ACI 318-14"]
HEADS = {"hex": "Hexagonal", "square": "Square"}
LAYOUTS = {"longitudinal": "Longitudinal position", "transversal": "Transversal position"}
MU = 0.55                                                     # ma sát thép – vữa (DG1 §3.5.1)
FY_REINF = 420.0                                              # cốt thép neo Grade 60
AXES = {"major": "Major axis", "minor": "Minor axis", "both": "Both axes", "biaxial": "Biaxial"}
BP_TP = [12, 14, 16, 18, 20, 22, 25, 28, 30, 32, 35, 36, 40, 45, 50, 55, 60]
SHEAR_MODE = {"anchors": "Bu lông neo", "lug": "Bản chắn cắt"}
DIR_NAME = {"33": "phương N (M33)", "22": "phương B (M22)", "bi": "hai phương (biaxial)"}
# ACI 318-14 Ch. 17 ↔ ACI 318-08/11 App. D
D2_17 = {"D.3.3": "17.2.3", "D.5.1": "17.4.1", "D.5.2": "17.4.2", "D.5.2.3": "17.4.2.3", "D.5.2.9": "17.4.2.9", "D.5.3": "17.4.3",
         "D.5.4": "17.4.4", "D.6.1": "17.5.1", "D.6.1.3": "17.5.1.3", "D.6.2": "17.5.2", "D.6.2.4": "17.5.2.4", "D.6.2.9": "17.5.2.9",
         "D.6.3": "17.5.3", "D.7": "17.6", "D.8.1": "17.7.1", "D.8.2": "17.7.2", "D.8.5": "17.7.5"}


def anchor_hole(d): return HOLE_DG1.get(int(d), d + 20)
def washer_min(d): return WASHER_DG1.get(int(d), (2.5 * d, d / 3))
def anchor_ase(d): return math.pi / 4 * (d - 0.9382 * PITCH.get(int(d), 0.125 * d)) ** 2


def anchor_mat(grade):
    fy, fu = ANCHOR_GRADES.get(grade, ANCHOR_GRADES["5.6"])
    return dict(name=grade if grade in ANCHOR_GRADES else "5.6", Fy=float(fy), Fu=float(fu))


def shear_mode(inp: dict) -> str:
    return "lug" if inp.get("lug", {}).get("on") else "anchors"


# ─────────────────────────── chuẩn hoá input ───────────────────────────
def normalize(inp: dict) -> dict:
    """Đồng bộ trường kiểu RAM → trường engine (sửa tại chỗ, trả về inp); chuyển dữ liệu kiểu cũ."""
    wd = inp.setdefault("weld", {})
    if "D" in wd:                                             # RAM: một cỡ hàn D cho cột
        for k in ("fl", "web"):
            wd.setdefault(k, {})["D"] = wd["D"]
    for k in ("fl", "web"):
        if k in wd and "D" in wd[k]:
            wd[k]["w"] = float(wd[k]["D"]) * IN16
    lug = inp.setdefault("lug", {})
    sh = inp.setdefault("shear", {})
    if "mode" in sh:                                          # dữ liệu cũ: shear.mode
        m = sh.pop("mode")
        if m == "lug": lug["on"] = True
        if m == "friction": inp.setdefault("gen", {})["friction"] = True
    sh["by"] = "lug" if lug.get("on") else "anchors"          # chỉ để hiển thị
    if "D" in lug:
        lug["w"] = float(lug["D"]) * IN16
    ped = inp["ped"]
    if "reinf" in ped and not isinstance(ped["reinf"], dict):  # dữ liệu cũ: ped.reinf, ped.AsN …
        on = bool(ped.pop("reinf"))
        r = inp.setdefault("reinf", {})
        r.update(type="primary", T=on, V=on)
        for k in ("fyr", "AsN", "AsV"):
            if k in ped: r[k] = ped.pop(k)
    if "cracked" in ped:
        inp["anchor"]["cracked"] = ped.pop("cracked")
    if ped.get("mat") not in CONC_MATS:
        ped["mat"] = min(CONC_MATS, key=lambda k: abs(CONC_MATS[k] - float(ped.get("fc") or 25)))
    ped["fc"] = CONC_MATS[ped["mat"]]
    an = inp["anchor"]
    if "shearAll" in an:
        an["welded"] = an.pop("shearAll") or an.get("welded", False)
    if an.get("head") not in HEADS: an["head"] = "hex"
    if an.get("layout") not in LAYOUTS: an["layout"] = "longitudinal"
    for k in ("d", "nr", "npr"):
        if k in an: an[k] = int(float(an[k]))
    return inp


# ─────────────────────────── hình học ───────────────────────────
def anchor_layout(an: dict, N: float, B: float) -> list[tuple[float, float]]:
    """Toạ độ neo (x theo N, y theo B) so với tâm bản đế. RAM: Anchor position Longitudinal / Transversal,
    Rows number per side (nr, bước sr), Anchors per row (npr, rải đều giữa hai khoảng cách mép)."""
    ex, ey = float(an["ex"]), float(an["ey"])
    ax, ay = N / 2 - ex, B / 2 - ey
    if ax <= 0 or ay <= 0:
        raise ValueError("Khoảng cách mép neo ex, ey phải nhỏ hơn N/2, B/2.")
    lay = an.get("layout", "longitudinal")
    spread = lambda a, n: [0.0] if n <= 1 else [-a + 2 * a * i / (n - 1) for i in range(n)]
    nr, npr, sr = max(int(an.get("nr", 1)), 1), max(int(an.get("npr", 2)), 1), float(an.get("sr", 80))
    rows = [(ax if lay == "longitudinal" else ay) - k * sr for k in range(nr)]
    if rows[-1] <= 0:
        raise ValueError("Hàng neo trong vượt quá tâm bản — giảm số hàng hoặc khoảng cách hàng.")
    pts = []
    for r in rows:
        for s in (1, -1):
            if lay == "longitudinal":
                pts += [(s * r, y) for y in spread(ay, npr)]
            else:
                pts += [(x, s * r) for x in spread(ax, npr)]
    return pts


def build_geometry(inp: dict) -> dict:
    W: list[str] = []
    c = member_at_joint(dict(inp["col"], topIsOuter=True), "cột")
    pl, ped, an = inp["plate"], inp["ped"], inp["anchor"]
    N, B, tp = float(pl["N"]), float(pl["B"]), float(pl["tp"])
    N2, B2 = float(ped["N2"]), float(ped["B2"])
    if N <= 0 or B <= 0 or tp <= 0:
        raise ValueError("Kích thước bản đế N, B, tp phải > 0.")
    ox, oz = float(inp["col"].get("ox") or 0), float(inp["col"].get("oz") or 0)
    px, pz = (float(pl.get("px") or 0), float(pl.get("pz") or 0)) if pl.get("pos") == "custom" else (0.0, 0.0)
    if N2 / 2 < N / 2 + abs(px) - 1e-6 or B2 / 2 < B / 2 + abs(pz) - 1e-6:
        raise ValueError(f"Bản đế {N:g} × {B:g} (lệch {px:g}; {pz:g}) nằm ngoài gối {N2:g} × {B2:g}.")
    pts = anchor_layout(an, N, B)
    d, bf = c["d"], max(c["bfE"], c["bfI"])
    tf, tw = max(c["tfE"], c["tfI"]), c["tw"]
    if abs(ox) + d / 2 > N / 2 + 1e-6 or abs(oz) + bf / 2 > B / 2 + 1e-6:
        W.append("Cột (kể cả lệch tâm) vượt ra ngoài bản đế.")
    anchors = []
    for x, y in pts:
        a = dict(x=x, y=y, xs=x + px, ys=y + pz)              # xs, ys: toạ độ trên gối
        a["cx"], a["cy"] = N2 / 2 - abs(a["xs"]), B2 / 2 - abs(a["ys"])
        a["ca"] = min(a["cx"], a["cy"])
        ax_, ay_ = abs(x - ox), abs(y - oz)
        if ax_ >= d / 2:                                     # ngoài cánh cột (DG1: tay đòn tới tâm cánh)
            a["zone"], a["arm"], a["clear"] = "out", ax_ - d / 2 + tf / 2, ax_ - d / 2
        elif ay_ >= bf / 2:                                  # cạnh mép cánh, trong chiều cao tiết diện
            a["zone"], a["arm"], a["clear"] = "tip", ay_ - bf / 2, ay_ - bf / 2
        elif ax_ <= d / 2 - tf:                              # giữa hai cánh: tay đòn tới bụng / cánh gần nhất (45°)
            a["zone"] = "in"
            a["arm"] = a["clear"] = min(ay_ - tw / 2, d / 2 - tf - ax_)
        else:
            a["zone"], a["arm"], a["clear"] = "clash", 0.0, -1.0
        anchors.append(a)
    m = (N / 2 + abs(ox)) - 0.95 * d / 2
    n = (B / 2 + abs(oz)) - 0.80 * bf / 2
    if pl.get("overA2"):
        sq = min(max(math.sqrt(max(float(pl.get("A2A1") or 1.0), 1.0)), 1.0), 2.0)
    else:
        kx = (N2 / 2 - abs(px)) / (N / 2)
        kz = (B2 / 2 - abs(pz)) / (B / 2)
        sq = min(max(min(kx, kz), 1.0), 2.0)
    grout = float(ped.get("grout") or 0) if ped.get("groutOn", True) else 0.0
    return dict(W=W, col=c, d=d, bf=bf, tf=tf, N=N, B=B, tp=tp, N2=N2, B2=B2, ha=float(ped["h"]), grout=grout,
                ox=ox, oz=oz, px=px, pz=pz, ax=N / 2 - float(an["ex"]), ay=B / 2 - float(an["ey"]),
                anchors=anchors, m=m, n=n, sqA=sq, A1=N * B, A2=N * B * sq * sq,
                nx=len({round(a["x"], 3) for a in anchors}), ny=len({round(a["y"], 3) for a in anchors}))


# ─────────────────────────── phân bố ép một phương ───────────────────────────
def dg1_direction(Pc: float, M: float, L: float, Wd: float, f: float, fpmax: float) -> dict:
    """Uniform (DG1 §3.3). Pc: nén (> 0), M ≥ 0, bản dài L, rộng Wd, nhóm neo kéo cách tâm f.
    Trả về case ∈ axial | small | large | nosol | tension; Y, q (N/mm), Tu (tổng lực kéo nhóm neo, N)."""
    qmax = fpmax * Wd
    if M < 1e-6 and Pc > 0:
        return dict(case="axial", e=0.0, Y=L, q=Pc / L, qmax=qmax, Tu=0.0, f=f, prof="uniform")
    if Pc > 0:
        e = M / Pc
        ecrit = L / 2 - Pc / (2 * qmax)
        if e <= ecrit:
            Y = L - 2 * e
            return dict(case="small", e=e, ecrit=ecrit, Y=Y, q=Pc / Y, qmax=qmax, Tu=0.0, f=f, prof="uniform")
    else:
        e, ecrit = math.inf, L / 2 - Pc / (2 * qmax)
    Kf = M + Pc * f                                          # mô men quanh nhóm neo kéo
    if Kf <= 0:
        return dict(case="tension", e=e, Y=0.0, q=0.0, qmax=qmax, Tu=None, f=f, prof="uniform")
    a = f + L / 2
    disc = a * a - 2 * Kf / qmax
    qreq = 2 * Kf / (a * a)
    if disc < 0:
        return dict(case="nosol", e=e, ecrit=ecrit, Y=None, q=qmax, qmax=qmax, qreq=qreq, Tu=None, f=f, prof="uniform")
    Y = a - math.sqrt(disc)
    return dict(case="large", e=e, ecrit=ecrit, Y=Y, q=qmax, qmax=qmax, qreq=qreq, Tu=qmax * Y - Pc, f=f, prof="uniform")


def tri_direction(Pc: float, M: float, L: float, Wd: float, f: float, fpmax: float) -> dict:
    """Triangular (không tương thích biến dạng): hình thang (e ≤ L/6) → tam giác không kéo neo → tam giác fp = fp,max + neo kéo.
    q: áp lực mép (N/mm); Y: chiều dài tới điểm áp lực bằng 0 (hình thang: Y > L)."""
    qmax = fpmax * Wd
    if Pc > 0:
        e = M / Pc
        if e <= L / 6:
            q1 = Pc / L + 6 * M / L ** 2
            q2 = Pc / L - 6 * M / L ** 2
            Y = L * q1 / (q1 - q2) if q1 - q2 > 1e-12 else math.inf
            return dict(case="axial" if M < 1e-6 else "small", e=e, Y=Y, q=q1, qmax=qmax, Tu=0.0, f=f, prof="linear",
                        txt=f"e ≤ L/6: hình thang, fp,1 = P/A + 6M/(B·L²) = {q1 / Wd:.3f} MPa, fp,2 = {q2 / Wd:.3f} MPa")
        Y = 3 * (L / 2 - e)
        q = 2 * Pc / Y if Y > 0 else math.inf
        if Y > 0 and q <= qmax:
            return dict(case="small", e=e, Y=Y, q=q, qmax=qmax, Tu=0.0, f=f, prof="linear",
                        txt=f"L/6 < e: tam giác không kéo neo, Y = 3(L/2 − e) = {Y:.1f} mm, fp = 2P/(B·Y) = {q / Wd:.3f} MPa")
    else:
        e = math.inf
    Kf = M + Pc * f
    if Kf <= 0:
        return dict(case="tension", e=e, Y=0.0, q=0.0, qmax=qmax, Tu=None, f=f, prof="linear")
    a = f + L / 2
    Ym = min(1.5 * a, L)
    Kmax = qmax * Ym / 2 * (a - Ym / 3)
    A_, B_, C_ = qmax / 6, -qmax / 2 * a, Kf                  # (qmax·Y/2)(a − Y/3) = Kf
    disc = B_ * B_ - 4 * A_ * C_
    if disc < 0 or Kf > Kmax:
        return dict(case="nosol", e=e, Y=None, q=qmax, qmax=qmax, Kreq=Kf, Kmax=Kmax, Tu=None, f=f, prof="linear")
    Y = (-B_ - math.sqrt(disc)) / (2 * A_)
    return dict(case="large", e=e, Y=Y, q=qmax, qmax=qmax, Kreq=Kf, Kmax=Kmax, Tu=qmax * Y / 2 - Pc, f=f, prof="linear",
                txt=f"Tam giác fp = fp,max: (fp,max·B·Y/2)(f + L/2 − Y/3) = Mu + Pu·f → Y = {Y:.1f} mm")


def _solve(Mx, b):
    n = len(b)
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(Mx[r][i]))
        if abs(Mx[p][i]) < 1e-300: raise ZeroDivisionError
        Mx[i], Mx[p] = Mx[p], Mx[i]; b[i], b[p] = b[p], b[i]
        for r in range(i + 1, n):
            f = Mx[r][i] / Mx[i][i]
            for c in range(i, n): Mx[r][c] -= f * Mx[i][c]
            b[r] -= f * b[i]
    xs = [0.0] * n
    for i in range(n - 1, -1, -1):
        xs[i] = (b[i] - sum(Mx[i][c] * xs[c] for c in range(i + 1, n))) / Mx[i][i]
    return xs


def solve_elastic(G, pts, Ab, Ec, Pc, Mx, My, use_x=True, use_y=True, nc=40):
    """Bản cứng, mặt phẳng biến dạng ε = e0 + kx·x + ky·y (nén +): bê tông chỉ chịu nén σ = Ec·ε, neo chỉ chịu kéo σ = Es·ε.
    Giải cân bằng N, Mx, My bằng Newton. Trả về dict(e0, kx, ky, fp (MPa, áp lực lớn nhất), T (N/neo), ok)."""
    N, B = G["N"], G["B"]
    dx, dy = N / nc, B / nc
    cells = [(-N / 2 + (i + 0.5) * dx, -B / 2 + (j + 0.5) * dy) for i in range(nc) for j in range(nc)]
    A = dx * dy
    ka = ES * Ab
    target = (Pc, Mx if use_x else 0.0, My if use_y else 0.0)
    scale = max(abs(Pc), abs(Mx) / N, abs(My) / B, 1.0)
    x = [Pc / (Ec * N * B) if Pc > 0 else Pc / (ka * max(len(pts), 1)) - 1e-6, 0.0, 0.0]

    def resid(v):
        e0, kx, ky = v
        R = [-target[0], -target[1], -target[2]]
        J = [[0.0] * 3 for _ in range(3)]
        for (cx, cy), k in [(c, Ec * A) for c in cells] + [(p, ka) for p in pts]:
            e = e0 + kx * cx + ky * cy
            if (k == ka and e < 0) or (k != ka and e > 0):
                w = (1.0, cx, cy)
                for i in range(3):
                    R[i] += k * e * w[i]
                    for j in range(3): J[i][j] += k * w[i] * w[j]
        return R, J

    def norm(R): return math.sqrt((R[0] / scale) ** 2 + (R[1] / (scale * N)) ** 2 + (R[2] / (scale * B)) ** 2)

    act = [0] + ([1] if use_x else []) + ([2] if use_y else [])
    R, J = resid(x)
    ok = False
    for _ in range(200):
        r0 = norm(R)
        if r0 < 1e-7:
            ok = True; break
        Js = [[J[i][j] for j in act] for i in act]
        tr = sum(Js[i][i] for i in range(len(act))) or 1.0
        for i in range(len(act)): Js[i][i] += 1e-12 * tr
        try:
            dv = _solve(Js, [-R[i] for i in act])
        except ZeroDivisionError:
            break
        step = 1.0
        while True:
            xn = list(x)
            for i, k in enumerate(act): xn[k] = x[k] + step * dv[i]
            Rn, Jn = resid(xn)
            if norm(Rn) < r0 or step < 1e-6: break
            step /= 2
        x, R, J = xn, Rn, Jn
    e0, kx, ky = x
    corners = [(sx * N / 2, sy * B / 2) for sx in (-1, 1) for sy in (-1, 1)]
    fp = max(0.0, max(Ec * (e0 + kx * a + ky * b) for a, b in corners))
    T = [max(-ka * (e0 + kx * a + ky * b), 0.0) for a, b in pts]
    return dict(e0=e0, kx=kx, ky=ky, fp=fp, T=T, ok=ok, Ec=Ec,
                bearing=any(Ec * (e0 + kx * a + ky * b) > 1e-9 for a, b in corners))


def strip_moment(fp, Y, l, prof):
    """Mô men uốn bản (N·mm/mm) tại tiết diện cách mép ép l: uniform (khối dài Y) hoặc tuyến tính (giảm từ fp về 0 trên Y)."""
    if fp <= 0 or l <= 0: return 0.0
    if prof == "uniform":
        return fp * l * l / 2 if Y >= l else fp * Y * (l - Y / 2)
    if Y is None or math.isinf(Y) or Y >= l:
        Yv = Y if Y and not math.isinf(Y) else 1e18
        return fp * (l * l / 2 - l ** 3 / (6 * Yv))
    return fp * Y / 2 * (l - Y / 3)


def eff_area(G, c, s0=-1e18, s1=1e18, axis=0, nc=120):
    """Diện tích hiệu quả quanh thép cột (cách mặt thép ≤ c), cắt bởi bản đế và dải [s0, s1] theo trục axis."""
    col, d, ox, oz = G["col"], G["d"], G["ox"], G["oz"]
    rects = [(ox + d / 2 - col["tfE"] - c, ox + d / 2 + c, oz - col["bfE"] / 2 - c, oz + col["bfE"] / 2 + c),
             (ox - d / 2 - c, ox - d / 2 + col["tfI"] + c, oz - col["bfI"] / 2 - c, oz + col["bfI"] / 2 + c),
             (ox - d / 2, ox + d / 2, oz - col["tw"] / 2 - c, oz + col["tw"] / 2 + c)]
    N, B = G["N"], G["B"]
    dx, dy = N / nc, B / nc
    A = 0.0
    for i in range(nc):
        xx = -N / 2 + (i + 0.5) * dx
        for j in range(nc):
            yy = -B / 2 + (j + 0.5) * dy
            s = xx if axis == 0 else yy
            if s0 <= s <= s1 and any(r[0] <= xx <= r[1] and r[2] <= yy <= r[3] for r in rects):
                A += dx * dy
    return A


# ─────────────────────────── ACI 318 (App. D / Ch. 17) ───────────────────────────
def _proj_area(pts, r, X, Y):
    """Diện tích hình chiếu: hộp bao các neo mở rộng r mỗi phía, cắt bởi biên gối [−X, X] × [−Y, Y]."""
    x0 = max(min(p[0] for p in pts) - r, -X); x1 = min(max(p[0] for p in pts) + r, X)
    y0 = max(min(p[1] for p in pts) - r, -Y); y1 = min(max(p[1] for p in pts) + r, Y)
    return max(x1 - x0, 0) * max(y1 - y0, 0)


def aci_breakout_tension(G, pts, forces, hef, fc, lam, cracked, headed=True):
    """Phá vỡ bê tông khi kéo của nhóm neo (D.5.2). pts: [(x, y)] trên gối, forces: lực kéo từng neo (N). Chưa nhân φ."""
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
    if headed and 280 <= h <= 635:
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
                Ncbg=Ncbg, ex=ex, ey=ey, n=len(pts))


def aci_breakout_shear(G, an_pts, axis, sign, hef, da, fc, lam, cracked):
    """Phá vỡ bê tông khi cắt về phía mép (D.6.2) — hàng neo trước chịu toàn bộ lực cắt (thiên an toàn). Chưa nhân φ.
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
                Vcbg=Vcbg, n=len(front))


def tension_group(coords, s):
    """Nhóm neo kéo theo một trục: phía s (±1), |toạ độ| ≥ 0.5·max. Trả về (chỉ số, f = khoảng cách trung bình tới tâm)."""
    vals = [s * c for c in coords]
    mx = max(vals) if vals else 0.0
    if mx <= 1e-9: return [], 0.0
    grp = [i for i, v in enumerate(vals) if v >= 0.5 * mx - 1e-9]
    return grp, sum(vals[i] for i in grp) / len(grp)


# ─────────────────────────── tính chính ───────────────────────────
def compute(inp: dict) -> dict:
    normalize(inp)
    G = build_geometry(inp)
    W = G["W"]
    gen = inp.get("gen", {})
    pl, ped, an, rf = inp["plate"], inp["ped"], inp["anchor"], inp.get("reinf", {})
    col = G["col"]
    fast = bool(inp.get("_fast"))
    pm = material(pl["mat"])
    Fy = pm["Fy"]
    fc, lam = float(ped["fc"]), 1.0
    cracked = bool(an.get("cracked", True))
    code = gen.get("designCode", "AISC 2010 LRFD")
    asd = "ASD" in code
    kA = 1 / 1.5 if asd else 1.0                              # ASD: Rn/Ω = φRn/1.5
    ccode = gen.get("concCode", "ACI 318-11")
    aref = lambda sec: f"{ccode} {D2_17.get(sec, sec) if ccode.endswith('14') else sec}"
    seismic = bool(gen.get("seismic"))
    sC = 0.75 if seismic else 1.0                             # D.3.3: chế độ phá hoại bê tông
    sS = 0.75 if seismic and ccode.endswith("08") else 1.0     # ACI 318-08: cả chế độ phá hoại thép
    tp = G["tp"]
    am = anchor_mat(an["grade"])
    da = float(an["d"])
    Ab = math.pi * da * da / 4
    Ase = anchor_ase(da)
    v16 = "2016" in code
    Fnt = 0.75 * am["Fu"]
    Fnv = (0.45 if v16 else 0.40) * am["Fu"]                # ren nằm trong mặt cắt (N)
    futa = min(am["Fu"], 1.9 * am["Fy"], 860.0)
    hef = float(an["hef"])
    headed = an.get("type", "headed") != "hooked"
    head = an.get("head", "heavy")
    if head == "square":
        F = 1.5 * da; Abrg = F * F - Ab; head_sz = 1.414 * F
    else:
        F = 1.5 * da                                         # cạnh – cạnh đầu lục giác
        Abrg = 0.866 * F * F - Ab; head_sz = 1.155 * F
    if not headed:
        head_sz = da
    weldF = ELECTRODES.get(inp["weld"]["electrode"], 482.6)
    fpmax = kA * 0.65 * 0.85 * fc * G["sqA"]
    Ec = 4700 * math.sqrt(fc)
    pts = [(a["x"], a["y"]) for a in G["anchors"]]
    spts = [(a["xs"], a["ys"]) for a in G["anchors"]]
    nA = len(pts)
    G.update(Fy=Fy, fpmax=fpmax, Ab=Ab, Ase=Ase, Abrg=Abrg, head=head_sz, hole=anchor_hole(da), washer=washer_min(da), am=am, Fnt=Fnt, Fnv=Fnv, Ec=Ec)
    mode = shear_mode(inp)
    axis = gen.get("axis", "both")
    press = gen.get("pressure", "uniform")
    compat = bool(gen.get("compat")) and press == "triangular"
    welded = bool(an.get("welded"))
    brittle = bool(an.get("brittle"))
    phi_st, phi_sv = (0.65, 0.60) if brittle else (0.75, 0.65)
    rtype = rf.get("type", "primary")
    primT, primV = rtype == "primary" and bool(rf.get("T")), rtype == "primary" and bool(rf.get("V"))
    phi_cbT = 0.75 if rtype == "supplementary" and rf.get("T") else 0.70
    phi_cbV = 0.75 if rtype == "supplementary" and rf.get("V") else 0.70
    fyr = FY_REINF
    asd_txt = ["ASD: khả năng cho phép = φRn/1.5 (= Rn/Ω)"] if asd else []

    checks: dict[str, dict] = {}
    order: list[str] = []

    def add(cid, grp, name, unit, ref, cap, dem, combo, detail, tags=(), info=False, scale=True):
        if scale and asd: cap = cap * kA
        ratio = abs(dem) / cap if cap and cap > 0 else (math.inf if abs(dem) > 0 or isnan(cap) else 0.0)
        if isnan(ratio): ratio = math.inf
        c = checks.get(cid)
        if c is None:
            c = checks[cid] = dict(id=cid, grp=grp, name=name, unit=unit, ref=ref, cap=cap, dem=dem, ratio=-1.0,
                                   combo=combo, detail=[], tags=list(tags), info=info)
            order.append(cid)
        if ratio > c["ratio"]:
            dl = detail() if callable(detail) else list(detail or [])
            c.update(cap=cap, dem=dem, ratio=ratio, combo=combo, detail=dl + (asd_txt if scale and asd else []))
        return ratio

    m_, n_ = G["m"], G["n"]
    Mcap = 0.9 * Fy * tp * tp / 4                           # φMn của bản trên đơn vị bề rộng (N·mm/mm)
    d, bf, tf, tw = G["d"], G["bf"], G["tf"], col["tw"]
    ox, oz = G["ox"], G["oz"]
    xs_ = [p[0] for p in pts]; ys_ = [p[1] for p in pts]
    sx2 = sum(v * v for v in xs_) or 1.0
    sy2 = sum(v * v for v in ys_) or 1.0

    # chu vi hàn cột – bản đế (đường, bề dày họng đơn vị)
    outer = bool(inp["weld"].get("outerOnly"))
    hw = d - col["tfE"] - col["tfI"]
    if outer:
        Lf, Lw = col["bfE"] + col["bfI"], 0.0
        I33 = (col["bfE"] + col["bfI"]) * (d / 2) ** 2
        I22 = (col["bfE"] ** 3 + col["bfI"] ** 3) / 12
    else:
        Lf = (2 * col["bfE"] - tw) + (2 * col["bfI"] - tw)
        Lw = 2 * hw
        I33 = sum(L * x * x for L, x in ((col["bfE"], d / 2), (col["bfE"] - tw, d / 2 - col["tfE"]),
                                         (col["bfI"], d / 2), (col["bfI"] - tw, d / 2 - col["tfI"]))) + 2 * hw ** 3 / 12
        I22 = sum((b ** 3 - (tw ** 3 if inner else 0)) / 12 for b, inner in ((col["bfE"], False), (col["bfE"], True),
                                                                               (col["bfI"], False), (col["bfI"], True))) + 2 * hw * (tw / 2) ** 2
    Lt = Lf + Lw
    G.update(Lf=Lf, Lw=Lw, Lt=Lt, I33=I33, I22=I22)
    wfl, wweb = float(inp["weld"]["fl"]["w"]), float(inp["weld"]["web"]["w"])
    qfl, qweb = 0.75 * 0.6 * weldF * 0.707 * wfl, 0.75 * 0.6 * weldF * 0.707 * wweb
    # Bearing stress calculation = Effective area: vùng cách mặt thép cột ≤ c
    eff = gen.get("bearCalc", "complete") == "effective"
    c_eff = tp * math.sqrt(0.9 * kA * Fy / (2 * fpmax)) if eff else 0.0
    if eff:
        G["c_eff"] = c_eff
        G["Aeff"] = eff_area(G, c_eff)

    demands = []
    for ci, cb in enumerate(inp.get("loads", [])):
        g = lambda key: float(cb.get(key) or 0.0)
        Nt, V2, V3, M33, M22 = g("N") * 1e3, g("V2") * 1e3, g("V3") * 1e3, g("M33") * 1e6, g("M22") * 1e6
        if axis == "major": V3 = M22 = 0.0
        if axis == "minor": V2 = M33 = 0.0
        nm = cb.get("name") or f"TH{ci + 1}"
        Pc = -Nt
        Mx, My = M33 + Pc * ox, M22 + Pc * oz                 # mô men quanh tâm bản đế
        Vr = math.hypot(V2, V3)
        T = [0.0] * nA
        dirs: dict = {}

        if axis == "biaxial":
            sol = solve_elastic(G, pts, Ab, Ec, Pc, Mx, My)
            if not sol["ok"]:
                W.append(f"{nm}: lời giải biaxial chưa hội tụ hoàn toàn — kiểm tra lại số liệu.")
            T = sol["T"]
            dirs["bi"] = dict(case="biaxial", sol=sol, fp=sol["fp"])
        else:
            cand = []
            if axis == "major" or (axis == "both" and (abs(Mx) > 1e-6 or (abs(My) <= 1e-6 and Pc > 0))):
                cand.append(("33", Mx, G["N"], G["B"], xs_, sx2))
            if axis == "minor" or (axis == "both" and abs(My) > 1e-6):
                cand.append(("22", My, G["B"], G["N"], ys_, sy2))
            for key, Mk, L, Wd, coords, s2 in cand:
                s = -1 if Mk >= 0 else 1                     # phía neo kéo (Mk > 0 nén mép +)
                grp, f = tension_group(coords, s)
                if not grp: grp, f = list(range(nA)), 0.0
                if compat:
                    sol = solve_elastic(G, pts, Ab, Ec, Pc, Mx, My, use_x=(key == "33"), use_y=(key == "22"))
                    k = sol["kx"] if key == "33" else sol["ky"]
                    r = dict(case="compat", sol=sol, fp=sol["fp"], prof="linear",
                             Y=(sol["fp"] / (Ec * abs(k)) if abs(k) > 1e-15 else math.inf), Tl=sol["T"], tension=not sol["bearing"])
                else:
                    r = (tri_direction if press == "triangular" else dg1_direction)(Pc, abs(Mk), L, Wd, f, fpmax)
                    r["fp"] = (r["q"] or 0.0) / Wd
                    Tl = [0.0] * nA
                    if r["case"] == "large":
                        for i in grp: Tl[i] = r["Tu"] / len(grp)
                    elif r["case"] == "tension":
                        for i, cc in enumerate(coords): Tl[i] = max(Nt / nA - Mk * cc / s2, 0.0)
                    r["Tl"] = Tl
                    r["tension"] = r["case"] == "tension"
                r.update(L=L, Wd=Wd, Mk=Mk, grp=grp, f=f)
                dirs[key] = r
            if not dirs:
                T = [max(Nt, 0.0) / nA] * nA
            else:
                for r in dirs.values():
                    for i in range(nA): T[i] += r["Tl"][i]
                if len(dirs) == 2:
                    if all(r["tension"] for r in dirs.values()):
                        T = [max(t - Nt / nA, 0.0) for t in T]
                    W.append(f"{nm}: mô men hai phương (Both axes) — kiểm tra ép mặt / bản đế độc lập từng phương, lực neo cộng tuyến tính.")
        Tmax = max(T) if T else 0.0
        Tsum = sum(T)

        # ---------- ép mặt bê tông + uốn bản phía ép ----------
        for key, r in dirs.items():
            dn = DIR_NAME[key]
            if key == "bi":
                sol = r["sol"]
                add("conc_bear_bi", "Bê tông (ép mặt)", "Ép mặt bê tông — hai phương (biaxial)", "MPa", "AISC J8 / DG1 Sec. 3.4 (elastic)",
                    fpmax, sol["fp"], nm, lambda sol=sol: [
                        f"Bản cứng, mặt phẳng biến dạng ε = e0 + kx·x + kz·z; bê tông Ec = 4700√f'c = {f1(Ec)} MPa (chỉ nén), neo Es = {ES:g} MPa (chỉ kéo)",
                        f"Pu = {f1(kN(Pc))} kN;  Mu,x = {f2(kNm(Mx))} kN·m;  Mu,z = {f2(kNm(My))} kN·m (quanh tâm bản)",
                        f"fp,max = 0.65·0.85·f'c·√(A2/A1){'/1.5' if asd else ''} = {f2(fpmax)} MPa",
                        f"Áp lực lớn nhất tại góc bản fp = {f2(sol['fp'])} MPa;  tổng lực kéo neo = {f2(kN(sum(sol['T'])))} kN",
                        "Analysis axis = Biaxial: phân bố tuyến tính (tương thích biến dạng)"], ("conc", "bp"), scale=False)
                Mb, best = 0.0, ""
                l = max(m_, n_)
                for k_, lab in ((sol["kx"], "phương N"), (sol["ky"], "phương B")):
                    Y = sol["fp"] / (Ec * abs(k_)) if abs(k_) > 1e-15 else math.inf
                    Mpl = strip_moment(sol["fp"], Y, l, "linear")
                    if Mpl >= Mb:
                        Mb, best = Mpl, f"Dải {lab}: fp = {f2(sol['fp'])} MPa giảm tuyến tính, Y = {'∞' if math.isinf(Y) else f1(Y)} mm, l = max(m; n) = {f1(l)} mm"
                add("bp_comp_bi", "Bản đế", "Uốn bản đế phía ép — hai phương", "kN·m/m", "DG1 Sec. 3.3 (linear distribution)", Mcap / 1e3, Mb / 1e3, nm,
                    lambda Mb=Mb, best=best: [f"m = {f1(m_)} mm;  n = {f1(n_)} mm", best,
                                              f"Mpl = {f2(Mb / 1e3)} kN·m/m;  φMn = 0.9·Fy·tp²/4 = {f2(Mcap / 1e3)} kN·m/m",
                                              f"tp,req = √(4Mpl/(0.9Fy)) = {f1(math.sqrt(4 * Mb / (0.9 * Fy)))} mm"], ("bp",))
                continue
            L, Wd, Mk = r["L"], r["Wd"], abs(r["Mk"])
            head_l = lambda r=r, L=L, Mk=Mk: [
                f"A1 = N·B = {G['N']:g}·{G['B']:g} = {f1(G['A1'])} mm²;  √(A2/A1) = {f2(G['sqA'])}" + (" (tự nhập)" if pl.get("overA2") else " (kể vị trí bản trên gối)"),
                f"fp,max = φc·0.85·f'c·√(A2/A1) = 0.65·0.85·{fc:g}·{f2(G['sqA'])}" + ("/1.5 (ASD)" if asd else "") + f" = {f2(fpmax)} MPa (J8-2)",
                f"Pu (nén) = {f1(kN(Pc))} kN;  Mu = {f2(kNm(Mk))} kN·m" + (" (kể Pu·lệch tâm cột)" if abs(ox) + abs(oz) > 0 else "")
                + f";  phân bố: {'tương thích biến dạng' if r['case'] == 'compat' else ('Uniform (DG1)' if r.get('prof') == 'uniform' else 'Triangular')}",
            ]
            if r["case"] == "compat":
                sol = r["sol"]
                add(f"conc_bear_{key}", "Bê tông (ép mặt)", f"Ép mặt bê tông dưới bản đế — {dn}", "MPa", "AISC J8 (strain compatibility)",
                    fpmax, r["fp"], nm, lambda head_l=head_l, sol=sol, r=r: head_l() + [
                        f"Bản cứng, Ec = {f1(Ec)} MPa, Es = {ES:g} MPa: áp lực mép fp = {f2(sol['fp'])} MPa, Y = {'∞' if math.isinf(r['Y']) else f1(r['Y'])} mm",
                        f"Tổng lực kéo neo = {f2(kN(sum(sol['T'])))} kN"], ("conc", "bp"), scale=False)
            elif r["case"] in ("axial", "small"):
                add(f"conc_bear_{key}", "Bê tông (ép mặt)", f"Ép mặt bê tông dưới bản đế — {dn}", "MPa", "AISC J8 / DG1 §3.1, 3.3",
                    fpmax, r["fp"], nm, lambda r=r, head_l=head_l, L=L: head_l() + [
                        r.get("txt") or ("Nén đúng tâm: Y = N" if r["case"] == "axial" else f"Mô men nhỏ (e ≤ e_crit): Y = {L:g} − 2e = {f1(r['Y'])} mm"),
                        f"fp = {f2(r['fp'])} MPa ≤ fp,max = {f2(fpmax)} MPa"], ("conc", "bp"), scale=False)
            elif r["case"] in ("large", "nosol"):
                lin = r.get("prof") == "linear"
                capS, demS = (kNm(r["Kmax"]), kNm(r["Kreq"])) if lin else (r["qmax"], r["qreq"])
                add(f"bp_size_{key}", "Bê tông (ép mặt)", f"Kích thước bản đế — mô men lớn, {dn}", "kN·m" if lin else "N/mm",
                    "Triangular distribution" if lin else "DG1 Eq. 3.4.4", capS, demS, nm,
                    lambda r=r, head_l=head_l, lin=lin: head_l() + [
                        f"Mô men lớn: neo chịu kéo, f = {f1(r['f'])} mm (tâm nhóm neo kéo)",
                        (f"Mu + Pu·f = {f2(kNm(r['Kreq']))} ≤ khả năng tam giác lớn nhất = {f2(kNm(r['Kmax']))} kN·m" if lin
                         else f"Điều kiện có nghiệm: q,req = 2(Mu + Pu·f)/(f + N/2)² = {f1(r['qreq'])} ≤ qmax = {f1(r['qmax'])} N/mm"),
                        ((r.get("txt") or f"Y = (f + N/2) − √[(f + N/2)² − 2(Mu + Pu·f)/qmax] = {f1(r['Y'])} mm") + f";  Tu = {f1(kN(r['Tu']))} kN"
                         if r["case"] == "large" else "Không có nghiệm → tăng kích thước bản đế (N) hoặc cường độ bê tông.")], ("conc", "bp"), scale=False)
            if r["fp"] > 0 and r["case"] not in ("nosol", "tension"):
                fp, Y, prof = r["fp"], r["Y"], r.get("prof", "uniform")
                lam_n, X, lamb = 0.0, 0.0, 0.0
                if r["case"] == "axial" and prof == "uniform":
                    X = min(4 * d * bf / (d + bf) ** 2 * Pc / (fpmax * G["A1"]), 1.0)
                    lamb = min(2 * math.sqrt(X) / (1 + math.sqrt(max(1 - X, 0.0))), 1.0)
                    lam_n = lamb * math.sqrt(d * bf) / 4
                l = max(m_, n_, lam_n)
                Mpl = strip_moment(fp, Y, l, prof)
                tpreq = math.sqrt(4 * Mpl / (0.9 * Fy)) if Mpl > 0 else 0.0
                lin = prof == "linear"
                add(f"bp_comp_{key}", "Bản đế", f"Uốn bản đế phía ép — {dn}", "kN·m/m", "DG1 Eq. 3.3.14, 3.3.15 / 3.1.3",
                    Mcap / 1e3, Mpl / 1e3, nm, lambda l=l, fp=fp, Y=Y, Mpl=Mpl, tpreq=tpreq, X=X, lamb=lamb, lam_n=lam_n, lin=lin: [
                        f"m = (N/2 + |ox|) − 0.95d/2 = {f1(m_)} mm;  n = (B/2 + |oz|) − 0.8bf/2 = {f1(n_)} mm",
                    ] + ([f"X = 4·d·bf/(d + bf)²·Pu/(φc·Pp) = {f2(X)};  λ = 2√X/(1 + √(1 − X)) = {f2(lamb)};  λn' = λ·√(d·bf)/4 = {f1(lam_n)} mm"]
                         if lam_n > 0 else []) + [
                        f"l = max(m; n{'; λn' if lam_n > 0 else ''}) = {f1(l)} mm;  fp = {f2(fp)} MPa;  Y = {'∞' if Y is None or math.isinf(Y) else f1(Y)} mm"
                        + (" (phân bố tuyến tính)" if lin else ""),
                        ((("Mpl = fp·(l²/2 − l³/(6Y))" if Y is None or Y >= l else "Mpl = fp·Y/2·(l − Y/3)") if lin else
                          ("Mpl = fp·l²/2" if Y >= l else "Mpl = fp·Y·(l − Y/2)")) + f" = {f2(Mpl / 1e3)} kN·m/m"),
                        f"φMn = 0.9·Fy·tp²/4 = 0.9·{Fy:g}·{tp:g}²/4 = {f2(Mcap / 1e3)} kN·m/m",
                        f"tp,req = √(4Mpl/(0.9Fy)) = {f1(tpreq)} mm  (tp = {tp:g} mm)"], ("bp",))
                if eff and prof == "uniform":
                    Ctot = Pc + (r["Tu"] or 0.0) if r["case"] == "large" else Pc
                    ai = 0 if key == "33" else 1
                    if r["case"] == "axial" or Y >= L - 1e-6:
                        Ae = G["Aeff"]
                    elif r["Mk"] >= 0:
                        Ae = eff_area(G, c_eff, L / 2 - Y, L / 2, ai)
                    else:
                        Ae = eff_area(G, c_eff, -L / 2, -L / 2 + Y, ai)
                    add(f"conc_eff_{key}", "Bê tông (ép mặt)", f"Ép mặt trên diện tích hiệu quả — {dn}", "kN", "Effective area",
                        kN(fpmax * Ae), kN(Ctot), nm, lambda Ae=Ae, Ctot=Ctot: [
                            f"c = tp·√(0.9·Fy/(2·fp,max)) = {tp:g}·√(0.9·{Fy:g}{'/1.5' if asd else ''}/(2·{f2(fpmax)})) = {f1(c_eff)} mm",
                            f"A_eff (trong vùng ép, cách thép cột ≤ c) = {f1(Ae)} mm²;  khả năng = fp,max·A_eff = {f2(kN(fpmax * Ae))} kN",
                            f"Lực ép C = {f2(kN(Ctot))} kN"], ("conc", "bp"), scale=False)

        # ---------- uốn bản phía kéo (mỗi neo) ----------
        if Tmax > 0:
            best = None
            for i, a in enumerate(G["anchors"]):
                if T[i] <= 0 or a["zone"] == "clash": continue
                arm = max(a["arm"], 0.0)
                if a["zone"] == "out":
                    beff = G["B"] / sum(1 for b in G["anchors"] if abs(b["x"] - a["x"]) < 1e-6)
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
                        (f"Bề rộng làm việc b = B / số neo cùng hàng = {f1(beff)} mm (DG1 §3.3)" if a["zone"] == "out"
                         else f"Bề rộng làm việc b = 2·tay đòn = {f1(beff)} mm (phân bố 45°, DG1 §3.2.2)"),
                        f"Mpl = Tu,neo·x/b = {f2(Mpl / 1e3)} kN·m/m;  φMn = 0.9·Fy·tp²/4 = {f2(Mcap / 1e3)} kN·m/m",
                        f"tp,req = 2.11·√(Tu·x/(b·Fy)) = {f1(tpreq)} mm  (tp = {tp:g} mm)"], ("bp", "anchors"))

        # ---------- cắt chân cột ----------
        mu = MU
        Vf = 0.75 * mu * max(Pc, 0.0) * kA if gen.get("friction") else 0.0
        Vd = max(Vr - Vf, 0.0)
        kV = Vd / Vr if Vr > 0 else 0.0
        V2d, V3d = V2 * kV, V3 * kV
        fric_txt = ([f"Include friction: φVf = 0.75·μ·Pu = 0.75·{mu:g}·{f2(kN(max(Pc, 0)))}" + ("/1.5" if asd else "")
                     + f" = {f2(kN(Vf))} kN → lực cắt còn lại {f2(kN(Vd))} kN"] if gen.get("friction") else [])
        if gen.get("friction"):
            add("shear_fric", "Truyền lực cắt", "Ma sát bản đế – vữa (giảm lực cắt)", "kN", "DG1 §3.5.1", kN(Vf), kN(min(Vr, Vf)), nm,
                lambda: fric_txt, ("bp", "conc"), info=True, scale=False)
        Va = 0.0
        nv = nA if welded else max(nA // 2, 1)
        if mode == "anchors":
            Va = Vd / nv
            if G["grout"] > 50 and Vd > 0:
                W.append(f"Lớp vữa {G['grout']:g} mm > 50 mm, neo chịu cắt: chưa xét uốn neo qua lớp vữa (DG1 §3.5.2).")
        else:
            lg = inp["lug"]
            bl, H, tl = float(lg["bl"]), float(lg["H"]), float(lg["tl"])
            lm = material(lg.get("mat", "Q345"))
            demb = max(H - G["grout"], 0.0)
            Abr = bl * demb
            capB = 0.65 * 1.3 * fc * Abr * sC
            add("lug_bear", "Bản chắn cắt", "Ép mặt bê tông lên bản chắn cắt", "kN", "ACI 349-06 D.4.6.2 (DG1 §3.5.3)", kN(capB), kN(Vd), nm,
                lambda Abr=Abr, demb=demb, capB=capB, bl=bl: fric_txt + [
                    f"Chiều sâu chôn trong bê tông = H − vữa = {f1(demb)} mm;  A_brg = bl·(H − G) = {bl:g}·{f1(demb)} = {f1(Abr)} mm²",
                    "φVn = 0.65·1.3·f'c·A_brg" + (" ·0.75 (seismic)" if seismic else "") + f" = {f2(kN(capB))} kN (bản chắn chịu toàn bộ lực cắt)"], ("lug", "conc"))
            arm = G["grout"] + demb / 2
            Mu = Vd * arm
            capM = 0.9 * lm["Fy"] * bl * tl * tl / 4
            add("lug_flex", "Bản chắn cắt", "Uốn bản chắn cắt tại chân hàn", "kN·m", "DG1 §3.5.3; AISC F11", kNm(capM), kNm(Mu), nm,
                lambda Mu=Mu, capM=capM, arm=arm: [
                    f"Mu = Vu·(G + (H − G)/2) = {f2(kN(Vd))}·{f1(arm)}/1000 = {f2(kNm(Mu))} kN·m",
                    f"φMn = 0.9·Fy·bl·tl²/4 = 0.9·{lm['Fy']:g}·{bl:g}·{tl:g}²/4 = {f2(kNm(capM))} kN·m"], ("lug",))
            capV = 1.0 * 0.6 * lm["Fy"] * bl * tl
            add("lug_v", "Bản chắn cắt", "Chảy cắt bản chắn cắt", "kN", "AISC Eq. J4-3", kN(capV), kN(Vd), nm,
                lambda capV=capV: [f"φVn = 1.0·0.6·Fy·bl·tl = {f2(kN(capV))} kN"], ("lug",))
            wl = float(lg["w"])
            armw = tl + 2 * wl / 3
            fv, fn = Vd / (2 * bl), Mu / (armw * bl)
            fr = math.hypot(fv, fn)
            capw = 0.75 * 0.6 * weldF * 0.707 * wl
            add("lug_w", "Bản chắn cắt", "Hàn bản chắn cắt vào bản đế", "kN/m", "AISC Eq. J2-4", capw, fr, nm,
                lambda fv=fv, fn=fn, fr=fr, capw=capw, wl=wl, armw=armw: [
                    f"Hai đường hàn góc w = {wl:g} mm dài bl = {bl:g} mm;  cánh tay đòn cặp lực = tl + 2w/3 = {f1(armw)} mm",
                    f"fv = Vu/(2bl) = {f1(fv)} N/mm;  fn = Mu/(arm·bl) = {f1(fn)} N/mm;  fr = √(fv² + fn²) = {f1(fr)} N/mm",
                    f"φRn = 0.75·0.6·FEXX·0.707·w = {f1(capw)} N/mm"], ("lug",))

        # ---------- neo: AISC J3 ----------
        rT = 0.75 * Fnt * Ab
        add("anc_t", "Bu lông neo (AISC)", "Neo chịu kéo", "kN", "AISC J3.6, Table J3.2", kN(rT), kN(Tmax), nm,
            lambda rT=rT: [f"Lực kéo neo lớn nhất Tu = {f2(kN(Tmax))} kN (tổng nhóm {f2(kN(Tsum))} kN)",
                           f"Neo M{da:g} cấp {am['name']}: Fu = {am['Fu']:g} MPa;  Fnt = 0.75Fu = {f1(Fnt)} MPa;  Ab = {f1(Ab)} mm²",
                           f"φRn = 0.75·Fnt·Ab = {f2(kN(rT))} kN"], ("anchors",))
        if mode == "anchors":
            rV = 0.75 * Fnv * Ab
            add("anc_v", "Bu lông neo (AISC)", "Neo chịu cắt", "kN", "AISC J3.6 (Table J3.2)", kN(rV), kN(Va), nm,
                lambda rV=rV, nv=nv: fric_txt + [
                    f"Vu = {f2(kN(Vd))} kN chia cho {nv} neo ({'neo hàn vào bản đế: mọi neo' if welded else 'lỗ quá cỡ: một nửa số neo, DG1 §3.5.2'}) → Vu,neo = {f2(kN(Va))} kN",
                    f"Fnv = {Fnv / am['Fu']:.3f}Fu = {f1(Fnv)} MPa;  φRn = 0.75·Fnv·Ab = {f2(kN(rV))} kN"], ("anchors",))
            frv = Va / Ab
            Fp = min(1.3 * Fnt - Fnt / (0.75 * Fnv * kA) * frv, Fnt)
            capTV = 0.75 * max(Fp, 0.0) * Ab
            add("anc_tv", "Bu lông neo (AISC)", "Neo chịu kéo + cắt đồng thời", "kN", "AISC Eq. J3-3" + ("b" if asd else "a"), kN(capTV), kN(Tmax), nm,
                lambda Fp=Fp, frv=frv, capTV=capTV: [
                    f"frv = Vu,neo/Ab = {f1(frv)} MPa;  F'nt = 1.3Fnt − Fnt/({'Fnv/Ω' if asd else 'φFnv'})·frv = {f1(Fp)} ≤ Fnt = {f1(Fnt)} MPa",
                    f"φRn = 0.75·F'nt·Ab = {f2(kN(capTV))} kN"], ("anchors",))

        # ---------- neo: ACI 318 ----------
        if not fast:
            tN, tV = [], []                                  # tỷ số nhóm kéo / cắt cho tương tác D.7
            stxt = lambda s: (f" ·0.75 (seismic, {aref('D.3.3')})" if s < 1 else "")
            if Tmax > 0:
                cap = phi_st * Ase * futa * sS
                tN.append(add("aci_sa", "Neo – bê tông (ACI 318)", "Bền thép neo khi kéo", "kN", aref("D.5.1"), kN(cap), kN(Tmax), nm,
                              lambda cap=cap: [f"Ase,N = π/4·(d − 0.9382p)² = {f1(Ase)} mm²;  futa = min(Fu; 1.9Fy; 860) = {f1(futa)} MPa",
                                               f"φNsa = {phi_st}·Ase·futa{stxt(sS)} = {f2(kN(cap))} kN" + ("  (thép giòn)" if brittle else "")], ("anchors",)))
                tp_ = [p for p, t in zip(spts, T) if t > 0]
                tf_ = [t for t in T if t > 0]
                if primT:
                    AsReq = Tsum / (0.75 * fyr * kA)
                    add("aci_rt", "Neo – bê tông (ACI 318)", "Cốt thép neo chịu kéo — As yêu cầu (thay phá vỡ bê tông)", "mm²", aref("D.5.2.9"),
                        AsReq, AsReq, nm, lambda AsReq=AsReq: [
                            "Tension reinforcement (primary): cốt thép neo ôm nhóm neo kéo, không xét phá vỡ hình nón bê tông",
                            f"As,req = Nua/(0.75·fy) = {f2(kN(Tsum))}·10³/(0.75·{fyr:g}{'/1.5' if asd else ''}) = {f1(AsReq)} mm²  (fy = {fyr:g} MPa, Grade 60)",
                            "Bố trí cốt thép ≥ As,req, neo đủ chiều dài phát triển về hai phía mặt phá hoại giả định."], ("conc", "anchors"), info=True, scale=False)
                else:
                    br = aci_breakout_tension(G, tp_, tf_, hef, fc, lam, cracked, headed)
                    phiN = phi_cbT * br["Ncbg"] * sC
                    tN.append(add("aci_cb", "Neo – bê tông (ACI 318)", "Phá vỡ bê tông khi kéo (nhóm neo)", "kN", aref("D.5.2"), kN(phiN), kN(Tsum), nm,
                                  lambda br=br, phiN=phiN: [
                                      f"Nhóm {br['n']} neo chịu kéo, tổng Nua = {f2(kN(Tsum))} kN;  hef = {hef:g} mm"
                                      + (f" → h'ef = {f1(br['h'])} mm ({aref('D.5.2.3')})" if br["h"] < hef else ""),
                                      br["nb_txt"],
                                      f"ANc = {f1(br['ANc'])} mm²;  ANco = 9·hef² = {f1(br['ANco'])} mm²",
                                      f"ψec = {f2(br['psi_ec'])} (e'N = {f1(br['ex'])}; {f1(br['ey'])} mm);  ψed = {f2(br['psi_ed'])} (ca,min = {f1(br['camin'])} mm);  "
                                      f"ψc = {br['psi_c']:g} ({'nứt' if cracked else 'không nứt'});  ψcp = 1.0",
                                      f"φNcbg = {phi_cbT}·ANc/ANco·ψec·ψed·ψc·ψcp·Nb{stxt(sC)} = {f2(kN(phiN))} kN"
                                      + ("  (Condition A — supplementary reinforcement)" if phi_cbT > 0.7 else "")], ("conc", "anchors")))
                psi_cp = 1.0 if cracked else 1.4
                if headed:
                    Np = 8 * Abrg * fc
                    ptxt = f"Abrg = {f1(Abrg)} mm² ({HEADS.get(head, head)});  Np = 8·Abrg·f'c = {f2(kN(Np))} kN"
                else:
                    eh = min(max(float(an.get("eh") or 3 * da), 3 * da), 4.5 * da)
                    Np = 0.9 * fc * eh * da
                    ptxt = f"Neo móc (hooked): eh = {f1(eh)} mm (3da ≤ eh ≤ 4.5da);  Np = 0.9·f'c·eh·da = {f2(kN(Np))} kN"
                capP = 0.70 * psi_cp * Np * sC
                tN.append(add("aci_pn", "Neo – bê tông (ACI 318)", "Nhổ tuột neo (pullout)", "kN", aref("D.5.3"), kN(capP), kN(Tmax), nm,
                              lambda capP=capP, psi_cp=psi_cp, ptxt=ptxt: [ptxt, f"φNpn = 0.70·ψc,P·Np{stxt(sC)} = 0.70·{psi_cp:g}·Np = {f2(kN(capP))} kN"],
                              ("anchors", "conc")))
                for edge, (ax_i, sgn) in ({"+x": (0, 1), "-x": (0, -1), "+z": (1, 1), "-z": (1, -1)}.items() if headed else ()):
                    E = G["N2"] / 2 if ax_i == 0 else G["B2"] / 2
                    grp = [(p, t) for p, t in zip(spts, T) if t > 0 and sgn * p[ax_i] > 0]
                    grp = [(p, t) for p, t in grp if E - abs(p[ax_i]) <= min(G["N2"] / 2 - abs(p[0]), G["B2"] / 2 - abs(p[1])) + 1e-6]
                    if not grp: continue
                    ca1 = min(E - abs(p[ax_i]) for p, _t in grp)
                    if hef <= 2.5 * ca1: continue
                    o = 1 - ax_i
                    E2 = G["B2"] / 2 if ax_i == 0 else G["N2"] / 2
                    ca2 = min(E2 - abs(p[o]) for p, _t in grp)
                    Nsb = 13 * ca1 * math.sqrt(Abrg) * lam * math.sqrt(fc)
                    if ca2 < 3 * ca1:
                        Nsb *= (1 + min(max(ca2 / ca1, 1.0), 3.0)) / 4
                    s = max(p[o] for p, _t in grp) - min(p[o] for p, _t in grp)
                    Nsbg = (1 + s / (6 * ca1)) * Nsb if len(grp) > 1 and s < 6 * ca1 else len(grp) * Nsb
                    dem = sum(t for _p, t in grp)
                    capSb = phi_cbT * Nsbg * sC
                    tN.append(add(f"aci_sb{edge}", "Neo – bê tông (ACI 318)", f"Nổ mặt bên bê tông (mép {edge})", "kN", aref("D.5.4"),
                                  kN(capSb), kN(dem), nm, lambda ca1=ca1, ca2=ca2, Nsb=Nsb, Nsbg=Nsbg, s=s, grp=grp, capSb=capSb: [
                                      f"hef = {hef:g} > 2.5·ca1 = {f1(2.5 * ca1)} mm → xét nổ mặt bên;  ca1 = {f1(ca1)} mm, ca2 = {f1(ca2)} mm",
                                      "Nsb = 13·ca1·√Abrg·λ·√f'c" + (" ·(1 + ca2/ca1)/4" if ca2 < 3 * ca1 else "") + f" = {f2(kN(Nsb))} kN",
                                      (f"Nhóm {len(grp)} neo, s = {f1(s)} mm < 6ca1: Nsbg = (1 + s/(6ca1))·Nsb = {f2(kN(Nsbg))} kN" if len(grp) > 1 and s < 6 * ca1
                                       else f"Nsbg = {len(grp)}·Nsb = {f2(kN(Nsbg))} kN"),
                                      f"φNsbg = {phi_cbT}·Nsbg{stxt(sC)} = {f2(kN(capSb))} kN"], ("conc", "anchors")))
            if mode == "anchors" and Vd > 0:
                Vsa = 0.6 * Ase * futa * (0.8 if G["grout"] > 0 else 1.0)
                capVs = phi_sv * Vsa * sS
                tV.append(add("aci_vsa", "Neo – bê tông (ACI 318)", "Bền thép neo khi cắt", "kN", aref("D.6.1"), kN(capVs), kN(Va), nm,
                              lambda Vsa=Vsa, capVs=capVs: [
                                  "Vsa = 0.6·Ase,V·futa" + (f" ·0.8 (có lớp vữa, {aref('D.6.1.3')})" if G["grout"] > 0 else "") + f" = {f2(kN(Vsa))} kN",
                                  f"φVsa = {phi_sv}·Vsa{stxt(sS)} = {f2(kN(capVs))} kN;  Vu,neo = {f2(kN(Va))} kN"], ("anchors",)))
                for ax_i, Vc, lab in ((0, V2d, "V2 — phương N"), (1, V3d, "V3 — phương B")):
                    if abs(Vc) < 1e-6: continue
                    if primV:
                        AsReqV = abs(Vc) / (0.75 * fyr * kA)
                        add(f"aci_rv_{ax_i}", "Neo – bê tông (ACI 318)", f"Cốt thép neo chịu cắt — As yêu cầu ({lab})", "mm²", aref("D.6.2.9"),
                            AsReqV, AsReqV, nm, lambda AsReqV=AsReqV, Vc=Vc: [
                                "Shear reinforcement (primary): đai / thép chữ U ôm neo, không xét phá vỡ bê tông khi cắt",
                                f"As,req = |V|/(0.75·fy) = {f2(kN(abs(Vc)))}·10³/(0.75·{fyr:g}{'/1.5' if asd else ''}) = {f1(AsReqV)} mm²"], ("conc", "anchors"), info=True, scale=False)
                        continue
                    sb = aci_breakout_shear(G, spts, ax_i, 1 if Vc > 0 else -1, hef, da, fc, lam, cracked)
                    phiV = phi_cbV * sb["Vcbg"] * sC
                    tV.append(add(f"aci_vcb_{ax_i}", "Neo – bê tông (ACI 318)", f"Phá vỡ bê tông khi cắt ({lab})", "kN", aref("D.6.2"),
                                  kN(phiV), kN(abs(Vc)), nm, lambda sb=sb, Vc=Vc, phiV=phiV: [
                                      f"Hàng neo trước ({sb['n']} neo) chịu toàn bộ |V| = {f2(kN(abs(Vc)))} kN;  ca1 = {f1(sb['ca1'])} mm"
                                      + (f" → c'a1 = {f1(sb['ca1e'])} mm ({aref('D.6.2.4')})" if sb["ca1e"] < sb["ca1"] else ""),
                                      f"Vb = min[0.6(le/da)^0.2·√da·λ·√f'c·ca1^1.5; 3.7·λ·√f'c·ca1^1.5] = {f2(kN(sb['Vb']))} kN  (le = {f1(sb['le'])} mm)",
                                      f"AVc = {f1(sb['AVc'])} mm²;  AVco = 4.5·ca1² = {f1(sb['AVco'])} mm²;  ψed = {f2(sb['psi_ed'])};  ψc = {sb['psi_c']:g};  ψh = {f2(sb['psi_h'])}",
                                      f"φVcbg = {phi_cbV}·AVc/AVco·ψed·ψc·ψh·Vb{stxt(sC)} = {f2(kN(phiV))} kN"
                                      + ("  (Condition A)" if phi_cbV > 0.7 else "")], ("conc", "anchors")))
                ball = aci_breakout_tension(G, spts, [1.0] * nA, hef, fc, lam, cracked, headed)
                kcp = 1.0 if hef < 65 else 2.0
                capCP = 0.70 * kcp * ball["Ncbg"] * sC
                tV.append(add("aci_cp", "Neo – bê tông (ACI 318)", "Cạy bê tông (pryout)", "kN", aref("D.6.3"), kN(capCP), kN(Vd), nm,
                              lambda capCP=capCP, ball=ball, kcp=kcp: [
                                  f"Ncpg = Ncbg của toàn nhóm {nA} neo = {f2(kN(ball['Ncbg']))} kN;  kcp = {kcp:g}",
                                  f"φVcpg = 0.70·kcp·Ncpg{stxt(sC)} = {f2(kN(capCP))} kN;  Vu = {f2(kN(Vd))} kN"], ("conc", "anchors")))
            if tN and tV:
                rn, rv = max(tN), max(tV)
                if rv <= 0.2: val, how = rn, "Vua/φVn ≤ 0.2 → chỉ kiểm tra kéo"
                elif rn <= 0.2: val, how = rv, "Nua/φNn ≤ 0.2 → chỉ kiểm tra cắt"
                else: val, how = (rn + rv) / 1.2, "Nua/φNn + Vua/φVn ≤ 1.2"
                add("aci_int", "Neo – bê tông (ACI 318)", "Tương tác kéo – cắt (neo / bê tông)", "", aref("D.7"), 1.0, val, nm,
                    lambda rn=rn, rv=rv, how=how, val=val: [f"Nua/φNn (lớn nhất) = {f2(rn)};  Vua/φVn (lớn nhất) = {f2(rv)}", how,
                                                           f"Tỷ số = {f2(val)}"], ("anchors", "conc"), scale=False)

        # ---------- hàn cột – bản đế (nội lực tại tâm cột) ----------
        Nw = max(Nt, 0.0)
        fv = Vr / Lt
        welds = [("w_fl", Nw / Lt + abs(M33) * (d / 2) / I33 + abs(M22) * (bf / 2) / I22, qfl, wfl,
                  "Hàn cánh cột vào bản đế" + (" (chỉ mặt ngoài cánh)" if outer else ""), "wflange")]
        if not outer:
            welds.append(("w_web", Nw / Lt + abs(M33) * (hw / 2) / I33 + abs(M22) * (tw / 2) / I22, qweb, wweb, "Hàn bụng cột vào bản đế", "wweb"))
        for key, fn, cap, wsz, lab, tag in welds:
            fr = math.hypot(fn, fv)
            add(key, "Hàn cột – bản đế", lab, "kN/m", "AISC Eq. J2-4 (elastic method)", cap, fr, nm,
                lambda fn=fn, fr=fr, cap=cap, wsz=wsz: [
                    f"Chu vi hàn: cánh Lf = {f1(Lf)} mm, bụng Lw = {f1(Lw)} mm, tổng L = {f1(Lt)} mm;  I33 = {f1(I33 / 1e6)}·10⁶ mm³, I22 = {f1(I22 / 1e6)}·10⁶ mm³",
                    f"Lực dọc kéo đưa vào hàn = {f2(kN(Nw))} kN (lực nén truyền bằng tì ép cột lên bản đế)",
                    f"fn = N/L + M33·c/I33 + M22·c/I22 = {f1(fn)} N/mm;  fv = Vu/L = {f1(fv)} N/mm;  fr = √(fn² + fv²) = {f1(fr)} N/mm",
                    f"φRn = 0.75·0.6·FEXX·0.707·w = 0.75·0.6·{weldF:g}·0.707·{wsz:g} = {f1(cap)} N/mm"], (tag,))

        r33 = dirs.get("33") or dirs.get("bi") or {}
        if r33.get("sol"):
            sol = r33["sol"]
            Y33 = sol["fp"] / (Ec * abs(sol["kx"])) if abs(sol["kx"]) > 1e-15 else math.inf
            prof33, q33 = "linear", sol["fp"]
        else:
            Y33, prof33, q33 = r33.get("Y"), r33.get("prof", "uniform"), r33.get("fp", 0.0)
        demands.append(dict(name=nm, N=kN(Nt), V2=kN(V2), V3=kN(V3), M33=kNm(M33), M22=kNm(M22), Pc=kN(Pc),
                            case33=r33.get("case", "—"), case22=dirs.get("22", {}).get("case", "—"),
                            Y33=Y33, q33=q33 or 0.0, prof33=prof33, Vf=kN(Vf),
                            Tmax=kN(Tmax), Tsum=kN(Tsum), T=[kN(t) for t in T], sM33=1 if Mx >= 0 else -1, sM22=1 if My >= 0 else -1))

    # ---------- kiểm tra cấu tạo ----------
    geo = []
    def gchk(grp, name, val, mn=None, mx=None, ref="", unit="mm"):
        ok = (mn is None or val >= mn - 1e-6) and (mx is None or val <= mx + 1e-6)
        geo.append(dict(grp=grp, name=name, val=val, min=mn, max=mx, ref=ref, unit=unit, ok=ok))
    projN, projB = G["N"] / 2 - abs(ox) - d / 2, G["B"] / 2 - abs(oz) - bf / 2
    gchk("Bản đế", "Phần bản nhô theo phương N", projN, 0.0, None, "DG1 §2.10")
    gchk("Bản đế", "Phần bản nhô theo phương B", projB, 0.0, None, "DG1 §2.10")
    if min(projN, projB) < 25:
        W.append("Bản đế nhô ra ngoài cột < 25 mm: khó hàn và đặt neo (DG1 §2.10).")
    emin = edge_min(int(da), True)
    gchk("Bu lông neo", "Khoảng cách mép bản ex (phương N)", float(an["ex"]), emin, None, "AISC J3.4")
    gchk("Bu lông neo", "Khoảng cách mép bản ey (phương B)", float(an["ey"]), emin, None, "AISC J3.4")
    sxv = sorted({round(a["x"], 3) for a in G["anchors"]}); syv = sorted({round(a["y"], 3) for a in G["anchors"]})
    if len(sxv) > 1: gchk("Bu lông neo", "Bước neo phương N", min(b - a for a, b in zip(sxv, sxv[1:])), 4 * da, None, aref("D.8.1"))
    if len(syv) > 1: gchk("Bu lông neo", "Bước neo phương B", min(b - a for a, b in zip(syv, syv[1:])), 4 * da, None, aref("D.8.1"))
    clr = min(a["clear"] for a in G["anchors"])
    wmin = washer_min(da)[0] / 2 + max(wfl, wweb)
    gchk("Bu lông neo", "Khoảng hở tâm neo – mặt thép cột", clr, wmin, None, "DG1 Sec. 2.10, Table 2.3")
    if not headed:
        gchk("Bu lông neo", "Chiều dài móc eh", float(an.get("eh") or 0), 3 * da, 4.5 * da, aref("D.5.3"))
    camin = min(a["ca"] for a in G["anchors"])
    gchk("Bê tông", "Khoảng cách neo tới mép gối", camin, 50 + head_sz / 2, None, aref("D.8.2") + ", 7.7 (50 mm cover)")
    gchk("Bê tông", "Chiều sâu chôn hef ≤ h − 50", hef, None, G["ha"] - 50, aref("D.8.5"))
    gchk("Bê tông", "Gối nhô ra ngoài bản đế", min(G["N2"] / 2 - abs(G["px"]) - G["N"] / 2, G["B2"] / 2 - abs(G["pz"]) - G["B"] / 2), 0.0, None, "AISC J8")
    gchk("Hàn", "Hàn góc cánh cột ≥ min", wfl, weld_min(min(tf, tp)), None, "Table J2.4")
    if not outer:
        gchk("Hàn", "Hàn góc bụng cột ≥ min", wweb, weld_min(min(tw, tp)), None, "Table J2.4")
    if mode == "lug":
        lg = inp["lug"]
        gchk("Bản chắn cắt", "Chiều cao chôn H − vữa", float(lg["H"]) - G["grout"], 50.0, None, "DG1 §3.5.3")
        gchk("Bản chắn cắt", "Hàn bản chắn ≥ min", float(lg["w"]), weld_min(min(float(lg["tl"]), tp)), None, "Table J2.4")
        W.append("Bản chắn cắt: chưa xét phá vỡ bê tông về phía mép gối do bản chắn (ACI 349-06 D.11.2) — kiểm tra riêng nếu gối hẹp.")
    if any(a["zone"] == "clash" for a in G["anchors"]):
        W.append("Có neo trùng vị trí cánh cột — đổi ex / ey hoặc số neo.")
    if primT or primV:
        W.append(f"Có cốt thép neo (primary): kiểm tra chiều dài neo của cốt thép về hai phía mặt phá hoại ({aref('D.5.2.9')}, {aref('D.6.2.9')}) — ngoài phạm vi tool.")
    if gen.get("compat") and press == "uniform" and axis != "biaxial":
        W.append("Consider strain compatibility chỉ áp dụng với phân bố Triangular — bỏ qua với Uniform.")
    if axis == "biaxial" and press == "uniform":
        W.append("Analysis axis = Biaxial: dùng phân bố ép tuyến tính (tương thích biến dạng) thay cho Uniform.")
    if eff and (press != "uniform" or axis == "biaxial"):
        W.append("Effective area chỉ kiểm tra với phân bố Uniform theo từng phương.")
    if pl.get("ctype") == "stiffened":
        W.append("Bản đế có sườn (Stiffened) chưa hỗ trợ — tính như bản không sườn (thiên an toàn cho bản đế).")
    if seismic:
        W.append("Seismic: neo thép giòn không được dùng trong vùng động đất (ACI D.3.3)." if brittle else
                 f"Seismic: sức kháng neo nhân 0.75 ({aref('D.3.3')}); yêu cầu dẻo của neo cần kiểm tra riêng.")

    lst = [checks[i] for i in order]
    gov = None
    for c in lst:
        if not c["info"] and (gov is None or c["ratio"] > gov["ratio"]):
            gov = c
    return dict(G=G, checks=lst, geo=geo, demands=demands, gov=gov, W=W, geoFail=sum(1 for x in geo if not x["ok"]), weldF=weldF,
                bolt=dict(db=int(da), grade=am["name"]))


# ─────────────────────────── Tối ưu (Optimization criteria như RAM) ───────────────────────────
def _frange(a, b, s):
    s = max(float(s), 1e-6)
    out, v = [], float(a)
    while v <= float(b) + 1e-9:
        out.append(round(v, 4)); v += s
    return out


def auto_design(inp: dict, dias=tuple(ANCHOR_DIAS), tps=None, progress: Optional[Callable] = None):
    """Theo Optimization criteria của RAM: tìm (N, B, tp) nhẹ nhất đạt các kiểm tra bê tông / bản đế, rồi đường kính neo nhỏ nhất
    (hef tăng dần từ hef,min nếu cần) đạt các kiểm tra neo. Trả về dict(tp, d, N, B, ex, ey, hef, ratio[, fail]) hoặc None."""
    base = copy.deepcopy(inp)
    normalize(base)
    o = base["opt"]
    try:
        G0 = build_geometry(base)
    except Exception:  # noqa: BLE001
        return None
    d, bf = G0["d"], G0["bf"]
    ox, oz = abs(G0["ox"]), abs(G0["oz"])
    if tps is None:
        tps = _frange(o.get("tpMin", 10), o.get("tpMax", 80), o.get("tpInc", 2)) if o.get("optTp", True) else [G0["tp"]]
    tps = sorted(tps) or [G0["tp"]]
    projs = _frange(o.get("pMin", 40), o.get("pMax", 380), o.get("dimInc", 25))
    Ns = sorted({round(d + 2 * (p + ox), 1) for p in projs}) if o.get("optN", True) else [G0["N"]]
    Bs = sorted({round(bf + 2 * (p + oz), 1) for p in projs}) if o.get("optB", True) else [G0["B"]]
    keep = o.get("keepPos", "initial")
    an0 = base["anchor"]
    ax0, ay0 = G0["N"] / 2 - float(an0["ex"]), G0["B"] / 2 - float(an0["ey"])

    def trial(N, B, tp, dd=None, hef=None, fast=True):
        t = copy.deepcopy(base)
        t["plate"].update(N=N, B=B, tp=tp)
        if keep == "initial":
            t["anchor"]["ex"], t["anchor"]["ey"] = round(N / 2 - ax0, 2), round(B / 2 - ay0, 2)
        if dd is not None: t["anchor"]["d"] = dd
        if hef is not None: t["anchor"]["hef"] = hef
        if fast: t["_fast"] = True
        try:
            return t, compute(t)
        except Exception:  # noqa: BLE001
            return t, None

    def plate_ratio(R):
        if R is None: return math.inf
        mx = max((c["ratio"] for c in R["checks"] if c["id"].startswith(("bp_", "conc_"))), default=0.0)
        bad = [x for x in R["geo"] if not x["ok"] and (x["grp"] == "Bản đế" or "mép" in x["name"] or "hở" in x["name"])]
        return mx if not bad else max(mx, 1.0 + 1e-6)

    best, fallback = None, None
    for N, B in sorted(((N, B) for N in Ns for B in Bs), key=lambda nb: nb[0] * nb[1]):
        if best and N * B * tps[0] >= best[0]: continue
        if keep == "initial" and (N / 2 - ax0 < 1 or B / 2 - ay0 < 1): continue
        rmax = plate_ratio(trial(N, B, tps[-1])[1])
        if rmax > 1.0:
            if fallback is None or rmax < fallback[3]: fallback = (math.inf, N, B, rmax, tps[-1])
            continue
        lo, hi, found = 0, len(tps) - 1, len(tps) - 1
        while lo <= hi:                                       # tp nhỏ nhất đạt (đơn điệu theo tp)
            mid = (lo + hi) // 2
            if plate_ratio(trial(N, B, tps[mid])[1]) <= 1.0:
                found, hi = mid, mid - 1
            else:
                lo = mid + 1
        w = N * B * tps[found]
        if best is None or w < best[0]:
            best = (w, N, B, plate_ratio(trial(N, B, tps[found])[1]), tps[found])
        if progress: progress(N)
    best = best or fallback
    if best is None: return None
    _w, N, B, rp, tp = best
    tpl, _R = trial(N, B, tp)
    ex, ey = tpl["anchor"]["ex"], tpl["anchor"]["ey"]

    hef0 = float(base["anchor"]["hef"])
    hmax = float(base["ped"]["h"]) - 50
    hefs = ([h for h in _frange(max(float(o.get("hefMin", 300)), 50), hmax, 25)] or [hef0]) if o.get("optD", True) else [hef0]
    dlist = list(dias) if o.get("optD", True) else [int(base["anchor"]["d"])]
    pick = lambda R: max((c["ratio"] for c in R["checks"] if c["id"].startswith(("anc_", "aci_", "bp_ten"))), default=0.0)
    bestA, done = None, False
    for dd in dlist:
        for hef in hefs:
            _t, R = trial(N, B, tp, dd, hef, fast=False)
            if R is None: continue
            mx = pick(R)
            gfail = [g for g in R["geo"] if not g["ok"] and g["grp"] in ("Bu lông neo", "Bê tông") and "long đen" not in g["name"]]
            if bestA is None or mx < bestA[2]: bestA = (dd, hef, mx)
            if mx <= 1.0 and not gfail:
                bestA, done = (dd, hef, mx), True
                break
        if done: break
    if bestA is None: return None
    res = dict(tp=tp, d=bestA[0], hef=bestA[1], N=N, B=B, ex=ex, ey=ey, ratio=max(rp, bestA[2]))
    if res["ratio"] > 1.0: res["fail"] = True
    return res
