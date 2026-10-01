"""
report.py — Báo cáo tiếng Anh theo form RAM Connection ("Steel Connections – Results")
======================================================================================
build(S, R) → cấu trúc báo cáo;  to_text() cho tab Report;  to_docx() xuất Word (không cần thư viện ngoài).
Bố cục: Demands · Geometric Considerations · Plate / Column Behavior · Design Check · Global critical strength ratio.
"""

from __future__ import annotations

import datetime
import math
import zipfile
from xml.sax.saxutils import escape

# id kiểm tra → (nhóm RAM, tên RAM, tham chiếu RAM)
G_EXT, G_INT = "Moment end plate (external flange)", "Moment end plate (internal flange)"
CHECK_EN = {
    "pl_flex_E": (G_EXT, "Flexural yielding", "DG16 Sec 2.5"),
    "bolt_np_E": (G_EXT, "No prying bolt moment strength", "DG16 Sec 2.5"),
    "bolt_q_E": (G_EXT, "Bolt rupture with prying moment strength", "DG16 Sec 2.5"),
    "bolt_v_E": (G_EXT, "Bolts shear", "Tables (7-1..14)"),
    "bear_p_E": (G_EXT, "Bolt bearing under shear load", "Eq. J3-6"),
    "pl_vy_E": (G_EXT, "Shear yielding", "DG4 Eq. 3.12"),
    "pl_vr_E": (G_EXT, "Shear rupture", "DG4 Eq. 3.13"),
    "pl_flex_I": (G_INT, "Flexural yielding", "DG16 Sec 2.5"),
    "bolt_np_I": (G_INT, "No prying bolt moment strength", "DG16 Sec 2.5"),
    "bolt_q_I": (G_INT, "Bolt rupture with prying moment strength", "DG16 Sec 2.5"),
    "bolt_v_I": (G_INT, "Bolts shear", "Tables (7-1..14)"),
    "bear_p_I": (G_INT, "Bolt bearing under shear load", "Eq. J3-6"),
    "pl_vy_I": (G_INT, "Shear yielding", "DG4 Eq. 3.12"),
    "pl_vr_I": (G_INT, "Shear rupture", "DG4 Eq. 3.13"),
    "bolt_v_A": ("Moment end plate (all bolts)", "Bolts shear", "Tables (7-1..14)"),
    "bear_p_A": ("Moment end plate (all bolts)", "Bolt bearing under shear load", "Eq. J3-6"),
    "m1_ww_v": ("Beam", "Web weld shear strength", "Eq. J2-4"),
    "m1_ww_t": ("Beam", "Web weld strength to reach yield stress", "Eq. J4-1"),
    "m1_wv": ("Beam", "Shear yielding", "Eq. J4-3"),
    "m1_wf_E": ("Beam", "Flange weld capacity (external flange)", "Eq. J2-4"),
    "m1_wf_I": ("Beam", "Flange weld capacity (internal flange)", "Eq. J2-4"),
    "sup_flex_E": ("Support", "Flexural yielding (external flange)", "DG4 Eq. 3.21"),
    "sup_q_E": ("Support", "Bolt rupture with prying moment strength", "DG16 Sec 2.5"),
    "bear_s_E": ("Support", "Support bolt bearing (external flange)", "Eq. J3-6"),
    "sup_flex_I": ("Support", "Flexural yielding (internal flange)", "DG4 Eq. 3.21"),
    "sup_q_I": ("Support", "Bolt rupture with prying moment strength", "DG16 Sec 2.5"),
    "bear_s_I": ("Support", "Support bolt bearing (internal flange)", "Eq. J3-6"),
    "bear_s_A": ("Support", "Support bolt bearing", "Eq. J3-6"),
    "pz": ("Support", "Panel web shear", "Sec. J10.6"),
    "j10y_E": ("Support - external flange", "Local web yielding", "Sec. J10"),
    "j10c_E": ("Support - external flange", "Web crippling", "Sec. J10.3"),
    "j10b_E": ("Support - external flange", "Web compression buckling", "Sec. J10.5"),
    "j10y_I": ("Support - internal flange", "Local web yielding", "Sec. J10"),
    "j10c_I": ("Support - internal flange", "Web crippling", "Sec. J10.3"),
    "j10b_I": ("Support - internal flange", "Web compression buckling", "Sec. J10.5"),
    "st_ax_E": ("Transverse stiffeners - top", "Yielding strength due to axial load", "Eq. J4-1"),
    "st_c_E": ("Transverse stiffeners - top", "Compression", "Sec. J4.4"),
    "st_wf_E": ("Transverse stiffeners - top", "Flange weld capacity", "Eq. J2-4"),
    "st_ww_E": ("Transverse stiffeners - top", "Web weld capacity", "Eq. J2-4"),
    "st_ax_I": ("Transverse stiffeners - bottom", "Yielding strength due to axial load", "Eq. J4-1"),
    "st_c_I": ("Transverse stiffeners - bottom", "Compression", "Sec. J4.4"),
    "st_wf_I": ("Transverse stiffeners - bottom", "Flange weld capacity", "Eq. J2-4"),
    "st_ww_I": ("Transverse stiffeners - bottom", "Web weld capacity", "Eq. J2-4"),
    "m2_ww_v": ("Support", "Web weld shear strength", "Eq. J2-4"),
    "m2_ww_t": ("Support", "Web weld strength to reach yield stress", "Eq. J4-1"),
    "m2_wv": ("Support", "Shear yielding", "Eq. J4-3"),
    "m2_wf_E": ("Support", "Flange weld capacity (external flange)", "Eq. J2-4"),
    "m2_wf_I": ("Support", "Flange weld capacity (internal flange)", "Eq. J2-4"),
}
GROUP_ORDER = [G_EXT, G_INT, "Moment end plate (all bolts)", "Beam", "Support", "Support - external flange",
               "Support - internal flange", "Transverse stiffeners - top", "Transverse stiffeners - bottom"]
