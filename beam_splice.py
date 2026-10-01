"""
Liên kết nối dầm (Beam Splice - BS) bằng mặt bích bu lông.

Cơ sở tính toán
    - AISC 360-10 (LRFD): J2.4 (hàn), J3.6 (bu lông kéo/cắt), J3.10 (ép mặt), J4.2 (cắt bản mã)
    - AISC Design Guide 39 "End-Plate Moment Connections" (2023), Ch.3 và Ch.5
      quy trình "bản mã dày / bu lông nhỏ" (thick end-plate, không kể lực nhổ - prying):
          Mu,eq  = Mu + (Tu/2)(d - tf)                       (DG39 Eq. 3-30)
          db,req = sqrt( 4 Mu,eq / (pi*phi*Fnt*Sum(ni*hi)) )   (DG39 Eq. 5-3a)
          tp,req = sqrt( 1.10 Mu,eq / (gr*phib*Fyp*Yp) )       (DG39 Eq. 5-4a)
      Liên kết nối dầm gồm 2 bản mã giống nhau áp vào nhau nên chỉ kiểm tra 1 phía
      và KHÔNG có các kiểm tra phía cột (cánh cột uốn, bụng cột, vùng panel...).

Kiểu mặt bích (config)
    "2F" : bích bằng 2 bu lông (Two-bolt flush unstiffened)       - DG39 Table 5-2
    "4E" : bích mở rộng 4 bu lông (Four-bolt extended unstiffened) - DG39 Eq. 3-14
           extended_both=True : mở rộng cả 2 phía, 8 bu lông (mô men đổi dấu)
           extended_both=False: chỉ mở rộng phía cánh kéo, 6 bu lông (mô men 1 chiều)

Đơn vị: chiều dài mm, ứng suất MPa, lực kN, mô men kN.m.

GHI CHÚ: phần trích DG39 dùng để đối chiếu dừng ở khoảng trang 69, nên các mục dưới đây là
quy ước kỹ sư, chưa đối chiếu với DG39 -> cần soát lại trước khi dùng thiết kế thật:
    * hàn bụng vùng kéo (phát triển cường độ chảy bụng) và hàn bụng chịu cắt,
    * bu lông A325/A490 chỉ theo Table J3.2; cấp 8.8 / 10.9 là quy đổi tỷ lệ theo Fu,
    * kiểm tra xé lỗ / ép mặt bản mã (hướng lực lấy theo phía bất lợi),
    * khoảng cách tối thiểu pfi/pfo (db + 13 mm) theo khuyến nghị DG4.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field

# ----------------------------------------------------------------------------
# Hằng số / vật liệu
# ----------------------------------------------------------------------------
PHI_T = 0.75    # bu lông kéo đứt
PHI_V = 0.75    # bu lông cắt, ép mặt, đứt cắt bản mã, hàn
PHI_B = 0.90    # uốn bản mã
PHI_Y = 1.00    # chảy cắt bản mã (J4.2a)
PHI_W = 0.75    # đường hàn

# (Fnt, Fnv ren trong mặt cắt "N", Fnv ren ngoài mặt cắt "X") [MPa]
# A325/A490: AISC 360-10 Table J3.2 (90/54/68 ksi và 113/68/84 ksi).
# 8.8 / 10.9: quy đổi theo Fu (0.75Fu, 0.45Fu, 0.563Fu) - không có trong AISC.
BOLT_GRADES: dict[str, tuple[float, float, float]] = {
    "A325": (620.0, 372.0, 469.0),
    "A490": (780.0, 469.0, 579.0),
    "8.8":  (600.0, 360.0, 450.0),
    "10.9": (750.0, 450.0, 563.0),
}

STD_BOLT_D = [16, 20, 22, 24, 27, 30, 36]
STD_PLATE_T = [10, 12, 14, 16, 18, 20, 22, 25, 28, 30, 32, 36, 40, 45, 50]
STD_WELD = [6, 8, 10, 12, 14, 16]
# AISC 360-10 Table J3.4M - khoảng cách mép tối thiểu (mép cắt)
MIN_EDGE = {16: 22, 20: 26, 22: 28, 24: 30, 27: 34, 30: 38, 36: 46}

TENSION_ZONE_EXTRA = 152.0   # mm (6 in.) kể từ hàng bu lông trong cùng (DG39 Eq. 3-40)


def hole_diameter(db: float) -> float:
    """Lỗ tiêu chuẩn, AISC 360-10 Table J3.3M."""
    return db + 2.0 if db <= 22.0 else db + 3.0


def min_edge(db: float) -> float:
    for d in sorted(MIN_EDGE):
        if db <= d:
            return float(MIN_EDGE[d])
    return 1.25 * db


def min_fillet(t_thin: float) -> float:
    """Chân hàn góc tối thiểu, AISC 360-10 Table J2.4."""
    if t_thin <= 6:
        return 3.0
    if t_thin <= 13:
        return 5.0
    if t_thin <= 19:
        return 6.0
    return 8.0


def _round_up(x: float, step: float) -> float:
    return math.ceil(x / step - 1e-9) * step


# ----------------------------------------------------------------------------
# Dữ liệu đầu vào
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Beam:
    name: str
    d: float
    bf: float
    tf: float
    tw: float
    Fy: float = 345.0
    Fu: float = 450.0

    @property
    def hw(self) -> float:
        return self.d - 2.0 * self.tf


@dataclass(frozen=True)
class EndPlate:
    bp: float
    tp: float
    Fy: float = 345.0
    Fu: float = 450.0
    dp: float | None = None        # chiều cao bản mã (chỉ dùng cho bích bằng, tùy chọn)


@dataclass(frozen=True)
class BoltLayout:
    db: float
    grade: str = "A325"
    g: float = 120.0               # khoảng cách ngang giữa 2 bu lông
    pfo: float = 55.0              # mặt cánh -> hàng ngoài (phần mở rộng)
    pfi: float = 55.0              # mặt cánh -> hàng trong
    de: float = 45.0               # hàng ngoài -> mép bản mã (phần mở rộng)
    threads_in_shear_plane: bool = True    # True: Fnv loại N, False: loại X

    def __post_init__(self) -> None:
        if self.grade not in BOLT_GRADES:
            raise ValueError(f"Cấp bu lông '{self.grade}' không hỗ trợ: {list(BOLT_GRADES)}")

    @property
    def Ab(self) -> float:
        return math.pi * self.db ** 2 / 4.0

    @property
    def Fnt(self) -> float:
        return BOLT_GRADES[self.grade][0]

    @property
    def Fnv(self) -> float:
        return BOLT_GRADES[self.grade][1 if self.threads_in_shear_plane else 2]

    @property
    def dh(self) -> float:
        return hole_diameter(self.db)


@dataclass(frozen=True)
class WeldSpec:
    wf: float = 10.0               # chân hàn góc cánh (hàn 2 phía)
    ww: float = 8.0                # chân hàn góc bụng (hàn 2 phía)
    FEXX: float = 480.0            # E70XX


@dataclass(frozen=True)
class LoadCase:
    name: str
    Mu: float                      # kN.m
    Vu: float                      # kN
    Nu: float = 0.0                # kN, + là kéo (nén được bỏ qua - thiên về an toàn)


@dataclass(frozen=True)
class Check:
    group: str
    name: str
    demand: float
    capacity: float
    unit: str
    ref: str = ""

    @property
    def ratio(self) -> float:
        if self.capacity <= 0:
            return math.inf if self.demand > 0 else 0.0
        return self.demand / self.capacity

    @property
    def ok(self) -> bool:
        return self.ratio <= 1.0 + 1e-9


@dataclass
class Result:
    load: LoadCase
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def worst(self) -> Check:
        return max(self.checks, key=lambda c: c.ratio)


# ----------------------------------------------------------------------------
# Liên kết
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Splice:
    beam: Beam
    plate: EndPlate
    bolts: BoltLayout
    weld: WeldSpec = WeldSpec()
    config: str = "4E"
    extended_both: bool = True

    def __post_init__(self) -> None:
        if self.config not in ("2F", "4E"):
            raise ValueError("config phải là '2F' hoặc '4E'")

    # -------------------------------------------------------------- hình học
    @property
    def extended(self) -> bool:
        return self.config == "4E"

    @property
    def h_outer(self) -> float:
        """Tâm cánh nén -> hàng bu lông ngoài vùng kéo (DG39: h1 của 4E)."""
        return self.beam.d - self.beam.tf / 2.0 + self.bolts.pfo

    @property
    def h_inner(self) -> float:
        """Tâm cánh nén -> hàng bu lông trong vùng kéo (DG39: h2 của 4E, h1 của 2F)."""
        return self.beam.d - 1.5 * self.beam.tf - self.bolts.pfi

    @property
    def sum_nh(self) -> float:
        """Sum(ni*hi) cho các bu lông vùng kéo (mm)."""
        if self.extended:
            return 2.0 * self.h_outer + 2.0 * self.h_inner
        return 2.0 * self.h_inner

    @property
    def s(self) -> float:
        return 0.5 * math.sqrt(self.plate.bp * self.bolts.g)

    @property
    def pfi_eff(self) -> float:
        return min(self.bolts.pfi, self.s)           # "dùng pfi = s nếu pfi > s"

    @property
    def gamma_r(self) -> float:
        return 1.0 if self.extended else 0.80        # DG39 Eq. 5-1

    @property
    def Yp(self) -> float:
        """Thông số đường chảy bản mã (mm)."""
        bp, g, s, pfi = self.plate.bp, self.bolts.g, self.s, self.pfi_eff
        h_in = self.h_inner
        if self.extended:      # DG39 Eq. 3-14
            return (bp / 2.0 * (self.h_outer / self.bolts.pfo
                                + h_in * (1.0 / pfi + 1.0 / s) - 0.5)
                    + 2.0 / g * h_in * (pfi + s))
        return bp / 2.0 * h_in * (1.0 / pfi + 1.0 / s) + 2.0 / g * h_in * (pfi + s)   # Table 5-2

    @property
    def Mpl(self) -> float:
        """kN.m"""
        return self.plate.Fy * self.plate.tp ** 2 * self.Yp / 1e6

    @property
    def Pt(self) -> float:
        """Lực kéo danh định 1 bu lông (kN)."""
        return self.bolts.Fnt * self.bolts.Ab / 1e3

    @property
    def Mnp(self) -> float:
        """Mô men danh định khi bu lông đứt, không prying (kN.m)."""
        return self.Pt * self.sum_nh / 1e3

    @property
    def n_bolts(self) -> int:
        if self.extended:
            return 8 if self.extended_both else 6
        return 4

    @property
    def n_shear_bolts(self) -> int:
        """Số bu lông vùng nén chịu cắt tại mặt tiếp xúc."""
        return 4 if (self.extended and self.extended_both) else 2

    @property
    def plate_height(self) -> float:
        b = self.bolts
        if self.extended:
            return self.beam.d + (b.pfo + b.de) * (2 if self.extended_both else 1)
        return self.plate.dp if self.plate.dp else self.beam.d + 50.0

    @property
    def weld_length_flange(self) -> float:
        return 2.0 * self.beam.bf - self.beam.tw

    # -------------------------------------------------------------- tải
    def Mu_eq(self, load: LoadCase) -> float:
        """DG39 Eq. 3-30 (kN.m)."""
        return abs(load.Mu) + max(load.Nu, 0.0) / 2.0 * (self.beam.d - self.beam.tf) / 1e3

    def flange_force(self, load: LoadCase) -> float:
        """Lực cánh kéo tính toán (kN)."""
        return abs(load.Mu) * 1e3 / (self.beam.d - self.beam.tf) + max(load.Nu, 0.0) / 2.0

    def flange_force_weld(self, load: LoadCase) -> float:
        """Lực thiết kế hàn cánh: max(tính toán, 0.6 Fy bf tf) nhưng <= Fy bf tf (DG39 Eq. 3-38)."""
        b = self.beam
        Tyf = b.Fy * b.bf * b.tf / 1e3
        return min(max(self.flange_force(load), 0.6 * Tyf), Tyf)

    def db_required(self, load: LoadCase) -> float:
        """DG39 Eq. 5-3a (mm)."""
        return math.sqrt(4.0 * self.Mu_eq(load) * 1e6
                         / (math.pi * PHI_T * self.bolts.Fnt * self.sum_nh))

    def tp_required(self, load: LoadCase) -> float:
        """DG39 Eq. 5-4a (mm)."""
        return math.sqrt(1.10 * self.Mu_eq(load) * 1e6
                         / (self.gamma_r * PHI_B * self.plate.Fy * self.Yp))

    # -------------------------------------------------------------- kiểm tra
    def _fillet_per_mm(self, leg: float, factor: float = 1.0) -> float:
        """Cường độ 1 mm dài đường hàn góc 2 phía (N/mm), đã nhân phi."""
        return PHI_W * 0.6 * self.weld.FEXX * 0.707 * leg * 2.0 * factor

    def check(self, load: LoadCase) -> Result:
        b, p, bt, w = self.beam, self.plate, self.bolts, self.weld
        res = Result(load)
        add = lambda *a, **k: res.checks.append(Check(*a, **k))   # noqa: E731
        Mu_eq = self.Mu_eq(load)
        Vu = abs(load.Vu)
        Tcalc = self.flange_force(load)
        dh = bt.dh

        # --- bu lông ---
        add("Bu lông", "Bu lông kéo đứt: Mu,eq ≤ φMnp", Mu_eq, PHI_T * self.Mnp,
            "kN.m", "DG39 5-3, Spec J3.6")
        add("Bu lông", f"Bu lông cắt ({self.n_shear_bolts} bl vùng nén): Vu ≤ φnFnvAb", Vu,
            PHI_V * self.n_shear_bolts * bt.Fnv * bt.Ab / 1e3, "kN", "Spec J3.6")

        # --- bản mã ---
        add("Bản mã", "Bản mã uốn: 1.10Mu,eq ≤ γr·φb·Mpl", 1.10 * Mu_eq,
            self.gamma_r * PHI_B * self.Mpl, "kN.m", "DG39 5-4")
        if self.extended:
            Vext = Tcalc / 2.0
            add("Bản mã", "Phần mở rộng - chảy cắt", Vext,
                PHI_Y * 0.6 * p.Fy * p.bp * p.tp / 1e3, "kN", "Spec J4.2a")
            An = (p.bp - 2.0 * (dh + 2.0)) * p.tp
            add("Bản mã", "Phần mở rộng - đứt cắt", Vext,
                PHI_V * 0.6 * p.Fu * An / 1e3, "kN", "Spec J4.2b")
            lc = min(bt.de - dh / 2.0, bt.pfi + b.tf + bt.pfo - dh)
        else:
            overhang = (self.plate_height - b.d) / 2.0
            lc = bt.pfi + b.tf + overhang - dh / 2.0
        rn_bolt = min(1.2 * lc * p.tp * p.Fu, 2.4 * bt.db * p.tp * p.Fu) / 1e3
        add("Bản mã", "Ép mặt / xé lỗ bản mã (bu lông chịu cắt)", Vu,
            PHI_V * self.n_shear_bolts * rn_bolt, "kN", "Spec J3.10")

        # --- hàn ---
        Lf = self.weld_length_flange
        add("Hàn", "Hàn cánh: max(Tcalc, 0.6FyAf) ≤ φRn (θ=90°)",
            self.flange_force_weld(load),
            PHI_W * 0.6 * w.FEXX * 1.5 * 0.707 * w.wf * Lf / 1e3,
            "kN", "Spec J2.4, DG39 3-38")
        # bụng vùng kéo: phát triển cường độ chảy bụng (Fy.tw trên mỗi mm dài)
        add("Hàn", "Hàn bụng vùng kéo: Fy·tw ≤ φ·Rn/mm", b.Fy * b.tw,
            self._fillet_per_mm(w.ww, 1.5), "N/mm", "quy ước - xem ghi chú đầu file")
        add("Hàn", "Hàn bụng chịu cắt: Vu ≤ φRn (toàn chiều cao bụng)", Vu,
            self._fillet_per_mm(w.ww) * b.hw / 1e3, "kN", "Spec J2.4")
        t_f = min(b.tf, p.tp)
        t_w = min(b.tw, p.tp)
        add("Hàn", "Chân hàn cánh ≥ tối thiểu J2.4", min_fillet(t_f), w.wf, "mm", "Spec J2.4")
        add("Hàn", "Chân hàn bụng ≥ tối thiểu J2.4", min_fillet(t_w), w.ww, "mm", "Spec J2.4")

        # --- cấu tạo ---
        add("Cấu tạo", "Bề rộng bản mã: bp ≤ bf + max(tp, 25)", p.bp, b.bf + max(p.tp, 25.4),
            "mm", "DG39 Eq. 4-3")
        add("Cấu tạo", "Gauge: g ≤ bf", bt.g, b.bf, "mm", "DG39 Eq. 4-1")
        add("Cấu tạo", "Khoảng cách 2 bu lông ngang ≥ 2.667db", 8.0 / 3.0 * bt.db, bt.g,
            "mm", "Spec J3.3")
        add("Cấu tạo", "Bản mã phải rộng hơn gauge + 2 khoảng mép", bt.g + 2.0 * min_edge(bt.db),
            p.bp, "mm", "Spec J3.4M")
        add("Cấu tạo", "Mép phần mở rộng de ≥ J3.4M", min_edge(bt.db),
            bt.de if self.extended else math.inf, "mm", "Spec J3.4M")
        add("Cấu tạo", "pfi, pfo ≥ db + 13 (cờ lê)", bt.db + 13.0, min(bt.pfi, bt.pfo),
            "mm", "khuyến nghị DG4")
        return res

    def check_all(self, loads: list[LoadCase]) -> list[Result]:
        return [self.check(l) for l in loads]

    # -------------------------------------------------------------- báo cáo
    def report(self, loads: list[LoadCase]) -> str:
        b, p, bt, w = self.beam, self.plate, self.bolts, self.weld
        kind = {"2F": "Bích bằng 2 bu lông (2F)",
                "4E": "Bích mở rộng 4 bu lông (4E), " +
                      ("mở rộng 2 phía" if self.extended_both else "mở rộng phía kéo")}[self.config]
        L = ["=" * 82,
             f" LIÊN KẾT NỐI DẦM (BEAM SPLICE) - {kind}",
             " AISC 360-10 LRFD + AISC Design Guide 39 (thick end-plate, không prying)",
             "=" * 82,
             f" Dầm     : {b.name}  d={b.d:g} bf={b.bf:g} tf={b.tf:g} tw={b.tw:g}  Fy={b.Fy:g}",
             f" Bản mã  : {p.bp:g} x {self.plate_height:g} x {p.tp:g} mm  Fy={p.Fy:g} Fu={p.Fu:g}",
             f" Bu lông : {self.n_bolts} x M{bt.db:g} {bt.grade}  g={bt.g:g} pfo={bt.pfo:g} "
             f"pfi={bt.pfi:g} de={bt.de:g}",
             f" Đường hàn: cánh {w.wf:g} mm, bụng {w.ww:g} mm, E{w.FEXX / 6.894757:.0f}XX (góc, 2 phía)",
             f" Hình học: h_ngoài={self.h_outer:.1f}  h_trong={self.h_inner:.1f}  "
             f"ΣnH={self.sum_nh:.1f}  s={self.s:.1f}  Yp={self.Yp:.1f} mm",
             f" φMnp={PHI_T * self.Mnp:.1f} kN.m   γr·φb·Mpl/1.10="
             f"{self.gamma_r * PHI_B * self.Mpl / 1.10:.1f} kN.m   φb·Mp(dầm)="
             f"{PHI_B * b.Fy * self._Zx() / 1e6:.1f} kN.m"]
        for r in self.check_all(loads):
            ld = r.load
            L += ["-" * 82,
                  f" Tổ hợp {ld.name}: Mu={ld.Mu:g} kN.m  Vu={ld.Vu:g} kN  Nu={ld.Nu:g} kN"
                  f"  ->  Mu,eq={self.Mu_eq(ld):.1f} kN.m   "
                  f"db,req={self.db_required(ld):.1f} mm   tp,req={self.tp_required(ld):.1f} mm",
                  "-" * 82,
                  f" {'Kiểm tra':<54}{'Yêu cầu':>9}{'Khả năng':>10}{'Tỷ số':>7}  KQ"]
            grp = ""
            for c in r.checks:
                if c.group != grp:
                    grp = c.group
                    L.append(f"  [{grp}]")
                L.append(f"  {c.name:<53}{c.demand:>9.1f}{c.capacity:>10.1f}{c.ratio:>7.2f}"
                         f"  {'OK' if c.ok else 'NG'}")
            wc = r.worst
            L.append(f" => {'ĐẠT' if r.ok else 'KHÔNG ĐẠT'}; tỷ số lớn nhất {wc.ratio:.2f} ({wc.name})")
        L.append("=" * 82)
        return "\n".join(L)

    def _Zx(self) -> float:
        b = self.beam
        return b.bf * b.tf * (b.d - b.tf) + b.tw * b.hw ** 2 / 4.0


# ----------------------------------------------------------------------------
# Tự chọn kích thước
# ----------------------------------------------------------------------------
def default_layout(beam: Beam, db: float, grade: str = "A325") -> BoltLayout:
    pf = _round_up(db + 25.0, 5.0)
    de = max(_round_up(1.5 * db, 5.0), min_edge(db))
    g_min = max(_round_up(8.0 / 3.0 * db, 5.0), beam.tw + 2.0 * 10.0 + hole_diameter(db) + 10.0)
    g = min(max(_round_up(0.55 * beam.bf, 5.0), g_min), beam.bf)
    return BoltLayout(db=db, grade=grade, g=g, pfo=pf, pfi=pf, de=de)


def required_welds(beam: Beam, plate_tp: float, loads: list[LoadCase], splice: Splice,
                   FEXX: float) -> tuple[float, float]:
    """Chân hàn (mm) nhỏ nhất đạt, làm tròn lên cỡ tiêu chuẩn. Raise nếu > 16 mm."""
    Lf = splice.weld_length_flange
    wf_req = max(splice.flange_force_weld(l) * 1e3 / (PHI_W * 0.6 * FEXX * 1.5 * 0.707 * Lf)
                 for l in loads)
    wf_req = max(wf_req, min_fillet(min(beam.tf, plate_tp)))
    ww_tension = beam.Fy * beam.tw / (PHI_W * 0.6 * FEXX * 0.707 * 2.0 * 1.5)
    ww_shear = max(abs(l.Vu) * 1e3 / (PHI_W * 0.6 * FEXX * 0.707 * 2.0 * beam.hw) for l in loads)
    ww_req = max(ww_tension, ww_shear, min_fillet(min(beam.tw, plate_tp)))
    out = []
    for req, what in ((wf_req, "cánh"), (ww_req, "bụng")):
        std = [x for x in STD_WELD if x >= req - 1e-9]
        if not std:
            raise ValueError(f"Hàn {what} cần {req:.1f} mm > {STD_WELD[-1]} mm: "
                             "dùng hàn ngấu hoặc tăng kích thước dầm")
        out.append(float(std[0]))
    return out[0], out[1]


def auto_design(beam: Beam, loads: list[LoadCase], config: str = "4E",
                extended_both: bool = True, grade: str = "A325",
                plate_Fy: float = 345.0, plate_Fu: float = 450.0, FEXX: float = 480.0,
                threads_in_shear_plane: bool = True) -> Splice:
    """Chọn bu lông + bản mã + hàn nhỏ nhất (theo thứ tự đường kính, rồi chiều dày) đạt mọi kiểm tra."""
    bp = min(_round_up(beam.bf + 10.0, 5.0), beam.bf + 25.0)
    for db in STD_BOLT_D:
        lay = default_layout(beam, db, grade)
        lay = BoltLayout(**{**lay.__dict__, "threads_in_shear_plane": threads_in_shear_plane})
        for tp in STD_PLATE_T:
            plate = EndPlate(bp=bp, tp=tp, Fy=plate_Fy, Fu=plate_Fu)
            trial = Splice(beam, plate, lay, WeldSpec(16, 16, FEXX), config, extended_both)
            # hàn độc lập với bu lông/bản mã: chọn bu lông + bản mã trước (bỏ qua nhóm "Hàn"),
            # rồi tính chân hàn nhỏ nhất
            if not all(c.ok for r in trial.check_all(loads) for c in r.checks
                       if c.group != "Hàn"):
                continue
            wf, ww = required_welds(beam, tp, loads, trial, FEXX)
            final = Splice(beam, plate, lay, WeldSpec(wf, ww, FEXX), config, extended_both)
            if all(r.ok for r in final.check_all(loads)):
                return final
    raise ValueError("Không tìm được cấu hình đạt: tăng cấp bu lông, đổi kiểu bích hoặc thêm sườn")


# ----------------------------------------------------------------------------
# Đầu vào JSON / CLI
# ----------------------------------------------------------------------------
def splice_from_dict(data: dict) -> tuple[Splice, list[LoadCase]]:
    beam = Beam(**data["beam"])
    loads = [LoadCase(**l) for l in data["loads"]]
    config = data.get("config", "4E")
    both = data.get("extended_both", True)
    if "plate" in data and "bolts" in data:
        weld = WeldSpec(**data.get("weld", {}))
        sp = Splice(beam, EndPlate(**data["plate"]), BoltLayout(**data["bolts"]), weld, config, both)
    else:
        opts = {k: data[k] for k in ("grade", "plate_Fy", "plate_Fu", "FEXX",
                                      "threads_in_shear_plane") if k in data}
        sp = auto_design(beam, loads, config, both, **opts)
    return sp, loads


DEMO = {
    "beam": {"name": "I600x250x12x20", "d": 600, "bf": 250, "tf": 20, "tw": 12, "Fy": 345, "Fu": 450},
    "config": "4E",
    "extended_both": True,
    "loads": [{"name": "LC1", "Mu": 650.0, "Vu": 250.0, "Nu": 0.0},
              {"name": "LC2 (đảo dấu)", "Mu": -400.0, "Vu": -180.0, "Nu": 60.0}],
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Kiểm tra / thiết kế liên kết nối dầm bằng mặt bích")
    ap.add_argument("input", nargs="?", help="file JSON đầu vào (bỏ trống để chạy ví dụ)")
    ap.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    args = ap.parse_args(argv)
    data = json.load(open(args.input, encoding="utf-8")) if args.input else DEMO
    sp, loads = splice_from_dict(data)
    if args.json:
        out = [{"load": r.load.name, "ok": r.ok,
                "checks": [{"name": c.name, "demand": c.demand, "capacity": c.capacity,
                            "ratio": c.ratio, "ok": c.ok} for c in r.checks]}
               for r in sp.check_all(loads)]
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(sp.report(loads))
    return 0 if all(r.ok for r in sp.check_all(loads)) else 1


if __name__ == "__main__":
    sys.exit(main())
