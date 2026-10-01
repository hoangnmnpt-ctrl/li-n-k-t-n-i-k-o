# 07 — NÚT GIÀN ỐNG (CHB) & NÚT HSS — AISC 360-10 CHƯƠNG K

Module: `limit_states/hss_ls.py`, `connections/hss/branch_chord.py`, `joints/chb.py`.
Nguồn: AISC 360-10 Chapter K (K1 lực tập trung lên HSS, K2 HSS-HSS truss, K3 HSS-HSS moment, K4 hàn HSS), AISC Design Guide 24 (HSS Connections, 2010). **Toàn bộ công thức Chương K phải test với ví dụ AISC Design Examples v14 Chapter K** (người dùng cung cấp số liệu).

## 1. Ký hiệu

| Ký hiệu | Ống tròn | Ống chữ nhật |
|---|---|---|
| Chord | D, t (tdes) | B (bề rộng mặt nhận nhánh), H, t |
| Branch | Db, tb | Bb, Hb, tb |
| β | Db/D | Bb/B |
| γ | D/(2t) | B/(2t) |
| η | — | lb/B, lb = Hb/sinθ |
| θ | góc nhánh–chord (độ) | |
| g | khe hở giữa hai nhánh (K gap) đo dọc mặt chord | |
| Ov | overlap % = (q/p)·100 | |
| e | lệch tâm điểm giao trục (âm = về phía nhánh) | |

Chord stress interaction:
```
U = | Pro/(Fc Ag) + Mro/(Fc S) |    Fc = Fy (LRFD), 0.6 Fy (ASD)
Pro: lực dọc chord phía có ứng suất nén nhỏ hơn (T/Y/X) — theo 360-10 định nghĩa [VERIFY phía chọn cho K]
```

## 2. Phân loại nút (bắt buộc — K2 yêu cầu phân loại theo lực, không theo hình học)

Hàm `classify_branch(branch, all_branches, chord)`:
- Lực vuông góc của nhánh được cân bằng bởi nhánh khác cùng phía trong cùng mặt → **K** (phần cân bằng).
- Truyền qua chord sang nhánh phía đối diện → **X** (cross).
- Truyền bằng lực cắt chord → **Y** (T khi θ = 90°).
- Nhánh có thể là tổ hợp (vd 50% K + 50% Y) → tính theo tỷ lệ (tổng các tỷ số ≤ 1). Implement phân rã tuyến tính như DG24/Commentary K2.

## 3. Ống tròn — Table K2.1 (360-10)

```
T/Y — chord plastification:
   Pn sinθ = Fy t² (3.1 + 15.6 β²) γ^0.2 Qf                 φ = 0.90, Ω = 1.67
T/Y/K — punching shear (khi Db < D − 2t):
   Pn = 0.6 Fy t π Db (1 + sinθ)/(2 sin²θ)                   φ = 0.95, Ω = 1.58
X — chord plastification:
   Pn sinθ = Fy t² [ 5.7 / (1 − 0.81 β) ] Qf                  φ = 0.90
K gap/overlap — chord plastification (nhánh nén):
   (Pn sinθ)_comp = Fy t² (2.0 + 11.33 Db,comp/D) Qg Qf       φ = 0.90
   (Pn sinθ)_tens = (Pn sinθ)_comp
   Qg = γ^0.2 [ 1 + 0.024 γ^1.2 / ( exp(0.5 g/t − 1.33) + 1 ) ]   (g lấy âm khi overlap — [VERIFY])
Qf = 1                            (chord kéo)
   = 1 − 0.3 U (1 + U)            (chord nén)
Giới hạn áp dụng Table K2.1A [VERIFY]:
   θ ≥ 30° ; D/t ≤ 50 (T,Y,K), ≤ 40 (X) ; Db/tb ≤ 50 và ≤ 0.05E/Fyb ; 0.2 < β ≤ 1.0 (K: 0.4 ≤ β) ;
   Fy, Fyb ≤ 360 MPa (52 ksi) ; Fy/Fu, Fyb/Fub ≤ 0.8 ; gap g ≥ tb,comp + tb,tens ; 25% ≤ Ov ≤ 100% ; tb overlapping ≤ tb overlapped ;
   −0.55 ≤ e/D ≤ 0.25 (K)
Ngoài giới hạn → check status "NA" + WARN "outside Table K2.1A limits".
```

