"""
splice_engine.py — Lõi tính liên kết NỐI DẦM bằng bản đầu bu lông (Beam splice / Apex)
=====================================================================================
AISC 360-10 (LRFD) + AISC Design Guide 4 (2003), Design Guide 16 (2002), Design Guide 39 (2023).

Dùng lại các hàm đã kiểm chứng của knee_app/engine.py: yield-line bản đầu (end_plate_Y), lực nhổ Kennedy hiệu chỉnh
(kennedy, bolt_moments), bảng vật liệu / bu lông / lỗ / mép, đọc tiết diện I tổ hợp (member_at_joint).

Mô hình: hai bản đầu áp vào nhau, bu lông xuyên cả hai bản. Mỗi bản có bề dày và vật liệu riêng (tp1/mat1, tp2/mat2).
Không có phía cột: bản 2 đóng vai "phía gối" — kiểm tra uốn và lực nhổ cho CẢ HAI bản, bu lông lấy theo bản bất lợi.

Quy ước dấu (nội lực tại mặt nối): N > 0 kéo · M > 0 → cánh DƯỚI chịu kéo (mô men dương) · M < 0 → cánh TRÊN chịu kéo.
Đơn vị nội bộ: N, mm, MPa. Nhập/xuất: kN, kN·m. Chiều dài thanh L: m.

Phạm vi / giả định (xem thêm README):
  • Thẳng (type = straight) và Apex (hai dầm nghiêng ±slope, bản đứng; nội lực quy đổi về hệ trục bản).
  • Hai dầm phải cùng chiều cao tiết diện tại mặt nối (±1 mm); bề dày cánh dầm 2 lệch dầm 1 chỉ dùng cho kiểm tra hàn.
  • Độ nghiêng cánh do tiết diện vát (tapered) bị bỏ qua khi quy đổi nội lực; có cảnh báo khi vát > 2°.
  • Không có kiểm tra phía cột, panel zone, sườn J10 (không có cột).
"""

from __future__ import annotations

import copy
import math
from typing import Callable, Optional

from _knee import K

E = K.E
IN = K.IN
IN16 = K.IN / 16.0
D2R = K.D2R
cosd, sind, isnan, fold = K.cosd, K.sind, K.isnan, K.fold
NAN = K.NAN
material, hole_dia, edge_min, weld_min = K.material, K.hole_dia, K.edge_min, K.weld_min
MATERIALS, BOLT_GRADES, BOLT_DIAS, ELECTRODES = K.MATERIALS, K.BOLT_GRADES, K.BOLT_DIAS, K.ELECTRODES
PRETENSION = K.PRETENSION
member_at_joint = K.member_at_joint
end_plate_Y, kennedy, bolt_moments = K.end_plate_Y, K.kennedy, K.bolt_moments
SectionError = K.SectionError
kN, kNm, f1, f2, f3 = K.kN, K.kNm, K.f1, K.f2, K.f3
TP_LIST = K.TP_LIST

EXT_MAP = {"flush": (False, False), "top": (True, False), "bottom": (False, True), "both": (True, True)}
TYPE_LABEL = {"straight": "Beam splice", "apex": "Apex"}
SIDE_NAME = {"T": "cánh trên", "B": "cánh dưới"}


# ─────────────────────────── chuẩn hoá input ───────────────────────────
def normalize(inp: dict) -> dict:
    """Đồng bộ các trường kiểu RAM → trường engine (sửa tại chỗ, trả về inp)."""
    pl = inp["plate"]
    if pl.get("extension") in EXT_MAP:
        pl["extT"], pl["extB"] = EXT_MAP[pl["extension"]]
    b1, b2 = inp["beam1"], inp["beam2"]
    if b2.get("same"):
        for k in ("sec", "mat", "L"):
            b2[k] = b1[k]
        b2["jointEnd"] = "I" if b1.get("jointEnd", "J") == "J" else "J"
    wd = inp.get("weld", {})
    for k in ("flT", "flB", "web"):
        if k in wd and "D" in wd[k]:
            wd[k]["w"] = float(wd[k]["D"]) * IN16
    return inp


