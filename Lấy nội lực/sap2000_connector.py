"""
sap2000_connector.py
====================
Wrapper kết nối SAP2000 qua COM API (comtypes).

Đóng gói toàn bộ tương tác SAP2000:
  - Kết nối / ngắt kết nối
  - Lấy danh sách Frame đang chọn
  - Lấy nội lực FrameForce
  - Lấy thông số tiết diện
  - Thiết lập nguồn tải đầu ra

Tương đương VBA: Phần COM trong Module1 + Module4.
"""

from __future__ import annotations

import math
import traceback
from dataclasses import dataclass, field
from typing import Optional


# ── Kiểu dữ liệu trả về ──────────────────────────────────────

@dataclass
class FrameInfo:
    """Thông tin cơ bản của 1 Frame."""
    name: str
    section_name: str           # ActualProp = SPropName hoặc PropName (Module4)
    length: float               # Chiều dài thực (m)
    prop_name: str = ""         # PropName thuần — Module1 ghi cột Tiet Dien
    s_prop_name: str = ""       # Auto-select (nếu có)
    length1: float = 0.0        # End offset đầu I (m) — Excel: GetEndLengthOffset
    length2: float = 0.0        # End offset đầu J (m)
    auto_offset: bool = False


@dataclass
class FrameForceRow:
    """1 kết quả nội lực tại 1 station / 1 load case."""
    obj_station: float          # Vị trí trên thanh (m)
    load_case: str              # Tên combo/case
    P: float = 0.0              # Lực dọc (kN)
    V2: float = 0.0             # Lực cắt phương 2 (kN)
    V3: float = 0.0             # Lực cắt phương 3 (kN)
    T: float = 0.0              # Mô-men xoắn (kNm)
    M2: float = 0.0             # Mô-men phương 2 (kNm)
    M3: float = 0.0             # Mô-men phương 3 (kNm)


@dataclass
class JointReactRow:
    """1 kết quả phản lực tại 1 nút / 1 load case / 1 step (Results.JointReact)."""
    joint: str
    load_case: str
    step_type: str = ""
    step_num: float = 0.0
    F1: float = 0.0             # kN
    F2: float = 0.0
    F3: float = 0.0
    M1: float = 0.0             # kNm
    M2: float = 0.0
    M3: float = 0.0


@dataclass
class SectionFromAPI:
    """Thông số tiết diện I-Section lấy từ SAP2000 API (đơn vị mm)."""
    htb: float = 0.0
    tw: float = 0.0
    bf: float = 0.0
    tf: float = 0.0
    success: bool = False


@dataclass
class SectionDims:
    """
    Kích thước tiết diện tại 1 station (đơn vị m).

    Tương đương Excel InternalForce: GetSectionDimensions / GetPrismaticDimensions.
    """
    type_name: str = ""
    t3: float = 0.0
    t2: float = 0.0
    tf: float = 0.0
    tw: float = 0.0
    t2b: float = 0.0
    tfb: float = 0.0
    dis: float = 0.0
    fillet: float = 0.0
    mirror2: bool = False
    mirror3: bool = False

    @property
    def mirror_text(self) -> str:
        """Excel: Mirror-2 cho Channel đơn, Mirror-3 cho Double Angle, còn lại N/A."""
        if "Channel" in self.type_name and "Double" not in self.type_name:
            return "Mirror-2" if self.mirror2 else "None"
        if "Double Angle" in self.type_name:
            return "Mirror-3" if self.mirror3 else "None"
        return "N/A"


# ── Nguồn tải ─────────────────────────────────────────────────

LOAD_PATTERNS = "1"
LOAD_CASES = "2"
LOAD_COMBOS = "3"
LOAD_DESIGN_COMBOS = "4"      # Excel: combo thiết kế cường độ gán cho từng thanh
LOAD_CASES_AND_DESIGN = "5"   # Excel: Load Cases + Design Combos

# CSI eLoadCaseType: Modal = 3, Buckling = 10 (không dùng cho nội lực thiết kế)
_LOAD_CASE_TYPE_MODAL = 3
_LOAD_CASE_TYPE_BUCKLING = 10

# FrameObj.GetDesignProcedure → đối tượng Design tương ứng (Excel + tài liệu API)
DESIGN_PROC_NO_DESIGN = 9
_DESIGN_OBJECTS = {
    1: "DesignSteel",
    2: "DesignConcrete",
    7: "DesignAluminum",
    8: "DesignColdFormed",
}

# PropFrame.GetTypeOAPI → (tên loại, hàm API, các giá trị ByRef sau MatProp)
# "_" = giá trị bỏ qua; "thick" gán cho cả tw và tf (tiết diện thành mỏng).
_FRAME_PROP_VARIABLE = 14
_PRISMATIC_API = {
    1: ("I-Section", "GetISection_1", ("t3", "t2", "tf", "tw", "t2b", "tfb", "fillet")),
    2: ("Channel", "GetChannel_2", ("t3", "t2", "tf", "tw", "fillet", "mirror2")),
    3: ("Tee", "GetTee_1", ("t3", "t2", "tf", "tw", "fillet", "mirror3")),
    4: ("Angle", "GetAngle_1", ("t3", "t2", "tf", "tw", "fillet")),
    5: ("Double Angle", "GetDblAngle_2", ("t3", "t2", "tf", "tw", "dis", "fillet", "mirror3")),
    6: ("Box", "GetTube", ("t3", "t2", "tf", "tw")),
    7: ("Pipe", "GetPipe", ("t3", "tw")),
    8: ("Rectangular", "GetRectangle", ("t3", "t2")),
    9: ("Circle", "GetCircle", ("t3",)),
    11: ("Double Channel", "GetDblChannel_1", ("t3", "t2", "tf", "tw", "dis", "fillet")),
    17: ("Cold Formed C", "GetColdC", ("t3", "t2", "thick", "fillet", "dis")),
    19: ("Cold Formed Z", "GetColdZ", ("t3", "t2", "thick", "fillet", "dis", "_")),
    22: ("Cold Formed Hat", "GetColdHat", ("t3", "t2", "thick", "fillet", "dis")),
}
_GENERAL_API = ("Other/General", "GetGeneral", ("t3", "t2") + ("_",) * 12)
# Dự phòng khi bản SAP cũ không có GetISection_1
_ISECTION_FALLBACK = ("I-Section", "GetISection", ("t3", "t2", "tf", "tw", "t2b", "tfb"))


