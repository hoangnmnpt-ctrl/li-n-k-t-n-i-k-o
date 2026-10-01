"""
gui_main.py
===========
Giao diện chính mini-tool "LẤY NỘI LỰC THIẾT KẾ – SAP2000".

Mini-tool gọn nhẹ cạnh SAP2000:
  - Nguồn tải + vị trí theo Excel "1. LẤY NỘI LỰC MAX_ANH HƯNG GỬI":
      + Design Combos (mặc định) / Load Cases / Cases + Design / Combos (tất cả)
      + Nút Đầu / Nút Cuối (mặt gối, trừ end offset) / Cả hai / Toàn thanh
  - Tab 1: Nút Đầu / Cuối (Chi tiết các thanh):
      + 9 cực trị (thêm Max T), cột Station, T và kích thước tiết diện (m)
      + Ô cực trị tô theo dấu như Excel
  - Tab 2: Tóm Tắt Cực Trị (giữ thứ tự & lựa chọn để dán RAM Connection):
      + CHỈ 1 BẢNG — Cả hai = gộp Nút Đầu + Nút Cuối, không cần chuyển đầu
      + ĐÃ LOẠI BỎ cột "Thanh"; cột "Lấy từ", "Tổ hợp" chỉ để xem, không bị copy
      + THAY ĐỔI THỨ TỰ HÀNG CỰC KỲ LINH HOẠT:
        * Phím tắt Alt+Up / Alt+Down
        * Menu chuột phải: Chuyển hàng lên/xuống
        * Dropdown chọn nhanh thứ tự chuẩn: M➔V➔N, M➔N➔V, N➔M➔V, N➔V➔M
      + Dropdown thứ tự cột lực; Copy 4 cột lực
      + Cột Axial LUÔN đổi dấu (dùng làm phản lực), giữ tên & vị trí dòng
      + Nguồn theo tab đang xem khi bấm: thanh, hoặc phản lực
        (V2 = F1, V3 = F2, Axial = F3 gốc – nén dương, M33 = M2, M22 = M1)
  - Tab 3: Phản Lực (Excel Reaction): Max (+) / Max (−) cho F1..M3, gộp mọi nút
    hoặc từng nút; nút đang chọn, hoặc nút gối của các thanh đang chọn.
    F3 (lực dọc) LUÔN đổi dấu. Dùng chung nguồn tải, tô màu, copy, xuất Excel.
  - Không có thanh chuyển tab: 3 nút hành động kiêm chuyển tab (đã có kết quả
    thì bấm lần đầu chỉ chuyển tab, bấm lần nữa mới xuất lại).
  - Tính năng mở rộng (Nhiều Vị Trí & Torsional Check) ẩn gọn, có thể bật khi cần.

LƯU Ý: Tất cả gọi COM đều chạy trên main thread (SAP2000 COM = STA).
"""

from __future__ import annotations

import os
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

import customtkinter as ctk

from core_engine import (
    NODE_BOTH,
    NODE_END,
    NODE_ENVELOPE,
    NODE_START,
    ReactionRow,
    ResultRow,
    ResultRowMulti,
    SummaryRow,
    apply_force_values,
    apply_reaction_values,
    filter_reactions,
    find_m3_min_row,
    flip_reaction_axial,
    forces_at_row_position,
    get_unique_locations,
    process_frame_multi_station,
    process_frame_node_extremes,
    process_reactions,
    reaction_choices,
    summarize_global_extremes,
    summarize_reaction_extremes,
)
from gui_widgets import DataTable, LoadSourcePicker, StatusBar
from sap2000_connector import (
    LOAD_CASES,
    LOAD_CASES_AND_DESIGN,
    LOAD_COMBOS,
    LOAD_DESIGN_COMBOS,
    SAP2000Connector,
    default_selected_loads,
    is_lrfd_load,
)


# ── Cấu hình Mini-Tool ───────────────────────────────────────

APP_TITLE = "LẤY NỘI LỰC THIẾT KẾ – SAP2000"
APP_SIZE = "800x580"

# Nguồn tải (Excel InternalForce: Cases / Design Combos / cả hai) + Combos tất cả
SOURCE_MENU = {
    "Design Combos": LOAD_DESIGN_COMBOS,
    "Load Cases": LOAD_CASES,
    "Cases + Design": LOAD_CASES_AND_DESIGN,
    "Combos (tất cả)": LOAD_COMBOS,
}
SOURCE_HINTS = {
    LOAD_DESIGN_COMBOS: (
        "Combo thiết kế cường độ (Design > Select Design Combos). Mỗi thanh chỉ "
        "xét combo của đúng thủ tục thiết kế của nó. Đã bỏ Modal."
    ),
    LOAD_CASES: "Mọi Load Case, đã bỏ Modal và Buckling.",
    LOAD_CASES_AND_DESIGN: (
        "Load Case (bỏ Modal/Buckling) + combo thiết kế cường độ của từng thanh."
    ),
    LOAD_COMBOS: (
        "Mọi Combo, đã bỏ combo chứa Modal/Buckling. Mặc định chỉ LRFD — "
        "tick thêm nếu cần."
    ),
}

# Nguồn bảng tóm tắt
SUMMARY_SRC_FRAME = "frame"
SUMMARY_SRC_REACTION = "reaction"

# Phạm vi của bảng tóm tắt theo lựa chọn vị trí lúc xuất
SUMMARY_SCOPE_TEXT = {
    NODE_START: "Nút Đầu",
    NODE_END: "Nút Cuối",
    NODE_BOTH: "Cả 2 đầu (gộp)",
    NODE_ENVELOPE: "Toàn thanh (Envelope)",
}

# Tên các Tab (Dùng text chuẩn Segoe UI, không dùng emoji để mở app siêu tốc)
TAB_NODE = "Nút Đầu / Cuối"
TAB_SUMMARY = "Tóm Tắt Cực Trị"
TAB_REACTION = "Phản Lực"
TAB_MULTI = "Nhiều Vị Trí"
TAB_TORSION = "Torsional Check"

# Phản lực (Excel Reaction): kiểu lọc — gộp mọi nút (mặc định) / từng nút
REACTION_VIEW_MERGED = "Gộp mọi nút"
REACTION_VIEW_BY_JOINT = "Từng nút"
COLUMNS_REACTION = [
    "Nút", "Cực Trị", "Nguồn Tải (Combo/Case)", "Step",
    "F1 (kN)", "F2 (kN)", "F3 (kN)", "M1 (kNm)", "M2 (kNm)", "M3 (kNm)",
]
REACTION_COL_WIDTHS = {
    "Nút": 70, "Cực Trị": 130, "Nguồn Tải (Combo/Case)": 230, "Step": 55,
}

# Thứ tự cột lực theo Excel: P, M3, M2, T, V2, V3 + kích thước tiết diện (m)
COLUMNS_NODE = [
    "Tên Thanh", "Tiết Diện", "Dài (m)", "Vị Trí Nút",
    "Cực Trị", "Nguồn Tải (Combo/Case)", "Station (m)",
    "P (kN)", "M3 (kNm)", "M2 (kNm)", "T (kNm)", "V2 (kN)", "V3 (kN)",
    "Loại TD", "t3 (m)", "t2 (m)", "tf (m)", "tw (m)", "t2b (m)", "tfb (m)",
    "dis (m)", "r (m)", "Mirror",
]
NODE_COL_WIDTHS = {
    "Nguồn Tải (Combo/Case)": 150, "Station (m)": 80, "Loại TD": 150,
    "t3 (m)": 70, "t2 (m)": 70, "tf (m)": 70, "tw (m)": 70, "t2b (m)": 70,
    "tfb (m)": 70, "dis (m)": 70, "r (m)": 70, "Mirror": 70,
}

COLUMNS_MULTI = [
    "Tên Thanh", "Tiết Diện", "htb (mm)", "tw (mm)", "bf (mm)", "tf (mm)",
    "Dài (m)", "Vị Trí", "Cực Trị", "Nguồn Tải (Combo/Case)",
    "P (kN)", "V2 (kN)", "V3 (kN)", "M2 (kNm)", "M3 (kNm)",
]

