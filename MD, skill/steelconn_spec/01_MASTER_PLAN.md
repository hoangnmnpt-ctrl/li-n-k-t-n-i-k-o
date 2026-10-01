# 01 — MASTER PLAN: STEELCONN (Python steel connection design, AISC 360-10)

## 1. Mục tiêu sản phẩm

Thư viện Python `steelconn` + CLI + (tùy chọn) GUI, có khả năng:

1. **Check mode**: nhận hình học liên kết do người dùng khai báo + nội lực → tính toàn bộ trạng thái giới hạn → tỷ số D/C (demand/capacity) từng check → báo cáo.
2. **Design mode** (giống "Smart connection" của RAM Connection): nhận nội lực + tiết diện cấu kiện + "template" (bảng lựa chọn cho phép: đường kính bu lông, chiều dày bản, kích thước hàn…) → tự tìm cấu hình nhẹ nhất/ rẻ nhất thỏa mọi check.
3. Xuất báo cáo Markdown/HTML/PDF theo kiểu RAM Connection: dữ liệu đầu vào → từng check có công thức, thay số, kết quả, tham chiếu điều khoản → tổng hợp ratio lớn nhất.
4. Nhập nội lực hàng loạt (CSV/Excel xuất từ SAP2000 `Joint Reactions`/`Element Forces - Frames`) cho nhiều nút và nhiều tổ hợp.

## 2. Giả định mặc định (AI KHÔNG được hỏi lại những điều này)

| Hạng mục | Mặc định | Ghi chú |
|---|---|---|
| Tiêu chuẩn | AISC 360-10, Manual 14th ed. | Thiết kế để có thể thêm 360-16/22 sau (strategy pattern `CodeEdition`) |
| Phương pháp | Cả **LRFD** và **ASD**, chọn bằng `design_method` | φ và Ω lưu cùng một chỗ trong mỗi check |
| Đơn vị nội bộ | N, mm, MPa, N·mm | Input/Output hỗ trợ kN, kN·m, và kip, in, ksi, kip-ft qua bộ chuyển đổi |
| Vật liệu mặc định | Dầm/cột A992 (Fy=345, Fu=450 MPa), bản mã A36 (250/400), HSS A500 Gr.C (tròn 317/427? xem bảng 02), neo F1554 Gr.36 | Người dùng có thể thêm mác VN/JIS/EN (SS400, Q345…) như vật liệu tùy biến |
| Bu lông | A325 (Group A), A490 (Group B); kiểu N, X, SC; lỗ STD, OVS, SSL, LSL | Hỗ trợ cả kích thước inch và M16–M36 |
| Que hàn | E70XX (FEXX = 482 MPa) | |
| Tiết diện | Đọc AISC Shapes Database v14.1/v15 (CSV, metric) do người dùng cung cấp; kèm file mẫu ~30 tiết diện để test; hỗ trợ tiết diện tổ hợp (built-up I, tapered) khai báo tay | |
| Nội lực | Đầu vào là nội lực **đã tổ hợp** (factored với LRFD, service với ASD). Module ASCE 7-10 combos là tùy chọn Phase 9 | |
| Quy ước dấu | Lực dọc P: kéo dương. V: theo trục địa phương của cấu kiện. M: dương khi căng thớ dưới (dầm) | Xem 02 §6 |
| Động đất | **Ngoài phạm vi** (AISC 341, 358). Nếu `seismic=True` → cảnh báo "not supported" | |
| Mỏi, cháy | Ngoài phạm vi | |
| Python | ≥3.10, chỉ dùng stdlib + `numpy`, `pydantic>=2`, `pandas`, `jinja2`, `pytest`; tùy chọn `matplotlib`, `weasyprint`/`markdown` | Không dùng thư viện kết cấu bên thứ ba |

## 3. Phạm vi — các nhóm nút (theo menu "New joint" của RAM Connection)

| Nhóm | Mã | Kiểu nút | Phase |
|---|---|---|---|
| Beam to support | BCF | Beam to column flange; with opposite beam; haunched; haunched with opposite; tapered beam to column; tapered beam to tapered column (Knee); tubular mitred knee | 3, 4, 5 |
| | BCW | Beam to column web; with opposite beam; tubular mitred knee (BCW) | 3, 4 |
| | BG | Beam to girder (single/double side) — nằm ngoài màn hình chụp nhưng có trong RAM (ô bị cắt bên phải) | 3 |
| Splices | BS | Beam splice; Apex; Apex with haunched beams; Tapered beam splice | 5 |
| | CS | Column splice | 5 |
| Column top & base | CC | Column cap (dầm liên tục trên cột) | 6 |
| | CB | Column base; with one brace; with two braces | 6 |
| | CCB | Column cap – brace | 6, 7 |
| Vertical bracing | CBB | Column–beam–brace 1/2/4 braces; Y brace; K brace | 7 |
| | CVR | Chevron 1/2/4 braces | 7 |
| | VXB | Vertical X brace | 7 |
| Horizontal bracing | HCBB | Horizontal column–beam–brace (full / front beam only / right beam only) | 7 |
| | HBBB | Horizontal beam–beam–brace; with girder only | 7 |
| | HXB | Horizontal X brace | 7 |
| Trusses | CHB | Tubular YT, KN, K, X (2 branches), X (4 branches), KT, KT 3 branches, KT 6 branches | 8 |

