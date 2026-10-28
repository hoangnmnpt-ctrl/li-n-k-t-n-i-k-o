"""Kiểm thử lõi tính CHÂN CỘT (base_engine).  Chạy: python tests/test_base_engine.py
Cân bằng lực theo DG1 §3.3 (mô men nhỏ / lớn), nén đúng tâm §3.1, nhổ, neo AISC J3, ACI 318-11 App. D, hàn, tự chọn."""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import base_engine as BE  # noqa: E402
from base_defaults import BASE, PRESETS, merge  # noqa: E402


def near(a, b, tol=1e-3):
    return abs(a - b) <= tol * max(1.0, abs(b))


def chk(R, cid):
    return next(c for c in R["checks"] if c["id"] == cid)


def st_one(load, **over):
    st = merge(BASE, over)
    st["loads"] = [dict({"name": "LC", "N": 0, "V2": 0, "V3": 0, "M33": 0, "M22": 0}, **load)]
    return st


def test_dg1_small_moment_equilibrium():
    Pc, M, L, W, f, fp = 800e3, 60e6, 600.0, 400.0, 240.0, 13.8
    r = BE.dg1_direction(Pc, M, L, W, f, fp)
    assert r["case"] == "small"
    assert near(r["q"] * r["Y"], Pc)                                   # ΣFy = 0
    assert near(r["q"] * r["Y"] * (L / 2 - r["Y"] / 2), M)             # ΣM quanh tâm bản = 0
    assert r["q"] <= r["qmax"]


def test_dg1_large_moment_equilibrium():
    Pc, M, L, W, f, fp = 300e3, 250e6, 650.0, 350.0, 265.0, 13.8
    r = BE.dg1_direction(Pc, M, L, W, f, fp)
    assert r["case"] == "large"
    assert near(r["q"] * r["Y"], Pc + r["Tu"])                         # ΣFy = 0
    assert near(r["q"] * r["Y"] * (L / 2 - r["Y"] / 2) + r["Tu"] * f, M)
    assert r["qreq"] < r["qmax"]


def test_dg1_no_solution_and_tension():
    r = BE.dg1_direction(100e3, 5000e6, 400.0, 300.0, 150.0, 10.0)
    assert r["case"] == "nosol" and r["qreq"] > r["qmax"]
    r = BE.dg1_direction(-200e3, 10e6, 400.0, 300.0, 150.0, 10.0)      # nhổ chiếm ưu thế: không còn vùng ép
    assert r["case"] == "tension"


def test_axial_bearing_and_plate_lambda():
    st = st_one({"N": -1500})
    R = BE.compute(st)
    G = R["G"]
    fpmax = 0.65 * 0.85 * 25 * min(G["N2"] / G["N"], G["B2"] / G["B"], 2.0)
    c = chk(R, "conc_bear_33")
    assert near(c["cap"], fpmax) and near(c["dem"], 1500e3 / (G["N"] * G["B"]))
    d, bf = G["d"], G["bf"]
    X = 4 * d * bf / (d + bf) ** 2 * 1500e3 / (fpmax * G["N"] * G["B"])
    lam = min(2 * math.sqrt(X) / (1 + math.sqrt(1 - X)), 1.0)
    l = max(G["m"], G["n"], lam * math.sqrt(d * bf) / 4)
    tp_req = l * math.sqrt(2 * 1500e3 / (0.9 * 345 * G["N"] * G["B"]))       # DG1 Eq. 3.1.7
    c = chk(R, "bp_comp_33")
    assert near(c["dem"] / c["cap"], (tp_req / G["tp"]) ** 2)


def test_uplift_anchor_forces_and_rod_strength():
    st = st_one({"N": 200})
    R = BE.compute(st)
    assert all(near(t, 50.0) for t in R["demands"][0]["T"])            # 200 kN / 4 neo
    da = BASE["anchor"]["d"]
    Ab = math.pi * da ** 2 / 4
    c = chk(R, "anc_t")
    assert near(c["cap"], 0.75 * 0.75 * 500 * Ab / 1e3) and near(c["dem"], 50.0)
    # neo ngoài cánh (DG1): Mpl = Tu·x/B với x = f − d/2 + tf/2, Tu = tổng 2 neo cùng hàng
    G = R["G"]
    x = G["ax"] - G["d"] / 2 + G["tf"] / 2
    assert near(chk(R, "bp_ten")["dem"], 100e3 * x / G["B"] / 1e3)


