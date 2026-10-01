"""Kiểm chứng splice_engine.  Chạy:  python tests/test_splice_engine.py   (hoặc pytest)

Đối chiếu:
  • AISC DG39 Example 5.2-1 (bích bằng 2 bu lông, dầm W18×35) — quy ước h tính từ TÂM cánh nén (hRef = centerline)
  • AISC DG16 Example 4.2.1 (bích mở rộng 4E): Y và lực nhổ qua hàm dùng chung với knee_app
Đổi đơn vị Mỹ → SI: 1 in = 25.4 mm, 1 ksi = 6.894757 MPa, 1 kip = 4.448222 kN, 1 kip-in = 0.1129848 kN·m
"""

import copy
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import splice_engine as SE  # noqa: E402
from splice_defaults import BASE, PRESETS, merge  # noqa: E402
from splice_store import SavedList  # noqa: E402

IN, KSI, KIP, KIPIN = 25.4, 6.894757, 4.448222, 0.1129848


def close(a, b, tol):
    return abs(a / b - 1) <= tol


def dg39_521():
    """DG39 Example 5.2-1: W18×35, bích bằng 2 bu lông, A325 3/4″, Mu = 800 kip-in, Tu = 3.30 kips, Vu = 25.8 kips."""
    s = merge(BASE, {})
    dims = dict(d=17.7 * IN, tw=0.300 * IN, bf_top=6.0 * IN, tf_top=0.425 * IN, bf_bot=6.0 * IN, tf_bot=0.425 * IN)
    s["beam1"] = dict(sec="W18x35", mat="A992", L=6.0, jointEnd="J", dims=dims)
    s["beam2"] = dict(same=True, sec="W18x35", mat="A992", L=6.0, jointEnd="I", dims=dims)
    s["plate"].update(extension="flush", tp1=15.875, tp2=15.875, mat1="A992", mat2="A992", g=3.5 * IN, Leh=1.75 * IN, Lev=40,
                      flushExt=0.525 * IN, pfiT=1.5 * IN, pfiB=1.5 * IN, nT=1, nB=1)
    s["bolt"].update(grade="A325", d=19, thread="N", snug=True)
    s["opt"].update(hRef="centerline", flangeWeldMin=True)
    s["loads"] = [dict(name="LRFD", N=3.30 * KIP, V=25.8 * KIP, M=-800 * KIPIN)]
    return s


def test_dg39_521_demand_and_Y():
    r = SE.compute(dg39_521())
    d = r["demands"][0]
    assert close(d["Mu"], 829 * KIPIN, 0.003), d["Mu"]                      # Mu,eq = 829 kip-in
    S = r["sides"]["T"]
    assert S["cfg"] == "2FU"
    Y = S["plates"][0]["Yr"]["Y"]
    bp = 7 * IN
    # DG39 Table 5-2 (2023) cho Yp = 93.9 in. Công thức DG16 (2002) — dùng trong knee_app / RAM Connection — còn số hạng
    # "−1/2" trong ngoặc: Y_DG16 = Y_DG39 − bp/4 (thấp hơn ~1.9 %, thiên về an toàn). Kiểm tra cả hai mối quan hệ.
    assert close(Y, 93.9 * IN - bp / 4, 0.005), Y / IN
    assert Y < 93.9 * IN and close(Y, 93.9 * IN, 0.025)
    assert close(S["plates"][0]["Yr"]["s"], 2.47 * IN, 0.005)


def test_dg39_521_bolt_diameter():
    r = SE.compute(dg39_521())
    c = next(x for x in r["checks"] if x["id"] == "bolt_np_T")
    db_req = 19 * math.sqrt(c["ratio"])            # φMnp ∝ db² → db,req = db·√(D/C)
    assert close(db_req, 0.708 * IN, 0.02), db_req / IN        # db,req = 0.708 in. (db = 19 mm: sai số làm tròn đường kính)


def test_dg39_521_flange_weld_force():
    r = SE.compute(dg39_521())
    c = next(x for x in r["checks"] if x["id"] == "m1_wf_T")
    assert close(c["dem"], 76.5 * KIP / 1e3 * 1e3 / 1.0, 0.01) or close(c["dem"], 340.3, 0.01), c["dem"]   # Tu,min = 0.6·Fy·bf·tf = 76.5 kips


def test_dg39_521_shear_strength():
    r = SE.compute(dg39_521())
    c = next(x for x in r["checks"] if x["id"] == "bolt_v_B")           # 2 bu lông phía nén
    assert close(c["cap"], 35.9 * KIP, 0.015), c["cap"]                 # φVn = 35.9 kips
    assert close(c["dem"], 25.8 * KIP, 0.001)


def test_centerline_is_conservative():
    a = dg39_521(); b = dg39_521(); b["opt"]["hRef"] = "face"
    ya = SE.compute(a)["sides"]["T"]["plates"][0]["Yr"]["Y"]
    yb = SE.compute(b)["sides"]["T"]["plates"][0]["Yr"]["Y"]
    assert ya < yb < ya * 1.03


def test_dg16_ex421_Y_shared_function():
    y = SE.end_plate_Y("4E", 8 * IN, 3 * IN, 1.75 * IN, 2.5 * IN, 0, 26.5 * IN, [21.875 * IN], 2.5 * IN)
    assert close(y["Y"] / IN, 187.4, 0.001)