UNIT_EN = {"kN·m": "KN*m", "kN": "KN", "kN/m": "KN/m"}

# kiểm tra cấu tạo: (nhóm VN, từ khoá trong tên VN) → (nhóm RAM, tên RAM, tham chiếu)
GEO_EN = [
    ("Khoảng cách mép dọc", "Extended end plate", "Vertical edge distance", "Sec. J3.5"),
    ("Khoảng cách mép ngang", "Extended end plate", "Horizontal edge distance", "Sec. J3.5"),
    ("Gage g", "Extended end plate", "Horizontal center-to-center spacing (gage)", "DG4 Sec. 2.1, 2.4, DG16 Sec. 2.5"),
    ("pf,o cánh ngoài", "Extended end plate", "Outer bolt distance (external flange)", "DG4 Sec. 2.1"),
    ("pf,i cánh ngoài", "Extended end plate", "Inner bolt distance (external flange)", "DG4 Sec. 2.1"),
    ("pf,o cánh trong", "Extended end plate", "Outer bolt distance (internal flange)", "DG4 Sec. 2.1"),
    ("pf,i cánh trong", "Extended end plate", "Inner bolt distance (internal flange)", "DG4 Sec. 2.1"),
    ("Hàng ngoài – hàng trong", "Extended end plate", "Vertical bolt spacing (external flange)", "Sec. J3.3"),
    ("Bước hàng pb (cánh ngoài)", "Extended end plate", "Vertical spacing between inner bolt rows (external flange)", "Sec. J3.3"),
    ("Bước hàng pb (cánh trong)", "Extended end plate", "Vertical spacing between inner bolt rows (internal flange)", "Sec. J3.3"),
    ("Khoảng trống giữa hai nhóm", "Extended end plate", "Clear spacing between bolt groups", "Sec. J3.3"),
    ("Đường kính bu lông", "Extended end plate", "Bolt diameter", "DG4 Sec. 1.1"),
    ("bp ≤ bf", "Extended end plate", "End plate width (effective)", "DG16 Sec. 2.5"),
    ("Hàn góc cánh ngoài", "Beam", "Weld size (external flange)", "table J2.4"),
    ("Hàn góc cánh trong", "Beam", "Weld size (internal flange)", "table J2.4"),
    ("Hàn góc bụng", "Beam", "Web", "table J2.4"),
    ("bs + tw/2", "Transverse stiffeners", "Width", "Sec. J10.8"),
    ("ts ≥ tf", "Transverse stiffeners", "Thickness (≥ tf/2)", "Sec. J10.8"),
    ("ts ≥ bs/16", "Transverse stiffeners", "Thickness (≥ bs/16)", "Sec. J10.8"),
    ("bs ≤ (bf", "Transverse stiffeners", "Width (max.)", "Geometry"),
    ("ts ≥ tw·Fyb", "End plate stiffener", "Thickness", "DG4 Eq. 3.15"),
    ("hst/ts", "End plate stiffener", "Slenderness hst/ts", "DG4 Eq. 3.16"),
    ("Lst ≥", "End plate stiffener", "Length", "DG4 Sec. 2.4"),
]