# ─────────────────────────── hình học ───────────────────────────
def build_geometry(inp: dict) -> dict:
    W: list[str] = []
    m1 = dict(inp["beam1"], topIsOuter=True)
    m2 = dict(inp["beam2"], topIsOuter=True)
    b1 = member_at_joint(m1, "dầm 1")
    b2 = member_at_joint(m2, "dầm 2")
    typ = inp["type"]
    alpha = abs(float(inp.get("slope") or 0.0)) if typ == "apex" else 0.0
    if alpha > 60:
        raise ValueError(f"Góc dốc {alpha:.1f}° quá lớn cho bản đầu đứng (≤ 60°).")
    phi = fold(alpha)
    c = cosd(phi)
    if abs(b1["d"] - b2["d"]) > 1.0:
        raise ValueError(f"Hai dầm khác chiều cao tại mặt nối (d1 = {b1['d']:.1f}, d2 = {b2['d']:.1f} mm): "
                         "tool chỉ hỗ trợ hai dầm cùng chiều cao tiết diện.")
    if abs(b1["tfE"] - b2["tfE"]) > 0.5 or abs(b1["tfI"] - b2["tfI"]) > 0.5:
        W.append("Bề dày cánh hai dầm khác nhau: vị trí hàng bu lông tính theo dầm 1.")
    for b in (b1, b2):
        if b["beta"] > 2.0:
            W.append(f"{b['label'].capitalize()} có tiết diện vát {b['beta']:.1f}°: độ nghiêng cánh do vát bị bỏ qua khi quy đổi nội lực.")
    pl = inp["plate"]
    dp = b1["d"] / c
    tfT, tfB = b1["tfE"] / c, b1["tfI"] / c
    dm = dp - tfT / 2 - tfB / 2
    rowsT, rowsB = [], []
    if pl["extT"]: rowsT.append(dict(s=-pl["pfoT"], outer=True, grp="T"))
    for k in range(int(pl["nT"])): rowsT.append(dict(s=tfT + pl["pfiT"] + k * pl["pbT"], outer=False, grp="T"))
    if pl["extB"]: rowsB.append(dict(s=dp + pl["pfoB"], outer=True, grp="B"))
    for k in range(int(pl["nB"])): rowsB.append(dict(s=dp - tfB - pl["pfiB"] - k * pl["pbB"], outer=False, grp="B"))
    sTop = -(pl["pfoT"] + pl["Lev"]) if pl["extT"] else -pl["flushExt"]
    sBot = dp + pl["pfoB"] + pl["Lev"] if pl["extB"] else dp + pl["flushExt"]
    bp = pl["g"] + 2 * pl["Leh"]
    return dict(W=W, type=typ, beam=[None, b1, b2], b1=b1, b2=b2, alpha=alpha, phi=phi, dp=dp, tfT=tfT, tfB=tfB, dm=dm,
                rowsT=rowsT, rowsB=rowsB, sTop=sTop, sBot=sBot, bp=bp)


