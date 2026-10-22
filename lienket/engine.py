"""
engine.py — Lõi tính knee kèo bản đầu bu lông
=============================================
AISC 360-10 (LRFD) + AISC Design Guide 4 (2003), Design Guide 16 (2002),
Design Guide 39 (2023, phụ lục A — Yc phía gối).

Port 1:1 từ knee_engine.js (đã kiểm chứng với DG16 Ex 4.2.1, DG4, DG39 và RAM Connection #11),
mở rộng: cánh ngoài / cánh trong khác nhau, quy cách tiết diện mới (section_parser).

Đơn vị nội bộ: N, mm, MPa. Nhập/xuất: kN, kN·m. Chiều dài thanh L: m.
Quy ước dấu (nội lực tại mặt liên kết): N > 0 kéo; M < 0 → cánh NGOÀI chịu kéo.
"""

from __future__ import annotations

import math
from typing import Callable, Optional

from knee_section import SectionError, parse_section

E = 200000.0
IN = 25.4
D2R = math.pi / 180.0


def cosd(a): return math.cos(a * D2R)
def sind(a): return math.sin(a * D2R)
def isnan(x): return x is None or (isinstance(x, float) and math.isnan(x))
NAN = float("nan")

# ─────────────────────────── Thư viện ───────────────────────────
MATERIALS = {
    "Q345": (345, 470), "Q235": (235, 370), "SS400": (245, 400), "SM490": (325, 490),
    "CCT34": (220, 340), "CCT38": (240, 380), "CCT42": (260, 420),
    "A36": (250, 400), "A572 Gr50": (345, 450), "A992": (345, 450),
}
BOLT_GRADES = {   # AISC 360-10 Table J3.2 (ksi quy đổi): 8.8 ≈ A325M, 10.9 ≈ A490M
    "8.8":  dict(Fnt=620.5, FnvN=372.3, FnvX=468.8, pre="A325", label="Cấp 8.8 (≈ A325M)"),
    "10.9": dict(Fnt=779.1, FnvN=468.8, FnvX=579.2, pre="A490", label="Cấp 10.9 (≈ A490M)"),
    "A325": dict(Fnt=620.5, FnvN=372.3, FnvX=468.8, pre="A325", label="ASTM A325M"),
    "A490": dict(Fnt=779.1, FnvN=468.8, FnvX=579.2, pre="A490", label="ASTM A490M"),
}
BOLT_DIAS = [16, 20, 22, 24, 27, 30, 36]
PRETENSION = {  # kN — Table J3.1M
    "A325": {16: 91, 20: 142, 22: 176, 24: 205, 27: 267, 30: 326, 36: 475},
    "A490": {16: 114, 20: 179, 22: 221, 24: 257, 27: 334, 30: 408, 36: 595},
}
HOLE_STD = {16: 18, 20: 22, 22: 24, 24: 27, 27: 30, 30: 33, 36: 39}
EDGE_MIN = {16: (28, 22), 20: (34, 26), 22: (38, 28), 24: (42, 30), 27: (48, 34), 30: (52, 38), 36: (64, 46)}
ELECTRODES = {"E60XX": 413.7, "E70XX": 482.6, "E80XX": 551.6, "AS E41XX": 410.0, "AS E48XX": 480.0}
COND_LABEL = {
    "endplate": "Bản đầu (như end-plate, DG16)",
    "cont_unstiff": "Cánh liên tục, không sườn",
    "cont_stiff": "Cánh liên tục, có sườn ngang",
    "top_cap": "Đỉnh cấu kiện có bản nắp",
    "top_unstiff": "Đỉnh cấu kiện, không sườn",
}


def hole_dia(db): return HOLE_STD.get(db, db + 3)
def edge_min(db, sheared):
    r = EDGE_MIN.get(db)
    if r: return r[0] if sheared else r[1]
    return (1.75 if sheared else 1.25) * db
def weld_min(t): return 3 if t <= 6 else 5 if t <= 13 else 6 if t <= 19 else 8


def material(name):
    fy, fu = MATERIALS.get(name, MATERIALS["Q345"])
    return dict(name=name if name in MATERIALS else "Q345", Fy=float(fy), Fu=float(fu))


def fold(a):
    y = abs(a) % 180
    return 180 - y if y > 90 else y


# ─────────────────────────── Cấu kiện tại nút ───────────────────────────
def member_at_joint(m: dict, label: str) -> dict:
    """m = {sec, mat, L (m), jointEnd 'I'|'J', topIsOuter, [dims]}. Trả về hình học tiết diện tại đầu nút.
    Ưu tiên đọc theo quy cách tên; tên không theo quy cách → dùng m['dims'] (kích thước đọc qua API SAP)."""
    from knee_section import SectionAt
    L = max(float(m.get("L") or 0), 0.01)
    x = 0.0 if m.get("jointEnd", "I") == "I" else L
    try:
        sec = parse_section(m["sec"])
        s = sec.at(x, L)
        dx = min(0.05 * L, 0.5)
        s2 = sec.at(x + dx if x == 0 else x - dx, L)
        taper_sign = 1 if s2.d < s.d - 1e-9 else (-1 if s2.d > s.d + 1e-9 else 0)
        tapered = sec.tapered
    except SectionError as e:
        dm = m.get("dims")
        if not dm:
            raise ValueError(f"Tiết diện {label}: {e}")
        d = float(dm["d"]); tt, tb = float(dm["tf_top"]), float(dm["tf_bot"])
        s = SectionAt(m["sec"], d, d - tt - tb, float(dm["tw"]), float(dm["bf_top"]), tt, float(dm["bf_bot"]), tb, float(dm.get("beta", 0)))
        taper_sign = int(dm.get("taper_sign", 0)); tapered = s.beta > 1e-6
    top_out = m.get("topIsOuter", True)
    bfE, tfE, bfI, tfI = (s.bf_top, s.tf_top, s.bf_bot, s.tf_bot) if top_out else (s.bf_bot, s.tf_bot, s.bf_top, s.tf_top)
    return dict(label=label, sec=m["sec"], d=s.d, hw=s.hw, tw=s.tw, bfE=bfE, tfE=tfE, bfI=bfI, tfI=tfI,
                bf=min(bfE, bfI), tf=min(tfE, tfI), beta=s.beta, taper_sign=taper_sign, L=L, A=s.area,
                mat=material(m.get("mat", "Q345")), text=s.text())


# ─────────────────────────── Yield-line bản đầu (DG16) ───────────────────────────
def end_plate_Y(cfg, bp, g, pfi, pfo, pb, h0, h, de):
    s = 0.5 * math.sqrt(bp * g)
    pf = min(pfi, s)
    if cfg == "2FU":
        Y = bp / 2 * (h[0] * (1 / pf + 1 / s) - 0.5) + 2 / g * (h[0] * (pf + s))
        f = "Y = bp/2·[h1(1/pf + 1/s) − 1/2] + 2/g·[h1(pf + s)]   (DG16 Table 3-2)"
    elif cfg == "4FU":
        Y = bp / 2 * (h[0] / pf + h[1] / s - 0.5) + 2 / g * (h[0] * (pf + 0.75 * pb) + h[1] * (s + 0.25 * pb)) + g / 2
        f = "Y = bp/2·[h1/pf + h2/s − 1/2] + 2/g·[h1(pf + 0.75pb) + h2(s + 0.25pb)] + g/2   (DG16 Table 3-3)"
    elif cfg == "4E":
        Y = bp / 2 * (h[0] * (1 / pf + 1 / s) + h0 / pfo - 0.5) + 2 / g * (h[0] * (pf + s))
        f = "Y = bp/2·[h1(1/pf,i + 1/s) + h0(1/pf,o) − 1/2] + 2/g·[h1(pf,i + s)]   (DG16 Table 4-2)"
    elif cfg == "4ES":
        if s < de:
            Y = bp / 2 * (h[0] * (1 / pf + 1 / s) + h0 * (1 / s + 1 / pfo)) + 2 / g * (h[0] * (pf + s) + h0 * (s + pfo))
            f = "Case 1 (s < de): Y = bp/2·[h1(1/pf,i + 1/s) + h0(1/s + 1/pf,o)] + 2/g·[h1(pf,i + s) + h0(s + pf,o)]   (DG16 Table 4-3)"
        else:
            Y = bp / 2 * (h[0] * (1 / pf + 1 / s) + h0 * (1 / pfo + 1 / (2 * de))) + 2 / g * (h[0] * (pf + s) + h0 * (de + pfo))
            f = "Case 2 (s ≥ de): Y = bp/2·[h1(1/pf,i + 1/s) + h0(1/pf,o + 1/(2de))] + 2/g·[h1(pf,i + s) + h0(de + pf,o)]   (DG16 Table 4-3)"
    elif cfg == "MRE 1/2":
        Y = bp / 2 * (h[0] / pf + h[1] / s + h0 / pfo - 0.5) + 2 / g * (h[0] * (pf + 0.75 * pb) + h[1] * (s + 0.25 * pb)) + g / 2
        f = "Y = bp/2·[h1/pf,i + h2/s + h0/pf,o − 1/2] + 2/g·[h1(pf,i + 0.75pb) + h2(s + 0.25pb)] + g/2   (DG16 Table 4-4)"
    elif cfg == "MRE 1/3":
        Y = bp / 2 * (h[0] / pf + h[2] / s + h0 / pfo - 0.5) + 2 / g * (h[0] * (pf + 1.5 * pb) + h[2] * (s + 0.5 * pb)) + g / 2
        f = "Y = bp/2·[h1/pf,i + h3/s + h0/pf,o − 1/2] + 2/g·[h1(pf,i + 1.5pb) + h3(s + 0.5pb)] + g/2   (DG16 Table 4-5)"
    else:
        raise ValueError("Cấu hình bu lông không hỗ trợ: " + str(cfg))
    return dict(Y=Y, s=s, pf=pf, formula=f)


