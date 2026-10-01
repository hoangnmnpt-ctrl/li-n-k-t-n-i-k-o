# 02 — KIẾN TRÚC & MÔ HÌNH DỮ LIỆU

## 1. Nguyên tắc kiến trúc

1. **3 tầng tách biệt**:
   - `limit_states/`: hàm thuần `f(numbers) -> CheckResult`. Không biết gì về joint.
   - `connections/`: một "connection" = cách một cấu kiện gắn vào cấu kiện đỡ (vd: shear tab của dầm phải vào cánh cột). Tự tính hình học dẫn xuất, phân phối lực, gọi limit_states.
   - `joints/`: một "joint" = nút gồm các slot cấu kiện (column, right_beam, left_beam, brace_1…), mỗi slot gán một connection; joint chịu trách nhiệm **cân bằng lực tại nút** và **check phía cấu kiện đỡ** (cột, dầm chính) do tổng hợp nhiều connection.
2. **Giống RAM Connection**: người dùng chọn Joint (mã BCF…), sau đó bấm "Data »" để khai báo: tiết diện, góc, lệch tâm, rồi với mỗi cấu kiện chọn kiểu connection + template. Cấu trúc JSON phản ánh đúng quy trình này.
3. **Code edition strategy**: mọi φ, Ω, bảng tra đi qua `code = get_code("AISC360-10")`. Không import hằng số trực tiếp trong limit_states.
4. **Không có trạng thái toàn cục**. Mọi object là `pydantic.BaseModel` (frozen với dữ liệu input) hoặc `@dataclass`.

## 2. Đơn vị (`units.py`)

- Nội bộ: **mm, N, MPa, N·mm, độ (deg) cho input góc, rad nội bộ**.
- Hàm: `ksi(x)->MPa` (×6.894757), `inch(x)->mm` (×25.4), `kip(x)->N` (×4448.222), `kipft(x)->N·mm` (×1.355818e6), `kN(x)`, `kNm(x)`, và nghịch đảo `to_kN`, `to_kNm`, `to_ksi`, `to_in`, `to_kip`.
- `E = 200_000 MPa` (AISC dùng 29 000 ksi = 199 948 MPa; dùng **ksi(29000)** để khớp ví dụ Manual khi test hệ inch; tham số `E_steel` trong settings, mặc định `ksi(29000)`).
- `G = ksi(11200)`.
- Input JSON có trường `"units": "SI" | "US"`. Báo cáo in theo hệ đơn vị input.

## 3. Vật liệu (`materials.py`)

```python
class Steel(BaseModel):
    name: str; Fy: float; Fu: float; E: float = E_STEEL
class BoltGrade(BaseModel):
    name: Literal["A307","A325","A490","F1852","F2280","A325M","A490M"]
    group: Literal["A","B","A307"]
    Fnt: float   # MPa, Table J3.2
    Fnv_N: float # threads included
    Fnv_X: float # threads excluded
class WeldElectrode(BaseModel):
    name: str = "E70XX"; FEXX: float = ksi(70)
class AnchorRod(BaseModel):
    grade: Literal["F1554-36","F1554-55","F1554-105"]; Fy: float; Fu: float
class Concrete(BaseModel):
    fc: float  # MPa
```

Bảng vật liệu mặc định (MPa):

| Mác | Fy | Fu | Dùng cho |
|---|---|---|---|
| A992 | 345 | 450 | W |
| A36 | 250 | 400 | bản, L, C |
| A572 Gr50 | 345 | 450 | bản dày, L |
| A500 Gr B (tròn / chữ nhật) | 290 / 317 | 400 / 400 | HSS |
| A500 Gr C (tròn / chữ nhật) | 317 / 345 | 427 / 427 | HSS (mặc định) |
| A53 Gr B | 240 | 415 | Pipe |
| F1554 Gr36 / 55 / 105 | 250 / 380 / 725 | 400 / 517 / 862 | Neo |
| SS400 (JIS) | 245 | 400 | tùy biến |
| Q345B (GB) | 345 | 470 | tùy biến |

HSS ERW: chiều dày thiết kế `t_des = 0.93 t_nom` (AISC 360-10 B4.2). Đọc từ database cột `tdes` nếu có.

## 4. Bu lông & lỗ (`components/bolts.py`, `codes/aisc360_10.py`)

