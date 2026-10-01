# 04 — CATALOG KIỂU NÚT (theo menu "New joint" của RAM Connection)

Mỗi mục gồm: **Slot cấu kiện** → **Connection cho phép** → **Đường truyền lực** → **Danh sách check** (ID dùng trong code) → **Input bắt buộc/ mặc định**.
Các check chi tiết của từng connection nằm ở mục C (dùng chung). Mục J liệt kê cách joint gộp chúng.

---

## C. CONNECTION DÙNG CHUNG (tầng `connections/`)

### C1. Single plate (shear tab) — Manual 14th Part 10
- Hình học: n hàng bu lông 1 cột (conventional) hoặc ≥1 cột (extended), khoảng a từ mặt đỡ tới đường bu lông, Leh/Lev, bản hàn 2 mặt vào đỡ.
- **Conventional** (điều kiện Manual Table 10-9: n = 2–12, a ≤ 3.5 in, lỗ STD hoặc SSLT, tp hoặc tw ≤ db/2 + 1/16 in, Leh ≥ 2db cả bản & dầm, hàn ≥ 5/8 tp):
  - Lệch tâm nhóm bu lông e (Manual Table 10-9) [VERIFY]: n = 2–5: e = a/2 (STD, SSLT); n = 6–9: e = a (STD), a/2 (SSLT); n = 10–12: e = a (cả hai) — nếu người dùng có Manual khác phiên bản, cho phép override `ecc_rule`.
  - Không cần check đứt bu lông do mômen ở mặt đỡ; hàn 5/8 tp cả hai mặt đảm bảo chảy bản trước.
