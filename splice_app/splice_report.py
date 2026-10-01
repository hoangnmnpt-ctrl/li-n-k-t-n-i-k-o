"""
splice_report.py — Báo cáo tiếng Anh theo form RAM Connection ("Steel Connections – Results") cho liên kết nối dầm
===================================================================================================================
build(S, R) → cấu trúc báo cáo;  to_text() cho tab Report;  to_docx() xuất Word (không cần thư viện ngoài).
Bố cục: Demands · Geometric Considerations · Plate Behavior · Design Check · Global critical strength ratio.
Dựng Word dùng lại các hàm _p, _tbl của knee_app/report.py.
"""

from __future__ import annotations

import datetime
import math
import re
import zipfile

from _knee import K  # noqa: F401  (đảm bảo knee_app nằm trong sys.path)
import report as KR  # knee_app/report.py

_num = KR._num
UNIT_EN = KR.UNIT_EN
SIDE_EN = {"T": "top flange", "B": "bottom flange"}

ROW_ORDER = ["Flexural yielding", "No prying", "Bolt rupture", "Bolts shear", "Bolt bearing", "Shear yielding", "Shear rupture",
             "Flange weld", "Web weld strength", "Web weld shear"]
DEM_HEAD = ["Description", "Ru [kN]", "Pu [kN]", "Mu [kN*m]", "PufTop [kN]", "PufBot [kN]", "Mu,eq [kN*m]", "Tension flange", "Load type"]
GEO_HEAD = ["Dimensions", "Unit", "Value", "Min.", "Max.", "Sta.", "References"]
CHK_HEAD = ["Verification", "Unit", "Capacity", "Demand", "Ctrl EQ", "Ratio", "References"]

# kiểm tra cấu tạo: (từ khoá trong tên VN) → (nhóm RAM, tên RAM, tham chiếu)
GEO_EN = [
    ("Khoảng cách mép dọc", "Extended end plate", "Vertical edge distance", "Sec. J3.5"),
    ("Khoảng cách mép ngang", "Extended end plate", "Horizontal edge distance", "Sec. J3.5"),
    ("Gage g", "Extended end plate", "Horizontal center-to-center spacing (gage)", "DG4 Sec. 2.1, 2.4, DG16 Sec. 2.5"),
    ("pf,o cánh trên", "Extended end plate", "Outer bolt distance (top flange)", "DG4 Sec. 2.1"),
    ("pf,i cánh trên", "Extended end plate", "Inner bolt distance (top flange)", "DG4 Sec. 2.1"),
    ("pf,o cánh dưới", "Extended end plate", "Outer bolt distance (bottom flange)", "DG4 Sec. 2.1"),
    ("pf,i cánh dưới", "Extended end plate", "Inner bolt distance (bottom flange)", "DG4 Sec. 2.1"),
    ("Hàng ngoài – hàng trong (cánh trên)", "Extended end plate", "Vertical bolt spacing (top flange)", "Sec. J3.3"),
    ("Hàng ngoài – hàng trong (cánh dưới)", "Extended end plate", "Vertical bolt spacing (bottom flange)", "Sec. J3.3"),
    ("Bước hàng pb (cánh trên)", "Extended end plate", "Vertical spacing between inner bolt rows (top flange)", "Sec. J3.3"),
    ("Bước hàng pb (cánh dưới)", "Extended end plate", "Vertical spacing between inner bolt rows (bottom flange)", "Sec. J3.3"),
    ("Khoảng trống giữa hai nhóm", "Extended end plate", "Clear spacing between bolt groups", "Sec. J3.3"),
    ("Đường kính bu lông", "Extended end plate", "Bolt diameter", "DG4 Sec. 1.1"),
    ("Hàn góc cánh trên dầm 1", "Beam 1", "Weld size (top flange)", "table J2.4"),
    ("Hàn góc cánh dưới dầm 1", "Beam 1", "Weld size (bottom flange)", "table J2.4"),
    ("Hàn góc bụng dầm 1", "Beam 1", "Web", "table J2.4"),
    ("Hàn góc cánh trên dầm 2", "Beam 2", "Weld size (top flange)", "table J2.4"),
    ("Hàn góc cánh dưới dầm 2", "Beam 2", "Weld size (bottom flange)", "table J2.4"),
    ("Hàn góc bụng dầm 2", "Beam 2", "Web", "table J2.4"),
    ("ts ≥ tw·Fyb", "End plate stiffener", "Thickness", "DG4 Eq. 3.15"),
    ("hst/ts", "End plate stiffener", "Slenderness hst/ts", "DG4 Eq. 3.16"),
    ("Lst ≥", "End plate stiffener", "Length", "DG4 Sec. 2.4"),
]


