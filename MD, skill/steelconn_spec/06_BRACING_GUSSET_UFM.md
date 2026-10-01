# 06 — LIÊN KẾT GIẰNG: GUSSET, UFM, CHEVRON, X, GIẰNG NGANG

Nguồn: AISC Manual 14th Part 13, Design Guide 29 (Vertical Bracing Connections — Analysis and Design), AISC 360-10 J & E. Module `connections/brace/`.

## 1. Brace-to-gusset (đầu giằng) — `brace_end.py`

Loại tiết diện giằng và kiểu nối (tùy chọn `brace_end_type`):

| Giằng | Kiểu nối | Checks riêng |
|---|---|---|
| W | bản nối cánh (flange plates) + bản bụng, hoặc claw angles | bu lông, block shear cánh W, bản nối kéo/nén, shear lag U (D3.1) |
| 2L (lưng đối lưng) | bắt bu lông/hàn trực tiếp vào gusset | U theo Table D3.1 case 2/8, block shear góc, bu lông cắt kép |
| L đơn | bu lông/hàn | U, lệch tâm |
| WT | hàn/ bu lông thân T vào gusset | U |
| HSS (khe) | gusset luồn vào khe ống, hàn 4 đường dọc | shear lag U = 1 − x̄/l (D3.1 case 5/6), đứt tiết diện thực tại khe (An = Ag − 2 t (tg + gap)), hàn dọc, gusset chảy/ đứt, cắt ống (shear rupture thành ống 0.6 Fu 4 Lw t) |
| HSS (bản đầu/ bản chữ thập) | bản hàn nắp + bản nối | bản nắp uốn, hàn chu vi, K1 |

Checks chung: `brace_tension_yield` (J4.1 / D2), `brace_tension_rupture` (Ae = U An), `brace_block_shear`, bu lông (cắt, bearing trên giằng và gusset), hàn (IC hoặc hàn đồng tâm J2.4(c)), `brace_connection_compression` (J4.4 cho đoạn nối).

## 2. Gusset — `gusset.py`

### 2.1 Whitmore
```
Lw = 2 L_conn tan30° + g_width     (bu lông: g_width = khoảng giữa hai đường bu lông ngoài cùng; hàn: bề rộng giằng hoặc khoảng hai đường hàn)
L_conn = chiều dài từ hàng bu lông đầu tới hàng cuối (hoặc chiều dài hàn)
Cắt Lw bởi mép gusset / phần nằm trên cấu kiện khác → phần nằm ngoài gusset bị trừ; phần đi vào bụng dầm/ cột được phép tính với chiều dày & Fy của phần đó (tùy chọn `whitmore_into_members=True`)
Aw = Lw_eff tg
Kéo:   φRn = 0.90 Fy Aw (yield) ; rupture 0.75 Fu Aw_net
Nén:   J4.4 với KL/r:
         r = tg/√12
         L = L_avg = (L1 + L2 + L3)/3  (Thornton) hoặc L_mid (tùy chọn `gusset_buckling_length="thornton_avg"|"L1_center"`)
         K = 0.5 (gusset góc nối 2 cạnh, compact), 0.65 (chevron/ single-edge, có sườn), 1.2 (gusset góc có cạnh tự do dài, DG29/ Dowswell) — theo settings.gusset_K
         KL/r ≤ 25 → Pn = Fy Aw ; else E3
```
Hình học L1, L2, L3: khoảng từ 3 điểm (hai đầu và giữa của Whitmore section) theo phương giằng tới mép gusset đối diện (cánh dầm/ cột). Implement bằng hình học đa giác (shapely-like tự viết: giao tia với đa giác).

### 2.2 Block shear gusset (J4.3) theo đường bu lông/ hàn của giằng.
### 2.3 Gusset mép tự do: `L_fg/tg ≤ 0.75 sqrt(E/Fy)` (Manual Part 13 khuyến nghị cho mép tự do không có sườn) → WARN nếu vượt, cho phép sườn mép.
### 2.4 Tiết diện gusset tại các giao diện (gusset–dầm, gusset–cột): chịu (V, H, M) → ứng suất: `fv = V/(L tg)`, `fa = H/(L tg)`, `fb = 6M/(L² tg)`; check chảy: von Mises hoặc tương tác Manual: (fa + fb)/(φFy) + ... ; implement: kiểm riêng shear yield (J4.2), normal yield (fa+fb ≤ φFy), tương tác `(fn/φFy)² + (fv/φ0.6Fy)² ≤ 1` [DG29 khuyến nghị — VERIFY].

