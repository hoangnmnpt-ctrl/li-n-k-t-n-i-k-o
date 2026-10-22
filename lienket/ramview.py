"""
ramview.py — Khung xem 3D kiểu RAM Connection (viết lại từ đầu).

  • Mô hình: model3d.Model gồm các khối lăng trụ (cấu kiện, bản đầu, bản gối, sườn, bu lông lục giác, gờ hàn).
  • Camera phối cảnh quay quanh tâm mô hình (yaw / pitch); mặc định nhìn chéo từ trên – trái – trước như RAM.
  • Ẩn mặt khuất theo từng khối (back-face culling). Thứ tự vẽ giữa các khối: với mỗi cặp khối chồng nhau trên màn hình,
    dùng MẶT PHẲNG PHÂN CÁCH (tính một lần) — camera nằm phía khối nào thì khối đó ở trước → sắp xếp tô-pô.
    Cách này đúng cả với các mặt tiếp giáp (bụng–cánh, bản–cánh) mà cách sắp theo độ sâu hay vẽ sai.
  • Chiếu sáng gắn theo camera (đèn đầu) + ánh sáng nền; viền đậm theo cạnh thật.
  • heat: tô màu theo D/C (tag → tỷ số); hl: tô sáng bộ phận của kiểm tra đang chọn.
Chuột trái kéo: xoay · chuột phải kéo: di chuyển · lăn: zoom · nhấp đúp: góc nhìn mặc định.
"""

from __future__ import annotations

import math
from collections import defaultdict

import drawing as D
from model3d import BOLT, WELD, Model, v_add, v_cross, v_dot, v_len, v_mul, v_norm, v_sub

NAVY = "#001A4D"
YAW0, PITCH0 = 42.0, 17.0


def _sep_plane(A, B):
    """Mặt phẳng phân cách hai khối lồi (A phía âm, B phía dương): chọn trong các mặt của A và B mặt có độ tách tốt nhất.
    Trả (n, p)."""
    best, best_s = None, -1e18
    vb, va = B.verts, A.verts
    for f, n in A.faces:
        p = f[0]
        s = min(v_dot(n, v_sub(v, p)) for v in vb)
        if s > best_s: best, best_s = (n, p), s
    for f, n in B.faces:
        p = f[0]
        s = min(v_dot(n, v_sub(v, p)) for v in va)
        if s > best_s: best, best_s = (v_mul(n, -1), p), s
    return best


def _hull(pts):
    """Bao lồi 2D (Andrew)."""
    pts = sorted(set((round(x, 9), round(y, 9)) for x, y in pts))
    if len(pts) <= 2: return pts
    def cross(o, a, b): return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0: lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0: up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def _overlap(h1, h2, eps):
    """Hai đa giác lồi 2D chồng nhau thật (trục tách, bỏ qua tiếp xúc nhỏ hơn eps)."""
    for h in (h1, h2):
        n = len(h)
        if n < 2: continue
        for i in range(n):
            a, b = h[i], h[(i + 1) % n]
            ax, ay = b[1] - a[1], a[0] - b[0]
            L = math.hypot(ax, ay)
            if L < 1e-15: continue
            ax, ay = ax / L, ay / L
            p1 = [x * ax + y * ay for x, y in h1]; p2 = [x * ax + y * ay for x, y in h2]
            if max(p1) <= min(p2) + eps or max(p2) <= min(p1) + eps:
                return False
    return True


