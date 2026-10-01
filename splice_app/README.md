# NỐI DẦM — Beam splice / Apex bằng bản đầu bu lông (AISC 360-10 LRFD)

Cùng khuôn với tool **KNEE KÈO** (`knee_app`): form nhập theo RAM Connection, hình 2D tô màu D/C, báo cáo form RAM, danh sách đã lưu.
Dùng lại lõi đã kiểm chứng của knee (yield-line bản đầu DG16, lực nhổ Kennedy hiệu chỉnh, bảng bu lông / vật liệu, đọc tiết diện I tổ hợp).

Chạy: nhấp đúp `Chay_Splice.bat` (dùng `.venv` của *Lấy nội lực*) hoặc `python run_splice.py`.
Cần Python ≥ 3.12 (như tool Knee) và `customtkinter`.

## Quy trình
1. Chọn kiểu **Beam splice** (thẳng) hoặc **Apex** (đỉnh mái, hai dầm nghiêng ±α, bản đầu đặt đứng) ở thanh trên hình.
2. Nhập tiết diện dầm 1 / dầm 2 (quy cách như SAP: `500.8-200.12` = bụng 500×8, cánh 200×12; hỗ trợ tiết diện vát `(580-380).6-200.10`).
   Tick *Same as beam 1* nếu hai dầm giống nhau. Hai dầm phải **cùng chiều cao** tại mặt nối.
3. Chọn kiểu bản đầu: **Flush** (bích bằng, 2FU / 4FU) · **Extended top / bottom / both** (4E, 4ES có sườn, MRE 1/2, 1/3), bề dày và vật liệu **từng bản** (tp1/tp2),
   bu lông, hàn (nhập cỡ theo D = 1/16 in như RAM), hình học hàng bu lông.
4. Tab **Loads**: nhập hoặc dán từ Excel (Description, Axial, V2, M3). Nội lực tại mặt nối.
5. Bấm một dòng kiểm tra → xem diễn giải công thức từng bước, bộ phận liên quan sáng lên trên hình. **⚙ Tự chọn tp / bu lông** tìm phương án nhẹ nhất đạt.
6. **Report (RAM)**: báo cáo tiếng Anh theo form RAM, nút *Export report (.docx)*. **Lưu vào danh sách** → `splice_app\splice_saved.json`.

## Quy ước dấu
N > 0 kéo · **M > 0 → cánh DƯỚI chịu kéo** (mô men dương), **M < 0 → cánh TRÊN chịu kéo** · V lấy giá trị tuyệt đối. Nhập kN, kN·m, mm.
Apex: nội lực của một dầm tại mặt nối (hệ trục dầm), tool tự quy đổi về hệ trục bản (Nn = N·cosα + |V|·sinα, Vt = |N|·sinα + |V|·cosα).

## Các kiểm tra (theo từng tổ hợp, lấy giá trị bất lợi nhất)
Mỗi **bản đầu 1 / 2**: chảy dẻo uốn (DG16 §2.5), cắt chảy / cắt đứt phần nhô (DG4 3.12, 3.13), ép mặt / xé lỗ (J3-6).
**Bu lông**: đứt không nhổ φMnp, đứt có lực nhổ φMq (Kennedy hiệu chỉnh, tính cho từng bản — lấy bản bất lợi), cắt (J3.6, nhóm phía nén).
**Hàn dầm 1 / 2**: hàn cánh (hàn góc hoặc CJP), hàn bụng vùng kéo (phát triển chảy bụng), hàn bụng chịu cắt, chảy cắt bụng dầm.
**Cấu tạo**: khoảng cách mép (J3.4, J3.5), gage, pf,o / pf,i, bước hàng, đường kính bu lông, hàn tối thiểu (J2.4), sườn 4ES (DG4 3.15, 3.16).
Không có kiểm tra phía cột / panel zone / J10 (không có cột).

## Hai quy ước DG16 ↔ DG39 (tuỳ chọn *Yield-line lever arm h* ở mục Options)
Mặc định theo **DG16 / RAM Connection** (h đo từ mặt cánh nén; Y của 2FU còn số hạng −1/2) — giống knee_app, đã khớp RAM #11.
Chọn *centerline* để đo h từ tâm cánh nén (DG4 / DG39): Y thấp hơn ~1–2 %, thiên về an toàn.
DG39 (2023) Table 5-2 bỏ số hạng −1/2 của 2FU, nên Y(DG39) cao hơn Y(DG16) khoảng 1.9 % với ví dụ 5.2-1.

## Kiểm chứng
- `python tests\test_splice_engine.py` — **DG39 Example 5.2-1** (bích bằng 2 bu lông, W18×35): Mu,eq, s, Yp (DG16 = DG39 − bp/4), db,req, lực hàn cánh Tu,min, φVn bu lông;
  **DG16 Example 4.2.1** (Y, dùng chung hàm với knee); đối xứng dấu mô men; lực dọc; Apex; hai bản khác bề dày; tự chọn; lưu danh sách.
- `xvfb-run -a python tests\test_gui_smoke.py` (Linux) hoặc `python tests\test_gui_smoke.py` (Windows) — thử giao diện: nhập số, đổi kiểu bích, Apex, tự chọn, dán tải, lưu / mở, báo cáo, Word.
  Tự bỏ qua nếu thiếu `customtkinter` hoặc màn hình.

## Giới hạn hiện tại
- **Chưa** đối chiếu số với một file RAM Connection nào cho Beam splice (knee đã đối chiếu RAM #11). Cần anh/chị cung cấp ví dụ RAM để so.
- **Chưa** xuất `.rcnx` cho RAM (cần khuôn `.rcnx` của Beam splice do RAM sinh ra, như `ram_proto.rcnx` của knee) và **chưa** có hình 3D, quét nội lực từ SAP2000.
- Hai dầm cùng chiều cao tại mặt nối; độ nghiêng cánh do tiết diện vát bị bỏ qua khi quy đổi nội lực (có cảnh báo khi vát > 2°).
- Không có bản đầu có sườn kiểu 8ES / 8E, bích bằng 6 bu lông, bản đầu mỏng theo EN; cấu hình MRE chưa kèm sườn.
- Công cụ hỗ trợ tính toán; kết quả cần được kỹ sư có chứng chỉ kiểm tra.

## Tệp
`splice_engine.py` lõi tính · `splice_defaults.py` mẫu · `splice_drawing.py` hình · `splice_gui.py` giao diện · `splice_report.py` báo cáo RAM + Word ·
`splice_store.py` danh sách lưu · `_knee.py` nối sang `knee_app` (engine, tiết diện, canvas).
