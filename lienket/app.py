"""
app.py — LIÊN KẾT THÉP · AISC 360-10 LRFD — cửa sổ chính theo bố cục RAM Connection Standalone
=================================================================================================
  • Thanh tiêu đề đỏ đô + nút nhanh (New / Open / Save).
  • Ribbon File · Home · Design · Output:
      Home   — Joints (New, Edit, Delete, Delete all, Copy, Go to) · Load conditions (Add/Edit, Delete, Generate)
               · View (Template, Information log, Critical load condition) · Databases (Sections, Materials, Connections, Bolts, Welds, Anchors)
      Design — Connection (Edit connection, Smart connection, Design all) · Data (Joint data)
      Output — Reports (Report, All reports) · Export (RAM .rcnx, Results table) · Log
  • Khung xem nền xanh đậm: hình nút đang chọn, tô màu D/C theo tổ hợp (Condition) ở thanh trạng thái.
  • Khung dưới: bảng các nút của dự án (ID, tên, họ, kiểu, cấu kiện, liên kết, số tổ hợp, tỷ số, trạng thái).
  • Thanh trạng thái: số nút, SI, Condition, zoom.
Edit mở cửa sổ thiết kế liên kết (Connection Pad: KNEE, NỐI DẦM hoặc CHÂN CỘT); New mở hộp thoại New joint 3 bước (Joint → Data → Loads).
"""

from __future__ import annotations

import copy
import csv
import json
import math
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import engine as K  # noqa: E402
import newjoint  # noqa: E402
import project as PJ  # noqa: E402
from drawing import KneeCanvas, heat_color  # noqa: E402
from ramview import RamView  # noqa: E402
import model3d  # noqa: E402
from knee_section import SectionError, parse_section  # noqa: E402

APP = "Liên kết thép — AISC 360-10 LRFD"
SETTINGS = os.path.join(HERE, "settings.json")
MAROON, MAROON_D = "#8B3540", "#6E2A33"
RIB_BG, RIB_LINE = "#F5F5F5", "#D4D4D4"
NAVY, SLATE = "#001A4D", "#2B3A55"
CARD, CARD_SEL = "#4A4F57", "#0B2A6B"
DESIGN_CODES = {"AISC-10 LRFD": "AISC 2010 LRFD", "AISC-16 LRFD": "AISC 2016 LRFD"}
OK_C, BAD_C = "#1A9E5A", "#D23B3B"


# ─────────────────────────── biểu tượng ribbon (vẽ bằng canvas) ───────────────────────────
def draw_icon(cv: tk.Canvas, name: str, s: int):
    k = s / 32.0
    P = lambda *xy: [v * k for v in xy]
    ln = "#3B4656"
    def page(x=6, y=3, w=18, h=24, fill="#FFFFFF"):
        cv.create_polygon(*P(x, y, x + w - 5, y, x + w, y + 5, x + w, y + h, x, y + h), fill=fill, outline=ln)
    if name == "new":
        cv.create_rectangle(*P(4, 4, 9, 28), fill="#D9D9D9", outline=ln); cv.create_rectangle(*P(11, 10, 28, 18), fill="#D9D9D9", outline=ln)
        cv.create_line(*P(24, 1, 24, 9), fill="#22A04B", width=3 * k); cv.create_line(*P(20, 5, 28, 5), fill="#22A04B", width=3 * k)
    elif name == "edit":
        page(); cv.create_line(*P(10, 24, 26, 8), fill="#2563EB", width=3 * k)
    elif name in ("delete", "ldelete"):
        if name == "delete": page()
        cv.create_rectangle(*P(8, 14, 26, 19), fill="#D23B3B", outline="#8B1E1E")
    elif name == "delall":
        cv.create_line(*P(6, 6, 26, 26), fill="#D23B3B", width=4 * k); cv.create_line(*P(26, 6, 6, 26), fill="#D23B3B", width=4 * k)
    elif name == "copy":
        page(4, 2, 16, 21, "#DCE8F7"); page(12, 9, 16, 21, "#FFFFFF")
    elif name == "goto":
        cv.create_text(*P(14, 16), text="1²", font=("Segoe UI", int(9 * k)), fill=ln)
    elif name == "addedit":
        cv.create_rectangle(*P(14, 10, 30, 30), fill="#1E3A8A", outline=ln)
        cv.create_text(*P(22, 20), text="E", fill="#FFFFFF", font=("Segoe UI", int(10 * k), "bold"))
        cv.create_line(*P(9, 2, 9, 16), fill="#22A04B", width=5 * k); cv.create_line(*P(2, 9, 16, 9), fill="#22A04B", width=5 * k)
    elif name == "generate":
        cv.create_oval(*P(6, 6, 26, 26), outline="#7C2D12", width=2 * k); cv.create_oval(*P(12, 12, 20, 20), fill="#D23B3B", outline="")
    elif name == "template":
        cv.create_rectangle(*P(4, 6, 24, 28), fill="#FFFFFF", outline=ln)
        for y in (11, 16, 21): cv.create_line(*P(7, y, 21, y), fill="#9AA5B1")
        cv.create_line(*P(14, 22, 29, 3), fill="#E8A33D", width=4 * k)
    elif name == "log":
        page(fill="#F0F0F0"); cv.create_text(*P(15, 16), text="i", font=("Segoe UI", int(11 * k), "bold"), fill="#9AA5B1")
    elif name == "critical":
        cv.create_rectangle(*P(5, 3, 11, 29), fill="#D9D9D9", outline=ln); cv.create_rectangle(*P(13, 14, 28, 22), fill="#D9D9D9", outline=ln)
        cv.create_oval(*P(17, 23, 22, 28), fill="#D23B3B", outline=""); cv.create_oval(*P(23, 23, 28, 28), fill="#22A04B", outline="")
    elif name == "sections":
        cv.create_rectangle(*P(6, 4, 22, 8), fill="#2E86C1", outline=ln); cv.create_rectangle(*P(12, 8, 16, 22), fill="#2E86C1", outline=ln)
        cv.create_rectangle(*P(6, 22, 22, 26), fill="#2E86C1", outline=ln); cv.create_oval(*P(18, 18, 30, 30), fill="#CBD5E1", outline=ln)
    elif name == "materials":
        for i, c in enumerate(("#C0A16B", "#8D99AE", "#5D6D7E")):
            cv.create_rectangle(*P(5 + i * 3, 6 + i * 7, 22 + i * 3, 12 + i * 7), fill=c, outline=ln)
    elif name == "connections":
        cv.create_polygon(*P(6, 8, 18, 4, 18, 26, 6, 30), fill="#1E40AF", outline=ln)
        cv.create_polygon(*P(14, 10, 26, 6, 26, 24, 14, 28), fill="#2563EB", outline=ln)
    elif name == "bolts":
        cv.create_polygon(*P(10, 4, 22, 4, 28, 12, 22, 20, 10, 20, 4, 12), fill="#9CA3AF", outline=ln)
        cv.create_rectangle(*P(13, 20, 19, 30), fill="#9CA3AF", outline=ln)
    elif name == "welds":
        cv.create_rectangle(*P(4, 4, 20, 20), fill="#E5B80B", outline=ln); cv.create_polygon(*P(20, 20, 30, 20, 20, 30), fill="#D23B3B", outline=ln)
    elif name == "anchors":
        cv.create_line(*P(12, 4, 12, 26, 22, 26), fill=ln, width=3 * k); cv.create_oval(*P(18, 10, 30, 22), fill="#CBD5E1", outline=ln)
    elif name == "design":
        cv.create_rectangle(*P(6, 3, 26, 29), fill="#E5E7EB", outline=ln); cv.create_rectangle(*P(9, 6, 23, 12), fill="#86EFAC", outline=ln)
        for x in (9, 15, 21):
            for y in (15, 21): cv.create_rectangle(*P(x, y, x + 3, y + 3), fill=ln, outline="")
    elif name == "smart":
        cv.create_polygon(*P(18, 2, 6, 18, 15, 18, 12, 30, 26, 12, 17, 12), fill="#F59E0B", outline="#92400E")
    elif name == "data":
        cv.create_rectangle(*P(4, 4, 28, 28), fill="#FFFFFF", outline=ln)
        for y in (10, 16, 22): cv.create_line(*P(7, y, 25, y), fill=ln); cv.create_line(*P(15, 6, 15, 26), fill=ln)
    elif name == "report":
        page(); cv.create_text(*P(15, 18), text="W", fill="#2563EB", font=("Segoe UI", int(10 * k), "bold"))
    elif name == "reports":
        page(3, 2, 16, 21, "#DCE8F7"); page(11, 8, 16, 21); cv.create_text(*P(19, 19), text="W", fill="#2563EB", font=("Segoe UI", int(8 * k), "bold"))
    elif name == "rcnx":
        page(fill="#EDE9FE"); cv.create_text(*P(15, 18), text="R", fill="#6D28D9", font=("Segoe UI", int(10 * k), "bold"))
    elif name == "csv":
        cv.create_rectangle(*P(4, 4, 28, 28), fill="#ECFDF5", outline="#15803D")
        for y in (11, 18): cv.create_line(*P(4, y, 28, y), fill="#15803D")
        cv.create_line(*P(14, 4, 14, 28), fill="#15803D")
    elif name == "file":
        page()


