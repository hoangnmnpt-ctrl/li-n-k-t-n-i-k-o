# LIÊN KẾT THÉP — AISC 360-10 LRFD (giao diện theo RAM Connection Standalone)

Chạy: nhấp đúp **`Chay_LienKet.bat`** ở thư mục gốc (dùng `.venv` của *Lấy nội lực*) hoặc `python run.py [du_an.lkt]`.
Cần Python ≥ 3.12, `customtkinter`; `comtypes` khi lấy nội lực từ SAP2000.

## Cửa sổ chính
| Vùng | Chức năng |
|---|---|
| Thanh tiêu đề | New project · Open · Save, tên dự án (`*` = chưa lưu) |
| **File** | New project, Open (Ctrl+O), Save (Ctrl+S), Save as, nhập danh sách đã lưu của tool cũ, Exit |
| **Home · Joints** | **New** (Ctrl+N) — hộp thoại New joint 3 bước · **Edit** (nhấp đúp dòng) — cửa sổ thiết kế liên kết · Delete · Delete all · Copy · Go to (gõ ID + Enter) |
| **Home · Load conditions** | **Add/Edit** — bảng tải của nút · Delete — xoá mọi tổ hợp · Generate — lấy nội lực từ SAP2000 (knee) |
| **Home · View** | Template — áp mẫu · Information log — mọi cảnh báo / N.G. của dự án · Critical load condition — hiện tổ hợp khống chế |
| **Home · Databases** | Sections (quy cách + tiết diện đang dùng) · Materials · Connections (kiểu nút có / chưa có) · Bolts · Welds · Anchors (cấp bu lông neo, lỗ DG1) |
| **Design** | Edit connection · Smart connection (tự chọn tp / bu lông) · Design all · Joint data · Loads |
| **Output** | Report (.docx nút đang chọn) · All reports (cả dự án) · RAM .rcnx (mọi knee) · Results table (.csv mở bằng Excel) · Information log |
| Khung xem xanh đậm | Hình 3D phối cảnh kiểu RAM dựng từ khối thật (`model3d.py`): cấu kiện xám, bản đầu tím, bản gối xanh lá, sườn xanh rêu, bu lông lục giác cam, đường hàn vàng. Kéo trái xoay, kéo phải di chuyển, lăn zoom, nhấp đúp về góc mặc định. Ô xem: **3D** · **3D D/C** (tô màu theo D/C của Condition) · Elevation · End plate |
| Bảng thông tin (phải) | JOINT, họ nút (BCF / BS), BEAM – COLUMN (hoặc LEFT / RIGHT BEAM), SHEAR AND MOMENT CONNECTION (Template, Connection, bản / bu lông, tỷ số khống chế), Design code, **Edit...**, Additional notes (lưu theo nút) |
| Dải thẻ (dưới) | Mỗi nút một thẻ như RAM: số nút, họ, hình thu nhỏ, `tỷ số - tổ hợp khống chế` (xanh = đạt, đỏ = không đạt). Bấm để chọn, nhấp đúp để Edit, lăn chuột để cuộn |

## New joint (3 bước như RAM)
1. **Joint** — chọn nhóm và kiểu nút. Có trong tool: *Tapered beam to tapered column (Knee)* (BCF), *Beam splice*, *Apex* (BS), *Column base* (CB). Các kiểu khác hiện mờ.
2. **Data** — bảng Property / Value riêng cho từng loại: Knee (Beam = kèo, Column), Beam splice / Apex (Left beam, Right beam, góc dốc), Column base (cột, bệ, bản đế, neo, cách truyền cắt). Nhấp ô Value để sửa. Help bên phải.
3. **Loads** — bảng Num · Condition · V2 · Axial · M33 theo từng cấu kiện (knee: kèo + cột; nối dầm: lực tại mặt nối; chân cột: Axial · V2 · V3 · M33 · M22), dán từ Excel.

Bản đầu, bu lông, hàn, sườn: nhập ở cửa sổ **Edit** (form theo RAM, hình, bảng kiểm tra, báo cáo), bấm **OK** để lưu vào dự án.
Dự án lưu một file `*.lkt` (mặc định `lienket\du_an.lkt`).

## KNEE (BCF — Tapered beam to tapered column)


