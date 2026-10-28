"""
newjoint.py — Hộp thoại "New joint" theo RAM Connection: cột "Joint group" bên trái, các ô kiểu nút bên phải (mã BCF/BCW/BS… ở góc),
tiêu đề "BCF - Beam to Column Flange", dòng "Selected joint: …", nút Joint / Data » / OK / Cancel / Help.
Chỉ các kiểu đã có lõi tính mới chọn được; các kiểu còn lại hiện mờ (chưa hỗ trợ).

Ba bước như RAM:  Joint (chọn kiểu nút)  →  Data (bảng Property / Value + Help)  →  Loads (bảng tải).
Kết quả: dict(key="knee" | "splice:straight" | "splice:apex" | "base", state=...) hoặc None (huỷ).
"""

from __future__ import annotations

import copy
import tkinter as tk
from tkinter import ttk

import base_defaults as BD
import base_engine as BE
import defaults as KD
import engine as K
import splice_defaults as SD
from knee_section import SectionError, parse_section

BG_DLG = "#FFFFFF"
BG_GROUP = "#8A95A3"
BG_JOINTS = "#D3D7DB"
ORANGE = "#F5823A"
TILE_BG = "#EDEDED"
TILE_BORDER = "#B8BCC0"
TILE_W, TILE_H, ROWS = 236, 82, 5

FAMILY = {"BCF": "Beam to Column Flange", "BCW": "Beam to Column Web", "BG": "Beam to Girder", "BS": "Beam Splice",
          "CS": "Column Splice", "CC": "Column Cap", "CB": "Column Base", "CCB": "Column Cap - Brace",
          "CBB": "Column - Beam - Brace", "CVR": "Chevron", "VXB": "Vertical X Brace", "HCBB": "Horizontal Column - Beam - Brace",
          "HBBB": "Horizontal Beam - Beam - Brace", "HXB": "Horizontal X Brace", "CHB": "Chord - Branch"}

# nhóm: (tên, biểu tượng nhóm, [(tên ô, mã, key hoặc None, biểu tượng)])  — các ô xếp theo cột, 5 ô mỗi cột như RAM
GROUPS = [
    ("Beam to support", "beam", [
        ("Beam to column flange", "BCF", None, "beam"),
        ("Beam to column flange with opposite beam", "BCF", None, "beam2"),
        ("Haunched beam to column flange", "BCF", None, "haunch"),
        ("Haunched beam to column flange with opposite haunched beam", "BCF", None, "haunch"),
        ("Tapered beam to column", "BCF", None, "haunch"),
        ("Tapered beam to tapered column (Knee)", "BCF", "knee", "knee"),
        ("Tubular mitred knee", "BCF", None, "mitre"),
        ("Beam to column web", "BCW", None, "beam"),
        ("Beam to column web with opposite beam", "BCW", None, "beam2"),
        ("Tubular mitred knee", "BCW", None, "mitre"),
        ("Beam to girder", "BG", None, "girder"),
        ("Beam to girder with opposite beam", "BG", None, "girder"),
    ]),
    ("Splices", "splice", [
        ("Beam splice", "BS", "splice:straight", "splice"),
        ("Apex", "BS", "splice:apex", "apex"),
        ("Apex with haunched beams", "BS", None, "apex_h"),
        ("Tapered beam splice", "BS", None, "tapered"),
        ("Column splice", "CS", None, "col"),
    ]),
    ("Column top and base", "col", [
        ("Column cap", "CC", None, "col"), ("Column base", "CB", "base", "base"), ("Column base with one brace", "CB", None, "vbrace"),
        ("Column base with two braces", "CB", None, "vbrace"), ("Column cap - brace", "CCB", None, "vbrace"),
    ]),
    ("Vertical bracing", "vbrace", [
        ("Column - beam - one brace", "CBB", None, "vbrace"), ("Column - beam - two braces", "CBB", None, "vbrace"),
        ("Column - beam - four braces", "CBB", None, "vbrace"), ("Y brace", "CBB", None, "vbrace"), ("K brace", "CBB", None, "vbrace"),
        ("Chevron - one brace", "CVR", None, "truss"), ("Chevron - two braces", "CVR", None, "truss"),
        ("Chevron - four braces", "CVR", None, "truss"), ("Vertical X brace", "VXB", None, "vbrace"),
    ]),
    ("Horizontal bracing", "hbrace", [
        ("Horizontal column - beam - brace", "HCBB", None, "hbrace"), ("Front beam only", "HCBB", None, "hbrace"),
        ("Right beam only", "HCBB", None, "hbrace"), ("Horizontal beam - beam - brace", "HBBB", None, "hbrace"),
        ("With girder only", "HBBB", None, "hbrace"), ("Horizontal X brace", "HXB", None, "hbrace"),
    ]),
    ("Trusses", "truss", [
        ("Tubular YT", "CHB", None, "truss"), ("Tubular KN", "CHB", None, "truss"), ("Tubular K", "CHB", None, "truss"),
        ("Tubular X (2 branches)", "CHB", None, "truss"), ("Tubular X (4 branches)", "CHB", None, "truss"),
        ("Tubular KT", "CHB", None, "truss"), ("Tubular KT with three branches", "CHB", None, "truss"),
        ("Tubular KT with six branches", "CHB", None, "truss"),
    ]),
]


CODE = {"knee": "BCF", "splice": "BS", "base": "CB"}
UNSUPPORTED = "Chưa hỗ trợ — chọn: Tapered beam to tapered column (Knee), Beam splice, Apex hoặc Column base."


def _pipe(cv, a, b, c="#2B2F36"):
    cv.create_line(*a, *b, fill=c, width=7)
    cv.create_line(*a, *b, fill="#FFFFFF", width=4)


