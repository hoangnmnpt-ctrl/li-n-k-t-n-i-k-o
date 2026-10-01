# 05 — LIÊN KẾT BẢN ĐẦU CHỊU MÔMEN (DG4, DG16, DG39)

Module: `connections/moment/end_plate.py`, `connections/moment/yield_lines.py`, `column_side.py`.

## 0. Phạm vi & lựa chọn phương pháp

| `end_plate_method` | Nguồn | Khi dùng |
|---|---|---|
| `"DG4_DG16"` (mặc định) | DG4 2nd ed. (2003) cho extended 4E/4ES/8ES; DG16 (2002) cho flush & multi-row extended | Cùng thời với AISC 360-05/10 → nhất quán với 360-10 |
| `"DG39"` | DG39 (AISC, 2023) — hợp nhất DG4 + DG16, cập nhật theo 360-22/358-22 | Chỉ bật khi người dùng cung cấp PDF DG39 để AI đối chiếu phương trình; nếu không có PDF → AI **không tự chế**, fallback DG4_DG16 + WARN "DG39 equations not verified" |

Phương pháp thiết kế bản & bu lông (`plate_behavior`):
- `"thick"` (mặc định, DG4/DG16 "no prying"): bản đủ dày để bu lông đạt Pt không có prying. Đơn giản, được RAM Connection dùng làm mặc định cho end plate.
- `"thin"` (DG16 §/ Kennedy modified): cho phép prying, bản mỏng hơn, tính `Qmax`.

## 1. Cấu hình (configuration codes)

| Code | Mô tả | Hàng bu lông kéo (từ ngoài vào) | Nguồn |
|---|---|---|---|
| `2FU` | Two-bolt flush unstiffened | 1 hàng trong (h1) | DG16 |
| `4FU` | Four-bolt flush unstiffened | 2 hàng trong (h1, h2), bước pb | DG16 |
| `4FS` | Four-bolt flush stiffened (sườn giữa 2 hàng) | h1, h2 | DG16 [VERIFY Y] |
| `4E` | Four-bolt extended unstiffened | h0 (ngoài), h1 (trong) | DG4, DG16 |
| `4ES` | Four-bolt extended stiffened | h0, h1 + sườn phần nhô | DG4 |
| `8ES` | Eight-bolt extended stiffened | h1,h2 (2 hàng ngoài), h3,h4 (2 hàng trong); mỗi hàng 2 bu lông → 8 bu lông vùng kéo | DG4 |
| `8E` | Eight-bolt extended unstiffened | như 8ES không sườn | DG39 [VERIFY] |
| `MRE1/2` | Multiple-row extended 1/2 (1 hàng ngoài, 2 hàng trong) | h1; h2, h3 | DG16 [VERIFY Y] |
| `MRE1/3` | 1 ngoài, 3 trong | h1; h2..h4 | DG16 [VERIFY Y] |
| `MRE1/3S` | như trên có sườn | | DG16 [VERIFY Y] |

Mỗi hàng có 2 bu lông (gage g), trừ 8ES/8E: mỗi phía cánh có 2 hàng × 2 bu lông ×… → theo DG4, 8ES có 4 bu lông ngoài (2 hàng × 2) và 4 bu lông trong. Code phải mô tả bu lông bằng danh sách hàng `rows=[{h, n_bolts, location:"outer"/"inner"}]` để tổng quát.

Ký hiệu hình học (DG4 Fig. 3-x):
- `bp` bề rộng bản, `tp` dày bản, `g` gage ngang, `pfo` khoảng từ mép ngoài cánh kéo tới hàng ngoài, `pfi` từ mép trong cánh kéo tới hàng trong, `pb` bước giữa hàng, `de` khoảng từ hàng ngoài cùng tới mép bản.
- `h0, h1, ...` = khoảng cách từ **tâm cánh nén** tới từng hàng bu lông kéo (DG4 dùng `d0, d1…` tương đương; giữ `h_i`).
- `s = 0.5 sqrt(bp g)`; nếu `pfi > s` → dùng `pfi = s` trong công thức Y.
- `tbf, tbw, d, bbf, Fyb` của dầm; `Fpy, Fpu` của bản.

## 2. Yield-line parameter Y — bản đầu (`yield_lines.py`)

Implement mỗi công thức là một hàm riêng, docstring ghi nguồn + `verified: bool`. Test bằng ví dụ DG.