### Quy trình
1. **Kết nối SAP** → chọn nguồn tải (Design Combos mặc định, nút *Nguồn tải ▾* để tick) → chọn cột + kèo trong SAP (hoặc tick *Toàn mô hình*) → **Quét knee từ SAP**.
2. Tab *Knee quét từ SAP*: knee gom nhóm theo kích thước tiết diện tại nút + góc dốc (knee đối xứng hai đầu khung vào chung nhóm). Nhấp đúp nhóm → nạp vào thiết kế (bao nội lực mọi knee trong nhóm).
3. Chọn kiểu **Knee đứng** (bản 90°) / **Knee ngang** / **Knee xiên** (bản ⟂ kèo, hàn vào panel cột), sửa thông số bản, bu lông, sườn, hoặc bấm **Tự chọn tp / bu lông**.
4. Bấm một dòng kiểm tra → xem diễn giải công thức, bộ phận liên quan nhấp nháy trên hình.
5. Bấm **OK** ở cửa sổ Edit để lưu vào dự án. Quét SAP nhiều nhóm: tab *Knee quét từ SAP* → **Thêm mọi nhóm vào dự án**.

### Tương đương RAM Connection (Knee moment end plate — BCF)
- **Form nhập** theo đúng thứ tự và nhãn tiếng Anh của RAM: General information → Members (Beam, Support) → Moment end plate
  (Connector, Weld, Bolts, Bolt group external extension / external flange / internal flange / internal extension) → Stiffeners.
  Rê chuột lên nhãn để xem chú thích tiếng Việt. *Plate alignment* = kiểu knee (Vertical = đứng, Perpendicular = xiên, Horizontal = ngang).
  Cỡ hàn nhập theo D (1/16 in) như RAM.
- **Tab Loads**: bảng như hộp thoại Loads của RAM (ID, Description, Right beam Axial/V2/M3, Left beam, Column Axial/V2/M3). Dấu giống RAM.
- **Tab Report (RAM)**: báo cáo tiếng Anh đúng form RAM (Demands, Geometric Considerations, Plate / Column Behavior, Design Check,
  Global critical strength ratio); nút *Export report (.docx)*.
- **Export RAM Connection (.rcnx)**: knee hiện tại (tab Report của cửa sổ Edit) hoặc mọi knee của dự án (Output → RAM .rcnx) → 1 file, mỗi knee = 1 connection `Bentley.AISC.MEPlateKneeBCF`
  kèm bảng tải. Dựng từ khuôn `ram_proto.rcnx` (lấy từ file RAM 23 thật; tạo lại bằng `tools/make_ram_proto.py`).
- **Database tiết diện**: khi xuất (tick "Tạo tiết diện…"), tiết diện `I {hw}x{bf}x{tw}x{tf}` còn thiếu được thêm vào
  `…\Sections\WS Section-Hoang\Built up.sec` (sao lưu bản cũ trong `_backup`, không thêm trùng). Đóng/mở lại RAM để nạp.
- Đối chứng knee #11 của RAM (dữ liệu gốc từ .rcnx): nội lực quy đổi trùng 100%; bản đầu, bu lông, hàn, panel, sườn lệch ≤ 0.7%;
  riêng uốn bản cánh trong −1.6% (tool áp γr = 1.25), phía gối −0.7…−5% và ép mặt bản gối −12% (tool xét xé mép) — đều thiên về an toàn.

### Lấy thẳng từ SAP2000
- **🎯 Chọn knee trong SAP**: chọn nút knee (hoặc cột + kèo) trong SAP → nạp ngay tiết diện, L, đầu nút, góc dốc α, hướng cánh và nội lực.
  Các ô này bị **khoá 🔒** (banner đầu form); bấm *Mở khoá* để sửa tay.
- Tên tiết diện không theo quy cách → kích thước I tại mặt gối đọc qua API SAP (I-Section / Nonprismatic), ghi chú "(kích thước qua API SAP)".

### Panel zone
Mục *Panel zone (bề dày riêng)*: kích thước theo tiết diện gối tại nút, nhập riêng bề dày bụng, cánh ngoài, bản gối và vật liệu.
Mọi kiểm tra phía gối (Yc, J10.2/10.3/10.5, J10.6, sườn) dùng tiết diện panel. Trên hình, panel tách riêng khỏi cột.