### 4.1 Table J3.2 (MPa, làm tròn theo Table J3.2M)

| Grade | Fnt | Fnv (N) | Fnv (X) |
|---|---|---|---|
| A307 | 310 | 188 | 188 |
| A325/A325M, F1852 (Group A) | 620 | 372 | 457 |
| A490/A490M, F2280 (Group B) | 780 | 457 | 579 |
| Bộ phận có ren (threaded parts, neo) | 0.75 Fu | 0.40 Fu (N) | 0.50 Fu (X) |

Ghi chú 360-10: nếu chiều dài mối nối (end-loaded, dọc theo lực) > 1270 mm (50 in) → Fnv × 0.83 (chú thích [b] Table J3.2).

### 4.2 Table J3.1 — Lực căng trước tối thiểu Tb

| d (in) | A325 (kip) | A490 (kip) | | d (mm) | A325M (kN) | A490M (kN) |
|---|---|---|---|---|---|---|
| 1/2 | 12 | 15 | | M16 | 91 | 114 |
| 5/8 | 19 | 24 | | M20 | 142 | 179 |
| 3/4 | 28 | 35 | | M22 | 176 | 221 |
| 7/8 | 39 | 49 | | M24 | 205 | 257 |
| 1 | 51 | 64 | | M27 | 267 | 334 |
| 1-1/8 | 56 | 80 | | M30 | 326 | 408 |
| 1-1/4 | 71 | 102 | | M36 | 475 | 595 |
| 1-3/8 | 85 | 121 | | | | |
| 1-1/2 | 103 | 148 | | | | |

### 4.3 Table J3.3 — Kích thước lỗ danh nghĩa (in / mm)

| d | STD | OVS | SSL (w × l) | LSL (w × l) |
|---|---|---|---|---|
| 1/2 | 9/16 | 5/8 | 9/16 × 11/16 | 9/16 × 1-1/4 |
| 5/8 | 11/16 | 13/16 | 11/16 × 7/8 | 11/16 × 1-9/16 |
| 3/4 | 13/16 | 15/16 | 13/16 × 1 | 13/16 × 1-7/8 |
| 7/8 | 15/16 | 1-1/16 | 15/16 × 1-1/8 | 15/16 × 2-3/16 |
| 1 | 1-1/16 | 1-1/4 | 1-1/16 × 1-5/16 | 1-1/16 × 2-1/2 |
| ≥1-1/8 | d+1/8 | d+5/16 | (d+1/8) × (d+3/8) | (d+1/8) × 2.5d |
| M16 | 18 | 20 | 18 × 22 | 18 × 40 |
| M20 | 22 | 24 | 22 × 26 | 22 × 50 |
| M22 | 24 | 28 | 24 × 30 | 24 × 55 |
| M24 | 27 | 30 | 27 × 32 | 27 × 60 |
| M27 | 30 | 35 | 30 × 37 | 30 × 67 |
| ≥M30 | d+3 | d+8 | (d+3) × (d+10) | (d+3) × 2.5d |

Đường kính lỗ dùng tính tiết diện thực (B4.3b): `d_h + 1/16 in` (= +2 mm).

### 4.4 Table J3.4 — Khoảng cách mép tối thiểu (từ tâm lỗ STD) [VERIFY bản 360-10 có cột sheared/rolled]

| d (in) | Mép cắt (sheared) | Mép cán/ cắt nhiệt |
|---|---|---|
| 1/2 | 7/8 | 3/4 |
| 5/8 | 1-1/8 | 7/8 |
| 3/4 | 1-1/4 | 1 |
| 7/8 | 1-1/2 | 1-1/8 |
| 1 | 1-3/4 | 1-1/4 |
| 1-1/8 | 2 | 1-1/2 |
| 1-1/4 | 2-1/4 | 1-5/8 |
| >1-1/4 | 1.75d | 1.25d |

Metric (Table J3.4M, mm, mép cắt / mép cán): M16 28/22, M20 34/26, M22 38/28, M24 42/30, M27 48/34, M30 52/38, M36 64/46, >M36 1.75d/1.25d. Lỗ OVS/slot: cộng `C2` theo Table J3.5 (OVS: +1/16 in cho d≤7/8, +1/8 cho d=1, +1/8 cho ≥1-1/8; slot dọc phương mép: 0.75d).

