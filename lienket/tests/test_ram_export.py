"""Kiểm tra xuất .rcnx + ghi database tiết diện (trong thư mục tạm, không đụng database thật)."""

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ram_export as X  # noqa: E402
import report as RP  # noqa: E402
import engine as K  # noqa: E402
from defaults import BASE, PRESETS, merge  # noqa: E402

KNEE11 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ram23_knee11.rcnx")    # knee #11 gốc (RAM 23)
UNITS = {"in": 25.4, "ft": 304.8, "mm": 1.0}


def _same(a: str, b: str) -> bool:
    """Giá trị RAM và giá trị xuất trùng nhau (cho phép khác cách ghi đơn vị: 1 in = 25.4 mm)."""
    if a == b:
        return True
    try:
        (va, ua), (vb, ub) = (x.split() for x in (a, b))
        return abs(float(va) * UNITS[ua] - float(vb) * UNITS[ub]) < 1e-6
    except (ValueError, KeyError):
        return False


def _cnx(db, cid=None):
    ref = db.execute("select CnxRef from Cnx" + (f" where CnxID={cid}" if cid else "")).fetchone()[0]
    return (dict((r[0], r[2]) for r in db.execute(f'select * from "{ref}"')),
            db.execute(f'select * from "{ref}_Loads"').fetchall())


def test_export_base_matches_ram_cb1():
    """Chân cột CB 1 "Pinned BP" xuất ra trùng từng thuộc tính / bảng tải với connection gốc của RAM 24 (trong khuôn)."""
    import base_defaults as BD
    st = BD.merge(BD.BASE, BD.PRESETS["RAM CB 1 — Pinned BP (I 300x215x5x10)"])
    st["opt"].update(tpMax=76.2, tpMin=6.35)                                    # tiêu chí optimize như file RAM
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "cb.rcnx")
        res = X.export_rcnx([st], out, False, kinds=["base"])
        assert not res["warnings"], res["warnings"]
        a = sqlite3.connect(f"file:{X.PROTO}?mode=ro", uri=True); b = sqlite3.connect(out)
        (pa, la), (pb, lb) = _cnx(a, 1), _cnx(b)
        diff = {k for k in pa if not _same(pa[k], pb[k])} - {"Optimize"}
        assert not diff and set(pa) == set(pb), {k: (pa[k], pb[k]) for k in diff}
        assert la == lb, (la, lb)
        assert a.execute("select * from Joints_Estados where Joints=1").fetchall() == \
            [(r[0] and 1,) + r[1:] for r in b.execute("select * from Joints_Estados").fetchall()]
        jb = b.execute("select JointFamily, JointSection2, JointMaterial2, JointDescription from Joints").fetchone()
        assert jb == (10, "I 300x215x5x10", "Q345", "COT KHUNG CHINH: 4M27 (4.6), PL.16mm"), jb
        assert b.execute("pragma integrity_check").fetchone()[0] == "ok"
        a.close(); b.close()


def splice_bs20():
    """Nối dầm BS #20 của file RAM 24: I 500x185x5x8, (4+4)M24, PL16, mở rộng 2 phía, có sườn 10 mm."""
    import copy
    import splice_defaults as SD
    st = copy.deepcopy(SD.BASE)
    st.update(name="MEP_BS_EU_3/8_PL_2B_1B1/2", type="straight", slope=0.0)
    st["beam1"].update(sec="I 500x185x5x8", mat="Q345", L=1.5); st["beam2"].update(same=True, sec="I 500x185x5x8", L=1.5)
    st["plate"].update(extension="both", tp1=16, tp2=16, g=100, Lev=50, Leh=50, pfoT=50, pfiT=50, nT=1, pbT=100,
                       pfoB=50, pfiB=50, nB=1, pbB=100, flushExt=25.4)
    st["plate"]["stiffT"].update(on=True, ts=10); st["plate"]["stiffB"].update(on=True, ts=10)
    st["bolt"].update(d=24, grade="8.8", snug=True)
    for k in ("flT", "flB", "web"):
        st["weld"][k]["D"] = 5
    st["loads"] = [dict(name="Mmax", N=-63, V=77, M=230)] + [dict(name=n, N=0, V=0, M=0) for n in ("Pmax", "Vmax", "Mmin", "Pmin")]
    return st


