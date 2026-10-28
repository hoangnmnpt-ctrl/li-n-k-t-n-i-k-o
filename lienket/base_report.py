"""
base_report.py — Báo cáo tiếng Anh theo form RAM Connection ("Steel Connections – Results") cho CHÂN CỘT (Base plate)
=====================================================================================================================
build(S, R) → cấu trúc báo cáo;  to_text() cho Print (xem báo cáo);  to_docx() xuất Word (không cần thư viện ngoài).
Bố cục: Members / Base plate / Anchors / Concrete · Demands · Geometric Considerations · Design Check · Global critical strength ratio.
Dựng Word dùng lại các hàm _p, _tbl của report.py (knee).
"""

from __future__ import annotations

import datetime
import re
import zipfile

import report as KR

_num = KR._num
UNIT_EN = dict(KR.UNIT_EN, **{"kN·m/m": "KN*m/m", "N/mm": "N/mm", "MPa": "MPa"})

DEM_HEAD = ["Description", "Pu [kN]", "V2 [kN]", "V3 [kN]", "M33 [kN*m]", "M22 [kN*m]", "Tu anchor [kN]", "Bearing (M33)", "Load type"]
GEO_HEAD = ["Dimensions", "Unit", "Value", "Min.", "Max.", "Sta.", "References"]
CHK_HEAD = ["Verification", "Unit", "Capacity", "Demand", "Ctrl EQ", "Ratio", "References"]
CASE_EN = {"axial": "Axial", "small": "Small moment", "large": "Large moment", "nosol": "No solution", "tension": "Uplift", "—": "--"}
GRP_EN = {"Bản đế": "Base plate", "Bu lông neo": "Anchors", "Bê tông": "Concrete support", "Hàn": "Welds", "Bản chắn cắt": "Shear lug"}
GEO_EN = [
    ("Phần bản nhô theo phương N", "Plate projection beyond column (N direction)"),
    ("Phần bản nhô theo phương B", "Plate projection beyond column (B direction)"),
    ("Khoảng cách mép bản ex", "Edge distance to plate (N direction)"),
    ("Khoảng cách mép bản ey", "Edge distance to plate (B direction)"),
    ("Bước neo phương N", "Anchor spacing (N direction)"),
    ("Bước neo phương B", "Anchor spacing (B direction)"),
    ("Khoảng hở tâm neo", "Anchor clearance to column steel"),
    ("Khoảng cách neo tới mép gối", "Anchor edge distance to support"),
    ("Chiều dài móc", "Hook length"),
    ("Chiều sâu chôn", "Embedment depth hef"),
    ("Gối nhô ra ngoài bản đế", "Support projection beyond base plate"),
    ("Hàn góc cánh cột", "Weld size (column flanges)"),
    ("Hàn góc bụng cột", "Weld size (column web)"),
    ("Chiều cao chôn H", "Shear lug embedment"),
    ("Hàn bản chắn", "Weld size (shear lug)"),
]
DIR_EN = {"33": "major axis", "22": "minor axis", "bi": "biaxial"}


def check_en(cid: str, c: dict) -> tuple[str, str, int]:
    """id kiểm tra → (nhóm RAM, tên RAM, thứ tự nhóm)."""
    m = re.fullmatch(r"(conc_bear|conc_eff|bp_size|bp_comp)_(\d\d|bi)", cid)
    if m:
        k, ax = m[1], DIR_EN[m[2]]
        if k == "conc_bear": return "Concrete support", f"Concrete bearing ({ax})", 20
        if k == "conc_eff": return "Concrete support", f"Concrete bearing on effective area ({ax})", 20
        if k == "bp_size": return "Concrete support", f"Base plate size for large moment ({ax})", 20
        return "Base plate", f"Flexural yielding - bearing interface ({ax})", 10
    simple = {
        "bp_ten": ("Base plate", "Flexural yielding - tension interface", 10),
        "anc_t": ("Anchors (AISC 360)", "Tensile strength", 30), "anc_v": ("Anchors (AISC 360)", "Shear strength", 30),
        "anc_tv": ("Anchors (AISC 360)", "Tensile strength with shear (interaction)", 30),
        "aci_sa": ("Anchors (ACI 318)", "Steel strength in tension", 40),
        "aci_cb": ("Anchors (ACI 318)", "Concrete breakout strength in tension", 40),
        "aci_rt": ("Anchors (ACI 318)", "Tension reinforcement - required area", 40),
        "aci_pn": ("Anchors (ACI 318)", "Pullout strength", 40),
        "aci_vsa": ("Anchors (ACI 318)", "Steel strength in shear", 41),
        "aci_cp": ("Anchors (ACI 318)", "Concrete pryout strength", 41),
        "aci_int": ("Anchors (ACI 318)", "Tension and shear interaction", 42),
        "shear_fric": ("Shear transfer", "Friction between base plate and support", 50),
        "lug_bear": ("Shear lug", "Concrete bearing on shear lug", 55), "lug_flex": ("Shear lug", "Flexural yielding", 55),
        "lug_v": ("Shear lug", "Shear yielding", 55), "lug_w": ("Shear lug", "Weld capacity", 55),
        "w_fl": ("Column", "Weld capacity (flanges)", 60), "w_web": ("Column", "Weld capacity (web)", 60),
    }
    if cid in simple: return simple[cid]
    m = re.fullmatch(r"aci_sb([+-][xz])", cid)
    if m: return "Anchors (ACI 318)", f"Side-face blowout ({m[1]} edge)", 40
    m = re.fullmatch(r"aci_(vcb|rv)_(\d)", cid)
    if m:
        lab = "V2" if m[2] == "0" else "V3"
        return ("Anchors (ACI 318)", f"Concrete breakout strength in shear ({lab})" if m[1] == "vcb"
                else f"Shear reinforcement - required area ({lab})", 41)
    return c["grp"], c["name"], 99