def icon(cv: tk.Canvas, kind: str, x: float, y: float, w: float = 60, h: float = 44):
    """Biểu tượng nét đơn giản (cột, dầm, bản, giằng)."""
    c = "#2B2F36"; W = "#FFFFFF"
    col = lambda x0: (cv.create_rectangle(x0, y, x0 + 9, y + h, outline=c, fill=W), cv.create_line(x0 + 4.5, y, x0 + 4.5, y + h, fill=c))
    if kind in ("beam", "beam2", "girder"):
        col(x + 4)
        cv.create_rectangle(x + 13, y + 12, x + w, y + 28, outline=c, fill=W)
        if kind == "beam2":
            cv.create_rectangle(x - 10, y + 12, x + 4, y + 28, outline=c, fill=W)
    elif kind == "haunch":
        col(x + 4)
        cv.create_rectangle(x + 13, y + 10, x + w, y + 24, outline=c, fill=W)
        cv.create_polygon(x + 13, y + 24, x + w * 0.75, y + 24, x + 13, y + 38, outline=c, fill=W)
    elif kind == "knee":
        cv.create_polygon(x + 4, y + 8, x + 18, y + 4, x + 22, y + h, x + 8, y + h, outline=c, fill=W)
        cv.create_polygon(x + 18, y + 4, x + w, y - 4, x + w, y + 14, x + 22, y + 24, outline=c, fill=W)
        cv.create_line(x + 18, y + 4, x + 22, y + 24, fill="#C2410C", width=2)
    elif kind == "mitre":
        cv.create_polygon(x + 6, y + 4, x + 18, y + 4, x + 18, y + h, x + 6, y + h, outline=c, fill=W)
        cv.create_polygon(x + 6, y + 4, x + w, y + 4, x + w, y + 16, x + 18, y + 16, outline=c, fill=W)
    elif kind in ("splice", "tapered"):
        d = 0 if kind == "splice" else 4
        cv.create_rectangle(x, y + 12, x + w / 2 - 3, y + h - 12, outline=c, fill=W)
        cv.create_rectangle(x + w / 2 + 3, y + 12 + d, x + w, y + h - 12 - d, outline=c, fill=W)
        cv.create_line(x + w / 2, y + 8, x + w / 2, y + h - 8, fill=c, width=2)
    elif kind in ("apex", "apex_h"):
        cv.create_polygon(x, y + 26, x + w / 2 - 3, y + 14, x + w / 2 - 3, y + 30, x, y + 42, outline=c, fill=W)
        cv.create_polygon(x + w, y + 26, x + w / 2 + 3, y + 14, x + w / 2 + 3, y + 30, x + w, y + 42, outline=c, fill=W)
        if kind == "apex_h":
            cv.create_line(x + 6, y + 40, x + w / 2 - 3, y + 30, x + w - 6, y + 40, fill=c)
    elif kind == "base":
        cv.create_rectangle(x + w / 2 - 9, y, x + w / 2 + 9, y + h - 14, outline=c, fill=W)
        cv.create_rectangle(x + 6, y + h - 14, x + w - 6, y + h - 9, outline=c, fill="#C9C2E6")
        cv.create_rectangle(x + 2, y + h - 9, x + w - 2, y + h, outline=c, fill="#D5D8DC")
        for xa in (x + 12, x + w - 12):
            cv.create_line(xa, y + h - 18, xa, y + h, fill="#C2410C", width=2)
    elif kind == "col":
        cv.create_rectangle(x + w / 2 - 9, y, x + w / 2 + 9, y + h / 2 - 2, outline=c, fill=W)
        cv.create_rectangle(x + w / 2 - 9, y + h / 2 + 2, x + w / 2 + 9, y + h, outline=c, fill=W)
    elif kind == "vbrace":
        col(x + 2)
        cv.create_rectangle(x + 11, y + h - 16, x + w, y + h - 8, outline=c, fill=W)
        _pipe(cv, (x + 14, y + h - 20), (x + w - 4, y + 2))
    elif kind == "hbrace":
        col(x + 2)
        cv.create_line(x + 11, y + h - 6, x + w, y + h - 6, fill=c, width=4, dash=(4, 2))
        _pipe(cv, (x + 14, y + h - 14), (x + w - 4, y + 4))
    else:  # truss
        cv.create_rectangle(x, y + h - 14, x + w, y + h - 4, outline=c, fill=W)
        _pipe(cv, (x + w / 2 - 4, y + h - 14), (x + 6, y + 2))
        _pipe(cv, (x + w / 2 + 4, y + h - 14), (x + w - 6, y + 2))


def _gradient(cv, x0, y0, x1, y1):
    n = int(x1 - x0)
    for k in range(0, n, 2):
        t = k / max(n, 1)
        cv.create_line(x0 + k, y0, x0 + k, y1, fill="#%02X%02X%02X" % (int(255 - 20 * (1 - t)), int(183 + 55 * t), int(119 + 100 * t)))


# ─────────────────────────── Bảng Data (Property / Value) theo từng kiểu nút ───────────────────────────
MATS = list(K.MATERIALS)
YN = [("Yes", True), ("No", False)]


def G(label):                                    # dòng nhóm (gạch chân, đậm)
    return dict(k="grp", l=label)


def P(path, label, kind="txt", opts=None, unit="", scale=1.0, show=None, ro=False, calc=None):
    return dict(k=kind, p=path, l=label, opts=opts, unit=unit, scale=scale, show=show, ro=ro, calc=calc)


def _member_type(sec):
    try:
        return "Tapered member" if parse_section(sec).tapered else "Prismatic member"
    except SectionError:
        return "— (tiết diện không đúng quy cách)"


