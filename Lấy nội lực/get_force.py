"""
LẤY NỘI LỰC THIẾT KẾ – SAP2000
=================================
Ứng dụng Python thay thế file Excel VBA.
Chạy file này để khởi động giao diện.

Yêu cầu:
  - Python 3.10+
  - SAP2000 đang chạy trên máy
  - pip install customtkinter openpyxl comtypes
"""

import sys
import os

# Đảm bảo import đúng thư mục
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui_main import App


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
