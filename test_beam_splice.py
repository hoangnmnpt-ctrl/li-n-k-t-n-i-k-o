"""
Kiểm chứng beam_splice.py.   Chạy:  python -m unittest -v

Ca đối chiếu: AISC Design Guide 39, Example 5.2-1 (Two-Bolt Flush Unstiffened, thick end-plate)
Dữ liệu gốc hệ Mỹ -> đổi sang SI:  1 in = 25.4 mm, 1 ksi = 6.894757 MPa,
1 kip = 4.448222 kN, 1 kip-in = 0.1129848 kN.m
"""
import math
import unittest

from beam_splice import (Beam, BoltLayout, EndPlate, LoadCase, Splice, WeldSpec,
                         auto_design, hole_diameter, DEMO, splice_from_dict)

IN, KSI, KIP, KIPIN = 25.4, 6.894757, 4.448222, 0.1129848


def dg39_example_5_2_1() -> tuple[Splice, LoadCase]:
    beam = Beam("W18x35", d=17.7 * IN, bf=6.00 * IN, tf=0.425 * IN, tw=0.300 * IN,
                Fy=50 * KSI, Fu=65 * KSI)
    plate = EndPlate(bp=7 * IN, tp=0.625 * IN, Fy=50 * KSI, Fu=65 * KSI, dp=18.75 * IN)
    bolts = BoltLayout(db=0.75 * IN, grade="A325", g=3.5 * IN, pfi=1.5 * IN, pfo=1.5 * IN, de=1.5 * IN)
    sp = Splice(beam, plate, bolts, WeldSpec(wf=0.25 * IN, ww=0.1875 * IN), config="2F")
    load = LoadCase("LRFD", Mu=800 * KIPIN, Vu=25.8 * KIP, Nu=3.30 * KIP)
    return sp, load


class TestDG39Example521(unittest.TestCase):
    def setUp(self):
        self.sp, self.load = dg39_example_5_2_1()

    def assertClose(self, got, want, tol=0.01):
        self.assertAlmostEqual(got / want, 1.0, delta=tol, msg=f"{got} vs {want}")

    def test_h1(self):                 # 15.6 in.
        self.assertClose(self.sp.h_inner, 15.6 * IN, 0.005)

    def test_s(self):                  # 2.47 in.
        self.assertClose(self.sp.s, 2.47 * IN, 0.005)

    def test_equivalent_moment(self):  # 829 kip-in.
        self.assertClose(self.sp.Mu_eq(self.load), 829 * KIPIN, 0.002)

    def test_yield_line_parameter(self):   # 93.9 in.
        self.assertClose(self.sp.Yp, 93.9 * IN, 0.005)

    def test_required_bolt_diameter(self):  # 0.708 in.
        self.assertClose(self.sp.db_required(self.load), 0.708 * IN, 0.005)

    def test_required_plate_thickness(self):  # 0.519 in.
        self.assertClose(self.sp.tp_required(self.load), 0.519 * IN, 0.005)

    def test_flange_weld_force(self):  # Tu,min = 0.60 Fy bf tf = 76.5 kips
        self.assertClose(self.sp.flange_force_weld(self.load), 76.5 * KIP, 0.005)

    def test_compression_shear_strength(self):  # phi*Vn = 35.9 kips (Fnv = 54 ksi)
        chk = next(c for c in self.sp.check(self.load).checks if c.name.startswith("Bu lông cắt"))
        self.assertClose(chk.capacity, 35.9 * KIP, 0.01)
        self.assertClose(chk.demand, 25.8 * KIP, 0.001)

    def test_bolts_and_plate_ok(self):
        r = self.sp.check(self.load)
        for c in r.checks:
            if c.name.startswith(("Bu lông kéo", "Bản mã uốn", "Bu lông cắt")):
                self.assertTrue(c.ok, c.name)