DATA_SPEC = {
    "knee": [
        P("_joint", "Joint", ro=True, calc=lambda S: "BCF"),
        P("name", "Name"), P("desc", "Description"), P("group", "Display group"),
        P("plate.alignment", "Plate alignment", "sel", [("Vertical alignment", "vertical"), ("Perpendicular to beam", "perpendicular"),
                                                       ("Horizontal alignment", "horizontal")]),
        G("Beam"),
        P("_btype", "Type", ro=True, calc=lambda S: _member_type(S["beam"]["sec"])),
        P("beam.sec", "Section"), P("beam.mat", "Material", "sel", [(m, m) for m in MATS]),
        P("beam.slope", "Slope angle", "num", unit="°"),
        P("beam.L", "L: Length", "num", unit="mm", scale=1000.0),
        P("beam.jointEnd", "Joint end (SAP)", "sel", [("End I", "I"), ("End J", "J")]),
        P("beam.topIsOuter", "Top flange (+2) is external", "sel", YN),
        G("Column"),
        P("_ctype", "Type", ro=True, calc=lambda S: _member_type(S["col"]["sec"])),
        P("col.sec", "Section"), P("col.mat", "Material", "sel", [(m, m) for m in MATS]),
        P("col.L", "L: Length", "num", unit="mm", scale=1000.0),
        P("col.jointEnd", "Joint end (SAP)", "sel", [("End J (top)", "J"), ("End I", "I")]),
        P("col.topIsOuter", "Top flange (+2) is external", "sel", YN),
    ],
    "splice": [
        P("_joint", "Joint", ro=True, calc=lambda S: "BS"),
        P("name", "Name"), P("desc", "Description"), P("group", "Display group"),
        P("type", "Splice type", "sel", [("Beam splice", "straight"), ("Apex", "apex")]),
        P("slope", "Slope angle (each beam)", "num", unit="°", show=lambda S: S["type"] == "apex"),
        G("Left beam"),
        P("_t1", "Type", ro=True, calc=lambda S: _member_type(S["beam1"]["sec"])),
        P("beam1.sec", "Section"), P("beam1.mat", "Material", "sel", [(m, m) for m in MATS]),
        P("beam1.L", "L: Length", "num", unit="mm", scale=1000.0),
        P("beam1.jointEnd", "Joint end (SAP)", "sel", [("End J", "J"), ("End I", "I")]),
        G("Right beam"),
        P("beam2.same", "Same as left beam", "sel", YN),
        P("_t2", "Type", ro=True, calc=lambda S: _member_type(S["beam2"]["sec"]), show=lambda S: not S["beam2"].get("same")),
        P("beam2.sec", "Section", show=lambda S: not S["beam2"].get("same")),
        P("beam2.mat", "Material", "sel", [(m, m) for m in MATS], show=lambda S: not S["beam2"].get("same")),
        P("beam2.L", "L: Length", "num", unit="mm", scale=1000.0, show=lambda S: not S["beam2"].get("same")),
        P("beam2.jointEnd", "Joint end (SAP)", "sel", [("End I", "I"), ("End J", "J")], show=lambda S: not S["beam2"].get("same")),
    ],
    "base": [
        P("_joint", "Joint", ro=True, calc=lambda S: "CB"),
        P("name", "Name"), P("desc", "Description"), P("group", "Display group"),
        G("Column"),
        P("_ctype", "Type", ro=True, calc=lambda S: _member_type(S["col"]["sec"])),
        P("col.sec", "Section"), P("col.mat", "Material", "sel", [(m, m) for m in MATS]),
        P("col.ox", "Longitudinal offset", "num", unit="mm"), P("col.oz", "Transversal offset", "num", unit="mm"),
        G("Base plate"),
        P("plate.N", "N: Longitudinal dimension", "num", unit="mm"), P("plate.B", "B: Transversal dimension", "num", unit="mm"),
        P("plate.tp", "Thickness", "num", unit="mm"), P("plate.mat", "Material", "sel", [(m, m) for m in MATS]),
        G("Support"),
        P("ped.isPed", "With pedestal", "sel", YN),
        P("ped.N2", "Longitudinal dimension", "num", unit="mm"), P("ped.B2", "Transversal dimension", "num", unit="mm"),
        P("ped.h", "Thickness", "num", unit="mm"), P("ped.mat", "Material", "sel", [(k, k) for k in BE.CONC_MATS]),
        P("ped.groutOn", "Include grouting", "sel", YN),
        G("Anchor"),
        P("anchor.layout", "Anchor position", "sel", [(v, k) for k, v in BE.LAYOUTS.items()]),
        P("anchor.nr", "Rows number per side", "sel", [("1", 1), ("2", 2), ("3", 3)]),
        P("anchor.npr", "Anchors per row", "sel", [(str(i), i) for i in range(1, 6)]),
        P("anchor.d", "Anchor", "sel", [(BE.anchor_label(d), d) for d in BE.ANCHOR_DIAS]),
        P("anchor.hef", "Effective embedment depth", "num", unit="mm"),
        P("anchor.grade", "Material", "sel", [(g, g) for g in BE.ANCHOR_GRADES]),
        P("anchor.cracked", "Cracked concrete", "sel", YN),
        P("lug.on", "Include shear lug", "sel", YN),
    ],
}

# Bảng Loads theo từng kiểu nút: (khoá, tiêu đề, nhóm)
LOAD_SPEC = {
    "knee": [("name", "Condition", ""), ("Vb", "V2", "Beam"), ("Nb", "Axial", "Beam"), ("Mb", "M33", "Beam"),
             ("Vc", "V2", "Column"), ("Nc", "Axial", "Column"), ("Mc", "M33", "Column")],
    "splice": [("name", "Condition", ""), ("V", "V2", "Left beam (at splice)"), ("N", "Axial", "Left beam (at splice)"),
               ("M", "M33", "Left beam (at splice)")],
    "base": [("name", "Description", "Load"), ("N", "Axial [kN]", "Column"), ("V2", "V2 [kN]", "Column"), ("V3", "V3 [kN]", "Column"),
             ("M22", "M2 [kN*m]", "Column"), ("M33", "M3 [kN*m]", "Column")],
}
LOAD_TITLE = {"knee": "Beam(s) - Column(s)", "splice": "Beam(s)", "base": "Column"}
LOAD_HELP = {
    "knee": [("Beam loads", ""),
             ("", "V2: lực cắt tại đầu kèo truyền qua liên kết (kN)."),
             ("", "Axial: lực dọc kèo, dương là kéo (kN)."),
             ("", "M33: mô men tại đầu kèo (kN·m). M33 < 0 → cánh NGOÀI chịu kéo (quy ước RAM / SAP)."),
             ("Column loads", ""),
             ("", "V2, Axial, M33 của cột tại đỉnh cột (cùng tổ hợp). Dùng cho knee ngang (bản trên đỉnh cột) và vùng panel."),
             ("Đơn vị", "kN, kN·m. Dán từ Excel theo thứ tự cột: Condition, V2, Axial, M33 (kèo), V2, Axial, M33 (cột).")],
    "splice": [("Beam loads", ""),
               ("", "V2: lực cắt tại mặt nối (kN)."),
               ("", "Axial: lực dọc, dương là kéo (kN). Lực nén làm giảm Mu,eq nếu bật tuỳ chọn như RAM."),
               ("", "M33: mô men tại mặt nối (kN·m). M33 > 0 → cánh DƯỚI chịu kéo; M33 < 0 → cánh TRÊN chịu kéo."),
               ("Apex", "Nhập nội lực của một kèo theo trục kèo; tool tự quy đổi về hệ trục bản đầu đứng."),
               ("Đơn vị", "kN, kN·m. Dán từ Excel theo thứ tự cột: Condition, V2, Axial, M33.")],
    "base": [("Column loads", ""),
             ("", "Axial: lực dọc cột tại chân, dương là kéo (nhổ), âm là nén (kN) — như SAP."),
             ("", "V2: lực cắt theo phương N (chiều cao tiết diện, cánh cột) · V3: theo phương B (kN)."),
             ("", "M3: mô men quanh trục mạnh (kN·m), M3 > 0 → mép +x (phía cánh trên) chịu nén. "
                  "M2: quanh trục yếu, M2 > 0 → mép +z chịu nén."),
             ("Đơn vị", "kN, kN·m. Dán từ Excel theo thứ tự cột như RAM: Description, Axial, V2, V3, M2, M3.")],
}

