"""
ram_export.py — Xuất liên kết sang RAM Connection (.rcnx) và tạo tiết diện trong database .sec
=============================================================================================
• .rcnx là SQLite. File xuất được dựng từ khuôn `ram_proto.rcnx` (lấy từ file thật của RAM Connection 24, xem
  tools/make_ram_proto.py): 1 connection mỗi loại — Bentley.AISC.MEPlateKneeBCF (knee), Bentley.AISC.BasePlate (chân cột),
  Bentley.AISC.MEPlateBeamSplice (nối dầm / apex) → mỗi liên kết = 1 Joint + 1 Cnx + bảng thuộc tính + bảng _Loads.
• Mã hoá đã đối chiếu với file RAM:
    DesignCode      2 = AISC-10 ASD, 3 = AISC-10 LRFD, 5 = AISC-16 LRFD
    BEPlateType     0 = Flush, 1 = Extended external edge, 2 = Extended internal edge, 3 = Extended both edges
    PlateAlignment  1 = Perpendicular, 2 = Vertical, 3 = Horizontal
    *WeldType       0 = Fillet, 1 = CJP
• Tiết diện: "I {hw}x{bf}x{tw}x{tf}" trong "<Catalog>\\Built up.sec" [BuiltUpI.leo] (bf1, bf2, d, tf1, tf2, tw);
  cấu kiện vát dùng cùng tên + Initial/Final depth (đúng cách RAM lưu knee).
"""

from __future__ import annotations

import copy
import datetime
import os
import shutil
import sqlite3
import uuid

import engine as K
from knee_section import SectionError, parse_section

HERE = os.path.dirname(os.path.abspath(__file__))
PROTO = os.path.join(HERE, "ram_proto.rcnx")
_RAM_ROOT = r"C:\ProgramData\Bentley\Engineering\RAM Connection"
_SEC_SUB = r"Database\Sections\WS Section-Hoang"


def _sec_dir() -> str:
    """Thư mục database tiết diện của phiên bản RAM Connection mới nhất có trên máy (mặc định 24.0.0)."""
    import glob
    found = sorted(glob.glob(os.path.join(_RAM_ROOT, "*", _SEC_SUB)),
                   key=lambda p: [int(x) if x.isdigit() else 0 for x in os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(p)))).split(".")])
    return found[-1] if found else os.path.join(_RAM_ROOT, "24.0.0", _SEC_SUB)


SEC_DIR = _sec_dir()
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
    """Thông số RAM của 1 cấu kiện: tên tiết diện, kích thước DB, chiều cao đầu nút (initial) / đầu xa (final).
    Tên đã theo kiểu RAM ("I 300x215x5x10", "I 650-5/150-8", W…) được giữ nguyên; tên kiểu tool (500.8-200.12) → "I hw x bf x tw x tf"."""
    import base_engine as BE
    raw = str(m.get("sec", "")).strip()
    keep = None
    if not m.get("dims") and BE.w_dims(raw):
        m = dict(m, dims=BE.w_dims(raw)); keep = raw
    elif raw[:2].upper() == "I " and "(" not in raw:
        keep = raw
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
    return dict(name=keep or name, bf1=bf1, bf2=bf2, d=mj["d"], tf1=tf1, tf2=tf2, tw=mj["tw"], d0=mj["d"], d1=d_far, L=L,
                mat=mj["mat"]["name"], unequal=(bf1, tf1) != (bf2, tf2), catalog=bool(keep and not raw.upper().startswith("I")),
                tapered=abs(d_far - mj["d"]) > 0.5)


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
    """Tên bu lông trong RAM Connection 24: "M24 G88" (đối chứng file RAM 24.0.4)."""
    gr = str(b["grade"])
    if gr in ("8.8", "10.9"):
        w = "" if gr == "8.8" else f"Tên bu lông 'M{b['d']} G109' (10.9) chưa đối chứng với RAM — kiểm tra lại trong RAM."
        return f"M{b['d']} G{gr.replace('.', '')}", w
    return f"M{b['d']} G88", f"Cấp bu lông {gr} chưa map sang tên RAM — tạm ghi M{b['d']} G88, cần chọn lại trong RAM."


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
        "InnerTopBoltRowFlushed": "1", "InnerBottomBoltRowFlushed": "1",
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


