# 03 — THƯ VIỆN TRẠNG THÁI GIỚI HẠN (AISC 360-10 + Manual 14th)

Quy ước chung cho MỌI hàm trong `limit_states/`:

```python
def ls_xxx(..., method: Literal["LRFD","ASD"], code=AISC360_10) -> CheckResult  # hoặc trả (Rn, phi, Omega)
```

- Mỗi hàm tính `Rn` (nominal), rồi `available = phi*Rn` (LRFD) hoặc `Rn/Omega` (ASD) qua `code.available(Rn, key)`.
- Bảng φ/Ω đặt trong `codes/aisc360_10.py`, key = mã điều khoản (ví dụ `"J3.6"`).
- Ký hiệu: `Ab` diện tích danh nghĩa thân bu lông `π d²/4`; `t` chiều dày; `Fy, Fu` vật liệu phần tử đang xét.

## A. Bảng φ / Ω

| Key | Trạng thái giới hạn | φ | Ω |
|---|---|---|---|
| J2.4 | Hàn góc / PJP (weld metal) | 0.75 | 2.00 |
| J2.4-BM-shear-yield | Kim loại cơ bản – chảy cắt | 1.00 | 1.50 |
| J2.4-BM-shear-rupt | Kim loại cơ bản – đứt cắt | 0.75 | 2.00 |
| J2.4-BM-tension | Kim loại cơ bản kéo/nén (PJP) | 0.90 | 1.67 |
| J3.6 | Bu lông kéo / cắt | 0.75 | 2.00 |
| J3.7 | Kéo + cắt đồng thời (bearing) | 0.75 | 2.00 |
| J3.8-STD | Slip (lỗ STD, SSL ⊥ lực) | 1.00 | 1.50 |
| J3.8-OVS | Slip (OVS, SSL ∥ lực) | 0.85 | 1.76 |
| J3.8-LSL | Slip (LSL) | 0.70 | 2.14 |
| J3.10 | Ép mặt / xé (bearing, tearout) | 0.75 | 2.00 |
| J4.1-yield | Chảy kéo | 0.90 | 1.67 |
| J4.1-rupture | Đứt kéo | 0.75 | 2.00 |
| J4.2-yield | Chảy cắt | 1.00 | 1.50 |
| J4.2-rupture | Đứt cắt | 0.75 | 2.00 |
| J4.3 | Block shear | 0.75 | 2.00 |
| J4.4 | Nén bản mã | 0.90 | 1.67 |
| FLEX-yield | Uốn bản (Manual Part 9) | 0.90 | 1.67 |
| FLEX-rupture | Đứt uốn (Manual Part 9) | 0.75 | 2.00 |
| J7 | Ép mặt tiếp xúc (bearing on milled surface) | 0.75 | 2.00 |
| J8 | Ép mặt bê tông | 0.65 | 2.31 |
| J10.1 | Uốn cục bộ cánh | 0.90 | 1.67 |
| J10.2 | Chảy cục bộ bụng | 1.00 | 1.50 |
| J10.3 | Oằn nhàu bụng (crippling) | 0.75 | 2.00 |
| J10.4 | Oằn bụng do lắc ngang | 0.85 | 1.76 |
| J10.5 | Oằn nén bụng | 0.90 | 1.67 |
| J10.6 | Cắt vùng panel | 0.90 | 1.67 |
| G2.1 | Cắt bụng (Cv=1, h/tw ≤ 2.24√(E/Fy)) | 1.00 | 1.50 |
| G2.1-other | Cắt bụng khác | 0.90 | 1.67 |
| E | Nén cấu kiện | 0.90 | 1.67 |
| F | Uốn cấu kiện | 0.90 | 1.67 |
| K | HSS connections | theo từng mục K (thường 0.90/1.67; punching 0.95/1.58) | |
| DG4-bolt | Bolt rupture trong end plate | 0.75 | 2.00 |
| DG4-plate | Chảy uốn end plate / cánh cột | 0.90 | 1.67 |