# ─────────────────────────── Yc phía gối (DG4 Table 3.4 / DG39 App. A) ───────────────────────────
def support_Yc(cond, b, g, rows, psiRaw=0.0, psoRaw=0.0, pcpRaw=0.0, de=0.0, stiff_between=False):
    s = 0.5 * math.sqrt(b * g)
    cap = lambda x: max(min(x, s), 1.0)
    note = ""
    if len(rows) == 1:
        h1 = rows[0]["d"]
        if cond == "cont_unstiff":
            Y = b * h1 / s + 4 * h1 * s / g
            f = "Yc = bcf·h1/s + 4h1·s/g   (DG39 Table A-1a)"
        elif cond == "cont_stiff":
            psi = cap(psiRaw)
            Y = b / 2 * h1 * (1 / psi + 1 / s) + 2 / g * h1 * (psi + s)
            f = f"Yc = bcf/2·h1(1/psi + 1/s) + 2/g·h1(psi + s)   (DG39 Table A-1b), psi = {psi:.1f}"
        elif cond == "top_unstiff":
            Y = b / 2 * (h1 / s - 0.5) + 2 / g * h1 * (s + de) + g / 4
            f = f"Yc = bcf/2·[h1/s − 1/2] + 2/g·h1(s + de) + g/4   (DG39 Table A-1c), de = {de:.1f}"
        elif cond == "top_cap":
            pcp = cap(pcpRaw)
            Y = b / 2 * h1 * (1 / pcp + 1 / s) + 2 / g * h1 * (pcp + s)
            f = f"Yc = bcf/2·h1(1/pcp + 1/s) + 2/g·h1(pcp + s)   (DG39 Table A-1d), pcp = {pcp:.1f}"
        else:
            raise ValueError("Điều kiện gối không hợp lệ: " + str(cond))
    else:
        srt = sorted(rows, key=lambda r: -r["d"])
        ho, hi = srt[0]["d"], srt[1]["d"]
        c = abs(srt[0]["s"] - srt[1]["s"])
        if len(rows) > 2:
            note = "Có > 2 hàng kéo: Yc chỉ tính với 2 hàng ngoài cùng (thiên về an toàn)."
        if cond == "cont_unstiff":
            Y = b / 2 * (hi / s + ho / s) + 2 / g * (hi * (s + 0.75 * c) + ho * (s + 0.25 * c) + c * c / 2) + g / 2
            f = f"Yc = bcf/2·[h1/s + h0/s] + 2/g·[h1(s + 3c/4) + h0(s + c/4) + c²/2] + g/2   (DG4 Table 3.4), c = {c:.1f}"
        elif cond == "cont_stiff":
            psi, pso = cap(psiRaw), cap(psoRaw)
            if stiff_between:
                Y = b / 2 * (hi * (1 / s + 1 / psi) + ho * (1 / s + 1 / pso)) + 2 / g * (hi * (s + psi) + ho * (s + pso))
                f = f"Yc = bcf/2·[h1(1/s + 1/psi) + h0(1/s + 1/pso)] + 2/g·[h1(s + psi) + h0(s + pso)]   (DG4 Table 3.4 có sườn), psi = {psi:.1f}, pso = {pso:.1f}"
            else:
                Y = b / 2 * (ho / psi + hi / s) + 2 / g * (ho * (psi + 0.25 * c) + hi * (s + 0.75 * c)) + g / 2
                f = "Yc = bcf/2·[hn/psi + hf/s] + 2/g·[hn(psi + c/4) + hf(s + 3c/4)] + g/2   (DG39 Table A-2b) [VERIFY]"
        elif cond == "top_unstiff":
            Y = b / 2 * (hi / s - 0.5) + 2 / g * (ho * (de + 0.25 * c) + hi * (s + 0.75 * c)) + 3 * g / 4
            f = f"Yc = bcf/2·[h1/s − 1/2] + 2/g·[h0(de + c/4) + h1(s + 3c/4)] + 3g/4   (DG39 Table A-2d) [VERIFY], de = {de:.1f}"
        elif cond == "top_cap":
            pcp = cap(pcpRaw)
            Y = b / 2 * (ho / pcp + hi / s) + 2 / g * (ho * (pcp + 0.25 * c) + hi * (s + 0.75 * c)) + g / 2
            f = f"Yc = bcf/2·[h0/pcp + h1/s] + 2/g·[h0(pcp + c/4) + h1(s + 3c/4)] + g/2   (DG39 Table A-2e) [VERIFY], pcp = {pcp:.1f}"
        else:
            raise ValueError("Điều kiện gối không hợp lệ: " + str(cond))
    return dict(Y=Y, s=s, formula=f, note=note)


# ─────────────────────────── Kennedy hiệu chỉnh (DG16) ───────────────────────────
def kennedy(t, Fy, b, db, Fnt, pfi, pfo=None, edgeOut=0.0):
    wc = b / 2 - (db + IN / 16)
    a = max(IN * (3.682 * (t / db) ** 3 - 0.085), 0.1)
    Fi = (t * t * Fy * (0.85 * b / 2 + 0.8 * wc) + math.pi * db ** 3 * Fnt / 8) / (4 * pfi)
    radI = Fy * Fy - 3 * (Fi / (wc * t)) ** 2
    Qi = wc * t * t / (4 * a) * math.sqrt(radI) if radI > 0 else NAN
    ao = Fo = Qo = None
    if pfo:
        ao = min(a, edgeOut)
        Fo = Fi * pfi / pfo
        radO = Fy * Fy - 3 * (Fo / (wc * t)) ** 2
        Qo = wc * t * t / (4 * ao) * math.sqrt(radO) if radO > 0 else NAN
    return dict(wc=wc, a=a, Fi=Fi, Qi=Qi, ao=ao, Fo=Fo, Qo=Qo)


def bolt_moments(ext, d0, inner, Pt, Tb, Qi, Qo):
    sumD = (d0 or 0.0) + sum(inner)
    Mnp = 2 * Pt * sumD
    if ext:
        d1 = inner[0] if len(inner) > 0 else 0.0
        d2 = inner[1] if len(inner) > 1 else 0.0
        d3 = inner[2] if len(inner) > 2 else 0.0
        po, pi = Pt - (Qo if Qo is not None else 0), Pt - Qi
        cases = [
            (2 * po * d0 + 2 * pi * (d1 + d3) + 2 * Tb * d2, "2(Pt−Qo)d0 + 2(Pt−Qi)(d1+d3) + 2Tb·d2"),
            (2 * po * d0 + 2 * Tb * (d1 + d2 + d3), "2(Pt−Qo)d0 + 2Tb(d1+d2+d3)"),
            (2 * pi * (d1 + d3) + 2 * Tb * (d0 + d2), "2(Pt−Qi)(d1+d3) + 2Tb(d0+d2)"),
            (2 * Tb * (d0 + d1 + d2 + d3), "2Tb(d0+d1+d2+d3)"),
        ]
    else:
        ds = sum(inner)
        cases = [(2 * (Pt - Qi) * ds, "2(Pt−Qi)Σd"), (2 * Tb * ds, "2Tb·Σd")]
    bad = isnan(Qi) or (ext and isnan(Qo))
    best = max((c for c in cases if not isnan(c[0])), key=lambda c: c[0], default=(NAN, ""))
    return dict(Mnp=Mnp, Mq=NAN if bad else best[0], cases=cases, sumD=sumD)