# Loại liên kết của tool → ClassName trong RAM Connection (khuôn trong ram_proto.rcnx).
RAM_CLASS = {"knee": "Bentley.AISC.MEPlateKneeBCF", "base": "Bentley.AISC.BasePlate", "splice": "Bentley.AISC.MEPlateBeamSplice"}
KIND_LABEL = {"knee": "Knee (BCF)", "base": "Column base (CB)", "splice": "Beam splice / Apex (BS)"}
JOINT_FAMILY = {"knee": 1, "base": 10, "splice": 4}
KSI = 6.894757                                         # MPa / ksi


def supported(kind: str) -> bool:
    return kind in RAM_CLASS


def unsupported_note(joints: list[dict]) -> str:
    """Thông báo các liên kết chưa xuất được (chưa có khuôn RAM cho loại đó)."""
    if not joints:
        return ""
    by = {}
    for j in joints:
        by.setdefault(KIND_LABEL.get(j["kind"], j["kind"]), []).append(str(j.get("state", {}).get("name") or j.get("id")))
    lines = [f"  • {k}: {', '.join(v)}" for k, v in by.items()]
    return ("Chưa xuất (chưa có khuôn RAM cho loại này — cần 1 file .rcnx của RAM có sẵn liên kết loại đó,\n"
            "chạy tools/make_ram_proto.py để lấy khuôn):\n" + "\n".join(lines))


class _Codes:
    """Mã lựa chọn của RAM: (giá trị, đã đối chứng với file RAM thật?). Mã chưa đối chứng → cảnh báo."""

    def __init__(self):
        self.unverified = []

    def __call__(self, label, table, key, default=None):
        val, ok = table.get(key, (default, False)) if default is not None else table[key]
        if not ok:
            self.unverified.append(f"{label} = {key}")
        return val


b01 = lambda x: "1" if x else "0"


