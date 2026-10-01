"""Nối sang knee_app: dùng lại engine (yield-line, Kennedy, bảng bu lông/vật liệu), tiết diện, hình vẽ, báo cáo.

splice_app dùng tên module có tiền tố `splice_` nên không trùng với module của knee_app.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KNEE = os.path.join(os.path.dirname(HERE), "knee_app")
if KNEE not in sys.path:
    sys.path.insert(0, KNEE)      # ưu tiên knee_app để không bị thư viện cùng tên (report, drawing, engine…) che mất

import engine as K  # noqa: E402,F401  (knee_app/engine.py)
import knee_section  # noqa: E402,F401
