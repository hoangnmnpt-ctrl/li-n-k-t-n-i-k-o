"""
splice_gui.py — NỐI DẦM (Beam splice / Apex) — AISC 360-10 LRFD · DG4 / DG16 / DG39 (customtkinter)
================================================================================================
Cùng bố cục với KNEE KÈO (knee_app/gui.py):
  • Form nhập theo đúng thứ tự & nhãn của RAM Connection (Beam splice — Moment end plate).
  • Hình mặt đứng + mặt bản đầu, tô màu theo D/C, dòng lực, thanh trượt / phát tự động theo tổ hợp.
  • Bảng kiểm tra D/C, diễn giải công thức từng bước, thẻ đồng hồ theo nhóm.
  • Tab Loads (dán từ Excel), Report (RAM) + xuất Word, Danh sách đã lưu, Nội lực quy đổi, Cấu tạo & cảnh báo.
  • Tự chọn tp / bu lông.
"""

from __future__ import annotations

import copy
import json
import math
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _knee import K, knee_section  # noqa: E402
import splice_engine as SE  # noqa: E402
import splice_report as RP  # noqa: E402
from splice_defaults import BASE, PRESETS, merge  # noqa: E402
from splice_drawing import KneeCanvas, elevation, heat_color, plate_face  # noqa: E402
from splice_store import SavedList  # noqa: E402

APP_TITLE = "NỐI DẦM — AISC 360-10 LRFD · DG4 / DG16 / DG39"
TYPE_LABEL = {"straight": "Beam splice", "apex": "Apex"}
TYPE_KEY = {v: k for k, v in TYPE_LABEL.items()}
MATS = list(K.MATERIALS)
FONT = ("Segoe UI", 12)
FONT_S = ("Segoe UI", 11)
FONT_B = ("Segoe UI", 12, "bold")
OK_C, WARN_C, BAD_C = "#1A9E5A", "#D99A00", "#D23B3B"
ACCENT = "#E0701C"

CATS = [("Bản đầu 1", ("pl1_",)), ("Bản đầu 2", ("pl2_",)), ("Bu lông", ("bolt_", "bear_")),
        ("Hàn dầm 1", ("m1_wf", "m1_ww")), ("Hàn dầm 2", ("m2_wf", "m2_ww")), ("Bụng dầm", ("m1_wv", "m2_wv"))]
TAG_NAME = {"plate1": "Bản đầu 1", "plate2": "Bản đầu 2", "boltsT": "Bu lông nhóm cánh trên", "boltsB": "Bu lông nhóm cánh dưới"}
for _k in (1, 2):
    TAG_NAME.update({f"m{_k}weldT": f"Hàn cánh trên dầm {_k}", f"m{_k}weldB": f"Hàn cánh dưới dầm {_k}",
                     f"m{_k}webweld": f"Hàn bụng dầm {_k}", f"m{_k}web": f"Bụng dầm {_k}"})


def rc(r):
    return BAD_C if r > 1.0001 else WARN_C if r > 0.9 else OK_C


# ─────────────────────────── Khai báo form ───────────────────────────
def num(p, l, u="mm", show=None, w2=False): return dict(k="num", p=p, l=l, u=u, show=show, w2=w2)
def txt(p, l, show=None, w2=True): return dict(k="txt", p=p, l=l, show=show, w2=w2)
def sel(p, l, opts, show=None, w2=False): return dict(k="sel", p=p, l=l, opts=[o if isinstance(o, tuple) else (o, str(o)) for o in opts], show=show, w2=w2)
def chk(p, l, show=None): return dict(k="chk", p=p, l=l, show=show, w2=True)
def sub(l, show=None): return dict(k="sub", l=l, show=show, w2=True)
def info(p, show=None): return dict(k="info", p=p, w2=True, show=show)
def btn(l, cmd): return dict(k="btn", l=l, cmd=cmd, w2=True, show=None)
def note(l, show=None): return dict(k="note", l=l, w2=True, show=show)


def tip(spec, text):
    spec["tip"] = text
    return spec


