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

import base_engine as BE
import report as KR

_num = KR._num
UNIT_EN = dict(KR.UNIT_EN, **{"kN·m/m": "KN*m/m", "N/mm": "N/mm", "MPa": "MPa"})

DEM_HEAD = ["Description", "Pu [kN]", "Mu22 [kN*m]", "Mu33 [kN*m]", "Vu2 [kN]", "Vu3 [kN]", "Load type"]
GEO_HEAD = ["Dimensions", "Unit", "Value", "Min.", "Max.", "Sta.", "References"]
CHK_HEAD = ["Verification", "Unit", "Capacity", "Demand", "Ctrl EQ", "Ratio", "References"]
CASE_EN = {"axial": "Axial", "small": "Small moment", "large": "Large moment", "nosol": "No solution", "tension": "Uplift", "—": "--"}
GRP_EN = {"Bản đế": "Base plate", "Bu lông neo": "Anchors", "Bê tông": "Concrete base", "Hàn": "Welds", "Bản chắn cắt": "Shear lug"}
GEO_EN = [
    ("Phần bản nhô theo phương N", "Plate projection beyond column (N direction)"),
    ("Phần bản nhô theo phương B", "Plate projection beyond column (B direction)"),
    ("Khoảng cách neo tới mép bản", "Distance from anchor to edge"),
    ("Bước neo", "Anchor spacing"), ("Lớp bê tông bảo vệ", "Concrete cover"), ("Chiều dài hiệu quả", "Effective length"),
    ("Cỡ hàn cột", "Weld size"),
    ("Bề dày bản đế tối thiểu", "Minimum plate thickness"),
    ("Đường kính neo tối thiểu", "Minimum anchor diameter"),
    ("Tim neo tới mép bản", "Anchor center to plate edge"),
    ("Bước neo phương N", "Anchor spacing (N direction)"),
    ("Bước neo phương B", "Anchor spacing (B direction)"),
    ("Khoảng hở tâm neo", "Anchor clearance to column steel"),
    ("Khoảng cách neo tới mép gối", "Anchor edge distance to support"),
    ("Chiều dài móc", "Hook length"),
    ("Chiều sâu chôn", "Embedment depth hef"),
    ("Gối nhô ra ngoài bản đế", "Support projection beyond base plate"),
    ("Chiều cao chôn H", "Shear lug embedment"),
    ("Hàn bản chắn", "Weld size (shear lug)"),
]
DIR_EN = {"33": "major axis", "22": "minor axis", "bi": "biaxial"}


AXIS_TITLE = {"33": "major axis", "22": "minor axis"}
# id kiểm tra → (nhóm RAM, tên RAM, tham chiếu RAM (None = lấy theo engine), thứ tự)
PLATE = {
    "conc_bear": ("Concrete base", "Axial bearing", "DG1 3.1.1", 5), "conc_eff": ("Concrete base", "Bearing on effective area", None, 5),
    "bp_size": ("Concrete base", "Base plate size for large moment", None, 5),
    "bp_comp": ("Base plate", "Flexural yielding (bearing interface)", None, 10), "bp_ten": ("Base plate", "Flexural yielding (tension interface)", "DG1 Eq. 3.3.13", 11),
    "shear_fric": ("Base plate", "Friction between base plate and support", None, 12),
    "lug_bear": ("Shear lug", "Concrete bearing", None, 50), "lug_flex": ("Shear lug", "Flexural yielding", None, 50),
    "lug_v": ("Shear lug", "Shear yielding", None, 50), "lug_w": ("Shear lug", "Weld capacity", None, 50),
    "w_cap": ("Column", "Weld capacity", "DG1 p. 35", 60), "w_v": ("Column", "Elastic method weld shear capacity", "Sec. J2.4", 61),
    "w_n": ("Column", "Elastic method weld axial capacity", "Sec. J2.4", 62),
}
ANCH = {
    "aci_sa": ("Anchor tension", "Eq. D-3", 1), "aci_pn": ("Pullout of anchor in tension", "Sec. D.4.1.1", 2),
    "aci_sb": ("Side-face blowout", "Sec. D.4.1.1", 3), "aci_cb": ("Concrete breakout of group of anchors in tension", "Sec. D.4.1.1", 4),
    "aci_rt": ("Anchors reinforcement in tension", "Sec. D.5.2.9, D.6.2.9", 5),
    "aci_vsa": ("Anchor shear", "Eq. D-20, Sec. D.6.1.3", 6), "aci_cp1": ("Pryout of anchor in shear", "Sec. D.4.1.1", 7),
    "aci_cp": ("Pryout of group of anchors in shear", "Sec. D.4.1.1", 8), "aci_vcb": ("Concrete breakout of group of anchors in shear", "Sec. D.4.1.1", 9),
    "aci_rv": ("Anchors reinforcement in shear", "Sec. D.5.2.9, D.6.2.9", 10), "aci_int": ("Interaction of tensile and shear forces", "Sec. D.7", 11),
}


