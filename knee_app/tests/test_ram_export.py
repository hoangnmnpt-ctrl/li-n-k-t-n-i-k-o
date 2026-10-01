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


def test_export_matches_ram_knee11():
    """Knee #11 xuất ra phải trùng thuộc tính với knee #11 gốc của RAM (trừ cách ghi đơn vị)."""
    with tempfile.TemporaryDirectory() as tmp:
        sec = os.path.join(tmp, "sec"); os.makedirs(sec)
        st = merge(BASE, PRESETS["Đối chứng RAM #11"]); st["gen"]["designCode"] = "AISC 2016 LRFD"
        out = os.path.join(tmp, "t.rcnx")
        res = X.export_rcnx([st, merge(BASE, {})], out, True, sec)
        assert res["n"] == 2 and res["sections"]["added"], res
        a = sqlite3.connect(f"file:{X.PROTO}?mode=ro", uri=True); b = sqlite3.connect(out)
        ra = a.execute("select CnxRef from Cnx").fetchone()[0]
        pa = dict((r[0], r[2]) for r in a.execute(f'select * from "{ra}"'))
        cn = b.execute("select CnxRef, CnxJoint, CnxID from Cnx order by CnxID").fetchall()
        pb = dict((r[0], r[2]) for r in b.execute(f'select * from "{cn[0][0]}"'))
        unit_only = {"BeamInitialDepth", "BeamFinalDepth", "BeamLength", "SupportInitialDepth", "SupportFinalDepth", "SupportLength",
                     "FlushExtensionDistance", "SupportSectionTapered", "InnerTopBoltSpaV", "InnerBottomBoltSpaV"}
        diff = {k for k in pa if pa[k] != pb.get(k)} - unit_only
        assert not diff and set(pa) == set(pb), diff
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
