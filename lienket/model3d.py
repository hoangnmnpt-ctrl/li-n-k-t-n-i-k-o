"""
model3d.py — Mô hình 3D của nút (knee / nối dầm / chân cột) dạng lưới tam giác, để vẽ kiểu RAM Connection.

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
STEEL = "#B9B9B9"
END_PLATE = "#5E5486"
SUPPORT_PLATE = "#22B92B"
STIFF = "#86A878"
PLATE_STIFF = "#ADA8EE"
BOLT = "#D87A28"
WELD = "#F2B42C"
CONCRETE = "#A9ADB3"
GROUT = "#CFC6A8"
WASHER = "#9AA0A8"


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
    focus: tuple | None = None        # tâm vùng nút (camera nhắm vào đây)
    focus_size: float = 0.0           # kích thước vùng nút để phóng hình (mm)
    frame: tuple | None = None        # hộp (min, max) vùng hiển thị như RAM: nút + một đoạn cấu kiện
    view: tuple | None = None         # góc nhìn mặc định (yaw, pitch) riêng của kiểu nút; None = mặc định của khung xem

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


def _bbox2(pts):
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def from_scene(m: Model, sc):
    # bản nắp (supportE, không phải bản gối): sườn trùng cao độ bản nắp thì bỏ — bản nắp đã làm sườn (như RAM)
    caps = [_bbox2(it["pts"]) for it in sc.items if it["k"] == "poly" and it.get("fill") == D.C_PANEL and tuple(it.get("tags", ())) == ("supportE",)]
    for it in sc.items:
        if it["k"] != "poly" or not it.get("z"): continue
        if caps and set(it.get("tags", ())) & {"supEstiff", "supIstiff"}:
            b = _bbox2(it["pts"])
            if any(b[1] < c[3] - 1e-6 and b[3] > c[1] + 1e-6 and b[0] < c[2] and b[2] > c[0] for c in caps):
                continue
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
def _rect_bb(it):
    return _bbox2(it["pts"])


def _set_span(it, axis, lo, hi):
    """Đặt lại khoảng [lo, hi] theo trục axis (0 = x, 1 = y) của đa giác chữ nhật trục thẳng."""
    b = _bbox2(it["pts"])
    o0, o1 = b[axis], b[axis + 2]
    pts = []
    for p in it["pts"]:
        q = list(p)
        q[axis] = lo if abs(p[axis] - o0) < abs(p[axis] - o1) else hi
        pts.append(tuple(q))
    it["pts"] = pts


def _knee_support_as_plate(sc, st, G, C):
    """Bản gối (connection plate, xanh lá) cùng kích thước với bản đầu như RAM: kéo dài theo chiều bản (sTop → sBot);
    phần cấu kiện gối phía sau được nối tiếp đúng mép bản. Thêm sườn tam giác phía gối ở phần bản nhô ngoài."""
    T = G["type"]
    items = [it for it in sc.items if it["k"] == "poly"]
    supp = next((it for it in items if {"supportE", "supportI"} <= set(it.get("tags", ())) and it.get("fill") in (D.C_PLATE, D.C_PANEL)), None)
    if supp is None or T == "xien":
        return None
    a, b = C(G["sTop"]), C(G["sBot"])
    if T == "dung":
        lo, hi = min(a[1], b[1]), max(a[1], b[1])
        sb = _rect_bb(supp)
        for it in items:                                   # cánh trong cột ngay dưới bản gối → nối tới mép dưới bản
            if it is supp or it.get("fill") != D.C_STEEL: continue
            bb = _rect_bb(it)
            if abs(bb[0] - sb[0]) < 1e-3 and abs(bb[2] - sb[2]) < 1e-3 and abs(bb[3] - sb[1]) < 1e-3:
                _set_span(it, 1, bb[1], lo)
        _set_span(supp, 1, lo, hi)
        return dict(x=sb[0], top=hi, col_top=sb[3])
    lo, hi = min(a[0], b[0]), max(a[0], b[0])
    sb = _rect_bb(supp)
    if sb[2] > hi + 1e-3:                                  # phần cánh kèo ngoài bản → thép
        sc.items.append(dict(supp, pts=[(hi, sb[1]), (sb[2], sb[1]), (sb[2], sb[3]), (hi, sb[3])], fill=D.C_STEEL, tags=()))
    _set_span(supp, 0, lo, hi)
    return None


def knee_model(st: dict, R: dict) -> Model:
    m = Model()
    G = R["G"]; T = G["type"]; M1 = G["M1"]; sup = st["sup"]
    tp = float(st["plate"]["tp"])
    nn = D.ang(G["thN"])
    t = (-nn[1], nn[0]) if T == "ngang" else (nn[1], -nn[0])
    C = lambda s: (t[0] * s, t[1] * s)
    sc = D.elevation(st, R, None, flow=False)
    info = _knee_support_as_plate(sc, st, G, C)
    from_scene(m, sc)
    pst = st["plate"].get("stiffE", {})
    if info and pst.get("on") and st["plate"].get("extension") in ("external", "both") and info["top"] > info["col_top"] + 1:
        # sườn tam giác phía cột (xanh lá) trên phần bản nhô, tựa lên đỉnh cột / bản nắp — như RAM
        L, w = float(pst.get("L", 150)), float(pst.get("ts", 10))
        ta = math.tan(math.radians(G["a"]))
        x0 = info["x"]
        y0 = info["col_top"] + (x0 * ta if sup.get("condE") == "top_cap" else 0.0)
        y1 = y0 + (-L * ta if sup.get("condE") == "top_cap" else 0.0)
        add_prism(m, [(x0, y0, -w / 2), (x0, info["top"], -w / 2), (x0 - L, y1, -w / 2)], (0.0, 0.0, w), SUPPORT_PLATE, ("supportE",))
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
    mid = C((G["sTop"] + G["sBot"]) / 2)
    m.focus = (mid[0] + face[0] / 2, mid[1] + face[1] / 2, 0.0)
    m.focus_size = 2.3 * max(G["dp"], G["M2"]["d"], G["sBot"] - G["sTop"])
    # khung như RAM: cột (hoặc kèo với knee ngang) + ~1.25d kèo về phía có bản, bản đầu ở giữa
    ends = [C(G["sTop"]), C(G["sBot"])]
    xs = [p[0] for p in ends]; ys = [p[1] for p in ends]
    d = max(G["dp"], G["M2"]["d"])
    bf = max(M1["bfE"], M1["bfI"], G["M2"]["bfE"])
    if T == "ngang":
        lo = (min(xs) - 0.25 * d, min(ys) - 0.75 * d, -bf / 2); hi = (max(xs) + 1.35 * d, max(ys) + 1.05 * d, bf / 2)
    else:
        lo = (min(xs) - G["M2"]["d"] - 40, min(ys) - 0.55 * d, -bf / 2); hi = (max(xs) + 1.25 * d, max(ys) + 60, bf / 2)
    m.frame = (lo, hi)
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
    m.focus = ((tp2 - tp1) / 2, -(G["sTop"] + G["sBot"]) / 2, 0.0)
    m.focus_size = 3.2 * (G["sBot"] - G["sTop"])
    return m


# ─────────────────────────── chân cột ───────────────────────────
def box(m, lo, hi, color, tags=()):
    add_prism(m, [(lo[0], lo[1], lo[2]), (hi[0], lo[1], lo[2]), (hi[0], lo[1], hi[2]), (lo[0], lo[1], hi[2])],
              (0.0, hi[1] - lo[1], 0.0), color, tags)


def base_model(st: dict, R: dict) -> Model:
    """Chân cột: x theo phương N (chiều cao tiết diện cột), y hướng lên, z theo phương B. Mặt trên bản đế ở y = tp."""
    m = Model()
    G = R["G"]; c = G["col"]; an = st["anchor"]
    N, B, N2, B2, tp, gr = G["N"], G["B"], G["N2"], G["B2"], G["tp"], G["grout"]
    d, tw, tfE, tfI = G["d"], c["tw"], c["tfE"], c["tfI"]
    hshow = min(G["ha"], 0.55 * max(N2, B2))
    box(m, (-N2 / 2, -gr - hshow, -B2 / 2), (N2 / 2, -gr, B2 / 2), CONCRETE, ("conc",))
    if gr > 0:
        box(m, (-N / 2 - 25, -gr, -B / 2 - 25), (N / 2 + 25, 0.0, B / 2 + 25), GROUT, ("conc",))
    box(m, (-N / 2, 0.0, -B / 2), (N / 2, tp, B / 2), END_PLATE, ("bp",))
    Hc = max(1.6 * d, 500.0)
    box(m, (d / 2 - tfE, tp, -c["bfE"] / 2), (d / 2, tp + Hc, c["bfE"] / 2), STEEL, ("col", "wflange"))
    box(m, (-d / 2, tp, -c["bfI"] / 2), (-d / 2 + tfI, tp + Hc, c["bfI"] / 2), STEEL, ("col", "wflange"))
    box(m, (-d / 2 + tfI, tp, -tw / 2), (d / 2 - tfE, tp + Hc, tw / 2), STEEL, ("col", "wweb"))
    wf = max(float(st["weld"]["fl"].get("w", 8)), 5.0)
    ww = max(float(st["weld"]["web"].get("w", 6)), 5.0)
    up = (0.0, 1.0, 0.0)
    weld_bead(m, (d / 2, tp, -c["bfE"] / 2), (1.0, 0.0, 0.0), up, (0.0, 0.0, c["bfE"]), wf, ("wflange",))
    weld_bead(m, (-d / 2, tp, -c["bfI"] / 2), (-1.0, 0.0, 0.0), up, (0.0, 0.0, c["bfI"]), wf, ("wflange",))
    for s in (1, -1):
        weld_bead(m, (-d / 2 + tfI, tp, s * tw / 2), (0.0, 0.0, float(s)), up, (d - tfE - tfI, 0.0, 0.0), ww, ("wweb",))
    da = float(an["d"]); wB = float(an.get("washer") or 3 * da); wT = float(an.get("washerT") or 8)
    for a in G["anchors"]:
        x, z = a["x"], a["y"]
        box(m, (x - wB / 2, tp, z - wB / 2), (x + wB / 2, tp + wT, z + wB / 2), WASHER, ("anchors",))
        hex_prism(m, (x, tp + wT, z), up, (1.0, 0.0, 0.0), 0.92 * da, 0.9 * da, BOLT, ("anchors",))
        hex_prism(m, (x, tp + wT + 0.9 * da, z), up, (1.0, 0.0, 0.0), 0.5 * da, 0.6 * da, BOLT, ("anchors",))
    m.focus = (0.0, tp + 0.15 * Hc, 0.0)
    m.focus_size = 1.5 * max(N2, B2, d)
    m.frame = ((-0.6 * N2, -gr - hshow, -0.6 * B2), (0.6 * N2, tp + 1.1 * Hc, 0.6 * B2))
    m.view = (32.0, 24.0)
    return m


def build(kind: str, st: dict, R: dict) -> Model:
    if kind == "base":
        return base_model(st, R)
    return knee_model(st, R) if kind == "knee" else splice_model(st, R)