# Help: (tiêu đề, mô tả, [(liên kết, V2, V3, Axial, M3, có trong tool?)])
HELP = {
    "knee": ("Tapered Beam to Tapered Column (Knee) Joint (BCF)",
             "Nút khung cổng: kèo (có thể vát) nối vào đỉnh cột (có thể vát) bằng bản đầu bu lông. Kiểu bản: đứng (Vertical), "
             "vuông góc kèo (Perpendicular) hoặc nằm ngang trên đỉnh cột (Horizontal). Kiểm tra theo AISC 360-10 + DG4 / DG16 / DG39.",
             [("Moment end plate (Knee)", "X", "", "X", "X", True), ("Mitred knee HSS (MKHSS)", "X", "", "X", "X", False),
              ("Directly welded (FW)", "X", "", "X", "X", False)]),
    "splice": ("Beam Splice Joint (BS)",
               "Nối hai dầm (thẳng) hoặc hai kèo đối xứng ở đỉnh mái (Apex) bằng hai bản đầu bu lông áp vào nhau. "
               "Kiểm tra theo AISC 360-10 + DG4 / DG16 / DG39; mỗi bản có bề dày và vật liệu riêng.",
               [("Moment end plate (MEP)", "X", "", "X", "X", True), ("Flange plate + web plate splice (FP)", "X", "", "X", "X", False),
                ("Directly welded (DW)", "X", "", "X", "X", False)]),
    "base": ("Column Base Joint (CB)",
             "Chân cột chữ I hàn lên bản đế, neo vào bệ bê tông bằng bu lông neo. Nén + mô men theo AISC Design Guide 1 (2006), "
             "bản đế, neo (AISC 360-10 J3), neo trong bê tông (ACI 318-11 App. D), truyền cắt bằng ma sát / neo / bản chắn cắt, "
             "hàn cột – bản đế. Bản đế, neo, bệ chi tiết hơn nhập ở cửa sổ Edit.",
             [("Base plate (BP)", "X", "X", "X", "X", True), ("Base plate with stiffeners", "X", "X", "X", "X", False),
              ("Embedded column base", "X", "X", "X", "X", False)]),
}


def _get(S, path):
    d = S
    for k in path.split("."):
        d = d[k]
    return d


def _set(S, path, v):
    ks = path.split(".")
    d = S
    for k in ks[:-1]:
        d = d.setdefault(k, {})
    d[ks[-1]] = v


class PropertyGrid(ttk.Frame):
    """Bảng Property / Value như RAM: nhấp vào ô Value để sửa (ô nhập hoặc danh sách chọn)."""

    def __init__(self, master, spec, S, on_change=None):
        super().__init__(master)
        self.spec, self.S, self.on_change = spec, S, on_change
        st = ttk.Style()
        st.configure("PG.Treeview", rowheight=22, font=("Segoe UI", 9), background="#D6DCE4", fieldbackground="#D6DCE4")
        st.configure("PG.Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#8A95A3", foreground="#FFFFFF")
        st.map("PG.Treeview", background=[("selected", "#FFC48C")], foreground=[("selected", "#1B2430")])
        tv = self.tv = ttk.Treeview(self, columns=("v",), style="PG.Treeview", selectmode="browse")
        tv.heading("#0", text="Property"); tv.heading("v", text="Value")
        tv.column("#0", width=250); tv.column("v", width=180)
        tv.tag_configure("grp", font=("Segoe UI", 9, "bold underline"))
        tv.tag_configure("ro", foreground="#4B5563")
        tv.tag_configure("odd", background="#D6DCE4")
        sb = ttk.Scrollbar(self, orient="vertical", command=tv.yview); tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        tv.bind("<ButtonRelease-1>", self._click)
        self._ed = None
        self.fill()

    def _text(self, r):
        if r.get("calc"): return r["calc"](self.S)
        v = _get(self.S, r["p"])
        if r["k"] == "sel":
            return next((lab for lab, key in r["opts"] if key == v or str(key) == str(v)), str(v))
        if r["k"] == "num":
            x = float(v) * r["scale"]
            return f"{x:g} {r['unit']}".strip()
        return "" if v is None else str(v)

    def fill(self):
        tv = self.tv
        tv.delete(*tv.get_children())
        for i, r in enumerate(self.spec):
            if r.get("show") and not r["show"](self.S): continue
            if r["k"] == "grp":
                tv.insert("", "end", text=r["l"], values=("",), tags=("grp",)); continue
            tv.insert("", "end", iid=str(i), text=("    " if i > 0 and any(x["k"] == "grp" for x in self.spec[:i]) else "") + r["l"],
                      values=(self._text(r),), tags=("ro",) if r.get("ro") else ())

    def _click(self, e):
        if self._ed: self._commit()
        iid = self.tv.identify_row(e.y)
        if not iid or not iid.isdigit() or self.tv.identify_column(e.x) != "#1": return
        r = self.spec[int(iid)]
        if r.get("ro"): return
        x, y, w, h = self.tv.bbox(iid, "v")
        if r["k"] == "sel":
            ed = ttk.Combobox(self.tv, values=[lab for lab, _ in r["opts"]], state="readonly", font=("Segoe UI", 9))
            ed.set(self._text(r))
            ed.bind("<<ComboboxSelected>>", lambda _e: self._commit())
        else:
            ed = ttk.Entry(self.tv, font=("Segoe UI", 9))
            v = _get(self.S, r["p"])
            ed.insert(0, f"{float(v) * r['scale']:g}" if r["k"] == "num" else str(v or ""))
            ed.select_range(0, "end")
            ed.bind("<Return>", lambda _e: self._commit()); ed.bind("<FocusOut>", lambda _e: self._commit())
        ed.bind("<Escape>", lambda _e: self._cancel())
        ed.place(x=x, y=y, width=w, height=h); ed.focus_set()
        self._ed = (ed, r)

    def _cancel(self):
        if self._ed:
            self._ed[0].destroy(); self._ed = None

    def _commit(self):
        if not self._ed: return
        ed, r = self._ed
        self._ed = None
        txt = ed.get(); ed.destroy()
        if r["k"] == "sel":
            v = next((key for lab, key in r["opts"] if lab == txt), None)
            if v is None: return
        elif r["k"] == "num":
            try: v = float(txt.replace(",", ".").split()[0]) / r["scale"]
            except (ValueError, IndexError): return
        else:
            v = txt
        _set(self.S, r["p"], v)
        if self.on_change: self.on_change(r["p"])
        self.fill()


_SAP = {}          # kết nối SAP2000 dùng chung giữa các lần mở hộp thoại


