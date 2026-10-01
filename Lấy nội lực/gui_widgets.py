"""
gui_widgets.py
==============
Các widget tùy chỉnh cho giao diện:
  - DataTable: Bảng dữ liệu có kẻ ô dọc/ngang (grid),
    TÔ MÀU Ô CỰC TRỊ THEO DẤU GIỐNG EXCEL InternalForce:
      * Chỉ tô đúng ô giá trị cực trị, chữ đậm
      * Dương (+): nền xanh lá nhạt, chữ xanh đậm — Âm (−): nền cam nhạt, chữ đỏ
      * Tất cả các ô và cột khác giữ nền trắng tinh / sọc nhạt sạch sẽ y như Excel
    Hỗ trợ:
      - Đổi thứ tự hàng (▲/▼, Alt+Up/Down, chuột phải, presets)
      - Đổi thứ tự cột (V2, Axial, M33, M22, V3)
      - Ẩn/hiện dòng (V3max)
      - Copy khối nội lực vào Excel theo đúng thứ tự hiển thị
      - Cột thông tin (no_copy_columns): luôn nằm cuối, không bị copy
  - StatusBar: Thanh trạng thái hiển thị thông tin ở cuối cửa sổ.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Optional

try:
    import customtkinter as ctk
except ImportError:
    ctk = None


# Màu ô cực trị theo dấu — Excel InternalForce (PrintExtremeRows)
POS_BG = "#E2EFDA"   # RGB(226, 239, 218)
POS_FG = "#385723"   # RGB(56, 87, 35)
NEG_BG = "#FCE4D6"   # RGB(252, 228, 214)
NEG_FG = "#C00000"   # RGB(192, 0, 0)

# Loại cực trị / điều kiện → cột cần tô
EXTREME_TO_COLUMN = {
    # Bảng Nút Đầu / Cuối (Excel InternalForce) + Nhiều vị trí (Module 4)
    "Max P": "P (kN)",
    "Min P": "P (kN)",
    "Max V2 (Abs)": "V2 (kN)",
    "Max V2": "V2 (kN)",
    "Min V2": "V2 (kN)",
    "Max V3 (Abs)": "V3 (kN)",
    "Max V3": "V3 (kN)",
    "Min V3": "V3 (kN)",
    "Max M2": "M2 (kNm)",
    "Min M2": "M2 (kNm)",
    "Max M3": "M3 (kNm)",
    "Min M3": "M3 (kNm)",
    "Max T (Abs)": "T (kNm)",
    # Bảng Tóm Tắt Cực Trị (Module 2)
    "Mmax": "M33 (kNm)",
    "Mmin": "M33 (kNm)",
    "V2max": "V2 (kN)",
    "Nmax": "Axial (kN)",
    "Nmin": "Axial (kN)",
    "V3max": "V3 (kN)",
}
# Bảng Phản Lực (Excel Reaction): "Max F1 (Fx) (+)" → "F1 (kN)", ...
for _comp, _axis, _unit in (
    ("F1", "Fx", "kN"), ("F2", "Fy", "kN"), ("F3", "Fz", "kN"),
    ("M1", "Mx", "kNm"), ("M2", "My", "kNm"), ("M3", "Mz", "kNm"),
):
    for _sign in ("+", "-"):
        EXTREME_TO_COLUMN[f"Max {_comp} ({_axis}) ({_sign})"] = f"{_comp} ({_unit})"

# Tiền tố tên cột nội lực (để Copy các cột lực)
FORCE_COLUMN_PREFIXES = {
    "P", "V2", "V3", "T", "M2", "M3", "Axial", "M33", "M22", "F1", "F2", "F3", "M1",
}


def is_force_column(col_name: str) -> bool:
    parts = (col_name or "").split()
    return bool(parts) and parts[0] in FORCE_COLUMN_PREFIXES


def sign_colors(value) -> tuple[str, str]:
    """(nền, chữ) theo dấu giá trị — Excel: >= 0 xanh lá, < 0 cam/đỏ."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return POS_BG, POS_FG
    return (POS_BG, POS_FG) if v >= 0 else (NEG_BG, NEG_FG)


# ═══════════════════════════════════════════════════════════════
# BẢNG DỮ LIỆU KẺ Ô LƯỚI + TÔ MÀU Ô CỰC TRỊ GIỐNG EXCEL
# ═══════════════════════════════════════════════════════════════