```text
2FU (DG16):
  Y = bp/2 [ h1 (1/pf + 1/s) − 1/2 ] + 2/g [ h1 (pf + s) ]

4FU (DG16)  [VERIFY]:
  Y = bp/2 [ h1 (1/pf + 1/s) + h2 (1/s) − 1/2 ] + 2/g [ h1 (pf + 0.75 pb) + h2 (s + 0.25 pb) ] + g/2

4E (DG4 Table 3.1):
  Y = bp/2 [ h1 (1/pfi + 1/s) + h0 (1/pfo) − 1/2 ] + 2/g [ h1 (pfi + s) ]

4ES (DG4 Table 3.1):
  Case 1 (de ≤ s):
  Y = bp/2 [ h1 (1/pfi + 1/s) + h0 (1/pfo + 1/(2 de)) ] + 2/g [ h1 (pfi + s) + h0 (de + pfo) ]
  Case 2 (de > s):
  Y = bp/2 [ h1 (1/pfi + 1/s) + h0 (1/s + 1/pfo) ] + 2/g [ h1 (pfi + s) + h0 (s + pfo) ]

8ES (DG4 Table 3.1):  (h1 ngoài cùng, h2 ngoài-trong, h3 trong-trên, h4 trong-dưới)
  Case 1 (de ≤ s):
  Y = bp/2 [ h1/(2de) + h2/pfo + h3/pfi + h4/s ]
      + 2/g [ h1 (de + pb/4) + h2 (pfo + 3pb/4) + h3 (pfi + pb/4) + h4 (s + 3pb/4) + pb² ] + g
  Case 2 (de > s):
  Y = bp/2 [ h1/s + h2/pfo + h3/pfi + h4/s ]
      + 2/g [ h1 (s + pb/4) + h2 (pfo + 3pb/4) + h3 (pfi + pb/4) + h4 (s + 3pb/4) + pb² ] + g

MRE1/2, MRE1/3, 4FS, 8E: [VERIFY] — lấy nguyên văn từ DG16 Table 2-x / DG39; không có PDF → raise NotVerifiedError, joint báo "configuration not available".
```

## 3. Yield-line Yc — cánh cột (DG4 Table 3.4 & 3.5)

`s = 0.5 sqrt(bcf g)`, `c = pfo + pfi + tbf` (khoảng giữa hàng ngoài và hàng trong), `psi, pso` = khoảng từ sườn liên tục (continuity plate) tới hàng trong / hàng ngoài.

```text
4E / 4ES, cánh cột KHÔNG sườn:
  Yc = bcf/2 [ h1/s + h0/s ] + 2/g [ h1 (s + 3c/4) + h0 (s + c/4) + c²/2 ] + g/2

4E / 4ES, cánh cột CÓ sườn (continuity plates tại cao độ cánh dầm):
  Yc = bcf/2 [ h1 (1/s + 1/psi) + h0 (1/s + 1/pso) ] + 2/g [ h1 (s + psi) + h0 (s + pso) ]

8ES, KHÔNG sườn  [VERIFY]:
  Yc = bcf/2 [ h1/s + h4/s ] + 2/g [ h1 (pb + c/2 + s) + h2 (pb/2 + c/4) + h3 (pb/2 + c/2) + h4 (s) ] + g/2

8ES, CÓ sườn  [VERIFY]:
  Yc = bcf/2 [ h1/s + h2/pso + h3/psi + h4/s ] + 2/g [ h1 (s + pb/4) + h2 (pso + 3pb/4) + h3 (psi + pb/4) + h4 (s + 3pb/4) + pb² ]

Flush (2FU/4FU) cánh cột: [VERIFY] DG16 Table 2-x.
```
Nếu cột là tiết diện đầu cột (column top, không có phần cột phía trên), Yc thay đổi — DG4 có công thức riêng [VERIFY]; không có → WARN và yêu cầu sườn.

## 4. Quy trình thiết kế/ kiểm tra — `plate_behavior="thick"` (LRFD; ASD thay φ bằng 1/Ω)

Đầu vào: Mu (có dấu; xét cả hai chiều nếu có mômen đảo chiều → hoán đổi cánh kéo/nén), Vu, Pu.

