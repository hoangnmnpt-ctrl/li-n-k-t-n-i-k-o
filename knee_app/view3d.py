"""
view3d.py — Hình 3D knee trên tk.Canvas (không cần thư viện ngoài).
Dựng khối từ Scene mặt đứng: mỗi đa giác có khoảng bề dày z → lăng trụ (cánh, bụng, bản, sườn, bu lông).
Chiếu trực giao + xoay (yaw/pitch), sắp xếp mặt theo độ sâu (painter), tô bóng theo pháp tuyến.
Chuột trái kéo: xoay · chuột phải kéo: di chuyển · lăn: zoom · nhấp đúp: về góc nhìn mặc định.
"""

from __future__ import annotations

import math
import tkinter as tk

from drawing import C_HL, _BaseView, heat_color, item_ratio, shade

LIGHT = (0.35, 0.55, 0.76)


def _norm(v):
    L = math.sqrt(sum(x * x for x in v)) or 1.0
    return tuple(x / L for x in v)


LIGHT = _norm(LIGHT)
YAW0, PITCH0 = -38.0, 22.0


class Knee3D(_BaseView):
    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.configure(background="#F3F6FA")
        self.yaw, self.pitch = YAW0, PITCH0
        self._faces = []
        self._lines = []
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._rot)
        self.bind("<ButtonPress-3>", self._press)
        self.bind("<B3-Motion>", self._panm)

    def reset_view(self):
        self.yaw, self.pitch = YAW0, PITCH0
        super().reset_view()

    def show(self, scene, hl_tags=(), heat=None):
        self._build(scene)
        super().show(scene, hl_tags, heat)

    # ---------- dựng khối ----------
    def _build(self, sc):
        faces, lines = [], []
        if sc is None:
            self._faces, self._lines = faces, lines; return
        for it in sc.items:
            if it["k"] == "poly" and it.get("z"):
                pts = it["pts"]
                n = len(pts)
                if n < 3: continue
                for z0, z1 in it["z"]:
                    top = [(x, y, z1) for x, y in pts]
                    bot = [(x, y, z0) for x, y in pts]
                    faces.append((top, it)); faces.append((bot[::-1], it))
                    for i in range(n):
                        j = (i + 1) % n
                        faces.append(([bot[i], bot[j], top[j], top[i]], it))
            elif it["k"] == "line" and any(t in ("force", "flow") for t in it.get("tags", ())):
                lines.append(it)
        self._faces, self._lines = faces, lines

    # ---------- chuột ----------
    def _press(self, e):
        self._drag = (e.x, e.y, self.yaw, self.pitch, self.pan[0], self.pan[1])

    def _rot(self, e):
        if not self._drag: return
        x0, y0, yw, pt, _, _ = self._drag
        self.yaw = yw + (e.x - x0) * 0.5
        self.pitch = max(-89, min(89, pt + (e.y - y0) * 0.5))
        self.redraw()

    def _panm(self, e):
        if not self._drag: return
        x0, y0, _, _, px, py = self._drag
        self.pan = [px + e.x - x0, py + e.y - y0]; self.redraw()

    # ---------- chiếu ----------
    def _proj(self):
        cy_, sy_ = math.cos(math.radians(self.yaw)), math.sin(math.radians(self.yaw))
        cp, sp = math.cos(math.radians(self.pitch)), math.sin(math.radians(self.pitch))

        def P(v):
            x, y, z = v
            x1 = x * cy_ + z * sy_
            z1 = -x * sy_ + z * cy_
            y2 = y * cp - z1 * sp
            d = y * sp + z1 * cp
            return x1, y2, d
        return P

    def redraw(self):
        self.delete("all")
        if not self._faces:
            return
        W, H = max(self.winfo_width(), 50), max(self.winfo_height(), 50)
        P = self._proj()
        proj = []
        xs, ys = [], []
        for poly, it in self._faces:
            q = [P(v) for v in poly]
            proj.append((q, poly, it))
            for x, y, _ in q:
                xs.append(x); ys.append(y)
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        pad = 30
        k = min((W - 2 * pad) / max(x1 - x0, 1), (H - 2 * pad) / max(y1 - y0, 1)) * self.zoom
        cxw, cyw = (x0 + x1) / 2, (y0 + y1) / 2
        ox, oy = W / 2 + self.pan[0], H / 2 + self.pan[1]
        S = lambda x, y: (ox + k * (x - cxw), oy - k * (y - cyw))
        heat, hl = self._heat, self._hl
        order = sorted(proj, key=lambda f: sum(v[2] for v in f[0]) / len(f[0]))
        for q, poly, it in order:
            # pháp tuyến (hệ đã xoay)
            a, b, c = q[0], q[1], q[2]
            u = (b[0] - a[0], b[1] - a[1], b[2] - a[2]); v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
            nrm = _norm((u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]))
            inten = 0.50 + 0.50 * abs(nrm[0] * LIGHT[0] + nrm[1] * LIGHT[1] + nrm[2] * LIGHT[2])
            base = it["fill"]
            if heat is not None:
                r = item_ratio(it, heat)
                base = heat_color(r) if r is not None else "#DDE2E8"
            on = bool(hl & set(it.get("tags", ())))
            pts = [c for x, y, _ in q for c in S(x, y)]
            tags = tuple("t_" + t for t in it.get("tags", ()))
            self.create_polygon(*pts, fill=shade(base, inten), outline=C_HL if on else shade(base, inten * 0.72),
                                width=2 if on else 1, tags=tags + (("hl",) if on else ()))
        for it in self._lines:
            pts = []
            for x, y in it["pts"]:
                px, py, _ = P((x, y, 0.0))
                pts += S(px, py)
            kw = dict(fill=it["color"], width=it["width"], tags=("anim",) if it.get("anim") else ())
            if it.get("dash"): kw["dash"] = it["dash"]
            if it.get("arrow"): kw.update(arrow=it["arrow"], arrowshape=(12, 14, 5))
            self.create_line(*pts, **kw)
        self._triad(W, H, P)
        self.create_text(8, H - 8, anchor="sw", text="Kéo trái: xoay · kéo phải: di chuyển · lăn: zoom · nhấp đúp: góc mặc định",
                         fill="#9AA5B1", font=("Segoe UI", 8))

    def _triad(self, W, H, P):
        cx, cy, L = 50, H - 55, 30
        for v, lab, col in (((1, 0, 0), "X", "#D23B3B"), ((0, 1, 0), "Z", "#1A9E5A"), ((0, 0, 1), "Y", "#1F6FEB")):
            x, y, _ = P(v)
            self.create_line(cx, cy, cx + x * L, cy - y * L, fill=col, width=2, arrow="last")
            self.create_text(cx + x * (L + 9), cy - y * (L + 9), text=lab, fill=col, font=("Segoe UI", 8, "bold"))
