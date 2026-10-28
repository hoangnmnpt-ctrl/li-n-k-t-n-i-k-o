"""Kiểm tra scanner với mô hình SAP giả lập: khung cổng 2 cột + 2 kèo (có đỉnh kèo)."""

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import scanner  # noqa: E402
from sap2000_connector import FrameForceRow, FrameInfo  # noqa: E402

PTS = {"1": (0, 0, 0), "2": (0, 0, 7), "3": (12, 0, 9), "4": (24, 0, 0), "5": (24, 0, 7)}
FR = {"C1": ("1", "2", "(280-570).8-250.16"), "R1": ("2", "3", "(580-380).6-200.10"),
      "R2": ("3", "5", "(380-580).6-200.10"), "C2": ("4", "5", "(280-570).8-250.16")}


class FakeFrameObj:
    def GetPoints(self, f, a, b): return (FR[f][0], FR[f][1], 0)
    def GetNameList(self, n, lst): return (len(FR), list(FR), 0)
    def GetTransformationMatrix(self, f, v, g):
        p1, p2 = PTS[FR[f][0]], PTS[FR[f][1]]
        if f.startswith("C"):
            l2 = (1.0, 0.0, 0.0)
        else:
            import math
            dx, dz = p2[0] - p1[0], p2[2] - p1[2]; L = math.hypot(dx, dz)
            l2 = (-dz / L * (1 if dx > 0 else -1), 0.0, abs(dx) / L)
        return ([0, l2[0], 0, 0, l2[1], 0, 0, l2[2], 0], 0)


class FakeModel:
    FrameObj = FakeFrameObj()


class FakeConn:
    _sap_model = FakeModel()
    last_error = ""
    def get_selected_frames(self): return list(FR)
    def _extract_name_list(self, ret): return list(ret[1])
    def _point_xyz(self, p): return PTS[p]
    def get_frame_info(self, f):
        import math
        a, b = PTS[FR[f][0]], PTS[FR[f][1]]
        return FrameInfo(name=f, section_name=FR[f][2], length=math.dist(a, b), prop_name=FR[f][2])
    def get_frame_forces(self, f):
        import math
        L = math.dist(PTS[FR[f][0]], PTS[FR[f][1]])
        rows = []
        # gravity: M3 dương ở cột trái đỉnh (mặt −X kéo = mặt ngoài), kèo đầu I âm (thớ trên kéo)
        M = {"C1": (0, 240), "R1": (-240, 60), "R2": (60, -240), "C2": (0, -240)}[f]
        for lc, k in (("COMB1", 1.0), ("COMB2", -0.5)):
            rows.append(FrameForceRow(obj_station=0.0, load_case=lc, P=-50 * k, V2=40 * k, M3=M[0] * k))
            rows.append(FrameForceRow(obj_station=L, load_case=lc, P=-50 * k, V2=40 * k, M3=M[1] * k))
        return rows


def test_scan_portal():
    knees = scanner.scan(FakeConn(), False, lambda f: None)
    assert [k.joint for k in knees] == ["2", "5"], [k.joint for k in knees]
    k1, k2 = knees
    assert (k1.col, k1.col_end, k1.raf, k1.raf_end) == ("C1", "J", "R1", "I")
    assert abs(k1.slope - 9.46) < 0.01
    # gravity COMB1 → tool: M < 0 (cánh ngoài kéo) cho cả cột và kèo ở cả hai knee
    for k in knees:
        r = next(x for x in k.loads if x["name"] == "COMB1")
        assert r["Mb"] < 0 and r["Mc"] < 0, (k.joint, r)
    assert k1.group == k2.group, "knee đối xứng phải cùng nhóm"
    st = scanner.knee_to_state(__import__("defaults").BASE, [k1, k2], k1.group)
    assert len(st["loads"]) == len(k1.loads) + len(k2.loads)