```
Bước 1  Lực kéo quy đổi do lực dọc: nếu Pu kéo → Mu_eq = |Mu| + Pu (d − tbf)/2   [giả thiết đơn giản, ghi rõ trong báo cáo]
        (RAM Connection: phân lực dọc đều cho bu lông; cách tương đương: cộng Pu/n_bolts vào mỗi bu lông kéo — chọn tùy chọn `axial_distribution="uniform"|"moment_equivalent"`, mặc định "moment_equivalent")
Bước 2  db_req = sqrt( 2 Mu / (π φ Fnt Σ h_i) ) , φ = 0.75                 (DG4 Eq. 3.5 / DG16)
        Σ h_i tổng qua các hàng kéo (mỗi hàng 2 bu lông → hệ số 2 đã nằm trong công thức)
Bước 3  Pt = Fnt Ab ; Mnp = 2 Pt Σ h_i  (mômen đứt bu lông không prying)
        Check: φ Mnp ≥ Mu   (φ = 0.75)                                         → check "bolt_tension_rupture_no_prying"
Bước 4  tp_req = sqrt( 1.11 γr φ Mnp / (φb Fpy Y) ) ; φb = 0.90 ; γr = 1.25 (flush), 1.00 (extended)
        Check: tp ≥ tp_req  → ratio = tp_req/tp                                → "end_plate_thickness_thick_plate"
Bước 5  Uốn bản: φb Mpl = φb Fpy tp² Y ≥ Mu                                   → "end_plate_flexural_yielding"
Bước 6  Lực cánh: Ffu = Mu / (d − tbf)
Bước 7  (Extended unstiffened 4E) Cắt phần nhô:
          chảy: Ffu/2 ≤ φ 0.6 Fpy bp tp       (φ = 1.00, J4.2)                 → "end_plate_shear_yield_ext"
          đứt : Ffu/2 ≤ φ 0.6 Fpu An ; An = [bp − 2(dh + 2mm)] tp (φ = 0.75)    → "end_plate_shear_rupture_ext"
        (Flush & stiffened: bỏ qua bước này hoặc NA)
Bước 8  Sườn bản đầu (4ES, 8ES, MRE-S):
          ts ≥ tbw (Fyb/Fys)                                                   → "stiffener_thickness"
          hst/ts ≤ 0.56 sqrt(E/Fys)                                            → "stiffener_local_buckling"
          Lst ≥ hst / tan30°                                                   → "stiffener_length" (detailing)
          hàn sườn–bản & sườn–cánh dầm: CJP khi ts > 10 mm, ngược lại hàn góc hai mặt phát triển Fys ts  [DG4 khuyến nghị]
Bước 9  Bu lông chịu cắt: Vu ≤ φRn = φ Fnv Ab n_b,comp  (φ = 0.75)
          n_b,comp = số bu lông vùng nén (4E: 4 ; 8ES: 8 ; flush: bu lông hàng nén) — tùy chọn `shear_bolts="compression_only"|"all"`
                                                                                → "bolt_shear"
Bước 10 Ép mặt/ xé bu lông cắt, trên bản đầu và trên cánh cột:
          φRn = n_i r_ni + n_o r_no  (J3.10, lc riêng bu lông trong/ngoài)       → "bolt_bearing_end_plate", "bolt_bearing_column_flange"
Bước 11 Hàn cánh dầm–bản: thiết kế cho Ffu (tùy chọn `flange_weld_develop="Ffu"|"flange_yield"`; mặc định "Ffu"; "flange_yield" = phát triển Fyb bbf tbf)
          Hàn góc 2 mặt: φRn = φ 0.6 FEXX (1.5) 0.707 w L_w (θ = 90° → hệ số 1.5 nếu use_directional_strength)
          L_w = 2 bbf − tbw (hai mặt cánh, trừ bụng)                              → "weld_beam_flange"
Bước 12 Hàn bụng–bản:
          (a) vùng kéo (từ mặt trong cánh kéo tới hàng bu lông trong cùng + 2db): phát triển φ 0.9 Fyb tbw  [DG4/DG16, VERIFY hệ số]  → "weld_web_tension"
          (b) chịu cắt Vu trên chiều dài từ giữa bụng tới cánh nén (hoặc toàn chiều cao nếu tùy chọn) → "weld_web_shear"
Bước 13 Dầm: F13.1 không áp dụng (không có lỗ trên cánh); check bụng dầm chịu cắt G2 (thường thỏa).
```

