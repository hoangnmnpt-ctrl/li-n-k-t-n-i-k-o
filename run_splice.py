"""Chạy tool NỐI DẦM (AISC 360-10 LRFD). Cần: customtkinter (dùng .venv của 'Lấy nội lực'); Python ≥ 3.12 như tool Knee."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "splice_app"))

from splice_gui import main  # noqa: E402

if __name__ == "__main__":
    main()