# ─────────────────────────── một phía kéo ───────────────────────────
def side_static(G: dict, inp: dict, side: str, bolt: dict) -> dict:
    """Phía kéo: T (cánh trên căng) hoặc B (cánh dưới căng). Tính bản 1 và bản 2."""
    pl, opt = inp["plate"], inp["opt"]
    T = side == "T"
    rows = [dict(r) for r in (G["rowsT"] if T else G["rowsB"])]
    ext = pl["extT"] if T else pl["extB"]
    n = int(pl["nT"] if T else pl["nB"])
    pfo, pfi, pb = (pl["pfoT"], pl["pfiT"], pl["pbT"]) if T else (pl["pfoB"], pl["pfiB"], pl["pbB"])
    compFace = G["dp"] if T else 0.0                         # mặt ngoài cánh nén
    compCtr = G["dp"] - G["tfB"] / 2 if T else G["tfT"] / 2   # tâm cánh nén
    for r in rows:
        r["h"] = abs(compFace - r["s"])                       # từ mặt cánh nén (DG16, như RAM Connection)
        r["d"] = abs(compCtr - r["s"])                        # từ tâm cánh nén (lực bu lông)
    hk = "d" if opt.get("hRef") == "centerline" else "h"      # centerline = DG4 / DG39 (thiên về an toàn ~1 %)
    outer = next((r for r in rows if r["outer"]), None)
    inner = [r for r in rows if not r["outer"]]
    W: list[str] = []
    st = pl["stiffT"] if T else pl["stiffB"]
    stiff = bool(st and st.get("on")) and ext
    if ext:
        cfg = {1: "4ES" if stiff else "4E", 2: "MRE 1/2", 3: "MRE 1/3"}.get(n)
        if stiff and n > 1:
            W.append(f"Sườn bản đầu chỉ hỗ trợ cho cấu hình 4ES — bỏ qua sườn với {cfg}."); stiff = False
    else:
        cfg = {1: "2FU", 2: "4FU"}.get(n)
    if not cfg:
        raise ValueError(f"Nhóm bu lông {SIDE_NAME[side]}: cấu hình không hỗ trợ (flush tối đa 2 hàng, extended tối đa 3 hàng trong).")
    gam = 1.0 if ext else 1.25                                # DG16: γr
    plates = []
    for k in (1, 2):
        tp = float(pl[f"tp{k}"]); Fpy = G["mat"][k]["Fy"]; mem = G["beam"][k]
        bf_t = mem["bfE"] if T else mem["bfI"]
        bpE = min(G["bp"], bf_t + IN)
        Yr = end_plate_Y(cfg, bpE, pl["g"], pfi, pfo, pb, outer[hk] if outer else 0.0, [r[hk] for r in inner], pl["Lev"])
        phiMpl = 0.9 * Fpy * tp * tp * Yr["Y"]
        ken = kennedy(tp, Fpy, bpE, bolt["db"], bolt["Fnt"], pfi, pfo if ext else None, pl["Lev"])
        bm = bolt_moments(ext, outer["d"] if outer else None, [r["d"] for r in inner], bolt["Pt"], bolt["Tb"], ken["Qi"], ken["Qo"])
        plates.append(dict(k=k, tp=tp, Fpy=Fpy, bpE=bpE, Yr=Yr, phiMpl=phiMpl, ken=ken, bm=bm, phiMq=0.75 * bm["Mq"],
                           thick=0.75 * bm["Mnp"] < 0.9 * phiMpl))
    bm0 = plates[0]["bm"]
    return dict(side=side, T=T, cfg=cfg, ext=ext, n=n, rows=rows, outer=outer, inner=inner, pfo=pfo, pfi=pfi, pb=pb, gam=gam,
                plates=plates, phiMnp=0.75 * bm0["Mnp"], sumD=bm0["sumD"], stiff=stiff, W=W, hk=hk)


