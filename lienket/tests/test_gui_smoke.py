"""Smoke test giao diện (cần customtkinter + màn hình; Linux không màn hình: xvfb-run -a python tests/test_gui_smoke.py).
Tự bỏ qua nếu thiếu tkinter / customtkinter / DISPLAY. Không ghi vào dự án thật (dùng file tạm)."""

import os
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def _spin(app, n=10):
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
    from tkinter import messagebox
    import app as A
    import newjoint as NJ
    import project as PJ

    messagebox.askyesno = lambda *a, **k: True          # tự xác nhận các hộp thoại hỏi
    messagebox.showinfo = messagebox.showwarning = lambda *a, **k: None
    tmp = tempfile.mkdtemp()
    A.SETTINGS = os.path.join(tmp, "settings.json")
    path = os.path.join(tmp, "p.lkt")
    PJ.Project(path).save()
    errs, fails = [], []
    app = A.App(path)
    app.report_callback_exception = lambda *a: (errs.append(a), traceback.print_exception(*a))
    _spin(app)

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond: fails.append(name)

    check("mở dự án trống", app.project.joints == [] and "Elements: 0" in app.lbl_count.cget("text"))

    # New joint 3 bước: Joint → Data → Loads → OK
    d = NJ.NewJointDialog(app, "knee", "K-01"); _spin(app)
    check("New joint: mặc định chọn Knee", d._key() == "knee" and "BCF" in d.lbl_title.cget("text"))
    d._next("data"); _spin(app)
    check("bước Data có bảng thuộc tính knee", d.page == "data" and d.S["beam"]["sec"])
    d.S["beam"]["sec"] = "600.6-200.12"
    d._show("loads"); _spin(app)
    check("bước Loads", d.page == "loads")
    d._ok()
    j = app.project.add(d.result["kind"], d.result["state"]); app.refresh(); app.select(j["id"]); _spin(app)
    check("tạo knee qua 3 bước", app.project.get(j["id"])["state"]["beam"]["sec"] == "600.6-200.12")

    d = NJ.NewJointDialog(app, "splice:apex"); _spin(app)
    d._next("data"); d._ok()
    j2 = app.project.add(d.result["kind"], d.result["state"]); app.refresh(); app.select(j2["id"]); _spin(app)
    check("tạo Apex", app.project.get(j2["id"])["state"]["type"] == "apex" and j2["id"] in app.cards)

    d = NJ.NewJointDialog(app, None); _spin(app)
    d._pick_group(0); d._pick(0); d._next("data")
    check("kiểu chưa hỗ trợ không sang bước Data", d.page == "joint"); d.destroy()

    # Ribbon
    app.copy_joint(); _spin(app)
    check("Copy", len(app.project.joints) == 3)
    app.delete_joint(); _spin(app)
    check("Delete", len(app.project.joints) == 2)
    app.ent_goto.delete(0, "end"); app.ent_goto.insert(0, str(j["id"])); app._goto(); _spin(app)
    check("Go to", app.sel == j["id"])
    app.cmb_view.set("End plate"); app._draw(); _spin(app); app.cmb_view.set("Elevation"); app._draw()
    app.toggle_critical(); _spin(app)
    check("Critical load condition", app.critical and app.cmb_cond.get() != ""); app.toggle_critical()
    app.smart_connection(); _spin(app)
    check("Smart connection", app.result(app.project.get(j["id"]))[1] is not None)
    for f in (app.db_sections, app.db_materials, app.db_bolts, app.db_welds, app.db_connections, app.info_log):
        w = f(); _spin(app, 3)
        if w is not None: w.destroy()
    check("Databases + Information log mở được", not errs)
    app.design_all(); _spin(app)

    # Edit: cửa sổ thiết kế, sửa và OK
    app.select(j2["id"]); app.edit_joint(); _spin(app, 20)
    ed = app.editors[j2["id"]]
    check("Connection Pad: ô tỷ số", ed.box.cget("text") not in ("—", "!"))
    ed.S["plate"]["tp1"] = ed.S["plate"]["tp2"] = 25; ed.ok(); _spin(app)
    check("Edit → OK lưu vào dự án", app.project.get(j2["id"])["state"]["plate"]["tp1"] == 25)
    app.select(j["id"]); app.edit_joint("Loads"); _spin(app, 20)
    ed = app.editors[j["id"]]
    check("Edit knee mở bảng Loads", ed.loads_win is not None and ed.loads_win.winfo_exists())
    ed.loads_win.destroy(); _spin(app)
    for st_ in ("lines", "transparent", "solid"): ed.set_style(st_)
    w = ed.results(); check("Results mở được", w is not None); w.destroy()
    w = ed.print_preview(); check("Print (xem báo cáo) mở được", w is not None); w.destroy()
    adv = app.advanced_editor(app.project.get(j["id"])); _spin(app, 10)
    check("Advanced (khung thiết kế đầy đủ)", adv.panel.S["name"] == ed.S["name"]); adv.destroy()
    ed.destroy()

    # lưu / mở lại
    app.save_project(); app2 = PJ.Project.load(path)
    check("Save → mở lại", [x["id"] for x in app2.joints] == [x["id"] for x in app.project.joints])
    out = os.path.join(tmp, "r.csv")
    A.filedialog.asksaveasfilename = lambda **k: out
    app.export_csv()
    check("Results table CSV", os.path.getsize(out) > 50)
    docx = os.path.join(tmp, "r.docx"); A.filedialog.asksaveasfilename = lambda **k: docx
    app.report_one()
    check("Report Word", os.path.getsize(docx) > 2000)
    app.delete_all(); _spin(app)
    check("Delete all", app.project.joints == [])
    check("không có exception trong callback", not errs)
    app.project.dirty = False; app.destroy()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