## B. Bu lông (`bolt_ls.py`)

### B1. Kéo / cắt — J3.6
```
Rn = Fn * Ab                         (J3-1)
Fn = Fnt (kéo) | Fnv (cắt, theo N/X)
Cắt: nhân với số mặt cắt ns (single/double shear)
```

### B2. Kéo + cắt (bearing-type) — J3.7
```
LRFD:  F'nt = 1.3 Fnt − Fnt/(φ Fnv) * frv ≤ Fnt       (J3-3a), φ = 0.75
ASD:   F'nt = 1.3 Fnt − Ω Fnt/Fnv * frv ≤ Fnt          (J3-3b), Ω = 2.00
frv = ứng suất cắt yêu cầu = Vu_per_bolt / Ab
Rn = F'nt * Ab ; nếu frv ≤ 0.30 φFnv (LRFD) hoặc tổng ≤ 30% thì bỏ qua tương tác (J3.7 cho phép)
```

### B3. Slip-critical — J3.8 (360-10: kiểm tra ở mức strength)
```
Rn = μ Du hf Tb ns                    (J3-4)
μ = 0.30 (Class A) | 0.50 (Class B)
Du = 1.13
hf = 1.0 (không filler hoặc 1 filler, hoặc filler đã phát triển), 0.85 (≥2 filler)
Tb: Table J3.1 ; ns: số mặt trượt
Kéo đồng thời (J3.9):
  LRFD ks = 1 − Tu/(Du Tb nb)         (J3-5a)
  ASD  ks = 1 − 1.5 Ta/(Du Tb nb)     (J3-5b)
Rn_eff = ks * Rn
```
SC bolt vẫn phải check bearing/tearout và shear (J3.8 bắt buộc).

### B4. Ép mặt & xé tại lỗ — J3.10 (360-10 dạng gộp)
```
Lỗ STD, OVS, SSL (mọi phương), LSL // lực:
  deformation considered: Rn = 1.2 lc t Fu ≤ 2.4 d t Fu     (J3-6a)
  not considered:          Rn = 1.5 lc t Fu ≤ 3.0 d t Fu     (J3-6b)
LSL ⊥ lực:                 Rn = 1.0 lc t Fu ≤ 2.0 d t Fu     (J3-6c)
lc = khoảng cách thông thủy theo phương lực: mép lỗ tới mép vật liệu (bu lông cuối) hoặc tới mép lỗ kế (bu lông trong)
     lc_edge = Le − dh/2 ; lc_inner = s − dh
```
Ép mặt kiểm tra cho **mọi phần được nối** (bản, bụng dầm, cánh cột…), lấy nhỏ nhất. Sức chịu một bu lông = min(shear, bearing/tearout các lớp). Bolt group: `Rn_group = Σ min(...)` theo từng bu lông (bu lông mép và bu lông trong khác lc), sau đó nhân `C/n` khi có lệch tâm (Manual Part 7 cho phép dùng giá trị nhỏ nhất × C, là cách an toàn; RAM dùng cách này — ghi rõ trong báo cáo).

### B5. Lực kéo bu lông nghiêng/ phương lực tổng quát
Với lực nghiêng góc α so với phương cạnh: phân thành thành phần dọc để tính lc theo phương lực tổng (lc đo dọc phương lực). Implement: `lc_along_direction(hole_xy, edge_polygon, direction)`.

## C. Hàn (`weld_ls.py`)

### C1. Hàn góc — J2.4 (Table J2.5)
```
Rn = Fnw Awe                         (J2-4)
Fnw = 0.60 FEXX (1.0 + 0.50 sin^1.5 θ)   (J2-5) nếu use_directional_strength, else 0.60 FEXX
Awe = 0.707 w L (hàn góc cạnh bằng)
Kim loại cơ bản (J2-2): Rn = FnBM ABM
   chảy cắt: 0.60 Fy t L (φ1.00)
   đứt cắt:  0.60 Fu t L (φ0.75)
```
Công thức nhanh (Manual Part 8, LRFD, E70): `φRn = 1.392 D L` (kip, D = số 1/16 in, L in) → trong SI: `φRn = 0.75*0.6*482*0.707*w*L`.

