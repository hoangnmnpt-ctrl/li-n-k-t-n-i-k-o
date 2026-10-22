# Liên kết thép — AISC 360-10 (LRFD)

**Chạy:** nhấp đúp `Chay_LienKet.bat` (hoặc `python run.py`). Một tool duy nhất, giao diện theo RAM Connection:
Knee (BCF), Beam splice và Apex (BS) — xem `lienket\README.md`.

| Thư mục | Nội dung |
|---|---|
| `lienket\` | Tool liên kết (mã nguồn, dự án `du_an.lkt`, kiểm thử) |
| `Lấy nội lực\` | Lấy nội lực thiết kế từ SAP2000 (tool dùng chung kết nối SAP) |
| `MD, skill\steelconn_spec\` | Bộ đặc tả phạm vi RAM Connection |
| `fORMULAS\` | Tài liệu công thức |

Kiểm thử: `python lienket\tests\test_engine.py` · `python lienket\tests\test_splice_engine.py` · `python lienket\tests\test_gui_smoke.py`.