# ─────────────────────────── Hình học knee ───────────────────────────
def build_geometry(inp: dict) -> dict:
    W: list[str] = []
    beam = member_at_joint(inp["beam"], "kèo")
    col = member_at_joint(inp["col"], "cột")
    typ = inp["type"]
    a = float(inp["beam"].get("slope") or 0.0)
    col_inner_straight = bool(inp["col"].get("innerStraight", False))
    c_in_tilt = 0.0 if col_inner_straight else col["beta"]
    c_out_tilt = col["beta"] if col_inner_straight else 0.0
    pl = inp["plate"]
    phiCE = phiCI = None
    b_in = a + beam["taper_sign"] * beam["beta"]        # hướng cánh trong kèo
    if typ == "dung":                                    # bản đứng 90°
        M1, M2 = beam, col
        thN = 0.0
        phiE, phiI = fold(a - thN), fold(b_in - thN)
    elif typ == "ngang":                                 # bản ngang trên đỉnh cột
        M1, M2 = col, beam
        thN = -90.0
        phiE, phiI = fold(c_out_tilt), fold(c_in_tilt)
    else:                                                # xiên — bản trên panel đỉnh cột
        M1, M2 = beam, col
        mode = pl.get("mitre", "perp")
        thN = (90 + a) / 2 if mode == "bisector" else (a + beam["taper_sign"] * beam["beta"] / 2 if mode == "perp" else float(pl.get("theta", 0)))
        phiE, phiI = fold(a - thN), fold(b_in - thN)
        phiCE, phiCI = fold(90 - c_out_tilt - thN), fold(90 - c_in_tilt - thN)
    for p in (phiE, phiI):
        if p > 60:
            raise ValueError(f"Góc giữa cánh và pháp tuyến bản quá lớn ({p:.1f}°) — kiểm tra góc dốc / kiểu knee.")

    cE, cI = cosd(phiE), cosd(phiI)
    dp = M1["d"] / cE
    tfe, tfi = M1["tfE"] / cE, M1["tfI"] / cI
    dm = dp - tfe / 2 - tfi / 2
    phiA = (phiE + phiI) / 2

    rowsE, rowsI = [], []
    if pl["extE"]: rowsE.append(dict(s=-pl["pfoE"], outer=True, grp="E"))
    for k in range(int(pl["nE"])): rowsE.append(dict(s=tfe + pl["pfiE"] + k * pl["pbE"], outer=False, grp="E"))
    if pl["extI"]: rowsI.append(dict(s=dp + pl["pfoI"], outer=True, grp="I"))
    for k in range(int(pl["nI"])): rowsI.append(dict(s=dp - tfi - pl["pfiI"] - k * pl["pbI"], outer=False, grp="I"))
    sTop = -(pl["pfoE"] + pl["Lev"]) if pl["extE"] else -pl["flushExt"]
    sBot = dp + pl["pfoI"] + pl["Lev"] if pl["extI"] else dp + pl["flushExt"]
    bp = pl["g"] + 2 * pl["Leh"]

    dpc = tfce = tfci = dmc = None
    if phiCE is not None and "endplate" in (inp["sup"]["condE"], inp["sup"]["condI"]):
        if max(phiCE, phiCI) > 60:
            W.append("Knee xiên với điều kiện 'bản đầu cột': cánh cột gần song song với bản — nên dùng mô hình panel (cánh liên tục).")
        dpc = M2["d"] / max(cosd(phiCE), 0.2)
        tfce, tfci = M2["tfE"] / max(cosd(phiCE), 0.2), M2["tfI"] / max(cosd(phiCI), 0.2)
        dmc = dpc - tfce / 2 - tfci / 2
        if abs(dpc - dp) / dp > 0.05:
            W.append(f"Knee xiên: chiều cao cột đo dọc bản ({dpc:.0f} mm) lệch > 5% so với kèo ({dp:.0f} mm).")
    # Panel zone: tiết diện gối tại nút, cho phép nhập bề dày riêng (bụng, cánh ngoài, bản gối)
    PZ = dict(M2)
    pz = inp.get("pz") or {}
    if pz.get("on"):
        PZ.update(tw=float(pz["tw"]), tfE=float(pz["tfo"]), tfI=float(pz["tfi"]), mat=material(pz.get("mat", M2["mat"]["name"])))
        PZ["hw"] = PZ["d"] - PZ["tfE"] - PZ["tfI"]
        PZ["tf"] = min(PZ["tfE"], PZ["tfI"])
        PZ["A"] = PZ["bfE"] * PZ["tfE"] + PZ["bfI"] * PZ["tfI"] + PZ["hw"] * PZ["tw"]
        if PZ["hw"] <= 0:
            raise ValueError("Panel zone: bề dày cánh lớn hơn chiều cao tiết diện.")
    PZ["label"] = "panel"
    return dict(W=W, type=typ, beam=beam, col=col, M1=M1, M2=M2, PZ=PZ, a=a, thN=thN, phiE=phiE, phiI=phiI, phiA=phiA,
                phiCE=phiCE, phiCI=phiCI, dp=dp, tfe=tfe, tfi=tfi, dm=dm, rowsE=rowsE, rowsI=rowsI, sTop=sTop,
                sBot=sBot, bp=bp, dpc=dpc, tfce=tfce, tfci=tfci, dmc=dmc, c_in_tilt=c_in_tilt, c_out_tilt=c_out_tilt,
                b_in=b_in)


def side_static(G, inp, side, bolt):
    pl, sup = inp["plate"], inp["sup"]
    T = side == "E"
    rows = [dict(r) for r in (G["rowsE"] if T else G["rowsI"])]
    ext = pl["extE"] if T else pl["extI"]
    n = int(pl["nE"] if T else pl["nI"])
    pfo, pfi, pb = (pl["pfoE"], pl["pfiE"], pl["pbE"]) if T else (pl["pfoI"], pl["pfiI"], pl["pbI"])
    compFace = G["dp"] if T else 0.0
    compCtr = G["dp"] - G["tfi"] / 2 if T else G["tfe"] / 2
    for r in rows:
        r["h"] = abs(compFace - r["s"]); r["d"] = abs(compCtr - r["s"])
    outer = next((r for r in rows if r["outer"]), None)
    inner = [r for r in rows if not r["outer"]]
    W = []
    st = pl["stiffE"] if T else pl["stiffI"]
    stiff = bool(st and st.get("on")) and ext
    if ext:
        cfg = {1: "4ES" if stiff else "4E", 2: "MRE 1/2", 3: "MRE 1/3"}.get(n)
        if stiff and n > 1:
            W.append(f"Sườn bản đầu chỉ hỗ trợ cho cấu hình 4ES — bỏ qua sườn với {cfg}."); stiff = False
    else:
        cfg = {1: "2FU", 2: "4FU"}.get(n)
    if not cfg:
        raise ValueError(f"Nhóm bu lông {'cánh ngoài' if T else 'cánh trong'}: cấu hình không hỗ trợ (flush tối đa 2 hàng, extended tối đa 3 hàng trong).")
    gam = 1.0 if ext else 1.25
    Fpy = G["plMat"]["Fy"]
    bf_t = G["M1"]["bfE"] if T else G["M1"]["bfI"]
    bpE = min(G["bp"], bf_t + IN)
    Yr = end_plate_Y(cfg, bpE, pl["g"], pfi, pfo, pb, outer["h"] if outer else 0.0, [r["h"] for r in inner], pl["Lev"])
    tp = pl["tp"]
    phiMpl = 0.9 * Fpy * tp * tp * Yr["Y"]
    ken = kennedy(tp, Fpy, bpE, bolt["db"], bolt["Fnt"], pfi, pfo if ext else None, pl["Lev"])
    bm = bolt_moments(ext, outer["d"] if outer else None, [r["d"] for r in inner], bolt["Pt"], bolt["Tb"], ken["Qi"], ken["Qo"])
    phiMnp, phiMq = 0.75 * bm["Mnp"], 0.75 * bm["Mq"]
    thick = phiMnp < 0.9 * phiMpl

    cond = sup["condE"] if T else sup["condI"]
    M2 = G["PZ"]
    ts = M2["tfI"] if sup["useFlange"] else sup["t"]
    bs = M2["bfI"] if sup["useFlange"] else sup["b"]
    sMat = M2["mat"] if sup["useFlange"] else G["supMat"]
    S = dict(cond=cond, ts=ts, bs=bs, mat=sMat)
    if cond == "endplate":
        bsE = min(bs, M2["bf"] + IN)
        Ys = end_plate_Y(cfg, bsE, pl["g"], pfi, pfo, pb, outer["h"] if outer else 0.0, [r["h"] for r in inner], pl["Lev"])
        S.update(Y=Ys, bEff=bsE, phiM=0.9 * sMat["Fy"] * ts * ts * Ys["Y"] / gam, ref="DG16 Sec 2.5")
    else:
        fc = G["tfe"] / 2 if T else G["dp"] - G["tfi"] / 2
        stS = sup["stE"] if T else sup["stI"]
        tst = stS["ts"] if stS and stS.get("on") else 0.0
        psiRaw = abs(inner[0]["s"] - fc) - tst / 2
        psoRaw = abs(outer["s"] - fc) - tst / 2 if outer else psiRaw
        sEnd = G["sTop"] - float(sup.get("topOffset") or 0)
        nearest = min(rows, key=lambda r: abs(r["s"] - sEnd))
        pcpRaw = abs(nearest["s"] - (sEnd + float(sup.get("tcap") or 0)))
        de = abs(nearest["s"] - sEnd)
        if cond == "cont_stiff" and not (stS and stS.get("on")):
            W.append(f"Chọn 'cánh liên tục có sườn' nhưng chưa khai báo sườn ngang tại cánh {'ngoài' if T else 'trong'}.")
        Ys = support_Yc(cond, bs, pl["g"], rows, psiRaw, psoRaw, pcpRaw, de, stiff_between=outer is not None)
        if Ys["note"]: W.append(Ys["note"])
        S.update(Y=Ys, bEff=bs, phiM=0.9 * sMat["Fy"] * ts * ts * Ys["Y"], ref="DG4 Eq. 3.21")
    S["ken"] = kennedy(ts, sMat["Fy"], S["bEff"], bolt["db"], bolt["Fnt"], pfi, pfo if ext else None, pl["Lev"])
    S["bm"] = bolt_moments(ext, outer["d"] if outer else None, [r["d"] for r in inner], bolt["Pt"], bolt["Tb"], S["ken"]["Qi"], S["ken"]["Qo"])
    S["phiMq"] = 0.75 * S["bm"]["Mq"]
    return dict(side=side, T=T, cfg=cfg, ext=ext, n=n, rows=rows, outer=outer, inner=inner, pfo=pfo, pfi=pfi, pb=pb,
                gam=gam, Fpy=Fpy, bpE=bpE, Yr=Yr, phiMpl=phiMpl, ken=ken, bm=bm, phiMnp=phiMnp, phiMq=phiMq,
                thick=thick, stiff=stiff, S=S, W=W)