## 4. Ống chữ nhật — Table K2.2 (360-10) [VERIFY toàn mục; φ theo từng dòng]

```
T/Y/X:
 (a) Chord wall plastification (β ≤ 0.85):
     Pn sinθ = Fy t² [ 2η/(1 − β) + 4/sqrt(1 − β) ] Qf          φ = 1.00, Ω = 1.50
 (b) Punching shear (0.85 < β ≤ 1 − 1/γ, hoặc B/t < 10):
     Pn sinθ = 0.6 Fy t B (2η + 2 β_eop)                         φ = 0.95, Ω = 1.58
     β_eop = 5β/γ ≤ β
 (c) Sidewall local yielding (β = 1.0) — kéo hoặc nén:
     Pn sinθ = 2 Fy t (5k + lb)                                   φ = 1.00, Ω = 1.50 ; k = bán kính góc ngoài ≈ 1.5 t
 (d) Sidewall local crippling (β = 1.0, nhánh nén):
     T/Y: Pn sinθ = 1.6 t² [ 1 + 3 lb/(H − 3t) ] sqrt(E Fy) Qf   φ = 0.75, Ω = 2.00
     X:   Pn sinθ = [ 48 t³/(H − 3t) ] sqrt(E Fy) Qf              φ = 0.90, Ω = 1.67
 (e) Local yielding of branch due to uneven load distribution (β > 0.85):
     Pn = Fyb tb (2 Hb + 2 b_eoi − 4 tb)                           φ = 0.95, Ω = 1.58
     b_eoi = [10/(B/t)] [ (Fy t)/(Fyb tb) ] Bb ≤ Bb
 (f) Shear of chord sidewalls (X, cosθ > β): theo G5
 Qf = 1 (chord kéo) ; = 1.3 − 0.4 U/β ≤ 1.0 (chord nén, cho (a)) ; cho (d): Qf = sqrt(1 − U²)?  [VERIFY]

K gap:
 (a) Chord wall plastification:
     Pn sinθ = Fy t² (9.8 β_eff γ^0.5) Qf                        φ = 0.90, Ω = 1.67
     β_eff = Σ(Bb + Hb) / (4B)  (tổng 2 nhánh)
     Qf = 1.3 − 0.4 U/β_eff ≤ 1.0 (chord nén)
 (b) Shear yielding of chord in gap: theo G5 (khe hở), dùng Vgap
 (c) Punching shear (Bb < B − 2t): Pn sinθ = 0.6 Fy t B (2η + β + β_eop)  φ = 0.95  [VERIFY]
 (d) Local yielding of branch (uneven): Pn = Fyb tb (2Hb + Bb + b_eoi − 4tb)  φ = 0.95
K overlap:
 Local yielding of overlapping branch:
   25% ≤ Ov < 50%: Pn,i = Fybi tbi [ (Ov/50)(2Hbi − 4tbi) + beoi + beov ]
   50% ≤ Ov < 80%: Pn,i = Fybi tbi (2Hbi − 4tbi + beoi + beov)
   80% ≤ Ov ≤ 100%: Pn,i = Fybi tbi (2Hbi − 4tbi + Bbi + beov)
   beov = [10/(Bbj/tbj)] [ (Fybj tbj)/(Fybi tbi) ] Bbi ≤ Bbi              φ = 0.95
 Nhánh bị chồng: Pn,j ≤ Pn,i (Abj Fybj)/(Abi Fybi)
Giới hạn Table K2.2A [VERIFY]: θ ≥ 30° ; B/t, H/t ≤ 35 (gap K), ≤ 30 (overlap), ≤ 35 (T,Y,X) ;
   Bb/tb, Hb/tb ≤ 35 và ≤ 1.25 sqrt(E/Fyb) ; 0.25 ≤ β (0.35 cho K gap) ; 0.5 ≤ Hb/Bb ≤ 2.0 ; Fy ≤ 360 MPa ; Fy/Fu ≤ 0.8 ;
   gap: g/B ≥ 0.5(1 − β_eff), g ≥ tb1 + tb2 ; overlap Bbi/Bbj ≥ 0.75 ...
```