def _num(x, nd=2):
    if x is None or (isinstance(x, float) and (math.isnan(x))):
        return "--"
    if isinstance(x, float) and math.isinf(x):
        return "INF"
    return f"{x:.{nd}f}"


def build(S: dict, R: dict, file_name: str = "") -> dict:
    G = R["G"]
    isN = G["type"] == "ngang"
    code = S.get("gen", {}).get("designCode", "AISC 2010 LRFD").replace("AISC 2010", "AISC 360-10").replace("AISC 2016", "AISC 360-16")
    demands = []
    for d in R["demands"]:
        demands.append([d["name"], _num(d["V"]), _num(d["N"]), _num(d["M"]), _num(d["FnE"]), _num(d["FnI"]),
                        "0.00", "0.00", _num(d["N2"]), _num(d["Vpz"]), "Design"])
    geo = {}
    for x in R["geo"]:
        ent = next((e for e in GEO_EN if e[0] in x["name"]), None)
        grp, name, ref = (ent[1], ent[2], ent[3]) if ent else (x["grp"], x["name"], x["ref"])
        if "Sườn gối cánh" in x["grp"]:
            grp = "Transverse stiffeners - " + ("top" if "ngoài" in x["grp"] else "bottom")
        geo.setdefault(grp, []).append([name, f"[{x['unit']}]" if x["unit"] else "", _num(x["val"]), _num(x["min"]), _num(x["max"]),
                                        "OK" if x["ok"] else "N.G.", ref])
    beh = []
    for sd, lab in (("E", "external flange"), ("I", "internal flange")):
        s = R["sides"].get(sd, {})
        if "error" in s:
            continue
        def txt(thick, my, mq, mnp):
            if thick:
                return "Thick plate behavior controlled by " + ("plate yielding" if my < mnp else "bolt rupture (no prying)")
            return "Thin plate behavior controlled by " + ("plate yielding" if my < mq or mq != mq else "bolt rupture with prying")
        beh.append((f"End plate behavior ({lab})", txt(s["thick"], s["phiMpl"] / s["gam"], s["phiMq"], s["phiMnp"])))
        Sg = s["S"]
        thick_s = s["phiMnp"] < 0.9 * Sg["phiM"]
        beh.append((f"Connection plate behavior ({lab})", txt(thick_s, Sg["phiM"], Sg["phiMq"], s["phiMnp"])))
    checks = {}
    for c in R["checks"]:
        grp, name, ref = CHECK_EN.get(c["id"], (c["grp"], c["name"], c["ref"]))
        if isN and grp == "Beam": grp = "Column (end plate member)"
        checks.setdefault(grp, []).append([name + (" (stiffened)" if c["info"] else ""), f"[{UNIT_EN.get(c['unit'], c['unit'])}]",
                                           _num(c["cap"]), _num(abs(c["dem"])), c["combo"], _num(c["ratio"]), ref, c["ratio"], c["info"]])
    keys = list(CHECK_EN)
    idx = {(CHECK_EN[k][0], CHECK_EN[k][1]): i for i, k in enumerate(keys)}
    for gname, rows in checks.items():
        rows.sort(key=lambda r: idx.get((gname, r[0].replace(" (stiffened)", "")), 999))
    order = [g for g in GROUP_ORDER if g in checks] + [g for g in checks if g not in GROUP_ORDER]
    gov = R["gov"]
    return dict(
        date=datetime.datetime.now().strftime("%m/%d/%Y %I:%M %p").lstrip("0"), file=file_name,
        name=S.get("name", ""), family="Beam - Column flange (BCF)", type="Knee moment end plate", code=code,
        demands=demands, geo=geo, behavior=beh, checks=[(g, checks[g]) for g in order],
        ratio=gov["ratio"] if gov else 0.0,
        members=dict(beam=G["beam"], col=G["col"], slope=G["a"]),
    )