def check_en(cid: str, c: dict) -> tuple[str, str, str, int]:
    """id kiểm tra → (nhóm RAM, tên RAM, tham chiếu, thứ tự nhóm)."""
    m = re.fullmatch(r"pl(\d)_flex_([TB])", cid)
    if m: return f"Moment end plate {m[1]} ({SIDE_EN[m[2]]})", "Flexural yielding", "DG16 Sec 2.5", int(m[1]) * 10 + (m[2] == "B")
    m = re.fullmatch(r"pl(\d)_v([yr])_([TB])", cid)
    if m: return (f"Moment end plate {m[1]} ({SIDE_EN[m[3]]})", "Shear yielding" if m[2] == "y" else "Shear rupture",
                  "DG4 Eq. 3.12" if m[2] == "y" else "DG4 Eq. 3.13", int(m[1]) * 10 + (m[3] == "B"))
    m = re.fullmatch(r"bolt_np_([TB])", cid)
    if m: return f"Bolts ({SIDE_EN[m[1]]} in tension)", "No prying bolt moment strength", "DG16 Sec 2.5", 30 + (m[1] == "B")
    m = re.fullmatch(r"bolt_q(\d)_([TB])", cid)
    if m: return (f"Bolts ({SIDE_EN[m[2]]} in tension)", f"Bolt rupture with prying moment strength (plate {m[1]})",
                  "DG16 Sec 2.5", 30 + (m[2] == "B"))
    m = re.fullmatch(r"bolt_v_([TBA])", cid)
    if m: return "Bolts (shear)", "Bolts shear", "Tables (7-1..14)", 40
    m = re.fullmatch(r"bear_p(\d)_([TBA])", cid)
    if m: return "Bolts (shear)", f"Bolt bearing under shear load (plate {m[1]})", "Eq. J3-6", 40
    m = re.fullmatch(r"m(\d)_(wf|ww_v|ww_t|wv)(?:_([TB]))?", cid)
    if m:
        k, kind, f = m[1], m[2], m[3]
        name = {"wf": f"Flange weld capacity ({SIDE_EN.get(f, '')})", "ww_v": "Web weld shear strength",
                "ww_t": "Web weld strength to reach yield stress", "wv": "Shear yielding"}[kind]
        ref = {"wf": "Eq. J2-4", "ww_v": "Eq. J2-4", "ww_t": "Eq. J4-1", "wv": "Eq. J4-3"}[kind]
        return f"Beam {k}", name, ref, 50 + int(k)
    return c["grp"], c["name"], c["ref"], 99


