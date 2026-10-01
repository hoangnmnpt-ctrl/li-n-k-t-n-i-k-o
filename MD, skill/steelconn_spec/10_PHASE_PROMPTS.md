# 10 — PROMPT GIAO VIỆC THEO PHASE (copy-paste)

Cách dùng: mỗi phase mở **một cuộc hội thoại mới** trong Project/Gem/GPT đã nạp bộ tài liệu, dán **Prompt chung** + **Prompt phase**. Đính kèm code phase trước (zip hoặc các file liên quan) nếu nền tảng không giữ được repo.

---

## Prompt chung (dán đầu mọi phase)

```
Bạn là kỹ sư phần mềm kết cấu thép. Bạn đang xây dựng thư viện Python "steelconn" theo đúng bộ đặc tả đính kèm
(README, 01..10, skill/SKILL.md). Tuân thủ tuyệt đối SKILL.md.
Quy tắc:
1. Không hỏi lại những gì đã có mặc định trong 01 §2 và 02. Chỉ hỏi khi thiếu dữ liệu PDF cho mục gắn [VERIFY]
   — và ngay cả khi đó vẫn phải viết code hoàn chỉnh, đặt verify_flag=True, rồi liệt kê câu hỏi ở CUỐI câu trả lời.
2. Xuất code đầy đủ từng file (không "..." , không "phần còn lại tương tự"). File dài → chia nhiều tin nhắn, đánh số "Phần k/n".
3. Mỗi công thức có comment trích dẫn điều khoản. Đơn vị nội bộ N, mm, MPa.
4. Kèm test pytest cho mọi hàm mới. Kết thúc bằng: danh sách file đã tạo, lệnh chạy test, bảng check đã implement, danh sách [VERIFY].
```

## P0 — Nền tảng
```
PHASE P0. Tạo skeleton repo theo 01 §4. Implement đầy đủ:
- pyproject.toml (python>=3.10, numpy, pydantic>=2, pandas, jinja2, pytest, ruff, mypy)
- steelconn/units.py (02 §2), steelconn/codes/base.py + aisc360_10.py (03 §A bảng φ/Ω; 02 §4.1–4.4 bảng J3.1, J3.2, J3.3, J3.4 cả inch & metric; J2.4 min weld), materials.py (02 §3 bảng vật liệu), limit_states/result.py (CheckResult, JointResult theo 02 §8).
- API: code.available(Rn, key, method) ; code.hole_size(d, hole_type, units) ; code.min_edge(d, edge_type) ; code.pretension(grade, d).
Nghiệm thu: pytest pass; test tra bảng khớp tài liệu; test chuyển đổi đơn vị hai chiều.
```

## P1 — Tiết diện & nhóm bu lông/ hàn
```
PHASE P1. Implement sections/ (database.py đọc AISC Shapes CSV v15 metric/US tự nhận cột; shapes.py với IShape, Angle, Tee, Channel,
HSSRect, HSSRound, Pipe, DoubleAngle, BuiltUpI, TaperedI theo 02 §5; sample_shapes.csv ~30 tiết diện: W8–W36 phổ biến, L, HSS)
và components/ (bolts.py BoltGroup + IC method Crawford–Kulak + elastic; welds.py WeldGroup + IC method + J2.4(c); plates.py; holes.py).
Nghiệm thu: test IC bolt & weld với dữ liệu tests/data/manual_part7_ic.yaml, manual_part8_ic_weld.yaml (tạo khung TODO, skip nếu trống),
và test tự kiểm: nhóm bu lông lực đồng tâm → C = n (±0.5%); nhóm lệch tâm lớn → C giảm đơn điệu.
```

## P2 — Thư viện limit states
```
PHASE P2. Implement toàn bộ limit_states/ theo 03 (§B–§K) và 07 §3–4, 08 §2–5 phần công thức thuần (hss_ls.py, concrete_ls.py).
Mỗi hàm trả CheckResult đầy đủ formula + substituted. Test theo 09 §3 và test biên mọi nhánh if.
```

## P3 — Liên kết khớp + BCF/BCW/BG dạng khớp
```
PHASE P3. Implement connections/shear/* (04 §C1–C7) và joints bcf.py, bcw.py, bg.py (chỉ template shear), column_side.py phần J10 cho lực dọc dầm.
Implement design mode cục bộ cho single plate & double angle (template YAML 02 §10). CLI: `steelconn run examples/bcf_shear_tab.json --report out.html`.
Nghiệm thu: test với manual_part10_examples.yaml; examples/*.json cho mỗi connection.
```

