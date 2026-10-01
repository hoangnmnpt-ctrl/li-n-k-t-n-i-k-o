# STEELCONN — Bộ đặc tả để AI viết phần mềm tính liên kết thép theo AISC 360-10

Bộ tài liệu này là **"hợp đồng kỹ thuật"** để giao cho một AI lập trình (ChatGPT / Gemini / Grok / Claude…) viết một thư viện Python tính liên kết kết cấu thép, mô phỏng phạm vi và cách tổ chức của **RAM Connection** (Bentley), theo:

- **AISC 360-10** (Specification for Structural Steel Buildings) — chương J (liên kết), K (HSS), chương B/E/F/G khi cần.
- **AISC Steel Construction Manual 14th ed.** (Part 7, 8, 9, 10, 11, 12, 13, 14, 15) — Manual đi kèm 360-10.
- **AISC Design Guide 4** (Extended End-Plate Moment Connections, 2nd ed. 2003).
- **AISC Design Guide 16** (Flush and Extended Multiple-Row Moment End-Plate Connections, 2002).
- **AISC Design Guide 39** (End-Plate Moment Connections, 2023 — hợp nhất và thay thế DG4 + DG16).
- Bổ sung: DG1 (chân cột), DG24 / Chương K (HSS), DG29 (gusset, UFM), ASCE 7-10 (tổ hợp tải — tùy chọn).

> Lưu ý thuật ngữ: "AISC 7-10" trong yêu cầu gốc được hiểu là **AISC 360-10** (liên kết). Tổ hợp tải lấy theo **ASCE 7-10** (module tùy chọn).

## Danh sách file

| File | Nội dung | Ai đọc |
|---|---|---|
| `01_MASTER_PLAN.md` | Phạm vi, giả định mặc định, lộ trình 10 phase, cây thư mục repo, Definition of Done | AI + người |
| `02_ARCHITECTURE_DATA_MODEL.md` | Đơn vị, vật liệu, tiết diện, bu lông, hàn, mô hình Joint giống RAM Connection, JSON schema input/output, registry check | AI |
| `03_LIMIT_STATES_AISC360-10.md` | Thư viện công thức trạng thái giới hạn (bu lông, hàn, bản mã, block shear, prying, J10, cope…) có chữ ký hàm | AI |
| `04_JOINT_CATALOG.md` | Catalog 40+ kiểu nút theo đúng các màn hình RAM Connection (BCF, BCW, BG, BS, CS, CC, CB, CCB, CBB, CVR, VXB, HCBB, HBBB, HXB, CHB) + danh sách check cho từng kiểu | AI |
| `05_MOMENT_END_PLATE_DG4_DG16_DG39.md` | Quy trình end-plate chi tiết, bảng yield-line, cột, sườn, knee, apex, splice | AI |
| `06_BRACING_GUSSET_UFM.md` | Gusset, Whitmore, UFM, chevron, X-brace, giằng ngang | AI |
| `07_HSS_TRUSS_CHAPTER_K.md` | Nút giàn ống CHB (YT, K, KN, KT, X), mitred knee | AI |
| `08_COLUMN_BASE_DG1.md` | Chân cột, bản đế, bu lông neo, chân cột có giằng, đầu cột (column cap) | AI |
| `09_REPORT_TESTING_VALIDATION.md` | Mẫu báo cáo kiểu RAM Connection, bộ test, ví dụ đối chiếu, dung sai | AI |
| `10_PHASE_PROMPTS.md` | Prompt copy-paste cho từng phase, kèm tiêu chí nghiệm thu | Người dùng |
| `skill/SKILL.md` | Skill tổng (quy tắc hành xử của AI khi code) | AI |
| `skill/PLATFORM_INSTRUCTIONS.md` | Instructions rút gọn (<8000 ký tự) cho Custom GPT, Gemini Gem, Grok Project | Người dùng |

## Cách dùng nhanh

1. **ChatGPT (Custom GPT / Project)**: dán khối "ChatGPT" trong `skill/PLATFORM_INSTRUCTIONS.md` vào *Instructions*; upload tất cả file `0*.md` + `skill/SKILL.md` vào *Knowledge*.
2. **Gemini (Gem)**: dán khối "Gemini" vào *Instructions*; thêm các file vào *Knowledge*.
3. **Grok (Project)**: dán khối "Grok" vào *Custom instructions*; đính kèm file.
4. Giao việc **từng phase một** bằng prompt trong `10_PHASE_PROMPTS.md`. Không giao "viết cả chương trình" trong một lần — đó là nguyên nhân chính làm AI bịa công thức hoặc bỏ sót check.
5. Sau mỗi phase: chạy `pytest`, so sánh với ví dụ trong `09_…`, rồi mới sang phase kế.

## Nguyên tắc chống sai (bắt buộc với mọi AI)

- Mọi công thức trong code phải có comment trích dẫn điều khoản: `# AISC 360-10 Eq. J3-3a`.
- Công thức gắn nhãn **[VERIFY]** trong tài liệu này phải được đối chiếu với bản PDF gốc mà người dùng cung cấp trước khi đưa vào code; nếu không có PDF → vẫn code theo tài liệu, nhưng thêm `VERIFY_FLAG=True` vào metadata của check và in cảnh báo trong báo cáo.
- Không tự nghĩ ra hệ số. Không "làm tròn" hệ số φ/Ω.
- Mọi đơn vị nội bộ: **N, mm, MPa** (N/mm²). Hằng số viết theo ksi phải đổi sang MPa bằng hàm tiện ích.
