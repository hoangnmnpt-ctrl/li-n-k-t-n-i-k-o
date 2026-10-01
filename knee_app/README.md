# KNEE KÈO — AISC 360-10 LRFD (Python)

Chạy: nhấp đúp `Liên kết\Chay_Knee.bat` (dùng `.venv` của *Lấy nội lực*) hoặc `python run_knee.py`.

## Quy trình
1. **Kết nối SAP** → chọn nguồn tải (Design Combos mặc định, nút *Nguồn tải ▾* để tick) → chọn cột + kèo trong SAP (hoặc tick *Toàn mô hình*) → **Quét knee từ SAP**.
2. Tab *Knee quét từ SAP*: knee gom nhóm theo kích thước tiết diện tại nút + góc dốc (knee đối xứng hai đầu khung vào chung nhóm). Nhấp đúp nhóm → nạp vào thiết kế (bao nội lực mọi knee trong nhóm).
3. Chọn kiểu **Knee đứng** (bản 90°) / **Knee ngang** / **Knee xiên** (bản ⟂ kèo, hàn vào panel cột), sửa thông số bản, bu lông, sườn, hoặc bấm **Tự chọn tp / bu lông**.
4. Bấm một dòng kiểm tra → xem diễn giải công thức, bộ phận liên quan nhấp nháy trên hình.
5. **Lưu vào danh sách** (tab *Danh sách đã lưu*): mở lại, ghi đè, đổi tên, xoá, dời ▲▼. Lưu tại `knee_app\knee_saved.json`.

## Tương đương RAM Connection (Knee moment end plate — BCF)
- **Form nhập** theo đúng thứ tự và nhãn tiếng Anh của RAM: General information → Members (Beam, Support) → Moment end plate
  (Connector, Weld, Bolts, Bolt group external extension / external flange / internal flange / internal extension) → Stiffeners.
  Rê chuột lên nhãn để xem chú thích tiếng Việt. *Plate alignment* = kiểu knee (Vertical = đứng, Perpendicular = xiên, Horizontal = ngang).
  Cỡ hàn nhập theo D (1/16 in) như RAM.
- **Tab Loads**: bảng như hộp thoại Loads của RAM (ID, Description, Right beam Axial/V2/M3, Left beam, Column Axial/V2/M3). Dấu giống RAM.
- **Tab Report (RAM)**: báo cáo tiếng Anh đúng form RAM (Demands, Geometric Considerations, Plate / Column Behavior, Design Check,
  Global critical strength ratio); nút *Export report (.docx)*.
- **Export RAM Connection (.rcnx)**: knee hiện tại hoặc toàn bộ *Danh sách đã lưu* → 1 file, mỗi knee = 1 connection `Bentley.AISC.MEPlateKneeBCF`
  kèm bảng tải. Dựng từ khuôn `ram_proto.rcnx` (lấy từ file RAM 23 thật; tạo lại bằng `tools/make_ram_proto.py`).
- **Database tiết diện**: khi xuất (tick "Tạo tiết diện…"), tiết diện `I {hw}x{bf}x{tw}x{tf}` còn thiếu được thêm vào
  `…\Sections\WS Section-Hoang\Built up.sec` (sao lưu bản cũ trong `_backup`, không thêm trùng). Đóng/mở lại RAM để nạp.
- Đối chứng knee #11 của RAM (dữ liệu gốc từ .rcnx): nội lực quy đổi trùng 100%; bản đầu, bu lông, hàn, panel, sườn lệch ≤ 0.7%;
  riêng uốn bản cánh trong −1.6% (tool áp γr = 1.25), phía gối −0.7…−5% và ép mặt bản gối −12% (tool xét xé mép) — đều thiên về an toàn.

## Lấy thẳng từ SAP2000
- **🎯 Chọn knee trong SAP**: chọn nút knee (hoặc cột + kèo) trong SAP → nạp ngay tiết diện, L, đầu nút, góc dốc α, hướng cánh và nội lực.
  Các ô này bị **khoá 🔒** (banner đầu form); bấm *Mở khoá* để sửa tay.
- Tên tiết diện không theo quy cách → kích thước I tại mặt gối đọc qua API SAP (I-Section / Nonprismatic), ghi chú "(kích thước qua API SAP)".

## Panel zone
Mục *Panel zone (bề dày riêng)*: kích thước theo tiết diện gối tại nút, nhập riêng bề dày bụng, cánh ngoài, bản gối và vật liệu.
Mọi kiểm tra phía gối (Yc, J10.2/10.3/10.5, J10.6, sườn) dùng tiết diện panel. Trên hình, panel tách riêng khỏi cột.

## Trực quan
- **Tô màu theo D/C** (xanh ≤ 0.6 → vàng 0.9 → cam 1.0 → đỏ > 1) + nhãn D/C nổi trên từng bộ phận, tính theo tổ hợp đang xem.
- **Dòng lực**: kéo (đỏ) / nén (xanh) chạy từ cánh kèo qua bản, sườn, thanh chống chéo trong panel xuống cột.
- **Thanh trượt tổ hợp + ▶ phát tự động**: màu, lực, nhãn đổi theo từng tổ hợp.
- **3D**: kéo trái xoay, kéo phải di chuyển, lăn zoom, nhấp đúp về góc mặc định. Tô bóng, tô màu D/C, tô sáng kiểm tra đang chọn.
- **Thẻ đồng hồ** theo nhóm (Bản đầu, Bu lông, Phía gối, Panel·J10, Sườn, Hàn, Cấu kiện) — bấm để nhảy tới kiểm tra khống chế.
- **Rê chuột** lên bộ phận → tooltip các kiểm tra liên quan. 2D: lăn zoom, kéo di chuyển.

## Nội lực từ SAP (như tool Lấy nội lực)
- Vị trí: mặt gối đầu nút (trừ end offset), 9 cực trị tại đầu nút của **cả kèo và cột**; mỗi tổ hợp lấy đồng thời nội lực hai thanh.
- Đổi dấu: SAP M3 > 0 kéo mặt −2. Tool: M < 0 → cánh NGOÀI (kèo: cánh trên; cột: phía xa nhịp) chịu kéo. Hướng mặt ngoài xác định bằng trục local 2 (GetTransformationMatrix).

## Tiết diện
`250.5-150.5` (bụng 250×5, cánh 150×5, cao tổng 260) · `250.5-150.5.6` · `200.5.5-100.8` · `300.5-250.5-150.10` ·
`(250-500).5-150.5` · `(250-500-500-250).5.5.5-150.10.10.10/2-bal-2` · legacy `I (850-662)-5/150-8`.
"Cánh trên" = mặt +2 SAP.

## Kiểm chứng
`python tests\test_engine.py` (DG16 Ex 4.2.1, DG4 Yc, DG39 Yc bản nắp, RAM Connection #11, quy cách tiết diện) và `python tests\test_scanner.py` (khung cổng giả lập, đổi dấu, gom nhóm).

## Tệp
`engine.py` lõi tính (port từ bản HTML) · `knee_section.py` đọc tiết diện · `scanner.py` quét SAP · `drawing.py` hình knee · `gui.py` giao diện · `store.py` danh sách lưu · `defaults.py` mẫu.