def build_sections(app):
    """Form nhập theo đúng thứ tự & nhãn của RAM Connection (Beam splice — Moment end plate)."""
    S = lambda: app.S
    ext = lambda *v: S()["plate"].get("extension") in v
    two = lambda: not S()["beam2"].get("same", True)
    ELEC = list(K.ELECTRODES)
    WT = [("fillet", "Fillet"), ("cjp", "CJP")]
    return [
        ("General information", True, [
            sub("Analysis"),
            btn("Loads   <Loads>  →  mở bảng tải", lambda: app.tabs.set("Loads")),
            sub("Design criteria"),
            tip(sel("gen.designCode", "Design code", ["AISC 2010 LRFD", "AISC 2016 LRFD"], w2=True), "Tiêu chuẩn thiết kế (tính theo LRFD)"),
            sub("Construction criteria"),
            tip(chk("opt.holeDef", "Consider hole deformation in bolts"), "Xét biến dạng lỗ khi tính ép mặt (J3-6a: 1.2/2.4; bỏ chọn: 1.5/3.0)"),
            tip(chk("bolt.snug", "Snug-tight bolted"), "Bu lông siết sơ bộ → giảm Tb khi tính lực nhổ"),
            tip(chk("opt.sheared", "Consider sheared edges"), "Mép bản cắt bằng cưa/đột → khoảng cách mép tối thiểu lớn hơn"),
        ]),
        ("Members", True, [
            sub("Configuration"),
            note("Splice type:  Beam splice (thẳng) / Apex (đỉnh mái) — chọn ở thanh trên hình"),
            tip(num("slope", "Vertical angle of each rafter (deg)", "°", show=lambda: S()["type"] == "apex", w2=True),
                "Apex: góc dốc của mỗi dầm so với phương ngang; bản đầu đặt đứng"),
            sub("Beam 1 (left)"),
            tip(txt("beam1.sec", "Beam 1 section"), "Quy cách tiết diện — 500.8-200.12 (bụng 500×8, cánh 200×12) hoặc (580-380).6-200.10"), info("beam1.sec"),
            sel("beam1.mat", "Beam 1 material", MATS), tip(num("beam1.L", "Beam 1 length", "m"), "Chiều dài dầm 1 (chỉ dùng cho tiết diện vát)"),
            tip(sel("beam1.jointEnd", "Joint end", [("J", "End J"), ("I", "End I")]), "Đầu dầm tại mặt nối (chỉ dùng cho tiết diện vát)"),
            sub("Beam 2 (right)"),
            tip(chk("beam2.same", "Same as beam 1"), "Dầm 2 giống dầm 1"),
            txt("beam2.sec", "Beam 2 section", show=two), info("beam2.sec", show=two),
            sel("beam2.mat", "Beam 2 material", MATS, show=two), num("beam2.L", "Beam 2 length", "m", show=two),
            sel("beam2.jointEnd", "Joint end", [("I", "End I"), ("J", "End J")], show=two),
        ]),
        ("Moment end plate", True, [
            sub("Connector"),
            tip(sel("plate.extension", "Plate extension", [("flush", "Flush"), ("top", "Extended top edge"),
                                                          ("bottom", "Extended bottom edge"), ("both", "Extended both edges")], w2=True),
                "Bản nhô ra ngoài cánh trên / cánh dưới / cả hai (mô men đổi dấu cần nhô cả hai)"),
            tip(num("plate.tp1", "tp1: End plate 1 thickness"), "Bản đầu của dầm 1"), sel("plate.mat1", "Plate 1 material", MATS),
            tip(num("plate.tp2", "tp2: End plate 2 thickness"), "Bản đầu của dầm 2"), sel("plate.mat2", "Plate 2 material", MATS),
            sel("plate.holeType", "Hole type on plate", ["STD"]), tip(num("plate.flushExt", "Flush extension length"), "Phần bản thừa phía không nhô"),
            sub("Weld"),
            sel("weld.flT.type", "Top flange weld type", WT), sel("weld.flT.electrode", "Weld to top flange", ELEC),
            tip(num("weld.flT.D", "D1: Weld size to top flange (1/16in)", "/16", show=lambda: S()["weld"]["flT"]["type"] == "fillet", w2=True), "Cỡ hàn theo 1/16 inch (8 → 12.7 mm)"),
            sel("weld.flB.type", "Bottom flange weld type", WT), sel("weld.flB.electrode", "Weld to bottom flange", ELEC),
            num("weld.flB.D", "D3: Weld size to bottom flange (1/16in)", "/16", show=lambda: S()["weld"]["flB"]["type"] == "fillet", w2=True),
            sel("weld.web.electrode", "Web weld", ELEC), num("weld.web.D", "D2: Weld size to web (1/16in)", "/16"),
            sub("Bolts"),
            sel("bolt.d", "Bolts — diameter", [(d, f"M{d}") for d in K.BOLT_DIAS]),
            sel("bolt.grade", "Bolts — grade", [("8.8", "G_8_8"), ("10.9", "G_10_9"), ("A325", "A325M"), ("A490", "A490M")]),
            sel("bolt.thread", "Threads", [("N", "N — included"), ("X", "X — excluded")]),
            tip(num("plate.g", "g: Gage - transverse center-to-center spacing", w2=True), "Khoảng cách 2 dãy bu lông"),
            sel("bolt.holeType", "Hole type", ["STD"]), note(""),
            num("plate.Lev", "Lev: Vertical edge distance"), num("plate.Leh", "Leh: Horizontal edge distance"),
            sub("Bolt group (top extension)", show=lambda: ext("top", "both")),
            num("plate.pfoT", "pfo t: Distance from bolt rows to flange", show=lambda: ext("top", "both"), w2=True),
            sub("Bolt group (top flange)"),
            sel("plate.nT", "Bolts rows number", [1, 2, 3]), num("plate.pfiT", "pfi t: Distance from bolt rows to flange"),
            num("plate.pbT", "s t: Vertical spacing between inner bolt rows", show=lambda: int(S()["plate"]["nT"]) > 1, w2=True),
            sub("Bolt group (bottom flange)"),
            sel("plate.nB", "Bolts rows number", [1, 2, 3]), num("plate.pfiB", "pfi b: Distance from bolt rows to flange"),
            num("plate.pbB", "s b: Vertical spacing between inner bolt rows", show=lambda: int(S()["plate"]["nB"]) > 1, w2=True),
            sub("Bolt group (bottom extension)", show=lambda: ext("bottom", "both")),
            num("plate.pfoB", "pfo b: Distance from bolt rows to flange", show=lambda: ext("bottom", "both"), w2=True),
        ]),
        ("Options (tool)", False, [
            txt("name", "Connection name"),
            tip(sel("opt.hRef", "Yield-line lever arm h measured from", [("face", "Compression flange face (DG16 / RAM)"),
                                                                       ("centerline", "Compression flange centerline (DG4 / DG39)")], w2=True),
                "DG16 (như RAM Connection) đo h từ mặt cánh nén; DG4/DG39 đo từ tâm cánh nén (Y thấp hơn ~1–2 %, thiên về an toàn)"),
            tip(chk("opt.axialRelief", "Axial compression reduces Mu,eq (as RAM)"), "Kể lực dọc nén làm giảm Mu,eq"),
            chk("opt.directional", "Directional strength increase for fillet welds"),
            chk("opt.shearAll", "All bolts resist shear"),
            chk("opt.flangeWeldMin", "Flange weld design force ≥ 0.6·Fy·Af"),
            chk("plate.stiffT.on", "End-plate stiffener at top extension (4ES)", show=lambda: ext("top", "both") and int(S()["plate"]["nT"]) == 1),
            num("plate.stiffT.ts", "ts", show=lambda: S()["plate"]["stiffT"]["on"]), num("plate.stiffT.L", "Lst", show=lambda: S()["plate"]["stiffT"]["on"]),
            chk("plate.stiffB.on", "End-plate stiffener at bottom extension (4ES)", show=lambda: ext("bottom", "both") and int(S()["plate"]["nB"]) == 1),
            num("plate.stiffB.ts", "ts", show=lambda: S()["plate"]["stiffB"]["on"]), num("plate.stiffB.L", "Lst", show=lambda: S()["plate"]["stiffB"]["on"]),
        ]),
    ]


def getp(d, p):
    for k in p.split("."):
        d = d[k]
    return d


def setp(d, p, v):
    ks = p.split(".")
    for k in ks[:-1]:
        d = d.setdefault(k, {})
    d[ks[-1]] = v


class StatusBar(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, height=24, corner_radius=0)
        self.lbl = ctk.CTkLabel(self, text="Sẵn sàng", font=("Segoe UI", 11), anchor="w", text_color="#3B4656")
        self.lbl.pack(side="left", padx=8)

    def set_text(self, s):
        self.lbl.configure(text=s)