Check kim loại cơ bản theo chiều dày tối thiểu (Manual Part 9): `t_min = 6.19 D / Fu` (1 mặt hàn, E70, ksi, in) hoặc `3.09 D / Fu` (2 mặt đối xứng) — implement dưới dạng tổng quát: `0.6 Fu t ≥ Fnw*0.707*w` (φ như nhau 0.75).

### C2. Giới hạn kích thước hàn (J2.2b, Table J2.4)

| t mỏng hơn (in / mm) | w_min |
|---|---|
| ≤ 1/4 (6) | 1/8 (3) |
| 1/4 < t ≤ 1/2 (6–13) | 3/16 (5) |
| 1/2 < t ≤ 3/4 (13–19) | 1/4 (6) |
| > 3/4 (19) | 5/16 (8) |

w_max dọc mép: `t` nếu t < 6 mm; `t − 2 mm` (1/16 in) nếu t ≥ 6 mm. Chiều dài hiệu dụng tối thiểu 4w; hàn dọc cuối dải kéo: chiều dài ≥ khoảng cách giữa hai đường hàn; hệ số β chiều dài (J2-1) khi L > 100w: `β = 1.2 − 0.002 (L/w) ≤ 1.0`, L>300w → L_eff = 180w.

### C3. CJP: cường độ = kim loại cơ bản (Table J2.5) — check theo phần tử cơ bản (J4).
### C4. PJP: Table J2.1 chiều dày hiệu dụng; kéo ⊥ trục: `Rn = 0.60 FEXX Awe` (φ0.80, Ω1.88) và base metal `Fu ABM` (φ0.75).

### C5. Hàn nhóm lệch tâm: IC method (02 §4.6), cũng có elastic vector method.

### C6. Hàn chịu cắt + uốn (vd hàn bản mã vào cột): elastic vector: `fr = sqrt((fv)^2 + (fb + fa)^2)` trên đơn vị chiều dài; so với `φ Fnw 0.707 w` (có thể dùng hệ số hướng θ = atan theo vector).

## D. Phần tử liên kết (`element_ls.py`, `block_shear.py`)

```
J4.1 Kéo:  yield  Rn = Fy Ag ;  rupture Rn = Fu Ae ; Ae = U An, bản nối Ae = An ≤ 0.85 Ag  (J4-1, J4-2)
J4.2 Cắt:  yield  Rn = 0.60 Fy Agv ; rupture Rn = 0.60 Fu Anv     (J4-3, J4-4)
J4.3 Block shear:  Rn = 0.60 Fu Anv + Ubs Fu Ant ≤ 0.60 Fy Agv + Ubs Fu Ant   (J4-5)
     Ubs = 1.0 (ứng suất kéo đều), 0.5 (không đều: shear tab nhiều hàng, dầm cắt vát 2 hàng bu lông)
J4.4 Nén:  KL/r ≤ 25 → Pn = Fy Ag ; KL/r > 25 → Chapter E (E3), r = t/√12 cho bản chữ nhật
Uốn (Manual Part 9 — thành văn J4.5 ở 360-16, dùng như tham chiếu):
     yield   Mn = Fy Z   (φ0.90) ; Z = t d²/4
     rupture Mn = Fu Znet (φ0.75) ; implement tổng quát: Znet = t d²/4 − Σ_i (dh_net · t · |y_i|), y_i = tọa độ tâm lỗ so với trục giữa bản (một hàng lỗ đều)
     buckling bản mã có cope/ extended shear tab: Manual Part 9 classical plate buckling (xem F3)
Tương tác cắt–uốn của bản (Manual Part 10, extended shear tab): (Vr/Vc)² + (Mr/Mc)² ≤ 1.0
Tương tác kéo–uốn bản (H1 hoặc Manual Part 9):  Pr/Pc + Mr/Mc ≤ 1.0
```
Diện tích lỗ trừ (B4.3b): dùng `d_h + 2 mm`. Chuỗi zigzag: `+ s²/(4g)` cho mỗi đường chéo.