# ─────────────────────────── định dạng ───────────────────────────
def kN(x): return x / 1e3
def kNm(x): return x / 1e6
def f1(x): return "—" if isnan(x) else f"{x:.1f}"
def f2(x): return "—" if isnan(x) else f"{x:.2f}"
def f3(x): return "—" if isnan(x) else f"{x:.3f}"


# ═══════════════════════════ TÍNH TOÁN CHÍNH ═══════════════════════════
IN16 = IN / 16.0          # 1/16 in (đơn vị cỡ hàn của RAM Connection)
EXT_MAP = {"flush": (False, False), "external": (True, False), "internal": (False, True), "both": (True, True)}
ALIGN_TYPE = {"vertical": ("dung", None), "perpendicular": ("xien", "perp"), "horizontal": ("ngang", None), "bisector": ("xien", "bisector")}


def normalize(inp: dict) -> dict:
    """Đồng bộ các trường kiểu RAM Connection → trường engine (sửa tại chỗ, trả về inp).
       • plate.extension  → plate.extE / extI
       • plate.alignment  → type (+ plate.mitre)
       • stiff (1 bộ sườn ngang như RAM) + stiff.at → sup.stE / sup.stI
       • sup.useFlange = False (RAM knee luôn có connection plate)"""
    pl = inp["plate"]
    if pl.get("extension") in EXT_MAP:
        pl["extE"], pl["extI"] = EXT_MAP[pl["extension"]]
    if pl.get("alignment") in ALIGN_TYPE:
        t, m = ALIGN_TYPE[pl["alignment"]]
        inp["type"] = t
        if m: pl["mitre"] = m
    wd = inp.get("weld", {})
    for k in ("flE", "flI", "web"):
        if k in wd and "D" in wd[k]:
            wd[k]["w"] = float(wd[k]["D"]) * IN16
    sup = inp["sup"]
    if "extension" in pl:                       # bộ thông số kiểu RAM: luôn có connection plate
        sup["useFlange"] = False
        if sup.get("bAuto", True):
            sup["b"] = pl["g"] + 2 * pl["Leh"]
        if inp.get("pz", {}).get("on"):
            inp["pz"]["tfi"] = sup["t"]
    st = inp.get("stiff")
    if st:
        at = st.get("at", "both")
        for key, side in (("stE", "external"), ("stI", "internal")):
            inp["sup"][key] = dict(on=bool(st.get("on", True)) and at in ("both", side), bs=st["bs"], ts=st["ts"], clip=st["cc"],
                                   mat=st.get("mat", "Q345"), wf=st["D"] * IN16, ww=st["D"] * IN16, fullDepth=bool(st.get("fullDepth", True)),
                                   electrode=st.get("electrode"))
    return inp


