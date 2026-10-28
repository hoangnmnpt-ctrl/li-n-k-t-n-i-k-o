"""
results_view.py — Cửa sổ "Results" theo form báo cáo RAM Connection (tiếng Anh): Current Date · Units system ·
Steel connections / Results · Connection, Family, Type, Members · Design code · Demands · Geometric considerations ·
(Plate behavior) · Design check (nhóm, Verification · Unit · Capacity · Demand · Ctrl EQ · Ratio · References) ·
Global critical strength ratio. Bảng dựng trên Canvas: tiêu đề cột nền xám, dòng nhóm nền xám nhạt, tỷ số > 1 màu đỏ.

Nhấp một dòng Design check → khung dưới cùng hiện diễn giải công thức bằng tiếng Việt, bộ phận liên quan được tô sáng trên hình 3D.
"""

from __future__ import annotations

import math
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

PAGE = "#FFFFFF"
HEAD_BG, GROUP_BG, GRID = "#D9D9D9", "#F2F2F2", "#BFBFBF"
SEL_BG = "#FFE7B3"
TXT, DIM, OK_C, BAD_C, TITLE_C = "#000000", "#595959", "#2E7D32", "#C00000", "#2E7D32"
PAD = 24


class ResultsWindow(tk.Toplevel):
    def __init__(self, master, rep: dict, RP, checks: list, on_select=None, title=""):
        super().__init__(master)
        self.title(title or "Results")
        self.geometry("1180x800")
        self.rep, self.RP, self.on_select = rep, RP, on_select
        self.byid = {c["id"]: c for c in checks}
        self.f = tkfont.Font(family="Arial", size=9)
        self.fb = tkfont.Font(family="Arial", size=9, weight="bold")
        self.fh = tkfont.Font(family="Arial", size=12, weight="bold")
        self.ft = tkfont.Font(family="Arial", size=16, weight="bold")
        self.fs = tkfont.Font(family="Arial", size=8)
        pan = ttk.PanedWindow(self, orient="vertical"); pan.pack(fill="both", expand=True)
        top = tk.Frame(pan, bg=PAGE); pan.add(top, weight=4)
        self.cv = tk.Canvas(top, bg=PAGE, highlightthickness=0)
        ys = ttk.Scrollbar(top, orient="vertical", command=self.cv.yview)
        xs = ttk.Scrollbar(top, orient="horizontal", command=self.cv.xview)
        self.cv.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        ys.pack(side="right", fill="y"); xs.pack(side="bottom", fill="x"); self.cv.pack(fill="both", expand=True)
        self.cv.bind("<MouseWheel>", lambda e: self.cv.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        self.cv.bind("<Button-4>", lambda e: self.cv.yview_scroll(-1, "units"))
        self.cv.bind("<Button-5>", lambda e: self.cv.yview_scroll(1, "units"))
        # khung diễn giải tiếng Việt (giữ như cũ)
        self.det = tk.Text(pan, height=10, font=("Consolas", 10), wrap="word", padx=8, pady=6)
        pan.add(self.det, weight=1)
        self.det.insert("end", "Nhấp một dòng trong Design check để xem diễn giải công thức (tiếng Việt).")
        self.det.configure(state="disabled")
        self.row_boxes = {}
        self._sel = None
        self.draw()

    # ───────────────────────── vẽ ─────────────────────────
    def _text(self, x, y, s, font=None, color=TXT, anchor="nw"):
        return self.cv.create_text(x, y, text=s, font=font or self.f, fill=color, anchor=anchor)

    def _widths(self, head, rows, minw=None):
        n = len(head)
        w = [self.fb.measure(h) + 14 for h in head]
        for r in rows:
            if isinstance(r, str): continue
            for i in range(n):
                w[i] = max(w[i], self.f.measure(str(r[i])) + 14)
        if minw:
            w = [max(a, b) for a, b in zip(w, list(minw) + [0] * (n - len(minw)))]
        return w

    def _table(self, y, head, rows, widths, align=None, ids=None, ratio_col=None):
        cv = self.cv
        x0 = PAD
        H = self.f.metrics("linespace") + 8
        W = sum(widths)
        cv.create_rectangle(x0, y, x0 + W, y + H, fill=HEAD_BG, outline=GRID)
        x = x0
        for h, w in zip(head, widths):
            cv.create_line(x, y, x, y + H, fill=GRID)
            self._text(x + w / 2, y + H / 2, h, self.fb, anchor="center")
            x += w
        y += H
        for k, r in enumerate(rows):
            if isinstance(r, str):
                cv.create_rectangle(x0, y, x0 + W, y + H, fill=GROUP_BG, outline=GRID)
                self._text(x0 + 6, y + H / 2, r, self.fb, anchor="w")
                y += H; continue
            rid = ids[k] if ids else None
            bg = cv.create_rectangle(x0, y, x0 + W, y + H, fill=PAGE, outline=GRID, tags=(f"row_{rid}",) if rid else ())
            x = x0
            for i, w in enumerate(widths):
                cv.create_line(x, y, x, y + H, fill=GRID)
                s = str(r[i])
                col = TXT
                if ratio_col is not None and i == ratio_col and len(r) > 7:
                    col = DIM if r[8] else (BAD_C if r[7] > 1.0001 else TXT)
                if i == 5 and len(r) == 7 and s in ("OK", "N.G."):
                    col = BAD_C if s == "N.G." else TXT
                a = (align or ["w"] * len(widths))[i]
                tx = x + 6 if a == "w" else (x + w - 6 if a == "e" else x + w / 2)
                self._text(tx, y + H / 2, s, self.f, col, anchor=a if a != "c" else "center")
                x += w
            if rid:
                self.row_boxes[rid] = bg
                for item in cv.find_overlapping(x0 + 1, y + 1, x0 + W - 1, y + H - 1):
                    cv.tag_bind(item, "<Button-1>", lambda e, rid=rid: self.select(rid))
                    cv.itemconfigure(item, tags=tuple(cv.gettags(item)) + ("clickable",))
            y += H
        return y

    def draw(self):
        cv, rep = self.cv, self.rep
        cv.delete("all")
        self.row_boxes = {}
        y = PAD
        self._text(PAD, y, f"Current Date: {rep['date']}", self.fs, DIM); y += 16
        self._text(PAD, y, "Units system: SI", self.fs, DIM); y += 16
        if rep.get("file"):
            self._text(PAD, y, f"File name: {rep['file']}", self.fs, DIM); y += 16
        y += 10
        self._text(PAD, y, "Steel connections", self.ft, TITLE_C); y += 30
        self._text(PAD, y, "Results", self.fh); y += 30
        self._text(PAD, y, f"Connection:  {rep['name']}", self.fh); y += 24
        for line in self._header_lines():
            self._text(PAD, y, line); y += 17
        y += 8
        self._text(PAD, y, f"Design code: {rep['code']}", self.fb); y += 28

        RP = self.RP
        # Demands
        self._text(PAD, y, "Demands", self.fh); y += 24
        dh = getattr(RP, "DEM_HEAD", [])
        y = self._table(y, dh, rep["demands"], self._widths(dh, rep["demands"]), ["w"] + ["e"] * (len(dh) - 2) + ["w"]) + 26
        # Geometric considerations
        self._text(PAD, y, "Geometric considerations", self.fh); y += 24
        grows = []
        for grp, rr in rep["geo"].items():
            grows.append(grp); grows += rr
        gh = getattr(RP, "GEO_HEAD", ["Dimensions", "Unit", "Value", "Min.", "Max.", "Sta.", "References"])
        y = self._table(y, gh, grows, self._widths(gh, grows, [320]), ["w", "c", "e", "e", "e", "c", "w"]) + 26
        # Plate behavior (knee / splice)
        if rep.get("behavior"):
            self._text(PAD, y, "Plate behavior", self.fh); y += 24
            for a, b in rep["behavior"]:
                self._text(PAD, y, a, self.fb); y += 16
                self._text(PAD + 12, y, b); y += 20
            y += 10
        # Design check
        self._text(PAD, y, "Design check", self.fh); y += 24
        crows, ids = [], []
        for grp, rr in rep["checks"]:
            crows.append(grp); ids.append(None)
            for r in rr:
                crows.append(r); ids.append(r[9] if len(r) > 9 else None)
        ch = getattr(RP, "CHK_HEAD", ["Verification", "Unit", "Capacity", "Demand", "Ctrl EQ", "Ratio", "References"])
        y = self._table(y, ch, crows, self._widths(ch, crows, [320]), ["w", "c", "e", "e", "w", "e", "w"], ids, ratio_col=5) + 22
        r = rep["ratio"]
        ok = r <= 1.0001
        self._text(PAD, y, "Global critical strength ratio", self.fh)
        self._text(PAD + 330, y, "INF" if math.isinf(r) else f"{r:.2f}", self.fh, OK_C if ok else BAD_C)
        y += 34
        if rep.get("warnings"):
            self._text(PAD, y, "Notes", self.fb); y += 18
            for w in rep["warnings"]:
                self._text(PAD, y, "• " + w, self.fs, DIM); y += 15
        bb = cv.bbox("all") or (0, 0, 800, y)
        cv.configure(scrollregion=(0, 0, bb[2] + PAD, y + PAD))
        cv.tag_bind("clickable", "<Enter>", lambda e: cv.configure(cursor="hand2"))
        cv.tag_bind("clickable", "<Leave>", lambda e: cv.configure(cursor=""))

    def _header_lines(self):
        rep = self.rep
        out = [f"Family: {rep['family']}", f"Type: {rep['type']}"]
        m = rep.get("members")
        if isinstance(m, list):
            out += [f"{k}: {v}" for k, v in m]
        elif isinstance(m, dict):
            for k, v in m.items():
                if isinstance(v, dict):
                    v = v.get("text") or v.get("sec") or ""
                elif isinstance(v, float):
                    v = f"{v:g}"
                if v not in ("", None, "0"):
                    out.append(f"{k.capitalize()}: {v}")
        return out

    # ───────────────────────── chọn dòng ─────────────────────────
    def select(self, rid):
        if self._sel in self.row_boxes:
            self.cv.itemconfigure(self.row_boxes[self._sel], fill=PAGE)
        self._sel = rid
        if rid in self.row_boxes:
            self.cv.itemconfigure(self.row_boxes[rid], fill=SEL_BG)
        c = self.byid.get(rid)
        self.det.configure(state="normal"); self.det.delete("1.0", "end")
        if c:
            r = c["ratio"]
            self.det.insert("end", f"{c['name']}  —  {c['ref']}\nCapacity = {c['cap']:.2f} {c['unit']};  Demand = {abs(c['dem']):.2f} {c['unit']};"
                                   f"  Ratio = {'∞' if math.isinf(r) else format(r, '.3f')}  ({c['combo']})\n\n" + "\n".join(c["detail"]))
            if self.on_select:
                self.on_select(set(c.get("tags", ())))
        self.det.configure(state="disabled")