def test_anchors_between_flanges_plate_tension():
    st = merge(BASE, PRESETS["Mẫu chân cột khớp — 4 neo trong cánh"])
    st["loads"] = [{"name": "U", "N": 80, "V2": 0, "V3": 0, "M33": 0, "M22": 0}]
    R = BE.compute(st)
    assert all(a["zone"] == "in" for a in R["G"]["anchors"])
    assert near(chk(R, "bp_ten")["dem"], 20e3 / 2 / 1e3)              # b = 2a → Mpl = T/2 (DG1 §3.2.2)


def test_large_moment_anchor_tension_matches_dg1():
    st = st_one({"N": -250, "M33": 160})
    R = BE.compute(st)
    G = R["G"]
    r = BE.dg1_direction(250e3, 160e6, G["N"], G["B"], G["ax"], G["fpmax"])
    dm = R["demands"][0]
    assert dm["case33"] == "large"
    assert near(dm["Tsum"], r["Tu"] / 1e3)
    tens = [a for a, t in zip(G["anchors"], dm["T"]) if t > 0]
    assert len(tens) == G["ny"] and all(a["x"] < 0 for a in tens)      # M33 > 0 nén mép +x → neo phía −x chịu kéo


def test_aci_single_anchor_breakout_far_from_edges():
    st = st_one({"N": 50}, ped={"N2": 5000, "B2": 5000, "h": 3000}, reinf={"T": False, "V": False})
    R = BE.compute(st)
    br = BE.aci_breakout_tension(R["G"], [(0.0, 0.0)], [50e3], 400.0, 25.0, 1.0, True)
    Nb = max(10 * math.sqrt(25) * 400 ** 1.5, 3.9 * math.sqrt(25) * 400 ** (5 / 3))
    assert near(br["Ncbg"], Nb)
    assert any(c["id"] == "aci_cb" for c in R["checks"]) and not any(c["id"] == "aci_rt" for c in R["checks"])


def test_anchor_reinforcement_replaces_breakout():
    st = st_one({"N": 100, "V2": 50}, reinf={"type": "primary", "T": True, "V": True})
    R = BE.compute(st)
    ids = {c["id"] for c in R["checks"]}
    assert "aci_rt" in ids and "aci_cb" not in ids and "aci_rv_0" in ids and "aci_vcb_0" not in ids
    assert near(chk(R, "aci_rt")["dem"], 100e3 / (0.75 * BE.FY_REINF)) and chk(R, "aci_rt")["info"]
    # supplementary: Condition A → φ = 0.75 thay 0.70
    R2 = BE.compute(st_one({"N": 100}, reinf={"type": "supplementary", "T": True, "V": False}))
    R3 = BE.compute(st_one({"N": 100}, reinf={"type": "primary", "T": False, "V": False}))
    assert near(chk(R2, "aci_cb")["cap"] / chk(R3, "aci_cb")["cap"], 0.75 / 0.70)


def test_weld_pure_tension():
    st = st_one({"N": 300})
    R = BE.compute(st)
    G = R["G"]
    assert near(chk(R, "w_fl")["dem"], 300e3 / G["Lt"])


def test_shear_modes():
    st = st_one({"N": -400, "V2": 200}, gen={"friction": True})
    R = BE.compute(st)
    Vf = 0.75 * 0.55 * 400
    assert near(chk(R, "shear_fric")["cap"], Vf)
    nv = len(R["G"]["anchors"]) // 2                                        # neo không hàn: một nửa số neo chịu cắt
    assert near(chk(R, "anc_v")["dem"], (200 - Vf) / nv)
    st = st_one({"N": -400, "V2": 80}, lug={"on": True})
    R = BE.compute(st)
    assert {"lug_bear", "lug_flex", "lug_v", "lug_w"} <= {c["id"] for c in R["checks"]}
    assert not any(c["id"] == "anc_v" for c in R["checks"])


def test_biaxial_warning_and_presets_run():
    st = st_one({"N": -300, "M33": 80, "M22": 20})
    R = BE.compute(st)
    assert any("hai phương" in w for w in R["W"])
    assert {"conc_bear_22", "bp_comp_22"} & {c["id"] for c in R["checks"]} or "bp_size_22" in {c["id"] for c in R["checks"]}
    st["gen"]["axis"] = "major"
    R = BE.compute(st)
    assert not any(c["id"].endswith("_22") for c in R["checks"])
    for p in PRESETS.values():
        R = BE.compute(merge(BASE, p))
        assert R["gov"] is not None and R["geoFail"] == 0
        assert R["gov"]["ratio"] <= 1.0, (p.get("name"), R["gov"]["name"], R["gov"]["ratio"])


