"""
ram_export.py — Xuất knee sang RAM Connection (.rcnx) và tạo tiết diện trong database .sec
=========================================================================================
• .rcnx là SQLite. File xuất được dựng từ khuôn `ram_proto.rcnx` (1 connection Bentley.AISC.MEPlateKneeBCF
  lấy từ file thật của RAM Connection 23) → mỗi knee/nhóm = 1 Joint + 1 Cnx + bảng thuộc tính + bảng _Loads.
• Mã hoá đã đối chiếu với file RAM:
    DesignCode      2 = AISC-10 ASD, 3 = AISC-10 LRFD, 5 = AISC-16 LRFD
    BEPlateType     0 = Flush, 1 = Extended external edge, 2 = Extended internal edge, 3 = Extended both edges
    PlateAlignment  1 = Perpendicular, 2 = Vertical, 3 = Horizontal
    *WeldType       0 = Fillet, 1 = CJP
• Tiết diện: "I {hw}x{bf}x{tw}x{tf}" trong "<Catalog>\\Built up.sec" [BuiltUpI.leo] (bf1, bf2, d, tf1, tf2, tw);
  cấu kiện vát dùng cùng tên + Initial/Final depth (đúng cách RAM lưu knee).
"""

from __future__ import annotations

import datetime
import os
import shutil
import sqlite3
import uuid

import engine as K
from knee_section import SectionError, parse_section

HERE = os.path.dirname(os.path.abspath(__file__))
PROTO = os.path.join(HERE, "ram_proto.rcnx")
SEC_DIR = r"C:\ProgramData\Bentley\Engineering\RAM Connection\23.0.0\Database\Sections\WS Section-Hoang"
SEC_FILE = "Built up.sec"

DESIGN_CODE = {"AISC 2010 LRFD": ("3", "AISC-10 LRFD"), "AISC 2016 LRFD": ("5", "AISC-16 LRFD"), "AISC 2010 ASD": ("2", "AISC-10 ASD")}
PLATE_TYPE = {"flush": "0", "external": "1", "internal": "2", "both": "3"}
ALIGN = {"perpendicular": ("1", "Perpendicular"), "vertical": ("2", "Vertical"), "horizontal": ("3", "Horizontal"), "bisector": ("1", "Perpendicular")}
EXT_LABEL = {"flush": "Flush", "external": "Extended upwards", "internal": "Extended downwards", "both": "Extended both ways"}


def g(x):
    return f"{float(x):.6g}"


def mm(x):
    return f"{g(x)} mm"


# ─────────────────────────── tiết diện ───────────────────────────
def member_ram(m: dict) -> dict:
    """Thông số RAM của 1 cấu kiện: tên tiết diện, kích thước DB, chiều cao đầu nút (initial) / đầu xa (final)."""
    mj = K.member_at_joint(m, "")
    L = max(float(m.get("L") or 0), 0.01)
    top_out = m.get("topIsOuter", True)
    bf1, tf1, bf2, tf2 = (mj["bfE"], mj["tfE"], mj["bfI"], mj["tfI"]) if top_out else (mj["bfI"], mj["tfI"], mj["bfE"], mj["tfE"])
    try:
        sec = parse_section(m["sec"])
        far = sec.at(L if m.get("jointEnd", "I") == "I" else 0.0, L)
        d_far = far.d
    except SectionError:
        import math
        d_far = mj["d"] - mj["taper_sign"] * math.tan(math.radians(mj["beta"])) * L * 1000
    hw = mj["hw"]
    if (bf1, tf1) == (bf2, tf2):
        name = f"I {g(hw)}x{g(bf1)}x{g(mj['tw'])}x{g(tf1)}"
    else:
        name = f"I {g(hw)}x{g(bf1)}x{g(mj['tw'])}x{g(tf1)}-{g(bf2)}x{g(tf2)}"
    return dict(name=name, bf1=bf1, bf2=bf2, d=mj["d"], tf1=tf1, tf2=tf2, tw=mj["tw"], d0=mj["d"], d1=d_far, L=L,
                mat=mj["mat"]["name"], unequal=(bf1, tf1) != (bf2, tf2))