### Trực quan
- **Tô màu theo D/C** (xanh ≤ 0.6 → vàng 0.9 → cam 1.0 → đỏ > 1) + nhãn D/C nổi trên từng bộ phận, tính theo tổ hợp đang xem.
- **Dòng lực**: kéo (đỏ) / nén (xanh) chạy từ cánh kèo qua bản, sườn, thanh chống chéo trong panel xuống cột.
- **Thanh trượt tổ hợp + ▶ phát tự động**: màu, lực, nhãn đổi theo từng tổ hợp.
- **3D**: kéo trái xoay, kéo phải di chuyển, lăn zoom, nhấp đúp về góc mặc định. Tô bóng, tô màu D/C, tô sáng kiểm tra đang chọn.
- **Thẻ đồng hồ** theo nhóm (Bản đầu, Bu lông, Phía gối, Panel·J10, Sườn, Hàn, Cấu kiện) — bấm để nhảy tới kiểm tra khống chế.
- **Rê chuột** lên bộ phận → tooltip các kiểm tra liên quan. 2D: lăn zoom, kéo di chuyển.

### Nội lực từ SAP (như tool Lấy nội lực)
- Vị trí: mặt gối đầu nút (trừ end offset), 9 cực trị tại đầu nút của **cả kèo và cột**; mỗi tổ hợp lấy đồng thời nội lực hai thanh.
- Đổi dấu: SAP M3 > 0 kéo mặt −2. Tool: M < 0 → cánh NGOÀI (kèo: cánh trên; cột: phía xa nhịp) chịu kéo. Hướng mặt ngoài xác định bằng trục local 2 (GetTransformationMatrix).

### Tiết diện
`250.5-150.5` (bụng 250×5, cánh 150×5, cao tổng 260) · `250.5-150.5.6` · `200.5.5-100.8` · `300.5-250.5-150.10` ·
`(250-500).5-150.5` · `(250-500-500-250).5.5.5-150.10.10.10/2-bal-2` · legacy `I (850-662)-5/150-8`.
"Cánh trên" = mặt +2 SAP.

