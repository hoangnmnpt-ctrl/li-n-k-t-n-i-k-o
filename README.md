# Liên kết nối dầm (Beam Splice - BS)

Kiểm tra / tự thiết kế liên kết nối dầm bằng **mặt bích bu lông** theo **AISC 360-10 (LRFD)**
và **AISC Design Guide 39** (quy trình bản mã dày, không kể prying). Chỉ dùng thư viện chuẩn của Python (≥ 3.9).

Hai bản mã giống nhau áp vào nhau nên chỉ kiểm tra 1 phía, không có kiểm tra phía cột như liên kết knee.

## Kiểu mặt bích
| `config` | Mô tả | Cơ sở |
|---|---|---|
| `2F` | Bích bằng 2 bu lông, 4 bu lông tổng | DG39 Table 5-2 (đã đối chiếu số Ví dụ 5.2-1) |
| `4E` | Bích mở rộng 4 bu lông. `extended_both=true`: 8 bu lông, mô men đổi dấu; `false`: 6 bu lông, mô men 1 chiều | DG39 Eq. 3-14 |

Chưa có: bích có sườn (4ES), 8ES, bích bằng 4/6 bu lông, kiểm tra có prying (bản mã mỏng).

## Cách dùng
```bash
python beam_splice.py                      # chạy ví dụ
python beam_splice.py example_input.json   # chạy theo file JSON
python beam_splice.py input.json --json    # xuất kết quả dạng JSON
python -m unittest -v                      # chạy test
```
Đơn vị: mm, MPa, kN, kN.m. `Nu` dương là kéo (nén bị bỏ qua, thiên về an toàn). Dấu của `Mu` không ảnh hưởng.

JSON có `plate` + `bolts` (+ `weld`) thì chương trình **kiểm tra** đúng kích thước đó; thiếu thì **tự chọn**
bu lông, bản mã và chân hàn nhỏ nhất đạt mọi tổ hợp trong `loads`. Dùng trong Python:
```python
from beam_splice import Beam, LoadCase, auto_design
beam = Beam("I600x250x12x20", d=600, bf=250, tf=20, tw=12)
sp = auto_design(beam, [LoadCase("LC1", Mu=650, Vu=250)], config="4E")
print(sp.report([LoadCase("LC1", Mu=650, Vu=250)]))
```

## Độ tin cậy
- Test trong `test_beam_splice.py` khớp **DG39 Example 5.2-1** (Yp, db,req, tp,req, Mu,eq, lực hàn cánh, khả năng cắt bu lông).
- Công thức Yp của `4E` lấy từ lời giải đường chảy ở DG39 Chương 3 (Eq. 3-14), **chưa đối chiếu với ví dụ 4E có số** (Example 5.3-1).
- Các mục sau là quy ước kỹ sư, cần soát lại: hàn bụng (vùng kéo và cắt), xé lỗ/ép mặt bản mã, khoảng cách pfi/pfo tối thiểu,
  bu lông 8.8/10.9 (quy đổi theo Fu, không có trong AISC).
- Chưa kiểm tra phạm vi tham số đã thí nghiệm (DG39 Table 5-1, 5-10...).
- Công cụ hỗ trợ tính toán, kết quả phải được kỹ sư có chuyên môn soát lại trước khi dùng thiết kế.