class DataTable(ttk.Frame):
    """
    Bảng hiển thị dữ liệu dạng Treeview:
      - Kẻ ô dọc rõ nét giống Excel
      - TÔ MÀU ĐÚNG Ô CỰC TRỊ theo dấu (Excel InternalForce):
          + Cột được tô xác định theo loại cực trị (EXTREME_TO_COLUMN)
          + Giá trị >= 0: nền #E2EFDA, chữ #385723 — < 0: nền #FCE4D6, chữ #C00000
      - Hỗ trợ đổi thứ tự hàng và thứ tự cột
      - Nút copy khối các cột lực theo đúng thứ tự hiển thị
    """

    def __init__(
        self,
        master,
        columns: list[str],
        status_callback: Optional[Callable[[str], None]] = None,
        no_copy_columns: Optional[list[str]] = None,
        col_widths: Optional[dict[str, int]] = None,
        **kwargs,
    ):
        super().__init__(master, **kwargs)

        self._columns = list(columns)
        # Cột chỉ để xem (vd "Lấy từ"): luôn ở cuối, không bị copy
        self._no_copy = [c for c in (no_copy_columns or []) if c in self._columns]
        self._data_rows: list[tuple] = []
        self.status_callback = status_callback
        self.on_load_source_click: Optional[Callable[..., None]] = None
        self._dividers: list[tk.Frame] = []
        self._selected_cell_info: Optional[tuple[str, int, str]] = None
        self._detached_items: dict[str, Any] = {}

        # Quản lý tô màu từng ô (Cell Highlights giống Excel)
        self._cell_overlays: list[tk.Label] = []
        self._cell_highlights: dict[str, tuple[str, str, str]] = {}  # {item_id: (col, nền, chữ)}
        self._update_overlays_pending: bool = False

        # ── Cấu hình Theme và Style ───────────────────────────
        self._setup_style()

        # ── Treeview ──────────────────────────────────────────
        self.tree = ttk.Treeview(
            self,
            columns=self._columns,
            show="headings",
            selectmode="extended",
            style="Grid.Treeview",
        )

        widths = col_widths or {}
        for col in self._columns:
            self.tree.heading(
                col,
                text=col,
                anchor="center",
                command=lambda c=col: self.copy_column(c),
            )
            self.tree.column(col, anchor="center", width=widths.get(col, 95), minwidth=50)

        # ── Scrollbars ────────────────────────────────────────
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self._on_vscroll)
        self.hsb = ttk.Scrollbar(self, orient="horizontal", command=self._on_hscroll)
        self.tree.configure(yscrollcommand=self._on_tree_yscroll, xscrollcommand=self._on_tree_xscroll)

        # ── Layout ────────────────────────────────────────────
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.hsb.grid(row=1, column=0, sticky="ew")

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        # ── Tags nền hàng (trắng / xám nhạt như Excel) ─────────
        self.tree.tag_configure("even", background="#F8FAFC")
        self.tree.tag_configure("odd", background="#FFFFFF")

        # ── Menus ─────────────────────────────────────────────
        self._build_context_menu()
        self._build_header_menu()

        # ── Sự kiện chuột và bàn phím ─────────────────────────
        self.tree.bind("<Button-1>", self._on_cell_click)
        self.tree.bind("<Double-Button-1>", self._on_cell_double_click)
        self.tree.bind("<Button-3>", self._on_right_click)
        self.tree.bind("<Control-c>", self._copy_selection)
        self.tree.bind("<Configure>", self._on_configure)
        self.tree.bind("<MouseWheel>", lambda e: self._schedule_update_overlays())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._schedule_update_overlays())

        # Phím tắt di chuyển hàng: Alt+Up / Alt+Down
        self.tree.bind("<Alt-Up>", lambda e: self.move_selected_row("up"))
        self.tree.bind("<Alt-Down>", lambda e: self.move_selected_row("down"))

    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "Grid.Treeview",
            background="#FFFFFF",
            foreground="#0F172A",
            font=("Segoe UI", 10),
            rowheight=29,
            fieldbackground="#FFFFFF",
            borderwidth=1,
            relief="solid",
        )
        style.configure(
            "Grid.Treeview.Heading",
            background="#E2E8F0",
            foreground="#0F172A",
            font=("Segoe UI", 10, "bold"),
            borderwidth=1,
            relief="solid",
            padding=(4, 6),
        )
        style.map(
            "Grid.Treeview.Heading",
            background=[("active", "#CBD5E1")],
        )
        style.map(
            "Grid.Treeview",
            background=[("selected", "#2563EB")],
            foreground=[("selected", "#FFFFFF")],
        )

    # ══════════════════════════════════════════════════════════
    # CUỘN VÀ ĐIỀU PHỐI TÔ MÀU Ô
    # ══════════════════════════════════════════════════════════

    def _on_vscroll(self, *args):
        self.tree.yview(*args)
        self._schedule_update_overlays()

    def _on_hscroll(self, *args):
        self.tree.xview(*args)
        self._update_dividers()
        self._schedule_update_overlays()

    def _on_tree_yscroll(self, *args):
        self.vsb.set(*args)
        self._schedule_update_overlays()

    def _on_tree_xscroll(self, *args):
        self.hsb.set(*args)
        self._schedule_update_overlays()

    def _on_configure(self, event=None):
        self._update_dividers()
        self._schedule_update_overlays()

    def _schedule_update_overlays(self):
        if not self._update_overlays_pending:
            self._update_overlays_pending = True
            self.after_idle(self._do_update_overlays)

    def _do_update_overlays(self):
        self._update_overlays_pending = False

        for o in self._cell_overlays:
            try:
                o.destroy()
            except Exception:
                pass
        self._cell_overlays.clear()

        if not self._cell_highlights:
            return

        disp_cols = self.get_display_columns()
        tree_h = self.tree.winfo_height()
        tree_w = self.tree.winfo_width()
        selected_items = set(self.tree.selection())

        for item_id, (target_col, bg, fg) in list(self._cell_highlights.items()):
            if target_col not in disp_cols or not self.tree.exists(item_id):
                continue

            box = self.tree.bbox(item_id, target_col)
            if box and len(box) == 4 and box[2] > 0 and box[3] > 0:
                x, y, w, h = box
                # Kiểm tra ô có nằm trong vùng nhìn thấy theo chiều dọc không
                if y + h <= 0 or y >= tree_h:
                    continue

                real_idx = self._columns.index(target_col) if target_col in self._columns else -1
                vals = self.tree.item(item_id, "values")
                val_text = vals[real_idx] if 0 <= real_idx < len(vals) else ""

                is_sel = item_id in selected_items
                bg_color = "#2563EB" if is_sel else bg
                fg_color = "#FFFFFF" if is_sel else fg

                lbl = tk.Label(
                    self.tree,
                    text=str(val_text),
                    bg=bg_color,
                    foreground=fg_color,
                    font=("Segoe UI", 10, "bold"),
                    anchor="center",
                    relief="flat",
                )
                # Giảm 1px chiều rộng để không đè lên đường kẻ dọc
                lbl.place(x=x, y=y, width=max(1, w - 1), height=h)

                # Chuyển tiếp sự kiện
                lbl.bind("<Button-1>", lambda e, it=item_id: self._on_overlay_click(e, it))
                lbl.bind("<Double-Button-1>", lambda e, v=str(val_text), c=target_col: self._copy_cell_value(v, c))
                lbl.bind("<Button-3>", lambda e, it=item_id, c=target_col, v=str(val_text): self._on_overlay_right_click(e, it, c, v))

                self._cell_overlays.append(lbl)

    def _on_overlay_click(self, event, item_id):
        if event.state & 0x0004:  # Phím Control
            if item_id in self.tree.selection():
                self.tree.selection_remove(item_id)
            else:
                self.tree.selection_add(item_id)
        else:
            self.tree.selection_set(item_id)
        self.tree.focus(item_id)
        self._schedule_update_overlays()

    def _on_overlay_right_click(self, event, item_id, col_name, val):
        self.tree.selection_set(item_id)
        self.tree.focus(item_id)
        self._schedule_update_overlays()

        # Mở context menu
        col_idx = self.get_display_columns().index(col_name) if col_name in self.get_display_columns() else 0
        self._selected_cell_info = (item_id, col_idx, val)

        self.menu.delete(0, "end")
        display_val = val if len(val) < 25 else val[:22] + "..."
        self.menu.add_command(
            label=f"📋 Sao chép ô:  \"{display_val}\"",
            command=lambda: self._copy_cell_value(val, col_name),
        )
        self.menu.add_command(
            label=f"📋 Sao chép cả cột dọc:  [{col_name}]",
            command=lambda: self.copy_column(col_name),
        )
        self.menu.add_separator()
        self.menu.add_command(
            label="▲  Di chuyển hàng lên trên (Alt+Up)",
            command=lambda: self.move_selected_row("up"),
        )
        self.menu.add_command(
            label="▼  Di chuyển hàng xuống dưới (Alt+Down)",
            command=lambda: self.move_selected_row("down"),
        )
        self.menu.add_separator()
        self.menu.add_command(
            label="📊 Sao chép các cột nội lực (Paste thẳng vào Excel)",
            command=self.copy_force_columns,
        )
        self.menu.add_separator()
        self.menu.add_command(
            label="📋 Sao chép toàn bộ bảng (chỉ số liệu)",
            command=lambda: self.copy_all(include_headers=False),
        )

        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    # ══════════════════════════════════════════════════════════
    # THAY ĐỔI THỨ TỰ HÀNG (ROW REORDERING)
    # ══════════════════════════════════════════════════════════

    def move_selected_row(self, direction: str = "up"):
        selected = self.tree.selection()
        if not selected:
            return

        item = selected[0]
        children = list(self.tree.get_children())
        if item not in children:
            return

        idx = children.index(item)
        if direction == "up":
            new_idx = max(0, idx - 1)
        elif direction == "down":
            new_idx = min(len(children) - 1, idx + 1)
        elif direction == "top":
            new_idx = 0
        elif direction == "bottom":
            new_idx = len(children) - 1
        else:
            return

        if new_idx != idx:
            self.tree.move(item, "", new_idx)
            self._renumber_stt_and_sync()
            self.tree.selection_set(item)
            self._schedule_update_overlays()
            vals = self.tree.item(item, "values")
            cond = vals[1] if len(vals) > 1 else ""
            self._notify(f"Đã di chuyển hàng [{cond}] {'lên' if direction == 'up' else 'xuống'}.")

    def reorder_by_condition_names(self, desired_order: list[str]):
        children = self.tree.get_children()
        item_by_cond = {}
        for ch in children:
            vals = self.tree.item(ch, "values")
            if len(vals) > 1:
                item_by_cond[str(vals[1]).strip()] = ch

        idx = 0
        for cond in desired_order:
            clean_cond = str(cond).strip()
            if clean_cond in item_by_cond:
                self.tree.move(item_by_cond[clean_cond], "", idx)
                idx += 1

        self._renumber_stt_and_sync()
        self._schedule_update_overlays()
        self._notify(f"Đã sắp xếp lại thứ tự hàng: {' ➔ '.join(desired_order[:5])}")

    def set_hide_condition(self, condition_name: str, hide: bool):
        clean_target = condition_name.strip()

        if hide:
            for ch in self.tree.get_children():
                vals = self.tree.item(ch, "values")
                if len(vals) > 1 and str(vals[1]).strip() == clean_target:
                    self._detached_items[clean_target] = ch
                    self.tree.detach(ch)
                    break
        else:
            if clean_target in self._detached_items:
                ch = self._detached_items.pop(clean_target)
                self.tree.move(ch, "", "end")

        self._renumber_stt_and_sync()
        self._schedule_update_overlays()

    def _renumber_stt_and_sync(self):
        children = self.tree.get_children()
        new_rows = []
        # Chỉ đánh lại số khi cột đầu là STT (bảng khác cột đầu là Tên Thanh / Nút)
        has_stt = bool(self._columns) and self._columns[0] == "STT"

        for idx, ch in enumerate(children, 1):
            vals = list(self.tree.item(ch, "values"))
            if vals:
                if has_stt:
                    vals[0] = str(idx)
                    self.tree.item(ch, values=vals)
                new_rows.append(tuple(vals))

        self._data_rows = new_rows

    # ══════════════════════════════════════════════════════════
    # THỨ TỰ VÀ ĐỔI VỊ TRÍ CỘT (COLUMN REORDERING)
    # ══════════════════════════════════════════════════════════

    def get_display_columns(self) -> list[str]:
        raw = self.tree["displaycolumns"]
        if not raw or raw == ("#all",) or raw == "#all":
            return list(self._columns)
        return list(raw)

    def get_copy_columns(self) -> list[str]:
        """Cột hiển thị được phép copy (bỏ cột thông tin)."""
        return [c for c in self.get_display_columns() if c not in self._no_copy]

    def get_condition_order(self) -> list[str]:
        """Thứ tự điều kiện (cột thứ 2) đang hiển thị — dùng khi xuất Excel."""
        out = []
        for ch in self.tree.get_children():
            vals = self.tree.item(ch, "values")
            if len(vals) > 1:
                out.append(str(vals[1]).strip())
        return out

    def set_display_columns(self, new_order: list[str]):
        valid_order = [c for c in new_order if c in self._columns and c not in self._no_copy]
        valid_order += self._no_copy
        if valid_order:
            self.tree["displaycolumns"] = valid_order
            self.after(30, self._update_dividers)
            self._schedule_update_overlays()

    def move_column(self, col_name: str, target_pos: str | int):
        current = self.get_display_columns()
        if col_name not in current:
            return

        current.remove(col_name)
        if target_pos == "start":
            current.insert(0, col_name)
        elif target_pos == "end":
            current.append(col_name)
        elif target_pos == "after_stt":
            idx = 1 if "STT" in current else 0
            current.insert(idx, col_name)
        elif isinstance(target_pos, int):
            idx = max(0, min(target_pos, len(current)))
            current.insert(idx, col_name)

        self.set_display_columns(current)

    # ══════════════════════════════════════════════════════════
    # KẺ Ô DỌC GIỮA CÁC CỘT (DIVIDER LINES)
    # ══════════════════════════════════════════════════════════

    def _update_dividers(self, event=None):
        for d in self._dividers:
            try:
                d.destroy()
            except Exception:
                pass
        self._dividers.clear()

        disp_cols = self.get_display_columns()
        if len(disp_cols) <= 1:
            return

        children = self.tree.get_children()
        use_bbox = False

        if children:
            first_row = children[0]
            test_box = self.tree.bbox(first_row, disp_cols[0])
            if test_box and len(test_box) == 4 and test_box[2] > 0:
                use_bbox = True
                for col in disp_cols[:-1]:
                    box = self.tree.bbox(first_row, col)
                    if box and len(box) == 4:
                        x = box[0] + box[2]
                        line = tk.Frame(self.tree, width=1, bg="#CBD5E1")
                        line.place(x=x, y=0, relheight=1.0)
                        self._dividers.append(line)

        if not use_bbox:
            x = 0
            for col in disp_cols[:-1]:
                w = self.tree.column(col, "width")
                x += w
                line = tk.Frame(self.tree, width=1, bg="#CBD5E1")
                line.place(x=x, y=0, relheight=1.0)
                self._dividers.append(line)

    # ══════════════════════════════════════════════════════════
    # THIẾT LẬP DỮ LIỆU + BẢNG MÀU EXCEL CHUẨN XÁC
    # ══════════════════════════════════════════════════════════

    def set_data(self, rows: list[tuple], tag_column_idx: Optional[int] = None):
        """
        Thiết lập dữ liệu cho bảng.
        Tô màu ĐÚNG Ô CỰC TRỊ theo dấu (Excel InternalForce):
          - Các hàng có nền trắng / xám nhạt sạch sẽ
          - Chỉ riêng ô giá trị cực trị được tô màu nổi bật
        """
        for item in self.tree.get_children():
            self.tree.delete(item)

        self._data_rows = list(rows)
        self._selected_cell_info = None
        self._detached_items.clear()
        self._cell_highlights.clear()

        for i, row in enumerate(rows):
            # Tất cả các dòng đều có nền trắng / xám nhạt sạch sẽ như Excel
            tag = "even" if i % 2 == 0 else "odd"
            item_id = self.tree.insert("", "end", values=row, tags=(tag,))

            # Ghi nhận ô cực trị cần tô màu
            if tag_column_idx is not None and tag_column_idx < len(row):
                cell_info = self._highlight_for_row(row, str(row[tag_column_idx]).strip())
                if cell_info:
                    self._cell_highlights[item_id] = cell_info

        self.after(40, self._update_dividers)
        self.after(50, self._schedule_update_overlays)

    def _map_extreme_to_col(self, ext_type: str) -> Optional[str]:
        """Loại cực trị → tên cột của bảng này (khớp tiền tố nếu tên cột khác)."""
        col_target = EXTREME_TO_COLUMN.get(ext_type)
        if not col_target:
            return None
        if col_target in self._columns:
            return col_target
        prefix = col_target.split()[0]
        for col in self._columns:
            if col.split()[0] == prefix:
                return col
        return None

    def _highlight_for_row(self, row, ext_type: str) -> Optional[tuple[str, str, str]]:
        """(cột, nền, chữ) cho ô cực trị của 1 dòng — màu theo dấu giá trị."""
        col = self._map_extreme_to_col(ext_type)
        if not col:
            return None
        idx = self._columns.index(col)
        value = row[idx] if idx < len(row) else None
        bg, fg = sign_colors(value)
        return (col, bg, fg)

    # ══════════════════════════════════════════════════════════
    # TƯƠNG TÁC Ô VÀ MENU CHUỘT PHẢI
    # ══════════════════════════════════════════════════════════

    def _identify_cell(self, event) -> Optional[tuple[str, int, str]]:
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return None

        row_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)
        if not row_id or not col_id:
            return None

        try:
            col_idx = int(col_id.replace("#", "")) - 1
            disp_cols = self.get_display_columns()
            if 0 <= col_idx < len(disp_cols):
                col_name = disp_cols[col_idx]
                real_idx = self._columns.index(col_name) if col_name in self._columns else col_idx
                vals = self.tree.item(row_id, "values")
                val = vals[real_idx] if real_idx < len(vals) else ""
                return (row_id, col_idx, str(val))
        except Exception:
            pass
        return None

    def _is_load_source_column(self, col_name: str) -> bool:
        return "Nguồn Tải" in (col_name or "")

    def _on_cell_click(self, event):
        """Bấm ô Nguồn Tải → gọi callback (popup chọn lại), các ô khác chọn hàng."""
        info = self._identify_cell(event)
        if not info or not self.on_load_source_click:
            return
        row_id, col_idx, val = info
        disp_cols = self.get_display_columns()
        col_name = disp_cols[col_idx] if col_idx < len(disp_cols) else ""
        if not self._is_load_source_column(col_name):
            return
        vals = self.tree.item(row_id, "values")
        try:
            row_index = list(self.tree.get_children()).index(row_id)
        except ValueError:
            row_index = -1
        self.tree.selection_set(row_id)
        self.tree.focus(row_id)
        self.on_load_source_click(
            row_id=row_id,
            row_index=row_index,
            col_name=col_name,
            current_value=val,
            row_values=vals,
            event=event,
        )
        return "break"

    def _on_cell_double_click(self, event):
        info = self._identify_cell(event)
        if info:
            row_id, col_idx, val = info
            disp_cols = self.get_display_columns()
            col_name = disp_cols[col_idx] if col_idx < len(disp_cols) else ""
            if self._is_load_source_column(col_name):
                return "break"
            self._copy_cell_value(val, col_name)

    def update_row_values(self, row_id: str, values: tuple):
        """Cập nhật 1 hàng (sau khi chọn lại nguồn tải) và tô màu lại."""
        if not row_id or not self.tree.exists(row_id):
            return
        self.tree.item(row_id, values=values)
        try:
            idx = list(self.tree.get_children()).index(row_id)
        except ValueError:
            idx = -1
        if 0 <= idx < len(self._data_rows):
            self._data_rows[idx] = tuple(values)

        ext_idx = None
        for i, col in enumerate(self._columns):
            if col in ("Cực Trị", "Điều kiện"):
                ext_idx = i
                break
        if ext_idx is not None and ext_idx < len(values):
            cell_info = self._highlight_for_row(values, str(values[ext_idx]).strip())
            if cell_info:
                self._cell_highlights[row_id] = cell_info
            else:
                self._cell_highlights.pop(row_id, None)
        self._schedule_update_overlays()

    def _build_context_menu(self):
        self.menu = tk.Menu(self, tearoff=0, font=("Segoe UI", 10))

    def _build_header_menu(self):
        self.header_menu = tk.Menu(self, tearoff=0, font=("Segoe UI", 10))

    def _on_right_click(self, event):
        region = self.tree.identify("region", event.x, event.y)

        # Menu trên tiêu đề cột
        if region == "heading":
            col_id = self.tree.identify_column(event.x)
            try:
                col_idx = int(col_id.replace("#", "")) - 1
                disp_cols = self.get_display_columns()
                if 0 <= col_idx < len(disp_cols):
                    col_name = disp_cols[col_idx]
                    self._show_header_menu(event, col_name, col_idx)
                    return
            except Exception:
                pass

        # Menu trên ô dữ liệu
        info = self._identify_cell(event)
        self.menu.delete(0, "end")

        if info:
            self._selected_cell_info = info
            row_id, col_idx, cell_val = info
            disp_cols = self.get_display_columns()
            col_name = disp_cols[col_idx] if col_idx < len(disp_cols) else ""

            # 1. Sao chép ô
            display_val = cell_val if len(cell_val) < 25 else cell_val[:22] + "..."
            self.menu.add_command(
                label=f"Sao chép ô:  \"{display_val}\"",
                command=lambda: self._copy_cell_value(cell_val, col_name),
            )
            # 2. Sao chép cả cột dọc
            self.menu.add_command(
                label=f"Sao chép cả cột dọc:  [{col_name}]",
                command=lambda: self.copy_column(col_name),
            )
            self.menu.add_separator()

        # 3. Di chuyển hàng lên / xuống
        selected = self.tree.selection()
        if selected:
            self.menu.add_command(
                label="Di chuyển hàng lên trên (Alt+Up)",
                command=lambda: self.move_selected_row("up"),
            )
            self.menu.add_command(
                label="Di chuyển hàng xuống dưới (Alt+Down)",
                command=lambda: self.move_selected_row("down"),
            )
            self.menu.add_separator()

        # 4. Sao chép các cột lực
        self.menu.add_command(
            label="Sao chép các cột nội lực (Paste vào Excel)",
            command=self.copy_force_columns,
        )
        self.menu.add_separator()

        # 5. Sao chép hàng / toàn bộ bảng
        if selected:
            self.menu.add_command(
                label=f"Sao chép {len(selected)} hàng đang chọn",
                command=self._copy_selected_rows,
            )

        self.menu.add_command(
            label="Sao chép toàn bộ bảng (chỉ số liệu)",
            command=lambda: self.copy_all(include_headers=False),
        )
        self.menu.add_command(
            label="Sao chép toàn bộ bảng (kèm tiêu đề)",
            command=lambda: self.copy_all(include_headers=True),
        )

        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _show_header_menu(self, event, col_name: str, col_idx: int):
        self.header_menu.delete(0, "end")
        disp_cols = self.get_display_columns()

        self.header_menu.add_command(
            label=f"Cột: [{col_name}]",
            state="disabled",
        )
        self.header_menu.add_separator()

        if col_idx > 0:
            self.header_menu.add_command(
                label="Chuyển sang trái",
                command=lambda: self.move_column(col_name, col_idx - 1),
            )
            self.header_menu.add_command(
                label="Chuyển về trước",
                command=lambda: self.move_column(col_name, "start"),
            )

        if col_idx < len(disp_cols) - 1:
            self.header_menu.add_command(
                label="Chuyển sang phải",
                command=lambda: self.move_column(col_name, col_idx + 1),
            )
            self.header_menu.add_command(
                label="Chuyển về sau",
                command=lambda: self.move_column(col_name, "end"),
            )

        self.header_menu.add_separator()
        self.header_menu.add_command(
            label="Đặt lại thứ tự mặc định",
            command=lambda: self.set_display_columns(self._columns),
        )

        try:
            self.header_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.header_menu.grab_release()

    def _copy_cell_value(self, val: str, col_name: str):
        self._copy_to_clipboard(val)
        self._notify(f"📋 Đã sao chép ô [{col_name}]: {val}")

    # ══════════════════════════════════════════════════════════
    # CÁC HÀM SAO CHÉP NHANH (CLIPBOARD)
    # ══════════════════════════════════════════════════════════

    def copy_column(self, col_name: str):
        if col_name not in self._columns:
            return

        col_idx = self._columns.index(col_name)
        values = []

        for row in self._data_rows:
            if col_idx < len(row):
                values.append(str(row[col_idx]))

        text = "\n".join(values)
        self._copy_to_clipboard(text)
        self._notify(f"📋 Đã sao chép cột dọc '{col_name}' ({len(values)} giá trị) vào clipboard!")

    def copy_force_columns(self, max_cols: Optional[int] = None):
        """Sao chép khối các cột lực theo đúng thứ tự đang hiển thị trên bảng."""
        if not self._data_rows:
            self._notify("Chưa có dữ liệu để sao chép!")
            return

        disp_cols = self.get_copy_columns()
        disp_force_cols = [c for c in disp_cols if is_force_column(c)]

        if not disp_force_cols:
            disp_force_cols = [c for c in disp_cols if c not in ("STT", "Điều kiện")]

        if max_cols is not None and len(disp_force_cols) > max_cols:
            disp_force_cols = disp_force_cols[:max_cols]

        indices = [self._columns.index(c) for c in disp_force_cols if c in self._columns]

        lines = []
        for row in self._data_rows:
            line_vals = [str(row[i]) if i < len(row) else "" for i in indices]
            lines.append("\t".join(line_vals))

        text = "\n".join(lines)
        self._copy_to_clipboard(text)
        col_list_str = ", ".join(disp_force_cols)
        num_c = len(disp_force_cols)
        self._notify(f"Đã sao chép {num_c} cột lực ({col_list_str}) ({len(self._data_rows)} hàng) vào clipboard!")

    def copy_all(self, include_headers: bool = True):
        if not self._data_rows:
            self._notify("Chưa có dữ liệu để sao chép!")
            return

        disp_cols = self.get_copy_columns()
        indices = [self._columns.index(c) for c in disp_cols if c in self._columns]

        lines = []
        if include_headers:
            lines.append("\t".join(disp_cols))

        for row in self._data_rows:
            line_vals = [str(row[i]) if i < len(row) else "" for i in indices]
            lines.append("\t".join(line_vals))

        text = "\n".join(lines)
        self._copy_to_clipboard(text)
        mode_str = "kèm tiêu đề" if include_headers else "chỉ số liệu"
        self._notify(f"📋 Đã sao chép toàn bộ bảng ({len(self._data_rows)} dòng, {mode_str}) vào clipboard!")

    def _copy_selected_rows(self):
        selected = self.tree.selection()
        if not selected:
            self.copy_all(include_headers=False)
            return

        disp_cols = self.get_copy_columns()
        indices = [self._columns.index(c) for c in disp_cols if c in self._columns]

        lines = []
        for item in selected:
            vals = self.tree.item(item, "values")
            line_vals = [str(vals[i]) if i < len(vals) else "" for i in indices]
            lines.append("\t".join(line_vals))

        text = "\n".join(lines)
        self._copy_to_clipboard(text)
        self._notify(f"📋 Đã sao chép {len(selected)} hàng vào clipboard!")

    def _copy_selection(self, event=None):
        self._copy_selected_rows()

    def _copy_to_clipboard(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)

    def _notify(self, msg: str):
        if self.status_callback:
            self.status_callback(msg)

    def get_row_count(self) -> int:
        return len(self._data_rows)

    def clear(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for o in self._cell_overlays:
            try:
                o.destroy()
            except Exception:
                pass
        self._cell_overlays.clear()
        self._cell_highlights.clear()
        self._data_rows = []
        self._selected_cell_info = None
        self._detached_items.clear()
        for d in self._dividers:
            try:
                d.destroy()
            except Exception:
                pass
        self._dividers.clear()


# ═══════════════════════════════════════════════════════════
# THANH TRẠNG THÁI
# ═══════════════════════════════════════════════════════════

class StatusBar(ttk.Frame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self._label = ttk.Label(
            self,
            text="Sẵn sàng",
            anchor="w",
            padding=(8, 4),
            font=("Segoe UI", 10),
        )
        self._label.pack(fill="x", expand=True)

    def set_text(self, text: str, is_error: bool = False):
        self._label.config(text=text)
        if is_error:
            self._label.config(foreground="#DC2626")
        else:
            self._label.config(foreground="")

    def clear(self):
        self._label.config(text="Sẵn sàng", foreground="")


# ═══════════════════════════════════════════════════════════
# POPOVER CHỌN NGUỒN TẢI (chỉ hiện khi bấm)
# ═══════════════════════════════════════════════════════════

class LoadSourcePicker:
    """
    Ô chọn nguồn tải dạng popover: ẩn mặc định, chỉ hiện khi bấm.
    Modal không chọn được. Mặc định tick các nguồn có LRFD.
    """

    def __init__(
        self,
        master,
        names: list[str],
        selected: list[str],
        modal_names: Optional[set[str]] = None,
        on_apply: Optional[Callable[[list[str]], None]] = None,
        title: str = "Chọn nguồn tải",
        allow_non_lrfd: bool = True,
        single_select: bool = False,
        hint: Optional[str] = None,
    ):
        if ctk is None:
            raise RuntimeError("Cần customtkinter")

        self._names = list(names)
        self._selected = set(selected)
        self._modal = set(modal_names or ())
        self._on_apply = on_apply
        self._single = single_select
        self._allow_non_lrfd = allow_non_lrfd
        self._closed = False

        self.win = ctk.CTkToplevel(master)
        self.win.title(title)
        if single_select:
            self.win.geometry("420x320")
            self.win.minsize(320, 240)
        else:
            self.win.geometry("460x420")
            self.win.minsize(360, 280)
        self.win.transient(master)
        self.win.resizable(True, True)
        self.win.attributes("-topmost", True)
        self.win.protocol("WM_DELETE_WINDOW", self._close)

        try:
            self.win.grab_set()
        except Exception:
            pass

        if hint is None:
            hint = (
                "Modal không dùng cho thiết kế. Mặc định chỉ LRFD — "
                "tick thêm nếu cần tải khác."
                if allow_non_lrfd else
                "Chọn 1 nguồn tải cho dòng này."
            )
        ctk.CTkLabel(
            self.win, text=hint, font=("Segoe UI", 11),
            text_color="#475569", wraplength=430, justify="left",
        ).pack(fill="x", padx=10, pady=(8, 4))

        tool = ctk.CTkFrame(self.win, fg_color="transparent")
        tool.pack(fill="x", padx=10, pady=(0, 4))

        self._var_search = ctk.StringVar(value="")
        self._entry = ctk.CTkEntry(
            tool, textvariable=self._var_search, placeholder_text="Tìm tên nguồn tải...",
            width=180, height=28, font=("Segoe UI", 12),
        )
        self._entry.pack(side="left", padx=(0, 6))

        if not single_select:
            ctk.CTkButton(
                tool, text="Chỉ LRFD", width=78, height=28, font=("Segoe UI", 11),
                fg_color="#2563EB", command=self._select_lrfd_only,
            ).pack(side="left", padx=2)
            ctk.CTkButton(
                tool, text="Đang lọc", width=72, height=28, font=("Segoe UI", 11),
                fg_color="#64748B", command=self._select_visible,
            ).pack(side="left", padx=2)
            ctk.CTkButton(
                tool, text="Bỏ chọn", width=70, height=28, font=("Segoe UI", 11),
                fg_color="#94A3B8", command=self._clear_visible,
            ).pack(side="left", padx=2)

        self._lbl_count = ctk.CTkLabel(
            self.win, text="", font=("Segoe UI", 11, "bold"),
        )
        self._lbl_count.pack(anchor="w", padx=12, pady=(0, 2))

        list_frame = tk.Frame(self.win, bg="#FFFFFF", highlightbackground="#CBD5E1",
                              highlightthickness=1)
        list_frame.pack(fill="both", expand=True, padx=10, pady=4)

        self._list = tk.Listbox(
            list_frame,
            selectmode=tk.SINGLE if single_select else tk.EXTENDED,
            font=("Segoe UI", 10),
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            bg="#FFFFFF",
            fg="#0F172A",
            selectbackground="#2563EB",
            selectforeground="#FFFFFF",
        )
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self._list.yview)
        self._list.configure(yscrollcommand=vsb.set)
        self._list.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._list.bind("<Double-Button-1>", lambda e: self._apply())
        self._var_search.trace_add("write", lambda *_: self._rebuild_list())

        btn_bar = ctk.CTkFrame(self.win, fg_color="transparent")
        btn_bar.pack(fill="x", padx=10, pady=(4, 10))

        ctk.CTkButton(
            btn_bar, text="Đóng", width=90, height=30, font=("Segoe UI", 12),
            fg_color="#94A3B8", hover_color="#64748B",
            command=self._close,
        ).pack(side="right", padx=4)
        ctk.CTkButton(
            btn_bar, text="Áp dụng", width=110, height=30, font=("Segoe UI", 12, "bold"),
            fg_color="#059669", hover_color="#047857",
            command=self._apply,
        ).pack(side="right", padx=4)

        self._visible: list[str] = []
        self._rebuild_list()
        self._entry.focus_set()

    def place_near(self, widget=None, x_root: Optional[int] = None, y_root: Optional[int] = None):
        try:
            if widget is not None:
                x = widget.winfo_rootx()
                y = widget.winfo_rooty() + widget.winfo_height()
            elif x_root is not None and y_root is not None:
                x, y = x_root, y_root
            else:
                return
            self.win.geometry(f"+{int(x)}+{int(y)}")
        except Exception:
            pass

    def _is_modal(self, name: str) -> bool:
        from sap2000_connector import is_modal_load
        return name in self._modal or is_modal_load(name)

    def _filtered_names(self) -> list[str]:
        q = (self._var_search.get() or "").strip().lower()
        out = []
        for n in self._names:
            if self._is_modal(n):
                continue
            if q and q not in n.lower():
                continue
            out.append(n)
        return out

    def _sync_selected_from_listbox(self):
        if not getattr(self, "_visible", None) or not getattr(self, "_list", None):
            return
        visible_set = set(self._visible)
        in_box = {
            self._visible[i]
            for i in self._list.curselection()
            if 0 <= i < len(self._visible)
        }
        self._selected = (self._selected - visible_set) | in_box

    def _rebuild_list(self, keep_selected: bool = True):
        from sap2000_connector import is_lrfd_load
        if not hasattr(self, "_list"):
            return
        if keep_selected:
            self._sync_selected_from_listbox()
        self._list.delete(0, tk.END)
        self._visible = self._filtered_names()
        for i, name in enumerate(self._visible):
            tag = "LRFD" if is_lrfd_load(name) else "khác"
            self._list.insert(tk.END, f"[{tag}]  {name}")
            if name in self._selected:
                self._list.selection_set(i)
        n_all = len([n for n in self._names if not self._is_modal(n)])
        n_sel = len(self._selected)
        n_modal = len([n for n in self._names if self._is_modal(n)])
        extra = f"  ·  ẩn {n_modal} Modal" if n_modal else ""
        self._lbl_count.configure(
            text=f"Đã chọn {n_sel} / {n_all} nguồn{extra}"
        )

    def _current_selection(self) -> list[str]:
        idxs = self._list.curselection()
        picked = [self._visible[i] for i in idxs if 0 <= i < len(self._visible)]
        if self._single:
            return picked[:1]
        hidden_selected = [
            n for n in self._selected
            if n not in self._visible and not self._is_modal(n)
        ]
        # Giữ lựa chọn đang bị ẩn bởi ô tìm
        ordered = []
        seen = set()
        for n in picked + hidden_selected:
            if n not in seen:
                ordered.append(n)
                seen.add(n)
        return ordered

    def _select_lrfd_only(self):
        from sap2000_connector import is_lrfd_load
        self._selected = {
            n for n in self._names
            if is_lrfd_load(n) and not self._is_modal(n)
        }
        self._rebuild_list(keep_selected=False)

    def _select_visible(self):
        self._list.selection_set(0, tk.END)
        self._selected = set(self._current_selection())
        self._lbl_count.configure(
            text=f"Đã chọn {len(self._selected)} / "
                 f"{len([n for n in self._names if not self._is_modal(n)])} nguồn"
        )

    def _clear_visible(self):
        self._list.selection_clear(0, tk.END)
        hidden = [n for n in self._selected if n not in self._visible]
        self._selected = set(hidden)

    def _apply(self):
        self._sync_selected_from_listbox()
        if self._single:
            idxs = self._list.curselection()
            if idxs and 0 <= idxs[0] < len(self._visible):
                chosen = [self._visible[idxs[0]]]
            else:
                chosen = [n for n in self._names if n in self._selected][:1]
        else:
            chosen = [n for n in self._names if n in self._selected and not self._is_modal(n)]
        if self._on_apply:
            self._on_apply(chosen)
        self._close()

    def _close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.win.grab_release()
        except Exception:
            pass
        try:
            self.win.destroy()
        except Exception:
            pass