- **Extended** (vượt điều kiện): e = a; nhóm bu lông IC; bản check `Mmax = Vr e`; `tmax = 6 Mmax/(Fy d_p²)` với `Mmax = (Fnv/0.90)(Ab C')` (C' = hệ số mômen thuần của nhóm) — nếu tp > tmax → cần bản đủ cứng / check ổn định cột đỡ.
- Checks: `bolt_shear` (IC), `bolt_bearing_plate`, `bolt_bearing_beam_web`, `plate_shear_yield`, `plate_shear_rupture`, `plate_block_shear` (Ubs=1.0 một cột, 0.5 nhiều cột), `plate_flexure_yield/rupture` (extended), `plate_shear_flexure_interaction`, `plate_buckling` (03 §H, extended), `weld_plate_to_support` (hàn 2 mặt, 5/8 tp hoặc thiết kế theo lực + mômen), `beam_web_shear_yield/rupture`, `beam_web_block_shear` (nếu cope), `cope_checks` (03 §G), `support_shear_rupture_at_weld` (khi đỡ là bụng cột/ dầm chính: đứt cắt kim loại cơ bản đỡ tại hai đường hàn góc — tương đương t_min = 3.09 D/Fu (in, ksi, E70, LRFD) trong Manual Part 9; implement tổng quát `φ0.6 Fu_s t_s ≥ 2 × φFnw 0.707 w` trên đơn vị dài), `axial` (nếu P≠0: bản kéo J4.1, hàn, bearing theo phương hợp lực).

### C2. Double angle (all-bolted / bolted-welded / all-welded) — Part 10
- Checks: bu lông cắt kép qua bụng dầm (không lệch tâm với bu lông-bu lông); bu lông cắt đơn trên chân đỡ; bearing/tearout góc, bụng dầm, cánh/bụng đỡ; góc: shear yield/rupture, block shear; hàn góc vào bụng dầm dùng Manual Table 8-8 (IC, hàn chữ C) và hàn vào đỡ: elastic với lệch tâm (Manual Table 10-2 phương pháp); axial kéo → prying trên chân góc bắt vào đỡ (03 §E), cắt+kéo bu lông (J3.7).
- Detailing: t góc ≤ 5/8 in cho độ dẻo (WARN), chiều dài góc ≥ T/2.

### C3. Single angle — Part 10 (Table 10-11): bu lông chân đỡ chịu lệch tâm (IC, e = khoảng từ đường bu lông chân đỡ tới đường bu lông/ hàn chân dầm) ; bu lông chân dầm cắt đơn ; góc: shear yield/rupture, block shear, uốn tại tiết diện tới hạn ; hàn góc dạng L (IC weld, Manual Table 8-10) khi hàn.

### C4. Shear end plate — Part 10: bu lông cắt, bearing bản & đỡ, bản shear yield/rupture, block shear, hàn bụng dầm–bản (chỉ tính chiều dài bụng, trừ 2w), bụng dầm shear yield trên chiều dài hàn.

### C5. Unstiffened seated (seat angle + top angle) — Part 10:
- Chiều dài chịu lực cần `lb_req` từ J10.2 & J10.3 (end); bearing length không nhỏ hơn k.
- e của lực trên chân góc; check chân góc chịu uốn tại tiết diện tới hạn (cách mặt lưng góc t + 3/8 in): `Mu = Ru (e_f − t − 3/8")` [VERIFY]; `φMn = 0.9 Fy b t²/4`; chân góc cắt; bu lông/ hàn vào đỡ.

### C6. Stiffened seated — Part 10: bản chịu (seat plate) + sườn; check sườn: `Ru ≤ φ Fy ts W` [VERIFY], hàn sườn chịu uốn+cắt (Manual Table 10-8 hệ số), bụng cột đỡ: yield-line (Manual Part 10 cho gối đặt trên bụng cột) [VERIFY].

### C7. Shear tee — WT: tương tự single plate ở bụng T, prying ở cánh T nếu có kéo.

### C8. Moment end plate — xem file 05.

### C9. Bolted flange plate (FP) moment — Manual Part 12:
- Lực cánh `Pf = Mu/(d + tp)` (bản trên cánh) hoặc `Mu/d` (tuỳ vị trí bản). + lực dọc: `Pf ± P/2`.
- Bản kéo: J4.1 yield/rupture (Ae = An ≤ 0.85Ag), block shear (bản & cánh dầm); bản nén: J4.4 (KL = 0.65 × khoảng từ mặt cột tới hàng bu lông đầu, K=0.65) ; bu lông cắt đơn + bearing; F13.1 đứt cánh dầm tại lỗ; hàn bản vào cột (2 đường hàn góc dọc cạnh, hoặc CJP); bụng: shear connection (C1/C2) chịu V.
- Phía cột: J10.1–J10.6 (Ffu), sườn, doubler.

### C10. Welded flange plate — như C9 nhưng hàn bản–cánh dầm (hàn 3 cạnh, IC weld), shear lag U theo Table D3.1 case 4.

### C11. Direct welded flange (CJP) — cánh dầm hàn CJP vào cột; check: cánh dầm đủ (M ≤ φMn dầm), bụng: shear tab (C1) hoặc hàn trực tiếp, cột: J10 với `lb = tbf`, sườn/doubler.

### C12. Gusset brace connection — xem file 06.
### C13. Base plate — xem file 08.
### C14. HSS branch — xem file 07.
### C15. Splice plates (beam/column) — xem mục J-BS, J-CS.

---

## J. JOINTS

### J-BCF — Beam to Column Flange
| Template | Slot | Ghi chú |
|---|---|---|
| `beam_to_column_flange` | column, right_beam | dầm vào cánh cột |
| `with_opposite_beam` | column, right_beam, left_beam | hai dầm hai phía |
| `haunched` | column, right_beam(+haunch) | haunch = đoạn WT/ bản hàn dưới dầm → end plate cao hơn (05 §7) |
| `haunched_opposite` | column, right_beam, left_beam (+haunch) | |
| `tapered_beam` | column, right_beam (TaperedI) | end plate theo tiết diện đầu dầm |
| `tapered_knee` | column (TaperedI), rafter (TaperedI), slope | nút khung cổng (knee) — 05 §8 |
| `tubular_mitred_knee` | column (HSS), rafter (HSS), angle | 07 §5 |

Connections cho `right_beam/left_beam`: C1–C11.
Đường truyền: V → shear connection (hoặc bu lông vùng nén end plate); M → cặp lực cánh `Ffu = M/(d − tf)`; P → phân đều cho bu lông/ hàn (kéo cộng vào cánh kéo).
Checks phía cột (`column_side.py`, gọi một lần cho tổng lực từ các dầm):
- `col_flange_local_bending` (J10.1 hoặc yield-line cánh cột DG4 khi end plate),
- `col_web_local_yielding` (J10.2), `col_web_crippling` (J10.3), `col_web_compression_buckling` (J10.5, chỉ khi hai phía có lực nén đối nhau — opposite beam),
- `col_panel_zone_shear` (J10.6) với `Vu = Σ Ffu − Vc`,
- `continuity_plates_required` + thiết kế sườn (J10.8) + hàn sườn,
- `doubler_required` + thiết kế doubler + hàn,
- `col_flange_bolt_bearing` (khi bu lông xuyên cánh cột), `col_flange_prying` (liên kết góc/T có kéo).
Hình học: bề rộng bản ≤ bf cột + hợp lý; gage g ≥ tw_col + 2×clearance; bu lông không vướng k1.

### J-BCW — Beam to Column Web
- Slot: column (trục yếu), right_beam, [left_beam].
- Shear: C1, C2, C4, C5 (seat trên bụng), C7. Moment: flange plates hàn vào sườn/bản nối (thường RAM dùng "moment connection to column web" qua bản ngang hàn 3 cạnh) — implement C9/C10 với bản hàn vào bụng + cánh cột.
- Checks phía cột: bụng cột chịu cắt đứt tại hàn/bu lông (`0.6 Fu tw`), bụng cột uốn ngoài mặt phẳng do lực dọc dầm (yield-line bụng — Manual Part 9/ DG ... [VERIFY], nếu P≠0 → dùng mô hình yield-line bản 4 cạnh ngàm: `Rn = Fy tw²/4 × (hệ số hình học)`; nếu không chắc → WARN + yêu cầu người dùng xác nhận), khoảng hở với cánh cột (bề rộng dầm vs T cột), cope tự động nếu cánh dầm vướng cánh cột.
- `tubular_mitred_knee` (BCW): HSS cắt vát hàn — 07 §5.

### J-BG — Beam to Girder (có trong RAM, cắt khỏi ảnh)
- Slot: girder, right_beam, [left_beam], cope tự động theo cao độ cánh (top flush).
- Checks: connection shear; girder web: `shear_rupture` tại đường bu lông (khi hai dầm dùng chung bu lông → cộng lực), `web_bearing`; dầm: cope checks; khe hở cope; nếu dầm phụ đặt thấp hơn không cần cope.

### J-BS — Beam splice / Apex / Tapered splice
| Template | Connection | Đường truyền |
|---|---|---|
| `beam_splice` | (a) flange + web plates bolted (Manual Part 14 / 12); (b) end-plate splice (05 §6) | M → cặp lực cánh; V + mômen lệch tâm → bản bụng (IC) |
| `apex` | end-plate splice nghiêng góc | biến đổi nội lực về trục vuông góc bản đầu (05 §9) |
| `apex_haunched` | end-plate với haunch | |
| `tapered_splice` | end-plate giữa hai tiết diện tapered | |

Checks (plates): bản cánh kéo/nén (J4.1/J4.4), block shear bản & cánh, bu lông cắt (đơn/kép nếu bản trong+ngoài: chia lực theo diện tích), bearing, F13.1 đứt cánh, bản bụng: cắt + mômen lệch tâm (V·e, e = khoảng tới tâm nhóm bu lông), IC bu lông, bản bụng uốn/ cắt (tương tác), fill plates (hf). Quy tắc lực thiết kế tối thiểu (tùy chọn `splice_min_design`): mômen ≥ 50% φMn dầm? → **không mặc định**; để người dùng chọn `min_moment_ratio`.

### J-CS — Column splice (Manual Part 14)
- Slot: upper_column, lower_column (có thể khác tiết diện → fill plates, bearing/ butt plate).
- Lực: P (nén/kéo), V, M.
- Trường hợp nén thuần có tiếp xúc (milled): chỉ cần bản định vị; check J7 bearing.
- Kéo/ mômen: lực cánh `Ff = P/2 ± M/d` (cánh chịu kéo); bản cánh: bu lông cắt, bearing, J4.1, block shear; fill (hf 0.85 nếu ≥2 filler hoặc phát triển filler); bản bụng: V.
- Butt plate khi đổi độ sâu: bản chịu uốn (yield-line đơn giản: công-xôn), hàn.

### J-CC — Column cap (continuous beam over column)
- Slot: column, beam (liên tục phía trên), cap plate.
- Checks: cap plate: bearing J7, uốn bản (công-xôn phần nhô), hàn cột–bản (nén: tiếp xúc hoặc hàn đủ 100% nếu `bearing_contact=False`; kéo: hàn phát triển lực nhổ), bu lông bản–cánh dầm (kéo nhổ + prying, cắt do V ngang), dầm: J10.2, J10.3 (lb = chiều rộng tiếp xúc qua bản, phân bố 2.5:1 qua bản), J10.4 nếu cánh dưới không giằng, sườn dầm nếu cần (J10.8), web sidesway.
- `CCB`: + gusset phía trên/dưới cho giằng (06 §6).

### J-CB — Column base (08).

### J-CBB — Column–Beam–Brace (06)
| Template | Slot |
|---|---|
| `one_brace` | column, beam, brace (gusset ở góc dầm–cột) |
| `two_braces` | column, beam, brace_top, brace_bottom (hai gusset trên & dưới dầm) |
| `four_braces` | column, beam_left, beam_right, 4 braces (liên kết vào bụng hoặc cánh cột theo orientation) |
| `y_brace` | column, brace (gusset chỉ vào cột, không có dầm) |
| `k_brace` | column, brace_top, brace_bottom (gusset vào cột, hai giằng giao tại cột) |
Truyền lực: UFM (06 §3) cho gusset góc; gusset chỉ vào cột → hàn/ bu lông gusset–cột chịu toàn bộ lực + mômen lệch tâm.

### J-CVR — Chevron (06 §5): beam, 1/2/4 braces (4 braces = trên & dưới dầm). Checks thêm: dầm chịu lực không cân bằng (ngoài scope member design — chỉ xuất lực), bụng dầm J10.2/J10.3 dưới gusset, sườn dầm.

### J-VXB — Vertical X brace (06 §7): giằng liên tục + giằng đứt nối qua bản mã giao; check gusset trung tâm, bản nối.

### J-HCBB / HBBB / HXB — Giằng ngang (06 §8)
- `HCBB full`: column, front_beam, right_beam, brace (gusset nằm ngang dưới/ trên cánh dầm, bắt vào cánh dầm và đôi khi vào cột).
- `front_beam_only`, `right_beam_only`: bớt slot.
- `HBBB`: girder, beam, brace; `girder_only`: gusset chỉ gắn vào dầm chính.
- `HXB`: X ngang giữa nhịp.

### J-CHB — Tubular trusses (07)
| Template | Nhánh |
|---|---|
| `YT` | chord + 1 branch (T khi θ=90°) |
| `KN` | chord + 1 nhánh xiên + 1 nhánh đứng (N) |
| `K` | chord + 2 nhánh xiên (gap hoặc overlap) |
| `X2` | chord + 2 nhánh hai phía đối diện (thẳng hàng) |
| `X4` | chord + 4 nhánh (2 mỗi phía) |
| `KT` | chord + 3 nhánh cùng phía (2 xiên + 1 đứng) |
| `KT3` | "KT with three branches" (biến thể hình học, nhánh giữa lệch) |
| `KT6` | 3 nhánh mỗi phía chord |

## Ma trận (Joint × Check group)

| Joint | Bolts | Welds | Plates | Beam web/ cope | Column J10 | Panel | Gusset | HSS K | Concrete |
|---|---|---|---|---|---|---|---|---|---|
| BCF/BCW/BG | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ (moment) | | | |
| BS/CS | ✔ | ✔ | ✔ | ✔ | | | | | |
| CC/CCB | ✔ | ✔ | ✔ | ✔ (J10 dầm) | | | CCB | | |
| CB | ✔ (neo) | ✔ | ✔ | | | | 1–2 braces | | ✔ |
| CBB/CVR/VXB/H* | ✔ | ✔ | ✔ | ✔ | ✔ | | ✔ | | |
| CHB | | ✔ | | | | | | ✔ | |