### 4b. `plate_behavior="thin"` (DG16, cho phép prying) [VERIFY toàn bộ mục]
```
Mpl = Fpy tp² Y ; φb Mpl ≥ Mu  (φb = 0.90)
Với từng hàng (o = ngoài, i = trong):
  w'  = bp/2 − (dh + 2 mm)
  a_i = 3.682 (tp/db)³ − 0.085       [in] → đổi mm (công thức thứ nguyên inch: tính theo inch rồi đổi)
  F'_i = tp² (0.85 bp/2 + 0.80 w') + π db³ Fnt/8   /  (4 pf,i)
  Qmax,i = w' tp²/(4 a_i) · sqrt( Fpy² − 3 (F'_i/(w' tp))² )
φMq = max của 4 trường hợp (4E):
  (1) φ [ 2(Pt − Qmax,o) h0 + 2(Pt − Qmax,i) h1 ]
  (2) φ [ 2(Pt − Qmax,o) h0 + 2 Tb h1 ]
  (3) φ [ 2(Pt − Qmax,i) h1 + 2 Tb h0 ]
  (4) φ [ 2 Tb (h0 + h1) ]
Check φMq ≥ Mu  (φ = 0.75) ; Tb = lực căng trước Table J3.1
```
Nếu `pretensioned=False` → không cho phép thin plate (DG yêu cầu bu lông căng trước cho end plate chịu mômen) → NG.

## 5. Phía cột (`column_side.py`) khi dầm có end plate vào cánh cột

```
C1  Uốn cánh cột: tcf_req = sqrt( 1.11 φ Mnp / (φb Fyc Yc) )  (Yc không sườn)
      ratio = tcf_req / tcf ; nếu > 1 → cần sườn → tính lại với Yc có sườn
      Lực tương đương cánh cột: φRn_cf = φb Fyc Yc tcf² / (d − tbf)
C2  Chảy cục bộ bụng cột:
      φRn = φ Ct (6 kc + tbf + 2 tp) Fyc twc ; φ = 1.00 ; Ct = 0.5 nếu khoảng từ đỉnh cột tới mặt trên cánh dầm < dc, else 1.0
C3  Oằn nhàu bụng cột (nén):
      N = tbf + 2 w_f + 2 tp    [VERIFY DG4]
      φRn = φ 0.80 twc² [ 1 + 3 (N/dc) (twc/tcf)^1.5 ] sqrt(E Fyc tcf / twc)  (φ = 0.75); ×0.5 hệ số đầu cột theo J10.3
C4  Oằn nén bụng cột (J10.5): chỉ khi hai phía có lực nén đối nhau (with_opposite_beam) hoặc `always_check_web_buckling`
      φRn = φ 24 twc³ sqrt(E Fyc) / h ; φ = 0.90
C5  Sườn liên tục: Fsu = Ffu − min(φRn_C1, φRn_C2, φRn_C3, φRn_C4) > 0 → thiết kế sườn theo 03 §F (J10.8)
      và tính lại C1 với Yc có sườn
C6  Panel zone: Vu = Σ Ffu (cùng chiều) − Vcol ; J10.6 ; nếu NG → doubler
C7  Bu lông ép mặt trên cánh cột (Bước 10)
```

## 6. End-plate splice (BS `beam_splice` loại end plate, `tapered_splice`)
- Như §4 nhưng không có phía cột; kiểm tra **cả hai bản** (hai phía có thể khác bề dày/ vật liệu). Y cho cả hai bản bằng cùng công thức cấu hình.
- Bu lông dùng chung → Mnp một lần.
- Tapered: dùng tiết diện tại mặt nối (TaperedI.at(x_splice)); d, tbf, góc cánh nghiêng → lực cánh có thành phần vuông góc bản: `Ffu_normal = Ffu cos(β)` với β góc cánh so với pháp tuyến bản; thành phần tiếp tuyến cộng vào cắt bu lông.

## 7. Haunched beam (BCF `haunched`, `haunched_opposite`, BS `apex_haunched`)
- Haunch: tấm/ WT hàn dưới cánh dưới dầm, chiều cao tổng tại mặt cột `d_h`, chiều dài `L_h`, góc haunch `α_h`.
- End plate theo tiết diện tổng `d_h`; hàng bu lông có thể nhiều hơn (MRE) — cho phép người dùng khai báo `rows` tùy ý (Y tổng quát chỉ khi cấu hình chuẩn; tùy biến → dùng cách "bolt-row group" đơn giản: Mn = Σ 2 Pt h_i với kiểm tra bản bằng T-stub tương đương mỗi hàng (EN-style) — **tùy chọn**, mặc định chỉ cho các cấu hình chuẩn).
- Check thêm: cánh haunch chịu nén `Fh = Mu/d_h / cos α_h`: bản cánh haunch J4.4 / local buckling (b/t ≤ 0.56√(E/Fy)), hàn haunch–dầm (cắt dọc truyền `Fh sinα`), bụng haunch cắt, cân bằng lực tại đầu mút haunch (lực tập trung vào cánh dưới dầm → J10.2/J10.3 của dầm, sườn dầm tại đầu haunch nếu cần).

