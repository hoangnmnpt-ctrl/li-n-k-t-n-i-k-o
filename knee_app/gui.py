"""
gui.py — KNEE KÈO AISC 360-10 LRFD (customtkinter)
=================================================
  • Quét SAP2000 → tìm knee (đỉnh cột ↔ đầu kèo), lấy 9 cực trị của CẢ cột và kèo tại đầu nút,
    ghép theo cùng tổ hợp, gom nhóm knee giống nhau → nạp vào thiết kế.
  • Thiết kế knee đứng (bản 90°) / ngang / xiên (bản ⟂ kèo): form thông số, hình knee động,
    bảng kiểm tra D/C, diễn giải công thức từng bước, tự chọn tp & bu lông.
  • Danh sách đã lưu: lưu tên + thông số, mở lại, ghi đè, đổi tên, xoá, dời lên / xuống.
LƯU Ý: gọi COM SAP2000 trên main thread (STA) như tool Lấy nội lực.
"""

from __future__ import annotations

import copy
import math
import os
import sys
import tkinter as tk
from tkinter import messagebox, ttk

import customtkinter as ctk

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import engine as K  # noqa: E402
import scanner  # noqa: E402  (thêm đường dẫn "Lấy nội lực" vào sys.path)
from defaults import BASE, PRESETS, merge  # noqa: E402
from drawing import KneeCanvas, elevation, heat_color, plate_face  # noqa: E402
from view3d import Knee3D  # noqa: E402
import json  # noqa: E402
import ram_export  # noqa: E402
import report as RP  # noqa: E402
from tkinter import filedialog  # noqa: E402
from knee_section import SectionError, parse_section  # noqa: E402
from store import SavedList  # noqa: E402

from gui_widgets import LoadSourcePicker, StatusBar  # noqa: E402  (từ Lấy nội lực)
from sap2000_connector import (  # noqa: E402
    LOAD_CASES, LOAD_CASES_AND_DESIGN, LOAD_COMBOS, LOAD_DESIGN_COMBOS, SAP2000Connector, default_selected_loads,
)

APP_TITLE = "KNEE KÈO — AISC 360-10 LRFD · DG4 / DG16 / DG39"
SOURCE_MENU = {"Design Combos": LOAD_DESIGN_COMBOS, "Load Cases": LOAD_CASES,
               "Cases + Design": LOAD_CASES_AND_DESIGN, "Combos (tất cả)": LOAD_COMBOS}
TYPE_LABEL = {"dung": "Knee đứng", "ngang": "Knee ngang", "xien": "Knee xiên"}
TYPE_KEY = {v: k for k, v in TYPE_LABEL.items()}
MATS = list(K.MATERIALS)
COND_OPTS = [(k, v) for k, v in K.COND_LABEL.items() if k != "endplate"] + [("endplate", K.COND_LABEL["endplate"])]
FONT = ("Segoe UI", 12)
FONT_S = ("Segoe UI", 11)
FONT_B = ("Segoe UI", 12, "bold")
OK_C, WARN_C, BAD_C = "#1A9E5A", "#D99A00", "#D23B3B"


LOCKABLE = {"beam.sec", "beam.L", "beam.jointEnd", "beam.slope", "beam.topIsOuter",
            "col.sec", "col.L", "col.jointEnd", "col.topIsOuter"}
CATS = [("Bản đầu", ("pl_",)), ("Bu lông", ("bolt_", "bear_p")), ("Phía gối", ("sup_", "bear_s")),
        ("Panel · J10", ("pz", "j10")), ("Sườn", ("st_",)), ("Hàn", ("m1_wf", "m1_ww", "m2_wf", "m2_ww")),
        ("Cấu kiện", ("m1_wv", "m2_wv"))]
TAG_NAME = {"plate": "Bản đầu", "boltsE": "Bu lông nhóm cánh ngoài", "boltsI": "Bu lông nhóm cánh trong",
            "supportE": "Bản gối — cánh ngoài", "supportI": "Bản gối — cánh trong", "panel": "Panel zone",
            "supEweb": "Bụng panel/gối", "supIweb": "Bụng panel/gối", "supEstiff": "Sườn gối cánh ngoài",
            "supIstiff": "Sườn gối cánh trong", "m1weldE": "Hàn cánh ngoài", "m1weldI": "Hàn cánh trong",
            "m1webweld": "Hàn bụng", "m1web": "Bụng cấu kiện có bản"}


def rc(r):
    return BAD_C if r > 1.0001 else WARN_C if r > 0.9 else OK_C


# ─────────────────────────── Khai báo form ───────────────────────────
def num(p, l, u="mm", show=None, w2=False): return dict(k="num", p=p, l=l, u=u, show=show, w2=w2)
def txt(p, l, show=None, w2=True): return dict(k="txt", p=p, l=l, show=show, w2=w2)
def sel(p, l, opts, show=None, w2=False): return dict(k="sel", p=p, l=l, opts=[o if isinstance(o, tuple) else (o, str(o)) for o in opts], show=show, w2=w2)
def chk(p, l, show=None): return dict(k="chk", p=p, l=l, show=show, w2=True)
def sub(l, show=None): return dict(k="sub", l=l, show=show, w2=True)
def info(p): return dict(k="info", p=p, w2=True, show=None)
def lockbar(): return dict(k="lock", w2=True, show=None)
def btn(l, cmd): return dict(k="btn", l=l, cmd=cmd, w2=True, show=None)
def tip(spec, text):
    spec["tip"] = text
    return spec


