"""
connpad.py — Cửa sổ "Connection Pad" như RAM Connection (mở khi nhấp đúp một nút).

  • Trái: bảng thuộc tính nền xanh đậm, các mục thu gọn được (General information, Members, Moment end plate,
    Stiffeners …) — dùng chung danh sách trường với khung thiết kế (knee_gui / splice_gui.build_sections).
  • Giữa: hình 3D (RamView) + thanh công cụ nổi phía trên: Save · Print · Print to file | Optimize | Results · Data |
    Solid · Lines · Transparent | Help | ô tỷ số khống chế.
  • Dưới: OK / Apply / Cancel.  Tính lại tự động khi đổi thông số.
"""

from __future__ import annotations

import copy
import math
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import engine as K
import model3d
import newjoint
import project as PJ
import splice_engine as SE
from ramview import NAVY, RamView

PANEL = "#0E2756"          # nền bảng thuộc tính
ROW = "#123064"            # nền ô giá trị
LINE = "#1E3F78"           # đường kẻ giữa các dòng
HEAD = "#0B1F47"           # nền tiêu đề mục
SUBC = "#9DB4DC"           # chữ tiêu đề nhóm con
TXT = "#FFFFFF"
VAL = "#E6EEFA"
BAR = "#0A1A3E"            # nền thanh công cụ
BTN = "#0E2756"
BTN_ON = "#1F6FEB"
GOLD, RED = "#E5AC0B", "#D23B3B"
F = ("Segoe UI", 9)
F_HEAD = ("Segoe UI", 13)
F_SUB = ("Segoe UI", 11)


class _TabsShim:
    """build_sections gọi app.tabs.set("Loads") — ở Connection Pad mở bảng tải."""

    def __init__(self, pad):
        self.pad = pad
        self.cur = ""

    def set(self, name):
        self.cur = name
        if name == "Loads":
            self.pad.after(10, self.pad.open_loads)

    def get(self):
        return self.cur