# ═══════════════════════════ APP ═══════════════════════════
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1560x940")
        self.minsize(1100, 700)
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.S = merge(BASE, {})
        self.R = None
        self.sel_check = None
        self.combo_idx = 0
        self.view = "elev"
        self._suspend = False
        self._job = None
        self._playing = False
        self.fields = []
        self.saved = SavedList()

        self._build()
        self._load_form()
        self.run()
        self.after(300, self._init_sashes)

    def _init_sashes(self):
        try:
            W = self.hpan.winfo_width()
            self.hpan.sashpos(0, 385)
            self.hpan.sashpos(1, max(W - 600, 900))
            self.vpan.sashpos(0, int(self.vpan.winfo_height() * 0.70))
        except tk.TclError:
            pass

    # ───────────────────────── Bố cục ─────────────────────────
    def _build(self):
        self.status = StatusBar(self)
        self.status.pack(side="bottom", fill="x")

        top = ctk.CTkFrame(self, corner_radius=0)
        top.pack(fill="x")
        ctk.CTkLabel(top, text="NỐI DẦM", font=("Segoe UI", 16, "bold"), text_color=ACCENT).pack(side="left", padx=(10, 2))
        ctk.CTkLabel(top, text="AISC 360-10 LRFD", font=FONT_S, text_color="gray").pack(side="left", padx=(0, 12))
        self.opt_preset = ctk.CTkOptionMenu(top, values=list(PRESETS), width=300, height=28, command=self._preset)
        self.opt_preset.set("Nạp mẫu…"); self.opt_preset.pack(side="left", padx=3)
        ctk.CTkButton(top, text="⚙ Tự chọn tp / bu lông", width=160, height=30, fg_color="#B45309", hover_color="#92400E", font=FONT_B,
                      command=self._auto).pack(side="left", padx=6)
        ctk.CTkButton(top, text="💾 Lưu vào danh sách", width=150, height=30, fg_color="#059669", hover_color="#047857", font=FONT_B,
                      command=self._save_new).pack(side="right", padx=6)
        ctk.CTkButton(top, text="📄 Xuất Word", width=110, height=30, fg_color="#2563EB", font=FONT_B, command=self._export_docx).pack(side="right", padx=3)

        vpan = self.vpan = ttk.PanedWindow(self, orient="vertical")
        vpan.pack(fill="both", expand=True, padx=6, pady=4)
        hpan = self.hpan = ttk.PanedWindow(vpan, orient="horizontal")
        vpan.add(hpan, weight=4)

        # form trái
        left = ctk.CTkFrame(hpan, width=370)
        hpan.add(left, weight=0)
        self.form = ctk.CTkScrollableFrame(left, width=350, label_text="THÔNG SỐ LIÊN KẾT NỐI DẦM", label_font=FONT_B)
        self.form.pack(fill="both", expand=True)
        self._build_form()

        # giữa: hình
        mid = ctk.CTkFrame(hpan)
        hpan.add(mid, weight=3)
        bar = ctk.CTkFrame(mid, fg_color="transparent"); bar.pack(fill="x", padx=4, pady=4)
        self.seg_type = ctk.CTkSegmentedButton(bar, values=list(TYPE_LABEL.values()), command=self._type_changed, font=FONT_B,
                                               selected_color=ACCENT, selected_hover_color="#C25E12")
        self.seg_type.pack(side="left")
        self.seg_view = ctk.CTkSegmentedButton(bar, values=["Mặt đứng", "Mặt bản đầu"], command=self._view_changed, font=FONT_S)
        self.seg_view.set("Mặt đứng"); self.seg_view.pack(side="left", padx=10)
        self.opt_combo = ctk.CTkOptionMenu(bar, values=["—"], width=230, height=26, command=self._combo_changed)
        self.opt_combo.pack(side="right")
        ctk.CTkLabel(bar, text="Tổ hợp hiển thị", font=FONT_S).pack(side="right", padx=4)
        bar2 = ctk.CTkFrame(mid, fg_color="transparent"); bar2.pack(fill="x", padx=4)
        self.var_heat = ctk.BooleanVar(value=True)
        self.var_flow = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(bar2, text="Tô màu theo D/C", variable=self.var_heat, command=self._draw, font=FONT_S).pack(side="left", padx=(2, 10))
        ctk.CTkSwitch(bar2, text="Dòng lực", variable=self.var_flow, command=self._draw, font=FONT_S).pack(side="left", padx=(0, 10))
        self.btn_play = ctk.CTkButton(bar2, text="▶", width=34, height=26, command=self._play)
        self.btn_play.pack(side="left", padx=(6, 4))
        self.slider = ctk.CTkSlider(bar2, from_=0, to=1, number_of_steps=1, command=self._slider)
        self.slider.pack(side="left", fill="x", expand=True, padx=4)
        self.lbl_combo = ctk.CTkLabel(bar2, text="", font=("Segoe UI", 11, "bold"), width=150, anchor="w")
        self.lbl_combo.pack(side="left", padx=4)
        leg = tk.Canvas(bar2, width=150, height=22, highlightthickness=0, background="#F2F4F7")
        leg.pack(side="right", padx=4)
        for i in range(120):
            leg.create_line(15 + i, 4, 15 + i, 12, fill=heat_color(i / 100))
        for v in (0, 0.6, 0.9, 1.0, 1.2):
            leg.create_text(15 + v * 100, 18, text=f"{v:g}", font=("Segoe UI", 7), fill="#5B6777")
        self.view_host = tk.Frame(mid, background="#FFFFFF")
        self.view_host.pack(fill="both", expand=True, padx=4, pady=(2, 2))
        self.canvas = KneeCanvas(self.view_host)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.tipfn = self._tip_text
        self.lbl_draw = ctk.CTkLabel(mid, text="", font=("Consolas", 11), text_color="#5B6777", anchor="w")
        self.lbl_draw.pack(fill="x", padx=8, pady=(0, 4))

        # phải: tổng hợp + bảng kiểm tra + diễn giải
        right = ctk.CTkFrame(hpan, width=470)
        hpan.add(right, weight=2)
        head = ctk.CTkFrame(right, fg_color="transparent"); head.pack(fill="x", padx=8, pady=(8, 2))
        self.lbl_status = ctk.CTkLabel(head, text="", font=("Segoe UI", 20, "bold"))
        self.lbl_status.pack(side="left")
        self.lbl_ratio = ctk.CTkLabel(head, text="", font=("Consolas", 26, "bold"))
        self.lbl_ratio.pack(side="right")
        self.bar_ratio = ctk.CTkProgressBar(right, height=12)
        self.bar_ratio.pack(fill="x", padx=10)
        self.lbl_gov = ctk.CTkLabel(right, text="", font=FONT_S, justify="left", anchor="w", wraplength=440)
        self.lbl_gov.pack(fill="x", padx=10, pady=(4, 2))
        self.lbl_kv = ctk.CTkLabel(right, text="", font=("Consolas", 11), justify="left", anchor="w", text_color="#3B4656")
        self.lbl_kv.pack(fill="x", padx=10, pady=(0, 4))

        style = ttk.Style()
        style.configure("K.Treeview", rowheight=24, font=("Segoe UI", 10))
        style.configure("K.Treeview.Heading", font=("Segoe UI", 10, "bold"))
        cards = ctk.CTkFrame(right, fg_color="transparent"); cards.pack(fill="x", padx=6, pady=(2, 4))
        self.cards = {}
        for i, (name, _pref) in enumerate(CATS):
            cv = tk.Canvas(cards, width=108, height=74, highlightthickness=1, highlightbackground="#E2E7EE", background="#FFFFFF", cursor="hand2")
            cv.grid(row=i // 3, column=i % 3, padx=2, pady=2, sticky="ew")
            cv.bind("<Button-1>", lambda e, n=name: self._card_click(n))
            self.cards[name] = cv
        for c in range(3):
            cards.grid_columnconfigure(c, weight=1)
        tf = ttk.Frame(right); tf.pack(fill="both", expand=True, padx=6, pady=2)
        cols = ("dc", "cap", "dem", "unit", "combo", "ref")
        self.tree = ttk.Treeview(tf, columns=cols, style="K.Treeview", selectmode="browse")
        for c, h, w, an in (("#0", "Kiểm tra", 235, "w"), ("dc", "D/C", 48, "center"), ("cap", "Khả năng", 72, "e"), ("dem", "Yêu cầu", 72, "e"),
                            ("unit", "ĐV", 50, "center"), ("combo", "Tổ hợp", 90, "w"), ("ref", "Tham chiếu", 120, "w")):
            self.tree.heading(c, text=h); self.tree.column(c, width=w, anchor=an, stretch=c in ("#0", "ref"))
        for tag, col in (("ok", OK_C), ("warn", WARN_C), ("bad", BAD_C), ("info", "#8A94A3")):
            self.tree.tag_configure(tag, foreground=col)
        self.tree.tag_configure("grp", font=("Segoe UI", 10, "bold"), background="#FFF1E3")
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._check_selected)
        self.txt_detail = tk.Text(right, height=11, font=("Consolas", 10), wrap="word", background="#F6F8FB", relief="flat", padx=8, pady=6)
        self.txt_detail.pack(fill="x", padx=6, pady=(2, 8))

        # dưới: tab
        self.tabs = ctk.CTkTabview(vpan, height=250)
        vpan.add(self.tabs, weight=1)
        for name in ("Loads", "Report (RAM)", "Danh sách đã lưu", "Nội lực quy đổi", "Cấu tạo & cảnh báo"):
            self.tabs.add(name)
        self._build_loads_tab(self.tabs.tab("Loads"))
        self._build_report_tab(self.tabs.tab("Report (RAM)"))
        self._build_saved_tab(self.tabs.tab("Danh sách đã lưu"))
        self.tree_dem = self._mk_table(self.tabs.tab("Nội lực quy đổi"),
                                       [("name", "Tổ hợp", 170), ("V", "V", 70), ("N", "N", 70), ("M", "M (kN·m)", 80), ("Nn", "Nn", 70), ("Vt", "Vt", 70),
                                        ("FnT", "Ffu trên", 85), ("FnB", "Ffu dưới", 85), ("Mu", "Mu,eq", 80), ("side", "Phía kéo", 90)])
        self.tree_geo = self._mk_table(self.tabs.tab("Cấu tạo & cảnh báo"),
                                       [("grp", "Nhóm", 160), ("name", "Kích thước", 280), ("val", "Giá trị", 80), ("min", "Min", 80), ("max", "Max", 80), ("ok", "", 40), ("ref", "Tham chiếu", 200)])
        self.tree_geo.tag_configure("bad", foreground=BAD_C)
        self.tree_geo.tag_configure("warn", foreground=WARN_C)

    def _mk_table(self, parent, cols, height=7):
        fr = ttk.Frame(parent); fr.pack(fill="both", expand=True)
        tv = ttk.Treeview(fr, columns=[c[0] for c in cols], show="headings", style="K.Treeview", height=height)
        for c, h, w in cols:
            tv.heading(c, text=h); tv.column(c, width=w, anchor="w" if c in ("name", "grp", "ref", "src") else "e")
        sb = ttk.Scrollbar(fr, orient="vertical", command=tv.yview); tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        return tv

    # ───────────────────────── Form ─────────────────────────
    def _build_form(self):
        self.fields = []
        for title, opened, specs in build_sections(self):
            hdr = ctk.CTkButton(self.form, text=("▾ " if opened else "▸ ") + title, anchor="w", font=FONT_B, height=28,
                                fg_color="#EEF1F5", text_color="#18212F", hover_color="#E2E7EE")
            hdr.pack(fill="x", pady=(6, 2))
            body = ctk.CTkFrame(self.form, fg_color="transparent")
            if opened: body.pack(fill="x")
            body.grid_columnconfigure((0, 1), weight=1)
            hdr.configure(command=lambda b=body, h=hdr, t=title: self._toggle(b, h, t))
            r = c = 0
            for sp in specs:
                w2 = sp.get("w2")
                if w2 and c == 1: r += 1; c = 0
                cell = ctk.CTkFrame(body, fg_color="transparent")
                grid = dict(row=r, column=c, columnspan=2 if w2 else 1, sticky="ew", padx=3, pady=2)
                f = dict(spec=sp, cell=cell, grid=grid)
                self._make_widget(f)
                self.fields.append(f)
                if w2: r += 1; c = 0
                else:
                    c += 1
                    if c == 2: r += 1; c = 0

    def _toggle(self, body, hdr, title):
        if body.winfo_ismapped():
            body.pack_forget(); hdr.configure(text="▸ " + title)
        else:
            body.pack(fill="x", after=hdr); hdr.configure(text="▾ " + title)

    def _make_widget(self, f):
        sp, cell = f["spec"], f["cell"]
        k = sp["k"]
        if k == "sub":
            ctk.CTkLabel(cell, text=sp["l"].upper(), font=("Segoe UI", 11, "bold"), text_color=ACCENT, anchor="w").pack(fill="x", pady=(6, 0))
            return
        if k == "info":
            f["lbl"] = ctk.CTkLabel(cell, text="", font=("Segoe UI", 10), anchor="w", justify="left", wraplength=320)
            f["lbl"].pack(fill="x")
            return
        if k == "btn":
            ctk.CTkButton(cell, text=sp["l"], height=28, font=FONT_B, fg_color="#1F6FEB", command=sp["cmd"]).pack(fill="x", pady=2)
            return
        if k == "note":
            ctk.CTkLabel(cell, text=sp["l"], font=("Segoe UI", 11), text_color="#5B6777", anchor="w", wraplength=330, justify="left").pack(fill="x")
            return
        if k == "chk":
            var = ctk.BooleanVar()
            w = ctk.CTkCheckBox(cell, text=sp["l"], variable=var, font=FONT_S, command=lambda f=f: self._changed(f, True))
            w.pack(anchor="w")
            f["var"] = var; f["w"] = w
            self._bind_tip(w, sp)
            return
        lab = ctk.CTkLabel(cell, text=sp["l"], font=("Segoe UI", 10), text_color="#5B6777", anchor="w")
        lab.pack(fill="x")
        self._bind_tip(lab, sp)
        if k == "sel":
            labels = [l for _, l in sp["opts"]]
            w = ctk.CTkOptionMenu(cell, values=labels, height=26, font=FONT_S, dynamic_resizing=False,
                                  command=lambda _v, f=f: self._changed(f, True))
            w.pack(fill="x"); f["w"] = w
            return
        var = tk.StringVar()
        row = ctk.CTkFrame(cell, fg_color="transparent"); row.pack(fill="x")
        e = ctk.CTkEntry(row, textvariable=var, height=26, font=("Consolas", 12) if k == "txt" else FONT_S,
                         justify="left" if k == "txt" else "right")
        e.pack(side="left", fill="x", expand=True)
        if k == "num":
            ctk.CTkLabel(row, text=sp["u"], font=("Segoe UI", 10), text_color="gray", width=26).pack(side="left")
        var.trace_add("write", lambda *_a, f=f: self._changed(f, False))
        f["var"] = var; f["w"] = e

    def _bind_tip(self, widget, sp):
        if not sp.get("tip"): return
        if not hasattr(self, "_form_tip"):
            from drawing import _Tip
            self._form_tip = _Tip(self)
        widget.bind("<Enter>", lambda e, t=sp["tip"]: self._form_tip.show(e.x_root, e.y_root, t))
        widget.bind("<Leave>", lambda e: self._form_tip.hide())

    def _load_form(self):
        SE.normalize(self.S)
        self._suspend = True
        for f in self.fields:
            sp = f["spec"]; k = sp["k"]
            if k in ("sub", "info", "btn", "note"): continue
            v = getp(self.S, sp["p"])
            if k == "chk": f["var"].set(bool(v))
            elif k == "sel":
                lab = next((l for key, l in sp["opts"] if str(key) == str(v)), sp["opts"][0][1])
                f["w"].set(lab)
            else: f["var"].set("" if v is None else (f"{v:g}" if isinstance(v, float) else str(v)))
        self._suspend = False
        self.seg_type.set(TYPE_LABEL[self.S["type"]])
        self._refresh_visibility(); self._update_info()
        self._fill_loads()

    def _changed(self, f, structural):
        if self._suspend: return
        sp = f["spec"]; k = sp["k"]
        if k == "chk": v = bool(f["var"].get())
        elif k == "sel":
            lab = f["w"].get()
            v = next((key for key, l in sp["opts"] if l == lab), sp["opts"][0][0])
        elif k == "num":
            s = f["var"].get().replace(",", ".").strip()
            try: v = float(s)
            except ValueError: return
            if v.is_integer() and sp["p"] in ("plate.nT", "plate.nB", "bolt.d"): v = int(v)
        else: v = f["var"].get()
        setp(self.S, sp["p"], v)
        SE.normalize(self.S)
        if structural: self._refresh_visibility()
        if sp["p"].endswith(".sec") or sp["p"] == "beam2.same": self._update_info()
        self.schedule()

    def _refresh_visibility(self):
        for f in self.fields:
            show = f["spec"].get("show")
            vis = True
            if show:
                try: vis = bool(show())
                except Exception: vis = True
            if vis: f["cell"].grid(**f["grid"])
            else: f["cell"].grid_remove()

    def _update_info(self):
        for f in self.fields:
            if f["spec"]["k"] != "info": continue
            m = getp(self.S, f["spec"]["p"].rsplit(".", 1)[0])
            try:
                mm = K.member_at_joint(dict(m, topIsOuter=True), "")
                fl = (f"{mm['bfE']:g}×{mm['tfE']:g}" if (mm['bfE'], mm['tfE']) == (mm['bfI'], mm['tfI'])
                      else f"trên {mm['bfE']:g}×{mm['tfE']:g} / dưới {mm['bfI']:g}×{mm['tfI']:g}")
                f["lbl"].configure(text=f"✓ Tại mặt nối: d = {mm['d']:.1f}, bụng {mm['hw']:.1f}×{mm['tw']:g}, cánh {fl}"
                                        + (f" · vát {mm['beta']:.1f}°" if mm["beta"] > 1e-6 else ""), text_color=OK_C)
            except (knee_section.SectionError, ValueError) as e:
                f["lbl"].configure(text="✗ " + str(e), text_color=BAD_C)

    # ───────────────────────── Tính ─────────────────────────
    def schedule(self):
        if self._job: self.after_cancel(self._job)
        self._job = self.after(250, self.run)

    def run(self):
        self._job = None
        try:
            self.R = SE.compute(self.S); err = None
        except Exception as e:  # noqa: BLE001 — hiển thị mọi lỗi nhập liệu
            self.R = None; err = str(e)
        self._render(err)

    def _render(self, err=None):
        names = [l.get("name", f"TH{i + 1}") for i, l in enumerate(self.S["loads"])] or ["—"]
        if self.combo_idx >= len(names): self.combo_idx = 0
        self.opt_combo.configure(values=[f"{i + 1}. {n}" for i, n in enumerate(names)])
        self.opt_combo.set(f"{self.combo_idx + 1}. {names[self.combo_idx]}")
        self.tree.delete(*self.tree.get_children())
        if err or not self.R:
            self.lbl_status.configure(text="⛔ LỖI", text_color=BAD_C)
            self.lbl_ratio.configure(text="")
            self.lbl_gov.configure(text=err or "")
            self.lbl_kv.configure(text="")
            self.canvas.show(None)
            self._render_cards()
            return
        R = self.R
        g = R["gov"]; r = g["ratio"] if g else 0.0
        ok = r <= 1.0001 and R["geoFail"] == 0
        self.lbl_status.configure(text="✔ ĐẠT" if ok else "✘ KHÔNG ĐẠT", text_color=OK_C if ok else BAD_C)
        self.lbl_ratio.configure(text="∞" if math.isinf(r) else f"{r:.2f}", text_color=rc(r))
        self.bar_ratio.configure(progress_color=rc(r)); self.bar_ratio.set(min(r, 1.0))
        self.lbl_gov.configure(text=(f"Khống chế: {g['name']} — {g['grp']} ({g['combo']})" if g else "")
                               + (f"\n{R['geoFail']} kiểm tra cấu tạo không đạt" if R["geoFail"] else "")
                               + (f"\n⚠ {len(R['W'])} cảnh báo — xem tab Cấu tạo & cảnh báo" if R["W"] else ""))
        G = R["G"]
        sd = lambda s: ("lỗi" if "error" in s else f"{s['cfg']} · " + ("bản dày" if all(p['thick'] for p in s['plates']) else "bản mỏng"))
        pl = self.S["plate"]
        self.lbl_kv.configure(text=(f"Cánh trên : {sd(R['sides']['T'])}\nCánh dưới : {sd(R['sides']['B'])}\n"
                                    f"Chiều cao dọc bản d = {G['dp']:.1f} · dm = {G['dm']:.1f} mm" + (f" · Apex {G['alpha']:g}°" if G['type'] == 'apex' else "") + "\n"
                                    f"Bản đầu    : {G['bp']:.0f}×{pl['tp1']:g}/{pl['tp2']:g}×{G['sBot'] - G['sTop']:.0f}  ·  {R['bolt']['bg']['label']} M{R['bolt']['db']}"))
        self._render_cards()
        self._render_report()
        n = max(len(self.S["loads"]), 1)
        self.slider.configure(to=max(n - 1, 1), number_of_steps=max(n - 1, 1))
        self.slider.set(self.combo_idx)
        groups = {}
        for c in R["checks"]:
            groups.setdefault(c["grp"], []).append(c)
        for gname, lst in groups.items():
            worst = max((c["ratio"] for c in lst if not c["info"]), default=0.0)
            pid = self.tree.insert("", "end", text=gname, values=(f"{worst:.2f}", "", "", "", "", ""), open=True, tags=("grp",))
            for c in lst:
                tag = "info" if c["info"] else ("bad" if c["ratio"] > 1.0001 else "warn" if c["ratio"] > 0.9 else "ok")
                cap = "—" if K.isnan(c["cap"]) else f"{c['cap']:.2f}"
                self.tree.insert(pid, "end", iid=c["id"], text="  " + c["name"],
                                 values=("∞" if math.isinf(c["ratio"]) else f"{c['ratio']:.2f}", cap, f"{c['dem']:.2f}", c["unit"], c["combo"], c["ref"]), tags=(tag,))
        if self.sel_check and self.tree.exists(self.sel_check):
            self.tree.selection_set(self.sel_check); self.tree.see(self.sel_check)
        else:
            self.sel_check = None; self._show_detail(None)
        self.tree_dem.delete(*self.tree_dem.get_children())
        for d in R["demands"]:
            self.tree_dem.insert("", "end", values=(d["name"], f"{d['V']:.2f}", f"{d['N']:.2f}", f"{d['M']:.2f}", f"{d['Nn']:.2f}", f"{d['Vt']:.2f}",
                                                    f"{d['FnT']:.2f}", f"{d['FnB']:.2f}", f"{d['Mu']:.2f}",
                                                    {"T": "Cánh trên", "B": "Cánh dưới"}.get(d["side"], "—")))
        self.tree_geo.delete(*self.tree_geo.get_children())
        for w in R["W"]:
            self.tree_geo.insert("", "end", values=("⚠ Cảnh báo", w, "", "", "", "", ""), tags=("warn",))
        for x in R["geo"]:
            self.tree_geo.insert("", "end", values=(x["grp"], x["name"], f"{x['val']:.2f}", "—" if x["min"] is None else f"{x['min']:.2f}",
                                                    "—" if x["max"] is None else f"{x['max']:.2f}", "✔" if x["ok"] else "✘", x["ref"]),
                                 tags=(() if x["ok"] else ("bad",)))
        self._draw()

    def _heat_map(self):
        """D/C của từng bộ phận cho tổ hợp đang xem (tính riêng tổ hợp đó)."""
        if not self.var_heat.get() or not self.S["loads"]:
            return None
        key = json.dumps(self.S, sort_keys=True, default=str) + f"|{self.combo_idx}"
        if getattr(self, "_heat_key", None) == key:
            return self._heat_val
        st = dict(self.S); st["loads"] = [self.S["loads"][self.combo_idx]]
        heat = {}
        try:
            r = SE.compute(copy.deepcopy(st))
            for c in r["checks"]:
                if c["info"]: continue
                for t in c["tags"]:
                    heat[t] = max(heat.get(t, 0.0), c["ratio"])
        except Exception:  # noqa: BLE001
            heat = {}
        self._heat_key, self._heat_val = key, heat
        return heat

    def _tip_text(self, tags):
        if not self.R: return ""
        lst = [c for c in self.R["checks"] if set(c["tags"]) & tags and not c["info"]]
        if not lst: return ""
        lst.sort(key=lambda c: -c["ratio"])
        head = " · ".join(sorted({TAG_NAME.get(t, t) for t in tags}))
        lines = [head, "─" * min(len(head) + 2, 46)]
        for c in lst[:7]:
            lines.append(f"{'∞' if math.isinf(c['ratio']) else format(c['ratio'], '.2f'):>5}  {c['name'][:40]}  ({c['combo'][:16]})")
        return "\n".join(lines)

    def _draw(self):
        if not self.R: return
        dem = self.R["demands"][self.combo_idx] if self.R["demands"] else None
        c = next((x for x in self.R["checks"] if x["id"] == self.sel_check), None)
        heat = self._heat_map()
        sc = elevation(self.S, self.R, dem, flow=self.var_flow.get()) if self.view == "elev" else plate_face(self.S, self.R, dem)
        self.canvas.show(sc, c["tags"] if c else (), heat)
        names = [l.get("name", "") for l in self.S["loads"]]
        if names:
            self.lbl_combo.configure(text=f"{self.combo_idx + 1}/{len(names)} · {names[self.combo_idx][:18]}")
        if dem:
            self.lbl_draw.configure(text=f"{dem['name']}:  M = {dem['M']:.1f} kN·m · N = {dem['N']:.1f} kN · V = {dem['V']:.1f} kN  →  kéo "
                                         + {"T": "cánh trên", "B": "cánh dưới"}.get(dem["side"], "—"))

    def _check_selected(self, _e=None):
        s = self.tree.selection()
        cid = s[0] if s else None
        c = next((x for x in (self.R or {}).get("checks", []) if x["id"] == cid), None)
        self.sel_check = cid if c else None
        self._show_detail(c)
        if c:
            names = [l.get("name") for l in self.S["loads"]]
            if c["combo"] in names and names.index(c["combo"]) != self.combo_idx:
                self.combo_idx = names.index(c["combo"])
                self.opt_combo.set(f"{self.combo_idx + 1}. {c['combo']}")
            self._draw()
        else:
            self.canvas.set_highlight(())

    def _show_detail(self, c):
        self.txt_detail.configure(state="normal"); self.txt_detail.delete("1.0", "end")
        if c:
            self.txt_detail.insert("end", f"{c['name']}  —  {c['ref']}\n", ("h",))
            self.txt_detail.insert("end", f"Khả năng = {c['cap']:.2f} {c['unit']};  Yêu cầu = {c['dem']:.2f} {c['unit']};  D/C = {c['ratio']:.3f}  ({c['combo']})\n\n")
            self.txt_detail.insert("end", "\n".join(c["detail"]))
            self.txt_detail.tag_configure("h", font=("Consolas", 10, "bold"), foreground=ACCENT)
        else:
            self.txt_detail.insert("end", "Chọn một dòng kiểm tra để xem diễn giải công thức từng bước và tô sáng bộ phận trên hình.")
        self.txt_detail.configure(state="disabled")

    def _type_changed(self, lab):
        self.S["type"] = TYPE_KEY[lab]
        if self.S["type"] == "apex" and not float(self.S.get("slope") or 0):
            self.S["slope"] = 10.0
        self.sel_check = None
        self._load_form(); self.run()

    def _view_changed(self, lab):
        self.view = {"Mặt đứng": "elev", "Mặt bản đầu": "face"}[lab]
        self._draw()

    def _slider(self, v):
        i = int(round(float(v)))
        if i != self.combo_idx and 0 <= i < len(self.S["loads"]):
            self.combo_idx = i
            self.opt_combo.set(f"{i + 1}. {self.S['loads'][i].get('name', '')}")
            self._draw()

    def _play(self):
        self._playing = not self._playing
        self.btn_play.configure(text="⏸" if self._playing else "▶")
        if self._playing: self._play_step()

    def _play_step(self):
        if not self._playing or not self.S["loads"]: return
        self.combo_idx = (self.combo_idx + 1) % len(self.S["loads"])
        self.opt_combo.set(f"{self.combo_idx + 1}. {self.S['loads'][self.combo_idx].get('name', '')}")
        self.slider.set(self.combo_idx)
        self._draw()
        self.after(1300, self._play_step)

    # ───────────────────────── thẻ đồng hồ ─────────────────────────
    def _cat_checks(self, name):
        pref = dict(CATS)[name]
        return [c for c in (self.R or {}).get("checks", []) if not c["info"] and c["id"].startswith(pref)]

    def _render_cards(self):
        for name, cv in self.cards.items():
            cv.delete("all")
            lst = self._cat_checks(name)
            W = max(cv.winfo_width(), 108)
            cx, cy, r = W / 2, 44, 26
            cv.create_arc(cx - r, cy - r, cx + r, cy + r, start=-30, extent=240, style="arc", width=7, outline="#E6EBF1")
            if lst:
                w = max(lst, key=lambda c: c["ratio"]); v = w["ratio"]
                ext = 240 * min(v, 1.2) / 1.2
                cv.create_arc(cx - r, cy - r, cx + r, cy + r, start=210 - ext, extent=ext, style="arc", width=7, outline=heat_color(v))
                cv.create_text(cx, cy + 2, text="∞" if math.isinf(v) else f"{v:.2f}", font=("Consolas", 12, "bold"), fill=heat_color(v))
            else:
                cv.create_text(cx, cy + 2, text="—", font=("Consolas", 12, "bold"), fill="#9AA5B1")
            cv.create_text(cx, 9, text=name, font=("Segoe UI", 9, "bold"), fill="#3B4656")

    def _card_click(self, name):
        lst = self._cat_checks(name)
        if not lst: return
        w = max(lst, key=lambda c: c["ratio"])
        if self.tree.exists(w["id"]):
            self.tree.selection_set(w["id"]); self.tree.see(w["id"])

    def _combo_changed(self, lab):
        try: self.combo_idx = int(lab.split(".", 1)[0]) - 1
        except ValueError: self.combo_idx = 0
        self._draw()

    def _preset(self, name):
        self.S = merge(BASE, PRESETS[name]); self.sel_check = None; self.combo_idx = 0
        self.opt_preset.set("Nạp mẫu…"); self._load_form(); self.run()
        self.status.set_text(f"Đã nạp mẫu: {name}")

    def _auto(self):
        self.status.set_text("Đang thử các phương án tp / bu lông…"); self.update_idletasks()
        res = SE.auto_design(self.S)
        if not res:
            messagebox.showwarning("Tự chọn", "Không tính được phương án nào — kiểm tra lại số liệu."); return
        self.S["plate"]["tp1"] = self.S["plate"]["tp2"] = res["tp"]; self.S["bolt"]["d"] = res["d"]
        self._load_form(); self.run()
        msg = f"tp = {res['tp']} mm (cả hai bản), bu lông M{res['d']} — D/C (bản, bu lông) = {res['ratio']:.2f}"
        if res.get("fail"):
            messagebox.showwarning("Tự chọn", "Không có phương án đạt trong dải thử (tp ≤ 40, ≤ M30).\nPhương án tốt nhất: " + msg)
        self.status.set_text("Tự chọn: " + msg)

    # ───────────────────────── Loads (bảng như hộp thoại Loads của RAM Connection) ─────────────────────────
    LOAD_COLS = [("id", "ID", 40), ("name", "Description", 200), ("N", "Axial [kN]", 110), ("V", "V2 [kN]", 110), ("M", "M3 [kN*m]", 120)]
    LOAD_GROUPS = [("Load", 2), ("Forces at the splice", 3)]

    def _build_loads_tab(self, tab):
        bar = ctk.CTkFrame(tab, fg_color="transparent"); bar.pack(fill="x")
        for t, cmd in (("+ Add", self._load_add), ("− Delete", self._load_del), ("📋 Paste from Excel", self._load_paste), ("Clear", self._load_clear)):
            ctk.CTkButton(bar, text=t, width=120, height=26, command=cmd).pack(side="left", padx=3, pady=3)
        ctk.CTkLabel(bar, text="kN, kN·m · Axial > 0 kéo · M3 > 0 → cánh DƯỚI chịu kéo, M3 < 0 → cánh TRÊN chịu kéo · nhấp đúp để sửa · Dán: Description, Axial, V2, M3",
                     font=("Segoe UI", 10), text_color="gray").pack(side="left", padx=8)
        band = tk.Canvas(tab, height=22, highlightthickness=0, background="#3B4A5E")
        band.pack(fill="x")
        x = 0; i = 0
        for title, ncol in self.LOAD_GROUPS:
            w = sum(c[2] for c in self.LOAD_COLS[i:i + ncol]); i += ncol
            band.create_rectangle(x, 0, x + w, 22, outline="#6B7A90", fill="#3B4A5E")
            band.create_text(x + w / 2, 11, text=title, fill="#FFFFFF", font=("Segoe UI", 10, "bold"))
            x += w
        fr = ttk.Frame(tab); fr.pack(fill="both", expand=True)
        tv = ttk.Treeview(fr, columns=[c[0] for c in self.LOAD_COLS], show="headings", style="K.Treeview", height=6)
        for c, h, w in self.LOAD_COLS:
            tv.heading(c, text=h); tv.column(c, width=w, minwidth=w, stretch=False, anchor="w" if c == "name" else "e")
        sb = ttk.Scrollbar(fr, orient="vertical", command=tv.yview); tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        tv.tag_configure("odd", background="#F6F8FB")
        self.tree_load = tv
        tv.bind("<Double-1>", self._load_edit)

    def _fill_loads(self):
        tv = self.tree_load
        tv.delete(*tv.get_children())
        for i, l in enumerate(self.S["loads"]):
            vals = [i + 1] + [(f"{l.get(k, ''):g}" if isinstance(l.get(k, ""), (int, float)) else l.get(k, "")) for k, _, _ in self.LOAD_COLS[1:]]
            tv.insert("", "end", iid=str(i), values=vals, tags=("odd",) if i % 2 else ())

    def _load_edit(self, e):
        tv = self.tree_load
        row, col = tv.identify_row(e.y), tv.identify_column(e.x)
        if not row: return
        ci = int(col[1:]) - 1
        key = self.LOAD_COLS[ci][0]
        if key == "id": return
        x, y, w, h = tv.bbox(row, col)
        ent = tk.Entry(tv, font=("Segoe UI", 10), justify="left" if key == "name" else "right")
        ent.insert(0, str(self.S["loads"][int(row)].get(key, "")))
        ent.place(x=x, y=y, width=w, height=h); ent.focus_set(); ent.select_range(0, "end")

        def done(_e=None, save=True):
            if save:
                v = ent.get()
                if key != "name":
                    try: v = float(v.replace(",", "."))
                    except ValueError: v = 0.0
                self.S["loads"][int(row)][key] = v
                self._fill_loads(); self.schedule()
            ent.destroy()
        ent.bind("<Return>", done); ent.bind("<FocusOut>", done); ent.bind("<Escape>", lambda _e: done(save=False))

    def _load_add(self):
        self.S["loads"].append(dict(name=f"LC{len(self.S['loads']) + 1}", N=0, V=0, M=0))
        self._fill_loads(); self.schedule()

    def _load_del(self):
        for iid in sorted((int(i) for i in self.tree_load.selection()), reverse=True):
            del self.S["loads"][iid]
        self._fill_loads(); self.schedule()

    def _load_clear(self):
        if messagebox.askyesno("Clear", "Xoá toàn bộ tổ hợp tải?"):
            self.S["loads"] = []; self._fill_loads(); self.schedule()

    def _load_paste(self):
        """Dán theo thứ tự cột RAM: Description, Axial, V2, M3 (cột ID đầu dòng, nếu có, tự bỏ qua)."""
        try: raw = self.clipboard_get()
        except tk.TclError: raw = ""
        rows = []
        for line in raw.strip().splitlines():
            p = [x.strip() for x in line.replace(";", "\t").split("\t")]
            if p and p[0].isdigit() and len(p) > 4: p = p[1:]
            vals = []
            for x in p[1:]:
                try: vals.append(float(x.replace(",", ".")))
                except ValueError: vals.append(None)
            if len(vals) < 3 or any(v is None for v in vals[:3]): continue
            rows.append(dict(name=p[0] or f"LC{len(rows) + 1}", N=vals[0], V=vals[1], M=vals[2]))
        if not rows:
            messagebox.showinfo("Paste", "Clipboard không có dữ liệu hợp lệ (cần: Description, Axial, V2, M3)."); return
        self.S["loads"] += rows; self._fill_loads(); self.schedule()
        self.status.set_text(f"Đã dán {len(rows)} tổ hợp.")

    # ───────────────────────── Report (form RAM Connection) + xuất ─────────────────────────
    def _build_report_tab(self, tab):
        bar = ctk.CTkFrame(tab, fg_color="transparent"); bar.pack(fill="x")
        ctk.CTkButton(bar, text="📄 Export report (.docx)", width=170, height=26, command=self._export_docx).pack(side="left", padx=3, pady=3)
        fr = ttk.Frame(tab); fr.pack(fill="both", expand=True)
        self.txt_rep = tk.Text(fr, font=("Consolas", 10), wrap="none", background="#FFFFFF", relief="flat", padx=10, pady=8)
        sy = ttk.Scrollbar(fr, orient="vertical", command=self.txt_rep.yview); sx = ttk.Scrollbar(fr, orient="horizontal", command=self.txt_rep.xview)
        self.txt_rep.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        sy.pack(side="right", fill="y"); sx.pack(side="bottom", fill="x"); self.txt_rep.pack(side="left", fill="both", expand=True)
        t = self.txt_rep
        t.tag_configure("h1", font=("Segoe UI", 15, "bold"), foreground="#2E7D32")
        t.tag_configure("h2", font=("Segoe UI", 11, "bold"), foreground="#18212F", spacing1=4)
        t.tag_configure("grp", font=("Consolas", 10, "bold"), background="#D9DEE5")
        t.tag_configure("sub", font=("Consolas", 10, "bold", "underline"))
        t.tag_configure("bad", foreground=BAD_C); t.tag_configure("ok", foreground=OK_C, font=("Segoe UI", 12, "bold"))
        t.tag_configure("dim", foreground="#7B8794")

    def _render_report(self):
        t = self.txt_rep
        t.configure(state="normal"); t.delete("1.0", "end")
        if self.R:
            self._rep = RP.build(self.S, self.R)
            for text, tag in RP.to_text(self._rep):
                t.insert("end", text, (tag,))
        t.configure(state="disabled")

    def _export_docx(self):
        if not self.R: return
        path = filedialog.asksaveasfilename(title="Export report", defaultextension=".docx", filetypes=[("Word", "*.docx")],
                                            initialfile=f"{self.S.get('name', 'splice')}_report.docx".replace(":", "-").replace("/", "-"))
        if not path: return
        try:
            RP.to_docx(RP.build(self.S, self.R), path)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Export report", str(e)); return
        self.status.set_text(f"Đã xuất báo cáo: {path}")

    # ───────────────────────── Danh sách đã lưu ─────────────────────────
    def _build_saved_tab(self, tab):
        bar = ctk.CTkFrame(tab, fg_color="transparent"); bar.pack(fill="x")
        for t, cmd, col in (("💾 Lưu mới", self._save_new, "#059669"), ("↻ Ghi đè", self._save_over, None), ("📂 Mở", self._saved_open, None),
                            ("✎ Đổi tên", self._saved_rename, None), ("✕ Xoá", self._saved_delete, "#B91C1C"),
                            ("▲ Lên", lambda: self._saved_move(-1), None), ("▼ Xuống", lambda: self._saved_move(1), None)):
            kw = dict(fg_color=col) if col else {}
            ctk.CTkButton(bar, text=t, width=96, height=26, command=cmd, **kw).pack(side="left", padx=3, pady=3)
        cols = [("stt", "STT", 45), ("name", "Tên", 240), ("type", "Kiểu", 90), ("b1", "Dầm 1", 190), ("b2", "Dầm 2", 190),
                ("plate", "Bản", 110), ("bolt", "Bu lông", 110), ("nl", "Số TH", 60), ("dc", "D/C", 60), ("time", "Cập nhật", 130)]
        self.tree_saved = self._mk_table(tab, cols, height=6)
        self.tree_saved.bind("<Double-1>", lambda _e: self._saved_open())
        for tag, c in (("ok", OK_C), ("bad", BAD_C)):
            self.tree_saved.tag_configure(tag, foreground=c)
        self._fill_saved()

    def _summary_of(self, st):
        try:
            r = SE.compute(copy.deepcopy(st)); dc = r["gov"]["ratio"] if r["gov"] else 0.0; ok = dc <= 1.0001 and r["geoFail"] == 0
        except Exception:  # noqa: BLE001
            dc, ok = float("nan"), False
        return dict(type=st["type"], b1=st["beam1"]["sec"], b2=st["beam2"]["sec"], tp=f"{st['plate']['tp1']:g}/{st['plate']['tp2']:g}",
                    bolt=f"M{st['bolt']['d']} {st['bolt']['grade']}", nl=len(st["loads"]), dc=dc, ok=ok)

    def _fill_saved(self, select=None):
        tv = self.tree_saved
        tv.delete(*tv.get_children())
        for i, it in enumerate(self.saved.items):
            s = it.get("summary", {})
            dc = s.get("dc", float("nan"))
            tv.insert("", "end", iid=str(i), tags=("ok" if s.get("ok") else "bad",),
                      values=(i + 1, it["name"], TYPE_LABEL.get(s.get("type"), ""), s.get("b1", ""), s.get("b2", ""),
                              f"tp {s.get('tp', '')}", s.get("bolt", ""), s.get("nl", ""), "—" if dc != dc else f"{dc:.2f}", it.get("time", "")))
        if select is not None and 0 <= select < len(self.saved.items):
            tv.selection_set(str(select)); tv.see(str(select))

    def _saved_idx(self):
        s = self.tree_saved.selection()
        if not s:
            messagebox.showinfo("Danh sách", "Chọn một dòng trong danh sách đã lưu."); return None
        return int(s[0])

    def _save_new(self):
        name = ctk.CTkInputDialog(text="Tên liên kết / nhóm:", title="Lưu vào danh sách").get_input()
        if not name: return
        self.S["name"] = name
        i = self.saved.add(name, self.S, self._summary_of(self.S))
        self._load_form(); self._fill_saved(i); self.tabs.set("Danh sách đã lưu")
        self.status.set_text(f"Đã lưu '{name}'.")

    def _save_over(self):
        i = self._saved_idx()
        if i is None: return
        if messagebox.askyesno("Ghi đè", f"Ghi đè '{self.saved.items[i]['name']}' bằng thông số hiện tại?"):
            st = copy.deepcopy(self.S); st["name"] = self.saved.items[i]["name"]
            self.saved.update(i, st, self._summary_of(st)); self._fill_saved(i)

    def _saved_open(self):
        i = self._saved_idx()
        if i is None: return
        self.S = merge(BASE, self.saved.items[i]["state"]); self.sel_check = None; self.combo_idx = 0
        self._load_form(); self.run()
        self.status.set_text(f"Đã mở '{self.saved.items[i]['name']}'.")

    def _saved_rename(self):
        i = self._saved_idx()
        if i is None: return
        name = ctk.CTkInputDialog(text=f"Tên mới cho '{self.saved.items[i]['name']}':", title="Đổi tên").get_input()
        if name:
            self.saved.rename(i, name); self._fill_saved(i)

    def _saved_delete(self):
        i = self._saved_idx()
        if i is None: return
        if messagebox.askyesno("Xoá", f"Xoá '{self.saved.items[i]['name']}' khỏi danh sách?"):
            self.saved.delete(i); self._fill_saved(min(i, len(self.saved.items) - 1))

    def _saved_move(self, step):
        i = self._saved_idx()
        if i is None: return
        self._fill_saved(self.saved.move(i, step))


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
