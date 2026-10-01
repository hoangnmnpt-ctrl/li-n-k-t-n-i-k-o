"""Smoke test giao diện (cần customtkinter + màn hình; trên Linux không có màn hình: xvfb-run -a python tests/test_gui_smoke.py).
Tự bỏ qua nếu thiếu tkinter / customtkinter / DISPLAY."""

import os
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def _spin(app, n=12):
    for _ in range(n):
        app.update(); time.sleep(0.02)


def main() -> int:
    try:
        import tkinter  # noqa: F401
        import customtkinter  # noqa: F401
    except ImportError as e:
        print("SKIP (thiếu thư viện giao diện):", e); return 0
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        print("SKIP (không có DISPLAY)"); return 0
    import splice_gui as G
    import splice_store

    tmp = tempfile.mkdtemp()
    splice_store.PATH = os.path.join(tmp, "saved.json")
    errs = []
    app = G.App()
    app.saved = splice_store.SavedList(os.path.join(tmp, "saved.json"))
    app.report_callback_exception = lambda *a: (errs.append(a), traceback.print_exception(*a))
    _spin(app)
    fails = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond: fails.append(name)

    check("khởi động có kết quả", app.R is not None and app.R["gov"] is not None)
    r0 = app.R["gov"]["ratio"]

    # gõ vào ô tp1 → tính lại
    f = next(x for x in app.fields if x["spec"].get("p") == "plate.tp1")
    f["var"].set("12"); app.run(); _spin(app)
    check("đổi tp1 = 12 → D/C bản 1 tăng", app.R["checks"][0]["id"].startswith("pl1") and
          next(c for c in app.R["checks"] if c["id"] == "pl1_flex_T")["ratio"] > 1.0)
    check("tp1 lưu vào state", app.S["plate"]["tp1"] == 12.0)

    # đổi kiểu bích sang flush: hàng bu lông giảm
    f = next(x for x in app.fields if x["spec"].get("p") == "plate.extension")
    f["w"].set("Flush"); app._changed(f, True); app.run(); _spin(app)
    check("flush → cấu hình 2FU", app.R["sides"]["T"]["cfg"] == "2FU")
    f["w"].set("Extended both edges"); app._changed(f, True)

    # Apex
    app._type_changed("Apex"); _spin(app)
    check("apex có góc dốc", app.R["G"]["type"] == "apex" and app.R["G"]["alpha"] > 0)
    app._type_changed("Beam splice"); _spin(app)

    # tự chọn
    import splice_engine as SE
    app.S["plate"]["tp1"] = app.S["plate"]["tp2"] = 10; app.S["bolt"]["d"] = 16
    app._load_form(); app.run()
    bad = app.R["gov"]["ratio"] > 1.0
    app._auto(); _spin(app)
    check("tự chọn đưa D/C (bản, bu lông) về ≤ 1", bad and all(c["ratio"] <= 1.0001 for c in app.R["checks"] if c["id"].startswith(("pl", "bolt_", "bear_"))))

    # dán tải từ clipboard
    n0 = len(app.S["loads"])
    app.clipboard_clear(); app.clipboard_append("1\tLC_a\t-5\t40\t-100\n2\tLC_b\t10,5\t-20\t60\n")
    app._load_paste(); _spin(app)
    check("dán 2 tổ hợp", len(app.S["loads"]) == n0 + 2 and app.S["loads"][-1]["N"] == 10.5)
    app._load_add(); app._load_del()
    check("thêm / xoá tổ hợp", len(app.S["loads"]) == n0 + 3 or len(app.S["loads"]) == n0 + 2)

    # lưu danh sách + mở lại
    i = app.saved.add("TEST-1", app.S, app._summary_of(app.S))
    app._fill_saved(i); app.tree_saved.selection_set(str(i))
    app._saved_open(); _spin(app)
    check("lưu và mở lại danh sách", app.S["name"] == "TEST-1" and len(app.saved.items) == 1)

    # chọn một dòng kiểm tra, các tab, hình, báo cáo
    cid = app.R["checks"][0]["id"]
    app.tree.selection_set(cid); app._check_selected(); _spin(app)
    check("chọn dòng kiểm tra → có diễn giải", "Khả năng" in app.txt_detail.get("1.0", "end"))
    for view in ("Mặt bản đầu", "Mặt đứng"):
        app.seg_view.set(view); app._view_changed(view); _spin(app)
    check("báo cáo có nội dung", "Design Check" in app.txt_rep.get("1.0", "end"))
    import splice_report as RP
    p = os.path.join(tmp, "x.docx"); RP.to_docx(RP.build(app.S, app.R), p)
    check("xuất Word", os.path.getsize(p) > 2000)

    # lỗi nhập liệu hiển thị, không văng
    f = next(x for x in app.fields if x["spec"].get("p") == "beam1.sec")
    f["var"].set("abc"); app.run(); _spin(app)
    check("tiết diện sai → báo lỗi, không crash", app.R is None and "LỖI" in app.lbl_status.cget("text"))
    f["var"].set("500.8-200.12"); app.run(); _spin(app)
    check("sửa lại → tính lại được", app.R is not None)

    check("không có exception trong callback", not errs)
    app.destroy()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