def build(S: dict, R: dict, file_name: str = "") -> dict:
    G = R["G"]
    code = S.get("gen", {}).get("designCode", "AISC 2010 LRFD").replace("AISC 2010", "AISC 360-10").replace("AISC 2016", "AISC 360-16")
    demands = []
    for d in R["demands"]:
        demands.append([d["name"], _num(d["V"]), _num(d["N"]), _num(d["M"]), _num(d["FnT"]), _num(d["FnB"]), _num(d["Mu"]),
                        {"T": "Top", "B": "Bottom"}.get(d["side"], "--"), "Design"])
    geo = {}
    for x in R["geo"]:
        ent = next((e for e in GEO_EN if e[0] in x["name"]), None)
        grp, name, ref = (ent[1], ent[2], ent[3]) if ent else (x["grp"], x["name"], x["ref"])
        if x["grp"].startswith("Sườn bản đầu"):
            grp = "End plate stiffener (" + ("top" if "trên" in x["grp"] else "bottom") + ")"
        geo.setdefault(grp, []).append([name, f"[{x['unit']}]" if x["unit"] else "", _num(x["val"]), _num(x["min"]), _num(x["max"]),
                                        "OK" if x["ok"] else "N.G.", ref])
    beh = []
    for sd in ("T", "B"):
        s = R["sides"].get(sd, {})
        if "error" in s:
            continue
        for P in s["plates"]:
            my, mq, mnp = P["phiMpl"] / s["gam"], P["phiMq"], s["phiMnp"]
            if P["thick"]:
                t = "Thick plate behavior controlled by " + ("plate yielding" if my < mnp else "bolt rupture (no prying)")
            else:
                t = "Thin plate behavior controlled by " + ("plate yielding" if my < mq or mq != mq else "bolt rupture with prying")
            beh.append((f"End plate {P['k']} behavior ({SIDE_EN[sd]} in tension, {s['cfg']})", t))
    checks, rank = {}, {}
    for c in R["checks"]:
        grp, name, ref, rk = check_en(c["id"], c)
        checks.setdefault(grp, []).append([name, f"[{UNIT_EN.get(c['unit'], c['unit'])}]", _num(c["cap"]), _num(abs(c["dem"])),
                                           c["combo"], _num(c["ratio"]), ref, c["ratio"], c["info"]])
        rank[grp] = min(rank.get(grp, 999), rk)
    order = sorted(checks, key=lambda g: (rank[g], g))
    for rows in checks.values():
        rows.sort(key=lambda r: next((i for i, k in enumerate(ROW_ORDER) if r[0].startswith(k)), 99))
    gov = R["gov"]
    b1, b2 = G["b1"], G["b2"]
    return dict(
        date=datetime.datetime.now().strftime("%m/%d/%Y %I:%M %p").lstrip("0"), file=file_name,
        name=S.get("name", ""), family="Beam splice (BS)", type=("Apex moment end plate" if G["type"] == "apex" else "Beam splice moment end plate"),
        code=code, demands=demands, geo=geo, behavior=beh, checks=[(g, checks[g]) for g in order],
        ratio=gov["ratio"] if gov else 0.0,
        members=dict(beam1=b1["text"], beam2=b2["text"], slope=G["alpha"],
                     plate=f"{G['bp']:.0f} x {G['sBot'] - G['sTop']:.0f} x {S['plate']['tp1']:g}/{S['plate']['tp2']:g}",
                     bolts=f"M{R['bolt']['db']} {R['bolt']['bg']['label']}"),
    )