# Thứ tự mặc định chuẩn: V2, Axial, M33, M22, V3 (loại bỏ Thanh)
COLUMNS_SUMMARY = [
    "STT", "Điều kiện", "V2 (kN)", "Axial (kN)", "M33 (kNm)", "M22 (kNm)", "V3 (kN)",
]
# Cột chỉ để xem: luôn ở cuối, không bị copy (không ảnh hưởng dán RAM Connection)
SUMMARY_INFO_COLUMNS = ["Lấy từ", "Tổ hợp (Combo/Case)"]

# Các mẫu thứ tự hàng điều kiện phổ biến
ROW_ORDER_PRESETS = {
    "M ➔ V ➔ N": ["Mmax", "Mmin", "V2max", "Nmax", "Nmin", "V3max"],
    "M ➔ N ➔ V": ["Mmax", "Mmin", "Nmax", "Nmin", "V2max", "V3max"],
    "N ➔ M ➔ V": ["Nmax", "Nmin", "Mmax", "Mmin", "V2max", "V3max"],
    "N ➔ V ➔ M": ["Nmax", "Nmin", "V2max", "Mmax", "Mmin", "V3max"],
}

# Các mẫu thứ tự 5 cột lực phổ biến (Mặc định: V2 ➔ Axial ➔ M33 ➔ M22 ➔ V3)
FORCE_COL_ORDER_PRESETS = {
    "V2 ➔ N ➔ M ➔ V3": ["STT", "Điều kiện", "V2 (kN)", "Axial (kN)", "M33 (kNm)", "M22 (kNm)", "V3 (kN)"],
    "N ➔ V2 ➔ M ➔ V3": ["STT", "Điều kiện", "Axial (kN)", "V2 (kN)", "M33 (kNm)", "M22 (kNm)", "V3 (kN)"],
    "V2 ➔ V3 ➔ N ➔ M": ["STT", "Điều kiện", "V2 (kN)", "V3 (kN)", "Axial (kN)", "M33 (kNm)", "M22 (kNm)"],
    "M ➔ N ➔ V2 ➔ V3": ["STT", "Điều kiện", "M33 (kNm)", "M22 (kNm)", "Axial (kN)", "V2 (kN)", "V3 (kN)"],
}

# Nhãn dropdown → preset (dùng chung khi chọn và khi tạo lại bảng tóm tắt)
ROW_ORDER_MENU = {
    "Hàng: M-V-N": ROW_ORDER_PRESETS["M ➔ V ➔ N"],
    "Hàng: M-N-V": ROW_ORDER_PRESETS["M ➔ N ➔ V"],
    "Hàng: N-M-V": ROW_ORDER_PRESETS["N ➔ M ➔ V"],
    "Hàng: N-V-M": ROW_ORDER_PRESETS["N ➔ V ➔ M"],
}
COL_ORDER_MENU = {
    "Cột: V2-N-M-V3": FORCE_COL_ORDER_PRESETS["V2 ➔ N ➔ M ➔ V3"],
    "Cột: N-V2-M-V3": FORCE_COL_ORDER_PRESETS["N ➔ V2 ➔ M ➔ V3"],
    "Cột: V2-V3-N-M": FORCE_COL_ORDER_PRESETS["V2 ➔ V3 ➔ N ➔ M"],
    "Cột: M-N-V2-V3": FORCE_COL_ORDER_PRESETS["M ➔ N ➔ V2 ➔ V3"],
}


def reaction_row_values(r: ReactionRow) -> tuple:
    """1 dòng ReactionRow → tuple theo COLUMNS_REACTION."""
    return (
        r.joint, r.criteria, r.load_case, r.step_text,
        r.F1, r.F2, r.F3, r.M1, r.M2, r.M3,
    )


def _dim_or_na(value: float):
    """Excel: kích thước = 0 → ghi 'N/A'."""
    return value if value > 0 else "N/A"


def node_row_values(r: ResultRow) -> tuple:
    """1 dòng ResultRow → tuple theo COLUMNS_NODE."""
    return (
        r.frame_name, r.section_name, r.length, r.node_label,
        r.extreme_type, r.load_case, round(r.obj_station, 3),
        r.P, r.M3, r.M2, r.T, r.V2, r.V3,
        r.sec_type,
        _dim_or_na(r.t3), _dim_or_na(r.t2), _dim_or_na(r.tf), _dim_or_na(r.tw),
        _dim_or_na(r.t2b), _dim_or_na(r.tfb), _dim_or_na(r.dis), _dim_or_na(r.fillet),
        r.mirror,
    )