def _split_id(cid):
    """'w_v_33' → ('w_v', '33');  'bp_comp_bi' → ('bp_comp', 'bi');  'aci_sb+x' → ('aci_sb', None)."""
    m = re.fullmatch(r"(.+?)_(33|22|bi)", cid)
    if m: return m[1], m[2]
    m = re.fullmatch(r"(aci_sb)[+-][xz]", cid)
    if m: return m[1], None
    return cid, None


def check_en(cid: str, c: dict) -> tuple[str, str, int]:
    base, _ax = _split_id(cid)
    if base in PLATE:
        g, n, _r, rk = PLATE[base]; return g, n, rk
    if base in ANCH:
        n, _r, rk = ANCH[base]; return "Anchors", n, 30 + rk
    return c["grp"], c["name"], 99


def _unit(u, cap, dem):
    """Đơn vị và giá trị như RAM: áp lực theo KN/mm2."""
    if u == "MPa": return "KN/mm2", cap / 1e3, dem / 1e3
    if u == "N/mm": return "KN/m", cap, dem
    if u == "": return "KN", cap, dem
    return UNIT_EN.get(u, u), cap, dem


def _row(ch, name, ref):
    u, cap, dem = _unit(ch["unit"], ch["cap"], abs(ch["dem"]))
    return [name, f"[{u}]" if u else "", _num(cap), _num(dem), ch["combo"], "--" if ch["info"] else _num(ch["ratio"]),
            ref or ch["ref"], ch["ratio"], ch["info"], ch["id"]]