class ConnectionPad(tk.Toplevel):
    def __init__(self, app, j: dict, tab=None):
        super().__init__(app)
        self.app, self.jid, self.kind = app, j["id"], j["kind"]
        self.S = PJ.full_state(j)
        self.R = None
        self.err = None
        self.tabs = _TabsShim(self)
        self._job = None
        self._suspend = False
        self.loads_win = None
        fam = PJ.KINDS[self.kind]["family"]
        self.title(f"Connection Pad — {fam} {j['id']} {self.S.get('name', '')}")
        self.geometry("1500x940")
        self.minsize(1000, 640)
        self.configure(background=NAVY)
        self._build()
        self._fill()
        self.run()
        self.after(100, self.lift)
        if tab == "Loads":
            self.tabs.set("Loads")

    # ───────────────────────── bố cục ─────────────────────────
    def _build(self):
        foot = tk.Frame(self, bg="#F0F0F0"); foot.pack(side="bottom", fill="x")
        for t, cmd in (("Cancel", self.destroy), ("Apply", self.apply), ("OK", self.ok)):
            tk.Button(foot, text=t, width=10, font=F, relief="groove", command=cmd).pack(side="right", padx=6, pady=6)
        self.lbl_msg = tk.Label(foot, text="", bg="#F0F0F0", fg="#5B6777", font=F, anchor="w")
        self.lbl_msg.pack(side="left", fill="x", expand=True, padx=8)

        body = tk.Frame(self, bg=NAVY); body.pack(fill="both", expand=True)
        # trái: bảng thuộc tính (cuộn)
        left = tk.Frame(body, bg=PANEL, width=430); left.pack(side="left", fill="y"); left.pack_propagate(False)
        self.cv = tk.Canvas(left, bg=PANEL, highlightthickness=0)
        sb = ttk.Scrollbar(left, orient="vertical", command=self.cv.yview)
        self.cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); self.cv.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.cv, bg=PANEL)
        self._win = self.cv.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
        self.cv.bind("<Configure>", lambda e: self.cv.itemconfigure(self._win, width=e.width))
        for w in (self.cv, self.inner):
            w.bind("<MouseWheel>", self._wheel)
        tk.Frame(body, bg="#2B4C86", width=3).pack(side="left", fill="y")
        # giữa: hình 3D + thanh công cụ nổi
        mid = tk.Frame(body, bg=NAVY); mid.pack(side="left", fill="both", expand=True)
        self.view = RamView(mid)
        self.view.pack(fill="both", expand=True)
        self._toolbar(mid)

    def _wheel(self, e):
        self.cv.yview_scroll(-1 if e.delta > 0 else 1, "units")

    def _toolbar(self, parent):
        bar = tk.Frame(parent, bg=BAR, highlightthickness=1, highlightbackground="#2B4C86")
        bar.place(relx=0.5, y=6, anchor="n")
        groups = [
            ("Connection", [("💾", "Save", self.apply), ("🖨", "Print", self.print_preview), ("📷", "Print to file", self.print_file)]),
            ("Process", [("⟳", "Optimize", self.optimize)]),
            ("Reports", [("✔", "Results", self.results), ("▦", "Data", self.open_data)]),
            ("Draw options", [("■", "Solid", lambda: self.set_style("solid")), ("▢", "Lines", lambda: self.set_style("lines")),
                              ("◧", "Transparent", lambda: self.set_style("transparent"))]),
            ("Tool", [("⚙", "Advanced", self.advanced)]),
            ("Help", [("?", "Help", self.help)]),
        ]
        self.style_btns = {}
        for gi, (gname, items) in enumerate(groups):
            g = tk.Frame(bar, bg=BAR); g.grid(row=0, column=gi, padx=(0, 4), sticky="ns")
            row = tk.Frame(g, bg=BAR); row.pack()
            for icon, lab, cmd in items:
                b = tk.Frame(row, bg=BTN, width=68, height=56, cursor="hand2"); b.pack(side="left", padx=1, pady=(2, 0)); b.pack_propagate(False)
                l1 = tk.Label(b, text=icon, bg=BTN, fg=TXT, font=("Segoe UI Symbol", 15))
                l2 = tk.Label(b, text=lab, bg=BTN, fg=TXT, font=("Segoe UI", 8))
                l1.pack(pady=(4, 0)); l2.pack()
                for w in (b, l1, l2):
                    w.bind("<Button-1>", lambda e, c=cmd: c())
                if gname == "Draw options":
                    self.style_btns[lab.lower()] = (b, l1, l2)
            tk.Label(g, text=gname, bg=BAR, fg=SUBC, font=("Segoe UI", 8)).pack(fill="x")
        self.box = tk.Label(bar, text="—", bg=GOLD, fg=TXT, font=("Segoe UI", 18), width=5)
        self.box.grid(row=0, column=len(groups), sticky="nsew", padx=(4, 0))
        self.set_style("solid", redraw=False)

    def set_style(self, style, redraw=True):
        for k, ws in self.style_btns.items():
            for w in ws: w.configure(bg=BTN_ON if k == style else BTN)
        self.view.style = style
        if redraw: self.view.redraw()

    # ───────────────────────── bảng thuộc tính ─────────────────────────
    def _sections(self):
        if self.kind == "knee":
            import knee_gui as G
        else:
            import splice_gui as G
        return G.build_sections(self)

    def _fill(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self.fields = []
        for title, opened, specs in self._sections():
            sec = tk.Frame(self.inner, bg=PANEL); sec.pack(fill="x", pady=(0, 6))
            hdr = tk.Frame(sec, bg=HEAD, cursor="hand2"); hdr.pack(fill="x")
            ht = tk.Label(hdr, text=title, bg=HEAD, fg=TXT, font=F_HEAD, anchor="w"); ht.pack(side="left", padx=8, pady=5)
            arrow = tk.Label(hdr, text="▴" if opened else "▾", bg=HEAD, fg=TXT, font=F_SUB); arrow.pack(side="right", padx=10)
            body = tk.Frame(sec, bg=PANEL)
            if opened: body.pack(fill="x")
            for w in (hdr, ht, arrow):
                w.bind("<Button-1>", lambda e, b=body, a=arrow: self._toggle(b, a))
            grp = body
            r = 0
            for sp in specs:
                k = sp["k"]
                if k == "sub":
                    holder = tk.Frame(body, bg=PANEL)
                    h = tk.Label(holder, text="⌃  " + sp["l"], bg=PANEL, fg=SUBC, font=F_SUB, anchor="w", cursor="hand2")
                    h.pack(fill="x", padx=12, pady=(6, 2))
                    grp = tk.Frame(holder, bg=LINE); grp.pack(fill="x", padx=(16, 4))
                    grp.grid_columnconfigure(1, weight=1)
                    h.bind("<Button-1>", lambda e, g=grp, hh=h: self._toggle_sub(g, hh))
                    f = dict(spec=sp, cell=holder, pack=True)
                    holder.pack(fill="x"); self.fields.append(f); r = 0
                    continue
                if k == "lock":
                    continue
                if grp is body:                      # dòng không có nhóm con
                    grp = tk.Frame(body, bg=LINE); grp.pack(fill="x", padx=(16, 4)); grp.grid_columnconfigure(1, weight=1)
                f = self._row(grp, r, sp)
                self.fields.append(f); r += 1
        self._load()

    def _toggle(self, body, arrow):
        if body.winfo_ismapped():
            body.pack_forget(); arrow.configure(text="▾")
        else:
            body.pack(fill="x"); arrow.configure(text="▴")

    def _toggle_sub(self, grp, h):
        txt = h.cget("text")[3:]
        if grp.winfo_ismapped():
            grp.pack_forget(); h.configure(text="⌄  " + txt)
        else:
            grp.pack(fill="x", padx=(16, 4)); h.configure(text="⌃  " + txt)

    def _row(self, grp, r, sp):
        k = sp["k"]
        f = dict(spec=sp, pack=False)
        if k in ("info", "note"):
            lab = tk.Label(grp, text=sp.get("l", ""), bg=PANEL, fg="#7FD69A" if k == "info" else SUBC, font=("Segoe UI", 8),
                           anchor="w", justify="left", wraplength=380)
            f["cell"] = lab; f["lbl"] = lab; f["grid"] = dict(row=r, column=0, columnspan=2, sticky="ew", pady=(0, 1))
            lab.grid(**f["grid"])
            return f
        lab_txt = sp["l"].split("   ")[0] if k == "btn" else sp["l"]
        cell = tk.Frame(grp, bg=PANEL)
        lab = tk.Label(cell, text=lab_txt, bg=PANEL, fg=TXT, font=F, anchor="w", justify="left", wraplength=180, width=26)
        lab.pack(side="left", fill="y", padx=(10, 2), pady=3)
        val = tk.Frame(cell, bg=ROW); val.pack(side="left", fill="both", expand=True)
        if sp.get("tip"):
            lab.bind("<Enter>", lambda e, t=sp["tip"]: self.lbl_msg.configure(text=t))
        if k == "btn":
            b = tk.Label(val, text="<Loads>", bg=ROW, fg=VAL, font=F, anchor="w", cursor="hand2")
            b.pack(fill="x", padx=6, pady=3); b.bind("<Button-1>", lambda e, c=sp["cmd"]: c())
            tk.Label(val, text="▾", bg=ROW, fg=SUBC, font=F).place(relx=1.0, rely=0.5, anchor="e", x=-4)
        elif k == "chk":
            var = tk.BooleanVar()
            w = tk.Checkbutton(val, variable=var, bg=ROW, activebackground=ROW, fg=TXT, selectcolor="#1B4F9C", bd=0,
                               highlightthickness=0, command=lambda f=f: self._changed(f, True))
            w.pack(side="right", padx=10, pady=2)
            f["var"] = var; f["w"] = w
        elif k == "sel":
            var = tk.StringVar()
            mb = tk.Menubutton(val, textvariable=var, bg=ROW, fg=VAL, activebackground="#1B3F7E", activeforeground=TXT,
                               font=F, anchor="w", relief="flat", bd=0, indicatoron=False, cursor="hand2")
            m = tk.Menu(mb, tearoff=0, bg="#FFFFFF", fg="#111827", font=F)
            for _key, l in sp["opts"]:
                m.add_command(label=l, command=lambda l=l, f=f: (f["var"].set(l), self._changed(f, True)))
            mb.configure(menu=m); mb.pack(fill="x", padx=4, pady=2)
            tk.Label(val, text="▾", bg=ROW, fg=SUBC, font=F).place(relx=1.0, rely=0.5, anchor="e", x=-4)
            f["var"] = var; f["w"] = mb
        else:
            var = tk.StringVar()
            e = tk.Entry(val, textvariable=var, bg=ROW, fg=VAL, insertbackground=TXT, relief="flat", font=F,
                         justify="left", highlightthickness=0, bd=0)
            e.pack(side="left", fill="x", expand=True, padx=6, pady=3)
            if k == "num":
                tk.Label(val, text=sp.get("u", ""), bg=ROW, fg=SUBC, font=F).pack(side="right", padx=6)
            var.trace_add("write", lambda *_a, f=f: self._changed(f, False))
            f["var"] = var; f["w"] = e
        f["cell"] = cell; f["grid"] = dict(row=r, column=0, columnspan=2, sticky="ew", pady=(0, 1))
        cell.grid(**f["grid"])
        for w in (cell, lab, val):
            w.bind("<MouseWheel>", self._wheel)
        return f

    def _load(self):
        self._normalize()
        self._suspend = True
        for f in self.fields:
            sp = f["spec"]; k = sp["k"]
            if k not in ("chk", "sel", "num", "txt"): continue
            v = _getp(self.S, sp["p"])
            if k == "chk": f["var"].set(bool(v))
            elif k == "sel": f["var"].set(next((l for key, l in sp["opts"] if str(key) == str(v)), sp["opts"][0][1]))
            else: f["var"].set("" if v is None else (f"{v:g}" if isinstance(v, float) else str(v)))
        self._suspend = False
        self._visibility(); self._info()

    def _normalize(self):
        (K.normalize if self.kind == "knee" else SE.normalize)(self.S)

    def _changed(self, f, structural):
        if self._suspend: return
        sp = f["spec"]; k = sp["k"]
        if k == "chk": v = bool(f["var"].get())
        elif k == "sel":
            lab = f["var"].get()
            v = next((key for key, l in sp["opts"] if l == lab), sp["opts"][0][0])
        elif k == "num":
            s = f["var"].get().replace(",", ".").strip()
            try: v = float(s)
            except ValueError: return
            if v.is_integer() and sp["p"] in ("plate.nE", "plate.nI", "plate.nT", "plate.nB", "bolt.d"): v = int(v)
        else: v = f["var"].get()
        _setp(self.S, sp["p"], v)
        if self.kind == "knee" and sp["p"] == "plate.alignment":
            K.normalize(self.S); _knee_type_defaults(self.S); self._load()
        elif self.kind != "knee":
            SE.normalize(self.S)
        if structural: self._visibility()
        if sp["p"].endswith(".sec"): self._info()
        self.schedule()

    def _visibility(self):
        for f in self.fields:
            show = f["spec"].get("show")
            vis = True
            if show:
                try: vis = bool(show())
                except Exception: vis = True  # noqa: BLE001
            if f.get("pack"):
                if vis and not f["cell"].winfo_ismapped(): f["cell"].pack(fill="x")
                elif not vis: f["cell"].pack_forget()
            elif vis: f["cell"].grid(**f["grid"])
            else: f["cell"].grid_remove()
        # giữ đúng thứ tự các nhóm con khi hiện lại
        for f in self.fields:
            if f.get("pack") and f["cell"].winfo_manager():
                f["cell"].pack_forget(); f["cell"].pack(fill="x")

    def _info(self):
        for f in self.fields:
            sp = f["spec"]
            if sp["k"] != "info" or sp["p"] == "pz._": continue
            m = _getp(self.S, sp["p"].rsplit(".", 1)[0])
            try:
                if self.kind == "knee":
                    mm = K.member_at_joint(m, "")
                    f["lbl"].configure(text=f"✓ d = {mm['d']:.1f}, bụng {mm['hw']:.1f}×{mm['tw']:g}, cánh {mm['bfE']:g}×{mm['tfE']:g}"
                                            + (f" · vát {mm['beta']:.1f}°" if mm["beta"] > 1e-6 else ""), fg="#7FD69A")
                else:
                    f["lbl"].configure(text="✓ " + str(m.get("sec", "")), fg="#7FD69A")
            except Exception as e:  # noqa: BLE001
                f["lbl"].configure(text="✗ " + str(e), fg="#FF8A8A")

    # ───────────────────────── tính + vẽ ─────────────────────────
    def schedule(self):
        if self._job: self.after_cancel(self._job)
        self._job = self.after(300, self.run)

    def run(self):
        self._job = None
        st = copy.deepcopy(self.S)
        try:
            self.R = PJ.KINDS[self.kind]["compute"](st); self.err = None; self.st = st
        except Exception as e:  # noqa: BLE001
            self.R = None; self.err = str(e)
        self._render()

    def _render(self):
        if self.err or not self.R:
            self.box.configure(text="!", bg=RED); self.lbl_msg.configure(text="Lỗi số liệu: " + (self.err or ""))
            self.view.show(None); return
        g = self.R.get("gov")
        r = g["ratio"] if g else 0.0
        ok = r <= 1.0001 and self.R.get("geoFail", 0) == 0
        self.box.configure(text="∞" if math.isinf(r) else f"{r:.2f}", bg=GOLD if ok else RED)
        self.lbl_msg.configure(text=(f"Critical ratio {r:.2f} — {g['name']} ({g['combo']})" if g else "")
                               + ("" if self.R.get("geoFail", 0) == 0 else f" · {self.R['geoFail']} lỗi cấu tạo"))
        try:
            self.view.show_model(model3d.build(self.kind, self.st, self.R))
        except Exception as e:  # noqa: BLE001
            self.view.show(None); self.lbl_msg.configure(text="Không dựng được hình 3D: " + str(e))

    # ───────────────────────── lệnh thanh công cụ ─────────────────────────
    def apply(self):
        self.app.apply_editor(self.jid, copy.deepcopy(self.S), source=self)
        self.lbl_msg.configure(text="Đã lưu vào dự án.")

    def ok(self):
        self.apply(); self.destroy()

    def reload(self, state):
        self.S = PJ.KINDS[self.kind]["merge"](PJ.KINDS[self.kind]["base"], state)
        self._load(); self.run()

    def _report(self):
        if not self.R:
            messagebox.showerror("Report", self.err or "Chưa có kết quả.", parent=self); return None
        RP = PJ.KINDS[self.kind]["report"]
        return RP, RP.build(self.st, self.R, os.path.basename(self.app.project.path or ""))

    def print_preview(self):
        res = self._report()
        if not res: return None
        RP, rep = res
        w = tk.Toplevel(self); w.title("Report — " + self.S.get("name", "")); w.geometry("1100x800")
        t = tk.Text(w, font=("Consolas", 10), wrap="none", padx=12, pady=10)
        ys = ttk.Scrollbar(w, orient="vertical", command=t.yview); t.configure(yscrollcommand=ys.set)
        ys.pack(side="right", fill="y"); t.pack(fill="both", expand=True)
        for tag, kw in (("h1", dict(font=("Segoe UI", 14, "bold"), foreground="#1E3A8A")), ("h2", dict(font=("Segoe UI", 11, "bold"))),
                        ("grp", dict(font=("Consolas", 10, "bold"))), ("sub", dict(font=("Consolas", 10, "bold"), foreground="#B45309")),
                        ("ok", dict(foreground="#15803D", font=("Consolas", 11, "bold"))), ("bad", dict(foreground=RED)),
                        ("dim", dict(foreground="#6B7280"))):
            t.tag_configure(tag, **kw)
        for s, tag in RP.to_text(rep):
            t.insert("end", s, tag)
        t.configure(state="disabled")
        return w

    def print_file(self):
        res = self._report()
        if not res: return
        RP, rep = res
        path = filedialog.asksaveasfilename(parent=self, title="Print to file", defaultextension=".docx", filetypes=[("Word", "*.docx")],
                                            initialfile=f"{self.jid}_{self.S.get('name', 'joint')}_report.docx".replace("/", "-").replace(":", "-"))
        if not path: return
        RP.to_docx(rep, path)
        self.lbl_msg.configure(text=f"Đã xuất báo cáo: {path}")

    def optimize(self):
        self.lbl_msg.configure(text="Đang thử các phương án tp / bu lông…"); self.update_idletasks()
        res = PJ.KINDS[self.kind]["auto"](copy.deepcopy(self.S))
        if not res:
            messagebox.showwarning("Optimize", "Không tính được phương án nào — kiểm tra lại số liệu.", parent=self); return
        if self.kind == "knee": self.S["plate"]["tp"] = res["tp"]
        else: self.S["plate"]["tp1"] = self.S["plate"]["tp2"] = res["tp"]
        self.S["bolt"]["d"] = res["d"]
        self._load(); self.run()
        msg = f"Optimize: tp = {res['tp']} mm, bu lông M{res['d']} — D/C = {res['ratio']:.2f}"
        if res.get("fail"): msg += " (không có phương án đạt trong dải thử)"
        self.lbl_msg.configure(text=msg)

    def results(self):
        if not self.R:
            messagebox.showerror("Results", self.err or "Chưa có kết quả.", parent=self); return None
        w = tk.Toplevel(self); w.title("Results — " + self.S.get("name", "")); w.geometry("1150x720")
        pan = ttk.PanedWindow(w, orient="vertical"); pan.pack(fill="both", expand=True)
        fr = ttk.Frame(pan); pan.add(fr, weight=3)
        cols = ("dc", "cap", "dem", "unit", "combo", "ref")
        tv = ttk.Treeview(fr, columns=cols)
        for c, h, wd, an in (("#0", "Check", 330, "w"), ("dc", "Ratio", 60, "center"), ("cap", "Capacity", 90, "e"), ("dem", "Demand", 90, "e"),
                             ("unit", "Unit", 50, "center"), ("combo", "Ctrl EQ", 130, "w"), ("ref", "Reference", 260, "w")):
            tv.heading(c, text=h); tv.column(c, width=wd, anchor=an, stretch=c in ("#0", "ref"))
        tv.tag_configure("grp", font=("Segoe UI", 9, "bold"), background="#E8EEF8")
        tv.tag_configure("bad", foreground=RED); tv.tag_configure("info", foreground="#8A94A3")
        sb = ttk.Scrollbar(fr, orient="vertical", command=tv.yview); tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        det = tk.Text(pan, height=10, font=("Consolas", 10), wrap="word", padx=8, pady=6); pan.add(det, weight=1)
        groups, byid = {}, {}
        for c in self.R["checks"]:
            gid = groups.get(c["grp"])
            if gid is None:
                gid = groups[c["grp"]] = tv.insert("", "end", text=c["grp"], open=True, tags=("grp",))
            r = c["ratio"]
            iid = tv.insert(gid, "end", text=c["name"], tags=("info",) if c["info"] else (("bad",) if r > 1.0001 else ()),
                            values=("—" if c["info"] else ("∞" if math.isinf(r) else f"{r:.2f}"), f"{c['cap']:.2f}", f"{c['dem']:.2f}",
                                    c["unit"], c["combo"], c["ref"]))
            byid[iid] = c

        def show(_e=None):
            c = byid.get((tv.selection() or [""])[0])
            det.configure(state="normal"); det.delete("1.0", "end")
            if c:
                det.insert("end", f"{c['name']}  —  {c['ref']}\nCapacity = {c['cap']:.2f} {c['unit']};  Demand = {c['dem']:.2f} {c['unit']};"
                                  f"  Ratio = {c['ratio']:.3f}  ({c['combo']})\n\n" + "\n".join(c["detail"]))
                self.view.show_model(self.view._model, set(c.get("tags", ())))
            det.configure(state="disabled")
        tv.bind("<<TreeviewSelect>>", show)
        return w

    def _edit_page(self, page):
        """Bảng Data / Loads (như bước 2–3 của New joint) — không chặn vòng lặp sự kiện."""
        if self.loads_win is not None and self.loads_win.winfo_exists():
            self.loads_win.lift(); return
        key = "knee" if self.kind == "knee" else f"splice:{self.S.get('type', 'straight')}"
        d = newjoint.NewJointDialog(self, key, self.S.get("name", ""), dict(copy.deepcopy(self.S), _key=key), start_page=page)
        d._edit_mode = True
        d._show(page)
        self.loads_win = d

        def done(e):
            if e.widget is not d: return
            self.loads_win = None
            if not d.result: return
            st = d.result["state"]
            self.S = PJ.KINDS[self.kind]["merge"](self.S, st)
            self.S["loads"] = st.get("loads", self.S["loads"])
            self.after(10, lambda: (self._load(), self.run()))
        d.bind("<Destroy>", done, add="+")

    def open_data(self):
        self._edit_page("data")

    def open_loads(self):
        self._edit_page("loads")

    def advanced(self):
        """Mở khung thiết kế đầy đủ (SAP2000, bảng D/C, mặt đứng 2D) với thông số hiện tại."""
        self.apply()
        self.app.advanced_editor(self.app.project.get(self.jid))

    def help(self):
        messagebox.showinfo("Connection Pad", "Bảng trái: thông số liên kết như RAM Connection (nhấp tiêu đề để thu gọn).\n"
                            "Loads <Loads>: bảng tổ hợp tải · Data: tiết diện / vật liệu / hình học.\n"
                            "Save: lưu vào dự án · Print: xem báo cáo · Print to file: xuất Word.\n"
                            "Optimize: tự chọn tp / bu lông · Results: bảng kiểm tra + diễn giải (chọn dòng để tô sáng bộ phận).\n"
                            "Solid / Lines / Transparent: kiểu vẽ 3D.\n"
                            "Hình 3D: kéo trái xoay · kéo phải di chuyển · lăn zoom · nhấp đúp về góc mặc định.", parent=self)


def _knee_type_defaults(S):
    """Điều kiện phía gối mặc định theo kiểu knee (giống KneePanel)."""
    sup, t = S["sup"], S["type"]
    if t == "ngang":
        sup["condE"] = sup["condI"] = "cont_stiff"
    else:
        if sup["condE"] == "endplate" or (sup["condE"] == "cont_stiff" and sup["condI"] == "cont_stiff"): sup["condE"] = "top_cap"
        if sup["condI"] == "endplate": sup["condI"] = "cont_stiff"


def _getp(d, p):
    for k in p.split("."):
        d = d.get(k) if isinstance(d, dict) else None
    return d


def _setp(d, p, v):
    ks = p.split(".")
    for k in ks[:-1]:
        d = d.setdefault(k, {})
    d[ks[-1]] = v