## 3. Uniform Force Method (UFM) — `ufm.py` (Manual 14th Part 13)

Ký hiệu: θ góc giằng so với phương đứng (UFM chuẩn dùng θ so với phương đứng — lưu ý đổi từ input `theta` đo từ phương ngang: θ_ufm = 90° − theta), `eb = db/2` (nửa chiều cao dầm), `ec = dc/2` (cột trục mạnh, gusset vào cánh) hoặc `ec = 0` (gusset vào bụng cột), α = khoảng từ mặt cột tới trọng tâm liên kết gusset–dầm, β = khoảng từ mặt cánh dầm tới trọng tâm liên kết gusset–cột.

```
Điều kiện UFM chuẩn:  α − β tanθ = eb tanθ − ec
Chọn β (thực tế: β = β̄ theo hình học) → α = eb tanθ − ec + β tanθ
r = sqrt( (α + ec)² + (β + eb)² )
Vc = (β / r) P      Hc = (ec / r) P       (giao diện gusset–cột)
Vb = (eb / r) P     Hb = (α / r) P        (giao diện gusset–dầm)
Kiểm: Hb + Hc = P sinθ ; Vb + Vc = P cosθ
Dầm–cột (liên kết dầm vào cột): nhận thêm Vb (cộng vào phản lực dầm Rb) và lực dọc Ab ± Hc (Ab = lực dọc dầm từ phân tích)
```
**Khi α_actual ≠ α_ideal** (hình học không cho phép): mômen phụ
```
Mb = Vb (α_actual − α)     tại giao diện gusset–dầm   (special case 1 hoặc tổng quát)
Mc = Hc (β_actual − β)     tại giao diện gusset–cột
```
Tùy chọn `ufm_case`:
- `"general"` (mặc định): chọn β = β_actual, tính α; nếu |α − α_actual| > tol → Mb.
- `"special_case_1"`: gusset–cột chịu toàn bộ Vc hoặc chuyển ΔVb sang liên kết dầm–cột (Manual Part 13 SC1: loại bỏ Vb khỏi gusset–dầm, cộng vào dầm–cột) [VERIFY chiều chuyển].
- `"special_case_2"`: ΔVb chuyển để giảm lực trên liên kết dầm–cột (dùng khi dầm–cột yếu) — Mb = ΔVb α.
- `"special_case_3"`: gusset chỉ nối vào dầm (không nối cột), ec và β = 0 → Hc = Vc = 0 (dùng cho gusset trên cánh dầm, K-brace ở dầm).
- `"kl_method"` / `"parallel"`: phân chia đơn giản (không mặc định).

Lực thiết kế hàn gusset: nhân `weld_ductility_factor_UFM = 1.25` (Manual Part 13: "the larger of peak stress and 1.25 × average stress") → implement: `f_design = max(f_peak, 1.25 f_avg)` dọc chiều dài hàn khi có mômen.

## 4. CBB — Column–Beam–Brace
- `one_brace`: UFM §3. Joint gồm: brace_end (§1) + gusset (§2) + gusset–beam interface (hàn gusset vào cánh dầm hoặc bắt qua góc) + gusset–column interface (hàn / bu lông qua góc kép / bản đầu) + beam–column connection (shear tab, double angle, end plate) chịu (Rb + Vb, Ab ± Hc) + checks cột (J10 do Hc tại cánh cột: J10.1 nếu kéo; bụng cột nếu gusset vào bụng) + checks dầm (J10.2/J10.3 dưới Vb; bụng dầm cắt với Hb + mômen Mb).
- `two_braces`: hai gusset trên và dưới dầm (phía trên dầm và phía dưới dầm tại cùng cột), UFM riêng cho mỗi gusset; liên kết dầm–cột nhận tổng Vb1 − Vb2 và Hc1 + Hc2 (theo dấu); cột kiểm tra J10 với tổng lực.
- `four_braces`: hai dầm trái/phải, 4 gusset; cột nhận tổng hợp; bụng cột chịu cắt panel do cặp Hc (J10.6) khi các Hc ngược chiều.
- `y_brace`: gusset chỉ vào cột (không có dầm): lực tại giao diện gusset–cột = P sinθ, P cosθ + mômen `M = P · e` (e = khoảng từ đường tác dụng giằng tới trọng tâm mối hàn gusset–cột). Hàn: elastic + ductility factor.
- `k_brace`: hai giằng giao tại cột (không có dầm), gusset chung: tổng lực hai giằng (cân bằng thành phần đối xứng), mômen do lệch.