class TestGeneral(unittest.TestCase):
    def test_bolt_table_values(self):   # AISC 360-10 Table J3.2
        for grade, vals in {"A325": (90, 54, 68), "A490": (113, 68, 84)}.items():
            b = BoltLayout(db=20, grade=grade)
            self.assertAlmostEqual(b.Fnt, vals[0] * KSI, delta=0.01 * vals[0] * KSI)
            self.assertAlmostEqual(b.Fnv, vals[1] * KSI, delta=0.01 * vals[1] * KSI)
            x = BoltLayout(db=20, grade=grade, threads_in_shear_plane=False)
            self.assertAlmostEqual(x.Fnv, vals[2] * KSI, delta=0.01 * vals[2] * KSI)

    def test_standard_holes(self):      # AISC 360-10 Table J3.3M
        self.assertEqual([hole_diameter(d) for d in (16, 20, 22, 24, 27, 30, 36)],
                         [18, 22, 24, 27, 30, 33, 39])

    def test_extended_4e_yp_matches_formula(self):
        beam = Beam("B", 600, 250, 20, 12)
        sp = Splice(beam, EndPlate(270, 30), BoltLayout(30, g=140, pfo=55, pfi=55, de=45))
        s = 0.5 * math.sqrt(270 * 140)
        want = (270 / 2 * (sp.h_outer / 55 + sp.h_inner * (1 / 55 + 1 / s) - 0.5)
                + 2 / 140 * sp.h_inner * (55 + s))
        self.assertAlmostEqual(sp.Yp, want, places=6)

    def test_axial_tension_increases_demand(self):
        beam = Beam("B", 600, 250, 20, 12)
        sp = Splice(beam, EndPlate(270, 30), BoltLayout(30, g=140))
        a = sp.Mu_eq(LoadCase("a", 500, 100, 0))
        b = sp.Mu_eq(LoadCase("b", 500, 100, 200))
        self.assertGreater(b, a)
        self.assertEqual(sp.Mu_eq(LoadCase("c", 500, 100, -200)), a)   # nén bị bỏ qua

    def test_sign_of_moment_is_irrelevant(self):
        beam = Beam("B", 600, 250, 20, 12)
        sp = Splice(beam, EndPlate(270, 30), BoltLayout(30, g=140))
        self.assertEqual(sp.Mu_eq(LoadCase("a", 500, 100)), sp.Mu_eq(LoadCase("b", -500, 100)))

    def test_demo_auto_design_passes(self):
        sp, loads = splice_from_dict(DEMO)
        for r in sp.check_all(loads):
            self.assertTrue(r.ok, [c.name for c in r.checks if not c.ok])
        self.assertIn("ĐẠT", sp.report(loads))

    def test_auto_design_is_monotonic_in_moment(self):
        beam = Beam("B", 600, 250, 20, 12)
        small = auto_design(beam, [LoadCase("s", 150, 80)])
        large = auto_design(beam, [LoadCase("l", 750, 80)])
        self.assertGreaterEqual((large.bolts.db, large.plate.tp), (small.bolts.db, small.plate.tp))

    def test_underdesigned_splice_fails(self):
        beam = Beam("B", 600, 250, 20, 12)
        sp = Splice(beam, EndPlate(270, 12), BoltLayout(16, g=140, pfo=45, pfi=45, de=30))
        self.assertFalse(sp.check(LoadCase("x", 650, 250)).ok)

    def test_flush_gamma_r(self):
        beam = Beam("B", 400, 200, 14, 8)
        self.assertEqual(Splice(beam, EndPlate(210, 20), BoltLayout(20), config="2F").gamma_r, 0.8)
        self.assertEqual(Splice(beam, EndPlate(210, 20), BoltLayout(20), config="4E").gamma_r, 1.0)

    def test_invalid_config(self):
        with self.assertRaises(ValueError):
            Splice(Beam("B", 400, 200, 14, 8), EndPlate(210, 20), BoltLayout(20), config="8ES")

    def test_invalid_grade(self):
        with self.assertRaises(ValueError):
            BoltLayout(db=20, grade="12.9")


if __name__ == "__main__":
    unittest.main()