def base_props(st: dict) -> tuple[dict, dict, list, dict]:
    """Chân cột → thuộc tính Bentley.AISC.BasePlate. Trả về (thuộc tính, cột ram, cảnh báo, tải)."""
    import base_engine as BE
    st = BE.normalize(copy.deepcopy(st))
    C = _Codes()
    gen, colS, pl, ped, an, rf, w, lug, o = (st[k] for k in ("gen", "col", "plate", "ped", "anchor", "reinf", "weld", "lug", "opt"))
    warn = []
    col = member_ram(dict(colS, topIsOuter=True))
    code = gen.get("designCode", "AISC 2010 LRFD")
    rebar = list(BE.REBAR_US)
    P = {
        "DesignCode": C("Steel design code", {"AISC 2010 LRFD": ("3", True), "AISC 2016 LRFD": ("5", True), "AISC 2010 ASD": ("2", True),
                                              "AISC 2016 ASD": ("4", False)}, code, "3"),
        "ConcreteDesignCode": C("Concrete design code", {c: (str(i), i == 0) for i, c in enumerate(BE.CONC_CODES)}, gen.get("concCode", "ACI 318-08"), "0"),
        "BasePlateDesignAxis": C("Analysis axis", {"major": ("0", False), "minor": ("1", False), "both": ("2", False), "biaxial": ("3", True)},
                                 gen.get("axis", "both"), "2"),
        "PressureDistribution": C("Pressure distribution", {"uniform": ("0", True), "triangular": ("1", False)}, gen.get("pressure", "uniform"), "0"),
        "ConsiderStrainCompatibility": b01(gen.get("compat")),
        "SeismicProvisions": b01(gen.get("seismic")),
        "BearingStressCalculationMethod": C("Bearing stress calculation", {"complete": ("1", True), "effective": ("0", False)},
                                            gen.get("bearCalc", "complete"), "1"),
        "IncludeFrictionBetweenBasePlateAndConcrete": b01(gen.get("friction")),
        "OptimizePlateThickness": b01(o.get("optTp")),
        "OptimizationPlateMaxThickness": mm(o.get("tpMax", 45)), "OptimizationPlateMinThickness": mm(o.get("tpMin", 6)),
        "OptimizeLongDim": b01(o.get("optN")),
        "OptimizationPlateMaxLongDim": mm(o.get("pMaxN", 381)), "OptimizationPlateMinLongDim": mm(o.get("pMinN", 38.1)),
        "OptimizeTransvDim": b01(o.get("optB")),
        "OptimizationPlateMaxTransvDim": mm(o.get("pMaxB", 381)), "OptimizationPlateMinTransvDim": mm(o.get("pMinB", 38.1)),
        "OptimizationPlateDimStep": mm(o.get("dimInc", 25.4)),
        "OptimizeAnchorsDiameter": b01(o.get("optD")),
        "OptimizationMinAnchorEffectiveLength": mm(o.get("hefMin", 304.8)),
        "ConserveDuringOptimization": C("Keep anchor position", {"initial": ("1", True), "edge": ("0", False)}, o.get("keepPos", "initial"), "1"),
        "ColumnType": "1" if col["tapered"] else "0",
        "ColumnSection": "" if col["tapered"] else col["name"], "ColumnTaperedSection": col["name"] if col["tapered"] else "",
        "ColumnInitialDepth": mm(col["d0"] if col["tapered"] else 0), "ColumnFinalDepth": mm(col["d1"] if col["tapered"] else 0),
        "ColumnLength": mm(col["L"] * 1000 if col["tapered"] else 0),
        "ColumnMaterial": col["mat"],
        "ColumnLongitudinalOffset": mm(colS.get("ox") or 0), "ColumnTransversalOffset": mm(colS.get("oz") or 0),
        "BasePlateShape": "0", "BasePlateConnectionType": "0",
        "BasePlateLocation": C("Position on the support", {"center": ("4", True), "custom": ("0", False)}, pl.get("pos", "center"), "4"),
        "BasePlateLongitudinalDim": mm(pl["N"]), "BasePlateTransversalDim": mm(pl["B"]), "BasePlateThickness": mm(pl["tp"]),
        "BasePlateMaterial": pl["mat"],
        "BasePlateWeldType": "0", "BasePlateWeld": w.get("electrode", "E70XX"),
        "ConsiderExternalFlangeFaceWeldOnly": b01(w.get("outerOnly")), "BasePlateWeldD": str(int(round(float(w.get("D", 5))))),
        "OverrideConcreteAreaPlateAreaRatio": b01(pl.get("overA2")),
        "ConsiderShearLug": b01(lug.get("on")),
        "SupportWithPedestal": b01(ped.get("isPed")),
        "SupportLongitudinalDim": mm(ped["N2"]), "SupportTransversalDim": mm(ped["B2"]), "SupportThickness": mm(ped["h"]),
        "SupportMaterial": ped["mat"],
        "SupportConsiderGrout": b01(ped.get("groutOn")), "SupportGroutThickness": mm(ped.get("grout") or 0),
        "AnchorGeometry": C("Anchor position", {"longitudinal": ("1", True), "transversal": ("2", False)}, an.get("layout", "longitudinal"), "1"),
        "AnchorsNrRows": str(int(an["nr"])), "AnchorsNrPerRow": str(int(an["npr"])),
        "AnchorsLeV": mm(an["ex"]), "AnchorsLeH": mm(an["ey"]),
        "AnchorType": C("Anchor type", {"headed": ("0", True), "hooked": ("1", False)}, an.get("type", "headed"), "0"),
        "AnchorHeadType": C("Head type", {"hex": ("2", True), "square": ("0", False)}, an.get("head", "hex"), "2"),
        "AnchorLockNutProvided": b01(an.get("lockNut")),
        "Anchor": BE.anchor_label(an["d"]), "AnchorsLength": mm(an["hef"]), "AnchorMaterial": an["grade"],
        "CrackedConcrete": b01(an.get("cracked")), "AnchorBrittleSteel": b01(an.get("brittle")), "AnchorsWelded": b01(an.get("welded")),
        "AnchorReinforcementType": C("Type of reinforcement", {"primary": ("0", True), "supplementary": ("1", False)}, rf.get("type", "primary"), "0"),
        "AnchorTensionReinforcement": b01(rf.get("T")),
        "AnchorTensionReinforcementDiameter": str(rebar.index(rf.get("barT", "no. 10")) if rf.get("barT") in rebar else 7),
        "AnchorTensionReinforcementGrade": f"{g(float(rf.get('fyT', 275.79)) / KSI)} kip/in2",
        "AnchorTensionReinforcementBarsNumber": str(int(rf.get("nT", 0) or 0)),
        "AnchorShearReinforcement": b01(rf.get("V")),
        "AnchorShearReinforcementDiameter": str(rebar.index(rf.get("barV", "no. 10")) if rf.get("barV") in rebar else 7),
        "AnchorShearReinforcementGrade": f"{g(float(rf.get('fyV', 275.79)) / KSI)} kip/in2",
        "AnchorShearReinforcementBarsNumberMajorAxis": str(int(rf.get("nVx", 0) or 0)),
        "AnchorShearReinforcementBarsNumberMinorAxis": str(int(rf.get("nVy", 0) or 0)),
        "Optimize": "0",
    }
    if pl.get("pos") == "custom":
        P["BasePlateLongitudinalOffset"], P["BasePlateTransversalOffset"] = mm(pl.get("px") or 0), mm(pl.get("pz") or 0)
    if int(an["nr"]) > 1:
        P["AnchorsSpa"] = mm(an.get("sr") or 0)
    if pl.get("overA2"):
        P["ConcreteAreaPlateAreaRatio"] = g(pl.get("A2A1", 1))
    if ped.get("isPed"):
        P["SupportPedestalLongitudinalDim"], P["SupportPedestalTransversalDim"] = mm(ped["N2"]), mm(ped["B2"])
    if lug.get("on"):
        P.update(ConsiderShearLugWidthAsBasePlate="0", ShearLugWidth=mm(lug["bl"]), ShearLugDepth=mm(lug["H"]),
                 ShearLugThickness=mm(lug["tl"]), ShearLugWeldD=str(int(round(float(lug.get("D", 6))))))
        warn.append("Bản chắn cắt: vật liệu bản chắn cắt không có trong RAM (dùng mặc định của RAM).")
    if C.unverified:
        warn.append("Mã RAM chưa đối chứng (kiểm tra lại trong RAM): " + ", ".join(C.unverified))
    if an.get("type") == "hooked":
        warn.append(f"Neo móc: chiều dài móc eh = {g(an.get('eh', 0))} mm cần nhập lại trong RAM.")
    loads = st.get("loads", [])
    LD = dict(cols={"ColAxial": ("N", "kN"), "ColV2": ("V2", "kN"), "ColV3": ("V3", "kN"), "ColM22": ("M22", "kN*m"), "ColM33": ("M33", "kN*m")},
              est={"JointColAxial": "N", "JointColV2": "V2", "JointColV3": "V3"}, loads=loads)
    desc0, note0 = BE.short_text(st)
    desc = str(st.get("desc") or "").strip() or desc0                  # như trong tool (ô Description / Additional notes)
    note = str(st.get("notes") or "").replace("\r\n", "\n").replace("\n", "\r\n") or note0
    J = dict(JointDescription=desc, JointNotes=note, JointSection1=None, JointMaterial1=None,
             JointSection2=col["name"], JointMaterial2=col["mat"])
    return P, J, warn, LD | dict(members=[col], template=st.get("name") or "Pinned BP", button=None)


