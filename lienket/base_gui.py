"""
base_gui.py — Form nhập CHÂN CỘT (Column base — CB) cho Connection Pad, theo thứ tự & nhãn của RAM Connection "Base plate":
General information → Members (Column) → Base plate (Connector, Weld) → Anchors → Concrete support → Shear transfer → Options.
Rê chuột lên nhãn để xem chú thích tiếng Việt.
"""

from __future__ import annotations

import base_engine as BE
import engine as K

MATS = list(K.MATERIALS)


def num(p, l, u="mm", show=None): return dict(k="num", p=p, l=l, u=u, show=show)
def txt(p, l, show=None): return dict(k="txt", p=p, l=l, show=show)
def sel(p, l, opts, show=None): return dict(k="sel", p=p, l=l, opts=[o if isinstance(o, tuple) else (o, str(o)) for o in opts], show=show)
def chk(p, l, show=None): return dict(k="chk", p=p, l=l, show=show)
def sub(l, show=None): return dict(k="sub", l=l, show=show)
def info(p, show=None): return dict(k="info", p=p, show=show)
def btn(l, cmd): return dict(k="btn", l=l, cmd=cmd, show=None)
def note(l, show=None): return dict(k="note", l=l, show=show)


def tip(spec, text):
    spec["tip"] = text
    return spec