def test_auto_design():
    st = merge(BASE, {"plate": {"tp": 12}, "anchor": {"d": 16}})
    res = BE.auto_design(st)
    assert res and not res.get("fail") and res["tp"] > 12
    import project as PJ
    PJ.apply_auto("base", st, res)
    R = BE.compute(st)
    assert max(c["ratio"] for c in R["checks"] if c["id"].startswith(("bp_comp", "bp_ten", "anc_", "aci_"))) <= 1.0


def test_model3d_anchor_count():
    import model3d as M
    for p in PRESETS.values():
        st = merge(BASE, p)
        R = BE.compute(st)
        m = M.build("base", st, R)
        assert sum(1 for so in m.solids if so.color == M.BOLT) == 2 * len(R["G"]["anchors"])
        assert any(so.color == M.WELD for so in m.solids) and any(so.color == M.END_PLATE for so in m.solids)


def test_triangular_and_strain_compatibility():
    Pc, M, L, W, f, fp = 300e3, 250e6, 650.0, 350.0, 265.0, 13.8
    r = BE.tri_direction(Pc, M, L, W, f, fp)
    assert r["case"] == "large"
    assert near(r["q"] * r["Y"] / 2, Pc + r["Tu"])                    # ΣFy = 0 (tam giác)
    assert near(r["q"] * r["Y"] / 2 * (L / 2 - r["Y"] / 3) + r["Tu"] * f, M)
    r = BE.tri_direction(800e3, 40e6, 600.0, 400.0, 240.0, 13.8)       # e ≤ L/6: hình thang
    assert r["case"] == "small" and near(r["q"], 800e3 / 600 + 6 * 40e6 / 600 ** 2)
    # tương thích biến dạng: cân bằng lực / mô men của lời giải số (uniaxial và biaxial)
    st = st_one({"N": -300, "M33": 150, "M22": 40}, gen={"axis": "biaxial"})
    R = BE.compute(st)
    G = R["G"]
    sol = BE.solve_elastic(G, [(a["x"], a["y"]) for a in G["anchors"]], G["Ab"], G["Ec"], 300e3, 150e6, 40e6)
    assert sol["ok"] and sol["fp"] > 0 and sum(sol["T"]) > 0
    st = st_one({"N": -300, "M33": 150}, gen={"pressure": "triangular", "compat": True})
    R = BE.compute(st)
    assert R["demands"][0]["case33"] == "compat" and R["demands"][0]["Tsum"] > 0


def test_asd_offsets_and_options():
    R1 = BE.compute(st_one({"N": -300, "M33": 100}))
    R2 = BE.compute(st_one({"N": -300, "M33": 100}, gen={"designCode": "AISC 2010 ASD"}))
    assert near(chk(R2, "anc_t")["cap"], chk(R1, "anc_t")["cap"] / 1.5)
    R3 = BE.compute(st_one({"N": -300}, col={"ox": 50}))                  # lệch tâm cột → mô men Pu·ox
    assert R3["demands"][0]["case33"] in ("small", "large")
    R4 = BE.compute(st_one({"N": -300, "M33": 100}, plate={"overA2": True, "A2A1": 1.0}))
    assert near(R4["G"]["sqA"], 1.0)
    R5 = BE.compute(st_one({"N": 100}, gen={"seismic": True}, reinf={"T": False, "V": False}))
    R6 = BE.compute(st_one({"N": 100}, reinf={"T": False, "V": False}))
    assert near(chk(R5, "aci_cb")["cap"], 0.75 * chk(R6, "aci_cb")["cap"])
    R7 = BE.compute(st_one({"N": 100}, anchor={"layout": "transversal", "nr": 2, "npr": 3, "sr": 70}))
    assert len(R7["G"]["anchors"]) == 12
    R8 = BE.compute(st_one({"N": 100}, weld={"outerOnly": True}))
    assert not any(c["id"] == "w_web" for c in R8["checks"])


if __name__ == "__main__":
    fails = 0
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f(); print("PASS", n)
            except Exception as e:  # noqa: BLE001
                fails += 1; print("FAIL", n, type(e).__name__, e)
    sys.exit(1 if fails else 0)