## 8. Knee — tapered beam to tapered column (BCF `tapered_knee`)
- Hình học: cột tapered (d_c tại đỉnh), kèo (rafter) tapered nghiêng α so với phương ngang, bản đầu nằm theo mặt cánh cột (đứng) như hình RAM; tùy chọn `plate_orientation="vertical"|"horizontal"|"mitred"`.
- Biến đổi nội lực kèo (trục kèo: N_r, V_r, M_r) về hệ trục bản đầu (pháp tuyến n, tiếp tuyến t):
  ```
  góc giữa trục kèo và pháp tuyến bản: φ_p = α (vertical plate)
  N_n = N_r cos φ_p − V_r sin φ_p      (kéo +, vuông góc bản)
  V_t = N_r sin φ_p + V_r cos φ_p      (song song bản → cắt bu lông)
  M   = M_r (không đổi, lấy tại tâm bản)
  ```
- Chiều cao tiết diện kèo đo theo bản: `d_p = d_r / cos α` ; tbf_p = tbf / cos α ; các h_i đo dọc bản.
- Áp dụng §4 với d → d_p, cộng lực N_n theo tùy chọn axial.
- Cột: vì đỉnh cột có bản nắp/ cánh kéo kèo dẫn lực vào cột ở vùng đầu cột → Ct = 0.5, J10.3 hệ số đầu, panel zone tam giác/ tứ giác: dùng J10.6 với dc tại đỉnh; sườn chéo (diagonal stiffener) tùy chọn: lực sườn chéo `Fd = (Vu_pz − φRn_pz)/cos θ_d`, check J4.4 + hàn.
- Cảnh báo: DG4/DG16 không trực tiếp bao quát knee nghiêng → báo cáo ghi "extended application of DG16 procedure" (giống RAM).

## 9. Apex (BS `apex`)
- Hai kèo đối xứng nghiêng α; bản đầu nằm theo mặt phân giác (đứng).
- Biến đổi như §8 cho mỗi phía; bu lông chung; kiểm tra bản như splice (§6).
- Lực dọc kèo (thường nén) giảm lực kéo bu lông — chỉ lấy có lợi nếu `use_axial_relief=True` (mặc định False → bỏ qua phần có lợi).

## 10. Check list tổng (ID)

`bolt_tension_rupture_no_prying`, `bolt_tension_with_prying` (thin), `bolt_shear`, `bolt_bearing_end_plate`, `bolt_bearing_column_flange`, `end_plate_thickness_thick_plate`, `end_plate_flexural_yielding`, `end_plate_shear_yield_ext`, `end_plate_shear_rupture_ext`, `stiffener_thickness`, `stiffener_local_buckling`, `stiffener_length`, `stiffener_welds`, `weld_beam_flange`, `weld_web_tension`, `weld_web_shear`, `col_flange_bending`, `col_web_local_yielding`, `col_web_crippling`, `col_web_compression_buckling`, `continuity_plate_*`, `panel_zone_shear`, `doubler_*`, detailing: `pfo_min` (≥ db + 1/2 in, DG4 bảng khoảng tối thiểu; [VERIFY]), `pfi_min`, `g_min` (lắp cờ lê), `g_max` (≤ bbf), `bp ≤ bbf + 25 mm` (DG4 khuyến nghị bp ≤ bbf + 1 in) [VERIFY], `de_min` (Table J3.4).

## 11. Ví dụ đối chiếu bắt buộc (test)
- DG4 Example 4E (non-seismic, LRFD) và 4ES, 8ES → so db_req, tp_req, φMnp, column side (sai số ≤1%).
- DG16 Example 2-bolt flush và 4-bolt flush.
- Người dùng nhập số liệu ví dụ từ PDF vào `tests/data/dg4_examples.yaml` (AI tạo sẵn khung YAML với các trường cần điền, và test sẽ `skip` nếu chưa có số liệu → không fail giả).
