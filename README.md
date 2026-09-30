# Liên kết nối dầm (Beam Splice - BS)

`beam_splice.py` – kiểm tra liên kết nối dầm bằng mặt bích bu lông theo **AISC 360-10 (LRFD)** + AISC Design Guide 16 (thick-plate, không prying), cùng cách tính với liên kết knee.

- Kiểu bích: `4E` (mở rộng 1 phía), `4ES` (mở rộng 2 phía, mô men đổi dấu), `2F` (bích bằng).
- Kiểm tra: bu lông kéo, bản mã uốn (Yp), điều kiện bản dày, cắt phần bích mở rộng, bu lông cắt, ép mặt/xé lỗ, hàn cánh, hàn bụng, cấu tạo.
- Đơn vị: mm, kN, MPa, kN.m.

```bash
python beam_splice.py
```