def build(S: dict, R: dict, file_name: str = "") -> dict:
    G = R["G"]; c = G["col"]; an = S["anchor"]; ped = S["ped"]
    code = (S.get("gen", {}).get("designCode", "AISC 2010 LRFD").replace("AISC 2010", "AISC 360-10").replace("AISC 2016", "AISC 360-16")
            + " · " + S.get("gen", {}).get("concCode", "ACI 318-11"))
    demands = [[d["name"], _num(-d["N"]), _num(d["V2"]), _num(d["V3"]), _num(d["M33"]), _num(d["M22"]), _num(d["Tmax"]),
                CASE_EN.get(d["case33"], d["case33"]), "Design"] for d in R["demands"]]
    geo = {}
    for x in R["geo"]:
        name = next((e for k, e in GEO_EN if x["name"].startswith(k)), x["name"])
        geo.setdefault(GRP_EN.get(x["grp"], x["grp"]), []).append(
            [name, f"[{x['unit']}]" if x["unit"] else "", _num(x["val"]), _num(x["min"]), _num(x["max"]), "OK" if x["ok"] else "N.G.", x["ref"]])
    checks, rank = {}, {}
    for ch in R["checks"]:
        grp, name, rk = check_en(ch["id"], ch)
        checks.setdefault(grp, []).append([name, f"[{UNIT_EN.get(ch['unit'], ch['unit'])}]", _num(ch["cap"]), _num(abs(ch["dem"])),
                                           ch["combo"], "--" if ch["info"] else _num(ch["ratio"]), ch["ref"], ch["ratio"], ch["info"], ch["id"]])
        rank[grp] = min(rank.get(grp, 999), rk)
    order = sorted(checks, key=lambda g: (rank[g], g))
    gov = R["gov"]
    gen = S.get("gen", {})
    shear = ("Shear lug" if S["lug"].get("on") else "Anchors") + (" + friction" if gen.get("friction") else "")
    return dict(
        date=datetime.datetime.now().strftime("%m/%d/%Y %I:%M %p").lstrip("0"), file=file_name,
        name=S.get("name", ""), family="Column base (CB)", type="Base plate", code=code,
        demands=demands, geo=geo, checks=[(g, checks[g]) for g in order], ratio=gov["ratio"] if gov else 0.0, warnings=list(R["W"]),
        members=[
            ("Column", f"{c['text']}  ({S['col']['mat']})"),
            ("Base plate", f"{G['N']:g} x {G['B']:g} x {G['tp']:g} mm  ({S['plate']['mat']})"),
            ("Anchors", f"{len(G['anchors'])} x M{an['d']} {G['am']['name']} ({'Headed' if an.get('type') != 'hooked' else 'Hooked'}), "
                        f"hef = {float(an['hef']):g} mm, {an.get('layout', 'longitudinal').capitalize()} position, "
                        f"{an.get('nr', 1)} row(s) per side x {an.get('npr', 2)}, edge {float(an['ex']):g} / {float(an['ey']):g} mm"
                        + (", cracked concrete" if an.get("cracked", True) else "")),
            ("Support", f"{'Pedestal' if ped.get('isPed', True) else 'Footing'} {G['N2']:g} x {G['B2']:g} x {G['ha']:g} mm, {ped.get('mat', '')} "
                        f"(f'c = {float(ped['fc']):g} MPa)" + (f", grout {G['grout']:g} mm" if G["grout"] > 0 else "")),
            ("Analysis", {"major": "Major axis", "minor": "Minor axis", "both": "Both axes", "biaxial": "Biaxial"}.get(gen.get("axis", "both"), "")
                         + f", {gen.get('pressure', 'uniform').capitalize()} pressure distribution"
                         + (", strain compatibility" if gen.get("compat") else "")),
            ("Shear transfer", shear),
        ],
    )


