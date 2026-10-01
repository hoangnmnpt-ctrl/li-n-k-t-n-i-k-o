# KNEE TOOL — Liên kết knee kèo bản đầu bu lông (AISC 360-10 LRFD)

Mở file **`Knee_AISC360-10.html`** bằng trình duyệt (Chrome/Edge). Công cụ chạy offline trong 1 file, không cần cài đặt.

## Phạm vi
| Kiểu | Cấu kiện có bản đầu | Phía gối |
|---|---|---|
| Knee đứng | Kèo → áp vào cánh trong cột | Cánh cột (Yc DG4/DG39), J10 bụng cột, panel, sườn |
| Knee ngang | Cột → bản nằm ngang trên đỉnh cột | Bản/ cánh dưới kèo (Yc), J10 bụng kèo, panel, sườn |
| Knee xiên | Kèo + cột, 2 bản trên mặt nghiêng (phân giác / vuông góc kèo / góc tùy chọn) | Bản đầu cột (Y DG16) + hàn cột |

Cấu hình bu lông (như RAM Connection): mỗi nhóm cánh ngoài/trong khai báo extended hoặc flush, số hàng trong cánh 1–3 và pb → tự nhận dạng 2FU, 4FU, 4E, 4ES, MRE 1/2, MRE 1/3.

## Phương pháp
- Bản đầu: DG16 §2.5 — yield-line Y (Tables 3-2…4-5), φbMpl/γr; φMnp = 0.75·2Pt·Σd; φMq theo Kennedy hiệu chỉnh (Qmax,i, Qmax,o). h đo từ mặt ngoài cánh nén, d đo từ tâm cánh nén.
- Hình học knee: tiết diện cắt theo mặt bản → d/cosφ, tf/cosφ; nội lực chiếu lên hệ trục bản (lấy dấu bất lợi); Mu,eq = |M| + Nn·dm/2.
- Phía gối: Yc theo DG4 Table 3.4 và DG39 Phụ lục A (cánh liên tục có/không sườn, đỉnh cột có bản nắp / không sườn).
- Cắt bản DG4 Eq. 3.12, 3.13; cắt & ép mặt bu lông J3.6, J3.10; hàn J2.4; J10.2, J10.3, J10.5, J10.6, J10.8.
- Quy ước tiết diện: `I (h1-h2)-tw/bf-tf` (vát) hoặc `I h-tw/bf-tf`.
- Quy ước dấu: N > 0 kéo; M < 0 → cánh ngoài chịu kéo.

## Kiểm chứng
| Hạng mục | Tham chiếu | Tool | Sai số |
|---|---|---|---|
| Y (4E), DG16 Ex. 4.2.1 | 187.4 in | 187.4 | 0 |
| Qmax,i / Qmax,o | 9.48 / 9.69 k | 9.51 / 9.71 | +0.3% (sách làm tròn a) |
| φMq | 2175 k-in | 2170 | −0.2% |
| Yc không sườn / có sườn, DG4 Ex. | 170.1 / 309.1 in | 170.1 / 309.1 | 0 |
| Yc đỉnh cột có bản nắp, DG39 | 91.2 in | 91.2 | 0 |
| RAM #11 cánh ngoài: φMpl, φMnp, φMq | 307.72 / 512.00 / 420.75 | 307.74 / 512.02 / 420.76 | ≤0.01% |
| RAM #11 cánh trong: φMnp, φMq | 233.25 / 191.68 | 233.26 / 191.69 | ≤0.01% |
| RAM #11 cắt chảy / cắt đứt bản | 670.68 / 566.74 | 670.68 / 565.13 | 0 / −0.3% |
| RAM #11 bu lông cắt, hàn cánh, hàn bụng, cắt bụng | 505.30 / 863.04 / 5836.6 / 637.56 | 505.27 / 862.85 / 5849.8 / 637.61 | ≤0.3% |
| RAM #11 uốn bản cánh trong (flush) | 174.68 | 171.90 | −1.6% (tool áp γr = 1.25 theo DG16, an toàn hơn) |
| RAM #11 phía gối uốn / nhổ | 353.83 / 403.29 | 351.58 / 382.42 | −0.6% / −5.2% (an toàn hơn) |

Mẫu "Đối chứng RAM #11" có sẵn trong menu Nạp mẫu. Thông số cột của RAM #11 không có trong báo cáo nên tool phải giả định; vì vậy các kiểm tra J10 và panel của mẫu này chưa đối chiếu được.

## Cấu trúc
- `src/knee_engine.js` — lõi tính toán (không phụ thuộc giao diện)
- `src/knee_ui.html` — giao diện
- `build.py` — gộp thành `Knee_AISC360-10.html`
