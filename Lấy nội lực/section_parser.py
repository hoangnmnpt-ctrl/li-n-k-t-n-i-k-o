"""
section_parser.py
=================
Parse thông số tiết diện thép hình I/H từ tên tiết diện.

Tương đương VBA: GetSectionPropsAtStation (Module4) — nhánh ParseStringFallback.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SectionProps:
    """Thông số tiết diện I-Section (đơn vị mm)."""
    htb: float = 0.0   # Chiều cao tiết diện (mm)
    tw: float = 0.0     # Bề dày bản bụng (mm)
    bf: float = 0.0     # Bề rộng cánh (mm)
    tf: float = 0.0     # Bề dày cánh (mm)


def parse_section_name(
    prop_name: str,
    l_total: float = 0.0,
    station: float = 0.0,
) -> SectionProps:
    """
    Parse tên tiết diện → SectionProps.

    Giống VBA GetSectionPropsAtStation:
      1. Có ngoặc: (hStart-hEnd)...  → nội suy htb theo station/L
         ví dụ "(300-650)-5/150-8" hoặc "I (850-662)-5/150-8"
      2. I/H: "I300-5/150-8" → htb, tw, bf, tf
    """
    clean = (prop_name or "").strip().upper()
    if not clean:
        return SectionProps()

    # VBA: If InStr(cleanName, "(") > 0 And InStr(cleanName, "-") > 0
    p_open = clean.find("(")
    p_close = clean.find(")")
    if p_open >= 0 and "-" in clean and p_close > p_open:
        h_part = clean[p_open + 1:p_close]
        sub_part = clean[p_close + 1:]
        h_arr = [p.strip() for p in h_part.split("-")]
        if len(h_arr) >= 2 and _is_number(h_arr[0]) and _is_number(h_arr[1]):
            h_start = float(h_arr[0])
            h_end = float(h_arr[1])
            if l_total > 0:
                htb = h_start + (h_end - h_start) * (station / l_total)
            else:
                htb = h_start

            nums = _extract_numbers(sub_part)
            if len(nums) >= 3:
                return SectionProps(htb=htb, tw=nums[0], bf=nums[1], tf=nums[2])
            return SectionProps(htb=htb)

    # VBA: If InStr I or H → bỏ chữ I/H, đổi / thành -, lấy 4 số
    if "I" in clean or "H" in clean:
        stripped = clean.replace("I", "").replace("H", "")
        stripped = stripped.replace("/", "-")
        parts = stripped.split("-")
        nums = [float(p.strip()) for p in parts if _is_number(p.strip())]
        if len(nums) >= 4:
            return SectionProps(htb=nums[0], tw=nums[1], bf=nums[2], tf=nums[3])

    return SectionProps()


def _extract_numbers(text: str) -> list[float]:
    """VBA: Replace / bằng - rồi Split, lấy các phần IsNumeric."""
    text = text.replace("/", "-")
    result = []
    for p in text.split("-"):
        p = p.strip()
        if _is_number(p):
            result.append(float(p))
    return result


def _is_number(s: str) -> bool:
    if not s:
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False