## 5. Mitred knee (BCF/BCW `tubular_mitred_knee`)
- Không có trong AISC 360-10 Chương K. Cách làm (ghi rõ trong báo cáo "outside AISC 360 scope"):
  1. Hàn CJP toàn chu vi → cường độ mặt vát = tiết diện ống tại mặt cắt vát: kiểm tra `Mu ≤ φ Fy Z_eff`, `Z_eff = Z × μ_knee`.
  2. `μ_knee` (hệ số hiệu quả) lấy từ **CIDECT Design Guide 9 / Packer & Henderson** (không sườn / có bản ngăn) — AI phải yêu cầu bảng này từ người dùng; mặc định `μ_knee = 1.0` chỉ khi có bản ngăn dày ≥ max(t_ống) + 1 bậc và in WARN.
  3. Tương tác N–M: `Pu/φPn + 8/9 Mu/φMn ≤ 1` (H1-1a dạng liên kết).
- Tùy chọn `mitred_knee_method="cidect"|"welded_section_only"`.

## 6. Hàn HSS — K4
- Nhánh vào chord: hàn phải phát triển nhánh **hoặc** thiết kế theo lực với chiều dài hiệu dụng `le` (K4 Table K4.1 cho chữ nhật):
```
T/Y/X, θ ≤ 50°: le = 2Hb/sinθ + 2 b_eoi   ;   θ ≥ 60°: le = 2Hb/sinθ + b_eoi   (nội suy giữa 50–60)
K gap θ ≤ 50°: le = 2(Hb − 1.2tb)/sinθ + 2(Bb − 1.2tb)   ; θ ≥ 60°: le = 2(Hb − 1.2tb)/sinθ + (Bb − 1.2tb)
Ống tròn: le = chu vi giao tuyến (tính số) × hệ số hiệu dụng (1.0 nếu hàn phát triển)  [VERIFY 360-10 có K4 cho tròn?]
```
- Mặc định (giống RAM): `hss_weld_design="develop_branch"` → hàn đủ phát triển Fyb tb (khuyến nghị); tùy chọn `"force_based"`.

## 7. K1 — lực tập trung lên HSS (dùng cho gusset/ bản mã hàn vào cột/ dầm HSS)
- Bản dọc (longitudinal plate) vào HSS chữ nhật: `Rn = Fy t² [ 2lb/B + 4 sqrt(1 − tp/B) ] Qf` φ1.00 — [VERIFY Table K1.2]
- Bản ngang (transverse) vào HSS tròn: `Rn = Fy t² [5.5/(1 − 0.81 Bp/D)] Qf` φ0.90 ; bản dọc vào HSS tròn: `Rn = 5.5 Fy t² (1 + 0.25 lb/D) Qf` φ0.90 — [VERIFY Table K1.1]
- Punching của bản mã qua thành ống: `tp ≤ Fu t/Fyp` (bản không làm thủng thành ống) — K1 [VERIFY].

## 8. Joint CHB — luồng tính
```
1. Đọc chord (liên tục, 2 đầu chịu P_left, P_right, M_left, M_right) và n nhánh (Pi, θi, phía, thứ tự dọc chord)
2. Hình học: điểm giao tuyến trục, e, g (hoặc Ov) giữa các nhánh kề; kiểm tra giới hạn
3. Phân loại từng nhánh (§2) cho mỗi tổ hợp tải
4. Tính Qf với Pro, Mro (lấy phía nén nhỏ hơn)
5. Với mỗi nhánh: các limit state tương ứng (§3/§4) → ratio = Pu sinθ/φ(Pn sinθ) hoặc Pu/φPn
6. Chord: kiểm tra tương tác chord tại khe (shear in gap: V_gap = Σ Pi sinθi, N_gap), check G5 + H1 tại khe (ống chữ nhật)
7. Hàn (§6)
8. Tổng hợp: KT3, KT6, X4: xử lý mỗi mặt phẳng/ mỗi phía chord độc lập cho plastification + tổng hợp cắt chord; KT: nhánh giữa kiểm tra như K với nhánh xiên gần nhất và theo gap (DG24 hướng dẫn KT: coi hai nhánh xiên cùng phía như một K, nhánh đứng xét với tổng thành phần — [VERIFY])
```

## 9. Check IDs
`hss_chord_plastification_{branch}`, `hss_punching_shear_{branch}`, `hss_sidewall_yielding`, `hss_sidewall_crippling`, `hss_branch_local_yield_uneven`, `hss_chord_shear_gap`, `hss_overlap_*`, `hss_limits_of_applicability` (status NA/WARN), `hss_weld_{branch}`, `hss_chord_axial_moment_interaction`.
