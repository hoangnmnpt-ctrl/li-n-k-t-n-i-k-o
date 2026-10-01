"""Chạy tool KNEE KÈO (AISC 360-10 LRFD). Cần: customtkinter, comtypes (dùng .venv của 'Lấy nội lực')."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "knee_app"))

from gui import main  # noqa: E402

if __name__ == "__main__":
    main()