## P4 — Liên kết mômen
```
PHASE P4. Implement connections/moment/end_plate.py + yield_lines.py (05 toàn bộ, mặc định DG4_DG16, thick plate; thin plate tùy chọn),
flange_plate.py (04 §C9–C10), direct_weld.py (C11), và column_side.py đầy đủ (05 §5: Yc, J10, continuity plates, doubler, panel zone).
Joint BCF/BCW template with_opposite_beam: cộng lực panel zone đúng chiều.
Nghiệm thu: dg4_examples.yaml, dg16_examples.yaml; test đảo dấu mômen; test đối xứng trái/phải.
```

## P5 — Haunch, tapered, knee, apex, splice
```
PHASE P5. Implement 05 §6–9 (end-plate splice, haunch, tapered knee, apex), 04 J-BS (flange+web plate splice), J-CS (column splice).
Chú ý biến đổi nội lực theo góc (05 §8), TaperedI.at(x). Nghiệm thu: test cân bằng lực sau biến đổi; test α=0 trùng kết quả BCF thường.
```

## P6 — Chân cột & đầu cột
```
PHASE P6. Implement 08 toàn bộ (base_plate.py, anchor.py, shear_lug.py; CB, CB with braces dùng lại gusset P7 nếu đã có — nếu chưa, tạo interface và NotImplemented có test skip), CC, CCB (phần cap).
Nghiệm thu: dg1_examples.yaml; test chuyển tiếp e = e_crit liên tục.
```

## P7 — Giằng
```
PHASE P7. Implement 06 toàn bộ: brace_end.py, gusset.py (Whitmore bằng hình học đa giác, L1/L2/L3), ufm.py (general + special cases),
joints cbb.py (5 template), cvr.py, vxb.py, hcbb.py, hbbb.py, hxb.py, hoàn thiện CB with braces & CCB.
Nghiệm thu: manual_part13_ufm.yaml; test UFM cân bằng ΣH, ΣV; test θ=45° đối xứng.
```

## P8 — HSS
```
PHASE P8. Implement 07 toàn bộ: phân loại nhánh theo lực, Table K2.1/K2.2 kèm giới hạn áp dụng, K4 hàn, K1 bản vào HSS, mitred knee (tùy chọn cidect có verify_flag).
Joint chb.py 8 template. Nghiệm thu: aisc_design_examples_K.yaml; test nhánh 50%K+50%Y.
```

## P9 — Design mode, batch, SAP2000
```
PHASE P9. design/optimizer.py (duyệt rời rạc + cắt tỉa, trả top-3 phương án), templates.py (YAML cho mọi connection),
loads/sap2000_import.py (đọc CSV/XLSX bảng "Element Forces - Frames" và "Joint Reactions", map đầu I/J theo 02 §6), loads/asce7_10.py (tổ hợp LRFD/ASD cơ bản 2.3.2/2.4.1),
CLI `steelconn batch joints.xlsx forces.csv --out results.xlsx`. Nghiệm thu: 100 nút < 30 s.
```

## P10 — Báo cáo
```
PHASE P10. report/builder.py + templates Jinja2 theo 09 §2 (MD, HTML có màu, PDF), hình phác matplotlib cho BCF end plate, shear tab, gusset, base plate, CHB.
Lệnh `steelconn verify-list` sinh VERIFY_LIST.md. Viết docs/USER_GUIDE.md (tiếng Việt) và docs/ram_comparison.md (khung).
```

## Prompt sửa lỗi (khi test fail)
```
Test sau fail: <dán log pytest>. Hãy:
1) xác định nguyên nhân (đơn vị / nhánh công thức / dữ liệu test),
2) sửa code tối thiểu, không đổi API public,
3) giải thích bằng 3 câu, 4) in lại toàn bộ file đã sửa.
Không được sửa giá trị kỳ vọng trong test trừ khi chứng minh được test sai bằng trích dẫn điều khoản.
```

## Prompt review chéo (dùng AI thứ hai kiểm AI thứ nhất)
```
Bạn là reviewer. Đối chiếu file <tên file> với đặc tả 03/05/06/07/08: liệt kê (a) công thức sai hệ số/ sai đơn vị,
(b) check thiếu so với danh sách Check IDs, (c) φ/Ω sai, (d) nhánh if sai biên. Trả bảng: dòng code | vấn đề | điều khoản | sửa đề xuất.
```