def test_api_dims_and_pick():
    from sap2000_connector import SectionDims

    class Conn(FakeConn):
        def get_frame_info(self, f):
            info = super().get_frame_info(f)
            if f == "C1":
                info.section_name = info.prop_name = "COL_SAP"
            return info

        def get_section_dimensions(self, sec, x, L):
            return SectionDims(type_name="I-Section", t3=0.602, t2=0.25, tf=0.016, tw=0.008, t2b=0.25, tfb=0.016)

        def get_selected_frames(self): return []
        def get_selected_points(self): return ["2"]

    class PO:
        def GetConnectivity(self, p, n, a, b, c):
            fr = [f for f, v in FR.items() if p in v[:2]]
            return (len(fr), [2] * len(fr), fr, [1] * len(fr), 0)
    FakeModel.PointObj = PO()
    knees = scanner.pick(Conn(), lambda f: None)
    assert len(knees) == 1 and knees[0].joint == "2", [k.joint for k in knees]
    k = knees[0]
    assert k.col_dims and abs(k.col_dims["d"] - 602) < 1e-6
    import engine, defaults
    st = scanner.knee_to_state(defaults.BASE, [k], "G1")
    r = engine.compute(st)
    assert r["G"]["col"]["d"] == 602 and st["sap_lock"]


def test_base_reactions():
    """Phản lực gối → lực cột lên bản đế (quy ước RAM) và cực trị Mmax, Pmax, Vmax, Mmin, Pmin."""
    from sap2000_connector import JointReactRow

    class G:
        name, p1, p2, x1, x2 = "C1", "1", "2", (0.0, 0.0, 5.0), (0.0, 0.0, 0.0)     # cột vẽ từ trên xuống

    class Conn:
        class _sap_model:
            class FrameObj:
                @staticmethod
                def GetTransformationMatrix(*a): raise RuntimeError
    u, e2, e3 = axes = scanner.base_axes(Conn, G)
    assert u == (0.0, 0.0, 1.0) and e2 == (1.0, 0.0, 0.0) and e3 == (0.0, 1.0, 0.0)
    # Lực ngang H = 10 kN theo +X tại đỉnh cột cao 5 m, nén 214 kN → gối: F1 = −10, F3 = +214, M2 = −50
    v = scanner.reaction_to_base(JointReactRow("1", "U", F1=-10, F3=214, M2=-50), axes)
    assert v == dict(N=-214.0, V2=-10.0, V3=0.0, M22=0.0, M33=50.0), v
    v = scanner.reaction_to_base(JointReactRow("1", "U", F1=-10, F3=214, M2=-50), axes, {"M33": -1, "N": -1})
    assert v["M33"] == -50.0 and v["N"] == 214.0
    recs = [dict(joint="1", frame="C1", case=f"U{i}", step="", N=-200.0 + 60 * i, V2=5.0 * i, V3=0.0, M22=0.0, M33=10.0 - 7 * i)
            for i in range(5)]
    ex = scanner.base_extremes(recs)
    assert [r["name"] for r in ex] == ["Mmax", "Pmax", "Vmax", "Mmin", "Pmin"], ex
    assert [r["case"] for r in ex] == ["", "U0", "U4", "", "U4"]
    assert all(ex[i][k] == 0 for i in (0, 3) for k in scanner.BASE_KEYS) and ex[1]["N"] == -200 and ex[4]["N"] == 40
    # Vmax theo |V2| (như sắp xếp F1 trong SAP), không theo hợp lực: 33.4 > 32.448 dù √(32.448² + 11.712²) = 34.5
    r2 = [dict(joint="142", frame="C", case="LRFD: 23", step="", N=-98.57, V2=-33.4, V3=-0.012, M22=0, M33=0),
          dict(joint="169", frame="C", case="LRFD: 29", step="", N=-100.753, V2=-32.448, V3=-11.712, M22=0, M33=0)]
    assert scanner.base_extremes(r2)[2]["V2"] == -33.4


if __name__ == "__main__":
    test_scan_portal(); print("PASS test_scan_portal")
    test_api_dims_and_pick(); print("PASS test_api_dims_and_pick")
    test_base_reactions(); print("PASS test_base_reactions")