def compute(inp: dict) -> dict:
    normalize(inp)
    G = build_geometry(inp)
    W = G["W"]
    pl, sup, opt = inp["plate"], inp["sup"], inp["opt"]
    G["plMat"] = material(pl["mat"])
    G["supMat"] = material(sup["mat"])
    bg = BOLT_GRADES.get(inp["bolt"]["grade"], BOLT_GRADES["8.8"])
    db = int(inp["bolt"]["d"])
    Ab = math.pi * db * db / 4
    Tb = PRETENSION[bg["pre"]].get(db, 0.7 * 0.7 * bg["Fnt"] * Ab / 1e3) * 1e3
    snugF = 1.0
    if inp["bolt"].get("snug"):
        snugF = 0.75 if db <= 16 else 0.5 if db <= 20 else 0.375 if db <= 22 else 0.25
        Tb *= snugF
        if bg["pre"] == "A490":
            W.append("Bu lông cấp A490/10.9 không được siết sơ bộ (snug-tight) — DG16 §2.5.3.")
    bolt = dict(grade=inp["bolt"]["grade"], bg=bg, db=db, Ab=Ab, Fnt=bg["Fnt"],
                Fnv=bg["FnvX"] if inp["bolt"].get("thread") == "X" else bg["FnvN"],
                Pt=bg["Fnt"] * Ab, Tb=Tb, snugF=snugF, dh=hole_dia(db))
    G["bolt"] = bolt
    weldF = ELECTRODES.get(inp["weld"]["electrode"], 482.6)
    dirF = 1.5 if opt.get("directional", True) else 1.0

    sides = {}
    for sd in ("E", "I"):
        try:
            sides[sd] = side_static(G, inp, sd, bolt); W.extend(sides[sd]["W"])
        except ValueError as e:
            sides[sd] = dict(error=str(e)); W.append(str(e))

    checks: dict[str, dict] = {}
    order: list[str] = []

    def add(cid, grp, name, unit, ref, cap, dem, combo, detail, tags=(), info=False):
        ratio = abs(dem) / cap if cap and cap > 0 else (math.inf if dem > 0 or isnan(cap) else 0.0)
        if isnan(ratio): ratio = math.inf
        c = checks.get(cid)
        if c is None:
            c = checks[cid] = dict(id=cid, grp=grp, name=name, unit=unit, ref=ref, cap=cap, dem=dem, ratio=-1.0,
                                   combo=combo, detail=[], tags=list(tags), info=info)
            order.append(cid)
        if ratio > c["ratio"]:
            c.update(cap=cap, dem=dem, ratio=ratio, combo=combo, detail=detail() if callable(detail) else list(detail or []))

    M1, M2, PZ = G["M1"], G["M2"], G["PZ"]
    tp = pl["tp"]; Fpu = G["plMat"]["Fu"]; phiA = G["phiA"]
    nBE, nBI = 2 * len(G["rowsE"]), 2 * len(G["rowsI"])
    allRows = G["rowsE"] + G["rowsI"]

    # J3.10: xét biến dạng lỗ (J3-6a: 1.2/2.4) hoặc không (J3-6b: 1.5/3.0)
    kb1, kb2 = (1.2, 2.4) if opt.get("holeDef", True) else (1.5, 3.0)

    def bearing_group(rows, t, Fu, sLo, sHi):
        s = sorted(r["s"] for r in allRows)
        total, lines = 0.0, []
        for r in rows:
            i = s.index(r["s"])
            up = s[i] - s[i - 1] - bolt["dh"] if i > 0 else r["s"] - sLo - bolt["dh"] / 2
            dn = s[i + 1] - s[i] - bolt["dh"] if i < len(s) - 1 else sHi - r["s"] - bolt["dh"] / 2
            lc = max(min(up, dn), 0.0)
            rn = min(kb1 * lc * t * Fu, kb2 * db * t * Fu)
            total += 2 * rn
            lines.append(f"Hàng s = {f1(r['s'])} mm: lc = {f1(lc)} mm → Rn/bu lông = min({kb1}·lc·t·Fu; {kb2}·d·t·Fu) = {f1(kN(rn))} kN")
        return 0.75 * total, lines

    tsSup = PZ["tfI"] if sup["useFlange"] else sup["t"]
    supMatEff = PZ["mat"] if sup["useFlange"] else G["supMat"]
    bearE_p = bearing_group(G["rowsE"], tp, Fpu, G["sTop"], G["sBot"])
    bearI_p = bearing_group(G["rowsI"], tp, Fpu, G["sTop"], G["sBot"])
    sLoS, sHiS = G["sTop"], G["sBot"]
    if sup["useFlange"]:
        topC = sup["condE"].startswith("top_") or sup["condI"].startswith("top_")
        sLoS = G["sTop"] - float(sup.get("topOffset") or 0) if topC else -1e9
        sHiS = 1e9
    bearE_s = bearing_group(G["rowsE"], tsSup, supMatEff["Fu"], sLoS, sHiS)
    bearI_s = bearing_group(G["rowsI"], tsSup, supMatEff["Fu"], sLoS, sHiS)

    flangeSupport = not (sup["condE"] == "endplate" and sup["condI"] == "endplate")
    # connection plate (RAM) nằm trên cánh gối → lực tập trung truyền qua cả hai lớp
    tf2 = PZ["tfI"] if sup["useFlange"] else PZ["tfI"] + sup["t"]
    k2 = tf2 + float(sup.get("kw") or 0)
    h2 = PZ["hw"]
    tw2 = PZ["tw"]; Fy2 = PZ["mat"]["Fy"]
    sEnd = G["sTop"] - float(sup.get("topOffset") or 0)
    fcE, fcI = G["tfe"] / 2, G["dp"] - G["tfi"] / 2

    def flange_facts(f):
        w = inp["weld"]["flE"] if f == "E" else inp["weld"]["flI"]
        tfp = G["tfe"] if f == "E" else G["tfi"]
        N = tfp + (2 * w["w"] if w["type"] == "fillet" else 0)
        dist = (fcE if f == "E" else fcI) - sEnd
        return N, dist

    def web_yield(f):
        N, dist = flange_facts(f)
        Ct = 0.5 if dist < PZ["d"] else 1.0
        Rn = Ct * (6 * k2 + N + 2 * tp) * Fy2 * tw2
        return Rn, Ct, N, dist, f"φRn = 1.0·Ct·(6k + N + 2tp)·Fy·tw = 1.0·{Ct}·(6·{f1(k2)} + {f1(N)} + 2·{f1(tp)})·{Fy2:g}·{f1(tw2)}"

    def web_crip(f):
        N, dist = flange_facts(f)
        r = (tw2 / tf2) ** 1.5
        root = math.sqrt(E * Fy2 * tf2 / tw2)
        d = PZ["d"]
        if dist >= d / 2:
            Rn = 0.80 * tw2 ** 2 * (1 + 3 * (N / d) * r) * root; t = "0.80·tw²·[1 + 3(N/d)(tw/tf)^1.5]·√(E·Fy·tf/tw)  (J10-4)"
        elif N / d <= 0.2:
            Rn = 0.40 * tw2 ** 2 * (1 + 3 * (N / d) * r) * root; t = "0.40·tw²·[1 + 3(N/d)(tw/tf)^1.5]·√(E·Fy·tf/tw)  (J10-5a)"
        else:
            Rn = 0.40 * tw2 ** 2 * (1 + (4 * N / d - 0.2) * r) * root; t = "0.40·tw²·[1 + (4N/d − 0.2)(tw/tf)^1.5]·√(E·Fy·tf/tw)  (J10-5b)"
        return 0.75 * Rn, "φRn = 0.75·" + t

    def web_buck(f):
        N, dist = flange_facts(f)
        coef = 24 if dist >= PZ["d"] / 2 else 12
        Rn = coef * tw2 ** 3 * math.sqrt(E * Fy2) / h2
        return 0.9 * Rn, f"φRn = 0.9·{coef}·tw³·√(E·Fy)/h  (J10-8{', gần đầu cấu kiện ×0.5' if coef == 12 else ''}), h = {f1(h2)}"

    def stiff_cap(f):
        st = sup["stE"] if f == "E" else sup["stI"]
        if not st or not st.get("on"): return None
        stMat = material(st["mat"])
        bn = st["bs"] - st["clip"]
        Ast = 2 * bn * st["ts"]
        phiT = 0.9 * stMat["Fy"] * Ast
        # Nén (J4.4, cách tính của RAM Connection): bản sườn làm việc như thanh nén,
        # A = 2·bs·ts, r = ts/√12, KL = 0.75·(h − 2w)
        A = 2 * st["bs"] * st["ts"]
        r = st["ts"] / math.sqrt(12)
        Lc = max(h2 - 2 * st["wf"], 1.0)
        lam = 0.75 * Lc / r
        Fy = stMat["Fy"]
        Lw = 0.0
        if lam <= 25:
            Pn = Fy * A; pt = f"KL/r = {f1(lam)} ≤ 25 → Pn = Fy·Ag (J4-6)"
        else:
            Fe = math.pi ** 2 * E / lam ** 2
            Fcr = 0.658 ** (Fy / Fe) * Fy if lam <= 4.71 * math.sqrt(E / Fy) else 0.877 * Fe
            Pn = Fcr * A; pt = f"KL/r = 0.75·{f1(Lc)}/{f2(r)} = {f1(lam)} > 25 → Fcr (E3) = {f1(Fcr)} MPa"
        wFs = ELECTRODES.get(st.get("electrode"), weldF)
        qf = 0.75 * 0.6 * wFs * 0.707 * st["wf"] * dirF
        Lst = h2 if st.get("fullDepth", True) else h2 / 2
        qw = 0.75 * 0.6 * wFs * 0.707 * st["ww"]
        return dict(st=st, stMat=stMat, bn=bn, Ast=Ast, phiT=phiT, phiC=0.9 * Pn, pt=pt, A=A, Lw=Lw,
                    phiWF=qf * 4 * max(bn - st["wf"], 0), phiWW=qw * 4 * max(Lst - 2 * st["clip"] - 2 * st["ww"], 0), Lst=Lst)

    demands = []
    diag = sup.get("diag", {})
    isN = G["type"] == "ngang"
    for ci, cb in enumerate(inp.get("loads", [])):
        g = lambda k: float(cb.get(k) or 0.0)
        N = (g("Nc") if isN else g("Nb")) * 1e3
        V = (g("Vc") if isN else g("Vb")) * 1e3
        M = (g("Mc") if isN else g("Mb")) * 1e6
        N2 = (g("Nb") if isN else g("Nc")) * 1e3
        V2 = (g("Vb") if isN else g("Vc")) * 1e3
        nm = cb.get("name") or f"TH{ci + 1}"
        Nn = N * cosd(phiA) + abs(V) * sind(phiA)
        Vt = abs(N) * sind(phiA) + abs(V) * cosd(phiA)
        FnE = -M / G["dm"] + Nn / 2
        FnI = M / G["dm"] + Nn / 2
        Nrel = Nn if opt.get("axialRelief", True) else max(Nn, 0.0)
        Mu = max(abs(M) + Nrel * G["dm"] / 2, 0.0)
        side = "E" if M < 0 else "I" if M > 0 else None
        Vpz = max(abs(FnE), abs(FnI)) - (abs(V2) if opt.get("pzSubtractShear") else 0.0)
        demands.append(dict(name=nm, V=kN(V), N=kN(N), M=kNm(M), Nn=kN(Nn), Vt=kN(Vt), FnE=kN(FnE), FnI=kN(FnI),
                            Mu=kNm(Mu), side=side, Vpz=kN(Vpz), N2=kN(N2), V2=kN(V2)))

        # ---------- Bản đầu + bu lông (phía kéo) ----------
        if side and "error" not in sides[side]:
            S = sides[side]
            gname = "Bản đầu — nhóm cánh ngoài" if side == "E" else "Bản đầu — nhóm cánh trong"
            common = lambda S=S: [
                f"Cấu hình: {S['cfg']} ({'extended' if S['ext'] else 'flush'}),  γr = {S['gam']}",
                f"Mu,eq = |M| + Nn·dm/2 = {f2(kNm(abs(M)))} + {f2(kN(Nrel))}·{f1(G['dm'])}/2/1000 = {f2(kNm(Mu))} kN·m",
                "Hàng bu lông kéo (h từ mặt ngoài cánh nén; d từ tâm cánh nén): " + " | ".join(
                    f"{'ngoài' if r['outer'] else 'trong'} h={f1(r['h'])}, d={f1(r['d'])}" for r in S["rows"]),
            ]
            add("pl_flex_" + side, gname, "Chảy dẻo uốn bản đầu", "kN·m", "DG16 Sec 2.5", kNm(S["phiMpl"] / S["gam"]), kNm(Mu), nm,
                lambda S=S: common() + [
                    f"bp,eff = min(bp; bf + 25.4) = min({f1(G['bp'])}; {f1((M1['bfE'] if S['T'] else M1['bfI']) + IN)}) = {f1(S['bpE'])} mm,  s = ½√(bp·g) = {f1(S['Yr']['s'])} mm",
                    S["Yr"]["formula"], f"Y = {f1(S['Yr']['Y'])} mm",
                    f"φb·Mpl = 0.9·Fpy·tp²·Y = 0.9·{S['Fpy']:g}·{tp:g}²·{f1(S['Yr']['Y'])} = {f2(kNm(S['phiMpl']))} kN·m",
                    f"Khả năng = φb·Mpl/γr = {f2(kNm(S['phiMpl'] / S['gam']))} kN·m",
                    "Ứng xử bản: " + ("BẢN DÀY (φMnp < 0.9φbMpl) — không nhổ" if S["thick"] else "BẢN MỎNG (φMnp ≥ 0.9φbMpl) — có lực nhổ"),
                    f"tp,req (bản mỏng) = √(γr·Mu/(φb·Fpy·Y)) = {f1(math.sqrt(S['gam'] * Mu / (0.9 * S['Fpy'] * S['Yr']['Y'])))} mm",
                ], ("plate",))
            add("bolt_np_" + side, gname, "Đứt bu lông không nhổ (φMnp)", "kN·m", "DG16 Sec 2.5 / DG4 Eq. 3.7", kNm(S["phiMnp"]), kNm(Mu), nm,
                lambda S=S: common() + [
                    f"Pt = Fnt·Ab = {bg['Fnt']:g}·{f1(Ab)} = {f1(kN(bolt['Pt']))} kN", f"Σd = {f1(S['bm']['sumD'])} mm",
                    f"φMnp = 0.75·2·Pt·Σd = {f2(kNm(S['phiMnp']))} kN·m",
                    f"db,req = √(2Mu/(π·φ·Fnt·Σd)) = {f1(math.sqrt(2 * Mu / (math.pi * 0.75 * bolt['Fnt'] * S['bm']['sumD'])))} mm",
                ], ("bolts" + side,))
            add("bolt_q_" + side, gname, "Đứt bu lông có lực nhổ (φMq)", "kN·m", "DG16 Sec 2.5 (Kennedy hiệu chỉnh)", kNm(S["phiMq"]), kNm(Mu), nm,
                lambda S=S: common() + [
                    f"w' = bp/2 − (db + 1/16\") = {f1(S['ken']['wc'])} mm;  ai = 3.682(tp/db)³ − 0.085 [in] = {f2(S['ken']['a'])} mm",
                    f"F'i = [tp²·Fpy(0.85bp/2 + 0.8w') + π·db³·Fnt/8]/(4pf,i) = {f1(kN(S['ken']['Fi']))} kN",
                    f"Qmax,i = w'tp²/(4ai)·√(Fpy² − 3(F'i/(w'tp))²) = {f1(kN(S['ken']['Qi']))} kN",
                    (f"ao = min(ai; pext − pf,o) = {f2(S['ken']['ao'])} mm;  F'o = F'i·pf,i/pf,o = {f1(kN(S['ken']['Fo']))} kN;  Qmax,o = {f1(kN(S['ken']['Qo']))} kN") if S["ext"] else "Flush: không có hàng ngoài",
                    f"Pt = {f1(kN(bolt['Pt']))} kN;  Tb = {f1(kN(bolt['Tb']))} kN" + (f" (siết sơ bộ ×{bolt['snugF']})" if inp['bolt'].get('snug') else ""),
                ] + [f"  {t} = {f2(kNm(v))} kN·m" for v, t in S["bm"]["cases"]] + [
                    f"φMq = 0.75·max(...) = {f2(kNm(S['phiMq']))} kN·m" + ("  → căn âm: bản phá hoại do uốn + cắt kết hợp, cần tăng tp" if isnan(S["phiMq"]) else "")],
                ("bolts" + side, "plate"))
            Sg = S["S"]
            sgname = f"Phía gối ({'kèo' if isN else 'cột'}) — {'cánh ngoài' if side == 'E' else 'cánh trong'}"
            add("sup_flex_" + side, sgname, "Chảy dẻo uốn bản đầu cột" if Sg["cond"] == "endplate" else "Chảy dẻo uốn cánh/bản gối", "kN·m", Sg["ref"],
                kNm(Sg["phiM"]), kNm(Mu), nm, lambda Sg=Sg: [
                    f"Điều kiện: {COND_LABEL[Sg['cond']]};  t = {f1(Sg['ts'])} mm; b = {f1(Sg['bEff'])} mm; Fy = {Sg['mat']['Fy']:g} MPa",
                    Sg["Y"]["formula"], f"Y = {f1(Sg['Y']['Y'])} mm",
                    (f"φMpl/γr = 0.9·Fy·t²·Y/γr = {f2(kNm(Sg['phiM']))} kN·m") if Sg["cond"] == "endplate" else f"φMcf = 0.9·Fyc·tcf²·Yc = {f2(kNm(Sg['phiM']))} kN·m",
                    f"Mu,eq = {f2(kNm(Mu))} kN·m"], ("support" + side,))
            add("sup_q_" + side, sgname, "Đứt bu lông có lực nhổ (phía gối)", "kN·m", "DG16 Sec 2.5", kNm(Sg["phiMq"]), kNm(Mu), nm,
                lambda Sg=Sg, S=S: [f"t = {f1(Sg['ts'])} mm, b = {f1(Sg['bEff'])} mm, Fy = {Sg['mat']['Fy']:g}",
                                    f"Qmax,i = {f1(kN(Sg['ken']['Qi']))} kN" + (f";  Qmax,o = {f1(kN(Sg['ken']['Qo']))} kN" if S["ext"] else "")]
                + [f"  {t} = {f2(kNm(v))} kN·m" for v, t in Sg["bm"]["cases"]] + [f"φMq = {f2(kNm(Sg['phiMq']))} kN·m"],
                ("support" + side, "bolts" + side))

        # ---------- Cắt / ép mặt bu lông ----------
        grp = "I" if side == "E" else "E" if side == "I" else "A"
        allb = opt.get("shearAll") or grp == "A"
        idg = "A" if allb else grp
        nB = nBE + nBI if allb else (nBE if grp == "E" else nBI)
        phiRv = 0.75 * bolt["Fnv"] * Ab * nB
        gn = "Bu lông (toàn bộ)" if allb else ("Bản đầu — nhóm cánh ngoài" if grp == "E" else "Bản đầu — nhóm cánh trong")
        add("bolt_v_" + idg, gn, "Bu lông chịu cắt", "kN", "AISC J3.6 (Table J3.2)", kN(phiRv), kN(Vt), nm, lambda: [
            f"Lực cắt dọc bản Vt = |N|·sinφ + |V|·cosφ = {f2(kN(Vt))} kN  (φ = {f1(phiA)}°)",
            f"Bu lông chịu cắt: {'toàn bộ' if allb else 'nhóm phía nén'}, n = {nB}",
            f"φRn = 0.75·Fnv·Ab·n = 0.75·{f1(bolt['Fnv'])}·{f1(Ab)}·{nB} = {f2(kN(phiRv))} kN"],
            ("boltsE", "boltsI") if idg == "A" else ("bolts" + idg,))
        useE, useI = idg in ("E", "A"), idg in ("I", "A")
        capP = (bearE_p[0] if useE else 0) + (bearI_p[0] if useI else 0)
        capS = (bearE_s[0] if useE else 0) + (bearI_s[0] if useI else 0)
        add("bear_p_" + idg, gn, "Ép mặt / xé bu lông trên bản đầu", "kN", "AISC Eq. J3-6", kN(capP), kN(Vt), nm,
            lambda: [f"t = tp = {tp:g} mm, Fu = {Fpu:g} MPa (lc lấy theo chiều bất lợi)"] + (bearE_p[1] if useE else []) + (bearI_p[1] if useI else []) + [f"φRn = 0.75·Σ(2·Rn) = {f2(kN(capP))} kN"], ("plate",))
        add("bear_s_" + idg, gn.replace("Bản đầu", "Phía gối"), "Ép mặt / xé bu lông trên bản gối", "kN", "AISC Eq. J3-6", kN(capS), kN(Vt), nm,
            lambda: [f"t = {tsSup:g} mm, Fu = {supMatEff['Fu']:g} MPa"] + (bearE_s[1] if useE else []) + (bearI_s[1] if useI else []) + [f"φRn = {f2(kN(capS))} kN"], ("supportE", "supportI"))

        # ---------- Cắt bản đầu tại cánh (DG4 3.12, 3.13) ----------
        for f in ("E", "I"):
            Fn = FnE if f == "E" else FnI
            gname = "Bản đầu — nhóm cánh ngoài" if f == "E" else "Bản đầu — nhóm cánh trong"
            Rv = 0.9 * 0.6 * G["plMat"]["Fy"] * G["bp"] * tp
            add("pl_vy_" + f, gname, "Cắt chảy bản đầu (Ffu/2)", "kN", "DG4 Eq. 3.12", kN(Rv), kN(abs(Fn) / 2), nm, lambda Fn=Fn, Rv=Rv: [
                f"Ffu = |M|/dm ± Nn/2 = {f2(kN(abs(Fn)))} kN",
                f"φRn = 0.9·0.6·Fpy·bp·tp = 0.9·0.6·{G['plMat']['Fy']:g}·{f1(G['bp'])}·{tp:g} = {f2(kN(Rv))} kN"], ("plate",))
            extF = pl["extE"] if f == "E" else pl["extI"]
            if extF and Fn > 0 and "error" not in sides[f] and not sides[f]["stiff"]:
                An = (G["bp"] - 2 * (bolt["dh"] + 2)) * tp
                Rr = 0.75 * 0.6 * Fpu * An
                add("pl_vr_" + f, gname, "Cắt đứt phần bản nhô (Ffu/2)", "kN", "DG4 Eq. 3.13", kN(Rr), kN(Fn / 2), nm, lambda An=An, Rr=Rr: [
                    f"An = [bp − 2(dh + 2)]·tp = [{f1(G['bp'])} − 2({bolt['dh']} + 2)]·{tp:g} = {f1(An)} mm²",
                    f"φRn = 0.75·0.6·Fpu·An = {f2(kN(Rr))} kN"], ("plate",))

        # ---------- Hàn & bụng cấu kiện có bản ----------
        def member_welds(mem, key, FE, FI, phE, phI, dpL, tfeL, tfiL, label, tagm):
            for f in ("E", "I"):
                Fn = FE if f == "E" else FI
                if Fn <= 0: continue
                ph = phE if f == "E" else phI
                w = inp["weld"]["flE"] if f == "E" else inp["weld"]["flI"]
                bf_, tf_ = (mem["bfE"], mem["tfE"]) if f == "E" else (mem["bfI"], mem["tfI"])
                Ff = Fn / cosd(ph)
                Fmin = 0.6 * mem["mat"]["Fy"] * bf_ * tf_
                if opt.get("flangeWeldMin"): Ff = max(Ff, Fmin)
                nm2 = f"Hàn cánh {'ngoài' if f == 'E' else 'trong'} — bản đầu"
                if w["type"] == "cjp":
                    cap = 0.9 * mem["mat"]["Fy"] * bf_ * tf_
                    add(f"{key}_wf_{f}", label, nm2 + " (CJP)", "kN", "AISC Table J2.5 / J4.1", kN(cap), kN(Ff), nm, lambda cap=cap, Fn=Fn, ph=ph, bf_=bf_, tf_=tf_: [
                        f"Hàn thấu CJP: khả năng = φ·Fy·bf·tf = 0.9·{mem['mat']['Fy']:g}·{bf_:g}·{tf_:g} = {f2(kN(cap))} kN",
                        f"Lực cánh theo phương cánh = Fn/cosφ = {f2(kN(Fn))}/cos{f1(ph)}° = {f2(kN(Fn / cosd(ph)))} kN"], (tagm + "weld" + f,))
                else:
                    Lw = 2 * bf_ - mem["tw"]
                    wFf = ELECTRODES.get(w.get("electrode"), weldF)
                    cap = 0.75 * 0.6 * wFf * dirF * 0.707 * w["w"] * Lw
                    add(f"{key}_wf_{f}", label, nm2 + " (hàn góc)", "kN", "AISC Eq. J2-4, J2-5", kN(cap), kN(Ff), nm, lambda cap=cap, Lw=Lw, w=w, Ff=Ff: [
                        f"Lw = 2bf − tw = {f1(Lw)} mm;  w = {w['w']:g} mm ({f1(w['w'] / IN * 16)}/16\"),  FEXX = {weldF:g} MPa",
                        f"φRn = 0.75·0.6·FEXX·{dirF:g}·0.707·w·Lw = {f2(kN(cap))} kN",
                        f"Lực cánh theo phương cánh = Fn/cosφ = {f2(kN(Ff))} kN"], (tagm + "weld" + f,))
            ww = inp["weld"]["web"]["w"]
            wFw = ELECTRODES.get(inp["weld"]["web"].get("electrode"), weldF)
            qdem = 0.9 * mem["mat"]["Fy"] * mem["tw"]
            qcap = 2 * 0.75 * 0.6 * wFw * 0.707 * ww * dirF
            if abs(M) > 0:
                add(key + "_ww_t", label, "Hàn bụng vùng kéo (phát triển chảy bụng)", "kN/m", "AISC Eq. J2-4; J4-1", qcap, qdem, nm, lambda: [
                    f"Yêu cầu = φ·Fy·tw = 0.9·{mem['mat']['Fy']:g}·{mem['tw']:g} = {f1(qdem)} N/mm (kN/m)",
                    f"Khả năng 2 đường hàn góc: 2·0.75·0.6·FEXX·0.707·w·{dirF:g} = {f1(qcap)} N/mm"], (tagm + "webweld",))
            sd = side or "E"
            Sx = sides[sd] if "error" not in sides[sd] else None
            Lws = dpL / 2 - (tfiL if sd == "E" else tfeL)
            if Sx:
                last = Sx["inner"][-1]
                compInner = dpL - tfiL if sd == "E" else tfeL
                Lws = min(Lws, abs(compInner - last["s"]) - 2 * db)
            Lws = max(Lws, 0.0)
            capV = 2 * 0.75 * 0.6 * wFw * 0.707 * ww * Lws
            add(key + "_ww_v", label, "Hàn bụng chịu cắt", "kN", "AISC Eq. J2-4", kN(capV), kN(Vt), nm, lambda: [
                f"Chiều dài hàn hiệu quả (DG16 §2.5.3 item 10): min(d/2 − tf,c ; từ hàng kéo trong + 2db tới cánh nén) = {f1(Lws)} mm",
                f"φRn = 2·0.75·0.6·FEXX·0.707·w·L = {f2(kN(capV))} kN"], (tagm + "webweld",))
            capWV = 1.0 * 0.6 * mem["mat"]["Fy"] * dpL * mem["tw"]
            add(key + "_wv", label, f"Chảy cắt bụng {'cấu kiện' if key == 'm1' else 'cột'} tại bản", "kN", "AISC Eq. J4-3", kN(capWV), kN(Vt), nm, lambda: [
                f"φRn = 1.0·0.6·Fy·d·tw = 0.6·{mem['mat']['Fy']:g}·{f1(dpL)}·{mem['tw']:g} = {f2(kN(capWV))} kN"], (tagm + "web",))

        member_welds(M1, "m1", FnE, FnI, G["phiE"], G["phiI"], G["dp"], G["tfe"], G["tfi"],
                     f"{'Cột' if isN else 'Kèo'} (cấu kiện có bản đầu)", "m1")
        if G["dmc"]:
            member_welds(M2, "m2", -M / G["dmc"] + Nn / 2, M / G["dmc"] + Nn / 2, G["phiCE"], G["phiCI"], G["dpc"],
                         G["tfce"], G["tfci"], "Cột (bản đầu phía cột)", "m2")

        # ---------- J10, sườn, panel ----------
        if flangeSupport:
            glab = f"Bụng cấu kiện gối ({'kèo' if isN else 'cột'})"
            for f in ("E", "I"):
                Fn = FnE if f == "E" else FnI
                Fa = abs(Fn)
                if Fa <= 0: continue
                stc = stiff_cap(f)
                fl = "cánh ngoài" if f == "E" else "cánh trong"
                wyR, Ct, Nb_, dist, wyT = web_yield(f)
                caps = [("chảy cục bộ bụng", wyR)]
                add("j10y_" + f, glab, "Chảy cục bộ bụng tại " + fl, "kN", "AISC J10.2 / DG4 Eq. 3.24", kN(wyR), kN(Fa), nm, lambda wyR=wyR, Ct=Ct, Nb_=Nb_, dist=dist, wyT=wyT, Fa=Fa, stc=stc: [
                    f"Khoảng cách tới đầu cấu kiện = {f1(dist)} mm → Ct = {Ct};  k = tf + hàn = {f1(k2)} mm;  N = {f1(Nb_)} mm",
                    wyT + f" = {f2(kN(wyR))} kN",
                    f"Lực cánh Ffu = {f2(kN(Fa))} kN" + ("  (có sườn → xem kiểm tra sườn)" if stc else "")], ("sup" + f + "web",), bool(stc))
                if Fn < 0:
                    wcR, wcT = web_crip(f); wbR, wbT = web_buck(f)
                    caps.append(("oằn nhàu", wcR))
                    if opt.get("webBuckling", True):
                        caps.append(("oằn nén bụng", wbR))
                    add("j10c_" + f, glab, f"Oằn nhàu bụng tại {fl} (nén)", "kN", "AISC J10.3 / DG4 Eq. 3.29–3.31", kN(wcR), kN(Fa), nm, [wcT, f"= {f2(kN(wcR))} kN"], ("sup" + f + "web",), bool(stc))
                    if opt.get("webBuckling", True):
                        add("j10b_" + f, glab, f"Oằn nén bụng tại {fl} (nén)", "kN", "AISC J10.5 / DG4 Eq. 3.26", kN(wbR), kN(Fa), nm, [wbT, f"= {f2(kN(wbR))} kN"], ("sup" + f + "web",), bool(stc))
                elif side == f and "error" not in sides[f] and sides[f]["S"]["cond"] != "endplate":
                    caps.append(("uốn cánh gối", sides[f]["S"]["phiM"] / G["dm"]))
                mn = min(caps, key=lambda c: c[1])
                Fsu = max(Fa - mn[1], 0.0)
                if stc:
                    sn = "Sườn ngang gối tại " + fl
                    add("st_ax_" + f, sn, "Sườn — chảy do lực dọc (J4.1)", "kN", "AISC Eq. J4-1", kN(stc["phiT"]), kN(Fsu), nm,
                        lambda stc=stc, Fa=Fa, mn=mn, Fsu=Fsu: [
                            f"Fsu = Ffu − min(φRn) = {f2(kN(Fa))} − {f2(kN(mn[1]))} ({mn[0]}) = {f2(kN(Fsu))} kN   (DG4 Eq. 3.32)",
                            f"Sườn: 2 × {stc['st']['bs']:g}×{stc['st']['ts']:g} mm, vát góc {stc['st']['clip']:g} mm, {stc['stMat']['name']}",
                            f"φRn = 0.9·Fy·2(bs − cc)·ts = 0.9·{stc['stMat']['Fy']:g}·{f1(stc['Ast'])} = {f2(kN(stc['phiT']))} kN"], ("sup" + f + "stiff",))
                    if Fn < 0:
                        add("st_c_" + f, sn, "Sườn chịu nén (J4.4)", "kN", "AISC Sec. J4.4", kN(stc["phiC"]), kN(Fsu), nm,
                            lambda stc=stc, Fsu=Fsu: [f"Fsu = {f2(kN(Fsu))} kN", stc["pt"],
                                                      f"φPn = 0.9·Fcr·2bs·ts = {f2(kN(stc['phiC']))} kN  (A = {f1(stc['A'])} mm²)"], ("sup" + f + "stiff",))
                    add("st_wf_" + f, sn, "Hàn sườn – cánh", "kN", "AISC Eq. J2-4", kN(stc["phiWF"]), kN(Fsu), nm,
                        [f"4 đường hàn góc w = {stc['st']['wf']:g} mm, L = bs − cc − w = {f1(stc['bn'] - stc['st']['wf'])} mm → φRn = {f2(kN(stc['phiWF']))} kN"], ("sup" + f + "stiff",))
                    add("st_ww_" + f, sn, "Hàn sườn – bụng", "kN", "AISC Eq. J2-4", kN(stc["phiWW"]), kN(Fsu), nm,
                        [f"4 đường hàn góc w = {stc['st']['ww']:g} mm, L = {f1(stc['Lst'])} − 2·cc − 2·w → φRn = {f2(kN(stc['phiWW']))} kN"], ("sup" + f + "stiff",))

            Pc = Fy2 * PZ["A"]; Pr = abs(N2)
            red = 1.0 if Pr <= 0.4 * Pc else (1.4 - Pr / Pc)
            twP = tw2 + float(sup.get("doubler") or 0)
            Rv = 0.9 * 0.6 * Fy2 * PZ["d"] * twP * red
            dtxt = ""
            if diag.get("on"):
                th = math.atan(G["dm"] / PZ["d"])
                add2 = 0.9 * material(diag.get("mat", "Q345"))["Fy"] * 2 * diag["b"] * diag["t"] * math.cos(th)
                Rv += add2
                dtxt = f"Sườn chéo 2×{diag['b']:g}×{diag['t']:g}: + φ·Fy·Ad·cosθ = {f2(kN(add2))} kN (θ = {f1(th / D2R)}°)"
            add("pz", "Vùng panel", "Chảy cắt vùng panel", "kN", "AISC J10.6 (J10-9, J10-10)", kN(Rv), kN(Vpz), nm, lambda Rv=Rv, Vpz=Vpz, Pr=Pr, Pc=Pc, red=red, twP=twP, dtxt=dtxt: [
                f"Vu = max|Ffu|{' − |V cấu kiện gối|' if opt.get('pzSubtractShear') else ''} = {f2(kN(Vpz))} kN",
                ("Panel zone bề dày riêng: " + f"tw = {PZ['tw']:g}, cánh ngoài {PZ['tfE']:g}, bản gối {PZ['tfI']:g} mm, {PZ['mat']['name']}") if (inp.get("pz") or {}).get("on") else "Panel zone theo tiết diện gối",
                f"Pr = {f2(kN(Pr))} kN;  Pc = Fy·A = {f2(kN(Pc))} kN → hệ số = {f3(red)}",
                f"φRv = 0.9·0.6·Fy·dc·tw·hệ số = 0.9·0.6·{Fy2:g}·{f1(PZ['d'])}·{f1(twP)}·{f3(red)}"]
                + ([dtxt] if dtxt else []) + [f"φRv = {f2(kN(Rv))} kN"], ("panel",))

    # ---------- Kiểm tra cấu tạo ----------
    geo = []
    def gchk(grp, name, val, mn=None, mx=None, ref="", unit="mm"):
        ok = (mn is None or val >= mn - 1e-6) and (mx is None or val <= mx + 1e-6)
        geo.append(dict(grp=grp, name=name, val=val, min=mn, max=mx, ref=ref, unit=unit, ok=ok))
    emin = edge_min(db, opt.get("sheared", True))
    emax = min(12 * min(tp, tsSup), 150)
    gchk("Bản đầu", "Khoảng cách mép dọc bản Lev", pl["Lev"], emin, emax, "J3.4, J3.5")
    gchk("Bản đầu", "Khoảng cách mép ngang Leh", pl["Leh"], emin, emax, "J3.4, J3.5")
    gchk("Bản đầu", "Gage g", pl["g"], 2.667 * db, min(M1["bfE"], M1["bfI"]), "J3.3; DG16 §2.5.3-7")
    pmin = db + 12.7 if db <= 25.4 else db + 19.05
    if pl["extE"]: gchk("Bản đầu", "pf,o cánh ngoài", pl["pfoE"], pmin, None, "DG16 §2.5.3-4")
    gchk("Bản đầu", "pf,i cánh ngoài", pl["pfiE"], pmin, None, "DG16 §2.5.3-4")
    if pl["extI"]: gchk("Bản đầu", "pf,o cánh trong", pl["pfoI"], pmin, None, "DG16 §2.5.3-4")
    gchk("Bản đầu", "pf,i cánh trong", pl["pfiI"], pmin, None, "DG16 §2.5.3-4")
    if pl["extE"]: gchk("Bản đầu", "Hàng ngoài – hàng trong (cánh ngoài)", pl["pfoE"] + G["tfe"] + pl["pfiE"], 2.667 * db, None, "J3.3")
    if pl["nE"] > 1: gchk("Bản đầu", "Bước hàng pb (cánh ngoài)", pl["pbE"], 2.667 * db, None, "J3.3")
    if pl["nI"] > 1: gchk("Bản đầu", "Bước hàng pb (cánh trong)", pl["pbI"], 2.667 * db, None, "J3.3")
    lastE = [r for r in G["rowsE"] if not r["outer"]][-1:]
    lastI = [r for r in G["rowsI"] if not r["outer"]][-1:]
    if lastE and lastI:
        gchk("Bản đầu", "Khoảng trống giữa hai nhóm bu lông", lastI[0]["s"] - lastE[0]["s"], 2.667 * db, None, "J3.3")
    gchk("Bản đầu", "Đường kính bu lông", db, None, 38.1, "DG4 §1.1")
    if G["bp"] > min(M1["bfE"], M1["bfI"]) + IN + 1e-6:
        W.append(f"bp = {G['bp']:.0f} mm > bf + 25.4: tính toán dùng bề rộng hiệu quả bp,eff = bf + 25.4 (DG16 §2.5.3-6).")
    for f in ("E", "I"):
        w = inp["weld"]["flE"] if f == "E" else inp["weld"]["flI"]
        if w["type"] == "fillet":
            gchk("Hàn", f"Hàn góc cánh {'ngoài' if f == 'E' else 'trong'} ≥ min", w["w"], weld_min(min(M1["tfE"] if f == "E" else M1["tfI"], tp)), None, "Table J2.4")
    gchk("Hàn", "Hàn góc bụng ≥ min", inp["weld"]["web"]["w"], weld_min(min(M1["tw"], tp)), None, "Table J2.4")
    if flangeSupport:
        for f in ("E", "I"):
            st = sup["stE"] if f == "E" else sup["stI"]
            if not st or not st.get("on"): continue
            lab = f"Sườn gối {'cánh ngoài' if f == 'E' else 'cánh trong'}"
            gchk(lab, "bs + tw/2 ≥ bf/3", st["bs"] + tw2 / 2, PZ["bfI"] / 3, None, "J10.8")
            gchk(lab, "ts ≥ tf(kèo)/2", st["ts"], (G["tfe"] if f == "E" else G["tfi"]) / 2, None, "J10.8")
            gchk(lab, "ts ≥ bs/16", st["ts"], st["bs"] / 16, None, "J10.8")
            gchk(lab, "bs ≤ (bf − tw)/2", st["bs"], None, (min(PZ["bfE"], PZ["bfI"]) - tw2) / 2, "Hình học")
    for f in ("E", "I"):
        S = sides[f]
        if "error" in S or not S["stiff"]: continue
        st = pl["stiffE"] if f == "E" else pl["stiffI"]
        stMat = material(st.get("mat", "Q345"))
        hst = (pl["pfoE"] if f == "E" else pl["pfoI"]) + pl["Lev"]
        lab = f"Sườn bản đầu (4ES) {'ngoài' if f == 'E' else 'trong'}"
        gchk(lab, "ts ≥ tw·Fyb/Fys", st["ts"], M1["tw"] * M1["mat"]["Fy"] / stMat["Fy"], None, "DG4 Eq. 3.15")
        gchk(lab, "hst/ts ≤ 0.56√(E/Fys)", hst / st["ts"], None, 0.56 * math.sqrt(E / stMat["Fy"]), "DG4 Eq. 3.16", "")
        gchk(lab, "Lst ≥ hst/tan30°", st["L"], hst / math.tan(30 * D2R), None, "DG4 §2.4")

    lst = [checks[i] for i in order]
    gov = None
    for c in lst:
        if not c["info"] and (gov is None or c["ratio"] > gov["ratio"]):
            gov = c
    return dict(G=G, sides=sides, bolt=bolt, checks=lst, geo=geo, demands=demands, gov=gov, W=W,
                geoFail=sum(1 for x in geo if not x["ok"]), weldF=weldF)