EXT_SPLICE = {"flush": ("0", True, "Flush"), "top": ("1", False, "Extended upwards"), "bottom": ("2", False, "Extended downwards"),
              "both": ("3", True, "Extended both ways")}


def splice_props(st: dict) -> tuple[dict, dict, list, dict]:
    """Nối dầm / apex → thuộc tính Bentley.AISC.MEPlateBeamSplice."""
    import splice_engine as SE
    st = SE.normalize(copy.deepcopy(st))
    warn = []
    pl, w, bolt, op = st["plate"], st["weld"], st["bolt"], st.get("opt", {})
    b1 = st["beam1"]
    b2 = dict(b1, jointEnd=st["beam2"].get("jointEnd", "I")) if st["beam2"].get("same", True) else st["beam2"]
    left, right = member_ram(dict(b1, topIsOuter=True)), member_ram(dict(b2, topIsOuter=True))
    apex = st.get("type") == "apex"
    slope = -abs(float(st.get("slope") or 0)) if apex else 0.0
    ext = pl.get("extension", "both")
    ev, ok, elabel = EXT_SPLICE.get(ext, EXT_SPLICE["both"])
    if not ok:
        warn.append(f"Mã RAM BEPlateType cho '{elabel}' chưa đối chứng — kiểm tra lại trong RAM.")
    tp = max(float(pl["tp1"]), float(pl.get("tp2") or pl["tp1"]))
    if abs(float(pl["tp1"]) - float(pl.get("tp2") or pl["tp1"])) > 1e-6:
        warn.append(f"Hai bản đầu dày khác nhau ({g(pl['tp1'])} / {g(pl['tp2'])} mm) — RAM chỉ có 1 bề dày, ghi {g(tp)} mm.")
    code = st.get("gen", {}).get("designCode", "AISC 2010 LRFD")
    bname, bw = bolt_name(bolt)
    if bw: warn.append(bw)
    D = lambda x: str(int(round(float(x))))
    el = lambda k: w[k].get("electrode", w.get("electrode", "E70XX"))
    stiff = [pl.get("stiffT", {}), pl.get("stiffB", {})]
    stiff_on = any(s.get("on") for s in stiff)

    def beam(prefix, m):
        return {f"{prefix}Type": "1" if m["tapered"] else "0",
                f"{prefix}Section": "" if m["tapered"] else m["name"], f"{prefix}SectionTapered": m["name"] if m["tapered"] else "",
                f"{prefix}InitialDepth": mm(m["d0"] if m["tapered"] else 0), f"{prefix}FinalDepth": mm(m["d1"] if m["tapered"] else 0),
                f"{prefix}Length": mm(m["L"] * 1000)}
    P = {
        "DesignCode": DESIGN_CODE.get(code, DESIGN_CODE["AISC 2010 LRFD"])[0],
        "HoleDef": b01(op.get("holeDef", True)), "SnugTightBolts": b01(bolt.get("snug")), "ShearedEdges": b01(op.get("sheared", True)),
        "IsApex": b01(apex), "SlopeAngle": g(slope),
        "IncludeStiffener": b01(stiff_on), "StiffenerThickness": mm(max([float(s.get("ts", 10)) for s in stiff if s.get("on")] or [10])),
        **beam("Beam", right), "BeamPlateMaterial": right["mat"],
        **beam("LeftBeam", left), "LeftBeamMaterial": left["mat"],
        "BEPlateType": ev, "Tp": mm(tp), "EndplateMaterial": pl.get("mat1", "Q345"),
        "FlushExtensionDistance": mm(pl.get("flushExt", 25.4)),
        "BeamTopFlangeWeldType": "1" if w["flT"].get("type") == "cjp" else "0", "BeamTopFlangeWeld": el("flT"), "BeamTopFlangeWeldD": D(w["flT"].get("D", 5)),
        "BeamBottomFlangeWeldType": "1" if w["flB"].get("type") == "cjp" else "0", "BeamBottomFlangeWeld": el("flB"),
        "BeamBottomFlangeWeldD": D(w["flB"].get("D", 5)),
        "BeamWebWeldType": "0", "WebShearWeld": el("web"), "WebShearWeldD": D(w["web"].get("D", 4)),
        "Bolt": bname, "BoltColumns": "2", "SpaH": mm(pl["g"]), "Lev": mm(pl["Lev"]), "Leh": mm(pl["Leh"]),
        "OuterTopBoltRow": "1", "OuterTopBoltBeamFlangeDistance": mm(pl["pfoT"]),
        "InnerTopBoltRowFlushed": "1", "InnerBottomBoltRowFlushed": "1",
        "InnerTopBoltRow": str(int(pl["nT"])), "InnerTopBoltBeamFlangeDistance": mm(pl["pfiT"]), "InnerTopBoltSpaV": mm(pl["pbT"]),
        "InnerBottomBoltRow": str(int(pl["nB"])), "InnerBottomBoltBeamFlangeDistance": mm(pl["pfiB"]), "InnerBottomBoltSpaV": mm(pl["pbB"]),
        "OuterBottomBoltRow": "1", "OuterBottomBeamFlangeDistance": mm(pl["pfoB"]),
        "Optimize": "0",
    }
    if (left["name"], left["d0"]) != (right["name"], right["d0"]):
        warn.append("Hai dầm khác tiết diện — kiểm tra lại bên trái / phải trong RAM.")
    if stiff_on and len({float(s.get("ts", 10)) for s in stiff if s.get("on")}) > 1:
        warn.append("Sườn cánh trên / dưới dày khác nhau — RAM chỉ có 1 bề dày sườn.")
    LD = dict(cols={"Axial": ("N", "kN"), "V2": ("V", "kN"), "M33": ("M", "kN*m")},
              est={"JointAxial": "N", "JointV2": "V", "JointM33": "M"}, loads=st.get("loads", []))
    J = dict(JointDescription=st.get("desc") or st.get("name"), JointSection1=left["name"], JointMaterial1=left["mat"],
             JointSection2=right["name"], JointMaterial2=right["mat"], JointSlopeAngle1=slope if apex else None,
             JointSetBack1=0.01, JointMemberLength1=left["L"], JointMemberLength2=right["L"])
    btn = f"Basic MEP {elabel} Beam Splice" + (" Apex" if apex else "")
    return P, J, warn, LD | dict(members=[left, right], template=st.get("name") or ("APEX" if apex else "BS"), button=btn)


