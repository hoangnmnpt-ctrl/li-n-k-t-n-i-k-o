"""
BEAM SPLICE (BS) - Liên kết nối dầm bằng mặt bích bu lông (bolted end-plate splice)

Tiêu chuẩn : AISC 360-10 (LRFD) + AISC Design Guide 16 / Design Guide 39
Phương pháp: "thick plate" (bản mã đủ dày -> không kể lực nhổ/prying), giống knee joint.
Đơn vị     : mm, kN, MPa, kN.m

Kiểu mặt bích:
    "4E"   : mở rộng 1 phía (extended), 4 bu lông vùng kéo (2 hàng x 2)
    "4ES"  : mở rộng 2 phía (đối xứng) - dùng khi mô men đổi dấu
    "2F"   : bích bằng (flush), 1 hàng bu lông kéo phía trong cánh (2 bu lông)

Liên kết nối dầm gồm 2 bản mã giống nhau áp vào nhau -> chỉ cần kiểm tra 1 phía
(không có kiểm tra phía cột như knee: cánh cột uốn, bụng cột, panel zone...).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# ----------------------------------------------------------------------------
# Vật liệu
# ----------------------------------------------------------------------------
BOLT_GRADES = {
    #  grade      Fnt    Fnv(N)  Fnv(X)  [MPa]   - AISC 360-10 Table J3.2
    "A325":     (620.0, 372.0, 457.0),
    "A490":     (780.0, 457.0, 579.0),
    "8.8":      (600.0, 360.0, 450.0),   # ISO (quy đổi): Fnt=0.75Fu, Fnv=0.45/0.563Fu, Fu=800
    "10.9":     (750.0, 450.0, 563.0),   # Fu=1000
}

PHI_T = 0.75      # bu lông kéo đứt
PHI_V = 0.75      # bu lông cắt, ép mặt, đứt cắt
PHI_B = 0.90      # uốn bản mã
PHI_Y = 1.00      # chảy cắt bản mã (J4.2a)
PHI_W = 0.75      # đường hàn


def hole_diameter(db: float) -> float:
    """Lỗ tiêu chuẩn AISC Table J3.3M."""
    return db + 2.0 if db <= 24.0 else db + 3.0


# ----------------------------------------------------------------------------
# Dữ liệu đầu vào
# ----------------------------------------------------------------------------
@dataclass
class ISection:
    name: str
    d: float      # chiều cao
    bf: float     # bề rộng cánh
    tf: float     # dày cánh
    tw: float     # dày bụng
    Fy: float = 345.0
    Fu: float = 450.0

    @property
    def Zx(self) -> float:  # mm3
        hw = self.d - 2 * self.tf
        return self.bf * self.tf * (self.d - self.tf) + self.tw * hw ** 2 / 4.0

    @property
    def Mp(self) -> float:  # kN.m
        return self.Fy * self.Zx / 1e6


@dataclass
class EndPlate:
    bp: float          # bề rộng bản mã
    tp: float          # chiều dày bản mã
    Fy: float = 345.0
    Fu: float = 450.0


@dataclass
class Bolts:
    db: float                  # đường kính bu lông
    grade: str = "A325"
    g: float = 140.0           # khoảng cách ngang 2 bu lông (gauge)
    pfo: float = 50.0          # cánh -> hàng bu lông ngoài (phần mở rộng)
    pfi: float = 50.0          # cánh -> hàng bu lông trong
    de: float = 40.0           # hàng ngoài -> mép bản mã (phần mở rộng)
    threads_excluded: bool = False

    @property
    def Ab(self) -> float:
        return math.pi * self.db ** 2 / 4.0

    @property
    def Fnt(self) -> float:
        return BOLT_GRADES[self.grade][0]

    @property
    def Fnv(self) -> float:
        return BOLT_GRADES[self.grade][2 if self.threads_excluded else 1]


@dataclass
class Welds:
    wf: float = 10.0           # chân hàn cánh (2 phía)
    ww: float = 6.0            # chân hàn bụng (2 phía)
    FEXX: float = 480.0        # E70XX ~ 482 MPa


@dataclass
class Forces:
    Mu: float                  # kN.m  (+: kéo cánh trên)
    Vu: float                  # kN
    Nu: float = 0.0            # kN (+: kéo) -> quy đổi vào lực cánh


@dataclass
class Check:
    name: str
    demand: float
    capacity: float
    unit: str
    ref: str = ""

    @property
    def ratio(self) -> float:
        return self.demand / self.capacity if self.capacity > 0 else math.inf

    @property
    def ok(self) -> bool:
        return self.ratio <= 1.0


@dataclass
class BeamSplice:
    beam: ISection
    plate: EndPlate
    bolts: Bolts
    welds: Welds
    forces: Forces
    config: str = "4ES"            # "4E" | "4ES" | "2F"
    checks: list[Check] = field(default_factory=list)

    # ------------------------------------------------------------------ geometry
    @property
    def extended(self) -> bool:
        return self.config in ("4E", "4ES")

    @property
    def h0(self) -> float:
        """Tâm cánh nén -> hàng bu lông ngoài (vùng kéo)."""
        b = self.beam
        return b.d - b.tf / 2.0 + self.bolts.pfo

    @property
    def h1(self) -> float:
        """Tâm cánh nén -> hàng bu lông trong (vùng kéo)."""
        b = self.beam
        return b.d - 1.5 * b.tf - self.bolts.pfi

    @property
    def plate_height(self) -> float:
        ext = self.bolts.pfo + self.bolts.de
        n_ext = {"4E": 1, "4ES": 2, "2F": 0}[self.config]
        return self.beam.d + n_ext * ext

    @property
    def n_bolts(self) -> int:
        return {"4E": 8, "4ES": 8, "2F": 4}[self.config]

    def Yp(self) -> float:
        """Thông số đường chảy bản mã (DG16 / AISC 358 Ch.6)."""
        bp, g = self.plate.bp, self.bolts.g
        pfi, pfo = self.bolts.pfi, self.bolts.pfo
        s = 0.5 * math.sqrt(bp * g)
        pfi = min(pfi, s)
        h0, h1 = self.h0, self.h1
        if self.extended:
            return (bp / 2.0 * (h1 * (1 / pfi + 1 / s) + h0 * (1 / pfo) - 0.5)
                    + 2.0 / g * (h1 * (pfi + s)))
        return bp / 2.0 * (h1 * (1 / pfi + 1 / s) - 0.5) + 2.0 / g * (h1 * (pfi + s))

    # ------------------------------------------------------------------ design
    def flange_force(self) -> float:
        """Lực tập trung ở cánh kéo: Mu/(d-tf) + Nu/2 (kN)."""
        b, f = self.beam, self.forces
        return abs(f.Mu) * 1e3 / (b.d - b.tf) + max(f.Nu, 0.0) / 2.0

    def Mu_equiv(self) -> float:
        """Mô men tương đương kể thêm lực kéo dọc trục (kN.m)."""
        b = self.beam
        return self.flange_force() * (b.d - b.tf) / 1e3

    def run(self) -> list[Check]:
        self.checks = []
        b, p, bt, w, f = self.beam, self.plate, self.bolts, self.welds, self.forces
        Mu = self.Mu_equiv()
        if self.config == "4E" and f.Mu < 0:
            raise ValueError("4E chỉ chịu mô men 1 chiều - dùng '4ES' cho mô men đổi dấu.")

        # 1) Bu lông chịu kéo (không prying)  - DG16 eq. 3.4/3.5
        Pt = bt.Fnt * bt.Ab / 1e3                         # kN / bu lông
        hsum = self.h0 + self.h1 if self.extended else self.h1
        Mnp = 2.0 * Pt * hsum / 1e3                       # kN.m
        self.checks.append(Check("Bu lông kéo đứt (φMnp)", Mu, PHI_T * Mnp,
                                 "kN.m", "DG16 3.4, J3.6"))

        # 2) Bản mã chịu uốn - thick plate: φb·Mpl ≥ 1.11·φ·Mnp
        Mpl = p.Fy * p.tp ** 2 * self.Yp() / 1e6
        self.checks.append(Check("Bản mã uốn (φb·Mpl ≥ Mu)", Mu, PHI_B * Mpl,
                                 "kN.m", "DG16 3.7"))
        self.checks.append(Check("Điều kiện bản dày (1.11φMnp ≤ φbMpl)",
                                 1.11 * PHI_T * Mnp, PHI_B * Mpl, "kN.m",
                                 "DG16 - không prying"))

        Ffu = self.flange_force()
        dh = hole_diameter(bt.db)

        # 3) Cắt phần bích mở rộng
        if self.extended:
            Vext = Ffu / 2.0
            Rny = 0.6 * p.Fy * p.bp * p.tp / 1e3
            An = (p.bp - 2 * (dh + 2.0)) * p.tp
            Rnr = 0.6 * p.Fu * An / 1e3
            self.checks.append(Check("Bích mở rộng - chảy cắt", Vext, PHI_Y * Rny,
                                     "kN", "J4.2a"))
            self.checks.append(Check("Bích mở rộng - đứt cắt", Vext, PHI_V * Rnr,
                                     "kN", "J4.2b"))

        # 4) Bu lông chịu cắt: chỉ tính bu lông vùng nén (DG16)
        nb_c = 4 if self.extended else 2
        if self.config == "2F":
            nb_c = 2
        Rv = nb_c * bt.Fnv * bt.Ab / 1e3
        self.checks.append(Check(f"Bu lông cắt ({nb_c} bl vùng nén)", abs(f.Vu),
                                 PHI_V * Rv, "kN", "J3.6"))

        # 5) Ép mặt / xé lỗ tại bản mã (2 bản mã giống nhau -> kiểm 1 bản)
        lc_edge = bt.de - dh / 2.0 if self.extended else math.inf
        lc_in = (bt.pfi + b.tf + bt.pfo) - dh if self.extended else (b.d - 2 * b.tf - 2 * bt.pfi) - dh
        def rn_bear(lc: float) -> float:
            return min(1.2 * lc * p.tp * p.Fu, 2.4 * bt.db * p.tp * p.Fu) / 1e3
        n_edge = 2 if self.extended else 0
        n_in = nb_c - n_edge
        Rbr = n_edge * rn_bear(lc_edge) + n_in * rn_bear(lc_in)
        self.checks.append(Check("Ép mặt / xé lỗ bản mã", abs(f.Vu), PHI_V * Rbr,
                                 "kN", "J3.10"))

        # 6) Hàn cánh - bản mã (2 đường góc, lực vuông góc -> hệ số 1.5)
        Lf = 2 * b.bf - b.tw
        Rwf = 0.6 * w.FEXX * 1.5 * 0.707 * w.wf * Lf / 1e3
        Ff_req = max(Ffu, 0.6 * b.Fy * b.bf * b.tf / 1e3)   # tối thiểu 60% cánh (DG16)
        self.checks.append(Check("Hàn cánh (≥ Ffu, ≥ 0.6FyAf)", Ff_req, PHI_W * Rwf,
                                 "kN", "J2.4"))

        # 7) Hàn bụng: cắt (toàn chiều cao bụng trừ vùng hàn cánh)
        Lw = 2 * (b.d - 2 * b.tf)
        Rww = 0.6 * w.FEXX * 0.707 * w.ww * Lw / 1e3
        self.checks.append(Check("Hàn bụng chịu cắt", abs(f.Vu), PHI_W * Rww,
                                 "kN", "J2.4"))
        # hàn bụng vùng kéo phát triển chảy bụng (DG16): 0.6·Fy·tw trên 1 đơn vị dài
        req_ww = PHI_B * b.Fy * b.tw / (2 * PHI_W * 0.6 * w.FEXX * 0.707 * 1.5)
        self.checks.append(Check("Chân hàn bụng vùng kéo (ww,req)", req_ww, w.ww,
                                 "mm", "DG16 - phát triển chảy bụng"))

        # 8) Cấu tạo
        self.checks.append(Check("Bề rộng bản mã (bp ≤ bf + 25)", p.bp, b.bf + 25.0,
                                 "mm", "DG16 cấu tạo"))
        self.checks.append(Check("Gauge g ≥ bw + 2·(ww) + clearance",
                                 b.tw + 2 * w.ww + 2 * 1.5 * bt.db, bt.g, "mm",
                                 "khoảng vặn cờ lê"))
        return self.checks

    # ------------------------------------------------------------------ report
    def report(self) -> str:
        if not self.checks:
            self.run()
        b, p, bt, f = self.beam, self.plate, self.bolts, self.forces
        L = []
        L.append("=" * 78)
        L.append(f" BEAM SPLICE (BS) - mặt bích {self.config}  |  AISC 360-10 LRFD / DG16")
        L.append("=" * 78)
        L.append(f" Dầm      : {b.name}  d={b.d} bf={b.bf} tf={b.tf} tw={b.tw}  Fy={b.Fy}"
                 f"  φMp={PHI_B * b.Mp:.1f} kN.m")
        L.append(f" Bản mã   : {p.bp} x {self.plate_height:.0f} x {p.tp} mm  Fy={p.Fy}")
        L.append(f" Bu lông  : {self.n_bolts} x M{bt.db:.0f} {bt.grade}  g={bt.g}"
                 f"  pfo={bt.pfo} pfi={bt.pfi} de={bt.de}")
        L.append(f" Hình học : h0={self.h0:.1f}  h1={self.h1:.1f}  Yp={self.Yp():.1f} mm")
        L.append(f" Nội lực  : Mu={f.Mu} kN.m  Vu={f.Vu} kN  Nu={f.Nu} kN"
                 f"  -> Ffu={self.flange_force():.1f} kN")
        L.append("-" * 78)
        L.append(f" {'Kiểm tra':<40}{'Yêu cầu':>10}{'Khả năng':>10}{'Tỷ số':>8}  KQ")
        L.append("-" * 78)
        for c in self.checks:
            L.append(f" {c.name:<40}{c.demand:>10.1f}{c.capacity:>10.1f}"
                     f"{c.ratio:>8.2f}  {'OK' if c.ok else 'NG'}")
        L.append("-" * 78)
        worst = max(self.checks, key=lambda c: c.ratio)
        L.append(f" Tỷ số lớn nhất: {worst.ratio:.2f} ({worst.name})  ->  "
                 f"{'ĐẠT' if all(c.ok for c in self.checks) else 'KHÔNG ĐẠT'}")
        L.append("=" * 78)
        return "\n".join(L)


def required_bolt_diameter(Mu: float, h_sum: float, grade: str = "A325") -> float:
    """db,req = sqrt(2Mu / (π φ Fnt Σh))  (DG16 eq.3.5) - mm."""
    Fnt = BOLT_GRADES[grade][0]
    return math.sqrt(2 * Mu * 1e6 / (math.pi * PHI_T * Fnt * h_sum))


# ----------------------------------------------------------------------------
if __name__ == "__main__":
    beam = ISection("I600x250x12x20", d=600, bf=250, tf=20, tw=12, Fy=345, Fu=450)
    splice = BeamSplice(
        beam=beam,
        plate=EndPlate(bp=270, tp=30, Fy=345, Fu=450),
        bolts=Bolts(db=30, grade="A325", g=140, pfo=55, pfi=55, de=45),
        welds=Welds(wf=12, ww=10),
        forces=Forces(Mu=650.0, Vu=250.0, Nu=0.0),
        config="4ES",
    )
    print(splice.report())
    print(f"\n db,req = {required_bolt_diameter(650, splice.h0 + splice.h1):.1f} mm")
