# Liên kết thép — công cụ tính theo AISC 360-10 (LRFD)

| Tool | Chạy | Nội dung |
|---|---|---|
| **KNEE KÈO** | `Chay_Knee.bat` / `python run_knee.py` | Knee đứng / ngang / xiên, bản đầu bu lông, quét nội lực SAP2000, xuất RAM `.rcnx` — xem `knee_app\README.md` |
| **NỐI DẦM** | `Chay_Splice.bat` / `python run_splice.py` | Beam splice / Apex bằng bản đầu bu lông, cùng khuôn với Knee — xem `splice_app\README.md` |
| Lấy nội lực | `Lấy nội lực\` | Lấy nội lực thiết kế từ SAP2000 |

`MD, skill\steelconn_spec` là bộ đặc tả cho thư viện `steelconn` (phạm vi RAM Connection).

Kiểm thử: `python knee_app\tests\test_engine.py` · `python splice_app\tests\test_splice_engine.py`.
