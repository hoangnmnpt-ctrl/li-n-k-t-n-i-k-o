"""
core_engine.py
==============
Logic xử lý nội lực kết cấu: tìm cực trị, nội suy, tóm tắt.

Tương đương VBA:
  - Nút Đầu/Cuối: Excel "1. LẤY NỘI LỰC MAX_ANH HƯNG GỬI" (module InternalForce)
  - Tóm tắt cực trị: Module2 (giữ logic tool, thêm gộp cả 2 đầu)
  - Phản lực: Excel "1. LẤY NỘI LỰC MAX_ANH HƯNG GỬI" (module Reaction)
  - Nhiều vị trí: Module4
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Optional

from sap2000_connector import (
    FrameForceRow,
    FrameInfo,
    JointReactRow,
    SAP2000Connector,
    is_modal_load,
)
from section_parser import SectionProps, parse_section_name


# Vị trí xuất (radio "Vị trí nút")
NODE_START = "1"
NODE_END = "2"
NODE_BOTH = "3"
NODE_ENVELOPE = "4"   # Excel: Envelope — mọi station trong nhịp thông thủy

NODE_KEY_START = "Đầu"
NODE_KEY_END = "Cuối"
NODE_KEY_ENVELOPE = "Toàn thanh"

# Excel: dung sai so khớp station (m)
STATION_TOL = 0.001

# Thứ tự in 9 cực trị — Excel PrintExtremeRows: Array(0, 1, 3, 2, 5, 4, 6, 7, 8)
EXTREME_NAMES = [
    "Max P", "Min P",
    "Max M3", "Min M3",
    "Max M2", "Min M2",
    "Max T (Abs)", "Max V2 (Abs)", "Max V3 (Abs)",
]


def filter_design_forces(
    forces: list[FrameForceRow],
    allowed_loads: Optional[set[str]] = None,
) -> list[FrameForceRow]:
    """Bỏ Modal; nếu có danh sách cho phép thì chỉ giữ các nguồn đó."""
    out: list[FrameForceRow] = []
    for f in forces:
        if is_modal_load(f.load_case):
            continue
        if allowed_loads is not None and f.load_case not in allowed_loads:
            continue
        out.append(f)
    return out


# ═══════════════════════════════════════════════════════════════
# KIỂU DỮ LIỆU KẾT QUẢ
# ═══════════════════════════════════════════════════════════════

@dataclass
class ResultRow:
    """
    1 dòng kết quả xuất ra bảng (Module1 – Nút Đầu/Cuối).

    Logic theo Excel InternalForce (anh Hưng): 9 cực trị, có T và kích thước
    tiết diện tại station (m).
    """
    frame_name: str = ""
    section_name: str = ""
    length: float = 0.0
    node_label: str = ""       # "Nút Đầu (0.44m)" / "Nút Cuối (L = 6.82m)" / "Toàn thanh"
    extreme_type: str = ""     # "Max P", "Min P", ..., "Max T (Abs)"
    load_case: str = ""
    P: float = 0.0
    V2: float = 0.0
    V3: float = 0.0
    M2: float = 0.0
    M3: float = 0.0
    obj_station: float = 0.0
    T: float = 0.0
    node_key: str = ""         # "Đầu" / "Cuối" / "Toàn thanh"
    sec_type: str = ""
    t3: float = 0.0
    t2: float = 0.0
    tf: float = 0.0
    tw: float = 0.0
    t2b: float = 0.0
    tfb: float = 0.0
    dis: float = 0.0
    fillet: float = 0.0
    mirror: str = "N/A"

    @property
    def source_text(self) -> str:
        """Nơi lấy dòng này — dùng cho cột 'Lấy từ' của bảng tóm tắt."""
        if self.node_key in (NODE_KEY_START, NODE_KEY_END):
            return f"{self.frame_name} – {self.node_key}"
        return f"{self.frame_name} @ {self.obj_station:.2f}m"


@dataclass
class ResultRowMulti:
    """1 dòng kết quả xuất ra bảng (Module4 – Nhiều vị trí)."""
    frame_name: str = ""
    section_name: str = ""
    htb: float = 0.0
    tw: float = 0.0
    bf: float = 0.0
    tf: float = 0.0
    length: float = 0.0
    location_label: str = ""   # "Cach nut dau 2.00m"
    extreme_type: str = ""     # "Max P", "Min V3", ...
    load_case: str = ""
    P: float = 0.0
    V2: float = 0.0
    V3: float = 0.0
    M2: float = 0.0
    M3: float = 0.0


@dataclass
class SummaryRow:
    """1 dòng bảng tóm tắt cực trị toàn cục (Module2)."""
    num: int = 0
    condition: str = ""
    V2: float = 0.0
    V3: float = 0.0
    axial: float = 0.0
    M33: float = 0.0
    M22: float = 0.0
    bar: str = ""
    source: str = ""           # "1406 – Cuối" / "1406 @ 3.37m"
    load_case: str = ""


# ═══════════════════════════════════════════════════════════════
# MODULE 1: CỰC TRỊ TẠI NÚT ĐẦU / CUỐI (theo Excel InternalForce)
# ═══════════════════════════════════════════════════════════════

def station_indices(
    forces: list[FrameForceRow],
    info: FrameInfo,
    node_key: str,
) -> tuple[list[int], float]:
    """
    Chọn các dòng nội lực tại vị trí cần xét.

    Excel: mặt gối đầu I = Length1, đầu J = L − Length2 (end offset),
    dung sai 0.001 m; Envelope = mọi station trong [Length1, L − Length2].
    Nếu SAP không có station khớp (vd AutoOffset) → lấy station nhỏ/lớn nhất
    thực tế như tool cũ.

    Returns (danh sách index, station đại diện).
    """
    if not forces:
        return [], 0.0
    sta_i = info.length1
    sta_j = info.length - info.length2

    if node_key == NODE_KEY_ENVELOPE:
        idx = [
            j for j, f in enumerate(forces)
            if sta_i - STATION_TOL <= f.obj_station <= sta_j + STATION_TOL
        ]
        return (idx or list(range(len(forces)))), sta_i

    target = sta_i if node_key == NODE_KEY_START else sta_j
    idx = [j for j, f in enumerate(forces) if abs(f.obj_station - target) <= STATION_TOL]
    if not idx:
        stations = [f.obj_station for f in forces]
        target = min(stations) if node_key == NODE_KEY_START else max(stations)
        idx = [j for j, f in enumerate(forces) if abs(f.obj_station - target) <= STATION_TOL]
    return idx, target


def find_extremes(
    forces: list[FrameForceRow],
    indices: list[int],
) -> dict[str, int]:
    """
    Tìm index của 9 cực trị trong các dòng cho trước (Excel InternalForce).

    So sánh "lớn hơn hẳn" → khi bằng nhau giữ dòng gặp trước, giống Excel.
    Returns {"Max P": idx, ..., "Max V3 (Abs)": idx}; idx = -1 nếu không có.
    """
    best = {name: -1 for name in EXTREME_NAMES}
    max_p = -1e30; min_p = 1e30
    max_m3 = -1e30; min_m3 = 1e30
    max_m2 = -1e30; min_m2 = 1e30
    max_t = -1.0; max_v2 = -1.0; max_v3 = -1.0

    for j in indices:
        f = forces[j]
        if f.P > max_p:
            max_p = f.P; best["Max P"] = j
        if f.P < min_p:
            min_p = f.P; best["Min P"] = j
        if f.M3 < min_m3:
            min_m3 = f.M3; best["Min M3"] = j
        if f.M3 > max_m3:
            max_m3 = f.M3; best["Max M3"] = j
        if f.M2 < min_m2:
            min_m2 = f.M2; best["Min M2"] = j
        if f.M2 > max_m2:
            max_m2 = f.M2; best["Max M2"] = j
        if abs(f.T) > max_t:
            max_t = abs(f.T); best["Max T (Abs)"] = j
        if abs(f.V2) > max_v2:
            max_v2 = abs(f.V2); best["Max V2 (Abs)"] = j
        if abs(f.V3) > max_v3:
            max_v3 = abs(f.V3); best["Max V3 (Abs)"] = j

    return best


def node_label_for(node_key: str, station: float, info: FrameInfo) -> str:
    if node_key == NODE_KEY_START:
        return f"Nút Đầu ({station:.2f}m)"
    if node_key == NODE_KEY_END:
        return f"Nút Cuối (L = {info.length:.2f}m)"
    return "Toàn thanh"


def make_result_row(
    connector: SAP2000Connector,
    info: FrameInfo,
    f: FrameForceRow,
    node_key: str,
    node_label: str,
    extreme_type: str,
) -> ResultRow:
    """Tạo 1 dòng kết quả + kích thước tiết diện tại station của dòng đó."""
    row = ResultRow(
        frame_name=info.name,
        # Excel/Module1: cột Tiết Diện ghi PropName
        section_name=info.prop_name or info.section_name,
        length=round(info.length, 3),
        node_label=node_label,
        extreme_type=extreme_type,
        node_key=node_key,
    )
    apply_force_values(row, f)
    apply_section_dims(connector, info, row)
    return row


def _round(value: float, ndigits: int = 2) -> float:
    """Làm tròn, đổi -0.0 thành 0.0 (tránh dán '-0.0' sang RAM Connection)."""
    v = round(value, ndigits)
    return 0.0 if v == 0 else v


def apply_force_values(row: ResultRow, f: FrameForceRow):
    """Gán nội lực của 1 dòng FrameForce vào ResultRow (làm tròn như tool)."""
    row.load_case = f.load_case
    row.obj_station = f.obj_station
    row.P = _round(f.P)
    row.V2 = _round(f.V2)
    row.V3 = _round(f.V3)
    row.T = _round(f.T, 3)      # T thường rất nhỏ (Excel mẫu: 0.0018 kNm)
    row.M2 = _round(f.M2)
    row.M3 = _round(f.M3)


def apply_section_dims(connector: SAP2000Connector, info: FrameInfo, row: ResultRow):
    """
    Excel PrintExtremeRows: station tính từ mặt gối I, chiều dài thông thủy.
    Tiết diện thực (auto-select nếu có) để lấy đúng kích thước.
    """
    adj_station = max(0.0, row.obj_station - info.length1)
    adj_length = info.length - info.length1 - info.length2
    if adj_length <= 0:
        adj_length = info.length
    dims = connector.get_section_dimensions(
        info.section_name or info.prop_name, adj_station, adj_length,
    )
    row.sec_type = dims.type_name
    row.t3 = round(dims.t3, 4)
    row.t2 = round(dims.t2, 4)
    row.tf = round(dims.tf, 4)
    row.tw = round(dims.tw, 4)
    row.t2b = round(dims.t2b, 4)
    row.tfb = round(dims.tfb, 4)
    row.dis = round(dims.dis, 4)
    row.fillet = round(dims.fillet, 4)
    row.mirror = dims.mirror_text


def process_frame_node_extremes(
    connector: SAP2000Connector,
    frame_name: str,
    node_option: str,   # "1" Đầu, "2" Cuối, "3" Cả hai, "4" Toàn thanh
    callback=None,
    allowed_loads: Optional[set[str]] = None,
    force_cache: Optional[dict[str, list[FrameForceRow]]] = None,
    info_cache: Optional[dict[str, FrameInfo]] = None,
) -> list[ResultRow]:
    """
    Xử lý 1 Frame → trả về danh sách ResultRow (Excel InternalForce, Member-by-Member).

    Parameters
    ----------
    connector : SAP2000Connector
    frame_name : str
    node_option : str
        "1" = Nút Đầu, "2" = Nút Cuối, "3" = cả hai, "4" = toàn thanh (Envelope)
    callback : callable, optional
        Hàm gọi lại để cập nhật progress.
    allowed_loads : set[str], optional
        Chỉ xét các nguồn tải này. Modal luôn bị loại.
    force_cache, info_cache : dict, optional
        Lưu nội lực đã lọc / thông tin thanh (để chọn lại nguồn tải trên bảng).

    Returns
    -------
    list[ResultRow]
    """
    info = connector.get_frame_info(frame_name)
    forces = filter_design_forces(
        connector.get_frame_forces(frame_name),
        allowed_loads,
    )
    if force_cache is not None:
        force_cache[frame_name] = forces
    if info_cache is not None:
        info_cache[frame_name] = info

    if not forces:
        return []

    node_keys = []
    if node_option in (NODE_START, NODE_BOTH):
        node_keys.append(NODE_KEY_START)
    if node_option in (NODE_END, NODE_BOTH):
        node_keys.append(NODE_KEY_END)
    if node_option == NODE_ENVELOPE:
        node_keys.append(NODE_KEY_ENVELOPE)

    results: list[ResultRow] = []
    for node_key in node_keys:
        indices, station = station_indices(forces, info, node_key)
        label = node_label_for(node_key, station, info)
        extremes = find_extremes(forces, indices)
        for ext_name in EXTREME_NAMES:
            idx = extremes[ext_name]
            if idx != -1:
                results.append(make_result_row(
                    connector, info, forces[idx], node_key, label, ext_name,
                ))

    return results


def forces_at_row_position(
    forces: list[FrameForceRow],
    row: ResultRow,
) -> list[FrameForceRow]:
    """
    Các dòng nội lực cùng station với 1 dòng kết quả (để chọn lại nguồn tải).
    Toàn thanh cũng giữ nguyên station của dòng — chỉ đổi combo.
    """
    at_sta = [f for f in forces if abs(f.obj_station - row.obj_station) <= STATION_TOL]
    return at_sta or list(forces)


# ═══════════════════════════════════════════════════════════════
# MODULE 2: TÓM TẮT CỰC TRỊ TOÀN CỤC
# ═══════════════════════════════════════════════════════════════

SUMMARY_CONDITIONS = ["Mmax", "Mmin", "V2max", "Nmax", "Nmin", "V3max"]


def summarize_global_extremes(
    data: list[ResultRow],
    node_keyword: Optional[str] = None,   # "Nút Đầu" / "Nút Cuối" / None = mọi dòng
) -> list[SummaryRow]:
    """
    Tạo bảng tóm tắt 6 điều kiện cực trị toàn cục (Module2).

    node_keyword = None → gộp mọi dòng đã xuất (cả 2 đầu / toàn thanh) thành
    1 bảng duy nhất. Tìm: Mmax, Mmin, V2max, Nmax, Nmin, V3max.
    V2max / V3max so theo trị tuyệt đối (khớp dòng "Max V2 (Abs)"), giữ dấu.
    """
    best = {
        "Mmax":  {"val": -1e15, "row": None},
        "Mmin":  {"val":  1e15, "row": None},
        "V2max": {"val": -1e15, "row": None},
        "Nmax":  {"val": -1e15, "row": None},
        "Nmin":  {"val":  1e15, "row": None},
        "V3max": {"val": -1e15, "row": None},
    }

    kw_lower = (node_keyword or "").lower()
    is_dau_filter = ("dau" in kw_lower or "đầu" in kw_lower)
    is_cuoi_filter = ("cuoi" in kw_lower or "cuối" in kw_lower)

    for row in data:
        lbl_lower = row.node_label.lower()
        if is_dau_filter and ("dau" not in lbl_lower and "đầu" not in lbl_lower):
            continue
        if is_cuoi_filter and ("cuoi" not in lbl_lower and "cuối" not in lbl_lower):
            continue

        # VBA Module2: ElseIf InStr(cType, ...) — một dòng chỉ vào 1 điều kiện
        c_type = row.extreme_type
        if "Max M3" in c_type:
            if row.M3 > best["Mmax"]["val"]:
                best["Mmax"]["val"] = row.M3
                best["Mmax"]["row"] = row
        elif "Min M3" in c_type:
            if row.M3 < best["Mmin"]["val"]:
                best["Mmin"]["val"] = row.M3
                best["Mmin"]["row"] = row
        elif "Max V2" in c_type:
            if abs(row.V2) > best["V2max"]["val"]:
                best["V2max"]["val"] = abs(row.V2)
                best["V2max"]["row"] = row
        elif "Max P" in c_type:
            if row.P > best["Nmax"]["val"]:
                best["Nmax"]["val"] = row.P
                best["Nmax"]["row"] = row
        elif "Min P" in c_type:
            if row.P < best["Nmin"]["val"]:
                best["Nmin"]["val"] = row.P
                best["Nmin"]["row"] = row
        elif "Max V3" in c_type:
            if abs(row.V3) > best["V3max"]["val"]:
                best["V3max"]["val"] = abs(row.V3)
                best["V3max"]["row"] = row

    results: list[SummaryRow] = []
    for i, cond in enumerate(SUMMARY_CONDITIONS):
        r = best[cond]["row"]
        if r:
            results.append(SummaryRow(
                num=i + 1,
                condition=cond,
                V2=r.V2,
                V3=r.V3,
                axial=r.P,
                M33=r.M3,
                M22=r.M2,
                bar=r.frame_name,
                source=r.source_text,
                load_case=r.load_case,
            ))
        else:
            results.append(SummaryRow(num=i + 1, condition=cond))

    return results


# ═══════════════════════════════════════════════════════════════
# MODULE 4: NỘI SUY TẠI NHIỀU VỊ TRÍ
# ═══════════════════════════════════════════════════════════════

@dataclass
class InterpolatedResult:
    """Kết quả nội suy tại 1 vị trí cho 1 load case."""
    load_case: str = ""
    P: float = 0.0
    V2: float = 0.0
    V3: float = 0.0
    M2: float = 0.0
    M3: float = 0.0


def interpolate_forces_at_station(
    forces: list[FrameForceRow],
    target_station: float,
) -> list[InterpolatedResult]:
    """
    Nội suy nội lực tại 1 vị trí bất kỳ (Module4).

    Tìm 2 điểm gần nhất (trước và sau target_station) cùng load case,
    rồi nội suy tuyến tính.
    """
    # Tìm tất cả load case duy nhất
    case_set: dict[str, int] = {}
    for f in forces:
        if f.load_case not in case_set:
            case_set[f.load_case] = 1

    results: list[InterpolatedResult] = []

    for case_name in case_set:
        sta_low = -1.0
        sta_high = -1.0
        p_low = v2_low = v3_low = m2_low = m3_low = 0.0
        p_high = v2_high = v3_high = m2_high = m3_high = 0.0

        for f in forces:
            if f.load_case != case_name:
                continue

            cur_sta = f.obj_station

            # Trùng target
            if abs(cur_sta - target_station) < 0.0001:
                sta_low = sta_high = target_station
                p_low = p_high = f.P
                v2_low = v2_high = f.V2
                v3_low = v3_high = f.V3
                m2_low = m2_high = f.M2
                m3_low = m3_high = f.M3
                break

            # Phía trước target
            if cur_sta <= target_station:
                if cur_sta > sta_low or sta_low == -1:
                    sta_low = cur_sta
                    p_low = f.P; v2_low = f.V2; v3_low = f.V3
                    m2_low = f.M2; m3_low = f.M3

            # Phía sau target
            if cur_sta >= target_station:
                if cur_sta < sta_high or sta_high == -1:
                    sta_high = cur_sta
                    p_high = f.P; v2_high = f.V2; v3_high = f.V3
                    m2_high = f.M2; m3_high = f.M3

        # Fallback: chỉ có 1 phía
        if sta_low == -1 and sta_high != -1:
            sta_low = sta_high
            p_low = p_high; v2_low = v2_high; v3_low = v3_high
            m2_low = m2_high; m3_low = m3_high

        if sta_high == -1 and sta_low != -1:
            sta_high = sta_low
            p_high = p_low; v2_high = v2_low; v3_high = v3_low
            m2_high = m2_low; m3_high = m3_low

        # Nội suy
        if sta_low != -1 and sta_high != -1:
            if sta_low == sta_high:
                ip = p_low; iv2 = v2_low; iv3 = v3_low
                im2 = m2_low; im3 = m3_low
            else:
                ratio = (target_station - sta_low) / (sta_high - sta_low)
                ip = p_low + (p_high - p_low) * ratio
                iv2 = v2_low + (v2_high - v2_low) * ratio
                iv3 = v3_low + (v3_high - v3_low) * ratio
                im2 = m2_low + (m2_high - m2_low) * ratio
                im3 = m3_low + (m3_high - m3_low) * ratio

            results.append(InterpolatedResult(
                load_case=case_name,
                P=ip, V2=iv2, V3=iv3, M2=im2, M3=im3,
            ))

    return results


def find_extremes_from_interpolated(
    interpolated: list[InterpolatedResult],
) -> list[tuple[str, str]]:
    """
    Tìm 10 cực trị từ dữ liệu nội suy (Module4).

    Returns
    -------
    list[tuple[str, str]]
        [(extreme_name, load_case_name), ...]
        Ví dụ: [("Max P", "LRFD: 76: ..."), ("Min P", "LRFD: 1137: ..."), ...]
    """
    if not interpolated:
        return []

    val_p_max = -1e15; c_max_p = ""
    val_p_min = 1e15;  c_min_p = ""
    val_v2_max = -1e15; c_max_v2 = ""
    val_v2_min = 1e15;  c_min_v2 = ""
    val_v3_max = -1e15; c_max_v3 = ""
    val_v3_min = 1e15;  c_min_v3 = ""
    val_m2_max = -1e15; c_max_m2 = ""
    val_m2_min = 1e15;  c_min_m2 = ""
    val_m3_max = -1e15; c_max_m3 = ""
    val_m3_min = 1e15;  c_min_m3 = ""

    for r in interpolated:
        if r.P >= val_p_max:  val_p_max = r.P;  c_max_p = r.load_case
        if r.P <= val_p_min:  val_p_min = r.P;  c_min_p = r.load_case
        if r.V2 >= val_v2_max: val_v2_max = r.V2; c_max_v2 = r.load_case
        if r.V2 <= val_v2_min: val_v2_min = r.V2; c_min_v2 = r.load_case
        if r.V3 >= val_v3_max: val_v3_max = r.V3; c_max_v3 = r.load_case
        if r.V3 <= val_v3_min: val_v3_min = r.V3; c_min_v3 = r.load_case
        if r.M2 >= val_m2_max: val_m2_max = r.M2; c_max_m2 = r.load_case
        if r.M2 <= val_m2_min: val_m2_min = r.M2; c_min_m2 = r.load_case
        if r.M3 >= val_m3_max: val_m3_max = r.M3; c_max_m3 = r.load_case
        if r.M3 <= val_m3_min: val_m3_min = r.M3; c_min_m3 = r.load_case

    return [
        ("Max P", c_max_p),
        ("Min P", c_min_p),
        ("Max V2", c_max_v2),
        ("Min V2", c_min_v2),
        ("Max V3", c_max_v3),
        ("Min V3", c_min_v3),
        ("Max M2", c_max_m2),
        ("Min M2", c_min_m2),
        ("Max M3", c_max_m3),
        ("Min M3", c_min_m3),
    ]


def process_frame_multi_station(
    connector: SAP2000Connector,
    frame_name: str,
    stations: list[float],
    allowed_loads: Optional[set[str]] = None,
) -> list[ResultRowMulti]:
    """
    Xử lý 1 Frame tại nhiều vị trí → trả về danh sách ResultRowMulti (Module4).
    """
    info = connector.get_frame_info(frame_name)
    forces = filter_design_forces(
        connector.get_frame_forces(frame_name),
        allowed_loads,
    )

    if not forces:
        return []

    results: list[ResultRowMulti] = []

    for station in stations:
        # Bỏ qua nếu vị trí > chiều dài thanh
        if info.length < station:
            continue

        # Lấy thông số tiết diện
        api_props = connector.get_section_props_api(info.section_name)
        if api_props.success:
            props = SectionProps(
                htb=api_props.htb,
                tw=api_props.tw,
                bf=api_props.bf,
                tf=api_props.tf,
            )
        else:
            props = parse_section_name(
                info.section_name,
                l_total=info.length,
                station=station,
            )

        location_label = f"Cach nut dau {station:.2f}m"

        # Nội suy
        interpolated = interpolate_forces_at_station(forces, station)

        if not interpolated:
            continue

        # Tìm cực trị
        ext_pairs = find_extremes_from_interpolated(interpolated)

        for ext_name, case_name in ext_pairs:
            if not case_name:
                continue
            # Tìm dữ liệu nội suy của case đó
            for ir in interpolated:
                if ir.load_case == case_name:
                    results.append(ResultRowMulti(
                        frame_name=info.name,
                        section_name=info.section_name,
                        htb=round(props.htb, 3),
                        tw=round(props.tw, 2),
                        bf=round(props.bf, 2),
                        tf=round(props.tf, 2),
                        length=round(info.length, 3),
                        location_label=location_label,
                        extreme_type=ext_name,
                        load_case=case_name,
                        P=round(ir.P, 2),
                        V2=round(ir.V2, 2),
                        V3=round(ir.V3, 2),
                        M2=round(ir.M2, 2),
                        M3=round(ir.M3, 2),
                    ))
                    break

    return results


# ═══════════════════════════════════════════════════════════════
# TORSIONAL CHECK: TÌM M3 MIN THEO VỊ TRÍ
# ═══════════════════════════════════════════════════════════════

def find_m3_min_row(
    data: list[ResultRowMulti],
    location_label: str,
) -> Optional[ResultRowMulti]:
    """
    Tìm dòng có M3 nhỏ nhất tại vị trí cho trước (cho Torsional Check).
    """
    best: Optional[ResultRowMulti] = None
    best_m3 = 1e15

    for row in data:
        if row.location_label == location_label:
            if row.M3 < best_m3:
                best_m3 = row.M3
                best = row

    return best


def get_unique_locations(data: list[ResultRowMulti]) -> list[str]:
    """Lấy danh sách vị trí duy nhất từ dữ liệu."""
    seen: dict[str, int] = {}
    result: list[str] = []
    for row in data:
        if row.location_label not in seen:
            seen[row.location_label] = 1
            result.append(row.location_label)
    return result


# ═══════════════════════════════════════════════════════════════
# PHẢN LỰC NÚT (theo Excel Reaction)
# ═══════════════════════════════════════════════════════════════

# Thứ tự quét — Excel: tenPhanLuc = Array("F1 (Fx)", ..., "M3 (Mz)")
REACTION_COMPONENTS = [
    ("F1", "F1 (Fx)"), ("F2", "F2 (Fy)"), ("F3", "F3 (Fz)"),
    ("M1", "M1 (Mx)"), ("M2", "M2 (My)"), ("M3", "M3 (Mz)"),
]


@dataclass
class ReactionRow:
    """1 dòng kết quả phản lực: đủ 6 thành phần tại dòng cực trị (Excel GhiDongKetQua)."""
    joint: str = ""
    criteria: str = ""         # "Max F1 (Fx) (+)" / "Max F1 (Fx) (-)"
    load_case: str = ""
    step_type: str = ""
    step_num: float = 0.0
    F1: float = 0.0
    F2: float = 0.0
    F3: float = 0.0
    M1: float = 0.0
    M2: float = 0.0
    M3: float = 0.0
    comp: str = ""             # thành phần quyết định: "F1".."M3"

    @property
    def step_text(self):
        """Excel ghi StepNum; combo bao (Envelope) ghi thêm Max/Min cho rõ."""
        if self.step_type in ("Max", "Min"):
            return self.step_type
        step = float(self.step_num)
        return int(step) if step.is_integer() else step


def filter_reactions(
    reacts: list[JointReactRow],
    allowed_loads: Optional[set[str]] = None,
) -> list[JointReactRow]:
    """Bỏ Modal; nếu có danh sách cho phép thì chỉ giữ các nguồn đó."""
    return [
        r for r in reacts
        if not is_modal_load(r.load_case)
        and (allowed_loads is None or r.load_case in allowed_loads)
    ]


def flip_reaction_axial(reacts: list[JointReactRow]) -> list[JointReactRow]:
    """
    Đổi dấu lực dọc F3 (theo yêu cầu: phản lực luôn đổi dấu Axial).
    Đổi TRƯỚC khi tìm cực trị → nhãn (+)/(−) và màu khớp với giá trị hiển thị.
    """
    return [replace(r, F3=-r.F3 or 0.0) for r in reacts]


def apply_reaction_values(row: ReactionRow, r: JointReactRow):
    """Gán 6 thành phần phản lực của 1 dòng SAP vào ReactionRow (làm tròn như tool)."""
    row.joint = r.joint
    row.load_case = r.load_case
    row.step_type = r.step_type
    row.step_num = r.step_num
    for comp, _label in REACTION_COMPONENTS:
        setattr(row, comp, _round(getattr(r, comp)))


def find_reaction_extremes(
    reacts: list[JointReactRow],
    joint: Optional[str] = None,
) -> list[ReactionRow]:
    """
    Excel TimVaGhiDong: với mỗi thành phần F1..M3 tìm giá trị dương lớn nhất (+)
    và âm nhỏ nhất (−). Bỏ qua giá trị = 0 → gối khớp không có dòng M.
    joint = None: gộp mọi nút; có tên: chỉ xét nút đó.
    """
    cand = [r for r in reacts if joint is None or r.joint == joint]
    rows: list[ReactionRow] = []
    for comp, label in REACTION_COMPONENTS:
        pos = neg = None
        pos_val, neg_val = -1e20, 1e20
        for r in cand:
            v = getattr(r, comp)
            if v > 0:
                if v > pos_val:
                    pos_val, pos = v, r
            elif v < 0:
                if v < neg_val:
                    neg_val, neg = v, r
        for src, sign in ((pos, "+"), (neg, "-")):
            if src is not None:
                row = ReactionRow(criteria=f"Max {label} ({sign})", comp=comp)
                apply_reaction_values(row, src)
                rows.append(row)
    return rows


def reaction_joints(reacts: list[JointReactRow]) -> list[str]:
    """Danh sách nút theo thứ tự xuất hiện (Excel: Scripting.Dictionary keys)."""
    seen: dict[str, int] = {}
    for r in reacts:
        seen.setdefault(r.joint, 1)
    return list(seen)


def process_reactions(
    reacts: list[JointReactRow],
) -> tuple[list[ReactionRow], list[ReactionRow]]:
    """
    Tính cả 2 kiểu lọc của Excel trong 1 lần:
      (gộp mọi nút, từng nút riêng biệt).
    """
    merged = find_reaction_extremes(reacts)
    by_joint: list[ReactionRow] = []
    for j in reaction_joints(reacts):
        by_joint.extend(find_reaction_extremes(reacts, j))
    return merged, by_joint


def reaction_choices(
    reacts: list[JointReactRow],
    joint: str,
) -> list[tuple[str, JointReactRow]]:
    """
    Các dòng phản lực của 1 nút để chọn lại nguồn tải.
    Combo bao (nhiều step) được ghi kèm [StepType StepNum] để phân biệt.
    """
    at = [r for r in reacts if r.joint == joint]
    counts: dict[str, int] = {}
    for r in at:
        counts[r.load_case] = counts.get(r.load_case, 0) + 1
    out: list[tuple[str, JointReactRow]] = []
    seen: set[str] = set()
    for r in at:
        label = r.load_case
        if counts[r.load_case] > 1:
            label = f"{r.load_case} [{r.step_type} {r.step_num:g}]".replace("  ", " ")
        if label not in seen:
            out.append((label, r))
            seen.add(label)
    return out


def summarize_reaction_extremes(
    reacts: list[JointReactRow],
    axial_sign: float = 1.0,
) -> list[SummaryRow]:
    """
    Bảng tóm tắt 6 điều kiện (như tóm tắt thanh) từ MỌI dòng phản lực.

    Ghép theo trục cục bộ mặc định của cột đứng (trục 2 // X, trục 3 // Y):
      V2 = F1, V3 = F2, Axial = axial_sign × F3, M33 = M2, M22 = M1.
    axial_sign = -1 khi reacts đã bị đổi dấu F3 (tab Phản Lực) → Axial = F3 gốc
    của SAP (nén dương), cùng dấu với tóm tắt thanh.
    V2max / V3max so theo trị tuyệt đối, giữ dấu.
    """
    def mapped(r: JointReactRow) -> dict:
        return {
            "V2": r.F1, "V3": r.F2, "axial": axial_sign * r.F3,
            "M33": r.M2, "M22": r.M1,
        }

    # (điều kiện, đại lượng, hàm khóa so sánh — lấy dòng có khóa lớn nhất)
    rules = [
        ("Mmax", "M33", lambda v: v),
        ("Mmin", "M33", lambda v: -v),
        ("V2max", "V2", abs),
        ("Nmax", "axial", lambda v: v),
        ("Nmin", "axial", lambda v: -v),
        ("V3max", "V3", abs),
    ]

    results: list[SummaryRow] = []
    for i, (cond, key, score) in enumerate(rules):
        best = None
        best_score = -1e30
        for r in reacts:
            s = score(mapped(r)[key])
            if s > best_score:      # "lớn hơn hẳn" → bằng nhau giữ dòng gặp trước
                best_score, best = s, r
        if best is None:
            results.append(SummaryRow(num=i + 1, condition=cond))
            continue
        m = mapped(best)
        step = f" [{best.step_type}]" if best.step_type in ("Max", "Min") else ""
        results.append(SummaryRow(
            num=i + 1,
            condition=cond,
            V2=_round(m["V2"]),
            V3=_round(m["V3"]),
            axial=_round(m["axial"]),
            M33=_round(m["M33"]),
            M22=_round(m["M22"]),
            bar=best.joint,
            source=f"Nút {best.joint}",
            load_case=best.load_case + step,
        ))
    return results