def knee_rows(st: dict, i: int):
    P, beam, col, warn = knee_props(st)
    al = ALIGN.get(st["plate"].get("alignment", "vertical"), ALIGN["vertical"])[1]
    J = dict(JointDispIndexInGroup=i, JointSection1=beam["name"], JointMaterial1=beam["mat"], JointSection2=col["name"], JointMaterial2=col["mat"],
             JointSlopeAngle1=float(st["beam"].get("slope", 0)), JointSetBack1=0.01,
             JointMemberLength1=beam["L"], JointMemberLength2=col["L"], JointHasCLTRestraint=1,
             JointMember1DepthInitial=beam["d0"] / 1000, JointMember1DepthFinal=beam["d1"] / 1000, JointMember1SectionType=1,
             JointMember2DepthInitial=col["d0"] / 1000, JointMember2DepthFinal=col["d1"] / 1000, JointMember2SectionType=1,
             JointDescription=st.get("name"),
             JointNotes=f"{st.get('name', '')}\r\n{st['plate'].get('nE', 1)}+{st['plate'].get('nI', 1)} rows {P['Bolt']}_PL{g(st['plate']['tp'])}")
    LD = dict(cols={"Axial": ("Nb", "kN"), "V2": ("Vb", "kN"), "M33": ("Mb", "kN*m"),
                    "ColAxial": ("Nc", "kN"), "ColV2": ("Vc", "kN"), "ColM33": ("Mc", "kN*m")},
              est={"JointV2": "Vb", "JointM33": "Mb", "JointAxial": "Nb"}, loads=st["loads"], members=[beam, col],
              template=st.get("name") or f"KNEE {i}",
              button=f"Basic MEP Knee {al} {EXT_LABEL.get(st['plate'].get('extension', 'external'), 'Extended upwards')}")
    return P, J, warn, LD