# ─────────────────────────── Tự chọn tp / bu lông ───────────────────────────
TP_LIST = [10, 12, 14, 16, 18, 20, 22, 25, 28, 30, 32, 36, 40]


def auto_design(inp: dict, dias=(16, 20, 22, 24, 27, 30), tps=TP_LIST, progress: Optional[Callable] = None):
    """Thử tổ hợp (db, tp), chọn phương án nhẹ nhất (ưu tiên tp nhỏ rồi db nhỏ) đạt D/C ≤ 1
    ở các kiểm tra liên quan bản đầu / bu lông / phía gối và kiểm tra cấu tạo bản đầu."""
    import copy
    best = None
    for tp in tps:
        for d in dias:
            trial = copy.deepcopy(inp)
            trial["plate"]["tp"] = tp
            trial["bolt"]["d"] = d
            try:
                r = compute(trial)
            except Exception:
                continue
            rel = [c for c in r["checks"] if not c["info"] and (c["id"].startswith(("pl_", "bolt_", "bear_", "sup_")))]
            gfail = [g for g in r["geo"] if not g["ok"] and g["grp"] == "Bản đầu"]
            mx = max((c["ratio"] for c in rel), default=0.0)
            if mx <= 1.0 and not gfail:
                return dict(tp=tp, d=d, ratio=mx)
            if best is None or mx < best["ratio"]:
                best = dict(tp=tp, d=d, ratio=mx, fail=True)
        if progress: progress(tp)
    return best