class Ribbon(tk.Frame):
    """Ribbon tối giản: hàng tab (File là menu thả xuống) + thân gồm các nhóm nút có chú thích ở đáy."""

    def __init__(self, master, build_file_menu):
        super().__init__(master, bg=RIB_BG)
        self.tabs_row = tk.Frame(self, bg=RIB_BG); self.tabs_row.pack(fill="x")
        self.body_host = tk.Frame(self, bg=RIB_BG, height=104); self.body_host.pack(fill="x"); self.body_host.pack_propagate(False)
        tk.Frame(self, bg=RIB_LINE, height=1).pack(fill="x")
        fb = tk.Menubutton(self.tabs_row, text="File", bg=RIB_BG, relief="flat", font=("Segoe UI", 9), padx=12, pady=4, activebackground="#E5E5E5")
        fb["menu"] = build_file_menu(fb)
        fb.pack(side="left", padx=(6, 2))
        self.tab_lbl, self.bodies, self.current = {}, {}, None

    def add_tab(self, name: str) -> tk.Frame:
        lb = tk.Label(self.tabs_row, text=name, bg=RIB_BG, font=("Segoe UI", 9), padx=12, pady=4, cursor="hand2")
        lb.pack(side="left"); lb.bind("<Button-1>", lambda e: self.select(name))
        self.tab_lbl[name] = lb
        body = tk.Frame(self.body_host, bg=RIB_BG); self.bodies[name] = body
        if self.current is None: self.select(name)
        return body

    def select(self, name):
        for n, lb in self.tab_lbl.items():
            lb.configure(font=("Segoe UI", 9, "underline") if n == name else ("Segoe UI", 9), fg=MAROON if n == name else "#1B2430")
        for b in self.bodies.values(): b.pack_forget()
        self.bodies[name].pack(fill="both", expand=True); self.current = name

    @staticmethod
    def group(body, caption) -> tk.Frame:
        g = tk.Frame(body, bg=RIB_BG); g.pack(side="left", fill="y", padx=(4, 0))
        inner = tk.Frame(g, bg=RIB_BG); inner.pack(side="top", fill="both", expand=True, padx=4, pady=(4, 0))
        tk.Label(g, text=caption, bg=RIB_BG, fg="#3B4656", font=("Segoe UI", 8)).pack(side="bottom", pady=(0, 2))
        tk.Frame(body, bg=RIB_LINE, width=1).pack(side="left", fill="y", pady=6, padx=(4, 0))
        return inner

    @staticmethod
    def big(parent, text, icon, cmd, tip="", state="normal"):
        f = tk.Frame(parent, bg=RIB_BG, cursor="hand2"); f.pack(side="left", padx=3, fill="y")
        cv = tk.Canvas(f, width=34, height=34, bg=RIB_BG, highlightthickness=0); cv.pack(pady=(2, 0))
        draw_icon(cv, icon, 34)
        lb = tk.Label(f, text=text, bg=RIB_BG, fg="#1B2430" if state == "normal" else "#A0A6AE", font=("Segoe UI", 8), justify="center", wraplength=78)
        lb.pack()
        Ribbon._bind(f, (cv, lb), cmd if state == "normal" else None, tip)
        return f

    @staticmethod
    def small(parent, text, icon, cmd, tip="", state="normal"):
        f = tk.Frame(parent, bg=RIB_BG, cursor="hand2"); f.pack(side="top", anchor="w", pady=1)
        cv = tk.Canvas(f, width=16, height=16, bg=RIB_BG, highlightthickness=0); cv.pack(side="left")
        draw_icon(cv, icon, 16)
        lb = tk.Label(f, text=text, bg=RIB_BG, fg="#1B2430" if state == "normal" else "#A0A6AE", font=("Segoe UI", 8)); lb.pack(side="left", padx=2)
        Ribbon._bind(f, (cv, lb), cmd if state == "normal" else None, tip)
        return f

    @staticmethod
    def _bind(frame, kids, cmd, tip):
        ws = (frame,) + tuple(kids)
        def enter(_e):
            for w in ws: w.configure(bg="#E4E8EE")
        def leave(_e):
            for w in ws: w.configure(bg=RIB_BG)
        for w in ws:
            w.bind("<Enter>", enter); w.bind("<Leave>", leave)
            if cmd: w.bind("<Button-1>", lambda e: cmd())
        frame.tip = tip


class NavyView(KneeCanvas):
    """Khung xem nền xanh đậm như RAM: dùng hình của tool, đổi chữ tối thành chữ sáng."""

    DARK = {"#18212F", "#5B6777", "#2F5F8F", "#3B4656", "#9AA5B1"}

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.configure(background=NAVY)
        self.empty_text = ""

    def redraw(self):
        super().redraw()
        for i in self.find_all():
            if self.type(i) == "text" and self.itemcget(i, "fill").upper() in self.DARK:
                self.itemconfigure(i, fill="#E6EDF7")
            elif self.type(i) == "line" and self.itemcget(i, "fill").upper() in ("#5B6777",):
                self.itemconfigure(i, fill="#9FB3D1")
        if not self._scene and self.empty_text:
            W, H = max(self.winfo_width(), 50), max(self.winfo_height(), 50)
            self.create_text(W / 2, H / 2, text=self.empty_text, fill="#8FA6C8", font=("Segoe UI", 12), justify="center")


