"""
ramview.py — Khung xem 3D kiểu RAM Connection: nền xanh đậm, cấu kiện xám, bản đầu xanh lá, bu lông cam,
sườn tím nhạt, đường hàn vàng; nhìn gần chính diện. Dùng chung hình mặt đứng (Scene có bề dày z) của knee và nối dầm.
Chế độ heat=True: tô màu theo D/C như các khung xem khác.
"""

from __future__ import annotations

import math

import drawing as D
from view3d import LIGHT, Knee3D, _norm

NAVY = "#001A4D"
STEEL = "#B9BCC0"
RAM_FILL = {
    D.C_WEB: STEEL, D.C_STEEL: STEEL, D.C_PANEL: STEEL,
    D.C_PLATE: "#2FBF3A", D.C_STIFF: "#B9B4F2", D.C_BOLT: "#E98A2E", D.C_WELD: "#F3E31C",
}
PLATE_STIFF = "#8FE08F"          # sườn bản đầu (4ES): xanh nhạt như RAM


def ram_color(it) -> str:
    f = it.get("fill")
    if f == D.C_STIFF and any(t.startswith("plate") for t in it.get("tags", ())):
        return PLATE_STIFF
    return RAM_FILL.get(f, f or STEEL)


class RamView(Knee3D):
    YAW, PITCH = -14.0, 9.0

    def __init__(self, master, thumb: bool = False, **kw):
        super().__init__(master, **kw)
        self.configure(background=NAVY)
        self.thumb = thumb
        self.yaw, self.pitch = self.YAW, self.PITCH
        self.empty_text = ""
        if thumb:                                  # ô thu nhỏ: không xoay / zoom
            for ev in ("<ButtonPress-1>", "<B1-Motion>", "<ButtonPress-3>", "<B3-Motion>", "<MouseWheel>", "<Double-Button-1>", "<Motion>"):
                self.unbind(ev)

    def reset_view(self):
        self.yaw, self.pitch = self.YAW, self.PITCH
        self.zoom = 1.0; self.pan = [0.0, 0.0]; self.redraw()

    def redraw(self):
        self.delete("all")
        W, H = max(self.winfo_width(), 50), max(self.winfo_height(), 50)
        if not self._faces:
            if self.empty_text:
                self.create_text(W / 2, H / 2, text=self.empty_text, fill="#8FA6C8", font=("Segoe UI", 12), justify="center")
            return
        P = self._proj()
        proj, xs, ys = [], [], []
        cyaw = math.cos(math.radians(self.yaw))
        for poly, it in self._faces:
            q = [P(v) for v in poly]
            zc = sum(v[2] for v in poly) / len(poly)          # lớp bề dày (z gốc) của mặt
            proj.append((q, it, zc))
            for x, y, _ in q:
                xs.append(x); ys.append(y)
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        pad = 8 if self.thumb else 40
        k = min((W - 2 * pad) / max(x1 - x0, 1), (H - 2 * pad) / max(y1 - y0, 1)) * self.zoom
        cxw, cyw = (x0 + x1) / 2, (y0 + y1) / 2
        ox, oy = W / 2 + self.pan[0], H / 2 + self.pan[1]
        S = lambda x, y: (ox + k * (x - cxw), oy - k * (y - cyw))
        heat, hl = self._heat, self._hl
        # Hình gần chính diện: vẽ theo lớp z (mặt ở phía người nhìn vẽ sau) rồi mới theo độ sâu —
        # tránh mặt bụng lớn che mất sườn / bu lông như cách sắp theo độ sâu trung bình.
        sgn = 1.0 if cyaw >= 0 else -1.0
        for q, it, _zc in sorted(proj, key=lambda f: (round(sgn * f[2], 1), sum(v[2] for v in f[0]) / len(f[0]))):
            a, b, c = q[0], q[1], q[2]
            u = (b[0] - a[0], b[1] - a[1], b[2] - a[2]); v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
            nrm = _norm((u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]))
            inten = 0.58 + 0.42 * abs(nrm[0] * LIGHT[0] + nrm[1] * LIGHT[1] + nrm[2] * LIGHT[2])
            base = ram_color(it)
            if heat is not None:
                r = D.item_ratio(it, heat)
                base = D.heat_color(r) if r is not None else STEEL
            on = bool(hl & set(it.get("tags", ())))
            pts = [cc for x, y, _ in q for cc in S(x, y)]
            tags = tuple("t_" + t for t in it.get("tags", ()))
            self.create_polygon(*pts, fill=D.shade(base, inten), outline=D.C_HL if on else D.shade(base, inten * 0.8),
                                width=2 if on else 1, tags=tags + (("hl",) if on else ()))
        if not self.thumb:
            self.create_text(8, H - 8, anchor="sw", text="Kéo trái: xoay · kéo phải: di chuyển · lăn: zoom · nhấp đúp: góc mặc định",
                             fill="#6F86AD", font=("Segoe UI", 8))