def ensure_sections(members: list[dict], sec_dir: str = SEC_DIR, sec_file: str = SEC_FILE) -> dict:
    """Thêm các tiết diện còn thiếu vào <sec_dir>\\<sec_file> (sao lưu trước vào _backup). Trả về {added, existed, path}."""
    path = os.path.join(sec_dir, sec_file)
    if not os.path.isdir(sec_dir):
        raise FileNotFoundError(f"Không thấy thư mục database tiết diện: {sec_dir}")
    header = "[BuiltUpI.leo]\r\nName\tLocal\tQmod2exact\tUnit\tbf1\tbf2\td\ttf1\ttf2\ttw\r\n"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
            text = f.read()
    else:
        text = header
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or not lines[0].strip().startswith("[BuiltUpI"):
        raise ValueError(f"{sec_file} không phải bảng [BuiltUpI.leo]")
    cols = lines[1].split("\t")
    idx = {c: i for i, c in enumerate(cols)}
    have = {}
    for ln in lines[2:]:
        p = ln.split("\t")
        if len(p) >= len(cols) and p[0].strip():
            have[p[0].strip()] = p
    # tên đã có ở các file .sec khác trong cùng catalog → không thêm trùng
    import glob
    for other in glob.glob(os.path.join(sec_dir, "*.sec")):
        if os.path.abspath(other) == os.path.abspath(path):
            continue
        try:
            with open(other, "r", encoding="utf-8", errors="replace") as f:
                for ln in f:
                    nm = ln.split("	", 1)[0].strip()
                    if nm and nm not in have:
                        have[nm] = None
        except OSError:
            pass
    added, existed, conflict = [], [], []
    new_lines = []
    for m in members:
        nm = m["name"]
        if nm in have or nm in added:
            row = have.get(nm)
            if row:
                try:
                    same = abs(float(row[idx["d"]]) - m["d"]) < 0.51 and abs(float(row[idx["tw"]]) - m["tw"]) < 0.01
                except (ValueError, KeyError):
                    same = True
                (existed if same else conflict).append(nm)
            elif nm not in added:
                existed.append(nm)
            continue
        vals = {"Name": nm, "Local": "FALSE", "Qmod2exact": "FALSE", "Unit": "mm", "bf1": g(m["bf1"]), "bf2": g(m["bf2"]),
                "d": g(m["d"]), "tf1": g(m["tf1"]), "tf2": g(m["tf2"]), "tw": g(m["tw"])}
        new_lines.append("\t".join(vals.get(c, "") for c in cols))
        added.append(nm)
    if new_lines:
        if os.path.exists(path):
            bdir = os.path.join(sec_dir, "_backup")
            os.makedirs(bdir, exist_ok=True)
            shutil.copy2(path, os.path.join(bdir, f"{sec_file}.{datetime.datetime.now():%Y%m%d_%H%M%S}.bak"))
        body = [ln for ln in lines if ln.strip() != ""]
        out = "\r\n".join(body + new_lines) + "\r\n"
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(out)
        os.replace(tmp, path)
    return dict(added=added, existed=existed, conflict=conflict, path=path)


# ─────────────────────────── thuộc tính connection ───────────────────────────
def bolt_name(b: dict) -> tuple[str, str]:
    gmap = {"8.8": "G_8_8", "10.9": "G_10_9"}
    if b["grade"] in gmap:
        return f"M{b['d']} {gmap[b['grade']]}", ""
    return f"M{b['d']} G_8_8", f"Cấp bu lông {b['grade']} chưa map sang tên RAM — tạm ghi M{b['d']} G_8_8, cần chọn lại trong RAM."