def table_dialog(master, title, heads, rows, note=""):
    w = tk.Toplevel(master); w.title(title); w.geometry("820x460"); w.transient(master)
    if note:
        tk.Label(w, text=note, anchor="w", justify="left", fg="#3B4656", font=("Segoe UI", 9), wraplength=780).pack(fill="x", padx=10, pady=(8, 4))
    fr = ttk.Frame(w); fr.pack(fill="both", expand=True, padx=8, pady=4)
    tv = ttk.Treeview(fr, columns=[str(i) for i in range(len(heads))], show="headings")
    for i, h in enumerate(heads):
        tv.heading(str(i), text=h); tv.column(str(i), width=max(80, 760 // len(heads)), anchor="w" if i == 0 else "e")
    for r in rows: tv.insert("", "end", values=r)
    sb = ttk.Scrollbar(fr, orient="vertical", command=tv.yview); tv.configure(yscrollcommand=sb.set)
    tv.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
    ttk.Button(w, text="Close", command=w.destroy).pack(pady=6)
    return w


# ═══════════════════════════ CỬA SỔ CHÍNH ═══════════════════════════
class App(ctk.CTk):
    def __init__(self, project_path: str | None = None):
        super().__init__()
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self.geometry("1600x960")
        self.minsize(1100, 700)
        self.configure(fg_color="#FFFFFF")
        self.project = self._open_initial(project_path)
        self.sel: int | None = None
        self.critical = False
        self.editors: dict[int, ctk.CTkToplevel] = {}
        self._cache: dict = {}
        self._build()
        self.refresh()
        if self.project.joints:
            self.select(self.project.joints[0]["id"])
        self.protocol("WM_DELETE_WINDOW", self._exit)

    # ───────────────────────── dự án ─────────────────────────
    def _open_initial(self, path):
        if not path:
            try:
                with open(SETTINGS, encoding="utf-8") as f:
                    path = json.load(f).get("last")
            except (OSError, ValueError):
                path = None
        if path and os.path.exists(path):
            try:
                return PJ.Project.load(path)
            except Exception:  # noqa: BLE001
                pass
        if os.path.exists(PJ.DEFAULT_PATH):
            return PJ.Project.load(PJ.DEFAULT_PATH)
        p = PJ.Project(PJ.DEFAULT_PATH)
        if p.import_legacy():
            p.save()
        return p

    def _remember(self):
        try:
            with open(SETTINGS, "w", encoding="utf-8") as f:
                json.dump({"last": self.project.path}, f)
        except OSError:
            pass

    def _title(self):
        name = os.path.basename(self.project.path) if self.project.path else "(chưa lưu)"
        t = f"{APP} — {name}{' *' if self.project.dirty else ''}"
        self.title(t); self.lbl_title.configure(text=t)

    def new_project(self):
        if not self._confirm_discard(): return
        self.project = PJ.Project(None); self.sel = None; self.refresh(); self.select(None)

    def open_project(self):
        if not self._confirm_discard(): return
        path = filedialog.askopenfilename(title="Open", filetypes=[("Liên kết thép", "*.lkt"), ("JSON", "*.json")])
        if not path: return
        try:
            self.project = PJ.Project.load(path)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Open", str(e)); return
        self._remember(); self.sel = None; self.refresh()
        self.select(self.project.joints[0]["id"] if self.project.joints else None)

    def save_project(self, ask=False):
        path = self.project.path
        if ask or not path:
            path = filedialog.asksaveasfilename(title="Save as", defaultextension=".lkt", filetypes=[("Liên kết thép", "*.lkt")],
                                                initialfile="du_an.lkt")
            if not path: return False
        self.project.save(path); self._remember(); self._title()
        self.set_status(f"Đã lưu dự án: {path}")
        return True

    def _confirm_discard(self):
        if not self.project.dirty: return True
        r = messagebox.askyesnocancel("Dự án", "Lưu thay đổi của dự án hiện tại?")
        if r is None: return False
        return self.save_project() if r else True

    def _exit(self):
        if self._confirm_discard():
            self.destroy()

    # ───────────────────────── bố cục ─────────────────────────
    def _build(self):
        bar = tk.Frame(self, bg=MAROON, height=30); bar.pack(fill="x"); bar.pack_propagate(False)
        for icon, cmd in (("file", self.new_project), ("rcnx", self.open_project), ("report", lambda: self.save_project())):
            cv = tk.Canvas(bar, width=20, height=20, bg=MAROON, highlightthickness=0, cursor="hand2"); cv.pack(side="left", padx=(6, 0), pady=5)
            draw_icon(cv, icon, 20); cv.bind("<Button-1>", lambda e, c=cmd: c())
        self.lbl_title = tk.Label(bar, text="", bg=MAROON, fg="#FFFFFF", font=("Segoe UI", 9))
        self.lbl_title.place(relx=0.5, rely=0.5, anchor="center")

        def file_menu(parent):
            fm = tk.Menu(parent, tearoff=0)
            fm.add_command(label="New project", command=self.new_project)
            fm.add_command(label="Open…", accelerator="Ctrl+O", command=self.open_project)
            fm.add_command(label="Save", accelerator="Ctrl+S", command=lambda: self.save_project())
            fm.add_command(label="Save as…", command=lambda: self.save_project(ask=True))
            fm.add_separator()
            fm.add_command(label="Import saved lists of old tools", command=self._import_legacy)
            fm.add_separator()
            fm.add_command(label="Exit", command=self._exit)
            return fm
        rb = self.ribbon = Ribbon(self, file_menu); rb.pack(fill="x")

        home = rb.add_tab("Home")
        g = Ribbon.group(home, "Joints")
        Ribbon.big(g, "New", "new", self.new_joint, "Tạo nút mới (Ctrl+N)")
        col = tk.Frame(g, bg=RIB_BG); col.pack(side="left", padx=2)
        Ribbon.small(col, "Edit", "edit", self.edit_joint); Ribbon.small(col, "Delete", "delete", self.delete_joint)
        Ribbon.small(col, "Delete all", "delall", self.delete_all)
        Ribbon.big(g, "Copy", "copy", self.copy_joint)
        gt = tk.Frame(g, bg=RIB_BG); gt.pack(side="left", padx=4, pady=18)
        Ribbon.small(gt, "Go to", "goto", lambda: self._goto())
        self.ent_goto = tk.Entry(gt, width=5, font=("Segoe UI", 9)); self.ent_goto.pack(side="top", pady=2)
        self.ent_goto.bind("<Return>", lambda e: self._goto())
        g = Ribbon.group(home, "Load conditions")
        Ribbon.big(g, "Add/Edit", "addedit", lambda: self.edit_data("loads"))
        col = tk.Frame(g, bg=RIB_BG); col.pack(side="left", padx=2, pady=10)
        Ribbon.small(col, "Delete", "ldelete", self.delete_loads); Ribbon.small(col, "Generate", "generate", self.generate_loads)
        g = Ribbon.group(home, "View")
        Ribbon.big(g, "Template", "template", self.template)
        Ribbon.big(g, "Information\nlog", "log", self.info_log)
        self.btn_crit = Ribbon.big(g, "Critical load\ncondition", "critical", self.toggle_critical)
        g = Ribbon.group(home, "Databases")
        Ribbon.big(g, "Sections", "sections", self.db_sections); Ribbon.big(g, "Materials", "materials", self.db_materials)
        Ribbon.big(g, "Connections", "connections", self.db_connections); Ribbon.big(g, "Bolts", "bolts", self.db_bolts)
        Ribbon.big(g, "Welds", "welds", self.db_welds); Ribbon.big(g, "Anchors", "anchors", self.db_anchors)
        g = Ribbon.group(home, "RAM Connection")
        Ribbon.big(g, "Export\nRAM .rcnx", "rcnx", self.export_rcnx, "Tạo file RAM Connection (.rcnx) từ các liên kết trong dự án")

        des = rb.add_tab("Design")
        g = Ribbon.group(des, "Connection")
        Ribbon.big(g, "Edit\nconnection", "edit", self.edit_joint)
        Ribbon.big(g, "Smart\nconnection", "smart", self.smart_connection)
        Ribbon.big(g, "Design all", "design", self.design_all)
        g = Ribbon.group(des, "Data")
        Ribbon.big(g, "Joint data", "data", lambda: self.edit_data("data"))
        Ribbon.big(g, "Loads", "addedit", lambda: self.edit_data("loads"))

        out = rb.add_tab("Output")
        g = Ribbon.group(out, "Reports")
        Ribbon.big(g, "Report", "report", self.report_one); Ribbon.big(g, "All reports", "reports", self.report_all)
        g = Ribbon.group(out, "Export")
        Ribbon.big(g, "RAM\n.rcnx", "rcnx", self.export_rcnx); Ribbon.big(g, "Results\ntable", "csv", self.export_csv)
        g = Ribbon.group(out, "Log")
        Ribbon.big(g, "Information\nlog", "log", self.info_log)

        # thanh trạng thái
        sb = tk.Frame(self, bg="#F0F0F0", height=26); sb.pack(side="bottom", fill="x"); sb.pack_propagate(False)
        self.lbl_count = tk.Label(sb, text="", bg="#F0F0F0", font=("Segoe UI", 9)); self.lbl_count.pack(side="left", padx=8)
        tk.Frame(sb, bg=RIB_LINE, width=1).pack(side="left", fill="y", pady=3)
        self.lbl_status = tk.Label(sb, text="", bg="#F0F0F0", fg="#3B4656", font=("Segoe UI", 9), anchor="w")
        self.lbl_status.pack(side="left", padx=8, fill="x", expand=True)
        for t, cmd in (("⤢", lambda: self.view.reset_view()), ("−", lambda: self._zoom(1 / 1.25)), ("+", lambda: self._zoom(1.25))):
            tk.Button(sb, text=t, width=2, relief="flat", bg="#F0F0F0", font=("Segoe UI", 9), command=cmd).pack(side="right", padx=1)
        self.cmb_cond = ttk.Combobox(sb, state="readonly", width=26, font=("Segoe UI", 9))
        self.cmb_cond.pack(side="right", padx=6); self.cmb_cond.bind("<<ComboboxSelected>>", lambda e: self._draw())
        tk.Label(sb, text="Condition:", bg="#F0F0F0", font=("Segoe UI", 9)).pack(side="right")
        self.cmb_view = ttk.Combobox(sb, state="readonly", width=12, values=["3D", "3D D/C", "Elevation", "End plate"], font=("Segoe UI", 9))
        self.cmb_view.set("3D"); self.cmb_view.pack(side="right", padx=6); self.cmb_view.bind("<<ComboboxSelected>>", lambda e: self._draw())
        tk.Label(sb, text="SI", bg="#F0F0F0", font=("Segoe UI", 9)).pack(side="right", padx=8)

        # ── khung xem (giữa) + bảng thông tin nút (phải) ──
        vf = tk.Frame(self, bg=NAVY); vf.pack(fill="both", expand=True, padx=3, pady=(3, 0))
        self._build_info(vf)
        self.vhost = tk.Frame(vf, bg=NAVY); self.vhost.pack(side="left", fill="both", expand=True)
        self.view3 = RamView(self.vhost)
        self.view2 = NavyView(self.vhost)
        for v in (self.view3, self.view2):
            v.empty_text = "Chưa có nút nào.\nHome → New (Ctrl+N) để tạo nút: Knee, Beam splice, Apex, Column base."
            v.tipfn = self._tip
        self.view = self.view3; self.view3.pack(fill="both", expand=True)
        # ── dải thẻ các nút (dưới) ──
        tk.Frame(self, bg="#FFFFFF", height=4).pack(fill="x")
        sf = tk.Frame(self, bg=SLATE, height=196); sf.pack(fill="x"); sf.pack_propagate(False)
        self.strip = tk.Canvas(sf, bg=SLATE, highlightthickness=0, height=180)
        xs = ttk.Scrollbar(sf, orient="horizontal", command=self.strip.xview)
        self.strip.configure(xscrollcommand=xs.set)
        xs.pack(side="bottom", fill="x"); self.strip.pack(fill="both", expand=True)
        self.strip_in = tk.Frame(self.strip, bg=SLATE)
        self.strip.create_window(0, 0, window=self.strip_in, anchor="nw")
        self.strip_in.bind("<Configure>", lambda e: self.strip.configure(scrollregion=self.strip.bbox("all")))
        self.strip.bind("<MouseWheel>", lambda e: self.strip.xview_scroll(-1 if e.delta > 0 else 1, "units"))
        self.cards: dict[int, dict] = {}
        self.bind("<Delete>", lambda e: self.delete_joint() if self.focus_get() in (None, self, self.strip) else None)
        self.bind("<Control-n>", lambda e: self.new_joint())
        self.bind("<Control-s>", lambda e: self.save_project())
        self.bind("<Control-o>", lambda e: self.open_project())

    def set_status(self, s):
        self.lbl_status.configure(text=s)

    def _zoom(self, f):
        self.view.zoom = min(max(self.view.zoom * f, 0.3), 12); self.view.redraw()

    # ───────────────────────── tính + bảng ─────────────────────────
    def result(self, j):
        key = (j["id"], json.dumps(j["state"], sort_keys=True, default=str))
        if key not in self._cache:
            try:
                st, R = PJ.evaluate(j); self._cache[key] = (st, R, None)
            except Exception as e:  # noqa: BLE001
                self._cache[key] = (None, None, str(e))
        return self._cache[key]

    def refresh(self):
        for w in self.strip_in.winfo_children():
            w.destroy()
        self.cards = {}
        for j in self.project.joints:
            self.cards[j["id"]] = self._card(j)
        self.lbl_count.configure(text=f"Elements: {len(self.project.joints)}")
        self._title()
        if self.sel is not None and self.project.get(self.sel) is None:
            self.sel = None
        self._mark_cards(); self._show_info(); self._draw()

    def _card(self, j):
        """Thẻ thu nhỏ như RAM: số nút (trái), mã họ (phải), hình, tỷ số – tổ hợp khống chế (xanh / đỏ)."""
        st, R, err = self.result(j)
        fr = tk.Frame(self.strip_in, bg=CARD, width=186, height=172, highlightthickness=2, highlightbackground=CARD)
        fr.pack(side="left", padx=4, pady=6); fr.pack_propagate(False)
        head = tk.Frame(fr, bg=CARD); head.pack(fill="x")
        l1 = tk.Label(head, text=str(j["id"]), bg=CARD, fg="#FFFFFF", font=("Segoe UI", 14, "bold")); l1.pack(side="left", padx=6)
        lab = self._card_title(j)
        l2 = tk.Label(head, text=lab, bg=CARD, fg="#FFFFFF", font=("Segoe UI", 11 if len(lab) <= 8 else 9)); l2.pack(side="right", padx=6)
        th = RamView(fr, thumb=True, width=178, height=110)
        th.configure(background=CARD); th.pack(padx=2)
        if not err:
            try:
                th.show_model(model3d.build(j["kind"], st, R))
            except Exception:  # noqa: BLE001
                pass
        if err:
            txt, col = "lỗi số liệu", "#FBBF24"
        else:
            g = R["gov"]; r = g["ratio"] if g else 0.0
            ok = r <= 1.0001 and R["geoFail"] == 0
            txt = (f"{'∞' if math.isinf(r) else format(r, '.2f')} - {g['combo']}" if g else "—")
            col = "#4ADE80" if ok else "#FF4D4D"
        l3 = tk.Label(fr, text=txt, bg=CARD, fg=col, font=("Segoe UI", 9), anchor="w"); l3.pack(fill="x", padx=6)
        for w in (fr, head, l1, l2, th, l3):
            w.bind("<Button-1>", lambda e, i=j["id"]: self.select(i))
            w.bind("<Double-Button-1>", lambda e, i=j["id"]: (self.select(i), self.edit_joint()))
            w.bind("<MouseWheel>", lambda e: self.strip.xview_scroll(-1 if e.delta > 0 else 1, "units"))
        return dict(frame=fr, parts=(head, l1, l2, l3), thumb=th)

    @staticmethod
    def _card_title(j) -> str:
        """Tiêu đề thẻ: 'Column Base: B1' khi nút có tên, không thì mã họ (CB, BCF, BS)."""
        fam = PJ.KINDS[j["kind"]]["family"]
        lab = str(j["state"].get("label") or "").strip()
        return f"{newjoint.FAMILY.get(fam, fam)}: {lab}" if lab else fam

    def _mark_cards(self):
        for jid, c in self.cards.items():
            on = jid == self.sel
            bg = CARD_SEL if on else CARD
            c["frame"].configure(bg=bg, highlightbackground="#3B82F6" if on else CARD)
            for w in c["parts"]: w.configure(bg=bg)
            c["thumb"].configure(background=NAVY if on else CARD)
        if self.sel in self.cards:
            self.update_idletasks()
            x = self.cards[self.sel]["frame"].winfo_x(); W = max(self.strip_in.winfo_width(), 1)
            vis0, vis1 = self.strip.xview()
            if not (vis0 * W <= x <= vis1 * W - 186):
                self.strip.xview_moveto(max(x - 20, 0) / W)

    def select(self, jid):
        self.sel = jid
        self._mark_cards(); self._fill_conditions(); self._show_info(); self._draw()

    # ── bảng thông tin nút (bên phải, như RAM) ──
    def _build_info(self, parent):
        box = tk.Frame(parent, bg=NAVY, width=360); box.pack(side="right", fill="y"); box.pack_propagate(False)
        self.info = tk.Text(box, bg=NAVY, fg="#FFFFFF", relief="flat", highlightthickness=0, font=("Segoe UI", 10), wrap="word",
                            padx=12, pady=10, cursor="arrow", height=20)
        self.info.pack(fill="x")
        t = self.info
        t.tag_configure("jid", font=("Segoe UI", 10, "bold"))
        t.tag_configure("fam", font=("Segoe UI", 13, "bold"), justify="center", spacing1=10)
        t.tag_configure("famn", justify="center", spacing3=12)
        t.tag_configure("h", font=("Segoe UI", 10, "bold"), spacing1=10)
        t.tag_configure("r", lmargin1=10, lmargin2=10)
        t.tag_configure("ok", lmargin1=10, foreground="#4ADE80"); t.tag_configure("bad", lmargin1=10, foreground="#FF4D4D")
        row = tk.Frame(box, bg=NAVY); row.pack(fill="x", padx=22)
        tk.Label(row, text="Design code :", bg=NAVY, fg="#FFFFFF", font=("Segoe UI", 10)).pack(side="left")
        self.cmb_code = ttk.Combobox(row, state="readonly", width=17, values=list(DESIGN_CODES), font=("Segoe UI", 9))
        self.cmb_code.pack(side="left", padx=6); self.cmb_code.bind("<<ComboboxSelected>>", lambda e: self._code_changed())
        tk.Button(box, text="Edit...", width=10, bg="#C7CBD1", relief="flat", font=("Segoe UI", 8), command=self.edit_joint).pack(anchor="e", padx=10, pady=6)
        tk.Label(box, text="Joint name", bg=NAVY, fg="#FFFFFF", font=("Segoe UI", 7, "bold"), anchor="w").pack(fill="x", padx=6, pady=(22, 0))
        self.ent_label = tk.Entry(box, bg="#FFFFFF", fg="#1E3A8A", relief="flat", font=("Segoe UI", 10))
        self.ent_label.pack(fill="x", padx=6, ipady=3)
        self.ent_label.bind("<FocusOut>", lambda e: self._label_changed())
        self.ent_label.bind("<Return>", lambda e: self._label_changed())
        tk.Label(box, text="Additional notes", bg=NAVY, fg="#FFFFFF", font=("Segoe UI", 7, "bold"), anchor="w").pack(fill="x", padx=6, pady=(8, 0))
        self.notes = tk.Text(box, height=5, bg="#FFFFFF", fg="#1E3A8A", relief="flat", font=("Segoe UI", 9), wrap="word", padx=8, pady=6)
        self.notes.pack(fill="x", padx=6, pady=(0, 6))
        self.notes.bind("<FocusOut>", lambda e: self._notes_changed())

    def _show_info(self):
        t = self.info
        t.configure(state="normal"); t.delete("1.0", "end")
        j = self._joint(False)
        self.notes.delete("1.0", "end")
        self.ent_label.delete(0, "end")
        if not j:
            t.insert("end", "Chưa chọn nút.", "r"); t.configure(state="disabled"); self.cmb_code.set(""); return
        st = PJ.full_state(j)
        fam = PJ.KINDS[j["kind"]]["family"]
        t.insert("end", f"JOINT {j['id']}" + (f"  ·  {st.get('name')}" if st.get("name") else "") + "\n", "jid")
        t.insert("end", fam + "\n", "fam"); t.insert("end", newjoint.FAMILY.get(fam, "") + "\n", "famn")
        if j["kind"] == "knee":
            t.insert("end", "BEAM\n", "h")
            t.insert("end", f"Section : {st['beam']['sec']}\nMaterial : {st['beam']['mat']}\nSlope angle : {float(st['beam']['slope']):.2f}\n", "r")
            t.insert("end", "COLUMN\n", "h")
            t.insert("end", f"Section : {st['col']['sec']}\nMaterial : {st['col']['mat']}\n", "r")
            align = {"vertical": "Vertical", "horizontal": "Horizontal", "perpendicular": "Perpendicular", "bisector": "Bisector"}.get(st["plate"].get("alignment"), "")
            tpl, con = f"MEP Knee BCF - {align}", "Shear and moment connection (Knee moment end plate)"
        elif j["kind"] == "base":
            t.insert("end", "COLUMN\n", "h")
            t.insert("end", f"Section : {st['col']['sec']}\nMaterial : {st['col']['mat']}\n", "r")
            ped = st["ped"]
            t.insert("end", "CONCRETE SUPPORT\n", "h")
            t.insert("end", f"Pedestal : {ped['N2']:g} × {ped['B2']:g} × {ped['h']:g}\nf'c : {float(ped['fc']):g} MPa · vữa {ped['grout']:g} mm\n", "r")
            import base_engine as BE
            tpl, con = "BP CB - " + BE.AXES.get(st["gen"].get("axis"), ""), "Base plate (AISC DG1 + " + st["gen"].get("concCode", "ACI 318-11") + ")"
        else:
            same = st["beam2"].get("same", True)
            t.insert("end", "LEFT BEAM\n", "h")
            t.insert("end", f"Section : {st['beam1']['sec']}\nMaterial : {st['beam1']['mat']}\n"
                            + (f"Slope angle : {float(st.get('slope') or 0):.2f}\n" if st["type"] == "apex" else ""), "r")
            t.insert("end", "RIGHT BEAM\n", "h")
            t.insert("end", f"Section : {st['beam1']['sec'] if same else st['beam2']['sec']}\n"
                            f"Material : {st['beam1']['mat'] if same else st['beam2']['mat']}\n", "r")
            ext = {"flush": "Flush", "top": "Extended top", "bottom": "Extended bottom", "both": "Extended both"}.get(st["plate"].get("extension"), "")
            tpl, con = f"MEP BS - {PJ.type_label(j)} - {ext}", "Moment connection (Moment end plate splice)"
        t.insert("end", "BASE PLATE CONNECTION\n" if j["kind"] == "base" else "SHEAR AND MOMENT CONNECTION\n", "h")
        t.insert("end", f"Template : {tpl}\nConnection : {con}\n{'Plate / anchors' if j['kind'] == 'base' else 'Plate / bolts'} : {PJ.connection_text(j)}\n", "r")
        _s, R, err = self.result(j)
        if err:
            t.insert("end", f"Lỗi : {err}\n", "bad")
        elif R["gov"]:
            g = R["gov"]; ok = g["ratio"] <= 1.0001 and R["geoFail"] == 0
            t.insert("end", f"Critical ratio : {g['ratio']:.2f} - {g['combo']}  ({'OK' if ok else 'N.G.'})\n", "ok" if ok else "bad")
        t.configure(state="disabled")
        code = st.get("gen", {}).get("designCode", "AISC 2010 LRFD")
        self.cmb_code.set(next((k for k, v in DESIGN_CODES.items() if v == code), "AISC-10 LRFD"))
        notes = st.get("notes", "")
        if j["kind"] == "base" and not str(notes).strip():                 # chân cột: ghi chú mặc định theo thiết kế
            import base_engine as BE
            notes = BE.short_text(st)[1].replace("\r\n", "\n")
        self.notes.insert("1.0", notes)
        self.ent_label.insert(0, st.get("label", ""))

    def _label_changed(self):
        """Tên liên kết (vd. B1) → thẻ nhỏ hiện 'Column Base: B1'."""
        j = self._joint(False)
        if not j: return
        txt = self.ent_label.get().strip()
        if txt != j["state"].get("label", ""):
            j["state"]["label"] = txt; self.project.dirty = True; self._title()
            c = self.cards.get(j["id"])
            if c:
                lab = self._card_title(j)
                c["parts"][2].configure(text=lab, font=("Segoe UI", 11 if len(lab) <= 8 else 9))

    def _code_changed(self):
        j = self._joint(False)
        if not j: return
        st = copy.deepcopy(j["state"]); st.setdefault("gen", {})["designCode"] = DESIGN_CODES[self.cmb_code.get()]
        self.project.update(j["id"], st); self._title()

    def _notes_changed(self):
        j = self._joint(False)
        if not j: return
        txt = self.notes.get("1.0", "end").rstrip("\n")
        if j["kind"] == "base":
            # Additional notes ↔ Description ↔ Column type liên kết: dòng 1 = loại cột (Main / EW Column), dòng 2 = quy cách
            import base_engine as BE
            st = PJ.full_state(j)
            if txt == str(st.get("notes") or "").strip() or (not str(st.get("notes") or "").strip() and txt == BE.short_text(st)[1].replace("\r\n", "\n")):
                return
            role0 = st["opt"].get("colRole", "main")
            st["notes"] = txt
            BE.link_texts(st, "notes")
            for k in ("notes", "desc"): j["state"][k] = st[k]
            j["state"].setdefault("opt", {})["colRole"] = st["opt"]["colRole"]
            self.project.dirty = True; self._title()
            if st["opt"]["colRole"] != role0: self.refresh()
            else: self._show_info()
            return
        if txt != j["state"].get("notes", ""):
            j["state"]["notes"] = txt; self.project.dirty = True; self._title()

    def _joint(self, need=True):
        j = self.project.get(self.sel) if self.sel is not None else None
        if need and not j:
            messagebox.showinfo("Joint", "Chọn một nút ở dải hình phía dưới (hoặc tạo nút mới bằng New).")
        return j

    def _fill_conditions(self):
        j = self._joint(False)
        names = [l.get("name", f"LC{i + 1}") for i, l in enumerate(PJ.full_state(j)["loads"])] if j else []
        self.cmb_cond.configure(values=names)
        cur = self.cmb_cond.get()
        self.cmb_cond.set(cur if cur in names else (names[0] if names else ""))

    def _cond_index(self, j, R):
        names = [l.get("name", f"LC{i + 1}") for i, l in enumerate(PJ.full_state(j)["loads"])]
        if self.critical and R and R["gov"] and R["gov"]["combo"] in names:
            self.cmb_cond.set(R["gov"]["combo"])
        c = self.cmb_cond.get()
        return names.index(c) if c in names else (0 if names else None)

    def _draw(self):
        j = self._joint(False)
        if not j:
            self.view3.show(None); self.view2.show(None); return
        st, R, err = self.result(j)
        if err:
            self.view.show(None); self.set_status(f"Nút {j['id']}: {err}"); return
        i = self._cond_index(j, R)
        dem = R["demands"][i] if i is not None and R["demands"] else None
        heat = None
        if i is not None:
            try:
                st1, R1 = PJ.evaluate(j, [PJ.full_state(j)["loads"][i]])
                heat = {}
                for c in R1["checks"]:
                    if c["info"]: continue
                    for t in c["tags"]: heat[t] = max(heat.get(t, 0.0), c["ratio"])
            except Exception:  # noqa: BLE001
                heat = None
        k = PJ.KINDS[j["kind"]]
        mode = self.cmb_view.get()
        want = self.view3 if mode.startswith("3D") else self.view2
        if want is not self.view:
            self.view.pack_forget(); want.pack(fill="both", expand=True); self.view = want
        if mode.startswith("3D"):
            self.view.show_model(model3d.build(j["kind"], st, R), (), heat if mode == "3D D/C" else None)
        else:
            sc = k["elevation"](st, R, dem, flow=True) if mode == "Elevation" else k["face"](st, R, dem)
            self.view.show(sc, (), heat)
        g = R["gov"]
        self.set_status(f"{k['family']} {j['id']} · {j['state'].get('name', '')} · {PJ.type_label(j)} — "
                        f"Global critical strength ratio {('∞' if math.isinf(g['ratio']) else format(g['ratio'], '.2f')) if g else '—'}"
                        + (f" ({g['name']}, {g['combo']})" if g else ""))

    def _tip(self, tags):
        j = self._joint(False)
        if not j: return ""
        _st, R, err = self.result(j)
        if err: return ""
        lst = sorted((c for c in R["checks"] if set(c["tags"]) & tags and not c["info"]), key=lambda c: -c["ratio"])
        return "\n".join(f"{c['ratio']:5.2f}  {c['name'][:42]}" for c in lst[:7])

    # ───────────────────────── Home · Joints ─────────────────────────
    def new_joint(self):
        res = newjoint.ask(self, "knee", f"{'K'}-{self.project.next_id():02d}")
        if not res: return
        st = res["state"]
        if res["kind"] != "knee" and st.get("name", "").startswith("K-"):
            st["name"] = f"{PJ.KINDS[res['kind']]['prefix']}-{self.project.next_id():02d}"
        j = self.project.add(res["kind"], st)
        self.refresh(); self.select(j["id"])
        self.set_status(f"Đã tạo nút {j['id']} ({PJ.type_label(j)}). Nhấn Edit để thiết kế "
                        + ("bản đế, neo, bệ, hàn." if j["kind"] == "base" else "bản đầu, bu lông, hàn."))

    def edit_joint(self, tab=None):
        j = self._joint()
        if not j: return
        ed = self.editors.get(j["id"])
        if ed is not None and ed.winfo_exists():
            ed.lift(); ed.focus_force(); return
        from connpad import ConnectionPad
        self.editors[j["id"]] = ConnectionPad(self, j, tab)

    def advanced_editor(self, j, tab=None):
        """Khung thiết kế đầy đủ của tool (SAP2000, quét knee, bảng D/C, mặt đứng 2D)."""
        if j["kind"] == "base":
            return None
        key = ("adv", j["id"])
        ed = self.editors.get(key)
        if ed is not None and ed.winfo_exists():
            ed.lift(); ed.focus_force(); return ed
        ed = self.editors[key] = JointEditor(self, j, tab)
        return ed

    def apply_editor(self, jid, state, source=None):
        self.project.update(jid, state); self.refresh(); self.select(jid)
        pad = self.editors.get(jid)
        if pad is not None and pad is not source and pad.winfo_exists() and hasattr(pad, "reload"):
            pad.reload(self.project.get(jid)["state"])

    def delete_joint(self):
        j = self._joint()
        if not j: return
        if messagebox.askyesno("Delete", f"Xoá nút {j['id']} — {j['state'].get('name', '')}?"):
            self.project.delete(j["id"]); self.sel = None; self.refresh()
            self.select(self.project.joints[0]["id"] if self.project.joints else None)

    def delete_all(self):
        if not self.project.joints: return
        if messagebox.askyesno("Delete all", f"Xoá toàn bộ {len(self.project.joints)} nút của dự án?"):
            self.project.clear(); self.sel = None; self.refresh(); self.select(None)

    def copy_joint(self):
        j = self._joint()
        if not j: return
        n = self.project.copy_joint(j["id"]); self.refresh(); self.select(n["id"])

    def _goto(self):
        try:
            jid = int(self.ent_goto.get())
        except ValueError:
            return
        if self.project.get(jid): self.select(jid)
        else: self.set_status(f"Không có nút {jid}.")

    def _import_legacy(self):
        n = self.project.import_legacy(); self.refresh()
        self.set_status(f"Đã nhập {n} liên kết từ danh sách cũ." if n else "Không tìm thấy danh sách cũ (knee_saved.json / splice_saved.json).")

    # ───────────────────────── Load conditions ─────────────────────────
    def edit_data(self, page):
        j = self._joint()
        if not j: return
        st = newjoint.edit_data(self, j["kind"], PJ.full_state(j), page)
        if st is not None:
            self.project.update(j["id"], st); self.refresh(); self.select(j["id"])

    def delete_loads(self):
        j = self._joint()
        if not j: return
        if messagebox.askyesno("Load conditions", f"Xoá toàn bộ {len(j['state'].get('loads', []))} tổ hợp tải của nút {j['id']}?"):
            st = copy.deepcopy(j["state"]); st["loads"] = []
            self.project.update(j["id"], st); self.refresh(); self.select(j["id"])

    def generate_loads(self):
        j = self._joint()
        if not j: return
        if j["kind"] != "knee":
            messagebox.showinfo("Generate", "Lấy nội lực từ SAP2000 hiện có cho knee. Nối dầm / chân cột: nhập hoặc dán từ Excel ở Add/Edit "
                                "(chân cột: Axial, V2, V3, M33, M22 tại đầu I của cột)."); return
        ed = self.advanced_editor(j)
        if ed: ed.after(400, ed.panel._pick_knee)

    # ───────────────────────── View ─────────────────────────
    def template(self):
        j = self._joint()
        if not j: return
        pres = PJ.KINDS[j["kind"]]["presets"]
        m = tk.Menu(self, tearoff=0)
        for name in pres:
            m.add_command(label=name, command=lambda n=name: self._apply_template(j, n))
        m.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    def _apply_template(self, j, name):
        if not messagebox.askyesno("Template", f"Áp mẫu '{name}' cho nút {j['id']}? (tiết diện, bản, bu lông, tải theo mẫu)"): return
        k = PJ.KINDS[j["kind"]]
        st = k["merge"](k["base"], k["presets"][name]); st["name"] = j["state"].get("name", st.get("name"))
        self.project.update(j["id"], st); self.refresh(); self.select(j["id"])

    def info_log(self):
        rows = []
        for j in self.project.joints:
            _st, R, err = self.result(j)
            if err:
                rows.append((j["id"], j["state"].get("name", ""), "Lỗi", err)); continue
            for w in R["W"]:
                rows.append((j["id"], j["state"].get("name", ""), "Cảnh báo", w))
            for x in R["geo"]:
                if not x["ok"]: rows.append((j["id"], j["state"].get("name", ""), "Cấu tạo N.G.", f"{x['grp']}: {x['name']} = {x['val']:.1f}"))
            for c in R["checks"]:
                if c["ratio"] > 1.0001 and not c["info"]:
                    rows.append((j["id"], j["state"].get("name", ""), "N.G.", f"{c['grp']}: {c['name']} — {c['ratio']:.2f} ({c['combo']})"))
        table_dialog(self, "Information log", ["Joint", "Name", "Loại", "Nội dung"], rows or [("", "", "", "Không có cảnh báo.")])

    def toggle_critical(self):
        self.critical = not self.critical
        bg = "#D6DCE4" if self.critical else RIB_BG
        for w in [self.btn_crit] + list(self.btn_crit.winfo_children()):
            w.configure(bg=bg)
        self._draw()

    # ───────────────────────── Databases ─────────────────────────
    def db_sections(self):
        used = {}
        for j in self.project.joints:
            st = PJ.full_state(j)
            secs = ([st["beam"]["sec"], st["col"]["sec"]] if j["kind"] == "knee" else [st["col"]["sec"]] if j["kind"] == "base"
                    else [st["beam1"]["sec"], st["beam2"]["sec"]])
            for s in secs: used.setdefault(s, []).append(str(j["id"]))
        rows = []
        for s, ids in used.items():
            try:
                sec = parse_section(s); a = sec.at(0, 6.0)
                rows.append((s, "Tapered" if sec.tapered else "Prismatic", f"{a.d:g}", f"{a.tw:g}", f"{a.bf_top:g}×{a.tf_top:g}", f"{a.bf_bot:g}×{a.tf_bot:g}", ", ".join(ids)))
            except SectionError as e:
                rows.append((s, "lỗi", "", "", "", str(e)[:40], ", ".join(ids)))
        table_dialog(self, "Sections", ["Section", "Type", "d (đầu I)", "tw", "Cánh trên", "Cánh dưới", "Joints"], rows,
                     "Quy cách tiết diện I tổ hợp (mm): 250.5-150.5 (bụng 250×5, cánh 150×5) · 300.5-250.5-150.10 (cánh trên ≠ cánh dưới) · "
                     "(250-500).5-150.5 (vát) · (250-500-500-250).5.5.5-150.10.10.10/2-bal-2 (nhiều đoạn). Bảng: các tiết diện đang dùng trong dự án.")

    def db_materials(self):
        table_dialog(self, "Materials", ["Material", "Fy [MPa]", "Fu [MPa]"], [(k, v[0], v[1]) for k, v in K.MATERIALS.items()])

    def db_bolts(self):
        rows = [(k, v["label"], f"{v['Fnt']:.1f}", f"{v['FnvN']:.1f}", f"{v['FnvX']:.1f}") for k, v in K.BOLT_GRADES.items()]
        w = table_dialog(self, "Bolts", ["Grade", "Mô tả", "Fnt [MPa]", "Fnv N [MPa]", "Fnv X [MPa]"], rows,
                         "AISC 360-10 Table J3.2. Đường kính: " + ", ".join(f"M{d}" for d in K.BOLT_DIAS)
                         + " · Lỗ tiêu chuẩn (Table J3.3M): " + ", ".join(f"M{d}→{h}" for d, h in K.HOLE_STD.items()))
        return w

    def db_welds(self):
        table_dialog(self, "Welds", ["Electrode", "FEXX [MPa]", "φ·0.6·FEXX·0.707 [N/mm² trên chân hàn]"],
                     [(k, f"{v:.1f}", f"{0.75 * 0.6 * v * 0.707:.1f}") for k, v in K.ELECTRODES.items()],
                     "AISC 360-10 J2.4 — hàn góc. Cỡ hàn nhập theo D (1/16 in) như RAM: D = 5 → w = 7.94 mm.")

    def db_anchors(self):
        import base_engine as BE
        rows = [(g, f"{fy:g}", f"{fu:g}", f"{0.75 * 0.75 * fu:.1f}", f"{0.75 * 0.40 * fu:.1f}") for g, (fy, fu) in BE.ANCHOR_GRADES.items()]
        return table_dialog(self, "Anchors", ["Grade", "Fy [MPa]", "Fu [MPa]", "φFnt = 0.75·0.75Fu", "φFnv = 0.75·0.40Fu (N)"], rows,
                            "Bu lông neo (thanh ren) — AISC 360-10 Table J3.2. Đường kính: " + ", ".join(BE.anchor_label(d) for d in BE.ANCHOR_DIAS)
                            + " · Lỗ bản đế (DG1 Table 2.3 quy đổi): " + ", ".join(f"M{d}→{h}" for d, h in BE.HOLE_DG1.items()))

    def db_connections(self):
        rows = []
        for g in newjoint.GROUPS:
            for name, code, key, _ in g[2]:
                rows.append((g[0], name, code, "Có" if key else "Chưa hỗ trợ"))
        table_dialog(self, "Connections", ["Group", "Joint", "Code", "Trong tool"], rows)

    # ───────────────────────── Design ─────────────────────────
    def smart_connection(self):
        j = self._joint()
        if not j: return
        k = PJ.KINDS[j["kind"]]
        st = PJ.full_state(j)
        self.set_status("Đang thử các phương án tp / bu lông…"); self.update_idletasks()
        res = k["auto"](copy.deepcopy(st))
        if not res:
            messagebox.showwarning("Smart connection", "Không tính được phương án nào — kiểm tra lại số liệu."); return
        PJ.apply_auto(j["kind"], st, res)
        self.project.update(j["id"], st); self.refresh(); self.select(j["id"])
        msg = (f"Bản đế {res['N']:g}×{res['B']:g}×{res['tp']:g}, neo {PJ.BE.anchor_label(res['d'])} hef {res['hef']:g} — D/C = {res['ratio']:.2f}" if j["kind"] == "base"
               else f"tp = {res['tp']} mm, bu lông M{res['d']} — D/C (bản, bu lông) = {res['ratio']:.2f}")
        if res.get("fail"):
            messagebox.showwarning("Smart connection", "Không có phương án đạt trong dải thử.\nPhương án tốt nhất: " + msg)
        self.set_status("Smart connection: " + msg)

    def design_all(self):
        self._cache.clear(); self.refresh(); self._draw()
        bad = [j["id"] for j in self.project.joints if (self.result(j)[1] or {}).get("gov") and self.result(j)[1]["gov"]["ratio"] > 1.0001]
        self.set_status(f"Đã tính lại {len(self.project.joints)} nút." + (f" Không đạt: {', '.join(map(str, bad))}" if bad else " Tất cả đạt."))

    # ───────────────────────── Output ─────────────────────────
    def report_one(self):
        j = self._joint()
        if not j: return
        st, R, err = self.result(j)
        if err: messagebox.showerror("Report", err); return
        path = filedialog.asksaveasfilename(title="Report", defaultextension=".docx", filetypes=[("Word", "*.docx")],
                                            initialfile=f"{j['id']}_{j['state'].get('name', 'joint')}_report.docx".replace("/", "-").replace(":", "-"))
        if not path: return
        RP = PJ.KINDS[j["kind"]]["report"]
        RP.to_docx(RP.build(st, R, os.path.basename(self.project.path or "")), path)
        self.set_status(f"Đã xuất báo cáo: {path}")

    def report_all(self):
        if not self.project.joints: return
        d = filedialog.askdirectory(title="Thư mục lưu báo cáo")
        if not d: return
        n = 0
        for j in self.project.joints:
            st, R, err = self.result(j)
            if err: continue
            RP = PJ.KINDS[j["kind"]]["report"]
            name = f"{j['id']}_{j['state'].get('name', 'joint')}".replace("/", "-").replace(":", "-")
            RP.to_docx(RP.build(st, R, os.path.basename(self.project.path or "")), os.path.join(d, name + "_report.docx")); n += 1
        self.set_status(f"Đã xuất {n} báo cáo vào {d}")

    def export_rcnx(self):
        """File RAM Connection (.rcnx) với các liên kết của dự án, đúng thông số đầu vào trong tool."""
        import knee_gui
        import ram_export
        joints = self.project.joints
        if not joints:
            messagebox.showinfo("Export RAM", "Dự án chưa có liên kết."); return
        ok = [j for j in joints if ram_export.supported(j["kind"])]
        skip = [j for j in joints if not ram_export.supported(j["kind"])]
        if not ok:
            messagebox.showinfo("Export RAM", ram_export.unsupported_note(skip)); return
        states = [PJ.full_state(j) for j in ok]
        msg = knee_gui.export_rcnx_dialog(states, messagebox.askyesno("Export RAM", "Tạo tiết diện còn thiếu trong database RAM (WS Section-Hoang)?"),
                                          extra=ram_export.unsupported_note(skip) if skip else "", kinds=[j["kind"] for j in ok])
        if msg: self.set_status(msg)

    def export_csv(self):
        path = filedialog.asksaveasfilename(title="Results table", defaultextension=".csv", filetypes=[("CSV (Excel)", "*.csv")], initialfile="ket_qua.csv")
        if not path: return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["Joint", "Name", "Family", "Type", "Members", "Connection", "Conditions", "Ratio", "Status", "Critical check", "Condition"])
            for j in self.project.joints:
                _st, R, err = self.result(j)
                g = R["gov"] if R else None
                ok = bool(R) and g is not None and g["ratio"] <= 1.0001 and R["geoFail"] == 0
                w.writerow([j["id"], j["state"].get("name", ""), PJ.KINDS[j["kind"]]["family"], PJ.type_label(j), PJ.members_text(j),
                            PJ.connection_text(j), len(PJ.full_state(j)["loads"]), f"{g['ratio']:.3f}" if g else "",
                            "ERR" if err else ("OK" if ok else "N.G."), g["name"] if g else err or "", g["combo"] if g else ""])
        self.set_status(f"Đã xuất bảng kết quả: {path}")


class JointEditor(ctk.CTkToplevel):
    """Cửa sổ thiết kế liên kết của một nút (khung KNEE hoặc NỐI DẦM) + OK / Apply / Cancel."""

    def __init__(self, app: App, j: dict, tab=None):
        super().__init__(app)
        self.app, self.jid, self.kind = app, j["id"], j["kind"]
        fam = PJ.KINDS[j["kind"]]["family"]
        self.title(f"{fam} {j['id']} — {j['state'].get('name', '')} — Connection design")
        self.geometry("1560x940")
        self.minsize(1100, 700)
        foot = tk.Frame(self, bg="#F0F0F0"); foot.pack(side="bottom", fill="x")
        for t, cmd in (("Cancel", self.destroy), ("Apply", self.apply), ("OK", self.ok)):
            tk.Button(foot, text=t, width=10, font=("Segoe UI", 9), relief="groove", command=cmd).pack(side="right", padx=6, pady=6)
        tk.Label(foot, text="OK / Apply: lưu thông số vào dự án · Cancel: bỏ thay đổi", bg="#F0F0F0", fg="#5B6777", font=("Segoe UI", 9)).pack(side="left", padx=8)
        if j["kind"] == "knee":
            from knee_gui import KneePanel as Panel
        else:
            from splice_gui import SplicePanel as Panel
        self.panel = Panel(self, PJ.full_state(j), on_add=self._add)
        self.panel.pack(fill="both", expand=True)
        if tab:
            self.panel.tabs.set(tab)
        self.after(300, self.panel._init_sashes)
        self.after(100, self.lift)

    def _add(self, kind, name, state):
        st = copy.deepcopy(state); st["name"] = name
        self.app.project.add(kind, st); self.app.refresh()

    def apply(self):
        self.app.apply_editor(self.jid, copy.deepcopy(self.panel.S))

    def ok(self):
        self.apply(); self.destroy()


def main():
    App(sys.argv[1] if len(sys.argv) > 1 else None).mainloop()


if __name__ == "__main__":
    main()