class RamView(D._BaseView):
    def __init__(self, master, thumb: bool = False, **kw):
        super().__init__(master, **kw)
        self.configure(background=NAVY)
        self.thumb = thumb
        self.yaw, self.pitch = YAW0, PITCH0
        self.empty_text = ""
        self._model: Model | None = None
        self._center = (0.0, 0.0, 0.0)
        self._diag = 1.0
        self._planes: dict = {}
        if thumb:
            for ev in ("<MouseWheel>", "<Double-Button-1>", "<Motion>"):
                self.unbind(ev)
        else:
            self.bind("<ButtonPress-1>", self._press)
            self.bind("<B1-Motion>", self._rot)
            self.bind("<ButtonPress-3>", self._press)
            self.bind("<B3-Motion>", self._panm)

    # ---------- dữ liệu ----------
    def show_model(self, model: Model | None, hl_tags=(), heat=None):
        if model is not self._model:
            self._planes = {}
        self._model = model
        self._hl = set(hl_tags or ())
        self._heat = heat
        if model and model.solids:
            lo, hi = model.bbox()
            self._center = tuple((lo[i] + hi[i]) / 2 for i in range(3))
            self._diag = max(v_len(v_sub(hi, lo)), 1.0)
        self._scene = None
        self.redraw()

    def show(self, scene, hl_tags=(), heat=None):          # tương thích: show(None) để xoá
        if scene is None:
            self.show_model(None)

    def set_highlight(self, tags):
        self._hl = set(tags or ()); self.redraw()

    def reset_view(self):
        self.yaw, self.pitch = YAW0, PITCH0
        self.zoom = 1.0; self.pan = [0.0, 0.0]; self.redraw()

    # ---------- chuột ----------
    def _press(self, e):
        self._drag = (e.x, e.y, self.yaw, self.pitch, self.pan[0], self.pan[1])

    def _rot(self, e):
        if not self._drag: return
        x0, y0, yw, pt, _, _ = self._drag
        self.yaw = yw - (e.x - x0) * 0.45
        self.pitch = max(-85.0, min(85.0, pt + (e.y - y0) * 0.45))
        self.redraw()

    def _panm(self, e):
        if not self._drag: return
        x0, y0, _, _, px, py = self._drag
        self.pan = [px + e.x - x0, py + e.y - y0]; self.redraw()

    # ---------- vẽ ----------
    def _plane(self, i, j):
        key = (i, j)
        if key not in self._planes:
            so = self._model.solids
            self._planes[key] = _sep_plane(so[i], so[j])
        return self._planes[key]

    def redraw(self):
        self.delete("all")
        W, H = max(self.winfo_width(), 50), max(self.winfo_height(), 50)
        m = self._model
        if not m or not m.solids:
            if self.empty_text:
                self.create_text(W / 2, H / 2, text=self.empty_text, fill="#8FA6C8", font=("Segoe UI", 12), justify="center")
            return
        cy, sy = math.cos(math.radians(self.yaw)), math.sin(math.radians(self.yaw))
        cp, sp = math.cos(math.radians(self.pitch)), math.sin(math.radians(self.pitch))
        dist = self._diag * 2.6
        cam = v_add(self._center, (dist * cp * sy, dist * sp, dist * cp * cy))
        f = v_norm(v_sub(self._center, cam))
        r = v_norm(v_cross(f, (0.0, 1.0, 0.0)))
        u = v_cross(r, f)
        light = v_norm(v_add(v_add(v_mul(r, -0.30), v_mul(u, 0.45)), v_mul(f, -0.85)))     # đèn gần hướng nhìn (như RAM)

        def proj(p):
            v = v_sub(p, cam)
            z = max(v_dot(v, f), 1e-3)
            return v_dot(v, r) / z, v_dot(v, u) / z

        # mặt thấy được của từng khối
        vis = []
        xs, ys = [], []
        for idx, so in enumerate(m.solids):
            faces = []
            for poly, n in so.faces:
                if v_dot(n, v_sub(cam, poly[0])) <= 1e-9:
                    continue
                q = [proj(p) for p in poly]
                d = sum(v_len(v_sub(p, cam)) for p in poly) / len(poly)
                faces.append((d, q, n))
            if not faces: continue
            px = [x for _d, q, _n in faces for x, _y in q]; py = [y for _d, q, _n in faces for _x, y in q]
            xs += px; ys += py
            dmin = min(v_len(v_sub(p, cam)) for p in so.verts)
            vis.append(dict(i=idx, so=so, faces=faces, bb=(min(px), min(py), max(px), max(py)), d=dmin,
                            hull=_hull([proj(p) for p in so.verts])))
        if not vis:
            return
        # thứ tự giữa các khối: cạnh "a phải vẽ trước b" khi b ở trước a
        n = len(vis)
        eps = 1e-4 * max(max(xs) - min(xs), max(ys) - min(ys), 1e-9)
        after = defaultdict(list); indeg = [0] * n
        order_bb = sorted(range(n), key=lambda k: vis[k]["bb"][0])
        for ii in range(n):
            a = order_bb[ii]; ba = vis[a]["bb"]
            for jj in range(ii + 1, n):
                b = order_bb[jj]; bb = vis[b]["bb"]
                if bb[0] > ba[2]: break
                if bb[1] > ba[3] or bb[3] < ba[1]: continue
                if not _overlap(vis[a]["hull"], vis[b]["hull"], eps): continue     # không che nhau → không ràng buộc
                i, j = vis[a]["i"], vis[b]["i"]
                nrm, p = self._plane(i, j)               # A = i phía âm, B = j phía dương
                if v_dot(nrm, v_sub(cam, p)) > 0:        # camera phía j → j ở trước
                    after[a].append(b); indeg[b] += 1
                else:
                    after[b].append(a); indeg[a] += 1
        import heapq
        heap = [(-vis[k]["d"], k) for k in range(n) if indeg[k] == 0]
        heapq.heapify(heap)
        seq, done = [], [False] * n
        self.cycles = 0
        while len(seq) < n:
            if not heap:                                  # vòng lặp: lấy khối xa nhất còn lại
                self.cycles += 1
                k = max((k for k in range(n) if not done[k]), key=lambda k: vis[k]["d"])
                indeg[k] = 0; heapq.heappush(heap, (-vis[k]["d"], k))
            _dd, k = heapq.heappop(heap)
            if done[k]: continue
            done[k] = True; seq.append(k)
            for b in after[k]:
                indeg[b] -= 1
                if indeg[b] == 0 and not done[b]:
                    heapq.heappush(heap, (-vis[b]["d"], b))

        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        pad = 6 if self.thumb else 30
        k = min((W - 2 * pad) / max(x1 - x0, 1e-9), (H - 2 * pad) / max(y1 - y0, 1e-9)) * self.zoom
        cxw, cyw = (x0 + x1) / 2, (y0 + y1) / 2
        ox, oy = W / 2 + self.pan[0], H / 2 + self.pan[1]
        heat, hl = self._heat, self._hl
        for kk in seq:
            so = vis[kk]["so"]
            base = so.color
            if heat is not None:
                rr = D.item_ratio({"tags": so.tags}, heat)
                base = D.heat_color(rr) if rr is not None else "#9AA0A6"
            on = bool(hl & set(so.tags))
            tags = tuple("t_" + g for g in so.tags) + (("hl",) if on else ())
            faces = vis[kk]["faces"] if so.convex else sorted(vis[kk]["faces"], key=lambda fc: -fc[0])
            weld = so.color == WELD and heat is None
            for _d, q, nrm in faces:
                inten = min(0.38 + 0.70 * max(0.0, v_dot(nrm, light)), 1.15)
                col = D.shade(base, inten)
                pts = [c for x, y in q for c in (ox + k * (x - cxw), oy - k * (y - cyw))]
                if weld:                       # đường hàn: nét vàng dày theo điểm ảnh, như RAM
                    self.create_polygon(*pts, fill=col, outline="#F7B733", width=2 if self.thumb else 3, tags=tags)
                    continue
                edge = D.C_HL if on else (D.shade(base, 0.62) if so.color == BOLT else D.shade(base, 0.5 * min(inten, 1.0) + 0.12))
                self.create_polygon(*pts, fill=col, outline=edge, width=2 if on else 1, tags=tags)
        if not self.thumb:
            self.create_text(8, H - 8, anchor="sw", text="Kéo trái: xoay · kéo phải: di chuyển · lăn: zoom · nhấp đúp: góc mặc định",
                             fill="#6F86AD", font=("Segoe UI", 8))
