"""
scanner.py — Quét SAP2000 tìm knee (đỉnh cột ↔ đầu kèo) và lấy nội lực cả cột lẫn kèo.
=====================================================================================
Dùng lại SAP2000Connector + logic nút đầu/cuối, 9 cực trị của tool "Lấy nội lực".

Quy ước đổi dấu (SAP → tool knee):
  • SAP: M3 > 0 gây kéo mặt −2 của trục địa phương.
  • Tool: M < 0 → cánh NGOÀI chịu kéo.
  → Nếu cánh ngoài nằm ở mặt +2: M_tool = M3; ngược lại M_tool = −M3.
  • Cánh ngoài kèo = phía trên; cánh ngoài cột = phía xa nhịp (ngược hướng kèo).
  • "Cánh trên" trong tên tiết diện = mặt +2 ⇒ topIsOuter = (mặt +2 là mặt ngoài).
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass, field
from typing import Callable, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_LAY = os.path.join(os.path.dirname(_HERE), "Lấy nội lực")
if _LAY not in sys.path:
    sys.path.insert(0, _LAY)

from core_engine import (  # noqa: E402
    EXTREME_NAMES, NODE_KEY_END, NODE_KEY_START, filter_design_forces, find_extremes, station_indices,
)
from sap2000_connector import SAP2000Connector, _as_list, _safe_str  # noqa: E402

COL_MAX_TILT = 15.0      # frame lệch phương đứng ≤ 15° → cột
RAF_MAX_SLOPE = 45.0     # frame nghiêng ≤ 45° so với phương ngang → kèo
TOL = 1e-6


@dataclass
class FrameGeo:
    name: str
    p1: str
    p2: str
    x1: tuple
    x2: tuple
    kind: str            # 'col' | 'raf' | 'other'
    length: float
    local2: Optional[tuple] = None


@dataclass
class KneeFound:
    kid: str
    joint: str
    xyz: tuple
    col: str
    col_end: str
    col_sec: str
    col_L: float
    col_top_outer: bool
    raf: str
    raf_end: str
    raf_sec: str
    raf_L: float
    raf_top_outer: bool
    slope: float
    loads: list = field(default_factory=list)
    warn: list = field(default_factory=list)
    group: str = ""
    col_dims: Optional[dict] = None     # kích thước qua API SAP (khi tên không theo quy cách)
    raf_dims: Optional[dict] = None

    def group_key(self):
        """Knee giống nhau về hình học tại nút (kể cả knee đối xứng hai đầu khung) → cùng nhóm."""
        from engine import member_at_joint

        def dims(sec, L, end, top_out, api=None):
            try:
                m = member_at_joint(dict(sec=sec, L=L, jointEnd=end, topIsOuter=top_out, dims=api), "")
                return tuple(round(m[k], 1) for k in ("d", "tw", "bfE", "tfE", "bfI", "tfI", "beta")) + (m["taper_sign"],)
            except ValueError:
                return (sec, end, top_out)
        return (dims(self.col_sec, self.col_L, self.col_end, self.col_top_outer, self.col_dims),
                dims(self.raf_sec, self.raf_L, self.raf_end, self.raf_top_outer, self.raf_dims),
                round(self.slope * 2) / 2)


def _dot(a, b): return sum(x * y for x, y in zip(a, b))
def _sub(a, b): return tuple(x - y for x, y in zip(a, b))
def _norm(a):
    L = math.sqrt(_dot(a, a)) or 1.0
    return tuple(x / L for x in a)


def _local2(conn: SAP2000Connector, frame: str, axis: tuple) -> Optional[tuple]:
    """Trục địa phương 2 (hệ tổng thể) qua FrameObj.GetTransformationMatrix; lỗi → mặc định SAP."""
    sm = conn._sap_model
    try:
        ret = sm.FrameObj.GetTransformationMatrix(frame, [0.0] * 9, True)
        arr = None
        for item in (ret if isinstance(ret, (list, tuple)) else [ret]):
            lst = _as_list(item)
            if len(lst) == 9:
                arr = [float(v) for v in lst]
                break
        if arr:
            v = (arr[1], arr[4], arr[7])
            if _dot(v, v) > 0.5:
                return _norm(v)
    except Exception:
        pass
    # Mặc định SAP (góc xoay 0): thanh đứng → local 2 = +X; thanh khác → local 2 nằm trong mặt đứng, hướng lên
    ax = _norm(axis)
    if abs(ax[2]) > 0.999:
        return (1.0, 0.0, 0.0)
    z = (0.0, 0.0, 1.0)
    v = _sub(z, tuple(ax[i] * ax[2] for i in range(3)))
    return _norm(v)


def _all_frames(conn: SAP2000Connector) -> list[str]:
    try:
        ret = conn._sap_model.FrameObj.GetNameList(0, [])
        return conn._extract_name_list(ret)
    except Exception:
        return []


def classify(conn: SAP2000Connector, frames: list[str]) -> dict[str, FrameGeo]:
    out = {}
    for f in frames:
        try:
            ret = conn._sap_model.FrameObj.GetPoints(f, "", "")
            p1, p2 = _safe_str(ret[0]), _safe_str(ret[1])
        except Exception:
            continue
        x1, x2 = conn._point_xyz(p1), conn._point_xyz(p2)
        d = _sub(x2, x1)
        L = math.sqrt(_dot(d, d))
        if L < TOL:
            continue
        tilt = math.degrees(math.acos(min(abs(d[2]) / L, 1.0)))           # lệch phương đứng
        slope = 90.0 - tilt                                                 # nghiêng so với ngang
        kind = "col" if tilt <= COL_MAX_TILT else ("raf" if slope <= RAF_MAX_SLOPE else "other")
        out[f] = FrameGeo(f, p1, p2, x1, x2, kind, L)
    return out


def find_knees(conn: SAP2000Connector, geo: dict[str, FrameGeo]) -> list[KneeFound]:
    at: dict[str, list] = {}
    for g in geo.values():
        at.setdefault(g.p1, []).append((g, "I"))
        at.setdefault(g.p2, []).append((g, "J"))
    knees = []
    for pt, items in at.items():
        cols_top = []
        cols_bot = []
        rafs = []
        for g, end in items:
            here = g.x1 if end == "I" else g.x2
            other = g.x2 if end == "I" else g.x1
            if g.kind == "col":
                (cols_top if here[2] > other[2] else cols_bot).append((g, end))
            elif g.kind == "raf":
                rafs.append((g, end))
        if len(cols_top) != 1 or cols_bot or len(rafs) != 1:
            continue                     # không phải knee (cột liên tục, nút giữa, 2 kèo…)
        (cg, cend), (rg, rend) = cols_top[0], rafs[0]
        P = cg.x1 if cend == "I" else cg.x2
        far = rg.x2 if rend == "I" else rg.x1
        v = _sub(far, P)
        horiz = math.hypot(v[0], v[1])
        slope = math.degrees(math.atan2(v[2], horiz))
        u = _norm((v[0], v[1], 0.0)) if horiz > TOL else (1.0, 0.0, 0.0)
        warn = []
        # trục 2 và mặt ngoài
        l2c = _local2(conn, cg.name, _sub(cg.x2, cg.x1))
        l2r = _local2(conn, rg.name, _sub(rg.x2, rg.x1))
        outer_col = tuple(-x for x in u)
        c_dot = _dot(l2c, outer_col)
        r_dot = _dot(l2r, (0.0, 0.0, 1.0))
        if abs(c_dot) < 0.5:
            warn.append("Trục 2 của cột không nằm trong mặt phẳng khung (cột xoay trục yếu?) — kiểm tra lại.")
        if abs(r_dot) < 0.5:
            warn.append("Trục 2 của kèo không nằm trong mặt phẳng khung — kiểm tra lại.")
        knees.append(KneeFound(
            kid="", joint=pt, xyz=P,
            col=cg.name, col_end=cend, col_sec="", col_L=cg.length, col_top_outer=c_dot > 0,
            raf=rg.name, raf_end=rend, raf_sec="", raf_L=rg.length, raf_top_outer=r_dot > 0,
            slope=slope, warn=warn,
        ))
    knees.sort(key=lambda k: (k.xyz[1], k.xyz[0], k.xyz[2]))
    for i, k in enumerate(knees, 1):
        k.kid = f"K{i}"
    return knees


def _rows_at(conn, frame, end, allowed):
    info = conn.get_frame_info(frame)
    forces = filter_design_forces(conn.get_frame_forces(frame), allowed)
    idx, sta = station_indices(forces, info, NODE_KEY_START if end == "I" else NODE_KEY_END)
    return info, forces, idx


def api_dims(conn, sec, info, end, knee) -> Optional[dict]:
    """Tên không theo quy cách → đọc kích thước I tại mặt gối đầu nút qua API SAP (mm)."""
    from knee_section import SectionError, parse_section
    try:
        parse_section(sec)
        return None
    except SectionError:
        pass
    try:
        Lc = info.length - info.length1 - info.length2
        if Lc <= 0: Lc = info.length
        x = 0.0 if end == "I" else Lc
        a = conn.get_section_dimensions(sec, x, Lc)
        dx = min(0.05 * Lc, 0.5)
        b = conn.get_section_dimensions(sec, x + dx if end == "I" else x - dx, Lc)
    except Exception as e:  # noqa: BLE001
        knee.warn.append(f"Không đọc được kích thước '{sec}' qua API: {e}")
        return None
    if a.t3 <= 0 or a.tw <= 0:
        knee.warn.append(f"Tiết diện '{sec}' ({a.type_name}) không phải I — không tính được knee.")
        return None
    tfb = a.tfb or a.tf; t2b = a.t2b or a.t2
    beta = math.degrees(math.atan(abs(a.t3 - b.t3) / dx)) if dx > 0 else 0.0
    knee.warn.append(f"'{sec}': kích thước lấy qua API SAP ({a.type_name}).")
    return dict(d=a.t3 * 1000, tw=a.tw * 1000, bf_top=a.t2 * 1000, tf_top=a.tf * 1000, bf_bot=t2b * 1000,
                tf_bot=tfb * 1000, beta=beta, taper_sign=1 if b.t3 < a.t3 - 1e-9 else (-1 if b.t3 > a.t3 + 1e-9 else 0))


def fill_forces(conn: SAP2000Connector, knee: KneeFound, allowed_for: Callable[[str], Optional[set]]):
    """9 cực trị tại đầu nút của cột và của kèo (như tool Lấy nội lực); mỗi tổ hợp lấy đồng thời
    nội lực của cả hai thanh (cùng thứ tự bước nếu combo có nhiều bước)."""
    ci, cf, cidx = _rows_at(conn, knee.col, knee.col_end, allowed_for(knee.col))
    ri, rf, ridx = _rows_at(conn, knee.raf, knee.raf_end, allowed_for(knee.raf))
    knee.col_sec = ci.section_name or ci.prop_name
    knee.raf_sec = ri.section_name or ri.prop_name
    knee.col_L, knee.raf_L = ci.length, ri.length
    knee.col_dims = api_dims(conn, knee.col_sec, ci, knee.col_end, knee)
    knee.raf_dims = api_dims(conn, knee.raf_sec, ri, knee.raf_end, knee)

    def occ(forces, idx):
        m: dict[str, list] = {}
        for j in idx:
            m.setdefault(forces[j].load_case, []).append(j)
        return m

    cocc, rocc = occ(cf, cidx), occ(rf, ridx)
    picks: dict[tuple, list[str]] = {}
    order: list[tuple] = []
    for who, forces, idx, oc in (("Kèo", rf, ridx, rocc), ("Cột", cf, cidx, cocc)):
        ext = find_extremes(forces, idx)
        for en in EXTREME_NAMES:
            j = ext.get(en, -1)
            if j < 0:
                continue
            lc = forces[j].load_case
            k = oc[lc].index(j)
            key = (lc, k)
            if key not in picks:
                picks[key] = []; order.append(key)
            picks[key].append(f"{who} {en}")

    sgn_c = 1.0 if knee.col_top_outer else -1.0
    sgn_r = 1.0 if knee.raf_top_outer else -1.0
    rows = []
    for lc, k in order:
        rj = rocc.get(lc, []); cj = cocc.get(lc, [])
        if not rj or not cj:
            knee.warn.append(f"Tổ hợp {lc} không có ở cả hai thanh — bỏ qua.")
            continue
        fr = rf[rj[min(k, len(rj) - 1)]]
        fc = cf[cj[min(k, len(cj) - 1)]]
        step = f" #{k + 1}" if max(len(rj), len(cj)) > 1 else ""
        rows.append(dict(
            name=f"{lc}{step}", src=", ".join(picks[(lc, k)]),
            Vb=round(fr.V2, 2), Nb=round(fr.P, 2), Mb=round(sgn_r * fr.M3, 2),
            Vc=round(fc.V2, 2), Nc=round(fc.P, 2), Mc=round(sgn_c * fc.M3, 2),
        ))
    knee.loads = rows
    return knee


def group_knees(knees: list[KneeFound]) -> dict[str, list[KneeFound]]:
    groups: dict[tuple, list[KneeFound]] = {}
    for k in knees:
        groups.setdefault(k.group_key(), []).append(k)
    out = {}
    for i, (key, lst) in enumerate(groups.items(), 1):
        gid = f"G{i}"
        for k in lst:
            k.group = gid
        out[gid] = lst
    return out


def frames_at_points(conn: SAP2000Connector, points: list[str]) -> list[str]:
    """Các frame nối vào nút (PointObj.GetConnectivity)."""
    out = []
    for p in points:
        try:
            ret = conn._sap_model.PointObj.GetConnectivity(p, 0, [], [], [])
            n = int(ret[0]); types = _as_list(ret[1]); names = _as_list(ret[2])
            for i in range(min(n, len(types), len(names))):
                if int(types[i]) == 2 and str(names[i]) not in out:
                    out.append(str(names[i]))
        except Exception:
            continue
    return out


def pick(conn: SAP2000Connector, allowed_for, progress=None) -> list[KneeFound]:
    """Knee từ lựa chọn hiện tại trong SAP: nút đang chọn (lấy mọi thanh nối vào) + thanh đang chọn."""
    frames = list(conn.get_selected_frames())
    for f in frames_at_points(conn, conn.get_selected_points()):
        if f not in frames:
            frames.append(f)
    return _scan_frames(conn, frames, allowed_for, progress)


def scan(conn: SAP2000Connector, whole_model: bool, allowed_for: Callable[[str], Optional[set]],
         progress: Optional[Callable[[str], None]] = None) -> list[KneeFound]:
    frames = _all_frames(conn) if whole_model else conn.get_selected_frames()
    return _scan_frames(conn, frames, allowed_for, progress)


def _scan_frames(conn, frames, allowed_for, progress=None) -> list[KneeFound]:
    if not frames:
        return []
    if progress: progress(f"Phân loại {len(frames)} thanh…")
    geo = classify(conn, frames)
    knees = find_knees(conn, geo)
    for i, k in enumerate(knees, 1):
        if progress: progress(f"Lấy nội lực knee {i}/{len(knees)} (nút {k.joint})…")
        fill_forces(conn, k, allowed_for)
    group_knees(knees)
    return knees


def knee_to_state(base: dict, knees: list[KneeFound], gid: str) -> dict:
    """Tạo bộ thông số thiết kế cho 1 nhóm knee (bao nội lực mọi knee trong nhóm)."""
    import copy
    k0 = knees[0]
    st = copy.deepcopy(base)
    st["name"] = f"{gid}: " + ", ".join(k.kid for k in knees)
    st["beam"].update(sec=k0.raf_sec, L=k0.raf_L, jointEnd=k0.raf_end, slope=round(k0.slope, 3), topIsOuter=k0.raf_top_outer, dims=k0.raf_dims)
    st["col"].update(sec=k0.col_sec, L=k0.col_L, jointEnd=k0.col_end, topIsOuter=k0.col_top_outer, dims=k0.col_dims)
    st["sap_lock"] = True
    loads = []
    for k in knees:
        for r in k.loads:
            loads.append(dict(r, name=(f"{k.kid}·" if len(knees) > 1 else "") + r["name"]))
    st["loads"] = loads
    st["_source"] = dict(group=gid, knees=[dict(kid=k.kid, joint=k.joint, col=k.col, col_end=k.col_end, raf=k.raf,
                                                  raf_end=k.raf_end, slope=round(k.slope, 3)) for k in knees])
    return st
