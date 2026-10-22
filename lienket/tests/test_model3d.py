"""Kiểm tra mô hình 3D (model3d) và thứ tự vẽ (ramview).  Chạy: python tests/test_model3d.py
Phần thứ tự vẽ cần tkinter + màn hình (Linux: xvfb-run); tự bỏ qua nếu không có."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engine as K  # noqa: E402
import model3d as M  # noqa: E402
import splice_engine as SE  # noqa: E402
from defaults import BASE, PRESETS, merge  # noqa: E402
from splice_defaults import BASE as SB, PRESETS as SP, merge as smerge  # noqa: E402
from model3d import v_dot, v_sub  # noqa: E402


def cases():
    for p in PRESETS.values():
        st = merge(BASE, p); yield "knee", st, K.compute(st)
    for p in SP.values():
        st = smerge(SB, p); yield "splice", st, SE.compute(st)


def test_models_build_and_normals_point_out():
    for kind, st, R in cases():
        m = M.build(kind, st, R)
        assert m.solids, kind
        for so in m.solids:
            vs = so.verts
            c = tuple(sum(v[i] for v in vs) / len(vs) for i in range(3))
            for poly, n in so.faces:
                fc = tuple(sum(p[i] for p in poly) / len(poly) for i in range(3))
                if so.convex:
                    assert v_dot(n, v_sub(fc, c)) > -1e-6, (kind, so.tags)


def test_bolt_count_matches_rows():
    for kind, st, R in cases():
        m = M.build(kind, st, R)
        G = R["G"]
        rows = len(G["rowsE"]) + len(G["rowsI"]) if kind == "knee" else len(G["rowsT"]) + len(G["rowsB"])
        nb = sum(1 for so in m.solids if so.color == M.BOLT)
        assert nb == rows * 2 * 2, (kind, nb, rows)            # 2 bu lông / hàng, mỗi bu lông có đầu + đai ốc


def test_welds_and_end_plate_present():
    for kind, st, R in cases():
        m = M.build(kind, st, R)
        assert any(so.color == M.WELD for so in m.solids)
        assert any(so.color == M.END_PLATE for so in m.solids)


def test_draw_order_has_no_cycles():
    """Thứ tự vẽ giữa các khối (mặt phẳng phân cách) không có vòng lặp ở góc mặc định và vài góc xoay."""
    try:
        import tkinter as tk
        root = tk.Tk()
    except Exception as e:  # noqa: BLE001
        print("SKIP draw order:", e); return
    import ramview as RV
    v = RV.RamView(root, width=500, height=500); v.pack(); root.update()
    for kind, st, R in cases():
        v.show_model(M.build(kind, st, R))
        for yaw, pitch in ((RV.YAW0, RV.PITCH0), (-35, 20), (60, 30), (10, 5)):
            v.yaw, v.pitch = yaw, pitch; v.redraw()
            assert v.cycles == 0, (kind, st.get("name"), yaw, pitch, v.cycles)
    root.destroy()


if __name__ == "__main__":
    fails = 0
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f(); print("PASS", n)
            except AssertionError as e:
                fails += 1; print("FAIL", n, e)
    sys.exit(1 if fails else 0)