class BaseSapPanel(tk.LabelFrame):
    """
    Lấy PHẢN LỰC gối chân cột từ SAP2000 → bảng tải như RAM (Mmax, Pmax, Vmax, Mmin, Pmin;
    chân cột không lấy mô men: Mmax / Mmin = 0).
    Phản lực đổi sang lực cột tác dụng lên bản đế trong hệ trục cột (quy ước RAM: N < 0 nén, V2/M33 phương chính);
    ô "Đổi dấu" để lật từng thành phần nếu quy ước chiều dương khác.
    """

    SIGN_KEYS = (("N", "Axial"), ("V2", "V2"), ("V3", "V3"), ("M22", "M2"), ("M33", "M3"))

    def __init__(self, master, S, grid):
        super().__init__(master, text=" Lấy phản lực chân cột từ SAP2000 ", bg="#FFFFFF", fg="#1B2430", font=("Segoe UI", 9, "bold"))
        self.S, self.grid_ = S, grid
        cfg = S.setdefault("sap", {})
        cfg.setdefault("signs", {k: 1 for k, _ in self.SIGN_KEYS})
        self.cfg = cfg
        r1 = tk.Frame(self, bg="#FFFFFF"); r1.pack(fill="x", pady=2)
        ttk.Button(r1, text="Kết nối SAP2000", command=self._connect).pack(side="left", padx=3)
        self.lbl = tk.Label(r1, text="Chưa kết nối", bg="#FFFFFF", fg="#B42318", font=("Segoe UI", 9)); self.lbl.pack(side="left", padx=6)
        r2 = tk.Frame(self, bg="#FFFFFF"); r2.pack(fill="x", pady=2)
        tk.Label(r2, text="Nguồn tải", bg="#FFFFFF", font=("Segoe UI", 9)).pack(side="left", padx=3)
        self.src = tk.StringVar(value=cfg.get("source", "Design Combos"))
        cb = ttk.Combobox(r2, textvariable=self.src, values=list(self._menu()), state="readonly", width=16); cb.pack(side="left", padx=3)
        cb.bind("<<ComboboxSelected>>", lambda _e: self._source_changed())
        self.btn_pick = ttk.Button(r2, text="nguồn ▾", command=self._pick); self.btn_pick.pack(side="left", padx=3)
        r3 = tk.Frame(self, bg="#FFFFFF"); r3.pack(fill="x", pady=2)
        tk.Label(r3, text="Đổi dấu", bg="#FFFFFF", font=("Segoe UI", 9)).pack(side="left", padx=3)
        self.flip = {}
        for k, t in self.SIGN_KEYS:
            v = self.flip[k] = tk.BooleanVar(value=float(cfg["signs"].get(k, 1)) < 0)
            tk.Checkbutton(r3, text=t, variable=v, bg="#FFFFFF", font=("Segoe UI", 9), command=self._save_signs).pack(side="left")
        r4 = tk.Frame(self, bg="#FFFFFF"); r4.pack(fill="x", pady=2)
        self.replace = tk.BooleanVar(value=cfg.get("replace", True))
        tk.Checkbutton(r4, text="Thay bảng tải", variable=self.replace, bg="#FFFFFF", font=("Segoe UI", 9)).pack(side="left")
        ttk.Button(r4, text="Lấy phản lực (nút / cột đang chọn)", command=self._get).pack(side="right", padx=3)
        tk.Label(self, text="Chọn nút chân cột (hoặc cột) trong SAP rồi bấm Lấy phản lực. Axial: lực cột lên bản đế (< 0 nén); "
                            "V2, V3 giữ dấu phản lực SAP (trục 2, 3 của cột); Mmax / Mmin = 0 (chân cột không lấy mô men).",
                 bg="#FFFFFF", fg="#5B6777", font=("Segoe UI", 8), wraplength=400, justify="left").pack(fill="x", padx=3, pady=(0, 3))
        self._all, self._modal, self._chosen = [], set(), None
        if self._conn() and self._conn().is_connected:
            self._on_connected()

    # ------------------------------------------------------------------
    @staticmethod
    def _menu():
        import scanner  # noqa: F401  (thêm đường dẫn "Lấy nội lực")
        from sap2000_connector import LOAD_CASES, LOAD_CASES_AND_DESIGN, LOAD_COMBOS, LOAD_DESIGN_COMBOS
        return {"Design Combos": LOAD_DESIGN_COMBOS, "Load Cases": LOAD_CASES,
                "Cases + Design": LOAD_CASES_AND_DESIGN, "Combos (tất cả)": LOAD_COMBOS}

    def _conn(self, create=False):
        if "conn" not in _SAP and create:
            import scanner  # noqa: F401  (thêm đường dẫn "Lấy nội lực")
            from sap2000_connector import SAP2000Connector
            _SAP["conn"] = SAP2000Connector()
        return _SAP.get("conn")

    def _src(self):
        return self._menu().get(self.src.get(), "4")

    def _save_signs(self):
        self.cfg["signs"] = {k: (-1 if v.get() else 1) for k, v in self.flip.items()}

    def _connect(self):
        from tkinter import messagebox
        try:
            conn = self._conn(create=True)
            msg = conn.connect()
        except Exception as e:  # noqa: BLE001
            msg = str(e)
        if msg != "OK":
            self.lbl.configure(text="Lỗi kết nối", fg="#B42318"); messagebox.showerror("SAP2000", msg, parent=self); return False
        self._on_connected(); return True

    def _on_connected(self):
        conn = self._conn()
        conn.set_units_kn_m()
        self.lbl.configure(text="Đã kết nối (kN-m)", fg="#1F7A1F")
        self._source_changed()

    def _source_changed(self):
        self.cfg["source"] = self.src.get()
        conn = self._conn()
        if not conn or not conn.is_connected: return
        from sap2000_connector import default_selected_loads
        self._all, modal = conn.list_load_names(self._src())
        self._modal = set(modal)
        self._chosen = default_selected_loads(self._all, self._modal, self._src())
        self.btn_pick.configure(text=f"{len(self._chosen)} nguồn ▾")

    def _pick(self):
        from tkinter import messagebox
        conn = self._conn()
        if not conn or not conn.is_connected:
            messagebox.showinfo("Chưa kết nối", "Kết nối SAP2000 trước.", parent=self); return
        if not self._all: self._source_changed()
        from gui_widgets import LoadSourcePicker

        def apply(ch):
            self._chosen = list(ch); self.btn_pick.configure(text=f"{len(ch)} nguồn ▾")
        p = LoadSourcePicker(self, names=self._all, selected=self._chosen or [], modal_names=self._modal,
                             on_apply=apply, title=f"Chọn nguồn tải — {self.src.get()}")
        p.place_near(self.btn_pick); self._picker = p

    def _get(self):
        from tkinter import messagebox
        import scanner
        conn = self._conn()
        if not conn or not conn.is_connected:
            if not self._connect(): return
            conn = self._conn()
        src = self._src()
        if self._chosen is None: self._source_changed()
        try:
            chosen = set(conn.setup_output_source(src, self._chosen))
            cache = {}

            def allowed_for(frame):
                if frame not in cache: cache[frame] = conn.allowed_loads_for_frame(frame, src, chosen)
                return cache[frame]
            self._save_signs()
            recs, warn = scanner.base_reactions(conn, allowed_for, self.cfg["signs"])
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("SAP2000", f"Lỗi khi đọc SAP: {e}\n{conn.last_error}", parent=self); return
        if not recs:
            messagebox.showinfo("SAP2000", "Không lấy được phản lực.\nChọn nút gối chân cột (hoặc cột) trong SAP, "
                                "kiểm tra đã chạy phân tích và nguồn tải.\n" + "\n".join(warn), parent=self); return
        rows = [{k: r[k] for k in ("name", "N", "V2", "V3", "M22", "M33")} for r in scanner.base_extremes(recs)]
        self.cfg["replace"] = bool(self.replace.get())
        if self.replace.get(): self.S["loads"][:] = rows
        else: self.S["loads"].extend(rows)
        self.grid_.fill()
        joints = sorted({r["joint"] for r in recs})
        self.lbl.configure(text=f"{len(rows)} tải từ {len(recs)} kết quả · nút {', '.join(joints)}", fg="#1F7A1F")
        if warn: messagebox.showwarning("SAP2000", "\n".join(warn), parent=self)