def build(S: dict, R: dict, file_name: str = "") -> dict:
    G = R["G"]; c = G["col"]; an = S["anchor"]
    gen = S.get("gen", {})
    steel = gen.get("designCode", "AISC 2010 LRFD").replace("AISC 2010", "AISC 360-10").replace("AISC 2016", "AISC 360-16")
    conc = gen.get("concCode", "ACI 318-08")
    demands = [[d["name"], _num(d["N"]), _num(d["M22"]), _num(d["M33"]), _num(d["V2"]), _num(d["V3"]), "Design"] for d in R["demands"]]
    geo_p, geo_a = {}, {}
    for x in R["geo"]:
        name = next((e for k, e in GEO_EN if x["name"].startswith(k)), x["name"])
        nd = 0 if x["unit"] == "1/16in" else 2
        tgt = geo_a if x["grp"] == "Bu lông neo" else geo_p
        tgt.setdefault(GRP_EN.get(x["grp"], x["grp"]), []).append(
            [name, f"[{x['unit']}]" if x["unit"] else "", _num(x["val"], nd), _num(x["min"], nd), _num(x["max"], nd), "OK" if x["ok"] else "N.G.", x["ref"]])
    axis = gen.get("axis", "both")
    axes_used = {"major": ["33"], "minor": ["22"]}.get(axis, ["33", "22"])
    blocks = []
    for ax in axes_used:
        pl_checks, rank, an_rows = {}, {}, []
        for ch in R["checks"]:
            base, a = _split_id(ch["id"])
            if a in ("33", "22") and a != ax: continue
            if base in ANCH:
                n, ref, rk = ANCH[base]
                an_rows.append((rk, _row(ch, n, ref)))
            else:
                g, n, ref, rk = PLATE.get(base, (ch["grp"], ch["name"], None, 99))
                pl_checks.setdefault(g, []).append(_row(ch, n, ref))
                rank[g] = min(rank.get(g, 999), rk)
        for rows in pl_checks.values():
            rows.sort(key=lambda r: next((v[3] for k, v in PLATE.items() if v[1] == r[0]), 99))
        order = sorted(pl_checks, key=lambda g: (rank[g], g))
        an_rows = [r for _k, r in sorted(an_rows, key=lambda t: t[0])]
        pr = max([r[7] for g in order for r in pl_checks[g] if not r[8]] + [0.0])
        ar = max([r[7] for r in an_rows if not r[8]] + [0.0])
        blocks.append(dict(title=f"Design for {AXIS_TITLE[ax]}", sub=f"Base plate ({steel})", geo=geo_p, checks=[(g, pl_checks[g]) for g in order], ratio=pr,
                           anchors=dict(geo=geo_a, rows=an_rows, ratio=ar) if (an_rows or geo_a) else None))
    # chi tiết: Maximum compression / Maximum tension cho từng trục phân tích
    details = []
    keys = ["bi"] if axis == "biaxial" else [k for k in ("33", "22") if k in axes_used]
    for ax in keys:
        ds = [d for d in R["demands"] if ax in d.get("axes", {})]
        if not ds: continue
        subs = []
        dc = max(ds, key=lambda d: d["axes"][ax]["fpmax"])
        if dc["axes"][ax]["fpmax"] > 0: subs.append(("Maximum compression", dc))
        dt = max(ds, key=lambda d: d["Tmax"])
        if dt["Tmax"] > 0: subs.append(("Maximum tension", dt))
        if not subs: subs.append(("Maximum compression", dc))
        sec = []
        for lab, dm in subs:
            A = dm["axes"][ax]
            noNA = A["fpmax"] <= 0 or A["Y"] >= (G["N"] if ax != "22" else G["B"]) - 1e-6
            vcol = abs(dm["V2"] if ax != "22" else dm["V3"]) / len(G["anchors"])
            summ = [("Maximum bearing pressure", A["fpmax"], "[N/mm2]"), ("Minimum bearing pressure", A["fpmin"], "[N/mm2]"),
                    ("Maximum anchor tension", -max(dm["T"]) if max(dm["T"]) > 0 else 0.0, "[kN]"),
                    ("Minimum anchor tension", -min(dm["T"]) if min(dm["T"]) > 0 else 0.0, "[kN]"),
                    ("Neutral axis angle", A["ang"], "[deg]"), ("Neutral axis location", None if noNA else A["loc"], "[mm]"),
                    ("Bearing length", A["Y"], "[mm]")]
            rows = [[str(i + 1), _num(a["y"]), _num(a["x"]), _num(vcol), _num(t)] for i, (a, t) in enumerate(zip(G["anchors"], dm["T"]))]
            sec.append(dict(title=f"{lab} ({dm['name']})", summary=summ, anchors=rows, field=A.get("field", ("none",)), T=list(dm["T"])))
        details.append(dict(title={"bi": "Biaxial", "33": "Major axis", "22": "Minor axis"}[ax], subs=sec))
    gov = R["gov"]
    geom = dict(N=G["N"], B=G["B"], d=G["d"], ox=G["ox"], oz=G["oz"], tw=c["tw"], bfE=c["bfE"], tfE=c["tfE"], bfI=c["bfI"], tfI=c["tfI"],
                da=float(an["d"]), hole=G["hole"], anchors=[(a["x"], a["y"]) for a in G["anchors"]])
    return dict(
        date=datetime.datetime.now().strftime("%m/%d/%Y %I:%M %p").lstrip("0"), file=file_name,
        name=S.get("name", ""), family="Column - Base (CB)", type="Base plate", desc=S.get("desc", ""), code=f"{steel}, {conc}",
        demands=demands, geo=geo_p, blocks=blocks, details=details, geom=geom,
        checks=[g for b in blocks for g in b["checks"]] + ([("Anchors", blocks[0]["anchors"]["rows"])] if blocks and blocks[0].get("anchors") else []),
        ratio=gov["ratio"] if gov else 0.0, global_ratio=True,
        notes=list(R.get("notes", [])), warnings=list(R["W"]),
        members=[("Column", f"{c['text']}  ({S['col']['mat']})"),
                 ("Base plate", f"{G['N']:g} x {G['B']:g} x {G['tp']:g} mm  ({S['plate']['mat']})"),
                 ("Anchors", f"{len(G['anchors'])} x {BE.anchor_label(an['d'])} {G['am']['name']}, hef = {float(an['hef']):g} mm")],
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