def build_sections(app):
    """Form nhập theo đúng thứ tự & nhãn của RAM Connection (Knee moment end plate — BCF)."""
    S = lambda: app.S
    ext = lambda *v: S()["plate"].get("extension") in v
    ELEC = list(K.ELECTRODES)
    WT = [("fillet", "Fillet"), ("cjp", "CJP")]
    return [
        ("General information", True, [
            sub("Analysis"),
            btn("Loads   <Loads>  →  mở bảng tải", lambda: app.tabs.set("Loads")),
            sub("Design criteria"),
            tip(sel("gen.designCode", "Design code", ["AISC 2010 LRFD", "AISC 2016 LRFD"], w2=True), "Tiêu chuẩn thiết kế (tính theo LRFD)"),
            tip(chk("gen.frameStab", "Frame stability considered in analysis"), "Đã xét ổn định khung trong phân tích (chỉ truyền sang RAM)"),
            sub("Construction criteria"),
            tip(chk("opt.holeDef", "Consider hole deformation in bolts"), "Xét biến dạng lỗ khi tính ép mặt (J3-6a: 1.2/2.4; bỏ chọn: 1.5/3.0)"),
            tip(chk("bolt.snug", "Snug-tight bolted"), "Bu lông siết sơ bộ → giảm Tb khi tính lực nhổ"),
            tip(chk("opt.sheared", "Consider sheared edges"), "Mép bản cắt bằng cưa/đột → khoảng cách mép tối thiểu lớn hơn"),
        ]),
        ("Members", True, [
            sub("Configuration"),
            dict(k="note", l="Exists opposite connection:  No (knee)", w2=True, show=None),
            sub("Beam"),
            lockbar(),
            tip(txt("beam.sec", "Beam section"), "Tiết diện kèo — quy cách (580-380).6-200.10 hoặc 600.5-150.8"), info("beam.sec"),
            sel("beam.mat", "Beam material", MATS), tip(num("beam.L", "Beam length", "m"), "Chiều dài kèo"),
            tip(num("beam.slope", "Vertical angle (deg)", "°"), "Góc dốc kèo so với phương ngang"),
            sel("beam.jointEnd", "Joint end (SAP)", [("I", "End I"), ("J", "End J")]),
            tip(chk("beam.flangeStiff.on", "Include flange stiffener"), "Sườn cánh kèo (chỉ truyền sang RAM, không đưa vào tính)"),
            num("beam.flangeStiff.t", "Thickness for flange stiffener", show=lambda: S()["beam"]["flangeStiff"]["on"], w2=True),
            tip(chk("beam.topIsOuter", "Top flange (+2) is the EXTERNAL flange"), "Cánh trên (mặt +2 SAP) là cánh ngoài"),
            sub("Support"),
            tip(txt("col.sec", "Support section"), "Tiết diện cột"), info("col.sec"),
            sel("col.mat", "Support material", MATS), num("col.L", "Support length", "m"),
            sel("col.jointEnd", "Joint end (SAP)", [("J", "End J (top)"), ("I", "End I")]),
            chk("col.topIsOuter", "Top flange (+2) is the EXTERNAL flange"),
        ]),
        ("Moment end plate", True, [
            sub("Connector"),
            tip(sel("plate.extension", "Plate extension", [("flush", "Flush"), ("external", "Extended external edge"),
                                                          ("internal", "Extended internal edge"), ("both", "Extended both edges")], w2=True),
                "Bản nhô ra ngoài cánh ngoài / cánh trong / cả hai"),
            num("plate.tp", "tp: Plate thickness"), sel("plate.mat", "Plate material", MATS),
            sel("plate.holeType", "Hole type on plate", ["STD"]), tip(num("plate.flushExt", "Flush extension length"), "Phần bản thừa phía không nhô"),
            tip(sel("plate.alignment", "Plate alignment", [("vertical", "Vertical alignment"), ("perpendicular", "Perpendicular to beam"),
                                                          ("horizontal", "Horizontal alignment"), ("bisector", "Bisector (tool only)")], w2=True),
                "Vertical = knee đứng (bản 90°) · Perpendicular = knee xiên (bản ⟂ kèo) · Horizontal = knee ngang"),
            sub("Weld"),
            sel("weld.flE.type", "External flange weld type", WT), sel("weld.flE.electrode", "Weld to external flange", ELEC),
            tip(num("weld.flE.D", "D1: Weld size to external flange (1/16in)", "/16", show=lambda: S()["weld"]["flE"]["type"] == "fillet", w2=True), "Cỡ hàn theo 1/16 inch (8 → 12.7 mm)"),
            sel("weld.flI.type", "Internal flange weld type", WT), sel("weld.flI.electrode", "Weld to internal flange", ELEC),
            num("weld.flI.D", "D3: Weld size to internal flange (1/16in)", "/16", show=lambda: S()["weld"]["flI"]["type"] == "fillet", w2=True),
            sel("weld.web.electrode", "Web weld", ELEC), num("weld.web.D", "D2: Weld size to web (1/16in)", "/16"),
            sub("Bolts"),
            tip(num("sup.t", "tp: Connection plate thickness"), "Bề dày bản gối phía cột (connection plate)"),
            sel("bolt.d", "Bolts — diameter", [(d, f"M{d}") for d in K.BOLT_DIAS]),
            sel("bolt.grade", "Bolts — grade", [("8.8", "G_8_8"), ("10.9", "G_10_9"), ("A325", "A325M"), ("A490", "A490M")]),
            sel("bolt.thread", "Threads", [("N", "N — included"), ("X", "X — excluded")]),
            tip(num("plate.g", "g: Gage - transverse center-to-center spacing", w2=True), "Khoảng cách 2 dãy bu lông"),
            sel("bolt.holeType", "Hole type", ["STD"]), dict(k="note", l="", show=None),
            num("plate.Lev", "Lev: Vertical edge distance"), num("plate.Leh", "Leh: Horizontal edge distance"),
            sub("Bolt group (external extension)", show=lambda: ext("external", "both")),
            num("plate.pfoE", "pfo t: Distance from bolt rows to flange", show=lambda: ext("external", "both"), w2=True),
            sub("Bolt group (external flange)"),
            sel("plate.nE", "Bolts rows number", [1, 2, 3]), num("plate.pfiE", "pfi t: Distance from bolt rows to flange"),
            num("plate.pbE", "s t: Vertical spacing between inner bolt rows", show=lambda: int(S()["plate"]["nE"]) > 1, w2=True),
            sub("Bolt group (internal flange)"),
            sel("plate.nI", "Bolts rows number", [1, 2, 3]), num("plate.pfiI", "pfi b: Distance from bolt rows to flange"),
            num("plate.pbI", "s b: Vertical spacing between inner bolt rows", show=lambda: int(S()["plate"]["nI"]) > 1, w2=True),
            sub("Bolt group (internal extension)", show=lambda: ext("internal", "both")),
            num("plate.pfoI", "pfo b: Distance from bolt rows to flange", show=lambda: ext("internal", "both"), w2=True),
        ]),
        ("Stiffeners", True, [
            sub("Transverse stiffeners"),
            tip(sel("stiff.at", "Location (tool)", [("both", "Both flanges"), ("external", "External flange only"), ("internal", "Internal flange only")], w2=True),
                "Vị trí đặt sườn ngang trong panel (RAM tự đặt theo yêu cầu)"),
            chk("stiff.fullDepth", "Full depth"),
            num("stiff.bs", "bs: Transverse stiffeners width"), num("stiff.cc", "cc: Corner clips"),
            num("stiff.ts", "ts: Transverse stiffener thickness"), sel("stiff.mat", "Material", MATS),
            sel("stiff.weldType", "Weld type", ["Fillet"]), sel("stiff.electrode", "Welding electrode to support", ELEC),
            num("stiff.D", "D: Weld size to support (1/16 in)", "/16", w2=True),
        ]),
        ("Panel zone & support side (tool)", False, [
            tip(chk("pz.on", "Panel zone with its own thicknesses"), "Nhập bề dày panel zone riêng (kích thước theo tiết diện gối)"),
            num("pz.tw", "Panel web tw", show=lambda: S()["pz"]["on"]), num("pz.tfo", "Panel outer flange", show=lambda: S()["pz"]["on"]),
            sel("pz.mat", "Panel material", MATS, show=lambda: S()["pz"]["on"]),
            info("pz._"),
            tip(sel("sup.condE", "Support condition at external flange", COND_OPTS, w2=True), "Điều kiện đường chảy phía gối tại cánh ngoài (DG4 / DG39)"),
            sel("sup.condI", "Support condition at internal flange", COND_OPTS, w2=True),
            tip(num("sup.topOffset", "Support end → plate edge"), "Khoảng cách từ đỉnh cấu kiện gối tới mép bản"), num("sup.tcap", "Cap plate thickness"),
            tip(num("sup.kw", "Web-flange weld (k = tf + tcp + w)"), "Cỡ hàn cổ bụng–cánh để tính k"), num("sup.doubler", "Web doubler plate"),
            chk("sup.bAuto", "Connection plate width = end plate width"),
            num("sup.b", "Connection plate width", show=lambda: not S()["sup"].get("bAuto", True), w2=True),
            chk("sup.diag.on", "Diagonal stiffener in panel (both sides)"),
            num("sup.diag.b", "Diagonal b", show=lambda: S()["sup"]["diag"]["on"]), num("sup.diag.t", "Diagonal t", show=lambda: S()["sup"]["diag"]["on"]),
        ]),
        ("Options (tool)", False, [
            txt("name", "Connection name"),
            tip(chk("opt.axialRelief", "Axial compression reduces Mu,eq (as RAM)"), "Kể lực dọc nén làm giảm Mu,eq"),
            chk("opt.directional", "Directional strength increase for fillet welds"),
            chk("opt.shearAll", "All bolts resist shear"),
            chk("opt.flangeWeldMin", "Flange weld design force ≥ 0.6·Fy·Af"),
            chk("opt.webBuckling", "Check web compression buckling J10.5"),
            chk("opt.pzSubtractShear", "Panel: subtract support member shear"),
            chk("plate.stiffE.on", "End-plate stiffener at external extension (4ES)", show=lambda: ext("external", "both") and int(S()["plate"]["nE"]) == 1),
            num("plate.stiffE.ts", "ts", show=lambda: S()["plate"]["stiffE"]["on"]), num("plate.stiffE.L", "Lst", show=lambda: S()["plate"]["stiffE"]["on"]),
            chk("plate.stiffI.on", "End-plate stiffener at internal extension (4ES)", show=lambda: ext("internal", "both") and int(S()["plate"]["nI"]) == 1),
            num("plate.stiffI.ts", "ts", show=lambda: S()["plate"]["stiffI"]["on"]), num("plate.stiffI.L", "Lst", show=lambda: S()["plate"]["stiffI"]["on"]),
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
        self.fields = []
        self.saved = SavedList()
        self.knees: list = []
        self.groups: dict = {}
        self.conn = SAP2000Connector()
        self._all_loads: list[str] = []
        self._modal: set[str] = set()
        self._chosen_loads = None
        self._picker = None

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
        ctk.CTkLabel(top, text="KNEE KÈO", font=("Segoe UI", 16, "bold"), text_color="#E0701C").pack(side="left", padx=(10, 2))
        ctk.CTkLabel(top, text="AISC 360-10 LRFD", font=FONT_S, text_color="gray").pack(side="left", padx=(0, 12))
        ctk.CTkButton(top, text="Kết nối SAP", width=96, height=28, command=self._connect).pack(side="left", padx=3)
        self.lbl_conn = ctk.CTkLabel(top, text="Chưa kết nối", text_color="gray", font=FONT_B)
        self.lbl_conn.pack(side="left", padx=6)
        self.opt_src = ctk.CTkOptionMenu(top, values=list(SOURCE_MENU), width=140, height=28, command=lambda _v: self._source_changed())
        self.opt_src.set("Design Combos"); self.opt_src.pack(side="left", padx=3)
        self.btn_pick = ctk.CTkButton(top, text="Nguồn tải ▾", width=110, height=28, fg_color="#0F766E", hover_color="#115E59", command=self._pick_loads)
        self.btn_pick.pack(side="left", padx=3)
        self.var_whole = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(top, text="Toàn mô hình", variable=self.var_whole, font=FONT_S, width=20).pack(side="left", padx=6)
        ctk.CTkButton(top, text="🎯 Chọn knee trong SAP", width=170, height=30, fg_color="#7C3AED", hover_color="#6D28D9", font=FONT_B,
                      command=self._pick_knee).pack(side="left", padx=4)
        ctk.CTkButton(top, text="⟳ Quét knee từ SAP", width=150, height=30, fg_color="#2563EB", font=FONT_B, command=self._scan).pack(side="left", padx=4)

        ctk.CTkButton(top, text="💾 Lưu vào danh sách", width=150, height=30, fg_color="#059669", hover_color="#047857", font=FONT_B, command=self._save_new).pack(side="right", padx=6)
        ctk.CTkButton(top, text="⬇ RAM .rcnx", width=104, height=30, fg_color="#7C3AED", hover_color="#6D28D9", font=FONT_B,
                      command=lambda: self._export_rcnx("current")).pack(side="right", padx=3)
        ctk.CTkButton(top, text="⚙ Tự chọn tp / bu lông", width=160, height=30, fg_color="#B45309", hover_color="#92400E", font=FONT_B, command=self._auto).pack(side="right", padx=3)
        self.opt_preset = ctk.CTkOptionMenu(top, values=list(PRESETS), width=170, height=28, command=self._preset)
        self.opt_preset.set("Nạp mẫu…"); self.opt_preset.pack(side="right", padx=3)

        vpan = self.vpan = ttk.PanedWindow(self, orient="vertical")
        vpan.pack(fill="both", expand=True, padx=6, pady=4)
        hpan = self.hpan = ttk.PanedWindow(vpan, orient="horizontal")
        vpan.add(hpan, weight=4)

        # form trái
        left = ctk.CTkFrame(hpan, width=370)
        hpan.add(left, weight=0)
        self.form = ctk.CTkScrollableFrame(left, width=350, label_text="THÔNG SỐ KNEE", label_font=FONT_B)
        self.form.pack(fill="both", expand=True)
        self._build_form()

        # giữa: hình
        mid = ctk.CTkFrame(hpan)
        hpan.add(mid, weight=3)
        bar = ctk.CTkFrame(mid, fg_color="transparent"); bar.pack(fill="x", padx=4, pady=4)
        self.seg_type = ctk.CTkSegmentedButton(bar, values=list(TYPE_LABEL.values()), command=self._type_changed, font=FONT_B,
                                               selected_color="#E0701C", selected_hover_color="#C25E12")
        self.seg_type.pack(side="left")
        self.seg_view = ctk.CTkSegmentedButton(bar, values=["Mặt đứng", "Mặt bản đầu", "3D"], command=self._view_changed, font=FONT_S)
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
        # thang màu
        leg = tk.Canvas(bar2, width=150, height=22, highlightthickness=0, background="#F2F4F7")
        leg.pack(side="right", padx=4)
        for i in range(120):
            leg.create_line(15 + i, 4, 15 + i, 12, fill=heat_color(i / 100))
        for v in (0, 0.6, 0.9, 1.0, 1.2):
            leg.create_text(15 + v * 100, 18, text=f"{v:g}", font=("Segoe UI", 7), fill="#5B6777")
        self._playing = False
        self.view_host = tk.Frame(mid, background="#FFFFFF")
        self.view_host.pack(fill="both", expand=True, padx=4, pady=(2, 2))
        self.canvas = KneeCanvas(self.view_host)
        self.canvas3d = Knee3D(self.view_host)
        self.canvas.pack(fill="both", expand=True)
        for cv in (self.canvas, self.canvas3d):
            cv.tipfn = self._tip_text
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
            cv.grid(row=i // 4, column=i % 4, padx=2, pady=2, sticky="ew")
            cv.bind("<Button-1>", lambda e, n=name: self._card_click(n))
            self.cards[name] = cv
        for c in range(4):
            cards.grid_columnconfigure(c, weight=1)
        tf = ttk.Frame(right); tf.pack(fill="both", expand=True, padx=6, pady=2)
        cols = ("dc", "cap", "dem", "unit", "combo", "ref")
        self.tree = ttk.Treeview(tf, columns=cols, style="K.Treeview", selectmode="browse")
        for c, h, w, an in (("#0", "Kiểm tra", 250, "w"), ("dc", "D/C", 55, "center"), ("cap", "Khả năng", 80, "e"), ("dem", "Yêu cầu", 80, "e"),
                            ("unit", "ĐV", 45, "center"), ("combo", "Tổ hợp", 120, "w"), ("ref", "Tham chiếu", 170, "w")):
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
        for name in ("Loads", "Report (RAM)", "Knee quét từ SAP", "Danh sách đã lưu", "Nội lực quy đổi", "Cấu tạo & cảnh báo"):
            self.tabs.add(name)
        self._build_loads_tab(self.tabs.tab("Loads"))
        self._build_report_tab(self.tabs.tab("Report (RAM)"))
        self._build_scan_tab(self.tabs.tab("Knee quét từ SAP"))
        self._build_saved_tab(self.tabs.tab("Danh sách đã lưu"))
        self.tree_dem = self._mk_table(self.tabs.tab("Nội lực quy đổi"),
                                       [("name", "Tổ hợp", 170), ("V", "V", 70), ("N", "N", 70), ("M", "M (kN·m)", 80), ("Nn", "Nn", 70), ("Vt", "Vt", 70),
                                        ("FnE", "Ffu ngoài", 85), ("FnI", "Ffu trong", 85), ("Mu", "Mu,eq", 80), ("side", "Phía kéo", 90), ("Vpz", "Vu panel", 80)])
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
            ctk.CTkLabel(cell, text=sp["l"].upper(), font=("Segoe UI", 11, "bold"), text_color="#E0701C", anchor="w").pack(fill="x", pady=(6, 0))
            return
        if k == "info":
            f["lbl"] = ctk.CTkLabel(cell, text="", font=("Segoe UI", 10), anchor="w", justify="left", wraplength=320)
            f["lbl"].pack(fill="x")
            return
        if k == "btn":
            ctk.CTkButton(cell, text=sp["l"], height=28, font=FONT_B, fg_color="#1F6FEB", command=sp["cmd"]).pack(fill="x", pady=2)
            return
        if k == "note":
            ctk.CTkLabel(cell, text=sp["l"], font=("Segoe UI", 11), text_color="#5B6777", anchor="w").pack(fill="x")
            return
        if k == "lock":
            box = ctk.CTkFrame(cell, fg_color="#E8F1FF", corner_radius=8)
            box.pack(fill="x")
            f["lbl"] = ctk.CTkLabel(box, text="", font=("Segoe UI", 10), anchor="w", justify="left", wraplength=250, text_color="#1D4ED8")
            f["lbl"].pack(side="left", fill="x", expand=True, padx=6, pady=4)
            f["btn"] = ctk.CTkButton(box, text="🔓 Mở khoá", width=80, height=24, font=("Segoe UI", 10), command=self._toggle_lock)
            f["btn"].pack(side="right", padx=4)
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
        K.normalize(self.S)
        self._suspend = True
        for f in self.fields:
            sp = f["spec"]; k = sp["k"]
            if k in ("sub", "info", "lock", "btn", "note"): continue
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
            if v.is_integer() and sp["p"] in ("plate.nE", "plate.nI", "bolt.d"): v = int(v)
        else: v = f["var"].get()
        setp(self.S, sp["p"], v)
        if self.S.get("sap_lock") is None: pass
        if sp["p"] == "plate.alignment":
            K.normalize(self.S); self._apply_type_defaults()
            self.seg_type.set(TYPE_LABEL[self.S["type"]]); self._load_form()
        if structural: self._refresh_visibility()
        if sp["p"].endswith(".sec"): self._update_info()
        self.schedule()

    def _refresh_visibility(self):
        for f in self.fields:
            show = f["spec"].get("show")
            vis = True
            if show:
                try: vis = bool(show())
                except Exception: vis = True
            if f["spec"]["k"] == "lock":
                vis = bool(self.S.get("_source"))
            if vis: f["cell"].grid(**f["grid"])
            else: f["cell"].grid_remove()
        locked = bool(self.S.get("sap_lock")) and bool(self.S.get("_source"))
        for f in self.fields:
            sp = f["spec"]
            if sp.get("p") in LOCKABLE and "w" in f:
                try: f["w"].configure(state="disabled" if locked else "normal")
                except Exception: pass
            if sp["k"] == "lock" and self.S.get("_source"):
                src = self.S["_source"]
                ks = src.get("knees", [])
                desc = "; ".join(f"{k['kid']} nút {k['joint']}: kèo {k['raf']}·{k.get('raf_end', '')}, cột {k['col']}·{k.get('col_end', '')}" for k in ks[:3])
                if len(ks) > 3: desc += f" … (+{len(ks) - 3})"
                f["lbl"].configure(text=("🔒 Tiết diện, L, đầu nút, α lấy từ SAP2000 — " if locked else "🔓 Đang sửa tay (đã mở khoá) — ") + desc)
                f["btn"].configure(text="🔓 Mở khoá" if locked else "🔒 Khoá lại")

    def _toggle_lock(self):
        self.S["sap_lock"] = not self.S.get("sap_lock")
        self._refresh_visibility()

    def _update_info(self):
        for f in self.fields:
            if f["spec"]["k"] != "info": continue
            p = f["spec"]["p"]
            if p == "pz._":
                continue
            m = getp(self.S, p.rsplit(".", 1)[0])
            try:
                mm = K.member_at_joint(m, "")
                try:
                    parse_section(m["sec"]); src = ""
                except SectionError:
                    src = " (kích thước qua API SAP)"
                fl = (f"{mm['bfE']:g}×{mm['tfE']:g}" if (mm['bfE'], mm['tfE']) == (mm['bfI'], mm['tfI'])
                      else f"ngoài {mm['bfE']:g}×{mm['tfE']:g} / trong {mm['bfI']:g}×{mm['tfI']:g}")
                f["lbl"].configure(text=f"✓ Tại nút: d = {mm['d']:.1f}, bụng {mm['hw']:.1f}×{mm['tw']:g}, cánh {fl}"
                                        + (f" · vát {mm['beta']:.1f}°" if mm["beta"] > 1e-6 else "") + src, text_color=OK_C)
            except (SectionError, ValueError) as e:
                f["lbl"].configure(text="✗ " + str(e), text_color=BAD_C)

    # ───────────────────────── Tính ─────────────────────────
    def schedule(self):
        if self._job: self.after_cancel(self._job)
        self._job = self.after(250, self.run)

    def run(self):
        self._job = None
        try:
            self.R = K.compute(self.S); err = None
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
        sd = lambda s: f"{s['cfg']} · {'bản dày' if s['thick'] else 'bản mỏng'}" if "error" not in s else "lỗi"
        self.lbl_kv.configure(text=(f"Cánh ngoài : {sd(R['sides']['E'])}\nCánh trong : {sd(R['sides']['I'])}\n"
                                    f"φ cánh     : {G['phiE']:.1f}° / {G['phiI']:.1f}°   d, dm dọc bản: {G['dp']:.1f} / {G['dm']:.1f} mm\n"
                                    f"Bản đầu    : {G['bp']:.0f}×{self.S['plate']['tp']:g}×{G['sBot'] - G['sTop']:.0f}  ·  {R['bolt']['bg']['label']} M{R['bolt']['db']}"))
        self._render_cards()
        self._render_report()
        PZ = G["PZ"]
        for f in self.fields:
            if f["spec"]["k"] == "info" and f["spec"]["p"] == "pz._":
                f["lbl"].configure(text=f"Panel: d = {PZ['d']:.1f} (theo tiết diện {'cột' if G['type'] != 'ngang' else 'kèo'} tại nút), bề rộng cánh {PZ['bfE']:g}/{PZ['bfI']:g}; "
                                        f"bụng {PZ['tw']:g}, cánh ngoài {PZ['tfE']:g}, bản gối {PZ['tfI']:g} mm · {PZ['mat']['name']}", text_color="#B7862B")
        n = max(len(self.S["loads"]), 1)
        self.slider.configure(to=max(n - 1, 1), number_of_steps=max(n - 1, 1))
        self.slider.set(self.combo_idx)
        # bảng kiểm tra
        groups = {}
        for c in R["checks"]:
            groups.setdefault(c["grp"], []).append(c)
        for gname, lst in groups.items():
            worst = max((c["ratio"] for c in lst if not c["info"]), default=0.0)
            pid = self.tree.insert("", "end", text=gname, values=(f"{worst:.2f}", "", "", "", "", ""), open=True, tags=("grp",))
            for c in lst:
                tag = "info" if c["info"] else ("bad" if c["ratio"] > 1.0001 else "warn" if c["ratio"] > 0.9 else "ok")
                cap = "—" if K.isnan(c["cap"]) else f"{c['cap']:.2f}"
                self.tree.insert(pid, "end", iid=c["id"], text=("  " + c["name"] + ("  (có sườn)" if c["info"] else "")),
                                 values=("∞" if math.isinf(c["ratio"]) else f"{c['ratio']:.2f}", cap, f"{c['dem']:.2f}", c["unit"], c["combo"], c["ref"]), tags=(tag,))
        if self.sel_check and self.tree.exists(self.sel_check):
            self.tree.selection_set(self.sel_check); self.tree.see(self.sel_check)
        else:
            self.sel_check = None; self._show_detail(None)
        # nội lực quy đổi
        self.tree_dem.delete(*self.tree_dem.get_children())
        for d in R["demands"]:
            self.tree_dem.insert("", "end", values=(d["name"], f"{d['V']:.2f}", f"{d['N']:.2f}", f"{d['M']:.2f}", f"{d['Nn']:.2f}", f"{d['Vt']:.2f}",
                                                    f"{d['FnE']:.2f}", f"{d['FnI']:.2f}", f"{d['Mu']:.2f}",
                                                    {"E": "Cánh ngoài", "I": "Cánh trong"}.get(d["side"], "—"), f"{d['Vpz']:.2f}"))
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
            r = K.compute(st)
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
        if self.view == "3d":
            sc = elevation(self.S, self.R, dem, flow=self.var_flow.get())
            self.canvas3d.show(sc, c["tags"] if c else (), heat)
        else:
            sc = elevation(self.S, self.R, dem, flow=self.var_flow.get()) if self.view == "elev" else plate_face(self.S, self.R, dem)
            self.canvas.show(sc, c["tags"] if c else (), heat)
        names = [l.get("name", "") for l in self.S["loads"]]
        if names:
            self.lbl_combo.configure(text=f"{self.combo_idx + 1}/{len(names)} · {names[self.combo_idx][:18]}")
        if dem:
            self.lbl_draw.configure(text=f"{dem['name']}:  M = {dem['M']:.1f} kN·m · N = {dem['N']:.1f} kN · V = {dem['V']:.1f} kN  →  kéo "
                                         + {"E": "cánh ngoài", "I": "cánh trong"}.get(dem["side"], "—"))

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
            self.canvas.set_highlight(()); self.canvas3d.set_highlight(())

    def _show_detail(self, c):
        self.txt_detail.configure(state="normal"); self.txt_detail.delete("1.0", "end")
        if c:
            self.txt_detail.insert("end", f"{c['name']}  —  {c['ref']}\n", ("h",))
            self.txt_detail.insert("end", f"Khả năng = {c['cap']:.2f} {c['unit']};  Yêu cầu = {c['dem']:.2f} {c['unit']};  D/C = {c['ratio']:.3f}  ({c['combo']})\n\n")
            self.txt_detail.insert("end", "\n".join(c["detail"]))
            self.txt_detail.tag_configure("h", font=("Consolas", 10, "bold"), foreground="#E0701C")
        else:
            self.txt_detail.insert("end", "Chọn một dòng kiểm tra để xem diễn giải công thức từng bước và tô sáng bộ phận trên hình.")
        self.txt_detail.configure(state="disabled")

    # ───────────────────────── sự kiện thanh công cụ ─────────────────────────
    def _type_changed(self, lab):
        t = TYPE_KEY[lab]
        self.S["plate"]["alignment"] = {"dung": "vertical", "ngang": "horizontal", "xien": "perpendicular"}[t]
        K.normalize(self.S); self._apply_type_defaults()
        self.sel_check = None
        self._load_form(); self.run()

    def _apply_type_defaults(self):
        """Điều kiện phía gối mặc định theo kiểu knee."""
        sup, t = self.S["sup"], self.S["type"]
        if t == "ngang":
            sup["condE"] = sup["condI"] = "cont_stiff"
        else:
            if sup["condE"] == "endplate" or (sup["condE"] == "cont_stiff" and sup["condI"] == "cont_stiff"): sup["condE"] = "top_cap"
            if sup["condI"] == "endplate": sup["condI"] = "cont_stiff"

    def _view_changed(self, lab):
        self.view = {"Mặt đứng": "elev", "Mặt bản đầu": "face", "3D": "3d"}[lab]
        if self.view == "3d":
            self.canvas.pack_forget(); self.canvas3d.pack(fill="both", expand=True)
        else:
            self.canvas3d.pack_forget(); self.canvas.pack(fill="both", expand=True)
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
        res = K.auto_design(self.S)
        if not res:
            messagebox.showwarning("Tự chọn", "Không tính được phương án nào — kiểm tra lại số liệu."); return
        self.S["plate"]["tp"] = res["tp"]; self.S["bolt"]["d"] = res["d"]
        self._load_form(); self.run()
        msg = f"tp = {res['tp']} mm, bu lông M{res['d']} — D/C (bản, bu lông, phía gối) = {res['ratio']:.2f}"
        if res.get("fail"):
            messagebox.showwarning("Tự chọn", "Không có phương án đạt trong dải thử (tp ≤ 40, ≤ M30).\nPhương án tốt nhất: " + msg)
        self.status.set_text("Tự chọn: " + msg)

    # ───────────────────────── Loads (bảng như hộp thoại Loads của RAM Connection) ─────────────────────────
    LOAD_COLS = [("id", "ID", 40), ("name", "Description", 170),
                 ("Nb", "Axial [kN]", 90), ("Vb", "V2 [kN]", 90), ("Mb", "M3 [kN*m]", 95),
                 ("La", "Axial [kN]", 80), ("Lm", "M3 [kN*m]", 85),
                 ("Nc", "Axial [kN]", 90), ("Vc", "V2 [kN]", 90), ("Mc", "M3 [kN*m]", 95), ("src", "Source (SAP extremes)", 330)]
    LOAD_GROUPS = [("Load", 2), ("Right beam", 3), ("Left beam", 2), ("Column", 3), ("", 1)]

    def _build_loads_tab(self, tab):
        bar = ctk.CTkFrame(tab, fg_color="transparent"); bar.pack(fill="x")
        for t, cmd in (("+ Add", self._load_add), ("− Delete", self._load_del), ("📋 Paste from Excel", self._load_paste), ("Clear", self._load_clear)):
            ctk.CTkButton(bar, text=t, width=120, height=26, command=cmd).pack(side="left", padx=3, pady=3)
        ctk.CTkLabel(bar, text="kN, kN·m · Axial > 0 kéo · M3 < 0 → cánh NGOÀI chịu kéo (giống RAM) · nhấp đúp để sửa · Dán: Description, Axial, V2, M3 [, Left Axial, Left M3], Col Axial, Col V2, Col M3",
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
            tv.heading(c, text=h); tv.column(c, width=w, minwidth=w, stretch=False, anchor="w" if c in ("name", "src") else "e")
        sb = ttk.Scrollbar(fr, orient="vertical", command=tv.yview); tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        tv.tag_configure("odd", background="#F6F8FB")
        self.tree_load = tv
        tv.bind("<Double-1>", self._load_edit)

    def _fill_loads(self):
        tv = self.tree_load
        tv.delete(*tv.get_children())
        for i, l in enumerate(self.S["loads"]):
            vals = []
            for k, _, _ in self.LOAD_COLS:
                if k == "id": vals.append(i + 1)
                elif k in ("La", "Lm"): vals.append(0)
                else:
                    v = l.get(k, "")
                    vals.append(f"{v:g}" if isinstance(v, float) else v)
            tv.insert("", "end", iid=str(i), values=vals, tags=("odd",) if i % 2 else ())

    def _load_edit(self, e):
        tv = self.tree_load
        row, col = tv.identify_row(e.y), tv.identify_column(e.x)
        if not row: return
        ci = int(col[1:]) - 1
        key = self.LOAD_COLS[ci][0]
        if key in ("src", "id", "La", "Lm"): return
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
        self.S["loads"].append(dict(name=f"LC{len(self.S['loads']) + 1}", Vb=0, Nb=0, Mb=0, Vc=0, Nc=0, Mc=0))
        self._fill_loads(); self.schedule()

    def _load_del(self):
        for iid in sorted((int(i) for i in self.tree_load.selection()), reverse=True):
            del self.S["loads"][iid]
        self._fill_loads(); self.schedule()

    def _load_clear(self):
        if messagebox.askyesno("Clear", "Xoá toàn bộ tổ hợp tải?"):
            self.S["loads"] = []; self._fill_loads(); self.schedule()

    def _load_paste(self):
        """Dán theo thứ tự cột RAM: Description, Axial, V2, M3 [, Left Axial, Left M3], Col Axial, Col V2, Col M3."""
        try: raw = self.clipboard_get()
        except tk.TclError: raw = ""
        rows = []
        for line in raw.strip().splitlines():
            p = [x.strip() for x in line.replace(";", "\t").split("\t")]
            if p and p[0].isdigit() and len(p) > 4: p = p[1:]          # bỏ cột ID nếu có
            vals = []
            for x in p[1:]:
                try: vals.append(float(x.replace(",", ".")))
                except ValueError: vals.append(None)
            if len(vals) < 3 or vals[0] is None: continue
            col = vals[5:8] if len(vals) >= 8 else vals[3:6]
            col = [(v or 0.0) for v in col] + [0.0] * (3 - len(col))
            rows.append(dict(name=p[0] or f"LC{len(rows) + 1}", Nb=vals[0] or 0.0, Vb=vals[1] or 0.0, Mb=vals[2] or 0.0,
                             Nc=col[0], Vc=col[1], Mc=col[2]))
        if not rows:
            messagebox.showinfo("Paste", "Clipboard không có dữ liệu hợp lệ (cần: Description, Axial, V2, M3, …)."); return
        self.S["loads"] += rows; self._fill_loads(); self.schedule()
        self.status.set_text(f"Đã dán {len(rows)} tổ hợp.")

    # ───────────────────────── Report (form RAM Connection) + xuất ─────────────────────────
    def _build_report_tab(self, tab):
        bar = ctk.CTkFrame(tab, fg_color="transparent"); bar.pack(fill="x")
        ctk.CTkButton(bar, text="📄 Export report (.docx)", width=170, height=26, command=self._export_docx).pack(side="left", padx=3, pady=3)
        ctk.CTkButton(bar, text="⬇ Export RAM Connection (.rcnx) — knee hiện tại", width=300, height=26, fg_color="#7C3AED", hover_color="#6D28D9",
                      command=lambda: self._export_rcnx("current")).pack(side="left", padx=3)
        ctk.CTkButton(bar, text="⬇ Export .rcnx — toàn bộ danh sách đã lưu", width=280, height=26, fg_color="#7C3AED", hover_color="#6D28D9",
                      command=lambda: self._export_rcnx("saved")).pack(side="left", padx=3)
        self.var_mksec = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(bar, text="Tạo tiết diện trong database RAM (WS Section-Hoang)", variable=self.var_mksec, font=FONT_S).pack(side="left", padx=10)
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
                                            initialfile=f"{self.S.get('name', 'knee')}_report.docx".replace(":", "-").replace("/", "-"))
        if not path: return
        try:
            RP.to_docx(RP.build(self.S, self.R), path)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Export report", str(e)); return
        self.status.set_text(f"Đã xuất báo cáo: {path}")

    def _export_rcnx(self, which):
        if which == "saved":
            states = [merge(BASE, it["state"]) for it in self.saved.items]
            if not states:
                messagebox.showinfo("Export RAM", "Danh sách đã lưu đang trống — lưu knee vào danh sách trước."); return
        else:
            states = [copy.deepcopy(self.S)]
        path = filedialog.asksaveasfilename(title="Export RAM Connection", defaultextension=".rcnx", filetypes=[("RAM Connection", "*.rcnx")],
                                            initialfile="KNEE_export.rcnx")
        if not path: return
        try:
            res = ram_export.export_rcnx(states, path, make_sections=self.var_mksec.get())
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Export RAM", f"Không xuất được: {e}"); return
        msg = [f"Đã xuất {res['n']} connection (MEPlateKneeBCF) → {path}"]
        sec = res.get("sections")
        if sec:
            msg.append(f"\nDatabase tiết diện: {sec['path']}")
            msg.append(f"  • thêm mới: {', '.join(sec['added']) or '—'}")
            msg.append(f"  • đã có sẵn: {', '.join(sec['existed']) or '—'}")
            if sec["added"]: msg.append("  → ĐÓNG và mở lại RAM Connection để nạp tiết diện mới (bản gốc đã sao lưu trong _backup).")
        if res["warnings"]:
            msg.append("\nLưu ý:\n  • " + "\n  • ".join(res["warnings"]))
        messagebox.showinfo("Export RAM Connection", "\n".join(msg))
        self.status.set_text(msg[0])

    # ───────────────────────── SAP2000 ─────────────────────────
    def _connect(self):
        msg = self.conn.connect()
        if msg == "OK":
            self.conn.set_units_kn_m()
            self.lbl_conn.configure(text="Đã kết nối", text_color=OK_C)
            self._source_changed()
            self.status.set_text("Đã kết nối SAP2000 (đơn vị kN-m). Chọn khung trong SAP rồi bấm Quét knee.")
        else:
            self.lbl_conn.configure(text="Lỗi kết nối", text_color=BAD_C)
            messagebox.showerror("SAP2000", msg)

    def _source(self):
        return SOURCE_MENU.get(self.opt_src.get(), LOAD_DESIGN_COMBOS)

    def _source_changed(self):
        self._chosen_loads = None
        if not self.conn.is_connected: return
        self._all_loads, modal = self.conn.list_load_names(self._source())
        self._modal = set(modal)
        self._chosen_loads = default_selected_loads(self._all_loads, self._modal, self._source())
        self.btn_pick.configure(text=f"{len(self._chosen_loads)} nguồn ▾")

    def _pick_loads(self):
        if not self.conn.is_connected:
            messagebox.showinfo("Chưa kết nối", "Kết nối SAP2000 trước."); return
        if not self._all_loads: self._source_changed()

        def apply(ch):
            self._chosen_loads = list(ch); self.btn_pick.configure(text=f"{len(ch)} nguồn ▾")
        p = LoadSourcePicker(self, names=self._all_loads, selected=self._chosen_loads or [], modal_names=self._modal,
                             on_apply=apply, title=f"Chọn nguồn tải — {self.opt_src.get()}")
        p.place_near(self.btn_pick); self._picker = p

    def _pick_knee(self):
        """Knee từ lựa chọn trong SAP (nút hoặc cột + kèo) → nạp thẳng vào thiết kế."""
        knees = self._run_scan(lambda allowed_for, prog: scanner.pick(self.conn, allowed_for, prog))
        if knees is None: return
        if not knees:
            messagebox.showinfo("Chọn knee", "Không nhận ra knee từ lựa chọn trong SAP.\nChọn nút knee, hoặc chọn cột + kèo tại knee rồi bấm lại."); return
        self.knees = knees; self.groups = scanner.group_knees(knees); self._fill_scan()
        if len(self.groups) == 1:
            gid = next(iter(self.groups))
            self.S = self._group_state(gid); self.sel_check = None; self.combo_idx = 0
            self._load_form(); self.run(); self.tabs.set("Loads")
            self.status.set_text(f"Đã nạp knee từ SAP ({', '.join(k.kid + ' nút ' + k.joint for k in knees)}): tiết diện, độ dốc, L và {len(self.S['loads'])} tổ hợp.")
        else:
            self.tabs.set("Knee quét từ SAP")
            self.status.set_text(f"Lựa chọn chứa {len(knees)} knee / {len(self.groups)} nhóm — nhấp đúp nhóm cần thiết kế.")

    def _run_scan(self, fn):
        if not self.conn.is_connected:
            self._connect()
            if not self.conn.is_connected: return None
        src = self._source()
        if self._chosen_loads is None: self._source_changed()
        chosen_set = set(self.conn.setup_output_source(src, self._chosen_loads))
        cache = {}

        def allowed_for(frame):
            if frame not in cache:
                cache[frame] = self.conn.allowed_loads_for_frame(frame, src, chosen_set)
            return cache[frame]

        def prog(m):
            self.status.set_text(m); self.update_idletasks()
        try:
            return fn(allowed_for, prog)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("SAP2000", f"Lỗi khi đọc SAP: {e}\n{self.conn.last_error}")
            return None

    def _scan(self):
        if not self.conn.is_connected:
            self._connect()
            if not self.conn.is_connected: return
        src = self._source()
        if self._chosen_loads is None: self._source_changed()
        chosen = self.conn.setup_output_source(src, self._chosen_loads)
        chosen_set = set(chosen)
        cache = {}

        def allowed_for(frame):
            if frame not in cache:
                cache[frame] = self.conn.allowed_loads_for_frame(frame, src, chosen_set)
            return cache[frame]

        def prog(m):
            self.status.set_text(m); self.update_idletasks()
        try:
            knees = scanner.scan(self.conn, self.var_whole.get(), allowed_for, prog)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Quét knee", f"Lỗi khi quét: {e}\n{self.conn.last_error}"); return
        if not knees:
            messagebox.showinfo("Quét knee", "Không tìm thấy knee (đỉnh cột nối đầu kèo) trong các thanh "
                                + ("của mô hình." if self.var_whole.get() else "đang chọn.\nHãy chọn cả cột và kèo tại knee."))
            return
        self.knees = knees
        self.groups = scanner.group_knees(knees)
        self._fill_scan()
        self.tabs.set("Knee quét từ SAP")
        self.status.set_text(f"Tìm thấy {len(knees)} knee, {len(self.groups)} nhóm. Nhấp đúp một nhóm để nạp vào thiết kế.")

    # ───────────────────────── tab knee quét ─────────────────────────
    def _build_scan_tab(self, tab):
        bar = ctk.CTkFrame(tab, fg_color="transparent"); bar.pack(fill="x")
        ctk.CTkButton(bar, text="➜ Nạp nhóm vào thiết kế", width=170, height=26, command=self._scan_open).pack(side="left", padx=3, pady=3)
        ctk.CTkButton(bar, text="💾 Lưu mọi nhóm vào danh sách", width=210, height=26, fg_color="#059669", command=self._scan_save_all).pack(side="left", padx=3)
        ctk.CTkLabel(bar, text="Nhóm = cùng tiết diện cột, kèo, đầu nút, hướng cánh và góc dốc (±0.25°). Thông số bản/bu lông lấy theo thiết kế hiện tại.",
                     font=("Segoe UI", 10), text_color="gray").pack(side="left", padx=8)
        fr = ttk.Frame(tab); fr.pack(fill="both", expand=True)
        cols = [("joint", "Nút", 60), ("col", "Cột (thanh · đầu)", 110), ("csec", "Tiết diện cột", 220), ("raf", "Kèo (thanh · đầu)", 110),
                ("rsec", "Tiết diện kèo", 220), ("slope", "α (°)", 60), ("nl", "Số TH", 60), ("dc", "D/C", 60), ("warn", "Ghi chú", 300)]
        tv = ttk.Treeview(fr, columns=[c[0] for c in cols], style="K.Treeview", height=6)
        tv.heading("#0", text="Nhóm / knee"); tv.column("#0", width=130)
        for c, h, w in cols:
            tv.heading(c, text=h); tv.column(c, width=w, anchor="w")
        tv.tag_configure("grp", font=("Segoe UI", 10, "bold"), background="#EAF2FF")
        sb = ttk.Scrollbar(fr, orient="vertical", command=tv.yview); tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        tv.bind("<Double-1>", lambda _e: self._scan_open())
        self.tree_scan = tv

    def _group_state(self, gid):
        st = scanner.knee_to_state(self.S, self.groups[gid], gid)
        st["type"] = self.S["type"]
        st["plate"]["alignment"] = self.S["plate"].get("alignment", "vertical")
        return st

    def _fill_scan(self):
        tv = self.tree_scan
        tv.delete(*tv.get_children())
        for gid, lst in self.groups.items():
            k0 = lst[0]
            try:
                r = K.compute(self._group_state(gid)); dc = f"{r['gov']['ratio']:.2f}" if r["gov"] else "—"
            except Exception as e:  # noqa: BLE001
                dc = "lỗi"; k0.warn.append(str(e))
            pid = tv.insert("", "end", iid=gid, text=f"{gid} ({len(lst)} knee)", open=True, tags=("grp",),
                            values=("", "", k0.col_sec, "", k0.raf_sec, f"{k0.slope:.2f}", sum(len(k.loads) for k in lst), dc, ""))
            for k in lst:
                tv.insert(pid, "end", iid=f"{gid}/{k.kid}", text=k.kid,
                          values=(k.joint, f"{k.col} · {k.col_end}", k.col_sec, f"{k.raf} · {k.raf_end}", k.raf_sec, f"{k.slope:.2f}",
                                  len(k.loads), "", "; ".join(k.warn)))

    def _scan_open(self):
        s = self.tree_scan.selection()
        if not s:
            messagebox.showinfo("Knee", "Chọn một nhóm (hoặc knee) trong bảng."); return
        gid = s[0].split("/")[0]
        self.S = self._group_state(gid); self.sel_check = None; self.combo_idx = 0
        self._load_form(); self.run()
        self.tabs.set("Loads")
        self.status.set_text(f"Đã nạp nhóm {gid}: {len(self.S['loads'])} tổ hợp (9 cực trị cột + kèo, ghép cùng tổ hợp).")

    def _scan_save_all(self):
        if not self.groups: return
        for gid in self.groups:
            st = self._group_state(gid)
            self.saved.add(st["name"], st, self._summary_of(st))
        self._fill_saved(); self.tabs.set("Danh sách đã lưu")
        self.status.set_text(f"Đã lưu {len(self.groups)} nhóm vào danh sách.")

    # ───────────────────────── tab danh sách đã lưu ─────────────────────────
    def _build_saved_tab(self, tab):
        bar = ctk.CTkFrame(tab, fg_color="transparent"); bar.pack(fill="x")
        for t, cmd, col in (("💾 Lưu mới", self._save_new, "#059669"), ("↻ Ghi đè", self._save_over, None), ("📂 Mở", self._saved_open, None),
                            ("✎ Đổi tên", self._saved_rename, None), ("✕ Xoá", self._saved_delete, "#B91C1C"),
                            ("▲ Lên", lambda: self._saved_move(-1), None), ("▼ Xuống", lambda: self._saved_move(1), None)):
            kw = dict(fg_color=col) if col else {}
            ctk.CTkButton(bar, text=t, width=96, height=26, command=cmd, **kw).pack(side="left", padx=3, pady=3)
        cols = [("stt", "STT", 45), ("name", "Tên", 240), ("type", "Kiểu", 90), ("raf", "Kèo", 190), ("col", "Cột", 190),
                ("plate", "Bản", 110), ("bolt", "Bu lông", 110), ("nl", "Số TH", 60), ("dc", "D/C", 60), ("time", "Cập nhật", 130)]
        self.tree_saved = self._mk_table(tab, cols, height=6)
        self.tree_saved.bind("<Double-1>", lambda _e: self._saved_open())
        for tag, c in (("ok", OK_C), ("bad", BAD_C)):
            self.tree_saved.tag_configure(tag, foreground=c)
        self._fill_saved()

    def _summary_of(self, st):
        try:
            r = K.compute(st); dc = r["gov"]["ratio"] if r["gov"] else 0.0; ok = dc <= 1.0001 and r["geoFail"] == 0
        except Exception:  # noqa: BLE001
            dc, ok = float("nan"), False
        return dict(type=st["type"], raf=st["beam"]["sec"], col=st["col"]["sec"], tp=st["plate"]["tp"],
                    bolt=f"M{st['bolt']['d']} {st['bolt']['grade']}", nl=len(st["loads"]), dc=dc, ok=ok)

    def _fill_saved(self, select=None):
        tv = self.tree_saved
        tv.delete(*tv.get_children())
        for i, it in enumerate(self.saved.items):
            s = it.get("summary", {})
            dc = s.get("dc", float("nan"))
            tv.insert("", "end", iid=str(i), tags=("ok" if s.get("ok") else "bad",),
                      values=(i + 1, it["name"], TYPE_LABEL.get(s.get("type"), ""), s.get("raf", ""), s.get("col", ""),
                              f"tp {s.get('tp', '')}", s.get("bolt", ""), s.get("nl", ""), "—" if dc != dc else f"{dc:.2f}", it.get("time", "")))
        if select is not None and 0 <= select < len(self.saved.items):
            tv.selection_set(str(select)); tv.see(str(select))

    def _saved_idx(self):
        s = self.tree_saved.selection()
        if not s:
            messagebox.showinfo("Danh sách", "Chọn một dòng trong danh sách đã lưu."); return None
        return int(s[0])

    def _save_new(self):
        name = ctk.CTkInputDialog(text="Tên knee / nhóm:", title="Lưu vào danh sách").get_input()
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
