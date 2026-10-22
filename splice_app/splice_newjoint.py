"""
splice_newjoint.py — Hộp thoại "New joint" kiểu RAM Connection (nhóm liên kết bên trái, kiểu nút bên phải, mã BS/CS góc phải).
Chỉ các kiểu đã có engine mới chọn được; kiểu còn lại hiện mờ kèm ghi chú "chưa hỗ trợ".
"""

from __future__ import annotations

import tkinter as tk

BG_DLG = "#FFFFFF"
BG_GROUP = "#8A95A3"
BG_JOINTS = "#D3D7DB"
ORANGE = "#F5823A"
TILE_BG = "#EDEDED"
TILE_BORDER = "#B8BCC0"

# (nhóm) → [(tên, mã, key kiểu engine hoặc None nếu chưa hỗ trợ, icon)]
GROUPS = [
    ("Beam to support", "Beam to support", []),
    ("Splices", "Splices", [
        ("Beam splice", "BS", "straight", "splice"),
        ("Apex", "BS", "apex", "apex"),
        ("Apex with haunched beams", "BS", None, "apex_h"),
        ("Tapered beam splice", "BS", None, "tapered"),
        ("Column splice", "CS", None, "col"),
    ]),
    ("Column top and base", "Column top and base", []),
    ("Vertical bracing", "Vertical bracing", []),
    ("Horizontal bracing", "Horizontal bracing", []),
    ("Trusses", "Trusses", []),
]