## 5. CVR — Chevron (giằng chữ V / V ngược vào giữa dầm)
- Gusset chỉ nối vào dầm (UFM special case 3 cho mỗi giằng); với 2 giằng đối xứng: 
```
H = (P1 + P2) sinθ   (khi P1 kéo, P2 nén → cộng thành lực ngang lên gusset–dầm)
V = (P1 − P2) cosθ   (lực không cân bằng đứng)
M = H · eb  (eb = d_beam/2) + mômen do lệch điểm giao tại mặt cánh dầm
```
- Hàn gusset–dầm: phân bố lực từ (V, H, M) theo phương pháp "hai nửa gusset" (Manual Part 13 Ex chevron): mỗi nửa chịu lực tương ứng một giằng; tính hàn bằng elastic với 1.25.
- Dầm: J10.2, J10.3 dưới phần nén; sườn dầm tại mép gusset nếu cần (J10.8); cảnh báo "beam flexure/ unbalanced load design is outside connection scope" (xuất lực để người dùng check dầm).
- `chevron_four`: gusset trên và dưới dầm (giằng hai tầng) — kiểm tra hai gusset và dầm chịu tổng.

## 6. CCB — Column cap – brace
- Dầm liên tục trên đỉnh cột + gusset bên dưới dầm nối vào cột và bản đỉnh; UFM với cột có bản đỉnh (ec, eb tương ứng); cap plate chịu thêm lực đứng Vb.

## 7. VXB — Vertical X brace (giao điểm X)
- Giằng liên tục + hai nửa giằng đứt nối vào gusset trung tâm (hoặc cả hai giằng đứt).
- Gusset: kiểm tra Whitmore cho từng giằng, block shear, và tiết diện gusset tại giao cắt với giằng liên tục (chịu toàn bộ lực của giằng đứt khi cả hai đứt).
- Bản nối (splice) nếu giằng liên tục gồm 2L: bản đệm (filler/stitch).

## 8. Giằng ngang HCBB / HBBB / HXB
- Gusset nằm ngang, bắt bu lông (hoặc hàn) vào cánh dưới/trên dầm (và đôi khi vào cột qua bản góc).
- Lực giằng P chia vào các dầm theo hình học (tỷ lệ độ cứng của liên kết gusset–dầm): mặc định **phân bố theo UFM 2D trong mặt phẳng ngang** coi hai dầm như "dầm" và "cột" của UFM (eb = ec = khoảng từ trục dầm tới mép cánh bắt gusset, thường = bf/2 hoặc 0 nếu bắt dưới cánh) → tùy chọn `horizontal_distribution="ufm"|"stiffness"|"user"`.
- `front_beam_only` / `right_beam_only` / `girder_only`: gusset chỉ nối một dầm → toàn bộ P + mômen lệch tâm vào liên kết đó (bu lông IC trên cánh dầm).
- Checks cánh dầm: bu lông bearing trên cánh, block shear cánh, F13.1 cánh dầm có lỗ (bù trừ), cánh dầm uốn ngang cục bộ (WARN).
- `HXB`: như VXB trong mặt ngang.

## 9. CB with braces (chân cột có giằng) → xem 08 §6.

## 10. Check IDs
`brace_*`, `gusset_whitmore_yield`, `gusset_whitmore_rupture`, `gusset_buckling`, `gusset_block_shear`, `gusset_free_edge`, `gusset_interface_beam_{shear,normal,interaction}`, `gusset_interface_column_*`, `weld_gusset_beam`, `weld_gusset_column`, `bolt_gusset_*`, `ufm_equilibrium` (nội bộ, ratio = sai số/ tol), `beam_web_local_yield_under_gusset`, `beam_web_crippling_under_gusset`, `column_*`, `beam_to_column_connection_*` (tái sử dụng C1–C4 với lực UFM).

## 11. Ví dụ đối chiếu
- Manual 14th Part 13 Example 13-1 (UFM general), 13-2 (special case 1), 13-3 (special case 2), 13-6/13-7? (chevron) — số hiệu ví dụ [VERIFY] theo bản Manual người dùng có.
- DG29 ví dụ gusset buckling.
