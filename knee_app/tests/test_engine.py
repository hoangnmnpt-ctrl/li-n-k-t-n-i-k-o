"""Kiểm chứng engine: chạy `python tests/test_engine.py` (hoặc pytest)."""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engine as K  # noqa: E402
from defaults import PRESETS, merge, BASE  # noqa: E402
from knee_section import parse_section  # noqa: E402

IN = 25.4
KSI = 6.894757
KIP = 4448.22


def close(a, b, tol):
    return abs(a / b - 1) <= tol


def test_dg16_ex421_Y():
    y = K.end_plate_Y("4E", 8 * IN, 3 * IN, 1.75 * IN, 2.5 * IN, 0, 26.5 * IN, [21.875 * IN], 2.5 * IN)
    assert close(y["Y"] / IN, 187.4, 0.001)


def test_dg16_ex421_kennedy_Mq():
    kn = K.kennedy(0.5 * IN, 50 * KSI, 8 * IN, 0.75 * IN, 90 * KSI, 1.75 * IN, 2.5 * IN, 2.5 * IN)
    assert close(kn["Qi"] / KIP, 9.48, 0.005) and close(kn["Qo"] / KIP, 9.69, 0.005)
    Pt = math.pi * 0.75 ** 2 / 4 * 90 * KIP
    bm = K.bolt_moments(True, 26.3125 * IN, [21.6875 * IN], Pt, 14 * KIP, kn["Qi"], kn["Qo"])
    assert close(0.75 * bm["Mq"] / KIP / IN, 2175, 0.005)


def test_dg4_Yc():
    rows = [dict(d=22.54 * IN, s=0), dict(d=18.02 * IN, s=4.52 * IN)]
    assert close(K.support_Yc("cont_unstiff", 14.6 * IN, 5.5 * IN, rows)["Y"] / IN, 170.1, 0.001)
    assert close(K.support_Yc("cont_stiff", 14.6 * IN, 5.5 * IN, rows, 2.01 * IN, 2.01 * IN, stiff_between=True)["Y"] / IN, 309.1, 0.001)


def test_dg39_Yc_cap():
    y = K.support_Yc("top_cap", 6.56 * IN, 3.5 * IN, [dict(d=15.6 * IN, s=0)], pcpRaw=1.43 * IN)
    assert close(y["Y"] / IN, 91.2, 0.002)


RAM = {"pl_flex_E": 307.72, "bolt_np_E": 512.00, "bolt_q_E": 420.75, "pl_vy_E": 670.68, "pl_vr_E": 566.74,
       "bolt_v_E": 505.30, "bolt_np_I": 233.25, "bolt_q_I": 191.68, "bolt_v_I": 252.65, "m1_wf_I": 863.04,
       "m1_wv": 637.56, "sup_q_I": 174.22, "bear_s_I": 649.73}
# bear_s_E: RAM không xét xé mép trên bản gối (1299.46) — tool xét theo mép thật (1143.8), an toàn hơn


def test_ram11():
    r = K.compute(merge(BASE, PRESETS["Đối chứng RAM #11"]))
    caps = {c["id"]: c["cap"] for c in r["checks"]}
    for k, v in RAM.items():
        assert close(caps[k], v, 0.004), (k, caps[k], v)


def test_presets_run():
    for name, p in PRESETS.items():
        r = K.compute(merge(BASE, p))
        assert r["checks"] and r["gov"] is not None, name


def test_sections():
    s = parse_section("(250-500-500-250).5.5.5-150.10.10.10/2-bal-2")
    assert len(s.segments) == 3 and s.resolve_lengths(10) == [2, 6, 2]
    assert parse_section("250.5-150.5").at(0, 5).d == 260
    at = parse_section("300.5-250.5-150.10").at(0, 5)
    assert (at.bf_top, at.tf_top, at.bf_bot, at.tf_bot) == (250, 5, 150, 10)
    assert parse_section("200.5.5-100.8").at(0, 5).tw == 5.5


if __name__ == "__main__":
    fails = 0
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f(); print("PASS", n)
            except AssertionError as e:
                fails += 1; print("FAIL", n, e)
    sys.exit(1 if fails else 0)