def build_sections(app):
    S = lambda: app.S
    shear = lambda *v: S()["shear"].get("mode") in v
    reinf = lambda: bool(S()["ped"].get("reinf"))
    ELEC = list(K.ELECTRODES)
    return [
        ("General information", True, [
            sub("Analysis"),
            btn("Loads   <Loads>  →  mở bảng tải", lambda: app.tabs.set("Loads")),
            sub("Design criteria"),
            tip(sel("gen.designCode", "Design code", ["AISC 2010 LRFD", "AISC 2016 LRFD"]), "Tiêu chuẩn thiết kế (LRFD). AISC 2016: Fnv neo = 0.45Fu / 0.563Fu"),
            sub("Construction criteria"),
            tip(chk("opt.bear", "Column finished to bear"), "Đầu cột mài phẳng tì lên bản đế: lực nén truyền bằng tì ép, hàn chỉ chịu kéo + cắt"),
            tip(chk("opt.sheared", "Consider sheared edges"), "Mép bản cắt bằng cưa/đột → khoảng cách mép tối thiểu lớn hơn (J3.4)"),
            tip(chk("opt.aci", "Check anchors in concrete (ACI 318-11 App. D)"), "Kiểm tra phá hoại bê tông quanh neo theo ACI 318-11 Phụ lục D"),
        ]),
        ("Members", True, [
            sub("Column"),
            tip(txt("col.sec", "Section"), "Quy cách tiết diện — 400.8-200.12 (bụng 400×8, cánh 200×12) hoặc (300-500).6-200.10 (vát)"), info("col.sec"),
            sel("col.mat", "Material", MATS),
            tip(num("col.L", "Length", "m"), "Chiều dài cột (chỉ dùng cho tiết diện vát)"),
            tip(sel("col.jointEnd", "Joint end (SAP)", [("I", "End I (bottom)"), ("J", "End J")]), "Đầu cột tại chân (chỉ dùng cho tiết diện vát)"),
            note("Cánh trên (+2) của cột nằm ở phía +x (phải) trên hình."),
        ]),
        ("Base plate", True, [
            sub("Connector"),
            tip(num("plate.N", "N: Length (along column depth)"), "Chiều dài bản đế theo phương chiều cao tiết diện cột (uốn M33)"),
            tip(num("plate.B", "B: Width (along flanges)"), "Bề rộng bản đế theo phương bề rộng cánh (uốn M22)"),
            num("plate.tp", "tp: Thickness"), sel("plate.mat", "Material", MATS),
            sub("Weld"),
            sel("weld.electrode", "Electrode", ELEC),
            tip(num("weld.fl.D", "D1: Weld size to flanges (1/16in)", "/16"), "Cỡ hàn góc cánh cột theo 1/16 inch (5 → 7.9 mm)"),
            tip(num("weld.web.D", "D2: Weld size to web (1/16in)", "/16"), "Cỡ hàn góc bụng cột theo 1/16 inch"),
        ]),
        ("Anchors", True, [
            sub("Anchor rods"),
            sel("anchor.grade", "Grade", list(BE.ANCHOR_GRADES)),
            sel("anchor.d", "Diameter", [(d, f"M{d}") for d in BE.ANCHOR_DIAS]),
            sel("anchor.thread", "Threads", [("N", "N — included"), ("X", "X — excluded")]),
            tip(num("anchor.hef", "hef: Embedment depth"), "Chiều sâu chôn hiệu quả (tới mặt chịu lực của đầu neo)"),
            tip(sel("anchor.head", "Embedded end", [("hex", "Heavy hex nut"), ("plate", "Anchor plate")]), "Đầu neo trong bê tông: đai ốc lục giác nặng hoặc bản đầu neo"),
            num("anchor.plateB", "Anchor plate size", show=lambda: S()["anchor"].get("head") == "plate"),
            sub("Layout"),
            tip(sel("anchor.nx", "Anchors along N (columns)", [2, 3, 4]), "Số neo theo phương N; neo chỉ đặt trên chu vi lưới"),
            tip(sel("anchor.ny", "Anchors along B (rows)", [2, 3, 4]), "Số neo theo phương B"),
            tip(num("anchor.ex", "ex: Edge distance (N direction)"), "Từ tâm neo tới mép bản theo phương N. Neo đặt trong hai cánh khi N/2 − ex < d/2 − tf"),
            tip(num("anchor.ey", "ey: Edge distance (B direction)"), "Từ tâm neo tới mép bản theo phương B"),
            sub("Plate washers"),
            tip(num("anchor.washer", "Washer size"), "Cạnh long đen tấm (DG1 Table 2.3)"), num("anchor.washerT", "Washer thickness"),
            sub("Shear"),
            tip(chk("anchor.shearAll", "All anchors resist shear"), "Bỏ chọn: chỉ một nửa số neo chịu cắt (lỗ quá cỡ, DG1 §3.5.2)"),
            tip(chk("anchor.torqued", "Torqued anchors"), "Neo được siết: khoảng cách mép bệ ≥ 6da (ACI D.8.2)"),
        ]),
        ("Concrete support", True, [
            sub("Pedestal"),
            tip(num("ped.N2", "N2: Length"), "Kích thước bệ theo phương N (đồng tâm với bản đế)"),
            tip(num("ped.B2", "B2: Width"), "Kích thước bệ theo phương B"), num("ped.h", "h: Height"),
            num("ped.fc", "f'c: Concrete strength", "MPa"), tip(num("ped.grout", "Grout thickness"), "Lớp vữa không co ngót"),
            tip(chk("ped.cracked", "Cracked concrete"), "Bê tông nứt (thiên an toàn): ψc = 1.0 thay vì 1.25 / 1.4"),
            tip(num("ped.lw", "λ: Lightweight factor", ""), "1.0 bê tông thường"),
            sub("Anchor reinforcement"),
            tip(chk("ped.reinf", "Anchor reinforcement"), "Có cốt thép neo ôm neo (D.5.2.9 / D.6.2.9): thay kiểm tra phá vỡ bê tông bằng kiểm tra cốt thép"),
            num("ped.fyr", "fy: Reinforcement yield", "MPa", show=reinf),
            tip(num("ped.AsN", "As (tension)", "mm²", show=reinf), "Tổng diện tích cốt thép neo hiệu quả khi kéo (vd 8Ø16 = 1608)"),
            tip(num("ped.AsV", "As (shear)", "mm²", show=reinf), "Tổng diện tích cốt thép neo hiệu quả khi cắt (đai / chữ U)"),
        ]),
        ("Shear transfer", True, [
            tip(sel("shear.mode", "Shear resisted by", [("friction", "Friction"), ("anchors", "Anchors"), ("lug", "Shear lug")]),
                "Ma sát bản đế – vữa (DG1 §3.5.1) · Bu lông neo · Bản chắn cắt (DG1 §3.5.3)"),
            tip(num("shear.mu", "μ: Friction coefficient", "", show=lambda: shear("friction")), "0.55 thép trên vữa (DG1)"),
            sub("Shear lug", show=lambda: shear("lug")),
            tip(num("lug.bl", "Width (perpendicular to V2)", show=lambda: shear("lug")), "Bề rộng bản chắn cắt — mặt ép vuông góc V2"),
            tip(num("lug.H", "Height (below base plate)", show=lambda: shear("lug")), "Chiều cao bản chắn tính từ đáy bản đế (gồm lớp vữa)"),
            num("lug.tl", "Thickness", show=lambda: shear("lug")), sel("lug.mat", "Material", MATS, show=lambda: shear("lug")),
            num("lug.D", "Weld size (1/16in)", "/16", show=lambda: shear("lug")),
        ]),
        ("Options (tool)", False, [
            txt("name", "Connection name"),
        ]),
    ]
