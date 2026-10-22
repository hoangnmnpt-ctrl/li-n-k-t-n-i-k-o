"""
model3d.py — Mô hình 3D của nút (knee / nối dầm) dạng lưới tam giác, để vẽ kiểu RAM Connection.

Nguồn hình học: hình mặt đứng đã kiểm chứng của tool (drawing.elevation / splice_drawing.elevation) — mỗi đa giác có
khoảng bề dày z ngoài mặt phẳng → khối lăng trụ. Từ đó chỉ giữ CẤU KIỆN, BẢN, SƯỜN; các phần sau dựng mới bằng 3D thật:
  • bu lông: đầu lục giác + đai ốc lục giác, hai dãy cách nhau g, trục theo pháp tuyến bản;
  • đường hàn: gờ tam giác (chân hàn w) nằm ở góc cánh–bản và bụng–bản, hai phía.
Hệ trục: x ngang, y đứng (lên trên), z ngoài mặt phẳng khung. Đơn vị mm.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import drawing as D

# màu theo ảnh RAM Connection
STEEL = "#ABABAB"
END_PLATE = "#6C6698"
SUPPORT_PLATE = "#2EA043"
STIFF = "#8FAA7F"
PLATE_STIFF = "#7B76A8"
BOLT = "#D87A28"
WELD = "#F2B42C"


@dataclass
class Solid:
    """Khối (lăng trụ) — các mặt phẳng có pháp tuyến hướng ra ngoài. convex: khối lồi (đáy lồi)."""
    faces: list                   # [(đỉnh 3D theo vòng, pháp tuyến ngoài)]
    color: str
    tags: tuple = ()
    convex: bool = True

    @property
    def verts(self):
        return [p for f, _n in self.faces for p in f]


@dataclass
class Model:
    solids: list = field(default_factory=list)

    def bbox(self):
        vs = [p for so in self.solids for p in so.verts]
        if not vs: return (0, 0, 0), (1, 1, 1)
        return tuple(min(v[i] for v in vs) for i in range(3)), tuple(max(v[i] for v in vs) for i in range(3))


# ─────────────────────────── vector ───────────────────────────
def v_add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def v_sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def v_mul(a, k): return (a[0] * k, a[1] * k, a[2] * k)
def v_dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def v_cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def v_len(a): return math.sqrt(v_dot(a, a))
def v_norm(a):
    L = v_len(a) or 1.0
    return (a[0] / L, a[1] / L, a[2] / L)


# ─────────────────────────── khối lăng trụ ───────────────────────────
def _area2(pts):
    return sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))


def _clean(pts, eps=1e-6):
    out = []
    for p in pts:
        if not out or abs(p[0] - out[-1][0]) > eps or abs(p[1] - out[-1][1]) > eps:
            out.append(p)
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) < eps and abs(out[0][1] - out[-1][1]) < eps:
        out.pop()
    return out


def _newell(poly):
    nx = ny = nz = 0.0
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        nx += (a[1] - b[1]) * (a[2] + b[2]); ny += (a[2] - b[2]) * (a[0] + b[0]); nz += (a[0] - b[0]) * (a[1] + b[1])
    return v_norm((nx, ny, nz))


def _is_convex(poly, nb):
    sgn = 0
    for i in range(len(poly)):
        a, b, c = poly[i - 1], poly[i], poly[(i + 1) % len(poly)]
        cr = v_dot(v_cross(v_sub(b, a), v_sub(c, b)), nb)
        if abs(cr) < 1e-9: continue
        if sgn == 0: sgn = 1 if cr > 0 else -1
        elif (cr > 0) != (sgn > 0): return False
    return True


def add_prism(m: Model, base, vec, color, tags=()):
    """Lăng trụ: đa giác đáy (đỉnh 3D, phẳng) tịnh tiến theo vec. Pháp tuyến các mặt hướng ra ngoài."""
    base = list(base)
    if len(base) < 3 or v_len(vec) < 1e-9: return
    nb = _newell(base)
    if v_dot(nb, vec) > 0:
        base = base[::-1]; nb = v_mul(nb, -1)
    top = [v_add(p, vec) for p in base]
    cen = tuple(sum(p[i] for p in base + top) / (2 * len(base)) for i in range(3))
    faces = [(base, nb), (top[::-1], v_mul(nb, -1))]
    for i in range(len(base)):
        j = (i + 1) % len(base)
        nq = v_norm(v_cross(v_sub(base[j], base[i]), vec))
        if v_dot(nq, v_sub(base[i], cen)) < 0:
            nq = v_mul(nq, -1)
        faces.append(([base[i], base[j], top[j], top[i]], nq))
    m.solids.append(Solid(faces, color, tuple(tags), _is_convex(base, nb)))


def hex_prism(m, center, axis, e1, r, h, color, tags=()):
    e2 = v_norm(v_cross(axis, e1))
    base = [v_add(center, v_add(v_mul(e1, r * math.cos(math.radians(30 + 60 * k))), v_mul(e2, r * math.sin(math.radians(30 + 60 * k)))))
            for k in range(6)]
    add_prism(m, base, v_mul(axis, h), color, tags)


def weld_bead(m, corner, d1, d2, run, w, tags=()):
    """Gờ hàn góc: tam giác (corner, corner + d1·w, corner + d2·w) chạy theo vec run."""
    if v_len(run) < 1e-6: return
    add_prism(m, [corner, v_add(corner, v_mul(d1, w)), v_add(corner, v_mul(d2, w))], run, WELD, tags)


# ─────────────────────────── phân loại đa giác hình mặt đứng ───────────────────────────
def classify(it) -> str | None:
    f, tags = it.get("fill"), set(it.get("tags", ()))
    if f in (D.C_BOLT, D.C_WELD, "#6B7280") or "yield" in tags or "force" in tags:
        return None                                       # bu lông, hàn: dựng mới
    if f == D.C_STIFF:
        return PLATE_STIFF if any(t.startswith("plate") for t in tags) else STIFF
    if f == D.C_PLATE:
        return END_PLATE if any(t.startswith("plate") for t in tags) else (SUPPORT_PLATE if {"supportE", "supportI"} <= tags else STEEL)
    if f == D.C_PANEL and {"supportE", "supportI"} <= tags:       # bản gối (connection plate); bản nắp vẫn là thép
        return SUPPORT_PLATE
    return STEEL


def from_scene(m: Model, sc):
    for it in sc.items:
        if it["k"] != "poly" or not it.get("z"): continue
        col = classify(it)
        if col is None: continue
        pts = _clean(it["pts"])
        if len(pts) < 3 or abs(_area2(pts)) < 1e-6: continue
        for z0, z1 in it["z"]:
            if z1 - z0 < 1e-6: continue
            add_prism(m, [(x, y, z0) for x, y in pts], (0.0, 0.0, z1 - z0), col, tuple(it.get("tags", ())))


def _p3(p2, z=0.0):
    return (p2[0], p2[1], z)


def member_welds(m, A, Ai, Bi, B, uE, uI, t, tw, bfE, bfI, w, tagE, tagI, tagW):
    """Hàn cánh (ngoài + trong, hai phía bụng) và hàn bụng (hai phía) giữa một cấu kiện chữ I và bản đầu.
    A, Ai, Bi, B: điểm trên mặt bản (2D) tại mép ngoài / trong cánh trên, trong / ngoài cánh dưới; t: hướng dọc bản từ A sang B."""
    t3, mt3 = _p3(t), _p3((-t[0], -t[1]))
    uE3, uI3 = _p3(uE), _p3(uI)
    Z = (0.0, 0.0, 1.0)
    weld_bead(m, _p3(A, -bfE / 2), mt3, uE3, v_mul(Z, bfE), w, (tagE,))
    weld_bead(m, _p3(B, -bfI / 2), t3, uI3, v_mul(Z, bfI), w, (tagI,))
    for s in (1, -1):
        z0, z1 = s * tw / 2, s * bfE / 2
        weld_bead(m, _p3(Ai, min(z0, z1)), t3, uE3, (0, 0, abs(z1 - z0)), w, (tagE,))
        z0, z1 = s * tw / 2, s * bfI / 2
        weld_bead(m, _p3(Bi, min(z0, z1)), mt3, uI3, (0, 0, abs(z1 - z0)), w, (tagI,))
        a = v_add(_p3(Ai, s * tw / 2), v_mul(t3, w)); b = v_add(_p3(Bi, s * tw / 2), v_mul(mt3, w))
        um = v_norm(v_add(uE3, uI3))
        weld_bead(m, a, um, (0, 0, s), v_sub(b, a), w, (tagW,))


def bolts(m, rows_s, C, n, g, db, head_off, nut_off, tagof):
    """Bu lông lục giác: tâm C(s) trên mặt phẳng tiếp xúc, hai dãy z = ±g/2. Đầu ở phía +n (head_off), đai ốc phía −n."""
    n3 = _p3(n)
    for s, tag in rows_s:
        c2 = C(s)
        t2 = (C(s + 1.0)[0] - c2[0], C(s + 1.0)[1] - c2[1])
        e1 = v_norm(_p3(t2))
        for z in (g / 2, -g / 2):
            c = (c2[0], c2[1], z)
            hex_prism(m, v_add(c, v_mul(n3, head_off)), n3, e1, 0.92 * db, 0.62 * db, BOLT, (tag,))
            hex_prism(m, v_add(c, v_mul(n3, -nut_off)), v_mul(n3, -1), e1, 0.92 * db, 0.85 * db, BOLT, (tag,))


# ─────────────────────────── knee ───────────────────────────
def knee_model(st: dict, R: dict) -> Model:
    m = Model()
    from_scene(m, D.elevation(st, R, None, flow=False))
    G = R["G"]; T = G["type"]; M1 = G["M1"]; sup = st["sup"]
    tp = float(st["plate"]["tp"])
    nn = D.ang(G["thN"])
    t = (-nn[1], nn[0]) if T == "ngang" else (nn[1], -nn[0])
    C = lambda s: (t[0] * s, t[1] * s)
    face = (nn[0] * tp, nn[1] * tp)
    if T == "ngang":
        uE = D.ang(-90 + (G["c_out_tilt"] if st["col"].get("innerStraight") else 0)); uI = D.ang(-90 - G["c_in_tilt"])
    else:
        uE, uI = D.ang(G["a"]), D.ang(G["b_in"])
    P = lambda s: (C(s)[0] + face[0], C(s)[1] + face[1])
    wf = max(float(st["weld"]["flE"].get("w", 8)), 6.0)
    member_welds(m, P(0.0), P(G["tfe"]), P(G["dp"] - G["tfi"]), P(G["dp"]), uE, uI, t, M1["tw"], M1["bfE"], M1["bfI"], wf,
                 "m1weldE", "m1weldI", "m1webweld")
    ts = G["M2"]["tfI"] if sup["useFlange"] else float(sup["t"])
    rows = [(r["s"], "boltsE") for r in G["rowsE"]] + [(r["s"], "boltsI") for r in G["rowsI"]]
    bolts(m, rows, C, nn, float(st["plate"]["g"]), float(st["bolt"]["d"]), tp, ts, None)
    return m


# ─────────────────────────── nối dầm ───────────────────────────
def splice_model(st: dict, R: dict) -> Model:
    import splice_drawing as SDR
    m = Model()
    from_scene(m, SDR.elevation(st, R, None, flow=False))
    G = R["G"]; pl = st["plate"]
    tp1, tp2 = float(pl["tp1"]), float(pl["tp2"])
    dp, tfT, tfB = G["dp"], G["tfT"], G["tfB"]
    a = G["alpha"] if G["type"] == "apex" else 0.0
    u = {1: D.ang(180 + a) if a else (-1.0, 0.0), 2: D.ang(-a) if a else (1.0, 0.0)}
    x0 = {1: -tp1, 2: tp2}
    t = (0.0, -1.0)
    wf = max(float(st["weld"]["flT"].get("w", 8)), 6.0)
    for k in (1, 2):
        b = G["b%d" % k]
        P = lambda s, k=k: (x0[k], -s)
        member_welds(m, P(0.0), P(tfT), P(dp - tfB), P(dp), u[k], u[k], t, b["tw"], b["bfE"], b["bfI"], wf,
                     f"m{k}weldT", f"m{k}weldB", f"m{k}webweld")
    C = lambda s: (0.0, -s)
    rows = [(r["s"], "boltsT") for r in G["rowsT"]] + [(r["s"], "boltsB") for r in G["rowsB"]]
    bolts(m, rows, C, (-1.0, 0.0), float(pl["g"]), float(st["bolt"]["d"]), tp1, tp2, None)
    return m


def build(kind: str, st: dict, R: dict) -> Model:
    return knee_model(st, R) if kind == "knee" else splice_model(st, R)