- Khoảng cách tối thiểu (J3.3): `s ≥ 2⅔ d` (ưu tiên 3d).
- Khoảng cách tối đa (J3.5): `≤ 24 t` và `≤ 305 mm` (sơn/không ăn mòn); mép tối đa `12 t ≤ 150 mm`.

### 4.5 Bolt group (IC method — Manual Part 7)

- Quan hệ tải–biến dạng Crawford–Kulak: `R = R_ult (1 − e^(−10Δ))^0.55`, `Δ_max = 0.34 in (8.64 mm)`, `Δ_i = Δ_max · r_i / r_max`.
- Giải lặp tìm tâm quay tức thời (IC) sao cho ΣFx=0, ΣFy=0, ΣM=0 (Newton hoặc tìm kiếm 2D trên trục vuông góc với phương lực + bisection). Trả về hệ số `C` sao cho `R_n,group = C · r_n,bolt`.
- Cung cấp thêm **elastic method** (tùy chọn `bolt_group_method="IC"|"elastic"`), mặc định IC (giống RAM).
- Hàm `bolt_group_C(xs, ys, ex, theta_deg) -> C`.

### 4.6 Weld group (IC method — Manual Part 8)

- Mỗi đoạn hàn chia ≥ 20 phần tử/ đoạn. Với phần tử góc θ so với phương lực: `R = 0.60 FEXX (1 + 0.5 sin^1.5 θ) [p(1.9 − 0.9p)]^0.3 · A_w`, `p = Δ/Δ_m`, `Δ_m = 0.209(θ+2)^−0.32 w`, `Δ_u = 1.087(θ+6)^−0.65 w ≤ 0.17 w`. Phần tử tới hạn: nhỏ nhất `Δ_u/r`.
- Trả về `C` hoặc trực tiếp `R_n`. Có elastic method dự phòng.
- Mối hàn nhóm đồng tâm chứa cả hàn dọc & ngang (J2.4(c)): `Rn = max(Rnwl + Rnwt, 0.85 Rnwl + 1.5 Rnwt)`.

## 5. Tiết diện (`sections/`)

Thuộc tính tối thiểu từng loại (tên cột theo AISC Shapes Database):

- `IShape`: d, bf, tf, tw, k_des, k_det, k1, T (chiều cao phần phẳng bụng), A, Ix, Zx, Sx, rx, Iy, Zy, Sy, ry, J, Cw, workable gage `g`.
- `Angle`: b (chân dài), d (chân ngắn), t, k, x̄, ȳ, A, rz, gages chuẩn (Manual Table 1-7A: chân 4" g=2.5", chân 3" g=1.75", chân 3.5" g=2", chân 5" g=3", chân 6" g=3.5"…).
- `Tee`, `Channel`, `HSSRect` (H, B, tdes, A, Ix, Zx, …), `HSSRound` (OD, tdes…), `Pipe`.
- `BuiltUpI(d, bf_top, tf_top, bf_bot, tf_bot, tw)` và `TaperedI(d_start, d_end, …)` → tính mọi thuộc tính giải tích; `TaperedI.at(x)` trả `BuiltUpI`.

## 6. Hệ trục & quy ước dấu

- Mỗi cấu kiện có trục địa phương: x dọc trục cấu kiện hướng **ra xa nút**, y theo bụng (trục mạnh vuông góc), z = x × y.
- Nội lực tại đầu cấu kiện tại nút: `P` (kéo +), `V2` (cắt trong mặt bụng), `V3` (cắt ngoài mặt), `M3` (mômen trục mạnh, dương khi căng thớ dưới = thớ −y), `M2`, `T`.
- Góc giằng `theta` đo từ trục ngang (dầm) đến trục giằng, độ, 0–90.
- Import SAP2000: map `P, V2, V3, T, M2, M3` trực tiếp; chú ý dấu SAP ở đầu I/J của frame (đầu I dấu ngược khi quy về "lực cấu kiện tác dụng lên nút") → hàm `sap2000_import.to_joint_end(frame_forces, end="I"|"J")`.

## 7. JSON input schema (ví dụ đầy đủ — BCF moment end-plate)