DEM_HEAD = ["Description", "Ru [kN]", "Pu [kN]", "Mu [kN*m]", "PufTop [kN]", "PufBot [kN]", "L.PufTop", "L.PufBot", "Col Pu [kN]", "Panel Vu [kN]", "Load type"]
GEO_HEAD = ["Dimensions", "Unit", "Value", "Min.", "Max.", "Sta.", "References"]
CHK_HEAD = ["Verification", "Unit", "Capacity", "Demand", "Ctrl EQ", "Ratio", "References"]


def to_text(rep: dict) -> list[tuple[str, str]]:
    """Danh sách (nội dung, tag) cho tk.Text: tag ∈ h1, h2, grp, row, ok, bad, dim."""
    out = []
    add = lambda s, t="row": out.append((s + "\n", t))
    add(f"Current Date: {rep['date']}", "dim"); add("Units system: SI", "dim")
    if rep["file"]: add(f"File name: {rep['file']}", "dim")
    add(""); add("Steel Connections", "h1"); add("Results", "h1"); add("")
    add(f"Connection:  {rep['name']}", "h2"); add(f"Family: {rep['family']}"); add(f"Type: {rep['type']}"); add("")
    add(f"Design code: {rep['code']}", "h2"); add("")
    add("Demands", "h2")
    w = [18, 9, 9, 10, 11, 11, 9, 9, 10, 12, 9]
    fmt = lambda row, ws: "".join((f"{str(c)[:wd - 1]:<{wd}}" if i == 0 else f"{str(c):>{wd}}") for i, (c, wd) in enumerate(zip(row, ws)))
    add(fmt(["", "Beam", "", "", "Right beam", "", "Left beam", "", "Column", "Panel", ""], w), "grp")
    add(fmt(DEM_HEAD, w), "grp")
    for r in rep["demands"]: add(fmt(r, w))
    add(""); add("Geometric Considerations", "h2")
    wg = [58, 8, 10, 10, 10, 6]
    add(fmt(GEO_HEAD[:6], wg) + "  References", "grp")
    for grp, rows in rep["geo"].items():
        add(grp, "sub")
        for r in rows: add(fmt(r[:6], wg) + "  " + r[6], "row" if r[5] == "OK" else "bad")
    add(""); add("Plate / Column Behavior", "h2")
    for a, b in rep["behavior"]:
        add(a, "sub"); add(b)
    add(""); add("Design Check", "h2")
    wc = [46, 9, 11, 11, 18, 7]
    add(fmt(CHK_HEAD[:6], wc) + "  References", "grp")
    for grp, rows in rep["checks"]:
        add(grp, "sub")
        for r in rows:
            add(fmt(r[:6], wc) + "  " + r[6], "dim" if r[8] else ("bad" if r[7] > 1.0001 else "row"))
    add(""); add(f"Global critical strength ratio    {_num(rep['ratio'])}", "ok" if rep["ratio"] <= 1.0001 else "bad")
    return out


# ─────────────────────────── DOCX tối giản ───────────────────────────
def _p(text, bold=False, size=20, color=None, align=None):
    rpr = f"<w:rPr>{'<w:b/>' if bold else ''}<w:sz w:val=\"{size}\"/>{f'<w:color w:val=\"{color}\"/>' if color else ''}</w:rPr>"
    ppr = f"<w:pPr>{f'<w:jc w:val=\"{align}\"/>' if align else ''}<w:spacing w:after=\"40\"/></w:pPr>"
    return f"<w:p>{ppr}<w:r>{rpr}<w:t xml:space=\"preserve\">{escape(str(text))}</w:t></w:r></w:p>"