Kiểu liên kết cấp "connection" (gán cho từng cấu kiện trong nút — đúng triết lý RAM Connection):

- **Shear (Part 10)**: single plate (shear tab) conventional/extended, double angle (bolted/welded), single angle, shear end plate, unstiffened seat, stiffened seat, tee.
- **Moment**: extended/flush end plate (DG4/16/39), bolted flange plate (FP), welded flange plate, directly welded flange (CJP), + shear connection cho bản bụng.
- **Axial/brace**: gusset plate (bolted/welded brace: W, 2L, L, WT, HSS có khe, HSS có bản đầu), claw angles, UFM interfaces.
- **Splice**: flange-plate + web-plate splice (bolted), end-plate splice, column splice (flange plates, web plates, bearing).
- **Base**: base plate + anchor rods + (tùy chọn) shear lug.
- **HSS**: welded branch-to-chord (Chapter K).

## 4. Cây thư mục repo bắt buộc

```
steelconn/
├── pyproject.toml
├── README.md
├── steelconn/
│   ├── __init__.py
│   ├── units.py                  # chuyển đổi đơn vị, hằng số ksi->MPa
│   ├── codes/
│   │   ├── base.py               # CodeEdition abstract, phi/omega registry
│   │   └── aisc360_10.py         # hệ số, bảng J3.1, J3.2, J3.3, J3.4, J2.4
│   ├── materials.py              # Steel, BoltGrade, WeldElectrode, Concrete
│   ├── sections/
│   │   ├── database.py           # đọc AISC shapes CSV
│   │   ├── shapes.py             # IShape, Channel, Angle, Tee, HSSRect, HSSRound, Pipe, DoubleAngle, BuiltUpI, TaperedI
│   │   └── sample_shapes.csv
│   ├── components/
│   │   ├── bolts.py              # Bolt, BoltGroup (pattern, IC method)
│   │   ├── welds.py              # Weld, WeldGroup (elastic + IC method)
│   │   ├── plates.py             # Plate, Stiffener, Doubler
│   │   └── holes.py
│   ├── limit_states/             # HÀM THUẦN, không phụ thuộc joint
│   │   ├── result.py             # CheckResult dataclass
│   │   ├── bolt_ls.py            # J3.6, J3.7, J3.8, J3.9, J3.10
│   │   ├── weld_ls.py            # J2.4, base metal, IC weld
│   │   ├── element_ls.py         # J4.1–J4.4, flexure, buckling bản mã
│   │   ├── block_shear.py        # J4.3
│   │   ├── prying.py             # Manual Part 9
│   │   ├── concentrated.py       # J10.1–J10.8
│   │   ├── cope.py               # Manual Part 9 coped beam
│   │   ├── member_ls.py          # E, F, G, H1 cho bản mã/đoạn ngắn
│   │   ├── hss_ls.py             # Chapter K
│   │   └── concrete_ls.py        # J8 bearing, (tùy chọn) ACI 318 App. D
│   ├── connections/              # cấp "connection" (một đầu cấu kiện)
│   │   ├── base.py               # Connection abstract: geometry(), checks(), design()
│   │   ├── shear/                # single_plate.py, double_angle.py, single_angle.py, shear_end_plate.py, seat.py, stiffened_seat.py, tee.py
│   │   ├── moment/               # end_plate.py (DG4/16/39), flange_plate.py, direct_weld.py
│   │   ├── brace/                # gusset.py, ufm.py, whitmore.py, brace_end.py
│   │   ├── splice/               # beam_splice.py, column_splice.py, end_plate_splice.py
│   │   ├── base_plate/           # base_plate.py, anchor.py, shear_lug.py
│   │   └── hss/                  # branch_chord.py, mitred_knee.py
│   ├── joints/                   # cấp "joint" (BCF, BCW, CBB…)
│   │   ├── base.py               # Joint abstract, member slots
│   │   ├── registry.py           # map mã -> class; list các template
│   │   ├── bcf.py bcw.py bg.py bs.py cs.py cc.py cb.py ccb.py cbb.py cvr.py vxb.py hcbb.py hbbb.py hxb.py chb.py
│   ├── column_side.py            # check phía cột dùng chung (J10, panel zone, stiffener, doubler)
│   ├── design/
│   │   ├── templates.py          # "Smart connection" templates (YAML)
│   │   └── optimizer.py          # duyệt rời rạc có cắt tỉa
│   ├── loads/
│   │   ├── load_case.py
│   │   ├── asce7_10.py           # tùy chọn
│   │   └── sap2000_import.py
│   ├── report/
│   │   ├── builder.py
│   │   └── templates/*.md.j2 *.html.j2
│   └── cli.py                    # `steelconn run input.json --report out.html`
├── examples/                     # input JSON mẫu cho từng kiểu nút
└── tests/
    ├── test_units.py
    ├── limit_states/…            # test từng hàm với số liệu tay
    ├── connections/…             # đối chiếu ví dụ Manual/DG
    └── joints/…
```

