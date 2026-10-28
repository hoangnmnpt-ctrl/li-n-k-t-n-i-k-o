"""
base_gui.py — Form nhập CHÂN CỘT (Column base — CB) cho Connection Pad, đúng thứ tự & nhãn của RAM Connection "Base plate":
General information (Analysis · Design criteria · Optimization criteria) → Members (Column) →
Base plate (Base plate · Support · Anchor · Anchor reinforcement). Rê chuột lên nhãn để xem chú thích tiếng Việt.
"""

from __future__ import annotations

import base_engine as BE
import engine as K
from knee_section import SectionError, parse_section

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


def _tapered(sec):
    try:
        return parse_section(sec).tapered
    except SectionError:
        return False


def build_sections(app):
    S = lambda: app.S
    g = lambda k: S()["gen"].get(k)
    o = lambda k: S()["opt"].get(k)
    an = lambda k: S()["anchor"].get(k)
    lug = lambda: bool(S()["lug"].get("on"))
    prim = lambda k: S()["reinf"].get("type", "primary") == "primary" and bool(S()["reinf"].get(k))
    ELEC = list(K.ELECTRODES)
    return [
        ("General information", True, [
            sub("Analysis"),
            btn("Loads   <Loads>  →  mở bảng tải", lambda: app.tabs.set("Loads")),
            tip(sel("gen.axis", "Analysis axis", list(BE.AXES.items())),
                "Major: chỉ M33/V2 · Minor: chỉ M22/V3 · Both axes: từng phương độc lập · Biaxial: giải đồng thời hai mô men (bản cứng)"),
            tip(sel("gen.pressure", "Pressure distribution", [("uniform", "Uniform"), ("triangular", "Triangular")]),
                "Uniform: khối ứng suất đều fp,max (DG1) · Triangular: phân bố tam giác / hình thang"),
            tip(chk("gen.compat", "Consider strain compatibility", show=lambda: g("pressure") == "triangular"),
                "Tương thích biến dạng bê tông – neo (Ec, Es, bản cứng) để tìm lực neo và áp lực ép"),
            sub("Design criteria"),
            sel("gen.designCode", "Steel design code", BE.STEEL_CODES),
            sel("gen.concCode", "Concrete design code", BE.CONC_CODES),
            tip(chk("gen.seismic", "Seismic provisions"), "Vùng động đất: sức kháng neo ×0.75 (ACI D.3.3)"),
            tip(sel("gen.bearCalc", "Bearing stress calculation", [("complete", "Complete area"), ("effective", "Effective area")]),
                "Complete area: toàn bộ bản đế (DG1) · Effective area: vùng cách thép cột ≤ c = tp·√(φFy/(2fp,max))"),
            tip(chk("gen.friction", "Include friction between base plate and support"), "Ma sát 0.75·0.55·Pu giảm lực cắt cho neo / bản chắn cắt"),
            sub("Optimization criteria"),
            tip(chk("opt.optTp", "Optimize base plate thickness"),
                "Chọn trong 6 8 10 12 14 16 18 20 22 25 30 35 40 45 mm: ≥ 14 mm cột chính / ≥ 12 mm đầu hồi, ≥ hw/50"),
            num("opt.tpMax", "Maximum thickness", show=lambda: o("optTp")), num("opt.tpMin", "Minimum thickness", show=lambda: o("optTp")),
            tip(chk("opt.optN", "Longitudinal dimension from column"), "N = chiều cao tổng cột + 20 mm, làm tròn lên bội số 10"),
            tip(chk("opt.optB", "Transversal dimension from column"), "B = max(180 mm, bề rộng cánh cột); tăng theo bội số 10 khi tim neo → mép < 1.75D"),
            tip(chk("opt.optD", "Optimize anchors"),
                "M20…M36 Class 4.6 → 5.6 → 8.8 → 10.9 (≥ M24 cột chính, ≥ M20 đầu hồi). 1 hàng mỗi bên bụng: h < 500 → 2 neo / hàng, ex = (N − a)/2; "
                "h ≥ 500 → 3 neo / hàng, ex = (N − 2a)/2; ey = (B − a)/2, "
                "a = 100 (M20), 120 (M24, M27), 150 (M30, M36)"),
            tip(num("opt.vsaMax", "Maximum anchor shear ratio", "", show=lambda: o("optD")),
                "Khi tối ưu neo: tỷ số Anchor shear (ACI D.6.1) phải ≤ giá trị này (mặc định 0.4); các kiểm tra khác ≤ 1"),
            tip(chk("opt.optWeld", "Optimize column weld size"), "Cỡ hàn D tăng từng 1/16 in cho tới khi đạt"),
        ]),
        ("Members", True, [
            sub("Column"),
            note("Column type: Tapered member" if _tapered(S()["col"]["sec"]) else "Column type: Prismatic member"),
            tip(txt("col.sec", "Section"), "Quy cách tiết diện — 400.8-200.12 (bụng 400×8, cánh 200×12) hoặc (300-500).6-200.10 (vát)"), info("col.sec"),
            sel("col.mat", "Material", MATS),
            num("col.L", "Length", "m", show=lambda: _tapered(S()["col"]["sec"])),
            sel("col.jointEnd", "Joint end", [("I", "End I"), ("J", "End J")], show=lambda: _tapered(S()["col"]["sec"])),
            tip(num("col.ox", "Longitudinal offset"), "Lệch tâm cột so với tâm bản đế theo phương N (cánh trên +2 ở phía +x)"),
            tip(num("col.oz", "Transversal offset"), "Lệch tâm cột so với tâm bản đế theo phương B"),
        ]),
        ("Base plate", True, [
            sub("Base plate"),
            sel("plate.shape", "Plate shape", [("rect", "Rectangular")]),
            sel("plate.ctype", "Connection type", [("unstiffened", "Unstiffened")]),
            sel("plate.pos", "Position on the support", [("center", "Center"), ("custom", "Custom")]),
            tip(num("plate.px", "Longitudinal offset on the support", show=lambda: S()["plate"].get("pos") == "custom"), "Lệch tâm bản đế so với tâm gối theo phương N"),
            num("plate.pz", "Transversal offset on the support", show=lambda: S()["plate"].get("pos") == "custom"),
            tip(num("plate.N", "N: Longitudinal dimension"), "Theo phương chiều cao tiết diện cột (uốn M33)"),
            tip(num("plate.B", "B: Transversal dimension"), "Theo phương bề rộng cánh (uốn M22)"),
            num("plate.tp", "Thickness"), sel("plate.mat", "Material", MATS),
            sel("weld.electrode", "Column weld", ELEC),
            tip(chk("weld.outerOnly", "Outer welds flanges only"), "Chỉ hàn mặt ngoài hai cánh (không hàn mặt trong cánh, bụng)"),
            tip(num("weld.D", "D: Column weld size (1/16 in)", "/16"), "Cỡ hàn góc theo 1/16 inch (5 → 7.9 mm)"),
            chk("plate.overA2", "Override A2/A1 ratio"),
            tip(num("plate.A2A1", "A2/A1", "", show=lambda: S()["plate"].get("overA2")), "√(A2/A1) ≤ 2"),
            tip(chk("lug.on", "Include shear lug"), "Bản chắn cắt chịu toàn bộ lực cắt (thay cho neo)"),
            num("lug.bl", "Shear lug width", show=lug), num("lug.H", "Shear lug height", show=lug), num("lug.tl", "Shear lug thickness", show=lug),
            sel("lug.mat", "Shear lug material", MATS, show=lug), num("lug.D", "Shear lug weld size (1/16 in)", "/16", show=lug),
            sub("Support"),
            tip(chk("ped.isPed", "With pedestal"), "Bệ (pedestal) hay móng / sàn"),
            num("ped.N2", "Longitudinal dimension"), num("ped.B2", "Transversal dimension"), num("ped.h", "Thickness"),
            tip(sel("ped.mat", "Material", [(k, f"{k}  (f'c = {v:g} MPa)") for k, v in BE.CONC_MATS.items()]), "Bê tông gối"),
            chk("ped.groutOn", "Include grouting"), num("ped.grout", "Grout thickness", show=lambda: S()["ped"].get("groutOn")),
            sub("Anchor"),
            sel("anchor.layout", "Anchor position", list(BE.LAYOUTS.items())),
            tip(sel("anchor.nr", "Rows number per side", [1, 2, 3]), "Số hàng neo ở mỗi bên (Longitudinal: mỗi bên bụng; Transversal: mỗi phía cánh)"),
            tip(num("anchor.sr", "Spacing between rows", show=lambda: int(an("nr") or 1) > 1), "Khoảng cách giữa các hàng neo cùng phía"),
            sel("anchor.npr", "Anchors per row", [1, 2, 3, 4, 5]),
            tip(num("anchor.ex", "Longitudinal edge distance on the plate"), "Từ tâm neo tới mép bản theo phương N"),
            tip(num("anchor.ey", "Transverse edge distance on the plate"), "Từ tâm neo tới mép bản theo phương B"),
            sel("anchor.type", "Anchor type", [("headed", "Headed"), ("hooked", "Hooked")]),
            sel("anchor.head", "Head type", list(BE.HEADS.items()), show=lambda: an("type") != "hooked"),
            tip(num("anchor.eh", "Hook length eh", show=lambda: an("type") == "hooked"), "3da ≤ eh ≤ 4.5da (ACI D.5.3)"),
            chk("anchor.lockNut", "Include lock nut"),
            sel("anchor.d", "Anchor", [(d, BE.anchor_label(d)) for d in BE.ANCHOR_DIAS]),
            num("anchor.hef", "Effective embedment depth"),
            sel("anchor.grade", "Material", list(BE.ANCHOR_GRADES)),
            tip(chk("anchor.cracked", "Cracked concrete"), "Bê tông nứt: ψc = 1.0 thay vì 1.25 / 1.4"),
            tip(chk("anchor.brittle", "Brittle steel"), "Thép neo giòn: φ = 0.65 (kéo), 0.60 (cắt)"),
            tip(chk("anchor.welded", "Anchors welded to base plate"), "Neo hàn vào bản đế: mọi neo chịu cắt; không hàn: một nửa số neo (lỗ quá cỡ)"),
            sub("Anchor reinforcement"),
            tip(sel("reinf.type", "Type of reinforcement", [("primary", "Primary"), ("supplementary", "Supplementary")]),
                "Primary: cốt thép neo thay kiểm tra phá vỡ bê tông (báo As yêu cầu) · Supplementary: Condition A, φ = 0.75"),
            chk("reinf.T", "Tension reinforcement"),
            sel("reinf.barT", "Tension bar size", list(BE.REBAR_US), show=lambda: prim("T")),
            tip(num("reinf.fyT", "Tension bar grade", "MPa", show=lambda: prim("T")), "Giới hạn chảy cốt thép (40 ksi = 275.79 MPa, 60 ksi = 413.69 MPa)"),
            num("reinf.nT", "Tension number of bars", "", show=lambda: prim("T")),
            chk("reinf.V", "Shear reinforcement"),
            sel("reinf.barV", "Shear bar size", list(BE.REBAR_US), show=lambda: prim("V")),
            num("reinf.fyV", "Shear bar grade", "MPa", show=lambda: prim("V")),
            num("reinf.nVx", "Shear number of bars in major axis direction", "", show=lambda: prim("V")),
            num("reinf.nVy", "Shear number of bars in minor axis direction", "", show=lambda: prim("V")),
        ]),
    ]
