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
    # Column base (CB): New joint → Data → Loads → OK, các ô xem, Smart connection, Connection Pad
    d = NJ.NewJointDialog(app, None); _spin(app)
    d._pick_group(2); d._pick(1); _spin(app)
    check("New joint: Column base chọn được", d._key() == "base" and "CB" in d.lbl_title.cget("text"))
    d._next("data"); _spin(app)
    check("bước Data chân cột", d.page == "data" and d.S["col"]["sec"])
    d._show("loads"); _spin(app)
    check("bước Loads chân cột (5 cột tải)", d.page == "loads" and len(NJ.LOAD_SPEC["base"]) == 6)
    # Lấy phản lực chân cột từ SAP (giả lập kết nối)
    import scanner

    class FakeConn:
        is_connected, last_error = True, ""
        def set_units_kn_m(self): pass
        def list_load_names(self, src): return ["ULS1", "ULS2"], set()
        def setup_output_source(self, src, ch): return ["ULS1", "ULS2"]
        def allowed_loads_for_frame(self, f, src, ch): return set(ch)
    NJ._SAP["conn"] = FakeConn()
    old_br = scanner.base_reactions
    scanner.base_reactions = lambda conn, allowed_for, signs=None, progress=None: ([
        dict(joint="1", frame="C1", case="ULS1", step="", N=-214.0, V2=60.0, V3=0.0, M22=0.0, M33=12.0),
        dict(joint="1", frame="C1", case="ULS2", step="", N=110.0, V2=-23.0, V3=10.0, M22=0.0, M33=-8.0)], [])
    pan = [w for w in d.body.winfo_children() for w in [w] + list(w.winfo_children()) if isinstance(w, NJ.BaseSapPanel)]
    if pan: pan[0]._get(); _spin(app)
    scanner.base_reactions = old_br; NJ._SAP.clear()
    names = [r["name"] for r in d.S["loads"]]
    check("Loads chân cột: lấy phản lực SAP → Mmax, Pmax, Vmax, Mmin, Pmin",
          bool(pan) and names == ["Mmax", "Pmax", "Vmax", "Mmin", "Pmin"] and d.S["loads"][1]["N"] == -214.0
          and d.S["loads"][4]["N"] == 110.0 and d.S["loads"][0]["M33"] == 0 and len(pan[0].grid_.tv.get_children()) == 5)
    d._ok()
    jb = app.project.add(d.result["kind"], d.result["state"]); app.refresh(); app.select(jb["id"]); _spin(app)
    check("tạo Column base", jb["kind"] == "base" and app.result(jb)[1]["gov"] is not None)
    # Home → RAM Connection → Export: mọi liên kết của dự án
    import knee_gui
    import ram_export
    got = {}
    old_dlg = knee_gui.export_rcnx_dialog
    knee_gui.export_rcnx_dialog = lambda states, ms=True, extra="", kinds=None: got.update(n=len(states), kinds=kinds) or "ok"
    app.export_rcnx(); _spin(app)
    knee_gui.export_rcnx_dialog = old_dlg
    check("Export RAM .rcnx: xuất mọi liên kết (knee, splice, chân cột)",
          got.get("n") == len(app.project.joints) and got.get("kinds") == [j["kind"] for j in app.project.joints]
          and "base" in got["kinds"] and all(ram_export.supported(k) for k in ("knee", "base", "splice")))
    for mode in ("3D", "3D D/C", "Elevation", "End plate"):
        app.cmb_view.set(mode); app._draw(); _spin(app, 3)
    app.cmb_view.set("3D"); app._draw()
    check("chân cột: các ô xem 3D / 2D", not errs)
    app.smart_connection(); _spin(app)
    check("Smart connection chân cột", app.result(app.project.get(jb["id"]))[1] is not None)
    w = app.db_anchors(); _spin(app, 3); w.destroy()
    app.edit_joint(); _spin(app, 20)
    ed = app.editors[jb["id"]]
    check("Connection Pad chân cột: ô tỷ số", ed.box.cget("text") not in ("—", "!"))
    f = next(x for x in ed.fields if x["spec"].get("p") == "plate.tp")
    f["var"].set("50"); _spin(app, 30)
    f = next(x for x in ed.fields if x["spec"].get("p") == "lug.on")
    f["var"].set(True); ed._changed(f, True); _spin(app, 30)
    check("Connection Pad chân cột: sửa tp, Include shear lug", ed.S["plate"]["tp"] == 50 and ed.S["lug"]["on"]
          and any(c["id"] == "lug_bear" for c in ed.R["checks"]))
    f = next(x for x in ed.fields if x["spec"].get("p") == "gen.axis")
    f["var"].set("Biaxial"); ed._changed(f, True); _spin(app, 30)
    check("Connection Pad chân cột: Analysis axis = Biaxial", ed.R is not None and any(c["id"] == "conc_bear_bi" for c in ed.R["checks"]))
    w = ed.results(); _spin(app, 3)
    rid = next(iter(w.row_boxes)); w.select(rid); _spin(app, 3)
    check("Results chân cột (form RAM, chọn dòng → diễn giải)", w.det.get("1.0", "end").strip().startswith(w.byid[rid]["name"])); w.destroy()
    w = ed.print_preview(); check("Print chân cột", w is not None); w.destroy()
    ed.optimize(); _spin(app, 5)
    ed.open_loads(); _spin(app, 5)
    check("Loads chân cột mở được", ed.loads_win is not None and ed.loads_win.winfo_exists()); ed.loads_win.destroy(); _spin(app)
    ed.ok(); _spin(app)
    check("Edit chân cột → OK lưu", app.project.get(jb["id"])["state"]["lug"]["on"] is True)
    docx = os.path.join(tmp, "cb.docx"); A.filedialog.asksaveasfilename = lambda **k: docx
    app.report_one()
    check("Report Word chân cột", os.path.getsize(docx) > 2000)
    app.save_project(); app3 = PJ.Project.load(path)
    check("Save → mở lại có chân cột", any(x["kind"] == "base" for x in app3.joints))
    app.delete_all(); _spin(app)
    check("Delete all", app.project.joints == [])
    check("không có exception trong callback", not errs)
    app.project.dirty = False; app.destroy()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