def _icon(cv: tk.Canvas, kind: str, x: int, y: int, w: int = 64, h: int = 44):
    """Biểu tượng nét đơn giản cho từng nhóm / kiểu nút."""
    c = "#2B2F36"
    if kind in ("splice", "tapered"):
        top = 10 if kind == "splice" else 14
        cv.create_rectangle(x, y + 12, x + w / 2 - 3, y + h - 12, outline=c, fill="#FFFFFF")
        cv.create_rectangle(x + w / 2 + 3, y + 12 + (top - 10) // 2, x + w, y + h - 12 - (top - 10) // 2, outline=c, fill="#FFFFFF")
        cv.create_line(x + w / 2, y + 8, x + w / 2, y + h - 8, fill=c, width=2)
    elif kind in ("apex", "apex_h"):
        cv.create_polygon(x, y + 26, x + w / 2 - 3, y + 14, x + w / 2 - 3, y + 30, x, y + 42, outline=c, fill="#FFFFFF")
        cv.create_polygon(x + w, y + 26, x + w / 2 + 3, y + 14, x + w / 2 + 3, y + 30, x + w, y + 42, outline=c, fill="#FFFFFF")
        if kind == "apex_h":
            cv.create_line(x + 6, y + 38, x + w / 2 - 3, y + 26, x + w - 6, y + 38, fill=c)
    elif kind == "col":
        cv.create_rectangle(x + w / 2 - 9, y + 2, x + w / 2 + 9, y + h / 2 - 1, outline=c, fill="#FFFFFF")
        cv.create_rectangle(x + w / 2 - 9, y + h / 2 + 1, x + w / 2 + 9, y + h - 2, outline=c, fill="#FFFFFF")
    elif kind == "vbrace":
        cv.create_rectangle(x + 2, y + 2, x + 12, y + h - 2, outline=c, fill="#FFFFFF")
        cv.create_line(x + 12, y + h - 14, x + w, y + h - 14, fill=c, width=2)
        cv.create_line(x + 14, y + h - 18, x + w - 6, y + 4, fill=c, width=6)
        cv.create_line(x + 14, y + h - 18, x + w - 6, y + 4, fill="#FFFFFF", width=3)
    elif kind == "hbrace":
        cv.create_rectangle(x + 2, y + 2, x + 10, y + h - 2, outline=c, fill="#FFFFFF")
        cv.create_line(x + 10, y + h - 8, x + w, y + h - 8, fill=c, width=4, dash=(4, 2))
        cv.create_line(x + 14, y + h - 14, x + w - 6, y + 6, fill=c, width=6)
        cv.create_line(x + 14, y + h - 14, x + w - 6, y + 6, fill="#FFFFFF", width=3)
    elif kind == "truss":
        cv.create_rectangle(x, y + h - 14, x + w, y + h - 4, outline=c, fill="#FFFFFF")
        for a, b in ((x + w / 2 - 4, x + 6), (x + w / 2 + 4, x + w - 6)):
            cv.create_line(a, y + h - 14, b, y + 4, fill=c, width=6)
            cv.create_line(a, y + h - 14, b, y + 4, fill="#FFFFFF", width=3)
    else:
        cv.create_rectangle(x + 6, y + 6, x + 22, y + h - 6, outline=c, fill="#FFFFFF")
        cv.create_line(x + 22, y + 20, x + w, y + 20, fill=c, width=2)


class NewJointDialog(tk.Toplevel):
    """Trả kết quả qua self.result = key kiểu ('straight' | 'apex') hoặc None nếu huỷ."""

    def __init__(self, master, current: str = "straight"):
        super().__init__(master)
        self.title("New joint")
        self.configure(bg=BG_DLG)
        self.geometry("910x690")
        self.minsize(760, 560)
        self.transient(master)
        self.result = None
        self.group = 1
        self.sel = next((i for i, j in enumerate(GROUPS[1][2]) if j[2] == current), 0)
        self._build()
        self._refresh()
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.after(50, lambda: (self.grab_set(), self.focus_set()))

    # ------------------------------------------------------------------
    def _build(self):
        head = tk.Frame(self, bg=BG_DLG)
        head.pack(fill="x")
        self.lbl_title = tk.Label(head, text="", bg=BG_DLG, fg="#8A8F96", font=("Segoe UI", 12))
        self.lbl_title.pack(pady=(10, 4))
        self.lbl_sel = tk.Label(head, text="", bg=BG_DLG, fg="#1B2430", font=("Segoe UI", 10), anchor="w")
        self.lbl_sel.pack(fill="x", padx=14, pady=(2, 8))
        tk.Frame(self, bg="#C9CDD2", height=1).pack(fill="x")

        body = tk.Frame(self, bg="#E9EBED")
        body.pack(fill="both", expand=True, padx=12, pady=10)
        left = tk.Frame(body, bg=BG_GROUP, width=260)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Label(left, text="Joint group", bg=BG_GROUP, fg="#1B2430", font=("Segoe UI", 18)).pack(anchor="w", padx=14, pady=(14, 10))
        self.group_cv = []
        for i, (name, _t, _j) in enumerate(GROUPS):
            cv = tk.Canvas(left, width=228, height=70, bg=BG_GROUP, highlightthickness=0, cursor="hand2")
            cv.pack(padx=14, pady=3)
            cv.bind("<Button-1>", lambda e, i=i: self._pick_group(i))
            self.group_cv.append(cv)
        self.right = tk.Frame(body, bg=BG_JOINTS)
        self.right.pack(side="left", fill="both", expand=True)
        self.lbl_group = tk.Label(self.right, text="", bg=BG_JOINTS, fg="#1B2430", font=("Segoe UI", 18))
        self.lbl_group.pack(anchor="w", padx=22, pady=(14, 8))
        self.tiles = tk.Frame(self.right, bg=BG_JOINTS)
        self.tiles.pack(fill="both", expand=True, padx=18)

        foot = tk.Frame(self, bg=BG_DLG)
        foot.pack(fill="x", padx=14, pady=10)
        self.lbl_note = tk.Label(foot, text="", bg=BG_DLG, fg="#B45309", font=("Segoe UI", 9), anchor="w")
        self.lbl_note.pack(side="left")
        for txt, cmd, st in (("Help", self._help, "normal"), ("Cancel", self.destroy, "normal"), ("OK", self._ok, "normal"),
                             ("Data »", self._ok, "normal"), ("Joint", None, "disabled")):
            b = tk.Button(foot, text=txt, width=9, command=cmd, state=st, font=("Segoe UI", 9), relief="groove")
            b.pack(side="right", padx=5)

    # ------------------------------------------------------------------
    def _joints(self):
        return GROUPS[self.group][2]

    def _pick_group(self, i):
        self.group = i
        self.sel = 0
        self._refresh()

    def _refresh(self):
        for i, cv in enumerate(self.group_cv):
            cv.delete("all")
            on = i == self.group
            cv.create_rectangle(1, 1, 226, 68, fill=("#FFB777" if on else "#EDEDED"), outline=(ORANGE if on else "#B8BCC0"), width=(3 if on else 1))
            if on:
                for k in range(0, 224, 2):      # nền gradient cam nhạt
                    t = k / 224
                    col = "#%02X%02X%02X" % (int(255 - 20 * (1 - t)), int(183 + 55 * t), int(119 + 100 * t))
                    cv.create_line(2 + k, 3, 2 + k, 66, fill=col)
            kind = ["beam", "splice", "col", "vbrace", "hbrace", "truss"][i]
            _icon(cv, kind, 10, 12, 46, 44)
            cv.create_text(70, 35, text=GROUPS[i][1], anchor="w", font=("Segoe UI", 11), fill="#1B2430", width=150)
        self.lbl_group.configure(text=GROUPS[self.group][1])
        for w in self.tiles.winfo_children():
            w.destroy()
        js = self._joints()
        if not js:
            tk.Label(self.tiles, text="Nhóm liên kết này chưa được hỗ trợ trong tool.", bg=BG_JOINTS, fg="#4B5563", font=("Segoe UI", 11)).pack(anchor="w", pady=10)
        for i, (name, code, key, icon) in enumerate(js):
            cv = tk.Canvas(self.tiles, width=238, height=84, bg=BG_JOINTS, highlightthickness=0, cursor="hand2" if key else "arrow")
            cv.grid(row=i, column=0, sticky="w", pady=6)
            on = i == self.sel
            ok = key is not None
            fill = "#FFB777" if (on and ok) else TILE_BG
            cv.create_rectangle(2, 2, 236, 82, fill=fill, outline=(ORANGE if on else TILE_BORDER), width=(3 if on else 1))
            if on and ok:
                for k in range(0, 232, 2):
                    t = k / 232
                    cv.create_line(4 + k, 4, 4 + k, 80, fill="#%02X%02X%02X" % (int(255 - 20 * (1 - t)), int(183 + 55 * t), int(119 + 100 * t)))
            _icon(cv, icon, 12, 22, 60, 40)
            fg = "#1B2430" if ok else "#9AA0A6"
            cv.create_text(88, 42, text=name, anchor="w", width=120, font=("Segoe UI", 10), fill=fg)
            cv.create_text(228, 14, text=code, anchor="e", font=("Segoe UI", 11), fill=fg)
            cv.bind("<Button-1>", lambda e, i=i: self._pick(i))
            cv.bind("<Double-Button-1>", lambda e, i=i: (self._pick(i), self._ok()))
        self._header()

    def _pick(self, i):
        self.sel = i
        self._refresh()

    def _header(self):
        js = self._joints()
        if js and self.sel < len(js):
            name, code, key, _ = js[self.sel]
            self.lbl_title.configure(text=f"{code} - {name.replace('Beam splice', 'Beam Splice')}")
            self.lbl_sel.configure(text=f"Selected joint: {name}")
            self.lbl_note.configure(text="" if key else "Kiểu nút này chưa được hỗ trợ trong tool.")
        else:
            self.lbl_title.configure(text="")
            self.lbl_sel.configure(text="Selected joint: —")
            self.lbl_note.configure(text="")

    def _ok(self):
        js = self._joints()
        if js and self.sel < len(js) and js[self.sel][2]:
            self.result = js[self.sel][2]
            self.destroy()
        else:
            self.lbl_note.configure(text="Chọn Beam splice hoặc Apex — các kiểu khác chưa hỗ trợ.")

    def _help(self):
        self.lbl_note.configure(text="Beam splice: nối thẳng · Apex: đỉnh mái hai dầm nghiêng đối xứng.")


def ask(master, current: str = "straight"):
    d = NewJointDialog(master, current)
    master.wait_window(d)
    return d.result