def _clean(name: str) -> str:
    return str(name).replace(",", ";").replace("[", "(").replace("]", ")").strip() or "LC"


def _unit_of(val: str, default: str) -> str:
    import re
    m = re.match(r"\[\s*-?[\d.eE+-]+\s+([^,\]]+)", val or "")
    return m.group(1).strip() if m else default


def load_groups(states: list[dict]) -> list[list[int]]:
    """Nhóm liên kết có cùng bảng tải (cùng Description, cùng thứ tự). RAM chỉ có 1 danh sách điều kiện tải cho cả file,
    nên mỗi nhóm = 1 file thì bảng tải của từng nút trong RAM giống hệt bảng trong tool (tên + số dòng)."""
    groups: dict[tuple, list[int]] = {}
    for i, st in enumerate(states):
        groups.setdefault(tuple(_clean(l.get("name")) for l in st.get("loads", [])), []).append(i)
    return list(groups.values())


def export_rcnx(states: list[dict], out_path: str, make_sections: bool = True, sec_dir: str = SEC_DIR,
                kinds: list[str] | None = None, split: bool = True) -> dict:
    """Ghi file .rcnx cho các liên kết trong `states` (kinds[i] = knee / base / splice; mặc định knee).
    split: các nút có bảng tải khác nhau ghi ra file riêng <tên>_1.rcnx, <tên>_2.rcnx… (mỗi file 1 bảng tải chung).
    Trả về {path, paths, files: [(path, [tên nút])], n, warnings, sections}."""
    kinds = list(kinds or ["knee"] * len(states))
    groups = load_groups(states) if split else [list(range(len(states)))]
    if len(groups) <= 1:
        res = _export_one(states, out_path, make_sections, sec_dir, kinds)
        return dict(res, paths=[out_path], files=[(out_path, [str(st.get("name", "")) for st in states])])
    stem, ext = os.path.splitext(out_path)
    out = dict(path=None, paths=[], files=[], n=0, warnings=[], sections=None)
    for k, idx in enumerate(groups, 1):
        p = f"{stem}_{k}{ext or '.rcnx'}"
        r = _export_one([states[i] for i in idx], p, make_sections, sec_dir, [kinds[i] for i in idx])
        out["paths"].append(p); out["files"].append((p, [str(states[i].get("name", "")) for i in idx]))
        out["path"] = out["path"] or p
        out["n"] += r["n"]; out["warnings"] += r["warnings"]
        if r.get("sections"):
            sec = out["sections"] or dict(added=[], existed=[], conflict=[], path=r["sections"]["path"])
            for key in ("added", "existed", "conflict"):
                sec[key] += [x for x in r["sections"][key] if x not in sec[key]]
            out["sections"] = sec
    return out


