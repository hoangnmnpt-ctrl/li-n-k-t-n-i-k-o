"""
knee_section.py
===============
Đọc tên tiết diện I tổ hợp theo quy cách của mô hình SAP2000 (đơn vị mm, chiều dài đoạn: m).

BUILT-UP I
    250.5-150.5              bụng 250×5, cánh 150×5            → cao tổng = 250 + 5 + 5 = 260
    250.5-150.5.6            cánh TRÊN dày 5, cánh DƯỚI dày 6
    200.5.5-100.8            bụng 200 × 5.5, cánh 100×8
    300.5-250.5-150.10       bụng 300×5, cánh trên 250×5, cánh dưới 150×10
TAPERED I
    (250-500).5-150.5        bụng cao 250 → 500, dày 5, cánh 150×5
    (250-500).5-150.5.6      như trên, cánh dưới dày 6
    (250-500-500-250).5.5.5-150.10.10.10/2-bal-2
                             3 đoạn: 250→500, 500→500, 500→250; tw & tf theo từng đoạn;
                             chiều dài 2 m – phần còn lại – 2 m
LEGACY (tool cũ, h = chiều cao TỔNG)
    I (850-662)-5/150-8,  I 500-6/200-10

"Cánh trên" = mặt +2 của trục địa phương SAP (t2, tf), "cánh dưới" = mặt −2 (t2b, tfb).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field


class SectionError(ValueError):
    pass


@dataclass
class Segment:
    hw0: float          # chiều cao bụng đầu đoạn (mm)
    hw1: float          # chiều cao bụng cuối đoạn (mm)
    tw: float
    bf_top: float
    tf_top: float
    bf_bot: float
    tf_bot: float
    length: float = 0.0  # m (đã xử lý 'bal')


@dataclass
class ISection:
    name: str
    segments: list[Segment] = field(default_factory=list)
    legacy_total_height: bool = False
    len_spec: list = field(default_factory=list)   # chiều dài khai báo (m / 'bal'), rỗng = chia đều

    @property
    def tapered(self) -> bool:
        return any(abs(s.hw0 - s.hw1) > 1e-9 for s in self.segments) or len(self.segments) > 1

    def resolve_lengths(self, L: float) -> list[float]:
        """Chiều dài từng đoạn (m) cho thanh dài L (m)."""
        n = len(self.segments)
        if n == 1:
            return [L]
        spec = list(self.len_spec)
        if not spec:
            return [L / n] * n
        if len(spec) != n:
            raise SectionError(f"{self.name}: số chiều dài đoạn ({len(spec)}) khác số đoạn ({n})")
        known = sum(x for x in spec if x != "bal")
        nbal = sum(1 for x in spec if x == "bal")
        rest = max(L - known, 0.0)
        return [(rest / nbal if x == "bal" else float(x)) for x in spec]

    def at(self, x: float, L: float) -> "SectionAt":
        """Tiết diện tại vị trí x (m) trên thanh dài L (m)."""
        lens = self.resolve_lengths(L)
        x = min(max(x, 0.0), L)
        acc = 0.0
        for i, (seg, ls) in enumerate(zip(self.segments, lens)):
            last = i == len(self.segments) - 1
            if x <= acc + ls + 1e-9 or last:
                t = 0.0 if ls <= 0 else min(max((x - acc) / ls, 0.0), 1.0)
                hw = seg.hw0 + (seg.hw1 - seg.hw0) * t
                beta = math.degrees(math.atan(abs(seg.hw1 - seg.hw0) / (ls * 1000.0))) if ls > 0 else 0.0
                if self.legacy_total_height:
                    d = hw
                    hw = d - seg.tf_top - seg.tf_bot
                else:
                    d = hw + seg.tf_top + seg.tf_bot
                return SectionAt(self.name, d, hw, seg.tw, seg.bf_top, seg.tf_top, seg.bf_bot, seg.tf_bot, beta)
            acc += ls
        raise SectionError("Không xác định được đoạn tiết diện")


@dataclass
class SectionAt:
    name: str
    d: float
    hw: float
    tw: float
    bf_top: float
    tf_top: float
    bf_bot: float
    tf_bot: float
    beta: float          # góc vát bụng của đoạn chứa vị trí xét (độ)

    @property
    def area(self) -> float:
        return self.bf_top * self.tf_top + self.bf_bot * self.tf_bot + self.hw * self.tw

    def text(self) -> str:
        fl = (f"{self.bf_top:g}×{self.tf_top:g}" if (self.bf_top, self.tf_top) == (self.bf_bot, self.tf_bot)
              else f"trên {self.bf_top:g}×{self.tf_top:g} / dưới {self.bf_bot:g}×{self.tf_bot:g}")
        return f"d = {self.d:.1f} (bụng {self.hw:.1f}×{self.tw:g}), cánh {fl}"


_NUM = re.compile(r"^\d+(\.\d+)?$")


def _nums(tokens: list[str], name: str) -> list[float]:
    out = []
    for t in tokens:
        t = t.strip()
        if not t:
            continue
        try:
            out.append(float(t))
        except ValueError:
            raise SectionError(f"{name}: '{t}' không phải số")
    return out


def _web_tw(tokens: list[float], n: int, name: str) -> list[float]:
    if len(tokens) == n:
        return tokens
    if len(tokens) == 1:
        return tokens * n
    if n == 1 and len(tokens) == 2:          # "200.5.5" → 5.5
        return [float(f"{tokens[0]:g}.{tokens[1]:g}")]
    raise SectionError(f"{name}: số giá trị bề dày bụng ({len(tokens)}) không khớp số đoạn ({n})")


def _flange(tokens: list[float], n: int, name: str) -> tuple[float, list[float], list[float]]:
    """Một cụm cánh 'bf.t…' → (bf, tf_top theo đoạn, tf_bot theo đoạn)."""
    if len(tokens) < 2:
        raise SectionError(f"{name}: thiếu bề dày cánh")
    bf, ts = tokens[0], tokens[1:]
    m = len(ts)
    if m == 1:
        return bf, ts * n, ts * n
    if n == 1 and m == 2:
        return bf, [ts[0]], [ts[1]]
    if m == n:
        return bf, ts, ts
    if m == 2 * n:
        return bf, ts[0::2], ts[1::2]
    raise SectionError(f"{name}: số bề dày cánh ({m}) không khớp số đoạn ({n})")


def parse_section(name: str) -> ISection:
    raw = (name or "").strip()
    if not raw:
        raise SectionError("Tên tiết diện rỗng")
    s = raw.replace(" ", "")
    up = s.upper()

    # ---- legacy: I (h1-h2)-tw/bf-tf | I h-tw/bf-tf (chiều cao tổng)
    if up[0] in "IH":
        body = up[1:]
        m = re.match(r"^\(([\d.]+)-([\d.]+)\)-([\d.]+)/([\d.]+)-([\d.]+)$", body)
        if m:
            h1, h2, tw, bf, tf = map(float, m.groups())
            return ISection(raw, [Segment(h1, h2, tw, bf, tf, bf, tf)], legacy_total_height=True)
        m = re.match(r"^([\d.]+)-([\d.]+)/([\d.]+)-([\d.]+)$", body)
        if m:
            h, tw, bf, tf = map(float, m.groups())
            return ISection(raw, [Segment(h, h, tw, bf, tf, bf, tf)], legacy_total_height=True)
        raise SectionError(f"{raw}: sai quy cách I…")

    if re.match(r"^(D|\[\]|2?V|2?U|T|B|CT)", up):
        raise SectionError(f"{raw}: không phải tiết diện I — chưa hỗ trợ cho knee")

    len_spec: list = []
    if s.startswith("("):
        close = s.find(")")
        if close < 0:
            raise SectionError(f"{raw}: thiếu ')'")
        hs = _nums(s[1:close].split("-"), raw)
        if len(hs) < 2:
            raise SectionError(f"{raw}: cần ít nhất 2 chiều cao bụng")
        rest = s[close + 1:]
        if "/" in rest:
            rest, lens = rest.split("/", 1)
            for t in lens.split("-"):
                t = t.strip().lower()
                if t == "bal":
                    len_spec.append("bal")
                elif t:
                    len_spec.append(float(t))
        rest = rest.lstrip(".")
        parts = rest.split("-")
        n = len(hs) - 1
        tws = _web_tw(_nums(parts[0].split("."), raw), n, raw)
        heights = [(hs[i], hs[i + 1]) for i in range(n)]
    else:
        parts = s.split("-")
        web = _nums(parts[0].split("."), raw)
        if len(web) < 2:
            raise SectionError(f"{raw}: phần bụng cần 'hw.tw'")
        n = 1
        tws = _web_tw(web[1:], 1, raw)
        heights = [(web[0], web[0])]

    fparts = parts[1:]
    if len(fparts) == 1:
        bf, tt, tb = _flange(_nums(fparts[0].split("."), raw), n, raw)
        bft = bfb = bf
    elif len(fparts) == 2:
        bft, tt, _ = _flange(_nums(fparts[0].split("."), raw), n, raw)
        bfb, tb, _ = _flange(_nums(fparts[1].split("."), raw), n, raw)
    else:
        raise SectionError(f"{raw}: sai số cụm cánh (cần 1 hoặc 2)")

    segs = [Segment(heights[i][0], heights[i][1], tws[i], bft, tt[i], bfb, tb[i]) for i in range(n)]
    sec = ISection(raw, segs, len_spec=len_spec)
    if len_spec and len(len_spec) != n:
        raise SectionError(f"{raw}: số chiều dài đoạn ({len(len_spec)}) khác số đoạn ({n})")
    return sec


def section_at_end(name: str, L: float, end: str) -> SectionAt:
    """end = 'I' (x = 0) hoặc 'J' (x = L)."""
    sec = parse_section(name)
    return sec.at(0.0 if end == "I" else L, L)