## 5. Lộ trình (10 phase) — mỗi phase là 1 lần giao việc cho AI

| Phase | Nội dung | Đầu ra | Tiêu chí nghiệm thu |
|---|---|---|---|
| **P0** | Skeleton repo, `units.py`, `codes/aisc360_10.py` (bảng J3.1, J3.2, J3.3, J3.4, J2.4, φ/Ω), `materials.py`, `CheckResult` | Repo chạy `pytest` | Test bảng tra khớp 100% tài liệu 02/03 |
| **P1** | `sections/` (đọc CSV, tính thuộc tính tiết diện tổ hợp & tapered), `components/` (bolt group, weld group, IC method bu lông & hàn) | Hàm C-coefficient | IC bolt: sai số ≤2% so với Manual Table 7-6/7-7 (điểm kiểm tra do người dùng tra, xem 09 §4) ; IC weld ≤2% Manual Table 8-4 |
| **P2** | `limit_states/` đầy đủ theo 03 | ~60 hàm thuần | Mỗi hàm ≥2 test tay; đúng φ/Ω |
| **P3** | Liên kết khớp (shear connections) + nút BCF/BCW/BG dạng shear | 7 kiểu shear | Đối chiếu Manual Part 10 examples (sai số ≤1%) |
| **P4** | Liên kết mômen: end plate (DG4/16/39), flange plate, direct weld + `column_side.py` | 3 kiểu moment | Đối chiếu DG4 Ex 4E/4ES/8ES, DG16 flush examples (≤1%) |
| **P5** | Haunch, tapered, knee, apex, beam splice, tapered splice, column splice | BCF haunched/knee, BS, CS | Kiểm tra cân bằng lực, đối chiếu DG16 §/ví dụ tay |
| **P6** | Column base, base with 1/2 braces, column cap, column cap–brace | CB, CC, CCB | Đối chiếu DG1 Ex 4.1, 4.3, 4.4 (≤1%) |
| **P7** | Gusset/UFM, CBB (1/2/4 braces, Y, K), CVR, VXB, HCBB, HBBB, HXB | 12 kiểu nút giằng | Đối chiếu Manual Part 13 Ex 13-1, 13-2, 13-3 |
| **P8** | HSS Chapter K: CHB YT, K, KN, X, KT… + mitred knee | 9 kiểu | Đối chiếu Manual Part K examples / DG24 |
| **P9** | Design mode (optimizer + templates), import SAP2000, tổ hợp ASCE 7-10, batch | CLI batch | Chạy 100 nút <30 s |
| **P10** | Báo cáo HTML/PDF kiểu RAM, hình vẽ phác (matplotlib), docs | Báo cáo | Báo cáo đủ mục 09 §2 |

## 6. Definition of Done (áp dụng cho mọi phase)

1. `pytest -q` pass 100%, coverage module mới ≥85%.
2. Mỗi check trả về `CheckResult` với: `name`, `clause`, `demand`, `capacity` (đã nhân φ hoặc chia Ω), `ratio`, `formula` (chuỗi LaTeX/ký hiệu), `substituted` (chuỗi thay số), `status` (OK/NG/NA/WARN), `verify_flag`.
3. Không có số "ma thuật" trong code: hệ số lấy từ `codes/aisc360_10.py` hoặc hằng số có tên + trích dẫn.
4. Có ít nhất 1 file `examples/*.json` cho mỗi kiểu nút mới và CLI chạy được.
5. Hàm public có docstring (Google style) + type hints; `ruff`/`mypy --strict` sạch lỗi ở module mới.
6. Kiểm tra hình học (detailing): khoảng cách bu lông, mép, kích thước hàn min/max, khe hở lắp dựng — là check có ratio, không phải chỉ cảnh báo.

## 7. Rủi ro & cách xử lý

| Rủi ro | Biện pháp |
|---|---|
| AI bịa/nhớ sai công thức yield-line | Bảng yield-line được cung cấp nguyên văn trong 05; test bằng ví dụ DG |
| Nhầm đơn vị khi dùng hằng số ksi | Hàm `ksi(x)` trong `units.py`; test mỗi công thức ở cả hai hệ đơn vị |
| DG39 dựa trên AISC 360-22 (không phải 360-10) | Tham số `end_plate_method = "DG4_DG16" | "DG39"`; mặc định DG4/DG16 (đúng thời với 360-10); DG39 dùng khi người dùng chọn, ghi chú khác biệt trong báo cáo |
| Nút phức tạp (4 braces, KT 6 branches) quá tải cho AI | Nút = tổ hợp các "connection" độc lập + giao diện cân bằng lực (UFM, Chapter K) → mỗi connection code và test riêng |
| Người dùng muốn check tay | Báo cáo in công thức + thay số từng bước |