class App(ctk.CTk):
    """Cửa sổ chính của mini-tool."""

    def __init__(self):
        super().__init__()

        self.title(APP_TITLE)
        self.geometry(APP_SIZE)
        self.minsize(680, 480)
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        # ── State ────────────────────────────────────────────
        self.connector = SAP2000Connector()
        self.results_node: list[ResultRow] = []
        self.results_multi: list[ResultRowMulti] = []
        self._cond_pos_idx = 0  # 0: sau STT, 1: cuối bảng, 2: đầu bảng
        self._all_load_names: list[str] = []
        self._modal_load_names: set[str] = set()
        self._selected_load_names: Optional[list[str]] = None
        self._force_cache: dict = {}
        self._info_cache: dict = {}
        self._node_opt_run = NODE_BOTH      # vị trí đã dùng ở lần xuất gần nhất
        self.summary_rows: list[SummaryRow] = []
        self._summary_source = SUMMARY_SRC_FRAME   # nguồn bảng tóm tắt: thanh / phản lực
        self._summary_scope = ""
        self._load_picker = None
        # Phản lực
        self._reactions: list = []          # JointReactRow đã lọc (để chọn lại nguồn tải)
        self.reaction_merged: list[ReactionRow] = []
        self.reaction_by_joint: list[ReactionRow] = []

        # ── Build UI ─────────────────────────────────────────
        self._build_ui()

    # ══════════════════════════════════════════════════════════
    # XÂY DỰNG GIAO DIỆN MINI-TOOL
    # ══════════════════════════════════════════════════════════

    def _build_ui(self):
        self.status_bar = StatusBar(self)
        self.status_bar.pack(side="bottom", fill="x")

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=6, pady=(3, 0))

        top_panel = ctk.CTkFrame(main)
        top_panel.pack(fill="x", pady=(0, 2))

        self._build_connection_panel(top_panel)
        self._build_options_panel(top_panel)
        self._build_action_buttons(top_panel)

        # Khung nội dung chứa bảng (loại bỏ hoàn toàn khoảng trống xám)
        self.content_container = ctk.CTkFrame(main, fg_color="transparent")
        self.content_container.pack(fill="both", expand=True, pady=0)

        self.frame_node = ctk.CTkFrame(self.content_container, fg_color="transparent")
        self.frame_summary = ctk.CTkFrame(self.content_container, fg_color="transparent")
        self.frame_reaction = ctk.CTkFrame(self.content_container, fg_color="transparent")
        self._tab_frames = {
            TAB_NODE: self.frame_node,
            TAB_SUMMARY: self.frame_summary,
            TAB_REACTION: self.frame_reaction,
        }

        self._build_tab_node(self.frame_node)
        self._build_tab_summary(self.frame_summary)
        self._build_tab_reaction(self.frame_reaction)

        # Mặc định hiển thị tab Nút Đầu / Cuối
        self._switch_tab(TAB_NODE)

        # Khả năng tương thích ngược
        class TabviewCompat:
            def __init__(self, app): self._app = app
            def get(self): return self._app._current_tab_name
            def set(self, name): self._app._switch_tab(name)
        self.tabview = TabviewCompat(self)

        self.tab_multi = None
        self.tab_torsion = None

    # ── Panel kết nối SAP2000 ─────────────────────────────────

    def _build_connection_panel(self, parent):
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", padx=6, pady=(4, 2))

        ctk.CTkLabel(
            frame, text="SAP2000", font=("Segoe UI", 13, "bold"),
        ).pack(side="left", padx=(8, 4))

        self.btn_connect = ctk.CTkButton(
            frame, text="Kết nối", width=80, height=28, font=("Segoe UI", 12),
            command=self._on_connect,
        )
        self.btn_connect.pack(side="left", padx=4)

        self.lbl_status = ctk.CTkLabel(
            frame, text="Chưa kết nối", text_color="gray", font=("Segoe UI", 12, "bold"),
        )
        self.lbl_status.pack(side="left", padx=6)

        self.lbl_frames = ctk.CTkLabel(frame, text="", font=("Segoe UI", 12))
        self.lbl_frames.pack(side="left", padx=6)

        self.var_hide_v3 = ctk.BooleanVar(value=False)

    # ── Panel tùy chọn ────────────────────────────────────────

    def _build_options_panel(self, parent):
        self.frame_options = ctk.CTkFrame(parent)
        self.frame_options.pack(fill="x", padx=6, pady=2)

        ctk.CTkLabel(
            self.frame_options, text="Nguồn tải:", font=("Segoe UI", 12, "bold"),
        ).grid(row=0, column=0, padx=(8, 4), pady=2, sticky="w")

        # Excel InternalForce — Menu 2: Load Case/Combo scope (mặc định Design Combos)
        self.var_source = ctk.StringVar(value=LOAD_DESIGN_COMBOS)
        self.opt_source = ctk.CTkOptionMenu(
            self.frame_options,
            values=list(SOURCE_MENU),
            command=self._on_source_menu,
            width=150, height=26, font=("Segoe UI", 12),
        )
        self.opt_source.set("Design Combos")
        self.opt_source.grid(row=0, column=1, columnspan=2, padx=6, pady=2, sticky="w")

        self.btn_pick_loads = ctk.CTkButton(
            self.frame_options,
            text="Nguồn tải ▾",
            width=118, height=26, font=("Segoe UI", 11),
            fg_color="#0F766E", hover_color="#115E59",
            command=self._open_load_source_picker,
        )
        self.btn_pick_loads.grid(row=0, column=3, columnspan=2, padx=(8, 4), pady=2, sticky="w")

        ctk.CTkLabel(
            self.frame_options, text="Vị trí:", font=("Segoe UI", 12, "bold"),
        ).grid(row=1, column=0, padx=(8, 4), pady=2, sticky="w")

        # Excel InternalForce — Menu 3: Station (I-End / J-End / Envelope)
        self.var_node = ctk.StringVar(value=NODE_BOTH)
        nodes = [
            ("Nút Đầu", NODE_START),
            ("Nút Cuối", NODE_END),
            ("Cả hai", NODE_BOTH),
            ("Toàn thanh", NODE_ENVELOPE),
        ]
        for i, (text, val) in enumerate(nodes):
            ctk.CTkRadioButton(
                self.frame_options, text=text, variable=self.var_node, value=val,
                font=("Segoe UI", 12), width=20,
            ).grid(row=1, column=i + 1, padx=6, pady=2, sticky="w")

        self.frame_options.grid_columnconfigure(5, weight=1)

    # ── Nút hành động ────────────────────────────────────────

    def _build_action_buttons(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=6, pady=(2, 2))

        self.btn_run_node = ctk.CTkButton(
            frame,
            text="Xuất Nút Đầu / Cuối",
            width=165, height=32,
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            font=("Segoe UI", 12, "bold"),
            command=self._on_node_button,
        )
        self.btn_run_node.pack(side="left", padx=3)

        self.btn_summary = ctk.CTkButton(
            frame,
            text="Tóm Tắt Cực Trị",
            width=145, height=32,
            fg_color="#059669",
            hover_color="#047857",
            font=("Segoe UI", 12, "bold"),
            command=self._on_summary,
        )
        self.btn_summary.pack(side="left", padx=3)

        self.btn_run_reaction = ctk.CTkButton(
            frame,
            text="Xuất Phản Lực",
            width=135, height=32,
            fg_color="#B45309",
            hover_color="#92400E",
            font=("Segoe UI", 12, "bold"),
            command=self._on_reaction_button,
        )
        self.btn_run_reaction.pack(side="left", padx=3)

        # Không còn thanh chuyển tab: 3 nút hành động kiêm chuyển tab,
        # nút của tab đang xem có viền đậm.
        self._tab_buttons = {
            TAB_NODE: self.btn_run_node,
            TAB_SUMMARY: self.btn_summary,
            TAB_REACTION: self.btn_run_reaction,
        }

        # Không hiển thị thanh progress bar trên UI
        self.progress = type("DummyProgress", (), {"set": lambda self, val: None})()

    def _switch_tab(self, tab_name: str):
        if tab_name not in self._tab_frames:
            return
        for name, frame in self._tab_frames.items():
            if name != tab_name:
                frame.pack_forget()
        self._tab_frames[tab_name].pack(fill="both", expand=True)
        self._current_tab_name = tab_name
        for name, btn in self._tab_buttons.items():
            btn.configure(
                border_width=3 if name == tab_name else 0,
                border_color="#0F172A",
            )

    def _on_node_button(self):
        """Đang xem tab khác mà đã có kết quả → chỉ chuyển tab; đang ở tab này → xuất."""
        if self.results_node and self._current_tab_name != TAB_NODE:
            self._switch_tab(TAB_NODE)
            self.status_bar.set_text(
                "Đang xem kết quả Nút Đầu / Cuối đã xuất. Bấm lại để xuất mới."
            )
            return
        self._on_run_node()

    def _on_reaction_button(self):
        """Đang xem tab khác mà đã có kết quả → chỉ chuyển tab; đang ở tab này → xuất."""
        if self._reactions and self._current_tab_name != TAB_REACTION:
            self._switch_tab(TAB_REACTION)
            self.status_bar.set_text(
                "Đang xem kết quả Phản Lực đã xuất. Bấm lại để xuất mới."
            )
            return
        self._on_run_reaction()

    # ── Tab Nút Đầu/Cuối (Chi tiết) ─────────────────────────

    def _build_tab_node(self, parent):
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(0, 2))

        ctk.CTkButton(
            btn_frame, text="Copy 6 cột lực", width=125, height=28, font=("Segoe UI", 12),
            fg_color="#0D9488", hover_color="#0F766E",
            command=lambda: self.table_node.copy_force_columns(),
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_frame, text="Xuất Excel", width=95, height=28, font=("Segoe UI", 12),
            command=self._export_node_excel,
        ).pack(side="left", padx=2)

        self.lbl_node_count = ctk.CTkLabel(btn_frame, text="", font=("Segoe UI", 12, "bold"))
        self.lbl_node_count.pack(side="right", padx=6)

        self.table_node = DataTable(
            parent, COLUMNS_NODE, status_callback=self.status_bar.set_text,
            col_widths=NODE_COL_WIDTHS,
        )
        self.table_node.on_load_source_click = self._on_node_load_cell_click
        self.table_node.pack(fill="both", expand=True)

    # ── Tab Tóm Tắt Cực Trị (Đổi Thứ Tự Hàng & Cột) ─────────

    def _build_tab_summary(self, parent):
        top_bar = ctk.CTkFrame(parent, fg_color="transparent")
        top_bar.pack(fill="x", pady=(0, 3))

        # 1. Phạm vi bảng (1 bảng duy nhất — Cả hai = gộp Nút Đầu + Nút Cuối)
        self.lbl_summary_scope = ctk.CTkLabel(
            top_bar, text="Phạm vi: —", width=150, anchor="w",
            font=("Segoe UI", 12, "bold"), text_color="#1F4E79",
        )
        self.lbl_summary_scope.pack(side="left", padx=(4, 2))

        # 2. Dropdown chọn thứ tự hàng
        self.opt_row_order = ctk.CTkOptionMenu(
            top_bar,
            values=list(ROW_ORDER_MENU),
            command=self._on_select_row_order,
            width=110, height=30, font=("Segoe UI", 11),
        )
        self.opt_row_order.pack(side="left", padx=2)

        # 3. Dropdown chọn thứ tự 5 cột lực (Mặc định: V2, Axial, M33, M22, V3)
        self.opt_col_order = ctk.CTkOptionMenu(
            top_bar,
            values=list(COL_ORDER_MENU),
            command=self._on_select_col_order,
            width=125, height=30, font=("Segoe UI", 11),
        )
        self.opt_col_order.pack(side="left", padx=2)
        self.opt_col_order.set("Cột: V2-N-M-V3")

        # 4. Nút Xuất Excel
        ctk.CTkButton(
            top_bar, text="Xuất Excel", width=95, height=30, font=("Segoe UI", 12),
            command=self._export_summary_excel,
        ).pack(side="right", padx=2)

        # 5. Nút Copy 4 cột lực
        ctk.CTkButton(
            top_bar, text="Copy 4 cột lực", width=115, height=30, font=("Segoe UI", 12, "bold"),
            fg_color="#0D9488", hover_color="#0F766E",
            command=self._copy_current_summary_forces,
        ).pack(side="right", padx=2)

        # Khung chứa bảng
        self.summary_container = ctk.CTkFrame(parent, fg_color="transparent")
        self.summary_container.pack(fill="both", expand=True)

        self.table_sum = DataTable(
            self.summary_container, COLUMNS_SUMMARY + SUMMARY_INFO_COLUMNS,
            status_callback=self.status_bar.set_text,
            no_copy_columns=SUMMARY_INFO_COLUMNS,
            col_widths={"Lấy từ": 120, "Tổ hợp (Combo/Case)": 260},
        )
        self.table_sum.pack(fill="both", expand=True)

    def _get_active_summary_table(self) -> DataTable:
        """Bảng tóm tắt (chỉ còn 1 bảng)."""
        return self.table_sum

    def _on_select_row_order(self, selected_order_name: str):
        """Áp dụng thứ tự hàng theo preset đã chọn."""
        order = ROW_ORDER_MENU.get(selected_order_name, ROW_ORDER_PRESETS.get(selected_order_name))
        if order:
            self.table_sum.reorder_by_condition_names(order)
            self.status_bar.set_text(f"Đã đổi thứ tự hàng: [{selected_order_name}]")

    def _on_select_col_order(self, selected_col_name: str):
        """Áp dụng thứ tự 5 cột lực theo preset đã chọn."""
        order = COL_ORDER_MENU.get(selected_col_name)
        if order:
            self.table_sum.set_display_columns(order)
            self.status_bar.set_text(f"Đã đổi thứ tự cột: [{selected_col_name}]. Bấm 'Copy 4 cột lực' sẽ lấy đúng thứ tự này!")

    def _toggle_hide_v3(self):
        """Ẩn hoặc hiện dòng V3max (để bảng chỉ còn 5 hàng chính)."""
        hide = self.var_hide_v3.get()
        self.table_sum.set_hide_condition("V3max", hide)
        msg = "Đã ẩn dòng V3max (bảng còn đúng 5 hàng cực trị chính)." if hide else "Đã hiện lại dòng V3max."
        self.status_bar.set_text(msg)

    def _toggle_condition_column_pos(self):
        """Xoay vòng vị trí cột 'Điều kiện': Sau STT ➔ Cuối bảng ➔ Đầu bảng."""
        self._cond_pos_idx = (self._cond_pos_idx + 1) % 3
        modes = [
            ("after_stt", "Sau STT", "STT | Điều kiện | V2..M22"),
            ("end", "Cuối bảng", "STT | V2..M22 | Điều kiện (5 cột lực liền nhau)"),
            ("start", "Đầu bảng", "Điều kiện | STT | V2..M22"),
        ]
        target_pos, label_text, desc = modes[self._cond_pos_idx]

        self.table_sum.move_column("Điều kiện", target_pos)

        if hasattr(self, "btn_toggle_cond"):
            self.btn_toggle_cond.configure(text=f"⇄ {label_text}")
        self.status_bar.set_text(f"Đã đổi vị trí cột Điều kiện: [{label_text}] ({desc})")

    def _copy_current_summary_forces(self):
        table = self._get_active_summary_table()
        table.copy_force_columns(max_cols=4)

    def _copy_current_summary_all(self):
        table = self._get_active_summary_table()
        table.copy_all(include_headers=False)

    # ── Tab Phản Lực (Excel Reaction) ────────────────────────

    def _build_tab_reaction(self, parent):
        top_bar = ctk.CTkFrame(parent, fg_color="transparent")
        top_bar.pack(fill="x", pady=(0, 3))

        # Excel: kiểu lọc — tính sẵn cả 2, chuyển xem ngay không phải xuất lại
        self.seg_reaction_view = ctk.CTkSegmentedButton(
            top_bar,
            values=[REACTION_VIEW_MERGED, REACTION_VIEW_BY_JOINT],
            command=self._on_reaction_view,
            width=190, height=30,
            font=("Segoe UI", 12, "bold"),
        )
        self.seg_reaction_view.pack(side="left", padx=2)
        self.seg_reaction_view.set(REACTION_VIEW_MERGED)

        ctk.CTkButton(
            top_bar, text="Copy 6 cột lực", width=125, height=30, font=("Segoe UI", 12),
            fg_color="#0D9488", hover_color="#0F766E",
            command=lambda: self.table_reaction.copy_force_columns(),
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            top_bar, text="Xuất Excel", width=95, height=30, font=("Segoe UI", 12),
            command=self._export_reaction_excel,
        ).pack(side="left", padx=2)

        self.lbl_reaction_count = ctk.CTkLabel(top_bar, text="", font=("Segoe UI", 12, "bold"))
        self.lbl_reaction_count.pack(side="right", padx=6)

        self.table_reaction = DataTable(
            parent, COLUMNS_REACTION, status_callback=self.status_bar.set_text,
            col_widths=REACTION_COL_WIDTHS,
        )
        self.table_reaction.on_load_source_click = self._on_reaction_load_cell_click
        self.table_reaction.pack(fill="both", expand=True)

    def _current_reaction_rows(self) -> list[ReactionRow]:
        if self.seg_reaction_view.get() == REACTION_VIEW_BY_JOINT:
            return self.reaction_by_joint
        return self.reaction_merged

    def _on_reaction_view(self, _view: str = ""):
        self._show_reaction_rows()
        n_joint = len({r.joint for r in self.reaction_by_joint})
        self.status_bar.set_text(
            f"Phản lực — {self.seg_reaction_view.get()} "
            f"({len(self._current_reaction_rows())} dòng, {n_joint} nút có phản lực)."
        )

    def _show_reaction_rows(self):
        rows = self._current_reaction_rows()
        self.table_reaction.set_data(
            [reaction_row_values(r) for r in rows], tag_column_idx=1,
        )
        self.lbl_reaction_count.configure(text=f"{len(rows)} dòng")

    # ── Tab Nhiều Vị Trí (Mở rộng) ───────────────────────────

    def _build_tab_multi(self, parent):
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(0, 2))

        ctk.CTkButton(
            btn_frame, text="💾 Xuất Excel", width=100, height=26, font=("", 11),
            command=self._export_multi_excel,
        ).pack(side="left", padx=2)

        self.table_multi = DataTable(
            parent, COLUMNS_MULTI, status_callback=self.status_bar.set_text
        )

        ctk.CTkButton(
            btn_frame, text="📋 Copy tất cả", width=100, height=26, font=("", 11),
            command=lambda: self.table_multi.copy_all(include_headers=True),
        ).pack(side="left", padx=2)

        self.lbl_multi_count = ctk.CTkLabel(btn_frame, text="", font=("", 11, "bold"))
        self.lbl_multi_count.pack(side="right", padx=6)

        self.table_multi.pack(fill="both", expand=True)

    # ── Tab Torsional Check (Mở rộng) ─────────────────────────

    def _build_tab_torsion(self, parent):
        top = ctk.CTkFrame(parent)
        top.pack(fill="x", padx=4, pady=4)

        ctk.CTkLabel(
            top, text="Chọn vị trí:", font=("", 11, "bold"),
        ).pack(side="left", padx=4)

        self.combo_location = ctk.CTkComboBox(
            top, values=["(chưa có dữ liệu)"], width=220, height=26,
            command=self._on_location_changed,
        )
        self.combo_location.pack(side="left", padx=4)

        self.lbl_m3_min = ctk.CTkLabel(
            top, text="M3 MIN = —", font=("", 12, "bold"),
            text_color="#DC2626",
        )
        self.lbl_m3_min.pack(side="left", padx=12)

        self.table_torsion = DataTable(parent, COLUMNS_MULTI)
        self.table_torsion.pack(fill="both", expand=True, padx=4, pady=4)

    # ══════════════════════════════════════════════════════════
    # XỬ LÝ SỰ KIỆN SAP2000
    # ══════════════════════════════════════════════════════════

    def _refresh_frames(self) -> list[str]:
        frames = self.connector.get_selected_frames()
        n = len(frames)
        preview = ""
        if n > 0:
            shown = ", ".join(frames[:3])
            if n > 3:
                shown += ", ..."
            preview = f" ({shown})"
        self.lbl_frames.configure(text=f"{n} thanh{preview}")
        return frames

    def _warn_no_frames(self):
        debug_err = self.connector.last_error
        extra = self.connector.describe_selection()
        hint = ""
        if extra:
            hint = f"\nĐang chọn: {extra}\nHãy chọn THANH (Frame), không chọn nút/area."
        debug = ""
        if debug_err:
            debug = f"\n\n[DEBUG] {debug_err}"
            print("[DEBUG] last_error:", debug_err)
        messagebox.showwarning(
            "Không có Frame",
            "Chưa chọn Frame nào trong SAP2000!\n"
            "Quét chọn thanh trong cửa sổ SAP rồi bấm Xuất lại "
            "(không cần bấm Kết nối lại)."
            f"{hint}{debug}",
        )

    def _on_source_menu(self, label: str):
        self.var_source.set(SOURCE_MENU.get(label, LOAD_DESIGN_COMBOS))
        self._on_source_changed()

    def _on_source_changed(self, *_args):
        """Đổi loại nguồn tải → nạp lại danh sách với lựa chọn mặc định."""
        self._selected_load_names = None
        if self.connector.is_connected:
            self._refresh_load_names()
            n = len(self._active_load_names())
            self.status_bar.set_text(
                f"Nguồn tải: {self.opt_source.get()} — {n} nguồn. "
                f"{SOURCE_HINTS.get(self.var_source.get(), '')}"
            )
        else:
            self._all_load_names = []
            self._modal_load_names = set()
            self._update_load_button_label()

    def _refresh_load_names(self) -> tuple[list[str], set[str]]:
        source = self.var_source.get()
        names, modal = self.connector.list_load_names(source)
        self._all_load_names = names
        self._modal_load_names = set(modal)
        if self._selected_load_names is None:
            self._selected_load_names = default_selected_loads(
                names, self._modal_load_names, source,
            )
        else:
            allowed = set(names) - self._modal_load_names
            self._selected_load_names = [n for n in self._selected_load_names if n in allowed]
        self._update_load_button_label()
        return names, self._modal_load_names

    def _active_load_names(self) -> list[str]:
        if self._selected_load_names is None:
            return default_selected_loads(
                self._all_load_names, self._modal_load_names, self.var_source.get(),
            )
        return list(self._selected_load_names)

    def _update_load_button_label(self):
        chosen = self._active_load_names()
        n = len(chosen)
        n_lrfd = sum(1 for x in chosen if is_lrfd_load(x))
        if not self._all_load_names:
            text = "Nguồn tải ▾"
        elif n == 0:
            text = "0 nguồn ▾"
        elif self.var_source.get() == LOAD_DESIGN_COMBOS:
            text = f"{n} combo TK ▾"
        elif n_lrfd == n:
            text = f"{n} LRFD ▾"
        else:
            text = f"{n} nguồn ▾"
        self.btn_pick_loads.configure(text=text)

    def _open_load_source_picker(self):
        """Ô chọn nguồn tải — chỉ hiện khi bấm nút này."""
        if self._load_picker is not None:
            try:
                if self._load_picker.win.winfo_exists():
                    self._load_picker.win.lift()
                    self._load_picker.win.focus_force()
                    return
            except Exception:
                self._load_picker = None

        if not self.connector.is_connected:
            messagebox.showinfo(
                "Chưa kết nối",
                "Kết nối SAP2000 trước, rồi bấm lại để xem / chọn nguồn tải.",
            )
            return

        self._refresh_load_names()
        if not self._all_load_names:
            messagebox.showwarning(
                "Không có nguồn tải",
                self._no_load_message(),
            )
            return

        def on_apply(chosen: list[str]):
            self._selected_load_names = list(chosen)
            self._update_load_button_label()
            n = len(chosen)
            n_lrfd = sum(1 for x in chosen if is_lrfd_load(x))
            self.status_bar.set_text(
                f"Đã chọn {n} nguồn tải ({n_lrfd} LRFD, đã bỏ Modal). "
                "Bấm Xuất để lấy nội lực theo danh sách này."
            )

        picker = LoadSourcePicker(
            self,
            names=self._all_load_names,
            selected=self._active_load_names(),
            modal_names=self._modal_load_names,
            on_apply=on_apply,
            title=f"Chọn nguồn tải — {self.opt_source.get()}",
            hint=SOURCE_HINTS.get(self.var_source.get()),
        )
        picker.place_near(self.btn_pick_loads)
        self._load_picker = picker

    def _on_node_load_cell_click(
        self, row_id, row_index, col_name, current_value, row_values, event,
    ):
        """Bấm ô Nguồn Tải trên bảng → popover chọn lại combo/case cho đúng dòng đó."""
        if not self.results_node:
            return
        frame_name = str(row_values[0]) if row_values else ""
        node_label = str(row_values[3]) if len(row_values) > 3 else ""
        extreme_type = str(row_values[4]) if len(row_values) > 4 else ""
        row = None
        for r in self.results_node:
            if (r.frame_name == frame_name
                    and r.node_label == node_label
                    and r.extreme_type == extreme_type):
                row = r
                break
        if row is None and 0 <= row_index < len(self.results_node):
            row = self.results_node[row_index]
        if row is None:
            return
        forces = self._force_cache.get(row.frame_name) or []
        if not forces:
            self.status_bar.set_text(
                "Không có dữ liệu nội lực để chọn lại. Hãy Xuất Nút Đầu / Cuối trước."
            )
            return

        at_sta = forces_at_row_position(forces, row)

        names = []
        seen = set()
        for f in at_sta:
            if f.load_case not in seen:
                names.append(f.load_case)
                seen.add(f.load_case)
        if not names:
            return

        def on_apply(chosen: list[str]):
            if not chosen:
                return
            pick = chosen[0]
            match = next((f for f in at_sta if f.load_case == pick), None)
            if match is None:
                return
            apply_force_values(row, match)
            self.table_node.update_row_values(row_id, node_row_values(row))
            if self.summary_rows and self._summary_source == SUMMARY_SRC_FRAME:
                self._build_summary()
            self.status_bar.set_text(
                f"Đã đổi nguồn tải dòng [{row.extreme_type}] → {pick}"
                + (" (đã cập nhật bảng tóm tắt)" if self.summary_rows else "")
            )

        picker = LoadSourcePicker(
            self,
            names=names,
            selected=[row.load_case] if row.load_case in names else names[:1],
            modal_names=self._modal_load_names,
            on_apply=on_apply,
            title=f"Chọn lại nguồn tải — {row.extreme_type}",
            single_select=True,
            allow_non_lrfd=True,
        )
        try:
            picker.place_near(x_root=event.x_root, y_root=event.y_root)
        except Exception:
            picker.place_near(self.table_node)

    def _on_connect(self):
        self.status_bar.set_text("Đang kết nối SAP2000...")
        self.update_idletasks()

        result = self.connector.connect()

        if result == "OK":
            self.lbl_status.configure(text="● ĐÃ KẾT NỐI", text_color="#16A34A")
            self.connector.set_units_kn_m()

            frames = self._refresh_frames()
            n = len(frames)

            self._selected_load_names = None
            self._refresh_load_names()
            n_load = len(self._active_load_names())

            if n > 0:
                self.status_bar.set_text(
                    f"Kết nối thành công! {n} Frame đang được chọn. "
                    f"Nguồn tải: {n_load} LRFD (bỏ Modal). Bấm 'Nguồn tải' để xem/chọn lại."
                )
            else:
                extra = self.connector.describe_selection()
                msg = (
                    "Kết nối thành công nhưng chưa chọn Frame nào! "
                    "Hãy quét chọn thanh trong SAP2000 rồi bấm Xuất."
                )
                if extra:
                    msg += f" Đang chọn: {extra}."
                self.status_bar.set_text(msg)
                if self.connector.last_error:
                    print("[DEBUG] last_error:", self.connector.last_error)
        else:
            self.lbl_status.configure(text="● LỖI KẾT NỐI", text_color="#DC2626")
            self.status_bar.set_text(result, is_error=True)
            messagebox.showerror("Lỗi kết nối", result)
            if self.connector.last_error:
                print("[DEBUG] last_error:", self.connector.last_error)

    def _on_run_node(self):
        if not self.connector.is_connected:
            messagebox.showwarning("Chưa kết nối", "Vui lòng kết nối SAP2000 trước!")
            return

        self._set_buttons_enabled(False)
        self.status_bar.set_text("Đang xử lý xuất nội lực Nút Đầu / Cuối...")
        self.progress.set(0)
        self.update_idletasks()

        try:
            source = self.var_source.get()
            node_opt = self.var_node.get()
            self.connector.set_units_kn_m()

            # Luôn nạp lại danh sách: combo thiết kế có thể đã đổi trong SAP2000
            self._refresh_load_names()
            chosen = self._active_load_names()
            if not chosen:
                self._set_buttons_enabled(True)
                messagebox.showwarning(
                    "Chưa chọn nguồn tải",
                    self._no_load_message()
                    + "\n\nBấm nút 'Nguồn tải ▾' để xem và chọn lại.",
                )
                if self._all_load_names:
                    self._open_load_source_picker()
                return

            load_names = self.connector.setup_output_source(source, chosen)
            n_lrfd = sum(1 for x in load_names if is_lrfd_load(x))
            self.status_bar.set_text(
                f"Đã thiết lập {len(load_names)} nguồn tải ({n_lrfd} LRFD, bỏ Modal). "
                "Đang lấy dữ liệu Frame..."
            )
            self.update_idletasks()

            frames = self._refresh_frames()

            if not frames:
                self._warn_no_frames()
                self._set_buttons_enabled(True)
                return

            all_results: list[ResultRow] = []
            self._force_cache = {}
            self._info_cache = {}
            no_result: list[str] = []
            t0 = time.time()
            chosen_set = set(load_names)

            for i, frame_name in enumerate(frames):
                self.status_bar.set_text(
                    f"Đang xử lý Frame {i+1}/{len(frames)}: {frame_name}"
                )
                self.progress.set((i + 1) / len(frames))
                self.update_idletasks()

                # Excel: Design Combos → chỉ combo thiết kế của đúng thanh này
                allowed = self.connector.allowed_loads_for_frame(
                    frame_name, source, chosen_set,
                )
                rows = process_frame_node_extremes(
                    self.connector, frame_name, node_opt,
                    allowed_loads=allowed,
                    force_cache=self._force_cache,
                    info_cache=self._info_cache,
                )
                if not rows:
                    no_result.append(frame_name)
                all_results.extend(rows)

            self.results_node = all_results
            self._node_opt_run = node_opt
            elapsed = time.time() - t0

            if not all_results:
                messagebox.showwarning(
                    "Không tìm thấy dữ liệu",
                    "Không tìm thấy nội lực với nguồn đã chọn "
                    f"({len(load_names)} nguồn, đã bỏ Modal).\n"
                    + self._no_result_hint(source)
                    + "\nBấm nút 'Nguồn tải ▾' để xem và chọn lại.",
                )
                self._set_buttons_enabled(True)
                return

            self._display_node_results(elapsed, no_result)

        except Exception as e:
            import traceback
            err_msg = traceback.format_exc()
            print("[ERROR]", err_msg)
            messagebox.showerror("Lỗi", f"{e}\n\nChi tiết:\n{err_msg}")

        self._set_buttons_enabled(True)

    def _no_load_message(self) -> str:
        source = self.var_source.get()
        if source == LOAD_DESIGN_COMBOS:
            return (
                "Không có combo thiết kế cường độ nào trong SAP2000 "
                "(Design > Steel Frame Design > Select Design Combos...).\n"
                "Gán combo thiết kế trong SAP2000, hoặc đổi nguồn tải sang "
                "'Combos (tất cả)'."
            )
        return "Không có nguồn tải dùng được (đã bỏ Modal/Buckling) cho loại đang chọn."

    def _no_result_hint(self, source: str) -> str:
        if source in (LOAD_DESIGN_COMBOS, LOAD_CASES_AND_DESIGN):
            return (
                "Lưu ý: Design Combos chỉ lấy combo thiết kế của đúng thủ tục thiết kế "
                "của thanh (Steel/Concrete/...); thanh 'No Design' sẽ không có kết quả."
            )
        return ""

    def _display_node_results(self, elapsed: float, no_result: Optional[list[str]] = None):
        rows_data = [node_row_values(r) for r in self.results_node]

        self.table_node.set_data(rows_data, tag_column_idx=4)
        self.tabview.set(TAB_NODE)
        self.lbl_node_count.configure(
            text=f"{len(rows_data)} dòng | {elapsed:.1f}s",
        )

        # Bảng tóm tắt luôn khớp với lần xuất mới nhất
        if self.summary_rows and self._summary_source == SUMMARY_SRC_FRAME:
            self._build_summary()

        msg = f"✅ Xuất thành công {len(rows_data)} dòng | {elapsed:.1f} giây"
        if no_result:
            shown = ", ".join(no_result[:5]) + (", ..." if len(no_result) > 5 else "")
            msg += f" | ⚠ {len(no_result)} thanh không có kết quả: {shown}"
        self.status_bar.set_text(msg, is_error=bool(no_result))
        self.progress.set(1)

    def _on_run_multi(self):
        if not self.connector.is_connected:
            messagebox.showwarning("Chưa kết nối", "Vui lòng kết nối SAP2000 trước!")
            return

        stations_text = self.entry_stations.get().strip()
        if not stations_text:
            messagebox.showwarning(
                "Thiếu vị trí",
                "Vui lòng nhập các vị trí cần xuất (Ví dụ: 2.0, 4.0)",
            )
            return

        stations = []
        for s in stations_text.split(","):
            s = s.strip()
            try:
                stations.append(float(s))
            except ValueError:
                pass

        if not stations:
            messagebox.showwarning("Lỗi", "Không nhận dạng được số hợp lệ!")
            return

        self._set_buttons_enabled(False)
        self.status_bar.set_text("Đang xử lý xuất nội lực Nhiều Vị Trí...")
        self.progress.set(0)
        self.update_idletasks()

        try:
            source = self.var_source.get()
            self.connector.set_units_kn_m()
            if not self._all_load_names:
                self._refresh_load_names()
            chosen = self._active_load_names()
            if not chosen:
                self._set_buttons_enabled(True)
                messagebox.showwarning(
                    "Chưa chọn nguồn tải",
                    "Không lấy Modal và mặc định chỉ lấy tải có LRFD.\n"
                    "Bấm nút 'Nguồn tải ▾' để xem và chọn lại.",
                )
                self._open_load_source_picker()
                return
            self.connector.setup_output_source(source, chosen)
            allowed_multi = set(chosen)
            frames = self._refresh_frames()

            if not frames:
                self._warn_no_frames()
                self._set_buttons_enabled(True)
                return

            all_results: list[ResultRowMulti] = []
            t0 = time.time()

            for i, frame_name in enumerate(frames):
                self.status_bar.set_text(
                    f"Đang xử lý Frame {i+1}/{len(frames)}: {frame_name}"
                )
                self.progress.set((i + 1) / len(frames))
                self.update_idletasks()

                try:
                    rows = process_frame_multi_station(
                        self.connector, frame_name, stations,
                        allowed_loads=allowed_multi,
                    )
                    all_results.extend(rows)
                except Exception as skip_err:
                    print(f"[SkipFrame] {frame_name}: {skip_err}")
                    continue

            self.results_multi = all_results
            elapsed = time.time() - t0

            if not all_results:
                messagebox.showwarning(
                    "Không tìm thấy dữ liệu",
                    "Không tìm thấy dữ liệu phù hợp hoặc chiều dài thanh nhỏ hơn vị trí xuất!",
                )
                self._set_buttons_enabled(True)
                return

            self._display_multi_results(elapsed)

        except Exception as e:
            import traceback
            err_msg = traceback.format_exc()
            print("[ERROR]", err_msg)
            messagebox.showerror("Lỗi", f"{e}\n\nChi tiết:\n{err_msg}")

        self._set_buttons_enabled(True)

    def _display_multi_results(self, elapsed: float):
        if not hasattr(self, 'table_multi') or TAB_MULTI not in self.tabview._tab_dict:
            return

        rows_data = []
        for r in self.results_multi:
            rows_data.append((
                r.frame_name, r.section_name, r.htb, r.tw, r.bf, r.tf,
                r.length, r.location_label, r.extreme_type, r.load_case,
                r.P, r.V2, r.V3, r.M2, r.M3,
            ))

        self.table_multi.set_data(rows_data, tag_column_idx=8)
        self.tabview.set(TAB_MULTI)
        self.lbl_multi_count.configure(
            text=f"{len(rows_data)} dòng | {elapsed:.1f}s",
        )

        if hasattr(self, 'combo_location'):
            locations = get_unique_locations(self.results_multi)
            if locations:
                self.combo_location.configure(values=locations)
                self.combo_location.set(locations[0])
                self._on_location_changed(locations[0])

        self.status_bar.set_text(
            f"✅ Xuất thành công {len(rows_data)} dòng | {elapsed:.1f} giây",
        )
        self.progress.set(1)

    def _on_summary(self):
        """
        Tạo bảng tóm tắt cực trị (Module2) - Đã bỏ cột Thanh.
        Nguồn theo tab đang xem: tab Phản Lực → tóm tắt phản lực,
        tab Nút Đầu / Cuối → tóm tắt thanh, tab Tóm tắt → giữ nguồn hiện tại.
        """
        current = self._current_tab_name
        if current == TAB_REACTION:
            source = SUMMARY_SRC_REACTION
        elif current == TAB_NODE:
            source = SUMMARY_SRC_FRAME
        else:
            source = self._summary_source

        if source == SUMMARY_SRC_REACTION and not self._reactions:
            messagebox.showinfo("Chưa có dữ liệu", "Vui lòng chạy 'Xuất Phản Lực' trước!")
            return
        if source == SUMMARY_SRC_FRAME and not self.results_node:
            messagebox.showinfo("Chưa có dữ liệu", "Vui lòng chạy 'Xuất Nút Đầu / Cuối' trước!")
            return

        self._summary_source = source
        self._build_summary(keep_order=False)
        self.tabview.set(TAB_SUMMARY)
        self.status_bar.set_text(
            f"Đã tạo bảng tóm tắt cực trị [{self._summary_scope}]. "
            "Dùng dropdown để đổi thứ tự hàng/cột."
        )

    def _build_summary(self, keep_order: bool = True):
        """
        1 bảng duy nhất từ mọi dòng đã xuất: chọn Cả hai → gộp Nút Đầu + Nút Cuối,
        không cần chuyển đầu. Giữ preset thứ tự hàng/cột, ẩn V3 như tool.
        keep_order=True: giữ thứ tự hàng đang hiển thị (kể cả đã đổi bằng tay).

        Axial luôn theo quy ước "nén dương" để dán RAM Connection:
          - Thanh: Axial = −P (đổi dấu lực dọc thanh)
          - Phản lực: Axial = F3 gốc của SAP (tab Phản Lực đã đổi dấu → đổi lại)
        """
        current_order = self.table_sum.get_condition_order() if keep_order else []

        if self._summary_source == SUMMARY_SRC_REACTION:
            # V2 = F1, V3 = F2, Axial = F3 gốc, M33 = M2, M22 = M1
            self.summary_rows = summarize_reaction_extremes(self._reactions, axial_sign=-1.0)
            n_joint = len({r.joint for r in self._reactions})
            self._summary_scope = f"Phản lực ({n_joint} nút)"
            scope_label = f"Phạm vi: {self._summary_scope} · Axial = F3"
        else:
            self.summary_rows = summarize_global_extremes(self.results_node)
            for s in self.summary_rows:
                s.axial = -s.axial or 0.0
            self._summary_scope = SUMMARY_SCOPE_TEXT.get(self._node_opt_run, "")
            scope_label = f"Phạm vi: {self._summary_scope} · Axial đổi dấu"

        rows = [
            (r.num, r.condition, r.V2, r.axial, r.M33, r.M22, r.V3, r.source, r.load_case)
            for r in self.summary_rows
        ]
        self.table_sum.set_data(rows, tag_column_idx=1)

        # Thứ tự hàng: giữ thứ tự đang có, hoặc preset đang chọn
        order = current_order or ROW_ORDER_MENU.get(self.opt_row_order.get())
        if order:
            self.table_sum.reorder_by_condition_names(order)

        # Thứ tự cột lực theo preset đang chọn
        col_order = COL_ORDER_MENU.get(self.opt_col_order.get())
        if col_order:
            self.table_sum.set_display_columns(col_order)

        # Áp dụng ẩn V3 nếu đang tick
        if self.var_hide_v3.get():
            self.table_sum.set_hide_condition("V3max", True)

        self.lbl_summary_scope.configure(text=scope_label)

    # ══════════════════════════════════════════════════════════
    # PHẢN LỰC NÚT (Excel Reaction)
    # ══════════════════════════════════════════════════════════

    def _on_run_reaction(self):
        """Xuất phản lực nút — dùng chung nguồn tải với phần thanh."""
        if not self.connector.is_connected:
            messagebox.showwarning("Chưa kết nối", "Vui lòng kết nối SAP2000 trước!")
            return

        self._set_buttons_enabled(False)
        self.status_bar.set_text("Đang xử lý xuất Phản Lực...")
        self.update_idletasks()

        try:
            source = self.var_source.get()
            self.connector.set_units_kn_m()
            self._refresh_load_names()
            chosen = self._active_load_names()
            if not chosen:
                self._set_buttons_enabled(True)
                messagebox.showwarning(
                    "Chưa chọn nguồn tải",
                    self._no_load_message()
                    + "\n\nBấm nút 'Nguồn tải ▾' để xem và chọn lại.",
                )
                if self._all_load_names:
                    self._open_load_source_picker()
                return
            load_names = self.connector.setup_output_source(source, chosen)
            t0 = time.time()

            # Excel: các nút đang chọn. Không chọn nút → nút gối của các thanh đang chọn
            points = self.connector.get_selected_points()
            if points:
                how = f"{len(points)} nút đang chọn"
                raw = self.connector.get_joint_reactions()
            else:
                frames = self.connector.get_selected_frames()
                if not frames:
                    self._set_buttons_enabled(True)
                    messagebox.showwarning(
                        "Chưa chọn nút",
                        "Chưa chọn nút hoặc thanh nào trong SAP2000!\n"
                        "Quét chọn các nút chân cột rồi bấm Xuất Phản Lực.\n"
                        "Nếu chỉ chọn thanh, tool tự lấy các nút gối của các thanh đó.",
                    )
                    return
                points = self.connector.get_frame_end_points(frames)
                how = f"nút gối của {len(frames)} thanh đang chọn"
                raw = self.connector.get_joint_reactions(points)

            # Phản lực: lực dọc F3 LUÔN đổi dấu (như cột Axial của bảng tóm tắt)
            reacts = flip_reaction_axial(filter_reactions(raw, set(load_names)))
            if not reacts:
                self._set_buttons_enabled(True)
                messagebox.showwarning(
                    "Không có phản lực",
                    f"Không có phản lực ({how}, {len(load_names)} nguồn tải).\n"
                    "- Nút chọn không phải nút gối (không có liên kết / lò xo), hoặc\n"
                    "- Model chưa chạy phân tích / nguồn tải không có kết quả.",
                )
                return

            self._reactions = reacts
            if self.summary_rows and self._summary_source == SUMMARY_SRC_REACTION:
                self._build_summary()
            self.reaction_merged, self.reaction_by_joint = process_reactions(reacts)
            elapsed = time.time() - t0

            self._show_reaction_rows()
            self._switch_tab(TAB_REACTION)
            n_joint = len({r.joint for r in reacts})
            self.status_bar.set_text(
                f"✅ Phản lực: {n_joint} nút có phản lực ({how}) | "
                f"{len(load_names)} nguồn tải | {elapsed:.1f} giây"
            )

        except Exception as e:
            import traceback
            err_msg = traceback.format_exc()
            print("[ERROR]", err_msg)
            messagebox.showerror("Lỗi", f"{e}\n\nChi tiết:\n{err_msg}")

        self._set_buttons_enabled(True)

    def _on_reaction_load_cell_click(
        self, row_id, row_index, col_name, current_value, row_values, event,
    ):
        """Bấm ô Nguồn Tải bảng phản lực → chọn lại combo cho đúng dòng đó."""
        if not self._reactions or len(row_values) < 2:
            return
        joint, criteria = str(row_values[0]), str(row_values[1])
        row = next(
            (r for r in self._current_reaction_rows()
             if r.joint == joint and r.criteria == criteria),
            None,
        )
        if row is None:
            return
        choices = reaction_choices(self._reactions, row.joint)
        if not choices:
            return
        names = [label for label, _r in choices]
        current = next(
            (label for label, r in choices
             if r.load_case == row.load_case
             and r.step_type == row.step_type and r.step_num == row.step_num),
            names[0],
        )

        def on_apply(chosen: list[str]):
            if not chosen:
                return
            src = dict(choices).get(chosen[0])
            if src is None:
                return
            apply_reaction_values(row, src)
            self.table_reaction.update_row_values(row_id, reaction_row_values(row))
            self.status_bar.set_text(
                f"Đã đổi nguồn tải dòng [Nút {row.joint} · {row.criteria}] → {chosen[0]}"
            )

        picker = LoadSourcePicker(
            self,
            names=names,
            selected=[current],
            modal_names=self._modal_load_names,
            on_apply=on_apply,
            title=f"Chọn lại nguồn tải — Nút {row.joint} · {row.criteria}",
            single_select=True,
            allow_non_lrfd=True,
        )
        try:
            picker.place_near(x_root=event.x_root, y_root=event.y_root)
        except Exception:
            picker.place_near(self.table_reaction)

    def _export_reaction_excel(self):
        rows = self._current_reaction_rows()
        if not rows:
            messagebox.showinfo("Trống", "Chưa có dữ liệu phản lực để xuất!")
            return

        merged = self.seg_reaction_view.get() != REACTION_VIEW_BY_JOINT
        name = "PhanLuc_GopNut" if merged else "PhanLuc_TungNut"
        filepath = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("File Excel", "*.xlsx")],
            initialfile=f"{name}.xlsx",
        )
        if not filepath:
            return

        # Đúng thứ tự đang hiển thị (kể cả đã đổi bằng Alt+Up/Down)
        tree = self.table_reaction.tree
        by_key = {(r.joint, r.criteria): r for r in rows}
        ordered = []
        for ch in tree.get_children():
            vals = tree.item(ch, "values")
            key = (str(vals[0]), str(vals[1])) if len(vals) > 1 else None
            if key in by_key:
                ordered.append(by_key[key])

        try:
            from export_excel import export_reaction_results
            export_reaction_results(ordered or rows, filepath, sheet_name=name)
            self.status_bar.set_text(f"Đã xuất: {filepath}")
            messagebox.showinfo("Thành công", f"Đã xuất file:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Lỗi xuất Excel", str(e))

    def _on_location_changed(self, selected_location: str):
        if not self.results_multi or not hasattr(self, 'table_torsion'):
            return

        best = find_m3_min_row(self.results_multi, selected_location)

        if best:
            self.lbl_m3_min.configure(text=f"M3 MIN = {best.M3:.2f} kNm")
            row_data = [(
                best.frame_name, best.section_name,
                best.htb, best.tw, best.bf, best.tf,
                best.length, best.location_label,
                best.extreme_type, best.load_case,
                best.P, best.V2, best.V3, best.M2, best.M3,
            )]
            self.table_torsion.set_data(row_data)
        else:
            self.lbl_m3_min.configure(text="M3 MIN = —")
            self.table_torsion.clear()

    # ══════════════════════════════════════════════════════════
    # XUẤT EXCEL
    # ══════════════════════════════════════════════════════════

    def _export_node_excel(self):
        if not self.results_node:
            messagebox.showinfo("Trống", "Chưa có dữ liệu để xuất!")
            return

        filepath = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("File Excel", "*.xlsx")],
            initialfile="NoiLuc_NutDauCuoi.xlsx",
        )
        if not filepath:
            return

        try:
            from export_excel import export_node_results
            export_node_results(self.results_node, filepath)
            self.status_bar.set_text(f"Đã xuất: {filepath}")
            messagebox.showinfo("Thành công", f"Đã xuất file:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Lỗi xuất Excel", str(e))

    def _export_multi_excel(self):
        if not self.results_multi:
            messagebox.showinfo("Trống", "Chưa có dữ liệu để xuất!")
            return

        filepath = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("File Excel", "*.xlsx")],
            initialfile="NoiLuc_NhieuViTri.xlsx",
        )
        if not filepath:
            return

        try:
            from export_excel import export_multi_station_results
            export_multi_station_results(self.results_multi, filepath)
            self.status_bar.set_text(f"Đã xuất: {filepath}")
            messagebox.showinfo("Thành công", f"Đã xuất file:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Lỗi xuất Excel", str(e))

    def _export_summary_excel(self):
        if not self.summary_rows:
            messagebox.showinfo(
                "Trống",
                "Chưa có bảng tóm tắt để xuất! Bấm 'Tóm Tắt Cực Trị' trước.",
            )
            return

        is_reaction = self._summary_source == SUMMARY_SRC_REACTION
        filepath = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("File Excel", "*.xlsx")],
            initialfile="TomTat_PhanLuc.xlsx" if is_reaction else "TomTat_CucTri.xlsx",
        )
        if not filepath:
            return

        try:
            from export_excel import export_summary
            export_summary(
                self.summary_rows,
                filepath,
                columns_order=self.table_sum.get_display_columns(),
                condition_order=self.table_sum.get_condition_order(),
                scope_text=self._summary_scope,
            )
            self.status_bar.set_text(f"Đã xuất: {filepath}")
            messagebox.showinfo("Thành công", f"Đã xuất file:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Lỗi xuất Excel", str(e))

    # ══════════════════════════════════════════════════════════
    # TIỆN ÍCH
    # ══════════════════════════════════════════════════════════

    def _set_buttons_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.btn_run_node.configure(state=state)
        self.btn_summary.configure(state=state)
        self.btn_run_reaction.configure(state=state)
        if hasattr(self, 'btn_run_multi'):
            self.btn_run_multi.configure(state=state)