def test_export_splice_matches_ram_bs20():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "bs.rcnx")
        res = X.export_rcnx([splice_bs20()], out, False, kinds=["splice"])
        assert not res["warnings"], res["warnings"]
        a = sqlite3.connect(f"file:{X.PROTO}?mode=ro", uri=True); b = sqlite3.connect(out)
        (pa, la), (pb, lb) = _cnx(a, 20), _cnx(b)
        diff = {k for k in pa if not _same(pa[k], pb[k])}
        assert not diff and set(pa) == set(pb), {k: (pa[k], pb[k]) for k in diff}
        assert la == lb, (la, lb)
        assert b.execute("select * from Joints_Estados").fetchall() == [(1, 0, 77.0, 230.0, -63.0) + (None,) * 7]
        a.close(); b.close()


def test_export_mixed_project():
    """Knee + chân cột + nối dầm + apex trong cùng 1 file; apex: IsApex = 1, SlopeAngle = −độ dốc (như RAM)."""
    import base_defaults as BD
    import splice_defaults as SD
    ap = SD.merge(SD.BASE, SD.PRESETS["Mẫu Apex — đỉnh mái dốc 10°"]) if hasattr(SD, "merge") else None
    if ap is None:
        import copy
        ap = copy.deepcopy(SD.BASE); ap.update(type="apex", slope=10.0)
    states = [merge(BASE, PRESETS["Đối chứng RAM #11"]), BD.merge(BD.BASE, {}), splice_bs20(), ap]
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "all.rcnx")
        res = X.export_rcnx(states, out, False, kinds=["knee", "base", "splice", "splice"])
        b = sqlite3.connect(out)
        cls = [b.execute(f'select PropertyValue from "{r}" where PropertyName=\'ClassName\'').fetchone()[0]
               for r, in b.execute("select CnxRef from Cnx order by CnxID")]
        assert cls == ["Bentley.AISC.MEPlateKneeBCF", "Bentley.AISC.BasePlate", "Bentley.AISC.MEPlateBeamSplice",
                       "Bentley.AISC.MEPlateBeamSplice"], cls
        p4, _ = _cnx(b, 4)
        assert p4["IsApex"] == "1" and float(p4["SlopeAngle"]) == -10.0
        assert [r[0] for r in b.execute("select JointFamily from Joints order by JointID")] == [1, 10, 4, 4]
        assert b.execute("select count(*) from ConnectionObjects").fetchone()[0] == 5
        # điều kiện tải dùng chung theo vị trí: chân cột (5 tải) nằm ở 5 điều kiện đầu, không có dòng của nút khác chen trên
        n_lc = max(len(st["loads"]) for st in states)
        assert int(b.execute("select PropertyValue from ModelData_LoadConditions where PropertyName='Count'").fetchone()[0]) == n_lc
        cb = [k for (k,) in b.execute("select Estados from Joints_Estados where Joints=2 order by Estados")]
        assert cb and max(cb) < len(states[1]["loads"]), cb
        assert b.execute("pragma integrity_check").fetchone()[0] == "ok"
        b.close()