def test_presets_run_and_pass_basic_sanity():
    for name, p in PRESETS.items():
        r = SE.compute(merge(BASE, p))
        assert r["checks"] and r["gov"] is not None, name
        assert r["gov"]["ratio"] <= 1.0001 and r["geoFail"] == 0, (name, r["gov"]["id"], r["gov"]["ratio"])


def test_sign_symmetry():
    s = merge(BASE, {})
    s["loads"] = [dict(name="a", N=0, V=100, M=250), dict(name="b", N=0, V=100, M=-250)]
    r = SE.compute(s)
    cap = {c["id"]: c for c in r["checks"]}
    assert close(cap["bolt_q1_B"]["ratio"], cap["bolt_q1_T"]["ratio"], 1e-9)
    assert close(cap["pl1_flex_B"]["ratio"], cap["pl1_flex_T"]["ratio"], 1e-9)


def test_axial_tension_increases_Mu_eq_compression_reduces():
    s = merge(BASE, {})
    s["loads"] = [dict(name="0", N=0, V=0, M=-200), dict(name="T", N=200, V=0, M=-200), dict(name="C", N=-200, V=0, M=-200)]
    d = SE.compute(s)["demands"]
    assert d[1]["Mu"] > d[0]["Mu"] > d[2]["Mu"]
    s["opt"]["axialRelief"] = False
    d = SE.compute(s)["demands"]
    assert close(d[2]["Mu"], d[0]["Mu"], 1e-9)


def test_apex_force_transform():
    s = merge(BASE, PRESETS["Mẫu Apex — đỉnh mái dốc 10°"])
    s["loads"] = [dict(name="x", N=-30, V=70, M=-300)]
    d = SE.compute(s)["demands"][0]
    a = math.radians(10)
    assert close(d["Nn"], -30 * math.cos(a) + 70 * math.sin(a), 1e-9)
    assert close(d["Vt"], 30 * math.sin(a) + 70 * math.cos(a), 1e-9)


def test_two_plates_different_thickness_governed_by_thinner():
    s = merge(BASE, {})
    s["plate"].update(tp1=14, tp2=25)
    r = SE.compute(s)
    c = {x["id"]: x for x in r["checks"]}
    assert c["pl1_flex_T"]["ratio"] > c["pl2_flex_T"]["ratio"]
    assert c["bolt_q1_T"]["ratio"] >= c["bolt_q2_T"]["ratio"]
    assert any("khác bề dày" in w for w in r["W"])


def test_thicker_plate_never_worse():
    s = merge(BASE, {})
    prev = None
    for tp in (12, 16, 20, 25, 32):
        s["plate"].update(tp1=tp, tp2=tp)
        r = SE.compute(s)
        # chỉ kiểm tra uốn bản: φMq (Kennedy/DG16) không đơn điệu theo tp nên không đưa vào
        v = max(c["ratio"] for c in r["checks"] if c["id"].startswith(("pl1_flex", "pl2_flex")))
        assert prev is None or v < prev
        prev = v


def test_depth_mismatch_raises():
    s = merge(BASE, {})
    s["beam2"] = dict(same=False, sec="400.8-200.12", mat="Q345", L=6.0, jointEnd="I")
    try:
        SE.compute(s)
    except ValueError as e:
        assert "chiều cao" in str(e)
    else:
        raise AssertionError("phải báo lỗi khi hai dầm khác chiều cao")


def test_flush_plate_gamma_and_extended():
    r = SE.compute(merge(BASE, PRESETS["Mẫu nối dầm — bích bằng (2FU)"]))
    assert r["sides"]["T"]["gam"] == 1.25 and r["sides"]["T"]["cfg"] == "2FU"
    r = SE.compute(merge(BASE, {}))
    assert r["sides"]["T"]["gam"] == 1.0 and r["sides"]["T"]["cfg"] == "4E"


def test_stiffened_4ES():
    s = merge(BASE, {})
    s["plate"]["stiffT"]["on"] = True
    r = SE.compute(s)
    assert r["sides"]["T"]["cfg"] == "4ES"


def test_auto_design_finds_passing_connection():
    s = merge(BASE, {})
    res = SE.auto_design(s)
    assert res and not res.get("fail")
    s["plate"]["tp1"] = s["plate"]["tp2"] = res["tp"]; s["bolt"]["d"] = res["d"]
    assert SE.compute(s)["gov"]["ratio"] <= 1.0001 or res["ratio"] <= 1.0


def test_store_roundtrip(tmp_path=None):
    import tempfile
    d = tempfile.mkdtemp()
    p = os.path.join(d, "x.json")
    st = SavedList(p)
    i = st.add("BS-A", merge(BASE, {}), dict(dc=0.5))
    st2 = SavedList(p)
    want = merge(BASE, {"name": "BS-A"})
    assert st2.items[i]["name"] == "BS-A" and json.dumps(st2.items[i]["state"], sort_keys=True) == json.dumps(want, sort_keys=True)
    st2.rename(0, "BS-B"); st2.delete(0)
    assert SavedList(p).items == []


if __name__ == "__main__":
    fails = 0
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f(); print("PASS", n)
            except AssertionError as e:
                fails += 1; print("FAIL", n, e)
            except Exception as e:  # noqa: BLE001
                fails += 1; print("ERROR", n, type(e).__name__, e)
    sys.exit(1 if fails else 0)