class LoadGrid(ttk.Frame):
    """Bảng tải như bước Loads của RAM: Num · Condition · từng cấu kiện (V2, Axial, M33). Nhấp đúp để sửa."""

    def __init__(self, master, cols, S, title=""):
        super().__init__(master)
        self.cols, self.S = cols, S
        tk.Label(self, text=title, bg="#E5E7EB", fg="#1B2430", font=("Segoe UI", 9), anchor="w").pack(fill="x")
        bar = ttk.Frame(self); bar.pack(fill="x", pady=2)
        for t, cmd in (("Add", self.add), ("Delete", self.delete), ("Paste from Excel", self.paste)):
            ttk.Button(bar, text=t, command=cmd).pack(side="left", padx=3)
        self.lbl = ttk.Label(bar, text="nhấp đúp ô để sửa", foreground="#5B6777"); self.lbl.pack(side="left", padx=8)
        widths = [44] + [120] + [84] * (len(cols) - 1)
        heads = [("", "ID")] + [(g, h) for _k, h, g in cols]
        band = tk.Canvas(self, height=18, highlightthickness=0, background="#E5E7EB"); band.pack(fill="x")
        x, i = 0, 0
        while i < len(heads):
            g = heads[i][0]; w = widths[i]; j = i + 1
            while j < len(heads) and heads[j][0] == g and g: w += widths[j]; j += 1
            band.create_rectangle(x, 0, x + w, 18, outline="#C2C7CE", fill="#E5E7EB")
            if g: band.create_text(x + w / 2, 9, text=g, fill="#1B2430", font=("Segoe UI", 9))
            x += w; i = j
        st = ttk.Style()
        st.configure("LG.Treeview", rowheight=20, font=("Segoe UI", 9))
        st.configure("LG.Treeview.Heading", font=("Segoe UI", 9))
        tv = self.tv = ttk.Treeview(self, columns=["num"] + [c[0] for c in cols], show="headings", height=14, style="LG.Treeview")
        for k, (g, h), w in zip(["num"] + [c[0] for c in cols], heads, widths):
            tv.heading(k, text=h); tv.column(k, width=w, stretch=False, anchor="w" if k == "name" else ("center" if k == "num" else "e"))
        tv.tag_configure("odd", background="#F6F7F9")
        tv.pack(fill="both", expand=True)
        tv.bind("<Double-1>", self._edit)
        self.fill()

    def fill(self):
        self.tv.delete(*self.tv.get_children())
        for i, l in enumerate(self.S["loads"]):
            self.tv.insert("", "end", iid=str(i), tags=("odd",) if i % 2 else (),
                           values=[i + 1] + [(f"{float(l.get(k, 0) or 0):g}" if k != "name" else l.get(k, "")) for k, _, _ in self.cols])

    def add(self):
        row = {k: 0.0 for k, _, _ in self.cols}; row["name"] = f"LC{len(self.S['loads']) + 1}"
        self.S["loads"].append(row); self.fill()

    def delete(self):
        for iid in sorted((int(i) for i in self.tv.selection()), reverse=True):
            del self.S["loads"][iid]
        self.fill()

    def paste(self):
        try: raw = self.clipboard_get()
        except tk.TclError: raw = ""
        n = 0
        for line in raw.strip().splitlines():
            p = [x.strip() for x in line.replace(";", "\t").split("\t")]
            if p and p[0].isdigit() and len(p) > len(self.cols): p = p[1:]
            try:
                vals = [float(x.replace(",", ".")) for x in p[1:len(self.cols)]]
            except ValueError:
                continue
            if len(vals) < len(self.cols) - 1: continue
            row = {"name": p[0] or f"LC{len(self.S['loads']) + 1}"}
            row.update({k: v for (k, _, _), v in zip(self.cols[1:], vals)})
            self.S["loads"].append(row); n += 1
        self.fill()
        self.lbl.configure(text=f"Đã dán {n} tổ hợp." if n else "Clipboard không có dữ liệu hợp lệ.")

    def _edit(self, e):
        row, col = self.tv.identify_row(e.y), self.tv.identify_column(e.x)
        if not row or col == "#1": return
        key = self.cols[int(col[1:]) - 2][0]
        x, y, w, h = self.tv.bbox(row, col)
        ent = ttk.Entry(self.tv, font=("Segoe UI", 9)); ent.insert(0, str(self.S["loads"][int(row)].get(key, "")))
        ent.place(x=x, y=y, width=w, height=h); ent.focus_set(); ent.select_range(0, "end")

        def done(_e=None, save=True):
            if save:
                v = ent.get()
                if key != "name":
                    try: v = float(v.replace(",", "."))
                    except ValueError: v = 0.0
                self.S["loads"][int(row)][key] = v
            ent.destroy(); self.fill()
        ent.bind("<Return>", done); ent.bind("<FocusOut>", done); ent.bind("<Escape>", lambda _e: done(save=False))


def default_state(key: str, name: str = "") -> dict:
    """Thông số mặc định cho kiểu nút key."""
    if key == "knee":
        st = KD.merge(KD.BASE, {})
    elif key == "base":
        st = BD.merge(BD.BASE, {})
    else:
        st = SD.merge(SD.BASE, {"type": key.split(":")[1]})
        if st["type"] == "apex" and not st.get("slope"): st["slope"] = 10.0
    st.setdefault("desc", ""); st.setdefault("group", "Joints")
    if name: st["name"] = name
    return st