### Kiểm chứng
`python lienket\tests\test_engine.py` (DG16 Ex 4.2.1, DG4 Yc, DG39 Yc bản nắp, RAM Connection #11, quy cách tiết diện) và `python lienket\tests\test_scanner.py` (khung cổng giả lập, đổi dấu, gom nhóm).

## NỐI DẦM (BS — Beam splice / Apex)



### Quy ước dấu
N > 0 kéo · **M > 0 → cánh DƯỚI chịu kéo** (mô men dương), **M < 0 → cánh TRÊN chịu kéo** · V lấy giá trị tuyệt đối. Nhập kN, kN·m, mm.
Apex: nội lực của một dầm tại mặt nối (hệ trục dầm), tool tự quy đổi về hệ trục bản (Nn = N·cosα + |V|·sinα, Vt = |N|·sinα + |V|·cosα).

### Các kiểm tra (theo từng tổ hợp, lấy giá trị bất lợi nhất)
Mỗi **bản đầu 1 / 2**: chảy dẻo uốn (DG16 §2.5), cắt chảy / cắt đứt phần nhô (DG4 3.12, 3.13), ép mặt / xé lỗ (J3-6).
**Bu lông**: đứt không nhổ φMnp, đứt có lực nhổ φMq (Kennedy hiệu chỉnh, tính cho từng bản — lấy bản bất lợi), cắt (J3.6, nhóm phía nén).
**Hàn dầm 1 / 2**: hàn cánh (hàn góc hoặc CJP), hàn bụng vùng kéo (phát triển chảy bụng), hàn bụng chịu cắt, chảy cắt bụng dầm.
**Cấu tạo**: khoảng cách mép (J3.4, J3.5), gage, pf,o / pf,i, bước hàng, đường kính bu lông, hàn tối thiểu (J2.4), sườn 4ES (DG4 3.15, 3.16).
Không có kiểm tra phía cột / panel zone / J10 (không có cột).

### Hai quy ước DG16 ↔ DG39 (tuỳ chọn *Yield-line lever arm h* ở mục Options)
Mặc định theo **DG16 / RAM Connection** (h đo từ mặt cánh nén; Y của 2FU còn số hạng −1/2) — giống phần knee, đã khớp RAM #11.
Chọn *centerline* để đo h từ tâm cánh nén (DG4 / DG39): Y thấp hơn ~1–2 %, thiên về an toàn.
DG39 (2023) Table 5-2 bỏ số hạng −1/2 của 2FU, nên Y(DG39) cao hơn Y(DG16) khoảng 1.9 % với ví dụ 5.2-1.

### Kiểm chứng
- `python lienket\tests\test_splice_engine.py` — **DG39 Example 5.2-1** (bích bằng 2 bu lông, W18×35): Mu,eq, s, Yp (DG16 = DG39 − bp/4), db,req, lực hàn cánh Tu,min, φVn bu lông;
  **DG16 Example 4.2.1** (Y, dùng chung hàm với knee); đối xứng dấu mô men; lực dọc; Apex; hai bản khác bề dày; tự chọn; lưu danh sách.
- `python lienket\tests\test_gui_smoke.py` — thử cửa sổ chính: New joint 3 bước, Copy / Delete / Go to, Critical load condition, Smart connection, Databases, Edit → OK, Save / Open, Report Word, Results CSV.
  Tự bỏ qua nếu thiếu `customtkinter` hoặc màn hình.

### Giới hạn hiện tại
- **Chưa** đối chiếu số với một file RAM Connection nào cho Beam splice (knee đã đối chiếu RAM #11). Cần anh/chị cung cấp ví dụ RAM để so.
- **Chưa** xuất `.rcnx` cho RAM (cần khuôn `.rcnx` của Beam splice do RAM sinh ra, như `ram_proto.rcnx` của knee) và **chưa** có hình 3D, quét nội lực từ SAP2000.
- Hai dầm cùng chiều cao tại mặt nối; độ nghiêng cánh do tiết diện vát bị bỏ qua khi quy đổi nội lực (có cảnh báo khi vát > 2°).
- Không có bản đầu có sườn kiểu 8ES / 8E, bích bằng 6 bu lông, bản đầu mỏng theo EN; cấu hình MRE chưa kèm sườn.
- Công cụ hỗ trợ tính toán; kết quả cần được kỹ sư có chứng chỉ kiểm tra.

## CHÂN CỘT (CB — Column base, bản đế + bu lông neo)

Tương đương RAM Connection *Base plate*. Tạo: Home → New → *Column top and base* → **Column base**. Nhấp đúp thẻ để mở Connection Pad.
Form giữ đúng các mục và tên trường của RAM (tiếng Anh), rê chuột lên nhãn để xem chú thích tiếng Việt:

| Mục RAM | Trường |
|---|---|
| General information · Analysis | Loads · Analysis axis (Major / Minor / Both axes / Biaxial) · Pressure distribution (Uniform / Triangular) · Consider strain compatibility |
| General information · Design criteria | Steel design code (AISC 2010/2016 LRFD/ASD) · Concrete design code (ACI 318-08/11/14) · Seismic provisions · Bearing stress calculation (Complete / Effective area) · Include friction between base plate and support |
| General information · Optimization criteria | Optimize thickness (max, min, increment) · longitudinal / transversal dimension (max / min distance to plate edge, increment) · anchor diameter · minimum hef · Keep anchor position |
| Members · Column | Column type · Section · Material · Longitudinal / Transversal offset |
| Base plate · Base plate | Plate shape · Connection type · Position on the support · N · B · Thickness · Material · Column weld · Outer welds flanges only · D · Override A2/A1 · Include shear lug |
| Base plate · Support | With pedestal · Longitudinal / Transversal dimension · Thickness · Material · Include grouting |
| Base plate · Anchor | Anchor position (Longitudinal / Transversal) · Rows number per side · Anchors per row · edge distances · Anchor type (Headed / Hooked) · Head type · Include lock nut · Anchor · hef · Material · Cracked concrete · Brittle steel · Anchors welded to base plate |
| Base plate · Anchor reinforcement | Type (Primary / Supplementary) · Tension reinforcement · Shear reinforcement |

**Results**: cửa sổ theo form báo cáo RAM (tiếng Anh) — Demands, Geometric considerations, Design check (Verification · Unit · Capacity ·
Demand · Ctrl EQ · Ratio · References), Global critical strength ratio. Nhấp một dòng Design check → diễn giải công thức tiếng Việt ở khung dưới,
bộ phận liên quan sáng trên hình 3D. Dùng chung cho knee và nối dầm.

### Quy ước
N > 0 kéo (nhổ), N < 0 nén (như SAP) · V2 theo phương N (x) · V3 theo phương B (z) · M33 > 0 → mép +x (phía cánh trên +2) chịu nén ·
M22 > 0 → mép +z chịu nén. Nội lực tại tâm cột (lệch tâm cột cộng Pu·offset vào mô men quanh tâm bản). Nhập kN, kN·m, mm.

### Phương pháp
- **Uniform**: DG1 §3.3 (mô men nhỏ / lớn, điều kiện có nghiệm Eq. 3.4.4). **Triangular**: hình thang (e ≤ L/6) → tam giác không kéo neo → tam giác fp,max + neo kéo.
  **Strain compatibility / Biaxial**: bản cứng, mặt phẳng biến dạng, bê tông Ec = 4700√f'c chỉ nén, neo Es chỉ kéo — giải số (Newton).
- **Both axes**: kiểm tra độc lập từng phương, lực neo góc cộng tuyến tính. **Major / Minor**: bỏ M22, V3 / M33, V2.
- **Effective area**: vùng cách thép cột ≤ c = tp·√(φFy/(2fp,max)) — cách tiếp cận của tool, cần đối chiếu RAM.
- Bản đế: uốn phía ép (DG1 3.3.14/15, tuyến tính khi Triangular), phía kéo (neo ngoài cánh Tu·x/B; neo giữa cánh 45°).
- Neo AISC J3 (Fnt = 0.75Fu, Fnv = 0.40Fu / 0.45Fu 2016), J3.7. ACI: thép, phá vỡ kéo / cắt, nhổ tuột (headed / hooked), nổ mặt bên, pryout, D.7;
  Brittle steel φ 0.65/0.60; Seismic ×0.75 (318-08: mọi chế độ; 318-11/14: chế độ bê tông);
  Primary reinforcement: thay phá vỡ bê tông, báo As yêu cầu (fy = 420 MPa); Supplementary: Condition A φ = 0.75.
- Cắt: neo (hàn vào bản đế: mọi neo; không hàn: một nửa) hoặc bản chắn cắt; Include friction giảm lực cắt 0.75·0.55·Pu. ASD: φRn/1.5.
- Hàn cột – bản đế: đàn hồi trên chu vi hàn (Outer welds flanges only: chỉ mặt ngoài cánh), lực nén truyền bằng tì ép.

### Kiểm chứng
`python lienket\tests\test_base_engine.py` — cân bằng DG1 uniform / triangular, nén đúng tâm (λ), nhổ, tương thích biến dạng & biaxial, ACI một neo,
cốt thép neo primary / supplementary, seismic, ASD, lệch tâm, layout ngang, hàn, ma sát, tối ưu, mô hình 3D.

### Giới hạn hiện tại
- **Chưa** đối chiếu số với file RAM Base plate — cần một ví dụ RAM (.rcnx hoặc báo cáo) để so từng dòng.
- Chưa có: bản đế có sườn (Stiffened), hình dạng bản khác chữ nhật, cột hộp / ống, neo chôn sau; uốn neo qua vữa > 50 mm, phá vỡ bê tông do bản chắn cắt (có cảnh báo).
- Chưa xuất `.rcnx` cho chân cột, chưa lấy nội lực chân cột trực tiếp từ SAP2000 (dán từ Excel ở bảng Loads).

## Tệp
`app.py` cửa sổ chính · `newjoint.py` New joint · `project.py` dự án · `knee_gui.py` / `splice_gui.py` cửa sổ thiết kế ·
`engine.py` / `splice_engine.py` lõi tính · `model3d.py` mô hình 3D + `ramview.py` khung xem 3D kiểu RAM · `drawing.py` / `splice_drawing.py` / `view3d.py` hình · `report.py` / `splice_report.py` báo cáo ·
`base_engine.py` / `base_defaults.py` / `base_drawing.py` / `base_report.py` / `base_gui.py` chân cột · `results_view.py` cửa sổ Results ·
`defaults.py` / `splice_defaults.py` mẫu · `knee_section.py` tiết diện · `scanner.py` quét SAP · `ram_export.py` + `ram_proto.rcnx` xuất RAM · `tests\` kiểm thử.