def _tbl(head, rows, widths, group_rows=()):
    def cell(t, w, bold=False, shade=None, align="left", span=1):
        tcpr = f"<w:tcW w:w=\"{w}\" w:type=\"dxa\"/>" + (f"<w:gridSpan w:val=\"{span}\"/>" if span > 1 else "") + \
               (f"<w:shd w:val=\"clear\" w:fill=\"{shade}\"/>" if shade else "")
        return (f"<w:tc><w:tcPr>{tcpr}</w:tcPr><w:p><w:pPr><w:jc w:val=\"{align}\"/><w:spacing w:after=\"0\"/></w:pPr>"
                f"<w:r><w:rPr>{'<w:b/>' if bold else ''}<w:sz w:val=\"16\"/></w:rPr><w:t xml:space=\"preserve\">{escape(str(t))}</w:t></w:r></w:p></w:tc>")
    x = ["<w:tbl><w:tblPr><w:tblW w:w=\"0\" w:type=\"auto\"/><w:tblBorders>"
         + "".join(f"<w:{s} w:val=\"single\" w:sz=\"4\" w:color=\"BFBFBF\"/>" for s in ("top", "left", "bottom", "right", "insideH", "insideV"))
         + "</w:tblBorders></w:tblPr>"]
    x.append("<w:tr>" + "".join(cell(h, w, True, "D9D9D9", "center") for h, w in zip(head, widths)) + "</w:tr>")
    for r in rows:
        if isinstance(r, str):
            x.append("<w:tr>" + cell(r, sum(widths), True, "F2F2F2", "left", len(widths)) + "</w:tr>")
        else:
            x.append("<w:tr>" + "".join(cell(c, w, False, None, "left" if i == 0 or i == len(widths) - 1 else "right")
                                        for i, (c, w) in enumerate(zip(r, widths))) + "</w:tr>")
    x.append("</w:tbl>")
    return "".join(x)


def to_docx(rep: dict, path: str):
    b = [_p(f"Current Date: {rep['date']}", size=16), _p("Units system: SI", size=16)]
    if rep["file"]: b.append(_p(f"File name: {rep['file']}", size=16))
    b += [_p(""), _p("Steel Connections", True, 32, "2E7D32"), _p("Results", True, 28), _p("")]
    b += [_p(f"Connection:  {rep['name']}", True, 22), _p(f"Family: {rep['family']}"), _p(f"Type: {rep['type']}"), _p(""),
          _p(f"Design code: {rep['code']}", True, 22), _p(""), _p("Demands", True, 24)]
    b.append(_tbl(DEM_HEAD, rep["demands"], [1500, 800, 800, 900, 900, 900, 800, 800, 800, 900, 800]))
    b += [_p(""), _p("Geometric Considerations", True, 24)]
    rows = []
    for grp, rr in rep["geo"].items():
        rows.append(grp); rows += rr
    b.append(_tbl(GEO_HEAD, rows, [3900, 700, 900, 900, 900, 600, 2000]))
    b += [_p(""), _p("Plate / Column Behavior", True, 24)]
    for a, t in rep["behavior"]:
        b += [_p(a, True, 18), _p(t, size=18)]
    b += [_p(""), _p("Design Check", True, 24)]
    rows = []
    for grp, rr in rep["checks"]:
        rows.append(grp); rows += [r[:7] for r in rr]
    b.append(_tbl(CHK_HEAD, rows, [3600, 800, 1000, 1000, 1200, 700, 1600]))
    b += [_p(""), _p(f"Global critical strength ratio    {_num(rep['ratio'])}", True, 24, "2E7D32" if rep["ratio"] <= 1.0001 else "C00000")]
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + "".join(b) +
           '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="850" w:right="700" w:bottom="850" w:left="700" w:header="400" w:footer="400" w:gutter="0"/></w:sectPr>'
           '</w:body></w:document>')
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", doc)