```json
{
  "project": {"name": "Nha xuong A", "engineer": "HLD", "units": "SI"},
  "settings": {
    "code": "AISC360-10",
    "design_method": "LRFD",
    "mode": "check",
    "bolt_group_method": "IC",
    "end_plate_method": "DG4_DG16",
    "consider_prying": true,
    "bearing_deformation_considered": true,
    "E_steel": 199948,
    "check_detailing": true,
    "ratio_limit": 1.0
  },
  "joint": {
    "type": "BCF",
    "template": "beam_to_column_flange",
    "members": {
      "column": {"section": "W14X90", "material": "A992", "orientation": "strong", "position": "intermediate"},
      "right_beam": {"section": "W18X50", "material": "A992", "slope_deg": 0.0, "offset_mm": 0.0,
        "connection": {
          "type": "moment_end_plate",
          "config": "4E",
          "plate": {"t": 25, "bp": 230, "material": "A572Gr50", "extension": 90},
          "bolts": {"grade": "A325", "d": 22, "thread": "N", "hole": "STD", "pretensioned": true,
                    "g": 140, "pfo": 50, "pfi": 50, "pb": null, "de": 40},
          "welds": {"flange": {"type": "fillet", "size": 10, "both_sides": true},
                    "web": {"type": "fillet", "size": 6, "both_sides": true}},
          "stiffener": null
        }
      }
    },
    "column_side": {"continuity_plates": "auto", "doubler": "auto", "stiffener_material": "A36"}
  },
  "loads": [
    {"name": "LC1", "right_beam": {"P": 0, "V2": 150e3, "M3": 180e6}, "column": {"P_above": -800e3, "P_below": -950e3, "V2": 0, "M3_above": 0, "M3_below": 0}},
    {"name": "LC2", "right_beam": {"P": 20e3, "V2": 90e3, "M3": -120e6}}
  ]
}
```

Quy tắc: trường `null` hoặc `"auto"` → dùng giá trị mặc định/ tự thiết kế (design mode cục bộ). Mọi trường có mặc định được liệt kê trong docstring pydantic.

## 8. Output — `CheckResult` và `JointResult`

```python
@dataclass
class CheckResult:
    id: str                 # "right_beam.end_plate.bolt_tension"
    group: str              # "Bolts" | "Welds" | "Plate" | "Beam" | "Column" | "Detailing" | "Gusset" | "HSS" | "Concrete"
    name: str               # "Bolt tension with prying"
    clause: str             # "AISC 360-10 J3.6; DG4 Eq. 3.12"
    demand: float           # N hoặc N·mm hoặc mm (detailing)
    capacity: float         # phiRn (LRFD) hoặc Rn/Omega (ASD)
    ratio: float            # demand/capacity; detailing: required/provided
    unit: str
    load_case: str
    formula: str            # "phiRn = phi * Fnt * Ab"
    substituted: str        # "0.75 * 620 * 380.1 = 176.8 kN"
    status: Literal["OK","NG","NA","WARN"]
    verify_flag: bool = False
    notes: list[str] = field(default_factory=list)

@dataclass
class JointResult:
    joint_type: str; inputs: dict; checks: list[CheckResult]
    governing: CheckResult; max_ratio: float; status: str
    derived_geometry: dict   # kích thước tự sinh (design mode)
    warnings: list[str]
```

## 9. Registry & tùy chọn kiểu RAM Connection

`joints/registry.py`:

```python
JOINT_REGISTRY = {
  "BCF": {"templates": ["beam_to_column_flange", "with_opposite_beam", "haunched", "haunched_opposite",
                        "tapered_beam", "tapered_knee", "tubular_mitred_knee"], "cls": BCFJoint},
  "BCW": {"templates": ["beam_to_column_web", "with_opposite_beam", "tubular_mitred_knee"], "cls": BCWJoint},
  "BG":  {"templates": ["beam_to_girder", "beam_to_girder_both_sides"], "cls": BGJoint},
  "BS":  {"templates": ["beam_splice", "apex", "apex_haunched", "tapered_splice"], "cls": BSJoint},
  "CS":  {"templates": ["column_splice"], "cls": CSJoint},
  "CC":  {"templates": ["column_cap"], "cls": CCJoint},
  "CB":  {"templates": ["column_base", "base_one_brace", "base_two_braces"], "cls": CBJoint},
  "CCB": {"templates": ["column_cap_brace"], "cls": CCBJoint},
  "CBB": {"templates": ["one_brace", "two_braces", "four_braces", "y_brace", "k_brace"], "cls": CBBJoint},
  "CVR": {"templates": ["chevron_one", "chevron_two", "chevron_four"], "cls": CVRJoint},
  "VXB": {"templates": ["vertical_x"], "cls": VXBJoint},
  "HCBB":{"templates": ["full", "front_beam_only", "right_beam_only"], "cls": HCBBJoint},
  "HBBB":{"templates": ["beam_beam_brace", "girder_only"], "cls": HBBBJoint},
  "HXB": {"templates": ["horizontal_x"], "cls": HXBJoint},
  "CHB": {"templates": ["YT","KN","K","X2","X4","KT","KT3","KT6"], "cls": CHBJoint},
}
CONNECTION_REGISTRY = {
  "shear": ["single_plate","single_plate_extended","double_angle","single_angle","shear_end_plate",
            "unstiffened_seat","stiffened_seat","shear_tee"],
  "moment": ["moment_end_plate","bolted_flange_plate","welded_flange_plate","direct_weld"],
  "brace": ["gusset_bolted","gusset_welded","claw_angles","hss_slotted","hss_end_plate"],
  "splice": ["flange_web_plates","end_plate_splice","column_splice_plates","column_splice_bearing"],
  "base": ["base_plate"],
  "hss": ["hss_branch_welded"]
}
```

Tùy chọn toàn cục (settings) mô phỏng "Options/Criteria" của RAM Connection:

| Key | Giá trị | Ý nghĩa |
|---|---|---|
| `bearing_deformation_considered` | bool (True) | chọn 1.2/2.4 hay 1.5/3.0 trong J3.10 |
| `consider_prying` | bool (True) | tính prying cho T-stub/angle/end plate mỏng |
| `slip_critical_limit_state` | "serviceability"/"strength" | 360-10: SC ở mức strength với φ 1.00/0.85/0.70 |
| `fillers` | int 0..n | hf=1.0 (≤1 filler hoặc filler được phát triển) / 0.85 |
| `surface_class` | "A"/"B" | μ = 0.30 / 0.50 |
| `weld_design_method` | "IC"/"elastic" | |
| `use_directional_strength` | bool (True) | hệ số (1+0.5 sin^1.5θ) |
| `check_detailing` | bool | |
| `column_stiffener_design` | "auto"/"none"/"provided" | |
| `panel_zone_inelastic` | bool (False) | chọn J10-9/J10-10 hay J10-11/J10-12 |
| `gusset_K` | float (0.5 mặc định RAM/Manual cho gusset nối 2 cạnh; 0.65 cho single-edge/ chevron free edge; 1.2 corner-free) | |
| `weld_ductility_factor_UFM` | 1.25 | Manual Part 13 |
| `hss_Qf_include` | bool | |
| `ratio_limit` | 1.0 | cho phép đặt 0.95 |

## 10. Luồng tính trong một Joint

```
Joint.run(load_cases):
  validate_geometry()               # va chạm, thiếu dữ liệu, góc 0..90
  derive_geometry()                 # vị trí bu lông, chiều dài hàn, Whitmore…
  for lc in load_cases:
     forces = transform_member_forces(lc)     # về trục connection
     interface_forces = distribute(forces)    # UFM / couple method / Chapter K
     for conn in connections: checks += conn.check(interface_forces[conn])
     checks += support_member_checks(interface_forces)   # cột/dầm chính: J10, panel zone, web local
  checks += detailing_checks()      # không phụ thuộc tải
  return JointResult(...)
```

Design mode: `optimizer.design(joint, template)` duyệt danh sách ứng viên (sắp xếp theo khối lượng/ chi phí), cắt tỉa sớm theo check rẻ nhất (bu lông số lượng → kích thước bản → hàn), dừng ở ứng viên đầu tiên thỏa mọi check ≤ ratio_limit. Template YAML ví dụ:

```yaml
single_plate_default:
  bolt_d: [19.05, 22.225, 25.4]      # 3/4, 7/8, 1 in
  n_rows: [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
  s: 76.2
  Leh: [38.1, 50.8]
  Lev: [38.1]
  plate_t: [6.35, 7.94, 9.53, 11.11, 12.7, 15.88, 19.05]
  weld_size: "5/8 tp"                # quy tắc Manual Part 10
  a: 76.2
```