class NewJointDialog(tk.Toplevel):
    """Ba bước như RAM: Joint → Data → Loads. Dùng cả để sửa Data/Loads của nút có sẵn (start_page='data')."""

    def __init__(self, master, current: str | None = None, name: str = "", state: dict | None = None, start_page: str = "joint"):
        super().__init__(master)
        self.title("New joint")
        self.configure(bg=BG_DLG)
        self.geometry("1100x720")
        self.minsize(900, 600)
        self.transient(master)
        self.result = None
        self.name = name
        self.group, self.sel = 0, 5
        for gi, g in enumerate(GROUPS):
            for ji, j in enumerate(g[2]):
                if current and j[2] == current:
                    self.group, self.sel = gi, ji
        self.S = copy.deepcopy(state) if state else None
        self.page = None
        self._build()
        self._show(start_page if (state or start_page == "joint") else "joint")
        self.bind("<Escape>", lambda e: self.destroy())
        self.after(50, self._grab)

    def _grab(self):
        try:
            self.grab_set(); self.focus_set()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ khung chung
    def _build(self):
        head = tk.Frame(self, bg=BG_DLG); head.pack(fill="x")
        self.lbl_title = tk.Label(head, text="", bg=BG_DLG, fg="#8A8F96", font=("Segoe UI", 12))
        self.lbl_title.pack(pady=(8, 2))
        self.lbl_sel = tk.Label(head, text="", bg=BG_DLG, fg="#1B2430", font=("Segoe UI", 10), anchor="w")
        self.lbl_sel.pack(fill="x", padx=10, pady=(2, 8))
        tk.Frame(self, bg="#C9CDD2", height=1).pack(fill="x")
        self.body = tk.Frame(self, bg="#E9EBED"); self.body.pack(fill="both", expand=True, padx=8, pady=8)
        foot = tk.Frame(self, bg=BG_DLG); foot.pack(fill="x", padx=10, pady=8)
        self.lbl_note = tk.Label(foot, text="", bg=BG_DLG, fg="#B45309", font=("Segoe UI", 9), anchor="w")
        self.lbl_note.pack(side="left")
        self.btn = {}
        for txt in ("Help", "Cancel", "OK", "Next", "Back"):
            b = tk.Button(foot, width=9, font=("Segoe UI", 9), relief="groove")
            b.pack(side="right", padx=5); self.btn[txt] = b
        self.btn["Help"].configure(text="Help", command=self._help)
        self.btn["Cancel"].configure(text="Cancel", command=self.destroy)
        self.btn["OK"].configure(text="OK", command=self._ok)

    def _show(self, page):
        for w in self.body.winfo_children(): w.destroy()
        self.page = page
        if page != "joint" and self.S is None:
            self.S = default_state(self._key(), self.name)
        getattr(self, "_page_" + page)()
        b = self.btn
        if page == "joint":
            b["Back"].configure(text="Joint", state="disabled", command=lambda: None)
            b["Next"].configure(text="Data »", state="normal", command=lambda: self._next("data"))
        elif page == "data":
            b["Back"].configure(text="« Joint", state="normal" if self._new else "disabled", command=lambda: self._show("joint"))
            b["Next"].configure(text="Loads »", state="normal", command=lambda: self._show("loads"))
        else:
            b["Back"].configure(text="« Data", state="normal", command=lambda: self._show("data"))
            b["Next"].configure(text="Loads »", state="disabled", command=lambda: None)

    @property
    def _new(self):
        return not getattr(self, "_edit_mode", False)

    def _key(self):
        js = self._joints()
        return js[self.sel][2] if js and self.sel < len(js) else None

    def _kind(self):
        k = self._key() or ""
        return k if k in ("knee", "base") else "splice"

    def _next(self, page):
        key = self._key()
        if not key:
            self.lbl_note.configure(text=UNSUPPORTED); return
        if self.S is not None and self.S.get("_key") != key:
            self.S = None
        if self.S is None:
            self.S = default_state(key, self.name); self.S["_key"] = key
        self._show(page)

    # ------------------------------------------------------------------ trang 1: Joint
    def _page_joint(self):
        left = tk.Frame(self.body, bg=BG_GROUP, width=258); left.pack(side="left", fill="y"); left.pack_propagate(False)
        tk.Label(left, text="Joint group", bg=BG_GROUP, fg="#1B2430", font=("Segoe UI", 17)).pack(anchor="w", padx=12, pady=(10, 4))
        self.group_cv = []
        for i in range(len(GROUPS)):
            cv = tk.Canvas(left, width=228, height=78, bg=BG_GROUP, highlightthickness=0, cursor="hand2")
            cv.pack(padx=12, pady=3)
            cv.bind("<Button-1>", lambda e, i=i: self._pick_group(i))
            self.group_cv.append(cv)
        right = tk.Frame(self.body, bg=BG_JOINTS); right.pack(side="left", fill="both", expand=True)
        self.lbl_group = tk.Label(right, text="", bg=BG_JOINTS, fg="#1B2430", font=("Segoe UI", 17))
        self.lbl_group.pack(anchor="w", padx=22, pady=(10, 6))
        self.tiles = tk.Canvas(right, bg=BG_JOINTS, highlightthickness=0)
        self.tiles.pack(fill="both", expand=True, padx=12)
        sx = tk.Scrollbar(right, orient="horizontal", command=self.tiles.xview)
        self.tiles.configure(xscrollcommand=sx.set); sx.pack(fill="x")
        self._refresh()

    def _joints(self):
        return GROUPS[self.group][2]

    def _pick_group(self, i):
        self.group = i
        js = self._joints()
        self.sel = next((k for k, j in enumerate(js) if j[2]), 0)
        self._refresh()

    def _pick(self, i):
        self.sel = i
        self._refresh()

    def _refresh(self):
        for i, cv in enumerate(self.group_cv):
            cv.delete("all")
            on = i == self.group
            cv.create_rectangle(1, 1, 226, 76, fill=TILE_BG, outline=(ORANGE if on else TILE_BORDER), width=(3 if on else 1))
            if on: _gradient(cv, 3, 3, 224, 74)
            icon(cv, GROUPS[i][1], 12, 16, 44, 44)
            cv.create_text(80, 39, text=GROUPS[i][0], anchor="w", font=("Segoe UI", 11), fill="#1B2430", width=140)
        self.lbl_group.configure(text=GROUPS[self.group][0])
        cv = self.tiles
        cv.delete("all")
        for i, (name, code, key, ic) in enumerate(self._joints()):
            x = 4 + (i // ROWS) * (TILE_W + 16); y = 4 + (i % ROWS) * (TILE_H + 14)
            on, ok = i == self.sel, key is not None
            cv.create_rectangle(x, y, x + TILE_W, y + TILE_H, fill=TILE_BG, outline=(ORANGE if on else TILE_BORDER), width=(3 if on else 1))
            if on and ok: _gradient(cv, x + 2, y + 2, x + TILE_W - 2, y + TILE_H - 2)
            icon(cv, ic, x + 12, y + 22, 58, 40)
            fg = "#1B2430" if ok else "#9AA0A6"
            cv.create_text(x + 84, y + TILE_H / 2 + 4, text=name, anchor="w", width=TILE_W - 92, font=("Segoe UI", 9), fill=fg)
            cv.create_text(x + TILE_W - 8, y + 12, text=code, anchor="e", font=("Segoe UI", 11), fill=fg)
            hit = cv.create_rectangle(x, y, x + TILE_W, y + TILE_H, outline="", fill="")
            cv.tag_bind(hit, "<Button-1>", lambda e, i=i: self._pick(i))
            cv.tag_bind(hit, "<Double-Button-1>", lambda e, i=i: (self._pick(i), self._next("data")))
        n = len(self._joints())
        cv.configure(scrollregion=(0, 0, 8 + ((n - 1) // ROWS + 1) * (TILE_W + 16), 8 + ROWS * (TILE_H + 14)))
        js = self._joints()
        if js and self.sel < len(js):
            name, code, key, _ = js[self.sel]
            self.lbl_title.configure(text=f"{code} - {FAMILY.get(code, code)}")
            self.lbl_sel.configure(text=f"Selected joint: {name}")
            self.lbl_note.configure(text="" if key else "Kiểu nút này chưa được hỗ trợ trong tool.")

    # ------------------------------------------------------------------ trang 2: Data
    def _page_data(self):
        kind = self._kind()
        code = CODE[kind]
        self.lbl_title.configure(text=f"{code} - {FAMILY[code]}")
        self.lbl_sel.configure(text="Data")
        self.lbl_note.configure(text="")
        pg = PropertyGrid(self.body, DATA_SPEC[kind], self.S, on_change=self._data_changed)
        pg.pack(side="left", fill="both", expand=True, padx=(4, 8))
        self._help_panel(kind)

    def _data_changed(self, path):
        if path == "type" and self.S.get("type") == "apex" and not float(self.S.get("slope") or 0):
            self.S["slope"] = 10.0
        if path in ("type",):
            js = self._joints()
            for i, j in enumerate(js):
                if j[2] == f"splice:{self.S['type']}": self.sel = i
            self.S["_key"] = f"splice:{self.S['type']}"

    def _help_panel(self, kind):
        fr = tk.Frame(self.body, bg="#FFFFFF", width=430); fr.pack(side="left", fill="both")
        fr.pack_propagate(False)
        tk.Label(fr, text="Help", bg="#D9DCE1", fg="#1B2430", font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x")
        t = tk.Text(fr, wrap="word", relief="flat", padx=10, pady=8, font=("Segoe UI", 10), background="#FFFFFF")
        t.pack(fill="both", expand=True)
        title, desc, rows = HELP[kind]
        t.tag_configure("h", font=("Segoe UI", 17), foreground="#18212F", spacing3=6)
        t.tag_configure("d", foreground="#5B6777")
        t.tag_configure("th", font=("Consolas", 9, "bold"), background="#E5E7EB")
        t.tag_configure("tr", font=("Consolas", 9))
        t.tag_configure("na", font=("Consolas", 9), foreground="#9AA0A6")
        t.insert("end", title + "\n", "h"); t.insert("end", desc + "\n\n", "d")
        t.insert("end", f"{'CONNECTION':<30}{'V2':>4}{'V3':>4}{'Axial':>6}{'M3':>4}\n", "th")
        for name, v2, v3, ax, m3, ok in rows:
            t.insert("end", f"{name[:29]:<30}{v2:>4}{v3:>4}{ax:>6}{m3:>4}\n", "tr" if ok else "na")
        t.insert("end", "\nChữ xám: kiểu liên kết chưa có trong tool.\n", "d")
        t.configure(state="disabled")

    # ------------------------------------------------------------------ trang 3: Loads
    def _page_loads(self):
        kind = self._kind()
        code = CODE[kind]
        self.lbl_title.configure(text=f"{code} - {FAMILY[code]}")
        self.lbl_sel.configure(text="Loads")
        self.lbl_note.configure(text="")
        grid = LoadGrid(self.body, LOAD_SPEC[kind], self.S, LOAD_TITLE[kind])
        grid.pack(side="left", fill="both", expand=True, padx=(4, 8), pady=4)
        fr = tk.Frame(self.body, bg="#FFFFFF", width=430); fr.pack(side="left", fill="both"); fr.pack_propagate(False)
        tk.Label(fr, text="Help", bg="#D9DCE1", fg="#1B2430", font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x")
        if kind == "base":
            BaseSapPanel(fr, self.S, grid).pack(side="bottom", fill="x", padx=6, pady=6)
        t = tk.Text(fr, wrap="word", relief="flat", padx=10, pady=8, font=("Segoe UI", 10), background="#FFFFFF"); t.pack(fill="both", expand=True)
        t.tag_configure("h", font=("Segoe UI", 18)); t.tag_configure("h2", font=("Segoe UI", 13), spacing1=8)
        t.tag_configure("d", foreground="#5B6777", spacing3=6)
        t.insert("end", "Loads\n", "h")
        for a, b in LOAD_HELP[kind]:
            if a and not b: t.insert("end", a + "\n", "h2")
            elif a: t.insert("end", a + ": ", "h2"); t.insert("end", b + "\n", "d")
            else: t.insert("end", b + "\n", "d")
        t.configure(state="disabled")

    # ------------------------------------------------------------------
    def _ok(self):
        if self.page == "joint":
            if not self._key():
                self.lbl_note.configure(text=UNSUPPORTED); return
            if self.S is None or self.S.get("_key") != self._key():
                self.S = default_state(self._key(), self.name); self.S["_key"] = self._key()
        st = copy.deepcopy(self.S); key = st.pop("_key", None) or self._key()
        self.result = dict(key=key, kind=key if key in ("knee", "base") else "splice", state=st)
        self.destroy()

    def _help(self):
        self.lbl_note.configure(text="Joint: chọn kiểu nút · Data: tiết diện, vật liệu, hình học · Loads: nội lực tại nút. "
                                     "Bản đầu, bu lông, hàn nhập ở bước thiết kế (Edit).")


def ask(master, current: str | None = None, name: str = ""):
    """Tạo nút mới: trả dict(key, kind, state) hoặc None."""
    d = NewJointDialog(master, current, name)
    master.wait_window(d)
    return d.result


def edit_data(master, kind: str, state: dict, page: str = "data"):
    """Sửa Data / Loads của nút có sẵn. Trả state mới hoặc None."""
    key = kind if kind in ("knee", "base") else f"splice:{state.get('type', 'straight')}"
    d = NewJointDialog(master, key, state.get("name", ""), dict(state, _key=key), start_page=page)
    d._edit_mode = True
    d._show(page)
    master.wait_window(d)
    return d.result["state"] if d.result else None
