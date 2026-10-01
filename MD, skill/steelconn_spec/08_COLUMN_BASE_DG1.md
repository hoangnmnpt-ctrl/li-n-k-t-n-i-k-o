# 08 — CHÂN CỘT (CB), CHÂN CỘT CÓ GIẰNG, ĐẦU CỘT (CC)

Nguồn: AISC Design Guide 1, 2nd ed. (2006, Fisher & Kloiber) — Base Plate and Anchor Rod Design; AISC 360-10 J8, J9, J3 (neo = threaded parts); ACI 318-11 Appendix D (tùy chọn). Module `connections/base_plate/`.

## 1. Input (JSONC minh họa — bỏ comment khi dùng thật)

```jsonc
"column_base": {
  "plate": {"N": 450, "B": 400, "tp": 30, "material": "A36"},
  "pedestal": {"N2": 600, "B2": 600, "fc": 25, "grout_t": 50},
  "anchors": {"grade": "F1554-36", "d": 24, "n_x": 2, "n_y": 2, "edge_x": 50, "edge_y": 50,
              "layout": "4_corner" , "washer": "plate", "embedment": 400},
  "weld_column_plate": {"flange": 8, "web": 6, "type": "fillet_all_around"},
  "shear_transfer": "friction" ,           // "friction" | "anchor_bolts" | "shear_lug"
  "shear_lug": null,
  "stiffeners": null
}
```
Hướng mômen: `M_major` (quanh trục mạnh cột, uốn theo phương N), `M_minor` (tùy chọn — nếu ≠ 0 → phương pháp biaxial đơn giản: kiểm tra độc lập hai phương + WARN, hoặc phương pháp số §5).

## 2. Nén đúng tâm — DG1 §3.1 (LRFD; ASD dùng Ω)

```
fp,max = φc 0.85 f'c sqrt(A2/A1)  ;  sqrt(A2/A1) ≤ 2 ;  φc = 0.65   (J8)
A1_req = Pu / fp,max  → check A1 = B N ≥ A1_req      → "concrete_bearing"
m  = (N − 0.95 d)/2
n  = (B − 0.80 bf)/2
X  = [ 4 d bf / (d + bf)² ] · Pu / (φc Pp) ;  Pp = 0.85 f'c A1 sqrt(A2/A1)
λ  = 2 sqrt(X) / (1 + sqrt(1 − X)) ≤ 1
λn' = λ sqrt(d bf) / 4
l  = max(m, n, λn')
tp_req = l sqrt( 2 Pu / (0.90 Fy B N) )              → "base_plate_bending_compression"
Cột HSS: m = (N − 0.95 D)/2 ; n = (B − 0.95 B_hss)/2 (chữ nhật) ; tròn: m = n = (N − 0.80 D)/2 [VERIFY DG1 Table]
```

## 3. Nén + mômen — DG1 §3.3 (phương pháp ứng suất đều — Uniform bearing, mặc định giống DG1)

```
e = Mu / Pu
qmax = fp,max · B
e_crit = N/2 − Pu/(2 qmax)
(a) e ≤ e_crit (mômen nhỏ, không kéo neo):
     Y = N − 2e ; q = Pu / Y
     Check: q ≤ qmax
(b) e > e_crit (mômen lớn, neo chịu kéo):
     f = khoảng từ tâm bản tới tâm neo chịu kéo (= N/2 − edge_x)
     Điều kiện có nghiệm: (f + N/2)² ≥ 2 Pu (e + f)/qmax   (nếu không → tăng N)  → "base_plate_size_moment"
     Y = (f + N/2) − sqrt( (f + N/2)² − 2 Pu (e + f)/qmax )
     Tu = qmax Y − Pu     (tổng lực kéo neo)
Bản đế — phía nén:
     Y ≥ m:  tp_req = 1.5 m sqrt( fp / Fy )                    (fp = q/B)
     Y < m:  tp_req = 2.11 sqrt( fp Y (m − Y/2) / Fy )
Bản đế — phía kéo (nếu Tu > 0):
     x = f − d/2 + tf/2   (khoảng từ neo tới tâm cánh cột)
     tp_req = 2.11 sqrt( Tu x / (B Fy) )
Lấy max các tp_req                                            → "base_plate_bending_moment"
```
Tùy chọn `bearing_distribution="uniform"(DG1)|"triangular"`: triangular dùng phân bố tam giác cổ điển (tương thích biến dạng) — không mặc định.

## 4. Kéo thuần (nhổ) — DG1 §3.2

- Lực mỗi neo `Tu/n_anchor` (neo đối xứng quanh cột) ; bản chịu uốn: đường chảy dẻo 45° từ neo tới cánh/ bụng cột → `b_eff = 2 × khoảng cách neo–mặt cột` ; `Mu_pl = T_anchor × khoảng cách tới mặt hàn` ; `tp_req = sqrt(4 Mu_pl/(0.9 Fy b_eff))`.
- Hàn cột–bản chịu `Tu` (mỗi đường hàn nhận phần theo vị trí neo).

## 5. Neo (anchor rods)