## E. Prying action — Manual 14th Part 9 (`prying.py`)

Áp dụng cho T-stub, góc chịu kéo, end plate hàng ngoài khi dùng phương pháp "thin plate".
```
b  = khoảng từ tâm bu lông tới mặt phần tử đỡ: T-stub b = (g − tw)/2 ; góc b = g − t/2 (g đo từ lưng góc) ; end plate b = pf (xem 05)
a  = khoảng từ tâm bu lông tới mép bản
b' = b − db/2
a' = min(a, 1.25 b) + db/2         (Manual 9-...)
ρ  = b'/a'
p  = chiều dài nhánh (tributary width) mỗi bu lông, ≤ s và ≤ ... (thường p ≤ 2b hoặc khoảng cách bu lông)
δ  = 1 − d'/p  ; d' = đường kính lỗ
B  = sức kéo khả dụng một bu lông (φrn hoặc rn/Ω)
tc = sqrt( 4.44 B b' / (p Fu) )   LRFD ; sqrt( 6.66 B b' / (p Fu) )  ASD   [Manual 14th dùng Fu]
α' = 1/(δ(1+ρ)) * [ (tc/t)² − 1 ]
Q  = 1                          nếu α' < 0
   = (t/tc)² (1 + δ α')         nếu 0 ≤ α' ≤ 1
   = (t/tc)² (1 + δ)            nếu α' > 1
Sức kéo khả dụng một bu lông kể prying: T_avail = B Q
t_min (không prying): t_min = sqrt( 4.44 T b' / (p Fu) ) (LRFD) với T = lực yêu cầu/bu lông
```
[VERIFY] Hằng số 4.44/6.66 là của Manual 14th (Fu). Manual 13th dùng Fy với 4.44 → kiểm tra đúng bản.

## F. Lực tập trung lên cấu kiện đỡ — J10 (`concentrated.py`)

