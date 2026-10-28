"""
results_view.py — Cửa sổ "Results" trình bày như báo cáo RAM Connection (tiếng Anh):
  Steel Connections / Results (giữa trang) · Connection · Family / Type giữa hai đường gạch đứt · Design code ·
  Demands (tiêu đề đậm, đơn vị chữ nhỏ dòng dưới, gạch đứt) · Design calculations → "Design for major axis" /
  "Base plate (AISC …)" · Geometric Considerations (nhóm chữ nghiêng đậm, Sta. = dấu ✔ xanh / ✘ đỏ) ·
  Design Check (Ratio đậm xanh / đỏ) · Ratio · dải xanh "Major axis": hình ứng suất ép bê tông và lực kéo neo + dải màu,
  bảng tóm tắt (áp lực, lực neo, trục trung hoà, chiều dài ép), Anchors tensions · Notes.
Không kẻ ô như RAM. Nhấp một dòng Design check → khung dưới cùng hiện diễn giải tiếng Việt, bộ phận liên quan sáng trên hình 3D.
"""

from __future__ import annotations

import math
import re
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

PAGE = "#FFFFFF"
TXT, OK_C, BAD_C = "#000000", "#2EAD2E", "#E00000"
BAND = "#C6D9F1"
SEL_BG = "#FFE7B3"
PLATE_G, FIG_BG, NAVY_C = "#C0C0C0", "#F7F7F7", "#00008B"
X0 = 6                                                         # lề trái trang
PW = 860                                                       # bề rộng trang
# dải màu RAM: 17 mức, từ lớn nhất (đỏ sẫm) xuống nhỏ nhất (xanh dương)
SCALE = ["#8B0000", "#C00000", "#FF0000", "#FF4500", "#FF8C00", "#FFB300", "#FFD700", "#FFFF00", "#C0FF00",
         "#7FE000", "#00C800", "#00D88A", "#00E0E0", "#00BFFF", "#0090FF", "#0050FF", "#0000FF"]


def scale_color(v, vmin, vmax):
    if vmax - vmin < 1e-12:
        return SCALE[-1]
    t = (v - vmin) / (vmax - vmin)
    return SCALE[min(max(int(round((1 - t) * (len(SCALE) - 1))), 0), len(SCALE) - 1)]


def _split(h):
    m = re.match(r"(.*?)\s*\[(.*)\]$", h)
    return (m[1], f"[{m[2]}]") if m else (h, "")


