"""Chạy tool LIÊN KẾT THÉP (AISC 360-10 LRFD): Knee, Beam splice, Apex — giao diện theo RAM Connection.
Cần Python ≥ 3.12 và customtkinter (dùng .venv của 'Lấy nội lực'). Mở một dự án cụ thể: python run.py duong_dan.lkt"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lienket"))

from app import main  # noqa: E402

if __name__ == "__main__":
    main()