def knee_props(st: dict) -> tuple[dict, dict, dict, list]:
    """(thuộc tính connection, beam ram, support ram, cảnh báo)."""
    st = K.normalize(st)
    warn = []
    pl, w, sup, sf = st["plate"], st["weld"], st["sup"], st.get("stiff", {})
    beam, col = member_ram(st["beam"]), member_ram(st["col"])
    for who, m in (("kèo", beam), ("cột", col)):
        if m["unequal"]:
            warn.append(f"Tiết diện {who} có cánh trên/dưới khác nhau — RAM knee nhận theo tiết diện BuiltUpI '{m['name']}'.")
    if pl.get("alignment") == "bisector":
        warn.append("Bản theo đường phân giác không có trong RAM — xuất thành 'Perpendicular'.")
    code = st.get("gen", {}).get("designCode", "AISC 2010 LRFD")
    bname, bw = bolt_name(st["bolt"])
    if bw: warn.append(bw)
    ext = pl.get("extension", "external")
    D = lambda x: str(int(round(float(x))))
    b01 = lambda x: "1" if x else "0"
    P = {
        "DesignCode": DESIGN_CODE.get(code, DESIGN_CODE["AISC 2010 LRFD"])[0],
        "FrameStability": b01(st.get("gen", {}).get("frameStab")),
        "HoleDef": b01(st["opt"].get("holeDef", True)),
        "SnugTightBolts": b01(st["bolt"].get("snug")),
        "ShearedEdges": b01(st["opt"].get("sheared", True)),
        "HasOppositeConnection": "0",
        "BeamSectionTapered": beam["name"], "BeamPlateMaterial": beam["mat"],
        "BeamInitialDepth": mm(beam["d0"]), "BeamFinalDepth": mm(beam["d1"]), "BeamLength": mm(beam["L"] * 1000),
        "SlopeAngle": g(st["beam"].get("slope", 0)),
        "IncludeBeamStiffener": b01(st["beam"].get("flangeStiff", {}).get("on")),
        "BeamStiffenerThickness": mm(st["beam"].get("flangeStiff", {}).get("t", 8)),
        "SupportSectionTapered": col["name"], "SupportMaterial": col["mat"],
        "SupportInitialDepth": mm(col["d0"]), "SupportFinalDepth": mm(col["d1"]), "SupportLength": mm(col["L"] * 1000),
        "BEPlateType": PLATE_TYPE.get(ext, "1"),
        "Tp": mm(pl["tp"]), "EndplateMaterial": pl["mat"],
        "FlushExtensionDistance": mm(pl["flushExt"]),
        "PlateAlignment": ALIGN.get(pl.get("alignment", "vertical"), ALIGN["vertical"])[0],
        "BeamTopFlangeWeldType": "1" if w["flE"]["type"] == "cjp" else "0",
        "BeamTopFlangeWeld": w["flE"].get("electrode", w.get("electrode", "E70XX")), "BeamTopFlangeWeldD": D(w["flE"].get("D", 5)),
        "BeamBottomFlangeWeldType": "1" if w["flI"]["type"] == "cjp" else "0",
        "BeamBottomFlangeWeld": w["flI"].get("electrode", w.get("electrode", "E70XX")), "BeamBottomFlangeWeldD": D(w["flI"].get("D", 5)),
        "WebShearWeld": w["web"].get("electrode", w.get("electrode", "E70XX")), "WebShearWeldD": D(w["web"].get("D", 4)),
        "ColEndPlateTp": mm(sup["t"]),
        "Bolt": bname, "SpaH": mm(pl["g"]), "Lev": mm(pl["Lev"]), "Leh": mm(pl["Leh"]),
        "OuterTopBoltBeamFlangeDistance": mm(pl["pfoE"]),
        "InnerTopBoltRow": str(int(pl["nE"])), "InnerTopBoltBeamFlangeDistance": mm(pl["pfiE"]), "InnerTopBoltSpaV": mm(pl["pbE"]),
        "InnerBottomBoltRow": str(int(pl["nI"])), "InnerBottomBoltBeamFlangeDistance": mm(pl["pfiI"]), "InnerBottomBoltSpaV": mm(pl["pbI"]),
        "OuterBottomBeamFlangeDistance": mm(pl["pfoI"]),
        "TransverseStiffenerFullDepth": b01(sf.get("fullDepth", True)),
        "TransverseStiffenersWidth": mm(sf.get("bs", 100)), "TransverseStiffenersCornerClips": mm(sf.get("cc", 10)),
        "TransverseStiffenersTp": mm(sf.get("ts", 10)), "TransverseStiffenersMaterial": sf.get("mat", "Q345"),
        "TransverseStiffenerWeldType": "1" if str(sf.get("weldType", "Fillet")).upper().startswith("C") else "0",
        "TransverseStiffenersWeld": sf.get("electrode", "E70XX"), "TransverseStiffenersWeldD": D(sf.get("D", 5)),
        "Optimize": "0",
    }
    return P, beam, col, warn