class ResultsWindow(tk.Toplevel):
    def __init__(self, master, rep: dict, RP, checks: list, on_select=None, title=""):
        super().__init__(master)
        self.title(title or "Results")
        self.geometry("1000x860")
        self.rep, self.RP, self.on_select = rep, RP, on_select
        self.byid = {c["id"]: c for c in checks}
        F = lambda size, *st: tkfont.Font(family="Arial", size=size, weight="bold" if "b" in st else "normal",
                                          slant="italic" if "i" in st else "roman")
        self.f, self.fb, self.fbi, self.fs, self.fxs = F(9), F(9, "b"), F(9, "b", "i"), F(8), F(7)
        self.fh, self.fsub, self.fconn, self.ftitle, self.fratio = F(15), F(14), F(16, "b"), F(19), F(12, "b")
        pan = ttk.PanedWindow(self, orient="vertical"); pan.pack(fill="both", expand=True)
        top = tk.Frame(pan, bg=PAGE); pan.add(top, weight=4)
        self.cv = tk.Canvas(top, bg=PAGE, highlightthickness=0)
        ys = ttk.Scrollbar(top, orient="vertical", command=self.cv.yview)
        xs = ttk.Scrollbar(top, orient="horizontal", command=self.cv.xview)
        self.cv.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        ys.pack(side="right", fill="y"); xs.pack(side="bottom", fill="x"); self.cv.pack(fill="both", expand=True)
        for ev, d in (("<MouseWheel>", None), ("<Button-4>", -1), ("<Button-5>", 1)):
            self.cv.bind(ev, lambda e, d=d: self.cv.yview_scroll(d if d else (-1 if e.delta > 0 else 1), "units"))
        # khung diễn giải tiếng Việt (giữ như cũ)
        self.det = tk.Text(pan, height=9, font=("Consolas", 10), wrap="word", padx=8, pady=6)
        pan.add(self.det, weight=1)
        msg = "Nhấp một dòng trong Design Check để xem diễn giải công thức (tiếng Việt)."
        if rep.get("warnings"):
            msg += "\n\nGhi chú:\n" + "\n".join("• " + w for w in rep["warnings"])
        self.det.insert("end", msg)
        self.det.configure(state="disabled")
        self.row_boxes = {}
        self._sel = None
        self.draw()

    # ───────────────────────── tiện ích vẽ ─────────────────────────
    def _t(self, x, y, s, font=None, color=TXT, anchor="nw", tags=()):
        return self.cv.create_text(x, y, text=s, font=font or self.f, fill=color, anchor=anchor, tags=tags)

    def _dash(self, x0, x1, y):
        self.cv.create_line(x0, y, x1, y, fill="#000000", dash=(2, 2))

    def _heading(self, y, s):
        self._t(X0, y, s, self.fh)
        return y + 30

    # ───────────────────────── bảng kiểu RAM (không kẻ ô) ─────────────────────────
    def _table(self, y, cols, rows, unit_row=True, dashed=False, ids=None, group_indent=16, ratio_col=None, sta_col=None, unit_col=None):
        """cols: [(tiêu đề, x, căn 'w'|'e'|'c')]. rows: list (nhóm = str)."""
        heads = [_split(h) for h, _x, _a in cols]
        H = 17
        for (name, unit), (_h, x, a) in zip(heads, cols):
            self._t(x, y, name, self.fb, anchor="n" + ("w" if a == "w" else "e" if a == "e" else ""))
            if unit_row and unit:
                self._t(x, y + 16, unit, self.fxs, anchor="n" + ("w" if a == "w" else "e" if a == "e" else ""))
        y += 34 if unit_row and any(u for _n, u in heads) else 24
        xr = cols[-1][1] + (70 if cols[-1][2] == "w" else 6)
        if dashed:
            self._dash(X0, xr, y); y += 8
        for k, r in enumerate(rows):
            if isinstance(r, str):
                y += 6
                self._t(X0, y, r, self.fbi); y += H; continue
            rid = ids[k] if ids else None
            tag = (f"row_{rid}",) if rid else ()
            if rid:
                self.row_boxes[rid] = self.cv.create_rectangle(X0, y - 1, PW + 60, y + H - 2, fill=PAGE, outline="", tags=tag)
            for i, (_h, x, a) in enumerate(cols):
                if i >= len(r): break
                s = str(r[i]); font, col = self.f, TXT
                if i == 0 and group_indent and any(isinstance(q, str) for q in rows):
                    x = x + group_indent
                if unit_col is not None and i == unit_col:
                    font = self.fxs
                if ratio_col is not None and i == ratio_col and len(r) > 8:
                    font = self.fb
                    col = "#808080" if r[8] else (BAD_C if r[7] > 1.0001 else OK_C)
                if sta_col is not None and i == sta_col:
                    ok = s == "OK"
                    self._t(x, y + H / 2 - 1, "✔" if ok else "✘", tkfont.Font(family="Arial", size=12, weight="bold"),
                            OK_C if ok else BAD_C, anchor="center", tags=tag)
                    continue
                anc = "w" if a == "w" else ("e" if a == "e" else "center")
                self._t(x, y + H / 2 - 1, s, font, col, anchor=anc, tags=tag)
            if rid:
                self.cv.tag_bind(tag[0], "<Button-1>", lambda e, rid=rid: self.select(rid))
                self.cv.tag_bind(tag[0], "<Enter>", lambda e: self.cv.configure(cursor="hand2"))
                self.cv.tag_bind(tag[0], "<Leave>", lambda e: self.cv.configure(cursor=""))
            y += H
        if dashed:
            self._dash(X0, xr, y + 2); y += 8
        return y + 8

    # ───────────────────────── trang ─────────────────────────
    def draw(self):
        cv, rep, RP = self.cv, self.rep, self.RP
        cv.delete("all")
        self.row_boxes = {}
        mid = PW / 2
        y = 6
        self._t(mid, y, "Steel Connections", self.ftitle, anchor="n"); y += 32
        self._t(mid, y, "Results", self.ftitle, anchor="n"); y += 52
        self._t(X0, y, f"Connection:  {rep['name']}", self.fconn); y += 32
        self._dash(X0, X0 + 450, y); y += 8
        for k, v in (("Family:", rep["family"]), ("Type:", rep["type"])):
            self._t(X0, y, k, self.fs); self._t(X0 + 86, y, v, self.fs); y += 17
        self._dash(X0, X0 + 450, y + 2); y += 24
        self._t(X0, y, f"Design code: {rep['code']}", self.fs); y += 30

        # Demands
        y = self._heading(y, "Demands")
        dh = getattr(RP, "DEM_HEAD", [])
        cols = [(dh[0], X0, "w")]
        x = 140
        for h in dh[1:-1]:
            x += max(self.fb.measure(_split(h)[0]), self.fxs.measure(_split(h)[1]), 46) + 14
            cols.append((h, x, "e"))
        cols.append((dh[-1], x + 14, "w"))
        y = self._table(y, cols, rep["demands"], dashed=True, group_indent=0) + 14

        # Design calculations
        blocks = rep.get("blocks") or [dict(title=None, sub=None, geo=rep.get("geo"), checks=rep["checks"])]
        y = self._heading(y, "Design calculations") if rep.get("blocks") else y
        for b in blocks:
            if b.get("title"):
                y += 8
                self._t(mid, y, b["title"], self.fsub, anchor="n"); y += 24
                self._t(mid, y, b["sub"], tkfont.Font(family="Arial", size=11, weight="bold", slant="italic"), anchor="n"); y += 24
            if b.get("geo"):
                y = self._heading(y, "Geometric Considerations")
                grows = []
                for grp, rr in b["geo"].items():
                    grows.append(grp); grows += rr
                gcols = [("Dimensions", X0, "w"), ("Unit", 336, "w"), ("Value", 450, "e"), ("Min.", 537, "e"),
                         ("Max.", 622, "e"), ("Sta.", 652, "c"), ("References", 680, "w")]
                y = self._table(y, gcols, grows, unit_row=False, sta_col=5, unit_col=1) + 10
            if rep.get("behavior") and b is blocks[0]:
                y = self._heading(y, "Plate behavior")
                for a, t in rep["behavior"]:
                    self._t(X0, y, a, self.fbi); y += 16
                    self._t(X0 + 16, y, t); y += 22
            y = self._heading(y, "Design Check")
            crows, ids = [], []
            for grp, rr in b["checks"]:
                crows.append(grp); ids.append(None)
                for r in rr:
                    crows.append(r); ids.append(r[9] if len(r) > 9 else None)
            ccols = [("Verification", X0, "w"), ("Unit", 345, "w"), ("Capacity", 470, "e"), ("Demand", 560, "e"),
                     ("Ctrl EQ", 573, "w"), ("Ratio", 700, "e"), ("References", 718, "w")]
            y = self._table(y, ccols, crows, unit_row=False, ids=ids, ratio_col=5, unit_col=1) + 16
        r = rep["ratio"]
        self._t(X0 + 4, y, "Ratio", self.fratio)
        self._t(345, y, "INF" if math.isinf(r) else f"{r:.2f}", self.fratio, TXT)
        y += 46

        # chi tiết từng trục
        for dt in rep.get("details") or []:
            y = self._detail(y, dt)

        # Notes
        if rep.get("notes"):
            y = self._heading(y, "Notes")
            for n in rep["notes"]:
                self._t(X0, y - 6, n, self.fs); y += 16
        bb = cv.bbox("all") or (0, 0, PW, y)
        cv.configure(scrollregion=(0, 0, max(bb[2], PW) + 10, y + 30))

    # ───────────────────────── chi tiết trục: hình + tóm tắt + lực neo ─────────────────────────
    def _detail(self, y, dt):
        cv = self.cv
        cv.create_rectangle(X0, y, PW - 10, y + 26, fill=BAND, outline="")
        self._t(X0 + 6, y + 13, dt["title"], self.fh, anchor="w"); y += 38
        self._t(X0 + 10, y, f"Maximum compression and tension ({dt['combo']})", self.fbi); y += 22
        g = self.rep["geom"]
        fv = self._field_values(dt["field"], g)
        vmax_p = max([v for v in fv.values()] + [0.0])
        T = dt["T"]
        self._figure(X0 + 10, y, g, "pressure", fv, 0.0, vmax_p, "Base plate\nConcrete stress\n[N/mm2]")
        self._figure(X0 + 410, y, g, "tension", T, 0.0, max(T + [0.0]), "Base plate\nAnchors tension\n[kN]")
        y += 330
        self._dash(X0 + 10, X0 + 320, y); y += 8
        for lab, v, u in dt["summary"]:
            self._t(X0 + 10, y, lab, self.fs)
            self._t(X0 + 232, y, f"{v:.2f}", self.fs, anchor="ne")
            self._t(X0 + 242, y + 1, u, self.fxs)
            y += 17
        self._dash(X0 + 10, X0 + 320, y + 2); y += 26
        self._t(X0 + 10, y, "Anchors tensions", self.fbi); y += 24
        acols = [("Anchor", X0 + 54, "e"), ("Transverse [mm]", X0 + 150, "e"), ("Longitudinal [mm]", X0 + 250, "e"),
                 ("Shear [kN]", X0 + 300, "e"), ("Tension [kN]", X0 + 365, "e")]
        y = self._table(y, acols, dt["anchors"], dashed=True, group_indent=0)
        return y + 20

    def _field_values(self, field, g, nc=36):
        """Áp lực ép (N/mm2) tại tâm các ô lưới bản đế."""
        N, B = g["N"], g["B"]
        out = {}
        for i in range(nc):
            for j in range(nc):
                x = -N / 2 + (i + 0.5) * N / nc; z = -B / 2 + (j + 0.5) * B / nc
                p = 0.0
                if field[0] == "plane":
                    p = max(field[1] + field[2] * x + field[3] * z, 0.0)
                elif field[0] == "block":
                    s = x if field[1] == 0 else z
                    p = field[4] if field[2] - 1e-9 <= s <= field[3] + 1e-9 else 0.0
                out[(i, j)] = p
        return out

    def _figure(self, x0, y0, g, kind, vals, vmin, vmax, legend):
        cv = self.cv
        Wf, Hf = 300, 300
        cv.create_rectangle(x0, y0, x0 + Wf + 92, y0 + Hf + 16, fill=FIG_BG, outline="")
        N, B = g["N"], g["B"]
        k = min((Wf - 70) / B, (Hf - 70) / N)                   # mặt bằng: phương N đứng, phương B ngang (như RAM)
        cx, cy = x0 + Wf / 2, y0 + Hf / 2 + 8
        P = lambda xx, zz: (cx + zz * k, cy - xx * k)
        a, b = P(N / 2, -B / 2), P(-N / 2, B / 2)
        cv.create_rectangle(a[0], a[1], b[0], b[1], fill=PLATE_G, outline="")
        if kind == "pressure":
            nc = int(round(math.sqrt(len(vals)))) or 1
            for (i, j), p in vals.items():
                if p <= 1e-9: continue
                c = scale_color(p, vmin, vmax)
                q0 = P(-N / 2 + i * N / nc, -B / 2 + j * B / nc); q1 = P(-N / 2 + (i + 1) * N / nc, -B / 2 + (j + 1) * B / nc)
                cv.create_rectangle(q0[0], q1[1], q1[0], q0[1], fill=c, outline=c)
        # trục
        cv.create_line(cx - Wf / 2 + 6, cy, cx + Wf / 2 - 6, cy, fill="#7F7F7F")
        cv.create_line(cx, y0 + 8, cx, y0 + Hf + 8, fill="#7F7F7F")
        # cột chữ I (cánh trên +x ở phía trên hình)
        d, ox, oz, tw = g["d"], g["ox"], g["oz"], g["tw"]
        fill = NAVY_C if kind == "tension" else ""
        for (x_a, x_b, bf) in ((ox + d / 2 - g["tfE"], ox + d / 2, g["bfE"]), (ox - d / 2, ox - d / 2 + g["tfI"], g["bfI"])):
            p0, p1 = P(x_b, oz - bf / 2), P(x_a, oz + bf / 2)
            cv.create_rectangle(p0[0], p0[1], p1[0], p1[1], fill=fill, outline="#3F3F3F" if not fill else fill)
        p0, p1 = P(ox + d / 2 - g["tfE"], oz - tw / 2), P(ox - d / 2 + g["tfI"], oz + tw / 2)
        cv.create_rectangle(p0[0], p0[1], p1[0], p1[1], fill=fill if fill else PLATE_G, outline="#3F3F3F" if not fill else fill)
        # neo
        r = max(2.5, g["da"] / 2 * k * 0.6)
        for idx, (xa, za) in enumerate(g["anchors"]):
            q = P(xa, za)
            if kind == "tension":
                c = scale_color(vals[idx], vmin, vmax) if vmax > 1e-9 else "#00C800"
                cv.create_oval(q[0] - r, q[1] - r, q[0] + r, q[1] + r, fill=c, outline="#3F3F3F")
            else:
                cv.create_oval(q[0] - r, q[1] - r, q[0] + r, q[1] + r, fill="#808080", outline="#3F3F3F")
        # dải màu
        lx, ly = x0 + Wf + 14, y0 + 10
        self._t(lx, ly, legend, self.fxs); ly += 40
        n = len(SCALE)
        for i, c in enumerate(SCALE):
            v = vmax - (vmax - vmin) * i / (n - 1)
            cv.create_rectangle(lx, ly + i * 14, lx + 14, ly + (i + 1) * 14, fill=c, outline=c)
            self._t(lx + 20, ly + i * 14 + 7, f"{v:.3g}" if abs(v) >= 1e-9 else "0", self.fxs, anchor="w")

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