```
J10.1 Flange local bending (kéo):  Rn = 6.25 Fyf tf²          (J10-1)
       nếu lực cách đầu cấu kiện < 10 tf → Rn × 0.5
       bỏ qua nếu bề rộng tải < 0.15 bf
J10.2 Web local yielding:
       khoảng cách tới đầu > d:  Rn = Fyw tw (5k + lb)         (J10-2)
       ≤ d:                       Rn = Fyw tw (2.5k + lb)       (J10-3)
       k = k_des ; lb = chiều dài chịu lực (end plate: lb = tfb + 2w + 2tp; theo DG4 dùng 6k + ... xem 05)
J10.3 Web crippling (nén):
       khoảng cách tới đầu ≥ d/2:
          Rn = 0.80 tw² [1 + 3(lb/d)(tw/tf)^1.5] sqrt(E Fyw tf / tw)             (J10-4)
       < d/2, lb/d ≤ 0.2:
          Rn = 0.40 tw² [1 + 3(lb/d)(tw/tf)^1.5] sqrt(E Fyw tf / tw)             (J10-5a)
       < d/2, lb/d > 0.2:
          Rn = 0.40 tw² [1 + (4 lb/d − 0.2)(tw/tf)^1.5] sqrt(E Fyw tf / tw)      (J10-5b)
J10.4 Web sidesway buckling: chỉ khi flange nén không được giằng — áp dụng cho dầm đỡ tải tập trung (BG, CC); J10-6/J10-7 [VERIFY]
J10.5 Web compression buckling (cặp lực nén hai phía):
       Rn = 24 tw³ sqrt(E Fyw) / h                                             (J10-8)
       cách đầu < d/2 → × 0.5 ; h = d − 2 k_des
J10.6 Panel zone web shear:
   không kể biến dạng dẻo vùng panel (panel_zone_inelastic=False):
       Pr ≤ 0.4 Pc:  Rn = 0.60 Fy dc tw                                       (J10-9)
       Pr > 0.4 Pc:  Rn = 0.60 Fy dc tw (1.4 − Pr/Pc)                          (J10-10)
   có kể:
       Pr ≤ 0.75 Pc: Rn = 0.60 Fy dc tw [1 + 3 bcf tcf² / (db dc tw)]          (J10-11)
       Pr > 0.75 Pc: Rn = 0.60 Fy dc tw [1 + 3 bcf tcf² / (db dc tw)] (1.9 − 1.2 Pr/Pc)  (J10-12)
   360-10: Pc = Py = Fy Ag (LRFD) ; Pc = 0.6 Py (ASD) ; Pr = lực dọc yêu cầu của cột
   Lực cắt panel: Vu = Σ Mu/(db − tfb) − Vcolumn (ghi rõ chiều: các mômen hai dầm cùng chiều quay cộng lại)
J10.7 Đầu hở của dầm/cột chịu lực tập trung: cần sườn toàn chiều cao — check "stiffener required" (NA/NG).
J10.8 Sườn (continuity plates) khi cần:
   lực sườn: Fsu = Ffu − min(φRn_J10.1, φRn_J10.2, φRn_J10.3, φRn_J10.5)
   bề rộng bs + tw/2 ≥ bf_beam/3 ; ts ≥ tf_beam/2 ; ts ≥ bs/16  [VERIFY 360-10: /16]
   chiều dài ≥ d/2 cho sườn nửa chiều cao (khi chỉ một phía chịu lực)
   check sườn như cột ngắn (J4.4, KL = 0.75h) với bụng tham gia 25tw (nội) / 12tw (đầu) — Manual/360-10 J10.8
   hàn sườn–cánh: phát triển lực Fsu (hoặc CJP), hàn sườn–bụng: truyền Fsu
Doubler plate (J10.9): khi panel NG; t_dp ≥ (Vu − φRn)/(φ 0.6 Fy dc) ; chiều dày tổng panel và độ mảnh doubler: (dz + wz)/90 là yêu cầu 341, không áp dụng; check hàn doubler truyền phần cắt của nó.
```

## G. Dầm cắt vát (coped beam) — Manual 14th Part 9 (`cope.py`)

```
Tiết diện tại cope: Snet, Znet của tiết diện chữ T (cắt cánh trên) hoặc chữ nhật (cắt cả hai)
Mômen tại mép cope: Mr = Vr * e
   e = c + setback      cho double angle / shear end plate / seat (điểm mômen 0 lấy tại mặt gối) — Manual Part 9 examples
   e = khoảng từ đường bu lông trên bụng dầm tới mép cope    cho single plate / single angle bắt bu lông vào bụng dầm   [VERIFY]
Chảy uốn: Mn = Fy Snet   (Manual 14th dùng Snet cho local buckling), φ0.90
Đứt uốn:  Mn = Fu Snet   φ0.75
Local buckling — cắt cánh trên (c ≤ 2d, dc ≤ d/2):
   Fcr = 26,210 ksi * (tw/ho)² * f * k  ≤ Fy        (Manual 9-6)  → 26,210 ksi = 180,700 MPa
   f = 2c/d                 (c/d ≤ 1.0)
     = 1 + c/d              (c/d > 1.0)
   k = 2.2 (ho/c)^1.65      (c/ho ≤ 1.0)
     = 2.2 ho/c             (c/ho > 1.0)
Cắt cả hai cánh (dc ≤ 0.2d, c ≤ 2d):
   Fcr = 0.62 π E tw² fd / (c ho) ≤ Fy               (Manual 9-...)
   fd = 3.5 − 7.5 (dc/d)
Cope dài/ sâu vượt giới hạn: dùng lateral-torsional buckling (Chapter F, Cb = 1.0) cho đoạn chữ T — [VERIFY] Manual 14th Part 9.
Cắt tại cope: shear yield (J4.2) trên ho tw ; block shear dọc bụng (Ubs = 1.0 một hàng, 0.5 hai hàng).
```
c = chiều dài cope, dc = chiều sâu cope, ho = d − dc (một phía) hoặc d − dct − dcb.