def _export_one(states: list[dict], out_path: str, make_sections: bool, sec_dir: str, kinds: list[str]) -> dict:
    """Ghi 1 file .rcnx."""
    if not os.path.exists(PROTO):
        raise FileNotFoundError("Thiếu file khuôn ram_proto.rcnx (chạy tools/make_ram_proto.py).")
    if not states:
        raise ValueError("Chưa có liên kết nào để xuất.")
    warnings, members = [], []
    if os.path.exists(out_path):
        os.remove(out_path)
    shutil.copy2(PROTO, out_path)
    db = sqlite3.connect(out_path)
    try:
        jcols = [r[1] for r in db.execute("pragma table_info(Joints)")]
        ecols = [r[1] for r in db.execute("pragma table_info(Joints_Estados)")]
        proto = {}
        for ref0, btn0, jid in db.execute("select CnxRef, CnxAssignmentButton, CnxID from Cnx").fetchall():
            cls = db.execute(f'select PropertyValue from "{ref0}" where PropertyName=\'ClassName\'').fetchone()[0]
            jr = db.execute("select * from Joints where JointID=?", (jid,)).fetchone()
            proto[cls] = dict(props=db.execute(f'select PropertyName, PropertyType, PropertyValue from "{ref0}"').fetchall(),
                              loads=db.execute(f'select PropertyName, PropertyType, PropertyValue from "{ref0}_Loads"').fetchall(),
                              joint=dict(zip(jcols, jr)) if jr else {}, button=btn0)
        for ref0, in db.execute("select CnxRef from Cnx").fetchall():
            db.execute(f'drop table "{ref0}"'); db.execute(f'drop table "{ref0}_Loads"')
        for t in ("Cnx", "Joints", "Joints_Estados", "Estados"):
            db.execute(f"delete from {t}")
        db.execute("delete from ConnectionObjects where PropertyName != 'ConnectionVersion'")

        # RAM chỉ có MỘT danh sách điều kiện tải cho cả file, mọi nút đều hiện đủ danh sách đó. Để mỗi nút chỉ thấy tổ hợp của
        # nó (không có dòng của nút khác chen phía trên): tải thứ k của mọi nút dùng chung điều kiện k. Tên điều kiện = tên chung
        # nếu các nút trùng tên ở vị trí đó (vd. Mmax, Pmax… như file RAM), khác nhau thì ghép các tên.
        n_lc = max([len(st.get("loads", [])) for st in states] + [1])
        all_desc = []
        for k in range(n_lc):
            names = []
            for st in states:
                ls = st.get("loads", [])
                if k < len(ls) and _clean(ls[k].get("name")) not in names:
                    names.append(_clean(ls[k].get("name")))
            nm = " / ".join(n[:24] for n in names) if len(names) > 1 else (names[0] if names else f"LC{k + 1}")
            all_desc.append(nm if len(nm) <= 90 else nm[:89] + "…")
        codes = []
        for i, (st, kind) in enumerate(zip(states, kinds), 1):
            cls = RAM_CLASS.get(kind)
            if cls not in proto:
                raise ValueError(f"Khuôn RAM thiếu loại {cls or kind}.")
            pr = proto[cls]
            if kind == "knee":
                P, J, warn, LD = knee_rows(st, i)
            elif kind == "base":
                P, J, warn, LD = base_props(st)
            else:
                P, J, warn, LD = splice_props(st)
            warnings += [f"{st.get('name', i)}: {w}" for w in warn]
            members += LD["members"]
            code_txt = DESIGN_CODE.get(st.get("gen", {}).get("designCode", "AISC 2010 LRFD"), (None, None))[1] or \
                {"4": "AISC-16 ASD"}.get(P.get("DesignCode"), "AISC-10 LRFD")
            if code_txt not in codes: codes.append(code_txt)
            ref = "{" + str(uuid.uuid4()).upper() + "}"
            db.execute(f'create table "{ref}" (PropertyName TEXT, PropertyType INTEGER, PropertyValue TEXT)')
            db.execute(f'create table "{ref}_Loads" (PropertyName TEXT, PropertyType INTEGER, PropertyValue TEXT)')
            for name, typ, val in pr["props"]:
                db.execute(f'insert into "{ref}" values (?,?,?)', (name, typ, P.get(name, val)))
            loads = LD["loads"]
            pad = loads + [{}] * (n_lc - len(loads))             # đủ n_lc điều kiện, phần thiếu = 0
            rows = []
            for name, typ, val in pr["loads"]:
                if name == "Count":
                    v = str(n_lc)
                elif name == "Description":
                    v = "[" + ",".join(all_desc) + "]"
                elif name == "LoadType":
                    v = "[" + ",".join("0" for _ in pad) + "]"
                elif name in LD["cols"]:
                    key, unit = LD["cols"][name]
                    v = "[" + ",".join(f"{g(l.get(key) or 0)} {unit}" for l in pad) + "]"
                else:
                    unit = _unit_of(val, "kN")
                    v = "[" + ",".join(f"0 {unit}" for _ in pad) + "]"
                rows.append((name, typ, v))
            db.executemany(f'insert into "{ref}_Loads" values (?,?,?)', rows)

            db.execute("insert into Cnx (CnxTemplate, CnxRef, CnxAssignmentButton, CnxJoint, CnxDesignCode, CnxID) values (?,?,?,?,?,?)",
                       (_clean(LD["template"]), ref, LD.get("button") or pr["button"], i, code_txt, i))
            jr = {k: None for k in jcols}
            jr.update(JointFamily=pr["joint"].get("JointFamily", JOINT_FAMILY[kind]))
            jr.update({k: v for k, v in J.items() if k in jr})
            if not jr.get("JointNotes"):
                jr["JointNotes"] = str(st.get("name", ""))
            jr["JointID"] = i
            db.execute(f"insert into Joints ({','.join(jcols)}) values ({','.join('?' for _ in jcols)})", [jr[c] for c in jcols])
            for k, l in enumerate(loads):
                vals = {c: (float(l.get(key) or 0) or None) for c, key in LD["est"].items() if c in ecols}
                if not any(vals.values()):
                    continue                                   # như RAM: bỏ tổ hợp toàn 0
                cols = ["Joints", "Estados"] + list(vals)
                db.execute(f"insert into Joints_Estados ({','.join(cols)}) values ({','.join('?' for _ in cols)})", [i, k] + list(vals.values()))
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
            uniq = {m["name"]: m for m in members if not m.get("catalog")}
            sec = ensure_sections(list(uniq.values()), sec_dir)
            if sec["conflict"]:
                warnings.append("Tên tiết diện đã có trong database nhưng kích thước khác: " + ", ".join(sec["conflict"]))
        except Exception as e:  # noqa: BLE001
            warnings.append(f"Không ghi được database tiết diện: {e}")
    return dict(path=out_path, n=len(states), warnings=warnings, sections=sec)