def test_export_matches_ram_knee11():
    """Knee #11 xuất ra phải trùng thuộc tính với knee #11 gốc của RAM (trừ cách ghi đơn vị)."""
    with tempfile.TemporaryDirectory() as tmp:
        sec = os.path.join(tmp, "sec"); os.makedirs(sec)
        st = merge(BASE, PRESETS["Đối chứng RAM #11"]); st["gen"]["designCode"] = "AISC 2016 LRFD"
        out = os.path.join(tmp, "t.rcnx")
        res = X.export_rcnx([st, merge(BASE, {})], out, True, sec)
        assert res["n"] == 2 and res["sections"]["added"], res
        a = sqlite3.connect(f"file:{KNEE11}?mode=ro", uri=True); b = sqlite3.connect(out)
        ra = a.execute("select CnxRef from Cnx").fetchone()[0]
        pa = dict((r[0], r[2]) for r in a.execute(f'select * from "{ra}"'))
        cn = b.execute("select CnxRef, CnxJoint, CnxID from Cnx order by CnxID").fetchall()
        pb = dict((r[0], r[2]) for r in b.execute(f'select * from "{cn[0][0]}"'))
        unit_only = {"BeamInitialDepth", "BeamFinalDepth", "BeamLength", "SupportInitialDepth", "SupportFinalDepth", "SupportLength",
                     "FlushExtensionDistance", "SupportSectionTapered", "InnerTopBoltSpaV", "InnerBottomBoltSpaV"}
        diff = {k for k in pa if pa[k] != pb.get(k)} - unit_only - {"Bolt", "FrameworkVersion", "TransverseStiffenersLength"}   # chiều dài sườn: không dùng khi sườn suốt chiều cao
        assert not diff and set(pa) <= set(pb), diff
        assert pa["Bolt"] == "M24 G_8_8" and pb["Bolt"] == "M24 G88"            # RAM 23 → tên bu lông RAM 24
        assert pb["SupportInitialDepth"] == "616 mm" and pb["SupportFinalDepth"] == "416 mm"
        assert [c[1:] for c in cn] == [(1, 1), (2, 2)]
        assert b.execute("select count(*) from Joints").fetchone()[0] == 2
        assert b.execute("pragma integrity_check").fetchone()[0] == "ok"
        p2 = dict((r[0], r[2]) for r in b.execute(f'select * from "{cn[1][0]}"'))
        assert (p2["DesignCode"], p2["PlateAlignment"], p2["BEPlateType"]) == ("3", "2", "1")
        a.close(); b.close()
        # ghi lần 2: không thêm trùng, có sao lưu
        res2 = X.export_rcnx([st], os.path.join(tmp, "t2.rcnx"), True, sec)
        assert not res2["sections"]["added"] and len(res2["sections"]["existed"]) == 2
        txt = open(os.path.join(sec, X.SEC_FILE), encoding="utf-8", newline="").read()
        assert txt.startswith("[BuiltUpI.leo]\r\n") and "I 600x150x5x8\tFALSE\tFALSE\tmm\t150\t150\t616\t8\t8\t5\r\n" in txt


def test_report_english():
    st = merge(BASE, PRESETS["Đối chứng RAM #11"])
    rep = RP.build(st, K.compute(st))
    text = "".join(t for t, _ in RP.to_text(rep))
    for must in ("Steel Connections", "Demands", "Geometric Considerations", "Plate / Column Behavior", "Design Check",
                 "Moment end plate (external flange)", "Bolt rupture with prying moment strength", "Global critical strength ratio"):
        assert must in text, must
    with tempfile.TemporaryDirectory() as tmp:
        RP.to_docx(rep, os.path.join(tmp, "r.docx"))
        import zipfile
        from xml.dom import minidom
        minidom.parseString(zipfile.ZipFile(os.path.join(tmp, "r.docx")).read("word/document.xml"))


if __name__ == "__main__":
    test_export_matches_ram_knee11(); print("PASS test_export_matches_ram_knee11")
    test_report_english(); print("PASS test_report_english")
    test_export_base_matches_ram_cb1(); print("PASS test_export_base_matches_ram_cb1")
    test_export_splice_matches_ram_bs20(); print("PASS test_export_splice_matches_ram_bs20")
    test_export_mixed_project(); print("PASS test_export_mixed_project")