```
Kéo:  φRn = 0.75 · 0.75 Fu · Ab       (J3 Table J3.2 threaded parts: Fnt = 0.75 Fu)
Cắt:  φRn = 0.75 · 0.40 Fu · Ab (ren trong mặt cắt) ; nếu lớp vữa dày > 50 mm (2 in) → neo chịu uốn (DG1 §3.5) → tính thêm uốn neo nếu `anchor_bending=True`, ngược lại WARN
Kéo + cắt: J3.7
Lỗ bản đế cho neo: DG1 Table 2.3 (lỗ lớn: d + 5/16" … ) → washer plate bắt buộc kiểm tra kích thước & chiều dày
Bê tông (ACI 318-11 App. D) — module tùy chọn `aci_anchorage=True`:
  Nsa = Ase,N futa (steel) ; Ncb (breakout, ψ factors) ; Np = 8 Abrg f'c (pullout) ; Nsb (side-face blowout khi hef lớn & gần mép) ;
  Vsa, Vcb, Vcp ; tương tác N/φNn + V/φVn ≤ 1.2
  Nếu `aci_anchorage=False` → báo cáo in "Concrete anchorage not checked (ACI 318 App. D)" (status WARN).
```
Phương án chịu cắt (`shear_transfer`):
- `friction`: `φVn = 0.75 · μ · Pu` với μ = 0.55 (thép trên vữa, DG1) [VERIFY]; chỉ khi Pu nén.
- `anchor_bolts`: phân đều cho neo (chỉ các neo có long đen hàn hoặc giả thiết 2 neo làm việc — tùy chọn `n_anchor_shear="all"|"2"`).
- `shear_lug`: bản chắn cắt: ép mặt bê tông `φ0.8 f'c A_lug` (φ=0.60? DG1 dùng φ0.60 × 1.3? [VERIFY]), uốn bản chắn (công-xôn, momen tại mặt đáy bản đế với tay đòn G + (H−G)/2), hàn chắn cắt vào bản đế (cắt + uốn).

## 6. Chân cột có giằng (CB `base_one_brace`, `base_two_braces`)
- Gusset hàn lên bản đế và cánh/bụng cột; lực giằng P → thành phần đứng (P cosθ đứng, dấu) cộng vào Pu cột, thành phần ngang cộng vào lực cắt đáy; mômen lệch tâm do điểm làm việc (work point) không trùng tâm bản đế → cộng vào Mu.
- Gusset: như 06 §2 với giao diện gusset–bản đế (thay cho gusset–dầm) và gusset–cột. UFM special case: dầm → bản đế: eb = 0 (work point tại mặt bản đế) [tùy chọn `work_point="base_plate_top"|"column_centerline_at_grout"`].
- Bản đế: tính lại §3 với (Pu, Mu, Vu) tổng hợp; neo nhổ do thành phần đứng khi giằng kéo.
- `two_braces`: hai gusset hai phía (V ngược), cộng lực; kiểm tra cả trường hợp một kéo một nén.

## 7. Đầu cột — Column cap (CC)
- Bản đỉnh (cap plate) hàn vào cột, dầm liên tục đặt lên, bắt bu lông.
- Nén: J7 bearing (khi mài phẳng) hoặc hàn đủ chịu nén; bản đỉnh: ép mặt cục bộ, uốn phần nhô (công-xôn, tay đòn từ mép cột), chiều dày tối thiểu `tp ≥ tf_col` khuyến nghị (WARN).
- Nhổ (kéo): bu lông kéo + prying (03 §E) với bản đỉnh và cánh dưới dầm (lấy tp nhỏ hơn ↔ phân tích T-stub hai phía), hàn cột–bản chịu kéo.
- Ngang: bu lông cắt, bearing.
- Dầm: J10.2 với `lb = chiều dài tiếp xúc dọc dầm (= d_col hoặc bề rộng cột theo phương dầm) + 2·(2.5 tp)` khi `spread_through_cap_plate=True`, mặc định False (lb = chiều dài tiếp xúc, an toàn), J10.3, J10.4 (nếu cánh dưới dầm không được giằng tại đó → WARN + tính), sườn dầm theo J10.8 nếu cần (sườn thẳng hàng cánh cột).
- CCB: + gusset (06 §6).

## 8. Check IDs
`concrete_bearing`, `base_plate_bending_compression`, `base_plate_bending_moment`, `base_plate_bending_tension`, `base_plate_size_moment`, `anchor_tension`, `anchor_shear`, `anchor_tension_shear`, `anchor_concrete_*` (tùy chọn), `shear_friction`, `shear_lug_*`, `weld_column_base_plate` (kéo/ nén/ cắt/ mômen — elastic trên chu vi hàn), `washer_plate`, `cap_plate_*`, `beam_web_local_yield_cap`, `beam_web_crippling_cap`, `beam_sidesway_web_buckling_cap`, detailing (khoảng mép neo ≥ DG1 Table 2.x / ACI, khoảng giữa neo, bản đế nhô ≥ 25 mm quanh cột).

## 9. Ví dụ đối chiếu
DG1 2nd ed.: Example 4.1 (axial, pedestal lớn), 4.3 (axial, A2/A1 nhỏ), 4.7 (small moment), 4.8 (large moment) — [VERIFY số hiệu theo PDF]; sai số ≤1%.