## H. Uốn/ oằn bản mã (Manual Part 9, 10)

- Bản chịu uốn không giằng (extended shear tab / bản mã tự do): classical plate buckling
```
Fcr = Fy Q
λ = ho sqrt(Fy) / ( 10 tw sqrt( 475 + 280 (ho/c)² ) )        (Manual 9-...) [VERIFY; ksi]
Q = 1          λ ≤ 0.7
  = 1.34 − 0.486 λ    0.7 < λ ≤ 1.41
  = 1.30/λ²     λ > 1.41
```
- Bản dạng dầm (tỷ số chiều dài/chiều cao lớn): Chapter F11 (rectangular bars): Lb d/t² ≤ 0.08E/Fy → Mn = Mp ≤ 1.6My; ngoài ra LTB theo F11-3/F11-4.

## I. Cấu kiện (`member_ls.py`) — dùng cho đoạn cột ngắn, gusset nén, dầm tại liên kết

- Nén E3: `Fe = π²E/(KL/r)²`; `KL/r ≤ 4.71√(E/Fy)` → `Fcr = 0.658^(Fy/Fe) Fy`; ngược lại `Fcr = 0.877 Fe`.
- Cắt bụng G2.1: `Vn = 0.6 Fy Aw Cv`; dầm cán h/tw ≤ 2.24√(E/Fy) → Cv=1, φ=1.0.
- Tương tác H1-1a/b.
- Beam flange rupture tại lỗ bu lông (F13.1): nếu `Fu Afn < Yt Fy Afg` → `Mn = Fu Afn Sx / Afg`; Yt = 1.0 (Fy/Fu ≤ 0.8) else 1.1.

## J. Bê tông (`concrete_ls.py`)

- J8: `Pp = 0.85 f'c A1 sqrt(A2/A1) ≤ 1.7 f'c A1` (φc = 0.65, Ωc = 2.31).
- ACI 318-11 App. D (neo): tùy chọn Phase 6b — steel strength `Nsa = Ase,N futa`, concrete breakout `Ncb`, pullout `Np = 8 Abrg f'c`, side-face blowout, shear breakout `Vcb`, pryout — nếu không implement, báo cáo ghi "Concrete anchorage per ACI 318 not checked".

## K. Detailing checks (luôn chạy khi `check_detailing=True`)

| Check | Yêu cầu | Ratio |
|---|---|---|
| Bolt spacing min | s ≥ 2.667 d (J3.3) | 2.667d / s |
| Bolt spacing max | s ≤ min(24 t, 305 mm) | s / max |
| Edge distance min | Le ≥ Table J3.4 (+C2) | Lemin / Le |
| Edge distance max | Le ≤ min(12 t, 150 mm) | |
| Weld size min/max | Table J2.4; w ≤ t − 2 | |
| Weld length min | L ≥ 4w | |
| Bolt entering/ tightening clearance | Manual Table 7-15/7-16 (khoảng hở cờ lê) — [VERIFY] giá trị | |
| Shear tab: tp ≤ db/2 + 1/16" hoặc tw dầm tương tự (conventional) | Manual Table 10-9 | |
| Double angle: t_angle ≤ 5/8 in (ductility) | Manual Part 10 | WARN |
| Plate fit: chiều cao bản ≤ T của dầm (khoảng bụng phẳng) | hình học | |
| Gusset/ brace clearance 2t cho uốn dẻo (nếu `hinge_zone=2t`) | chỉ khi yêu cầu | WARN |
