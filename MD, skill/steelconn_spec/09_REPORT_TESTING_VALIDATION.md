# 09 — BÁO CÁO, KIỂM THỬ & NGHIỆM THU

## 1. Nguyên tắc kiểm thử

1. **Tầng 1 – đơn vị**: mỗi hàm `limit_states` có ≥2 test: một giá trị đối chiếu Manual/tay (bảng §3), một test biên (điều kiện rẽ nhánh: lb/d = 0.2, α' = 0 và 1, KL/r = 25, Pr = 0.4Pc…).
2. **Tầng 2 – connection**: đối chiếu ví dụ Manual/DG (sai số ≤ 1% trên từng giá trị trung gian chính, không chỉ kết quả cuối).
3. **Tầng 3 – joint**: cân bằng lực (tổng lực tại các giao diện = lực đầu vào, sai số < 1e-6 tương đối), đối xứng (gương nút trái/phải cho kết quả như nhau), đảo dấu mômen hoán đổi cánh kéo/nén.
4. **Property-based** (`hypothesis`, tùy chọn): capacity không giảm khi tăng t, d bu lông, w hàn; ratio ≥ 0.
5. **Hai hệ đơn vị**: mọi test tầng 1 chạy cả US (đổi sang SI rồi so) — bắt lỗi hằng số ksi.
6. Test phụ thuộc số liệu PDF người dùng chưa cung cấp → `pytest.skip("need DG4 example data")`, **không** tự bịa số liệu kỳ vọng.

## 2. Mẫu báo cáo (giống RAM Connection)

```
==============================================================
 STEELCONN  v0.x   —  AISC 360-10 LRFD
 Project: ...      Joint: BCF-01  (Beam to column flange)
 Date: ...         Units: SI (mm, kN, MPa)
==============================================================
1. GEOMETRY & MATERIALS
   Column  W14X90  A992  Fy=345 Fu=450
   Right beam W18X50 A992   Connection: Moment end plate 4E
   End plate 230x25 A572Gr50, bolts 4+4 A325-N M22 STD pretensioned, g=140, pfo=pfi=50, de=40
   Welds: flange 10 mm fillet both sides, web 6 mm fillet both sides (E70XX)
   [hình phác: SVG/PNG matplotlib - mặt đứng + mặt bằng]
2. LOADS
   | LC | P | V2 | M3 | ... |
3. CHECKS  (per load case, governing LC shown)
   ---------------------------------------------------------
   Bolts
   Bolt tension rupture (no prying)      DG4 Eq.3.x; J3.6
       φMnp = φ·2·Pt·Σh_i = 0.75·2·<Pt>·(<h0>+<h1>) = <value> kN·m
       Mu = <value> kN·m                                 ratio <r>  OK
   ...
   Column
   Panel zone shear                      J10.6 (J10-9)
       φRv = 0.90·0.6·Fy·dc·tw = 0.90·0.6·<Fy>·<dc>·<tw> = <value> kN     ratio <r> OK
   (mọi <...> là giá trị do chương trình điền)
   ---------------------------------------------------------
4. SUMMARY
   Max ratio = 0.87 (Column web crippling, LC2)   STATUS: OK
   Warnings: [...]
   Not checked / outside scope: [...]
```
Yêu cầu:
- Mỗi check in: tên, điều khoản, công thức ký hiệu, dòng thay số (đơn vị hiển thị), demand, capacity, ratio, status.
- Bảng tổng hợp ratio theo nhóm (Bolts, Welds, Plates, Beam, Column, Gusset, Concrete, Detailing), tô màu (HTML): ≤0.9 xanh, 0.9–1.0 vàng, >1.0 đỏ.
- Mục "Assumptions" liệt kê mọi tùy chọn settings đã dùng + các check có `verify_flag`.
- Xuất: `.md`, `.html` (Jinja2), `.pdf` (từ HTML), `.json` (máy đọc), `.xlsx` tổng hợp batch (một dòng/ nút: joint, LC điều khiển, max ratio, check điều khiển).

## 3. Giá trị đối chiếu tầng 1 (đã tính kiểm — dùng làm test)

| Test | Input | Kỳ vọng |
|---|---|---|
| Bolt shear A325-N 7/8" LRFD | Fnv=54 ksi, Ab=0.6013 in² | φrn = 24.35 kip (Manual Table 7-1: 24.3) |
| Bolt shear A325-X 7/8" | Fnv=68 | 30.67 kip (Manual 30.7) |
| Bolt tension A325 7/8" | Fnt=90 | 40.59 kip (Manual 40.6) |
| Bolt M20 A325M-N (SI) | Fnv=372 MPa | φrn = 87.65 kN ; kéo 146.08 kN |
| Tearout bu lông mép 3/4", Le=1.25", lỗ 13/16", t=1/2", Fu=58 | lc = 0.84375 in | φRn = 22.02 kip (tearout khống chế; bearing 39.15) |
| Hàn E70 LRFD | trên 1/16" | 1.392 kip/in (Manual 1.392) |
| J3.7 A325-N, frv = 20 ksi, LRFD | | F'nt = 72.56 ksi |
| Panel zone W14X90 (dc=14.0, tw=0.44, Fy=50), Pr ≤ 0.4Pc | | φRv = 166.3 kip |
| Yield-line 4E: bp=7, g=5.5, pfi=pfo=1.75, d=18.0, tbf=0.57 (in) | h0 = 19.465, h1 = 15.395, s = 3.102 | Y = 112.50 in (kiểm tra số học công thức 05 §2; đối chiếu thêm DG4 Example) |

## 4. Ví dụ đối chiếu tầng 2 (người dùng nhập từ tài liệu vào `tests/data/*.yaml`)

| File YAML | Nguồn | Nội dung cần nhập |
|---|---|---|
| `manual_part7_ic.yaml` | Manual 14th Table 7-6/7-7 | vài điểm (n, s, ex, θ) → C |
| `manual_part8_ic_weld.yaml` | Table 8-4, 8-8 | (k, a, θ) → C |
| `manual_part10_examples.yaml` | Ex 10-1 (double angle), 10-9/10-10 (single plate conv./ext.), 10-6 (seat) | input + kết quả trung gian |
| `dg4_examples.yaml` | DG4 §3 examples 4E, 4ES, 8ES | db_req, tp_req, φMnp, Y, Yc, column checks |
| `dg16_examples.yaml` | DG16 flush examples | tương tự |
| `dg1_examples.yaml` | DG1 Ex 4.x | A1, tp_req, Y, Tu |
| `manual_part13_ufm.yaml` | Ex 13-x | α, β, r, Vc, Hc, Vb, Hb, mômen phụ |
| `aisc_design_examples_K.yaml` | Design Examples v14 Ch. K | từng limit state |

Khung YAML (AI phải tạo sẵn, với `TODO` cho người dùng điền):
```yaml
- id: DG4_4E_example
  source: "AISC DG4 2nd ed., Example X.X, page YY"
  units: US
  inputs: {Mu: TODO, d: TODO, tbf: TODO, bp: TODO, g: TODO, pfi: TODO, pfo: TODO, bolt: A325, Fpy: TODO}
  expected: {db_req: TODO, Y: TODO, tp_req: TODO, phiMnp: TODO}
  tolerance_rel: 0.01
```

## 5. Nghiệm thu cuối cùng (release 1.0)

- [ ] 15 mã nút, 40+ template chạy được từ `examples/`.
- [ ] 100% test pass, 0 test skip ở các module đã có dữ liệu PDF.
- [ ] Báo cáo HTML mở được, đủ mục §2.
- [ ] Batch 100 nút từ file SAP2000 CSV < 30 s.
- [ ] Mọi `verify_flag=True` được liệt kê trong `VERIFY_LIST.md` tự sinh (`steelconn verify-list`).
- [ ] So sánh chéo với RAM Connection (người dùng chạy 10 nút mẫu trên RAM) — chênh lệch ratio ≤ 3% hoặc giải thích được (khác giả thiết) trong `docs/ram_comparison.md`.