def to_text(rep: dict) -> list[tuple[str, str]]:
    """Danh sách (nội dung, tag) cho tk.Text: tag ∈ h1, h2, grp, row, ok, bad, dim, sub."""
    out = []
    add = lambda s, t="row": out.append((s + "\n", t))
    add(f"Current Date: {rep['date']}", "dim"); add("Units system: SI", "dim")
    if rep["file"]: add(f"File name: {rep['file']}", "dim")
    add(""); add("Steel Connections", "h1"); add("Results", "h1"); add("")
    add(f"Connection:  {rep['name']}", "h2"); add(f"Family: {rep['family']}"); add(f"Type: {rep['type']}")
    for k, v in rep["members"]: add(f"{k}: {v}")
    add(""); add(f"Design code: {rep['code']}", "h2"); add("")
    add("Demands", "h2")
    w = [18, 10, 10, 10, 12, 12, 15, 15, 11]
    fmt = lambda row, ws: "".join((f"{str(c)[:wd - 1]:<{wd}}" if i == 0 else f"{str(c):>{wd}}") for i, (c, wd) in enumerate(zip(row, ws)))
    add(fmt(DEM_HEAD, w), "grp")
    for r in rep["demands"]: add(fmt(r, w))
    add("  Pu > 0: compression", "dim")
    add(""); add("Geometric Considerations", "h2")
    wg = [52, 8, 10, 10, 10, 6]
    add(fmt(GEO_HEAD[:6], wg) + "  References", "grp")
    for grp, rows in rep["geo"].items():
        add(grp, "sub")
        for r in rows: add(fmt(r[:6], wg) + "  " + r[6], "row" if r[5] == "OK" else "bad")
    add(""); add("Design Check", "h2")
    wc = [56, 10, 11, 11, 18, 7]
    add(fmt(CHK_HEAD[:6], wc) + "  References", "grp")
    for grp, rows in rep["checks"]:
        add(grp, "sub")
        for r in rows:
            add(fmt(r[:6], wc) + "  " + r[6], "dim" if r[8] else ("bad" if r[7] > 1.0001 else "row"))
    if rep["warnings"]:
        add(""); add("Notes", "h2")
        for x in rep["warnings"]: add("• " + x, "dim")
    add(""); add(f"Global critical strength ratio    {_num(rep['ratio'])}", "ok" if rep["ratio"] <= 1.0001 else "bad")
    return out


def to_docx(rep: dict, path: str):
    _p, _tbl = KR._p, KR._tbl
    b = [_p(f"Current Date: {rep['date']}", size=16), _p("Units system: SI", size=16)]
    if rep["file"]: b.append(_p(f"File name: {rep['file']}", size=16))
    b += [_p(""), _p("Steel Connections", True, 32, "2E7D32"), _p("Results", True, 28), _p("")]
    b += [_p(f"Connection:  {rep['name']}", True, 22), _p(f"Family: {rep['family']}"), _p(f"Type: {rep['type']}")]
    b += [_p(f"{k}: {v}") for k, v in rep["members"]]
    b += [_p(""), _p(f"Design code: {rep['code']}", True, 22), _p(""),
          _p("Demands", True, 24), _tbl(DEM_HEAD, rep["demands"], [1700, 900, 900, 900, 1000, 1000, 1100, 1300, 900]),
          _p("Pu > 0: compression", size=16, color="7B8794")]
    b += [_p(""), _p("Geometric Considerations", True, 24)]
    rows = []
    for grp, rr in rep["geo"].items():
        rows.append(grp); rows += rr
    b.append(_tbl(GEO_HEAD, rows, [3900, 700, 900, 900, 900, 600, 2300]))
    b += [_p(""), _p("Design Check", True, 24)]
    rows = []
    for grp, rr in rep["checks"]:
        rows.append(grp); rows += [r[:7] for r in rr]
    b.append(_tbl(CHK_HEAD, rows, [3600, 800, 1000, 1000, 1200, 700, 1900]))
    if rep["warnings"]:
        b += [_p(""), _p("Notes", True, 22)] + [_p("• " + x, size=16) for x in rep["warnings"]]
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