def _clean(name: str) -> str:
    return str(name).replace(",", ";").replace("[", "(").replace("]", ")").strip() or "LC"


def export_rcnx(states: list[dict], out_path: str, make_sections: bool = True, sec_dir: str = SEC_DIR) -> dict:
    """Ghi file .rcnx gồm các knee trong `states`. Trả về {path, n, warnings, sections}."""
    if not os.path.exists(PROTO):
        raise FileNotFoundError("Thiếu file khuôn ram_proto.rcnx (chạy tools/make_ram_proto.py).")
    if not states:
        raise ValueError("Chưa có knee nào để xuất.")
    warnings, members = [], []
    if os.path.exists(out_path):
        os.remove(out_path)
    shutil.copy2(PROTO, out_path)
    db = sqlite3.connect(out_path)
    try:
        ref0, btn0 = db.execute("select CnxRef, CnxAssignmentButton from Cnx").fetchone()
        proto_props = db.execute(f'select PropertyName, PropertyType, PropertyValue from "{ref0}"').fetchall()
        jcols = [r[1] for r in db.execute("pragma table_info(Joints)")]
        jrow0 = dict(zip(jcols, db.execute("select * from Joints").fetchone()))
        db.execute(f'drop table "{ref0}"'); db.execute(f'drop table "{ref0}_Loads"')
        for t in ("Cnx", "Joints", "Joints_Estados", "Estados"):
            db.execute(f"delete from {t}")
        db.execute("delete from ConnectionObjects where PropertyName != 'ConnectionVersion'")

        # điều kiện tải toàn mô hình = hợp các mô tả (giữ thứ tự)
        all_desc = []
        for st in states:
            for l in st["loads"]:
                d = _clean(l.get("name"))
                if d not in all_desc:
                    all_desc.append(d)
        n_lc = max(len(all_desc), 1)
        codes = []
        for i, st in enumerate(states, 1):
            P, beam, col, warn = knee_props(st)
            warnings += [f"{st.get('name', i)}: {w}" for w in warn]
            members += [beam, col]
            code_val, code_txt = DESIGN_CODE.get(st.get("gen", {}).get("designCode", "AISC 2010 LRFD"), DESIGN_CODE["AISC 2010 LRFD"])
            if code_txt not in codes: codes.append(code_txt)
            ref = "{" + str(uuid.uuid4()).upper() + "}"
            db.execute(f'create table "{ref}" (PropertyName TEXT, PropertyType INTEGER, PropertyValue TEXT)')
            db.execute(f'create table "{ref}_Loads" (PropertyName TEXT, PropertyType INTEGER, PropertyValue TEXT)')
            for name, typ, val in proto_props:
                db.execute(f'insert into "{ref}" values (?,?,?)', (name, typ, P.get(name, val)))
            loads = st["loads"]
            fmt = lambda key, unit: "[" + ",".join(f"{g(l.get(key) or 0)} {unit}" for l in loads) + "]"
            zeros = lambda unit: "[" + ",".join(f"0 {unit}" for _ in loads) + "]"
            rows = [("Count", 1, str(len(loads))),
                    ("Description", 4, "[" + ",".join(_clean(l.get("name")) for l in loads) + "]"),
                    ("Axial", 4, fmt("Nb", "kN")), ("V2", 4, fmt("Vb", "kN")), ("M33", 4, fmt("Mb", "kN*m")),
                    ("LeftBeamAxial", 4, zeros("kN")), ("LeftBeamM3", 4, zeros("kN*m")),
                    ("ColAxial", 4, fmt("Nc", "kN")), ("ColV2", 4, fmt("Vc", "kN")), ("ColM33", 4, fmt("Mc", "kN*m")),
                    ("LoadType", 5, "[" + ",".join("0" for _ in loads) + "]")]
            db.executemany(f'insert into "{ref}_Loads" values (?,?,?)', rows)

            al = ALIGN.get(st["plate"].get("alignment", "vertical"), ALIGN["vertical"])[1]
            tmpl = _clean(st.get("name") or f"KNEE {i}")
            btn = f"Basic MEP Knee {al} {EXT_LABEL.get(st['plate'].get('extension', 'external'), 'Extended upwards')}"
            db.execute("insert into Cnx (CnxTemplate, CnxRef, CnxAssignmentButton, CnxJoint, CnxDesignCode, CnxID) values (?,?,?,?,?,?)",
                       (tmpl, ref, btn, i, code_txt, i))
            jr = {k: None for k in jcols}
            jr.update(JointFamily=jrow0.get("JointFamily", 1), JointDispIndexInGroup=i,
                      JointSection1=beam["name"], JointMaterial1=beam["mat"], JointSection2=col["name"], JointMaterial2=col["mat"],
                      JointSlopeAngle1=float(st["beam"].get("slope", 0)), JointSetBack1=jrow0.get("JointSetBack1", 0.01),
                      JointMemberLength1=beam["L"], JointMemberLength2=col["L"], JointHasCLTRestraint=1,
                      JointMember1DepthInitial=beam["d0"] / 1000, JointMember1DepthFinal=beam["d1"] / 1000, JointMember1SectionType=1,
                      JointMember2DepthInitial=col["d0"] / 1000, JointMember2DepthFinal=col["d1"] / 1000, JointMember2SectionType=1,
                      JointNotes=f"{st.get('name', '')}\r\n{st['plate'].get('nE', 1)}+{st['plate'].get('nI', 1)} rows {P['Bolt']}_PL{g(st['plate']['tp'])}",
                      JointID=i)
            db.execute(f"insert into Joints ({','.join(jcols)}) values ({','.join('?' for _ in jcols)})", [jr[c] for c in jcols])
            for l in loads:
                k = all_desc.index(_clean(l.get("name")))
                db.execute("insert into Joints_Estados (Joints, Estados, JointV2, JointM33, JointAxial) values (?,?,?,?,?)",
                           (i, k, float(l.get("Vb") or 0), float(l.get("Mb") or 0), float(l.get("Nb") or 0)))
            db.execute("insert into ConnectionObjects values (?, 0, ?)", (str(i), ref))

        for _ in range(n_lc):
            db.execute("insert into Estados values (1)")
        lst = lambda v: "[" + ",".join(v for _ in range(n_lc)) + "]"
        upd = {"Count": str(n_lc), "EstadosIdCarga": "[" + ",".join(all_desc or ["LC1"]) + "]",
               "EstadosDescripcion": lst("Dead Load"), "EstadosCategoria": lst("DL"), "EstadosWoodDuration": lst("Permanent"),
               "EstadosUId": lst(""), "EstadosNotionalDirection": lst(""), "EstadosNotionalReferenceCaseId": lst(""),
               "EstadosNotionalFactor": lst("0"), "EstadosComboType": lst("0"), "EstadosEsComb": lst("0")}
        for k, v in upd.items():
            db.execute("update ModelData_LoadConditions set PropertyValue=? where PropertyName=?", (v, k))
        now = (datetime.datetime.now() - datetime.datetime(1899, 12, 30)).total_seconds() / 86400.0
        db.execute("update ModelProperties set PropertyValue=? where PropertyName='ModelDateModified'", (f"{now:.10f}",))
        db.execute("update ModelProperties set PropertyValue=? where PropertyName='DesignCode'", (", ".join(codes),))
        db.execute("update ModelProperties set PropertyValue=? where PropertyName='ModelProjectID'", ("{" + str(uuid.uuid4()).upper() + "}",))
        db.commit()
        db.execute("vacuum")
    finally:
        db.close()
    sec = None
    if make_sections:
        try:
            uniq = {m["name"]: m for m in members}
            sec = ensure_sections(list(uniq.values()), sec_dir)
            if sec["conflict"]:
                warnings.append("Tên tiết diện đã có trong database nhưng kích thước khác: " + ", ".join(sec["conflict"]))
        except Exception as e:  # noqa: BLE001
            warnings.append(f"Không ghi được database tiết diện: {e}")
    return dict(path=out_path, n=len(states), warnings=warnings, sections=sec)