def is_modal_load(name: str) -> bool:
    """True nếu tên là case Modal (không dùng cho nội lực thiết kế)."""
    n = (name or "").strip()
    if not n:
        return False
    head = n.split()[0].split(":")[0].split("-")[0].split("_")[0]
    return head.upper() == "MODAL"


def is_lrfd_load(name: str) -> bool:
    """True nếu tên nguồn tải chứa LRFD."""
    return "LRFD" in (name or "").upper()


def default_selected_loads(
    names: list[str],
    modal_names: Optional[set[str]] = None,
    source_type: Optional[str] = None,
) -> list[str]:
    """
    Nguồn tải mặc định (luôn bỏ Modal / Buckling):
      - Combos (tất cả) hoặc không rõ loại: chỉ lấy nguồn có LRFD.
      - Load Cases / Design Combos / Cases + Design: lấy hết (giống Excel).
    """
    modal = modal_names or set()
    usable = [n for n in names if n not in modal and not is_modal_load(n)]
    if source_type in (LOAD_PATTERNS, LOAD_CASES, LOAD_DESIGN_COMBOS, LOAD_CASES_AND_DESIGN):
        return usable
    return [n for n in usable if is_lrfd_load(n)]

OBJ_TYPE_POINT = 1
OBJ_TYPE_FRAME = 2

# eItemTypeElm cho Results.JointReact
_ITEM_OBJECT = 0
_ITEM_SELECTION = 3

# ProgID Helper: SAP2000v1 là chuẩn máy này (v25); CSiAPIv1 là alias cũ.
_HELPER_PROGIDS = ("SAP2000v1.Helper", "CSiAPIv1.Helper")
_SAP_PROGID = "CSI.SAP2000.API.SapObject"