def to_text(rep: dict) -> list[tuple[str, str]]:
    """Danh sách (nội dung, tag) cho tk.Text: tag ∈ h1, h2, grp, row, ok, bad, dim, sub."""
    out = []
    add = lambda s, t="row": out.append((s + "\n", t))
    add(f"Current Date: {rep['date']}", "dim"); add("Units system: SI", "dim")
    if rep["file"]: add(f"File name: {rep['file']}", "dim")
    add(""); add("Steel Connections", "h1"); add("Results", "h1"); add("")
    add(f"Connection:  {rep['name']}", "h2"); add(f"Family: {rep['family']}"); add(f"Type: {rep['type']}")
    m = rep["members"]
    add(f"Beam 1: {m['beam1']}"); add(f"Beam 2: {m['beam2']}")
    if m["slope"]: add(f"Rafter slope (apex): {m['slope']:g} deg")
    add(f"End plates: {m['plate']} mm   Bolts: {m['bolts']}"); add("")
    add(f"Design code: {rep['code']}", "h2"); add("")
    add("Demands", "h2")
    w = [18, 10, 10, 11, 12, 12, 13, 16, 11]
    fmt = lambda row, ws: "".join((f"{str(c)[:wd - 1]:<{wd}}" if i == 0 else f"{str(c):>{wd}}") for i, (c, wd) in enumerate(zip(row, ws)))
    add(fmt(DEM_HEAD, w), "grp")
    for r in rep["demands"]: add(fmt(r, w))
    add(""); add("Geometric Considerations", "h2")
    wg = [58, 8, 10, 10, 10, 6]
    add(fmt(GEO_HEAD[:6], wg) + "  References", "grp")
    for grp, rows in rep["geo"].items():
        add(grp, "sub")
        for r in rep["geo"][grp]: add(fmt(r[:6], wg) + "  " + r[6], "row" if r[5] == "OK" else "bad")
    add(""); add("Plate Behavior", "h2")
    for a, b in rep["behavior"]:
        add(a, "sub"); add(b)
    add(""); add("Design Check", "h2")
    wc = [56, 9, 11, 11, 18, 7]
    add(fmt(CHK_HEAD[:6], wc) + "  References", "grp")
    for grp, rows in rep["checks"]:
        add(grp, "sub")
        for r in rows:
            add(fmt(r[:6], wc) + "  " + r[6], "dim" if r[8] else ("bad" if r[7] > 1.0001 else "row"))
    add(""); add(f"Global critical strength ratio    {_num(rep['ratio'])}", "ok" if rep["ratio"] <= 1.0001 else "bad")
    return out


def to_docx(rep: dict, path: str):
    _p, _tbl = KR._p, KR._tbl
    m = rep["members"]
    b = [_p(f"Current Date: {rep['date']}", size=16), _p("Units system: SI", size=16)]
    if rep["file"]: b.append(_p(f"File name: {rep['file']}", size=16))
    b += [_p(""), _p("Steel Connections", True, 32, "2E7D32"), _p("Results", True, 28), _p("")]
    b += [_p(f"Connection:  {rep['name']}", True, 22), _p(f"Family: {rep['family']}"), _p(f"Type: {rep['type']}"),
          _p(f"Beam 1: {m['beam1']}"), _p(f"Beam 2: {m['beam2']}")]
    if m["slope"]: b.append(_p(f"Rafter slope (apex): {m['slope']:g} deg"))
    b += [_p(f"End plates: {m['plate']} mm   Bolts: {m['bolts']}"), _p(""), _p(f"Design code: {rep['code']}", True, 22), _p(""),
          _p("Demands", True, 24), _tbl(DEM_HEAD, rep["demands"], [1700, 900, 900, 1000, 1100, 1100, 1100, 1300, 900])]
    b += [_p(""), _p("Geometric Considerations", True, 24)]
    rows = []
    for grp, rr in rep["geo"].items():
        rows.append(grp); rows += rr
    b.append(_tbl(GEO_HEAD, rows, [3900, 700, 900, 900, 900, 600, 2000]))
    b += [_p(""), _p("Plate Behavior", True, 24)]
    for a, t in rep["behavior"]:
        b += [_p(a, True, 18), _p(t, size=18)]
    b += [_p(""), _p("Design Check", True, 24)]
    rows = []
    for grp, rr in rep["checks"]:
        rows.append(grp); rows += [r[:7] for r in rr]
    b.append(_tbl(CHK_HEAD, rows, [3600, 800, 1000, 1000, 1200, 700, 1600]))
    b += [_p(""), _p(f"Global critical strength ratio    {_num(rep['ratio'])}", True, 24, "2E7D32" if rep["ratio"] <= 1.0001 else "C00000"),
          _p(""), _p("Kết quả cần được kỹ sư có chứng chỉ kiểm tra.", size=16, color="7B8794")]
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