# ─────────────────────────── định dạng / tính chính ───────────────────────────
def compute(inp: dict) -> dict:
    normalize(inp)
    G = build_geometry(inp)
    W = G["W"]
    pl, opt = inp["plate"], inp["opt"]
    G["mat"] = [None, material(pl["mat1"]), material(pl["mat2"])]
    G["tp"] = [None, float(pl["tp1"]), float(pl["tp2"])]
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
    for sd in ("T", "B"):
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

    b1, b2, phi = G["b1"], G["b2"], G["phi"]
    allRows = G["rowsT"] + G["rowsB"]
    nBT, nBB = 2 * len(G["rowsT"]), 2 * len(G["rowsB"])
    kb1, kb2 = (1.2, 2.4) if opt.get("holeDef", True) else (1.5, 3.0)         # J3.10: J3-6a hoặc J3-6b

    def bearing_group(rows, t, Fu):
        s = sorted(r["s"] for r in allRows)
        total, lines = 0.0, []
        for r in rows:
            i = s.index(r["s"])
            up = s[i] - s[i - 1] - bolt["dh"] if i > 0 else r["s"] - G["sTop"] - bolt["dh"] / 2
            dn = s[i + 1] - s[i] - bolt["dh"] if i < len(s) - 1 else G["sBot"] - r["s"] - bolt["dh"] / 2
            lc = max(min(up, dn), 0.0)
            rn = min(kb1 * lc * t * Fu, kb2 * db * t * Fu)
            total += 2 * rn
            lines.append(f"Hàng s = {f1(r['s'])} mm: lc = {f1(lc)} mm → Rn/bu lông = min({kb1}·lc·t·Fu; {kb2}·d·t·Fu) = {f1(kN(rn))} kN")
        return 0.75 * total, lines

    bear = {(k, g): bearing_group(G["rowsT"] if g == "T" else G["rowsB"], G["tp"][k], G["mat"][k]["Fu"])
            for k in (1, 2) for g in ("T", "B")}
    stage = lambda k: f"Bản đầu {k}"
    demands = []
    for ci, cb in enumerate(inp.get("loads", [])):
        g = lambda key: float(cb.get(key) or 0.0)
        N, V, M = g("N") * 1e3, g("V") * 1e3, g("M") * 1e6
        nm = cb.get("name") or f"TH{ci + 1}"
        Nn = N * cosd(phi) + abs(V) * sind(phi)           # vuông góc bản (kéo +)
        Vt = abs(N) * sind(phi) + abs(V) * cosd(phi)      # dọc bản (cắt bu lông)
        FnT = -M / G["dm"] + Nn / 2
        FnB = M / G["dm"] + Nn / 2
        Nrel = Nn if opt.get("axialRelief", True) else max(Nn, 0.0)
        Mu = max(abs(M) + Nrel * G["dm"] / 2, 0.0)
        side = "T" if M < 0 else "B" if M > 0 else None
        demands.append(dict(name=nm, V=kN(V), N=kN(N), M=kNm(M), Nn=kN(Nn), Vt=kN(Vt), FnT=kN(FnT), FnB=kN(FnB),
                            Mu=kNm(Mu), side=side))

        # ---------- bản đầu + bu lông (phía kéo) ----------
        if side and "error" not in sides[side]:
            S = sides[side]
            gname = f"Bản đầu — nhóm {SIDE_NAME[side]}"
            common = lambda S=S: [
                f"Cấu hình: {S['cfg']} ({'extended' if S['ext'] else 'flush'}),  γr = {S['gam']}",
                f"Mu,eq = |M| + Nn·dm/2 = {f2(kNm(abs(M)))} + {f2(kN(Nrel))}·{f1(G['dm'])}/2/1000 = {f2(kNm(Mu))} kN·m",
                "Hàng bu lông kéo (h từ mặt ngoài cánh nén; d từ tâm cánh nén): " + " | ".join(
                    f"{'ngoài' if r['outer'] else 'trong'} h={f1(r['h'])}, d={f1(r['d'])}" for r in S["rows"]),
                f"Y dùng khoảng cách {'h (mặt cánh nén — DG16/RAM)' if S['hk'] == 'h' else 'd (tâm cánh nén — DG4/DG39)'}",
            ]
            for P in S["plates"]:
                k = P["k"]
                add(f"pl{k}_flex_{side}", gname, f"Chảy dẻo uốn bản đầu {k}", "kN·m", "DG16 Sec 2.5",
                    kNm(P["phiMpl"] / S["gam"]), kNm(Mu), nm,
                    lambda S=S, P=P: common() + [
                        f"bp,eff = min(bp; bf + 25.4) = min({f1(G['bp'])}; {f1(G['beam'][P['k']]['bfE' if S['T'] else 'bfI'] + IN)}) = {f1(P['bpE'])} mm,  s = ½√(bp·g) = {f1(P['Yr']['s'])} mm",
                        P["Yr"]["formula"], f"Y = {f1(P['Yr']['Y'])} mm",
                        f"φb·Mpl = 0.9·Fpy·tp²·Y = 0.9·{P['Fpy']:g}·{P['tp']:g}²·{f1(P['Yr']['Y'])} = {f2(kNm(P['phiMpl']))} kN·m",
                        f"Khả năng = φb·Mpl/γr = {f2(kNm(P['phiMpl'] / S['gam']))} kN·m",
                        "Ứng xử bản: " + ("BẢN DÀY (φMnp < 0.9φbMpl) — không nhổ" if P["thick"] else "BẢN MỎNG (φMnp ≥ 0.9φbMpl) — có lực nhổ"),
                        f"tp,req (bản mỏng) = √(γr·Mu/(φb·Fpy·Y)) = {f1(math.sqrt(S['gam'] * Mu / (0.9 * P['Fpy'] * P['Yr']['Y'])))} mm",
                    ], (f"plate{k}",))
            add("bolt_np_" + side, gname, "Đứt bu lông không nhổ (φMnp)", "kN·m", "DG16 Sec 2.5 / DG4 Eq. 3.7", kNm(S["phiMnp"]), kNm(Mu), nm,
                lambda S=S: common() + [
                    f"Pt = Fnt·Ab = {bg['Fnt']:g}·{f1(Ab)} = {f1(kN(bolt['Pt']))} kN", f"Σd = {f1(S['sumD'])} mm",
                    f"φMnp = 0.75·2·Pt·Σd = {f2(kNm(S['phiMnp']))} kN·m",
                    f"db,req = √(2Mu/(π·φ·Fnt·Σd)) = {f1(math.sqrt(2 * Mu / (math.pi * 0.75 * bolt['Fnt'] * S['sumD'])))} mm",
                ], ("bolts" + side,))
            for P in S["plates"]:
                k = P["k"]
                add(f"bolt_q{k}_{side}", gname, f"Đứt bu lông có lực nhổ — bản {k} (φMq)", "kN·m", "DG16 Sec 2.5 (Kennedy hiệu chỉnh)",
                    kNm(P["phiMq"]), kNm(Mu), nm,
                    lambda S=S, P=P: common() + [
                        f"Bản {P['k']}: tp = {P['tp']:g} mm, Fpy = {P['Fpy']:g} MPa, bp,eff = {f1(P['bpE'])} mm",
                        f"w' = bp/2 − (db + 1/16\") = {f1(P['ken']['wc'])} mm;  ai = 3.682(tp/db)³ − 0.085 [in] = {f2(P['ken']['a'])} mm",
                        f"F'i = [tp²·Fpy(0.85bp/2 + 0.8w') + π·db³·Fnt/8]/(4pf,i) = {f1(kN(P['ken']['Fi']))} kN",
                        f"Qmax,i = w'tp²/(4ai)·√(Fpy² − 3(F'i/(w'tp))²) = {f1(kN(P['ken']['Qi']))} kN",
                        (f"ao = min(ai; pext − pf,o) = {f2(P['ken']['ao'])} mm;  F'o = F'i·pf,i/pf,o = {f1(kN(P['ken']['Fo']))} kN;  Qmax,o = {f1(kN(P['ken']['Qo']))} kN") if S["ext"] else "Flush: không có hàng ngoài",
                        f"Pt = {f1(kN(bolt['Pt']))} kN;  Tb = {f1(kN(bolt['Tb']))} kN" + (f" (siết sơ bộ ×{bolt['snugF']})" if inp['bolt'].get('snug') else ""),
                    ] + [f"  {t} = {f2(kNm(v))} kN·m" for v, t in P["bm"]["cases"]] + [
                        f"φMq = 0.75·max(...) = {f2(kNm(P['phiMq']))} kN·m" + ("  → căn âm: bản phá hoại do uốn + cắt kết hợp, cần tăng tp" if isnan(P["phiMq"]) else "")],
                    (f"plate{k}", "bolts" + side))

        # ---------- cắt / ép mặt bu lông ----------
        grp = "B" if side == "T" else "T" if side == "B" else "A"
        allb = opt.get("shearAll") or grp == "A"
        idg = "A" if allb else grp
        nB = nBT + nBB if allb else (nBT if grp == "T" else nBB)
        phiRv = 0.75 * bolt["Fnv"] * Ab * nB
        gn = "Bu lông (toàn bộ)" if allb else f"Bản đầu — nhóm {SIDE_NAME[grp]}"
        add("bolt_v_" + idg, gn, "Bu lông chịu cắt", "kN", "AISC J3.6 (Table J3.2)", kN(phiRv), kN(Vt), nm, lambda: [
            f"Lực cắt dọc bản Vt = |N|·sinφ + |V|·cosφ = {f2(kN(Vt))} kN  (φ = {f1(phi)}°)",
            f"Bu lông chịu cắt: {'toàn bộ' if allb else 'nhóm phía nén'}, n = {nB}",
            f"φRn = 0.75·Fnv·Ab·n = 0.75·{f1(bolt['Fnv'])}·{f1(Ab)}·{nB} = {f2(kN(phiRv))} kN"],
            ("boltsT", "boltsB") if idg == "A" else ("bolts" + idg,))
        useT, useB = idg in ("T", "A"), idg in ("B", "A")
        for k in (1, 2):
            cap = (bear[(k, "T")][0] if useT else 0) + (bear[(k, "B")][0] if useB else 0)
            add(f"bear_p{k}_{idg}", gn, f"Ép mặt / xé bu lông trên bản đầu {k}", "kN", "AISC Eq. J3-6", kN(cap), kN(Vt), nm,
                lambda k=k, cap=cap: [f"t = tp{k} = {G['tp'][k]:g} mm, Fu = {G['mat'][k]['Fu']:g} MPa (lc lấy theo chiều bất lợi)"]
                + (bear[(k, "T")][1] if useT else []) + (bear[(k, "B")][1] if useB else []) + [f"φRn = 0.75·Σ(2·Rn) = {f2(kN(cap))} kN"], (f"plate{k}",))

        # ---------- cắt bản đầu tại cánh (DG4 3.12, 3.13) ----------
        for f in ("T", "B"):
            Fn = FnT if f == "T" else FnB
            gname = f"Bản đầu — nhóm {SIDE_NAME[f]}"
            for k in (1, 2):
                tp, Fpy, Fpu = G["tp"][k], G["mat"][k]["Fy"], G["mat"][k]["Fu"]
                Rv = 0.9 * 0.6 * Fpy * G["bp"] * tp
                add(f"pl{k}_vy_{f}", gname, f"Cắt chảy bản đầu {k} (Ffu/2)", "kN", "DG4 Eq. 3.12", kN(Rv), kN(abs(Fn) / 2), nm,
                    lambda Fn=Fn, Rv=Rv, tp=tp, Fpy=Fpy: [
                        f"Ffu = |M|/dm ± Nn/2 = {f2(kN(abs(Fn)))} kN",
                        f"φRn = 0.9·0.6·Fpy·bp·tp = 0.9·0.6·{Fpy:g}·{f1(G['bp'])}·{tp:g} = {f2(kN(Rv))} kN"], (f"plate{k}",))
                extF = pl["extT"] if f == "T" else pl["extB"]
                if extF and Fn > 0 and "error" not in sides[f] and not sides[f]["stiff"]:
                    An = (G["bp"] - 2 * (bolt["dh"] + 2)) * tp
                    Rr = 0.75 * 0.6 * Fpu * An
                    add(f"pl{k}_vr_{f}", gname, f"Cắt đứt phần bản nhô {k} (Ffu/2)", "kN", "DG4 Eq. 3.13", kN(Rr), kN(Fn / 2), nm,
                        lambda An=An, Rr=Rr, tp=tp, Fpu=Fpu: [
                            f"An = [bp − 2(dh + 2)]·tp = [{f1(G['bp'])} − 2({bolt['dh']} + 2)]·{tp:g} = {f1(An)} mm²",
                            f"φRn = 0.75·0.6·Fpu·An = {f2(kN(Rr))} kN"], (f"plate{k}",))

        # ---------- hàn & bụng dầm ----------
        for k in (1, 2):
            mem = G["beam"][k]
            label = f"Dầm {k} (hàn vào bản đầu {k})"
            for f in ("T", "B"):
                Fn = FnT if f == "T" else FnB
                if Fn <= 0: continue
                w = inp["weld"]["flT"] if f == "T" else inp["weld"]["flB"]
                bf_, tf_ = (mem["bfE"], mem["tfE"]) if f == "T" else (mem["bfI"], mem["tfI"])
                Ff = Fn / cosd(phi)
                if opt.get("flangeWeldMin"): Ff = max(Ff, 0.6 * mem["mat"]["Fy"] * bf_ * tf_)
                nm2 = f"Hàn {SIDE_NAME[f]} — bản đầu {k}"
                if w["type"] == "cjp":
                    cap = 0.9 * mem["mat"]["Fy"] * bf_ * tf_
                    add(f"m{k}_wf_{f}", label, nm2 + " (CJP)", "kN", "AISC Table J2.5 / J4.1", kN(cap), kN(Ff), nm,
                        lambda cap=cap, Fn=Fn, bf_=bf_, tf_=tf_, mem=mem: [
                            f"Hàn thấu CJP: khả năng = φ·Fy·bf·tf = 0.9·{mem['mat']['Fy']:g}·{bf_:g}·{tf_:g} = {f2(kN(cap))} kN",
                            f"Lực cánh theo phương cánh = Fn/cosφ = {f2(kN(Fn))}/cos{f1(phi)}° = {f2(kN(Fn / cosd(phi)))} kN"], (f"m{k}weld{f}",))
                else:
                    Lw = 2 * bf_ - mem["tw"]
                    wFf = ELECTRODES.get(w.get("electrode"), weldF)
                    cap = 0.75 * 0.6 * wFf * dirF * 0.707 * w["w"] * Lw
                    add(f"m{k}_wf_{f}", label, nm2 + " (hàn góc)", "kN", "AISC Eq. J2-4, J2-5", kN(cap), kN(Ff), nm,
                        lambda cap=cap, Lw=Lw, w=w, Ff=Ff: [
                            f"Lw = 2bf − tw = {f1(Lw)} mm;  w = {w['w']:g} mm ({f1(w['w'] / IN * 16)}/16\"),  FEXX = {weldF:g} MPa",
                            f"φRn = 0.75·0.6·FEXX·{dirF:g}·0.707·w·Lw = {f2(kN(cap))} kN",
                            f"Lực cánh theo phương cánh = Fn/cosφ = {f2(kN(Ff))} kN"], (f"m{k}weld{f}",))
            ww = inp["weld"]["web"]["w"]
            wFw = ELECTRODES.get(inp["weld"]["web"].get("electrode"), weldF)
            qdem = 0.9 * mem["mat"]["Fy"] * mem["tw"]
            qcap = 2 * 0.75 * 0.6 * wFw * 0.707 * ww * dirF
            if abs(M) > 0:
                add(f"m{k}_ww_t", label, "Hàn bụng vùng kéo (phát triển chảy bụng)", "kN/m", "AISC Eq. J2-4; J4-1", qcap, qdem, nm,
                    lambda mem=mem, qdem=qdem, qcap=qcap: [
                        f"Yêu cầu = φ·Fy·tw = 0.9·{mem['mat']['Fy']:g}·{mem['tw']:g} = {f1(qdem)} N/mm (kN/m)",
                        f"Khả năng 2 đường hàn góc: 2·0.75·0.6·FEXX·0.707·w·{dirF:g} = {f1(qcap)} N/mm"], (f"m{k}webweld",))
            sd = side or "T"
            Sx = sides[sd] if "error" not in sides[sd] else None
            Lws = G["dp"] / 2 - (G["tfB"] if sd == "T" else G["tfT"])
            if Sx:
                last = Sx["inner"][-1]
                compInner = G["dp"] - G["tfB"] if sd == "T" else G["tfT"]
                Lws = min(Lws, abs(compInner - last["s"]) - 2 * db)
            Lws = max(Lws, 0.0)
            capV = 2 * 0.75 * 0.6 * wFw * 0.707 * ww * Lws
            add(f"m{k}_ww_v", label, "Hàn bụng chịu cắt", "kN", "AISC Eq. J2-4", kN(capV), kN(Vt), nm,
                lambda Lws=Lws, capV=capV: [
                    f"Chiều dài hàn hiệu quả (DG16 §2.5.3 item 10): min(d/2 − tf,c ; từ hàng kéo trong + 2db tới cánh nén) = {f1(Lws)} mm",
                    f"φRn = 2·0.75·0.6·FEXX·0.707·w·L = {f2(kN(capV))} kN"], (f"m{k}webweld",))
            capWV = 1.0 * 0.6 * mem["mat"]["Fy"] * G["dp"] * mem["tw"]
            add(f"m{k}_wv", label, f"Chảy cắt bụng dầm {k} tại bản", "kN", "AISC Eq. J4-3", kN(capWV), kN(Vt), nm,
                lambda mem=mem, capWV=capWV: [
                    f"φRn = 1.0·0.6·Fy·d·tw = 0.6·{mem['mat']['Fy']:g}·{f1(G['dp'])}·{mem['tw']:g} = {f2(kN(capWV))} kN"], (f"m{k}web",))

    # ---------- kiểm tra cấu tạo ----------
    geo = []
    def gchk(grp, name, val, mn=None, mx=None, ref="", unit="mm"):
        ok = (mn is None or val >= mn - 1e-6) and (mx is None or val <= mx + 1e-6)
        geo.append(dict(grp=grp, name=name, val=val, min=mn, max=mx, ref=ref, unit=unit, ok=ok))
    tpmin = min(G["tp"][1], G["tp"][2])
    emin = edge_min(db, opt.get("sheared", True))
    emax = min(12 * tpmin, 150)
    bfmin = min(b1["bfE"], b1["bfI"], b2["bfE"], b2["bfI"])
    gchk("Bản đầu", "Khoảng cách mép dọc bản Lev", pl["Lev"], emin, emax, "J3.4, J3.5")
    gchk("Bản đầu", "Khoảng cách mép ngang Leh", pl["Leh"], emin, emax, "J3.4, J3.5")
    gchk("Bản đầu", "Gage g", pl["g"], 2.667 * db, bfmin, "J3.3; DG16 §2.5.3-7")
    pmin = db + 12.7 if db <= 25.4 else db + 19.05
    if pl["extT"]: gchk("Bản đầu", "pf,o cánh trên", pl["pfoT"], pmin, None, "DG16 §2.5.3-4")
    gchk("Bản đầu", "pf,i cánh trên", pl["pfiT"], pmin, None, "DG16 §2.5.3-4")
    if pl["extB"]: gchk("Bản đầu", "pf,o cánh dưới", pl["pfoB"], pmin, None, "DG16 §2.5.3-4")
    gchk("Bản đầu", "pf,i cánh dưới", pl["pfiB"], pmin, None, "DG16 §2.5.3-4")
    if pl["extT"]: gchk("Bản đầu", "Hàng ngoài – hàng trong (cánh trên)", pl["pfoT"] + G["tfT"] + pl["pfiT"], 2.667 * db, None, "J3.3")
    if pl["extB"]: gchk("Bản đầu", "Hàng ngoài – hàng trong (cánh dưới)", pl["pfoB"] + G["tfB"] + pl["pfiB"], 2.667 * db, None, "J3.3")
    if pl["nT"] > 1: gchk("Bản đầu", "Bước hàng pb (cánh trên)", pl["pbT"], 2.667 * db, None, "J3.3")
    if pl["nB"] > 1: gchk("Bản đầu", "Bước hàng pb (cánh dưới)", pl["pbB"], 2.667 * db, None, "J3.3")
    lastT = [r for r in G["rowsT"] if not r["outer"]][-1:]
    lastB = [r for r in G["rowsB"] if not r["outer"]][-1:]
    if lastT and lastB:
        gchk("Bản đầu", "Khoảng trống giữa hai nhóm bu lông", lastB[0]["s"] - lastT[0]["s"], 2.667 * db, None, "J3.3")
    gchk("Bản đầu", "Đường kính bu lông", db, None, 38.1, "DG4 §1.1")
    if G["bp"] > bfmin + IN + 1e-6:
        W.append(f"bp = {G['bp']:.0f} mm > bf + 25.4: tính toán dùng bề rộng hiệu quả bp,eff = bf + 25.4 (DG16 §2.5.3-6).")
    if abs(G["tp"][1] - G["tp"][2]) > 1e-9 or pl["mat1"] != pl["mat2"]:
        W.append("Hai bản đầu khác bề dày / vật liệu: bu lông lấy theo bản bất lợi (Q lớn hơn); bản đầu chịu uốn kiểm tra riêng từng bản.")
    for f in ("T", "B"):
        w = inp["weld"]["flT"] if f == "T" else inp["weld"]["flB"]
        if w["type"] == "fillet":
            for k in (1, 2):
                mem = G["beam"][k]
                gchk("Hàn", f"Hàn góc {SIDE_NAME[f]} dầm {k} ≥ min", w["w"],
                     weld_min(min(mem["tfE"] if f == "T" else mem["tfI"], G["tp"][k])), None, "Table J2.4")
    for k in (1, 2):
        gchk("Hàn", f"Hàn góc bụng dầm {k} ≥ min", inp["weld"]["web"]["w"], weld_min(min(G["beam"][k]["tw"], G["tp"][k])), None, "Table J2.4")
    for f in ("T", "B"):
        S = sides[f]
        if "error" in S or not S["stiff"]: continue
        st = pl["stiffT"] if f == "T" else pl["stiffB"]
        stMat = material(st.get("mat", "Q345"))
        hst = (pl["pfoT"] if f == "T" else pl["pfoB"]) + pl["Lev"]
        lab = f"Sườn bản đầu (4ES) {SIDE_NAME[f]}"
        gchk(lab, "ts ≥ tw·Fyb/Fys", st["ts"], b1["tw"] * b1["mat"]["Fy"] / stMat["Fy"], None, "DG4 Eq. 3.15")
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
def auto_design(inp: dict, dias=(16, 20, 22, 24, 27, 30), tps=TP_LIST, progress: Optional[Callable] = None):
    """Thử tổ hợp (db, tp) — dùng chung tp cho hai bản; chọn phương án nhẹ nhất (tp nhỏ rồi db nhỏ) đạt D/C ≤ 1
    ở các kiểm tra bản đầu / bu lông và kiểm tra cấu tạo bản đầu. Trả về None nếu không có tổ hợp chạy được."""
    best = None
    for tp in tps:
        for d in dias:
            trial = copy.deepcopy(inp)
            trial["plate"]["tp1"] = trial["plate"]["tp2"] = tp
            trial["bolt"]["d"] = d
            try:
                r = compute(trial)
            except Exception:  # noqa: BLE001
                continue
            rel = [c for c in r["checks"] if not c["info"] and c["id"].startswith(("pl", "bolt_", "bear_"))]
            gfail = [g for g in r["geo"] if not g["ok"] and g["grp"] == "Bản đầu"]
            mx = max((c["ratio"] for c in rel), default=0.0)
            if mx <= 1.0 and not gfail:
                return dict(tp=tp, d=d, ratio=mx)
            if best is None or mx < best["ratio"]:
                best = dict(tp=tp, d=d, ratio=mx, fail=True)
        if progress: progress(tp)
    return best