def _safe_int(val) -> int:
    """Chuyển đổi an toàn giá trị COM thành int."""
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def _safe_float(val) -> float:
    """Chuyển đổi an toàn giá trị COM thành float."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _safe_str(val) -> str:
    """Chuyển đổi an toàn giá trị COM thành str."""
    try:
        if val is None:
            return ""
        return str(val)
    except Exception:
        return ""


def _unpack_com_result(ret, expected_count: int):
    """
    Giải nén kết quả trả về từ COM method.

    comtypes có thể trả về:
      - Chỉ ret code (int)
      - Tuple (ret_code, param1, param2, ...)
      - Tuple (param1, param2, ...) không có ret code
    """
    if ret is None:
        return tuple([None] * (expected_count + 1))

    if isinstance(ret, (int, float)):
        # Chỉ trả về ret code
        return tuple([int(ret)] + [None] * expected_count)

    if isinstance(ret, tuple):
        return ret

    # Có thể là 1 giá trị đơn
    return (ret,) + tuple([None] * expected_count)


def _com_ret(out):
    """Mã trả về COM: phần tử cuối tuple (comtypes)."""
    if isinstance(out, (tuple, list)) and out:
        return out[-1]
    return out


def _as_list(x) -> list:
    """Đưa SAFEARRAY / tuple / giá trị đơn về list Python."""
    if x is None:
        return []
    if isinstance(x, str):
        return [x]
    if isinstance(x, (list, tuple)):
        return list(x)
    try:
        return list(x)
    except TypeError:
        return [x]


def _looks_like_names(arr: list) -> bool:
    sample = arr[:3]
    return bool(sample) and all(isinstance(x, str) for x in sample)


def _looks_like_types(arr: list) -> bool:
    sample = arr[:3]
    return bool(sample) and all(
        isinstance(x, (int, float)) and not isinstance(x, bool) for x in sample
    )


def parse_get_selected(out) -> list[tuple[int, str]]:
    """
    Bóc (ObjectType, ObjectName) từ SelectObj.GetSelected.

    comtypes chuẩn (có dummy ByRef): (NumberItems, ObjectType, ObjectName, ret)
    """
    if out is None or isinstance(out, (int, float)):
        return []
    if not isinstance(out, (tuple, list)) or len(out) < 2:
        return []

    items: list[tuple[int, str]] = []

    if len(out) >= 3:
        types = _as_list(out[1])
        names = _as_list(out[2])
        if _looks_like_names(types) and _looks_like_types(names):
            types, names = names, types
        try:
            n = int(out[0]) if out[0] is not None else len(names)
        except (TypeError, ValueError):
            n = len(names)
        if n <= 0 and names:
            n = len(names)
        n = max(0, min(n, len(names)))
        for i in range(n):
            name = str(names[i]) if names[i] is not None else ""
            if not name:
                continue
            try:
                t = int(types[i]) if i < len(types) else OBJ_TYPE_FRAME
            except (TypeError, ValueError):
                t = OBJ_TYPE_FRAME
            items.append((t, name))
        if items:
            return items

    arrays = [
        x for x in out
        if hasattr(x, "__iter__") and not isinstance(x, (str, bytes))
    ]
    if len(arrays) >= 2:
        types = _as_list(arrays[0])
        names = _as_list(arrays[1])
        if _looks_like_names(types) and _looks_like_types(names):
            types, names = names, types
        for i, raw_name in enumerate(names):
            name = str(raw_name) if raw_name is not None else ""
            if not name:
                continue
            try:
                t = int(types[i]) if i < len(types) else OBJ_TYPE_FRAME
            except (TypeError, ValueError):
                t = OBJ_TYPE_FRAME
            items.append((t, name))
    return items


class SAP2000Connector:
    """Quản lý kết nối và truy vấn SAP2000."""

    def __init__(self):
        self._sap_object = None
        self._sap_model = None
        self.last_error = ""
        self._case_type_cache: dict[str, Optional[int]] = {}
        self._design_combo_cache: dict[int, list[str]] = {}
        self._design_proc_cache: dict[str, int] = {}
        self._section_cache: dict[str, SectionDims] = {}
        self._prop_type_cache: dict[str, Optional[int]] = {}

    def clear_caches(self):
        """Xóa cache — gọi đầu mỗi lần xuất vì model có thể đã đổi."""
        self._case_type_cache.clear()
        self._design_combo_cache.clear()
        self._design_proc_cache.clear()
        self._section_cache.clear()
        self._prop_type_cache.clear()

    # ── Kết nối ────────────────────────────────────────────────

    def connect(self) -> str:
        """
        Kết nối SAP2000 đang chạy.

        Returns
        -------
        str
            "OK" nếu thành công, hoặc thông báo lỗi.
        """
        try:
            import comtypes.client
        except ImportError as e:
            self.last_error = traceback.format_exc()
            return f"Chua cai comtypes. Chay: pip install comtypes\n{e}"

        last_err = None
        self._sap_object = None
        self._sap_model = None

        for progid in _HELPER_PROGIDS:
            try:
                helper = comtypes.client.CreateObject(progid)
                self._sap_object = helper.GetObject(_SAP_PROGID)
                if self._sap_object is not None:
                    break
            except Exception as e:
                last_err = e
                self._sap_object = None

        if self._sap_object is None:
            try:
                self._sap_object = comtypes.client.GetActiveObject(_SAP_PROGID)
            except Exception as e:
                last_err = e
                self._sap_object = None

        if self._sap_object is None:
            self.last_error = traceback.format_exc() if last_err else ""
            return (
                "Khong tim thay SAP2000 dang chay!\n"
                "Mo SAP2000 + load model roi bam Ket noi lai."
            )

        try:
            self._sap_model = self._sap_object.SapModel
        except Exception as e:
            self.last_error = traceback.format_exc()
            return f"Loi lay SapModel: {e}"

        self.clear_caches()
        return "OK"

    @property
    def is_connected(self) -> bool:
        return self._sap_model is not None

    # ── Đơn vị ────────────────────────────────────────────────

    def set_units_kn_m(self):
        """Đặt đơn vị kN-m-C (unit enum = 6)."""
        if self._sap_model:
            try:
                self._sap_model.SetPresentUnits(6)
            except Exception:
                pass

    # ── Lấy Frame đang chọn ───────────────────────────────────

    def get_selected_objects(self) -> list[tuple[int, str]]:
        """
        Mọi đối tượng đang chọn: (ObjectType, ObjectName).
        ObjectType: 1=Point, 2=Frame, 3=Cable, 5=Area, ...
        """
        if not self._sap_model:
            return []

        out = None
        try:
            # Dummy ByRef bắt buộc với comtypes — GetSelected() không đối số
            # thường chỉ trả về ret code, không có danh sách chọn.
            out = self._sap_model.SelectObj.GetSelected(0, [], [])
        except TypeError:
            try:
                out = self._sap_model.SelectObj.GetSelected()
            except Exception as e:
                self.last_error = f"GetSelected error: {e}\n{traceback.format_exc()}"
                return []
        except Exception as e:
            self.last_error = f"GetSelected error: {e}\n{traceback.format_exc()}"
            return []

        items = parse_get_selected(out)
        if items:
            self.last_error = ""
            return items

        # Tuple chuẩn NumberItems=0 → thật sự chưa chọn, không phải lỗi unpack
        if isinstance(out, (tuple, list)) and len(out) >= 3:
            try:
                n = int(out[0] or 0)
            except (TypeError, ValueError):
                n = -1
            if n == 0:
                self.last_error = ""
                return []

        self.last_error = f"GetSelected raw={out!r}"
        return items

    def get_selected_frames(self) -> list[str]:
        """
        Lấy danh sách tên các Frame đang được chọn trong SAP2000.

        Returns
        -------
        list[str]
            Danh sách tên Frame. Rỗng nếu không có.
        """
        if not self._sap_model:
            return []

        items = self.get_selected_objects()
        frames: list[str] = []
        seen: set[str] = set()
        for t, name in items:
            if t == OBJ_TYPE_FRAME and name not in seen:
                frames.append(name)
                seen.add(name)

        if frames:
            return frames
        if items:
            # Đang chọn object khác (nút/area), không phải Frame
            return []
        if not self.last_error:
            return []

        # Dự phòng: SelectObj.GetSelected unpack sai
        scanned = self._scan_selected_frames()
        if scanned:
            self.last_error = (
                "SelectObj.GetSelected khong tra Frame; "
                f"da dung FrameObj.GetSelected ({len(scanned)} thanh)."
            )
        return scanned

    def get_selected_points(self) -> list[str]:
        """Tên các nút (Point) đang chọn trong SAP2000."""
        out: list[str] = []
        seen: set[str] = set()
        for t, name in self.get_selected_objects():
            if t == OBJ_TYPE_POINT and name not in seen:
                out.append(name)
                seen.add(name)
        return out

    def get_frame_end_points(self, frames: list[str]) -> list[str]:
        """2 nút đầu/cuối của các thanh (không trùng, giữ thứ tự)."""
        out: list[str] = []
        seen: set[str] = set()
        for frame in frames:
            try:
                ret = self._sap_model.FrameObj.GetPoints(frame, "", "")
            except Exception:
                continue
            if not isinstance(ret, (tuple, list)) or len(ret) < 2:
                continue
            for p in (_safe_str(ret[0]), _safe_str(ret[1])):
                if p and p not in seen:
                    out.append(p)
                    seen.add(p)
        return out

    def _scan_selected_frames(self) -> list[str]:
        """Quét từng Frame: FrameObj.GetSelected(name) — chậm hơn, chắc hơn."""
        sm = self._sap_model
        if not sm:
            return []

        try:
            out = sm.FrameObj.GetNameList(0, [])
        except TypeError:
            try:
                out = sm.FrameObj.GetNameList()
            except Exception as e:
                self.last_error = f"GetNameList error: {e}\n{traceback.format_exc()}"
                return []
        except Exception as e:
            self.last_error = f"GetNameList error: {e}\n{traceback.format_exc()}"
            return []

        names = self._extract_name_list(out)
        selected: list[str] = []
        for name in names:
            name = str(name)
            if not name:
                continue
            try:
                r = sm.FrameObj.GetSelected(name, False)
            except TypeError:
                try:
                    r = sm.FrameObj.GetSelected(name)
                except Exception:
                    continue
            except Exception:
                continue

            flag = False
            if isinstance(r, (tuple, list)) and r:
                flag = bool(r[0])
            elif isinstance(r, bool):
                flag = r
            if flag:
                selected.append(name)
        return selected

    def describe_selection(self) -> str:
        """Mô tả ngắn selection hiện tại — dùng cho hộp thoại lỗi."""
        try:
            items = self.get_selected_objects()
        except Exception:
            items = []
        if not items:
            return ""
        counts: dict[int, int] = {}
        for t, _name in items:
            counts[t] = counts.get(t, 0) + 1
        labels = {
            OBJ_TYPE_POINT: "nut (Point)",
            OBJ_TYPE_FRAME: "thanh (Frame)",
            3: "cap (Cable)",
            4: "tendon",
            5: "area",
            6: "solid",
            7: "link",
        }
        parts = [
            f"{n} {labels.get(t, f'type={t}')}"
            for t, n in sorted(counts.items())
        ]
        return ", ".join(parts)

    # ── Thông tin Frame ───────────────────────────────────────

    def get_frame_info(self, frame_name: str) -> FrameInfo:
        """Lấy thông tin cơ bản (tên, tiết diện, chiều dài) của 1 Frame."""
        sm = self._sap_model
        prop_name = ""
        s_prop_name = ""
        actual_prop = ""
        length = 0.0

        try:
            ret = sm.FrameObj.GetSection(frame_name, "", "")
            if isinstance(ret, (tuple, list)) and len(ret) >= 2:
                prop_name = _safe_str(ret[0])
                s_prop_name = _safe_str(ret[1])
                actual_prop = s_prop_name if s_prop_name else prop_name
            elif isinstance(ret, (tuple, list)):
                strings = [x for x in ret if isinstance(x, str)]
                if strings:
                    prop_name = strings[0]
                    actual_prop = prop_name
        except Exception as e:
            self.last_error = f"GetSection error: {e}"

        try:
            ret_pts = sm.FrameObj.GetPoints(frame_name, "", "")
            pt1 = pt2 = ""
            if isinstance(ret_pts, (tuple, list)) and len(ret_pts) >= 2:
                pt1, pt2 = _safe_str(ret_pts[0]), _safe_str(ret_pts[1])

            if pt1 and pt2:
                x1, y1, z1 = self._point_xyz(pt1)
                x2, y2, z2 = self._point_xyz(pt2)
                length = math.sqrt(
                    (x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2
                )
        except Exception as e:
            self.last_error = f"GetPoints/Coord error: {e}"

        auto_offset, length1, length2 = self.get_end_offsets(frame_name)

        return FrameInfo(
            name=frame_name,
            section_name=actual_prop,
            length=round(length, 6),
            prop_name=prop_name,
            s_prop_name=s_prop_name,
            length1=length1,
            length2=length2,
            auto_offset=auto_offset,
        )

    def get_end_offsets(self, frame_name: str) -> tuple[bool, float, float]:
        """
        End offset 2 đầu thanh (Excel: FrameObj.GetEndLengthOffset).

        Returns (AutoOffset, Length1, Length2) — lỗi thì (False, 0, 0) như Excel.
        comtypes: (AutoOffset, Length1, Length2, RZ, ret).
        """
        try:
            out = self._sap_model.FrameObj.GetEndLengthOffset(
                frame_name, False, 0.0, 0.0, 0.0,
            )
        except Exception:
            return False, 0.0, 0.0
        if not isinstance(out, (tuple, list)) or len(out) < 3:
            return False, 0.0, 0.0
        if len(out) >= 5 and _safe_int(_com_ret(out)) != 0:
            return False, 0.0, 0.0
        return bool(out[0]), _safe_float(out[1]), _safe_float(out[2])

    # ── Thủ tục thiết kế & combo thiết kế (Excel InternalForce) ──

    def get_design_procedure(self, frame_name: str) -> int:
        """FrameObj.GetDesignProcedure: 1 Thép, 2 BTCT, 7 Nhôm, 8 Nguội, 9 Không TK."""
        if frame_name in self._design_proc_cache:
            return self._design_proc_cache[frame_name]
        proc = 0
        try:
            out = self._sap_model.FrameObj.GetDesignProcedure(frame_name, 0)
            if isinstance(out, (tuple, list)) and out:
                proc = _safe_int(out[0])
            elif isinstance(out, (int, float)):
                proc = int(out)
        except Exception:
            proc = 0
        self._design_proc_cache[frame_name] = proc
        return proc

    def get_design_combos(self, procedure: int) -> list[str]:
        """Combo thiết kế cường độ của 1 thủ tục (Design*.GetComboStrength)."""
        if procedure in self._design_combo_cache:
            return self._design_combo_cache[procedure]
        combos: list[str] = []
        obj_name = _DESIGN_OBJECTS.get(procedure)
        if obj_name and self._sap_model:
            try:
                design = getattr(self._sap_model, obj_name)
                out = design.GetComboStrength(0, [])
                combos = [
                    n for n in self._extract_name_list(out)
                    if n.upper() != "MODAL" and not is_modal_load(n)
                ]
            except Exception as e:
                self.last_error = f"{obj_name}.GetComboStrength error: {e}"
        self._design_combo_cache[procedure] = combos
        return combos

    def get_frame_design_combos(self, frame_name: str) -> list[str]:
        """Combo thiết kế cường độ gán cho đúng thanh này (theo thủ tục thiết kế)."""
        return self.get_design_combos(self.get_design_procedure(frame_name))

    def list_design_combos(self) -> list[str]:
        """Hợp các combo thiết kế cường độ của mọi thủ tục (để hiện trong ô chọn)."""
        out: list[str] = []
        seen: set[str] = set()
        for proc in _DESIGN_OBJECTS:
            for name in self.get_design_combos(proc):
                if name not in seen:
                    out.append(name)
                    seen.add(name)
        return out

    # ── Kích thước tiết diện tại station (Excel InternalForce) ──

    def get_section_dimensions(
        self,
        sec_name: str,
        station_x: float,
        member_length: float,
    ) -> SectionDims:
        """
        Kích thước tiết diện (m) tại station_x tính từ mặt gối đầu I.

        Tiết diện Variable (Non-prismatic): nội suy tuyến tính trong đoạn chứa
        station, giống hệt Excel GetSectionDimensions.
        """
        prop_type = self._frame_prop_type(sec_name)
        if prop_type is None:
            return SectionDims(type_name="Unknown")

        if prop_type == _FRAME_PROP_VARIABLE:
            key = f"{sec_name}|{station_x:.4f}|{member_length:.4f}"
        else:
            key = f"{sec_name}|PRISMATIC"
        cached = self._section_cache.get(key)
        if cached is not None:
            return cached

        if prop_type == _FRAME_PROP_VARIABLE:
            dims = self._nonprismatic_dims(sec_name, station_x, member_length)
        else:
            dims = self._prismatic_dims(sec_name, prop_type)
        self._section_cache[key] = dims
        return dims

    def _frame_prop_type(self, sec_name: str) -> Optional[int]:
        """PropFrame.GetTypeOAPI → eFramePropType (cache); None nếu lỗi."""
        if not self._sap_model or not sec_name:
            return None
        if sec_name in self._prop_type_cache:
            return self._prop_type_cache[sec_name]
        prop_type = None
        try:
            out = self._sap_model.PropFrame.GetTypeOAPI(sec_name, 0)
            if isinstance(out, (tuple, list)) and out:
                if len(out) < 2 or _safe_int(_com_ret(out)) == 0:
                    prop_type = _safe_int(out[0])
        except Exception:
            prop_type = None
        self._prop_type_cache[sec_name] = prop_type
        return prop_type

    def _prismatic_dims(self, sec_name: str, prop_type: int) -> SectionDims:
        """Excel GetPrismaticDimensions — gọi đúng hàm Get* theo loại tiết diện."""
        spec = _PRISMATIC_API.get(prop_type, _GENERAL_API)
        dims = self._read_prop(sec_name, spec)
        if dims is None and prop_type == 1:
            dims = self._read_prop(sec_name, _ISECTION_FALLBACK)
        return dims or SectionDims(type_name=spec[0])

    def _read_prop(self, sec_name: str, spec) -> Optional[SectionDims]:
        """
        Gọi PropFrame.<method>(Name, FileName, MatProp, <fields...>, Color, Notes, GUID).
        comtypes trả về (FileName, MatProp, <fields...>, Color, Notes, GUID, ret).
        """
        type_name, method, fields = spec
        args = [sec_name, "", ""]
        for f in fields:
            args.append(False if f.startswith("mirror") else 0.0)
        args += [0, "", ""]
        try:
            out = getattr(self._sap_model.PropFrame, method)(*args)
        except Exception:
            return None
        if not isinstance(out, (tuple, list)) or len(out) < 2 + len(fields):
            return None
        if _safe_int(_com_ret(out)) != 0:
            return None

        dims = SectionDims(type_name=type_name)
        for i, f in enumerate(fields):
            val = out[2 + i]
            if f == "_":
                continue
            if f.startswith("mirror"):
                setattr(dims, f, bool(val))
            elif f == "thick":
                dims.tw = dims.tf = _safe_float(val)
            else:
                setattr(dims, f, _safe_float(val))
        return dims

    def _nonprismatic_dims(
        self,
        sec_name: str,
        station_x: float,
        member_length: float,
    ) -> SectionDims:
        """Excel GetSectionDimensions — nhánh propType = 14 (Variable)."""
        segs = self._nonprismatic_segments(sec_name)
        if not segs:
            return SectionDims(type_name="Tapered (Error)")

        # Chiều dài tuyệt đối từng đoạn: MyType 2 = tuyệt đối, 1 = tương đối
        sum_abs = sum(length for _s, _e, length, t in segs if t == 2)
        sum_rel = sum(length for _s, _e, length, t in segs if t != 2)
        remaining = max(0.0, member_length - sum_abs)
        abs_lengths = []
        for _s, _e, length, t in segs:
            if t == 2:
                abs_lengths.append(length)
            else:
                abs_lengths.append(length / sum_rel * remaining if sum_rel > 0 else 0.0)

        # Đoạn chứa station
        seg_idx = len(segs) - 1
        current_x = 0.0
        for i, seg_len in enumerate(abs_lengths):
            current_x += seg_len
            if station_x <= current_x + 0.001:
                seg_idx = i
                break
        seg_start = sum(abs_lengths[:seg_idx])
        seg_len = abs_lengths[seg_idx]
        r = (station_x - seg_start) / seg_len if seg_len > 0 else 0.0
        r = min(1.0, max(0.0, r))

        start_sec, end_sec = segs[seg_idx][0], segs[seg_idx][1]
        a = self._section_at_end(start_sec)
        b = self._section_at_end(end_sec)

        dims = SectionDims(type_name=f"Tapered ({start_sec} to {end_sec})")
        for f in ("t3", "t2", "tf", "tw", "t2b", "tfb", "dis", "fillet"):
            va, vb = getattr(a, f), getattr(b, f)
            setattr(dims, f, va + r * (vb - va))
        dims.mirror2 = a.mirror2
        dims.mirror3 = a.mirror3
        return dims

    def _section_at_end(self, sec_name: str) -> SectionDims:
        prop_type = self._frame_prop_type(sec_name)
        if prop_type is None:
            return SectionDims(type_name="Unknown")
        return self._prismatic_dims(sec_name, prop_type)

    def _nonprismatic_segments(self, sec_name: str) -> list[tuple[str, str, float, int]]:
        """
        PropFrame.GetNonPrismatic → [(StartSec, EndSec, MyLength, MyType), ...].
        comtypes: (NumberItems, StartSec, EndSec, MyLength, MyType, EI33, EI22,
                   Color, Notes, GUID, ret).
        """
        try:
            out = self._sap_model.PropFrame.GetNonPrismatic(
                sec_name, 0, [], [], [], [], [], [], 0, "", "",
            )
        except Exception:
            return []
        if not isinstance(out, (tuple, list)) or len(out) < 5:
            return []
        if _safe_int(_com_ret(out)) != 0:
            return []
        n = _safe_int(out[0])
        starts = _as_list(out[1])
        ends = _as_list(out[2])
        lengths = _as_list(out[3])
        types = _as_list(out[4])
        n = min(n, len(starts), len(ends), len(lengths), len(types))
        return [
            (_safe_str(starts[i]), _safe_str(ends[i]),
             _safe_float(lengths[i]), _safe_int(types[i]))
            for i in range(n)
        ]

    def _point_xyz(self, point_name: str) -> tuple[float, float, float]:
        """Tọa độ Cartesian (x, y, z) — comtypes: (x, y, z, ret)."""
        ret = self._sap_model.PointObj.GetCoordCartesian(
            point_name, 0.0, 0.0, 0.0,
        )
        if isinstance(ret, (tuple, list)) and len(ret) >= 3:
            return _safe_float(ret[0]), _safe_float(ret[1]), _safe_float(ret[2])
        return 0.0, 0.0, 0.0

    # ── Thông số tiết diện từ API ─────────────────────────────

    def get_section_props_api(self, prop_name: str) -> SectionFromAPI:
        """
        Lấy thông số I-Section từ SAP2000 API.

        Returns
        -------
        SectionFromAPI
            Thông số tiết diện (mm). success=False nếu không phải I-Section.
        """
        sm = self._sap_model
        result = SectionFromAPI()

        try:
            ret = sm.PropFrame.GetTypeOAPI(prop_name, 0)
            prop_type = 0
            if isinstance(ret, (tuple, list)) and ret:
                prop_type = _safe_int(ret[0])
            elif isinstance(ret, (int, float)):
                prop_type = int(ret)

            if prop_type != 1:  # 1 = I-Section (VBA GetSectionPropsAtStation)
                return result

            out = sm.PropFrame.GetISection(
                prop_name, "", "", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
            )
            if not isinstance(out, (tuple, list)) or len(out) < 6:
                return result
            # VBA: FileName, MatProp, T3, T2, tf, tw, t2b, tfb
            t3 = _safe_float(out[2])
            t2 = _safe_float(out[3])
            tf_ = _safe_float(out[4])
            tw_ = _safe_float(out[5])
            result.htb = t3 * 1000.0
            result.bf = t2 * 1000.0
            result.tf = tf_ * 1000.0
            result.tw = tw_ * 1000.0
            result.success = True
        except Exception:
            pass

        return result

    # ── Thiết lập nguồn tải đầu ra ────────────────────────────

    def list_load_names(self, source_type: str) -> tuple[list[str], set[str]]:
        """
        Liệt kê tên nguồn tải theo loại, không đổi lựa chọn output.

        Returns
        -------
        (names, modal_names)
            names: mọi pattern/case/combo (hoặc combo thiết kế).
            modal_names: nguồn Modal / Buckling — không dùng cho thiết kế.
        """
        sm = self._sap_model
        if not sm:
            return [], set()

        names: list[str] = []
        modal_names: set[str] = set()
        self._design_combo_cache.clear()

        try:
            if source_type == LOAD_PATTERNS:
                ret = sm.LoadPatterns.GetNameList(0, [])
                names = self._extract_name_list(ret)
            elif source_type == LOAD_CASES:
                names, modal_names = self._list_cases()
            elif source_type == LOAD_COMBOS:
                names = self._combo_names()
                modal_names = {
                    n for n in names if self._combo_has_modal_or_buckling(n)
                }
            elif source_type == LOAD_DESIGN_COMBOS:
                names = self.list_design_combos()
            elif source_type == LOAD_CASES_AND_DESIGN:
                names, modal_names = self._list_cases()
                case_set = set(names)
                names = names + [
                    n for n in self.list_design_combos() if n not in case_set
                ]
        except Exception as e:
            self.last_error = f"list_load_names error: {e}\n{traceback.format_exc()}"
            return [], set()

        for name in names:
            if is_modal_load(name):
                modal_names.add(name)

        return names, modal_names

    def _list_cases(self) -> tuple[list[str], set[str]]:
        """Mọi Load Case + tập case Modal/Buckling."""
        ret = self._sap_model.LoadCases.GetNameList(0, [])
        names = self._extract_name_list(ret)
        modal = {
            n for n in names if is_modal_load(n) or self._is_modal_case_type(n)
        }
        return names, modal

    def _combo_names(self) -> list[str]:
        try:
            return self._extract_name_list(self._sap_model.RespCombo.GetNameList(0, []))
        except Exception:
            return []

    def _case_type(self, name: str) -> Optional[int]:
        """LoadCases.GetTypeOAPI → eLoadCaseType (cache). comtypes: (CaseType, SubType, ret)."""
        if name in self._case_type_cache:
            return self._case_type_cache[name]
        case_type = None
        try:
            out = self._sap_model.LoadCases.GetTypeOAPI(name, 0, 0)
            if isinstance(out, (tuple, list)) and out:
                if len(out) < 3 or _safe_int(_com_ret(out)) == 0:
                    case_type = _safe_int(out[0])
        except Exception:
            case_type = None
        self._case_type_cache[name] = case_type
        return case_type

    def _is_modal_case_type(self, name: str) -> bool:
        """True nếu case là Modal (3) hoặc Buckling (10) — Excel Reaction."""
        if not self._sap_model:
            return False
        return self._case_type(name) in (_LOAD_CASE_TYPE_MODAL, _LOAD_CASE_TYPE_BUCKLING)

    def _combo_has_modal_or_buckling(
        self, combo_name: str, _seen: Optional[set[str]] = None,
    ) -> bool:
        """
        Combo có chứa case Modal/Buckling (xét cả combo lồng) — Excel Reaction.
        comtypes: (NumberItems, CNameType, CName, SF, ret); CNameType 0 = case, 1 = combo.
        """
        seen = _seen if _seen is not None else set()
        if combo_name in seen:
            return False
        seen.add(combo_name)
        try:
            out = self._sap_model.RespCombo.GetCaseList(combo_name, 0, [], [], [])
        except Exception:
            return False
        if not isinstance(out, (tuple, list)) or len(out) < 3:
            return False
        kinds = _as_list(out[1])
        items = _as_list(out[2])
        for kind, item in zip(kinds, items):
            item = _safe_str(item)
            if _safe_int(kind) == 1:
                if self._combo_has_modal_or_buckling(item, seen):
                    return True
            elif is_modal_load(item) or self._is_modal_case_type(item):
                return True
        return False

    def setup_output_source(
        self,
        source_type: str,
        selected_names: Optional[list[str]] = None,
    ) -> list[str]:
        """
        Thiết lập nguồn tải cho output và trả về danh sách tên đã chọn.

        Parameters
        ----------
        source_type : str
            "1" Patterns, "2" Cases, "3" Combos (tất cả),
            "4" Design Combos, "5" Cases + Design Combos
        selected_names : list[str], optional
            Chỉ bật các tên này. None = mặc định (xem default_selected_loads).

        Returns
        -------
        list[str]
            Danh sách tên đã Set...SelectedForOutput.
        """
        sm = self._sap_model
        if not sm:
            return []

        self.clear_caches()
        all_names, modal_names = self.list_load_names(source_type)

        if selected_names is None:
            chosen = default_selected_loads(all_names, modal_names, source_type)
        else:
            allowed = set(all_names)
            chosen = [
                n for n in selected_names
                if n in allowed and n not in modal_names and not is_modal_load(n)
            ]

        try:
            sm.Results.Setup.DeselectAllCasesAndCombosForOutput()
        except Exception:
            pass

        try:
            combo_set = set(self._combo_names())
            for name in chosen:
                try:
                    if name in combo_set:
                        sm.Results.Setup.SetComboSelectedForOutput(name, True)
                    else:
                        sm.Results.Setup.SetCaseSelectedForOutput(name, True)
                except Exception:
                    pass
        except Exception as e:
            self.last_error = f"setup_output_source error: {e}\n{traceback.format_exc()}"

        return chosen

    def allowed_loads_for_frame(
        self,
        frame_name: str,
        source_type: str,
        chosen: set[str],
    ) -> set[str]:
        """
        Nguồn tải được xét cho 1 thanh (Excel InternalForce):
          - Design Combos: chỉ combo cường độ gán cho đúng thanh đó.
          - Cases + Design: case đã chọn + combo cường độ của thanh.
          - Loại khác: đúng danh sách đã chọn.
        """
        if source_type not in (LOAD_DESIGN_COMBOS, LOAD_CASES_AND_DESIGN):
            return set(chosen)
        member_combos = set(self.get_frame_design_combos(frame_name))
        if source_type == LOAD_DESIGN_COMBOS:
            return chosen & member_combos
        all_design = set(self.list_design_combos())
        return {
            n for n in chosen
            if n in member_combos or n not in all_design
        }

    def _extract_name_list(self, ret) -> list[str]:
        """Trích xuất danh sách tên từ GetNameList: (NumberNames, MyName, ret)."""
        if not isinstance(ret, (tuple, list)) or len(ret) < 2:
            return []
        names = _as_list(ret[1])
        try:
            n = int(ret[0]) if ret[0] is not None else len(names)
        except (TypeError, ValueError):
            n = len(names)
        if n > 0:
            names = names[:n]
        return [str(x) for x in names if x is not None and str(x)]

    # ── Lấy nội lực FrameForce ────────────────────────────────

    def get_frame_forces(self, frame_name: str) -> list[FrameForceRow]:
        """
        Lấy toàn bộ kết quả nội lực FrameForce cho 1 Frame.

        Returns
        -------
        list[FrameForceRow]
            Danh sách nội lực tại mỗi station / load case.
        """
        sm = self._sap_model
        rows = []

        try:
            out = sm.Results.FrameForce(
                frame_name, 0,
                0, [], [], [], [], [], [], [],
                [], [], [], [], [], [],
            )
        except TypeError:
            try:
                out = sm.Results.FrameForce(frame_name, 0)
            except Exception as e:
                self.last_error = f"FrameForce error: {e}\n{traceback.format_exc()}"
                return []
        except Exception as e:
            self.last_error = f"FrameForce error: {e}\n{traceback.format_exc()}"
            return []

        if not isinstance(out, (tuple, list)) or len(out) < 14:
            self.last_error = (
                f"FrameForce: ket qua khong du truong "
                f"(len={len(out) if isinstance(out, (tuple, list)) else type(out)})"
            )
            return []

        try:
            n = _safe_int(out[0])
            if n <= 0:
                return []

            # (NumberResults, Obj, ObjSta, Elm, ElmSta, LoadCase, StepType,
            #  StepNum, P, V2, V3, T, M2, M3, ret)
            obj_sta = _as_list(out[2])
            load_case = _as_list(out[5])
            p_arr = _as_list(out[8])
            v2_arr = _as_list(out[9])
            v3_arr = _as_list(out[10])
            t_arr = _as_list(out[11])
            m2_arr = _as_list(out[12])
            m3_arr = _as_list(out[13])

            for j in range(n):
                rows.append(FrameForceRow(
                    obj_station=_safe_float(obj_sta[j] if j < len(obj_sta) else 0),
                    load_case=_safe_str(load_case[j] if j < len(load_case) else ""),
                    P=_safe_float(p_arr[j] if j < len(p_arr) else 0),
                    V2=_safe_float(v2_arr[j] if j < len(v2_arr) else 0),
                    V3=_safe_float(v3_arr[j] if j < len(v3_arr) else 0),
                    T=_safe_float(t_arr[j] if j < len(t_arr) else 0),
                    M2=_safe_float(m2_arr[j] if j < len(m2_arr) else 0),
                    M3=_safe_float(m3_arr[j] if j < len(m3_arr) else 0),
                ))

        except Exception as e:
            self.last_error = f"Parse FrameForce error: {e}\n{traceback.format_exc()}"

        return rows

    # ── Phản lực nút (Excel Reaction) ─────────────────────────

    def get_joint_reactions(
        self,
        point_names: Optional[list[str]] = None,
    ) -> list[JointReactRow]:
        """
        Phản lực nút (Results.JointReact).

        point_names = None → các nút đang chọn (SelectionElm, 1 lần gọi như Excel).
        Có danh sách → gọi từng nút (ObjectElm); nút không có gối trả về rỗng.
        """
        if point_names is None:
            return self._joint_react("", _ITEM_SELECTION)
        rows: list[JointReactRow] = []
        for name in point_names:
            rows.extend(self._joint_react(name, _ITEM_OBJECT))
        return rows

    def _joint_react(self, name: str, item_type: int) -> list[JointReactRow]:
        """
        comtypes: (NumberResults, Obj, Elm, LoadCase, StepType, StepNum,
                   F1, F2, F3, M1, M2, M3, ret).
        """
        try:
            out = self._sap_model.Results.JointReact(
                name, item_type, 0, [], [], [], [], [], [], [], [], [], [], [],
            )
        except Exception as e:
            self.last_error = f"JointReact error: {e}\n{traceback.format_exc()}"
            return []
        if not isinstance(out, (tuple, list)) or len(out) < 12:
            return []
        n = _safe_int(out[0])
        if n <= 0:
            return []

        cols = [_as_list(out[i]) for i in range(1, 12)]
        obj, _elm, case, step_type, step_num, f1, f2, f3, m1, m2, m3 = cols

        def at(arr, j, conv):
            return conv(arr[j] if j < len(arr) else None)

        rows: list[JointReactRow] = []
        for j in range(n):
            rows.append(JointReactRow(
                joint=at(obj, j, _safe_str),
                load_case=at(case, j, _safe_str),
                step_type=at(step_type, j, _safe_str),
                step_num=at(step_num, j, _safe_float),
                F1=at(f1, j, _safe_float),
                F2=at(f2, j, _safe_float),
                F3=at(f3, j, _safe_float),
                M1=at(m1, j, _safe_float),
                M2=at(m2, j, _safe_float),
                M3=at(m3, j, _safe_float),
            ))
        return rows
