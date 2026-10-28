"""
project.py — Dự án gồm nhiều nút (joint) như RAM Connection: mỗi nút có ID, loại (knee | splice | base) và toàn bộ thông số.
Lưu một file JSON (*.lkt). Dùng chung cho cửa sổ chính app.py.
"""

from __future__ import annotations

import copy
import json
import os

import base_defaults as BD
import base_drawing as BDR
import base_engine as BE
import base_report as BR
import defaults as KD
import drawing as KDR
import engine as K
import report as KR
import splice_defaults as SD
import splice_drawing as SDR
import splice_engine as SE
import splice_report as SR

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PATH = os.path.join(HERE, "du_an.lkt")
LEGACY = [("knee", os.path.join(HERE, "knee_saved.json")), ("splice", os.path.join(HERE, "splice_saved.json"))]

KNEE_TYPE = {"dung": "Knee đứng", "ngang": "Knee ngang", "xien": "Knee xiên"}
SPLICE_TYPE = {"straight": "Beam splice", "apex": "Apex"}

# loại nút → hàm tính, mặc định, vẽ, báo cáo
KINDS = {
    "knee": dict(family="BCF", compute=K.compute, base=KD.BASE, merge=KD.merge, presets=KD.PRESETS, auto=K.auto_design,
                 elevation=KDR.elevation, face=KDR.plate_face, report=KR, prefix="K", normalize=K.normalize),
    "splice": dict(family="BS", compute=SE.compute, base=SD.BASE, merge=SD.merge, presets=SD.PRESETS, auto=SE.auto_design,
                   elevation=SDR.elevation, face=SDR.plate_face, report=SR, prefix="BS", normalize=SE.normalize),
    "base": dict(family="CB", compute=BE.compute, base=BD.BASE, merge=BD.merge, presets=BD.PRESETS, auto=BE.auto_design,
                 elevation=BDR.elevation, face=BDR.plate_face, report=BR, prefix="CB", normalize=BE.normalize),
}


def joint_key(kind: str, st: dict) -> str:
    """Khoá kiểu nút của hộp thoại New joint: knee | splice:straight | splice:apex | base."""
    return f"splice:{st.get('type', 'straight')}" if kind == "splice" else kind


def kind_of(key: str) -> str:
    return "splice" if key.startswith("splice") else key


def apply_auto(kind: str, st: dict, res: dict):
    """Ghi kết quả Smart connection / Optimize (tp, đường kính bu lông / neo) vào state."""
    if kind == "knee": st["plate"]["tp"] = res["tp"]
    elif kind == "splice": st["plate"]["tp1"] = st["plate"]["tp2"] = res["tp"]
    else:
        st["plate"].update({k: res[k] for k in ("tp", "N", "B") if k in res})
        st["anchor"].update({k: res[k] for k in ("ex", "ey", "hef", "grade", "layout", "nr", "npr") if k in res})
        if "D" in res:
            st["weld"]["D"] = res["D"]
            for k in ("fl", "web"):
                st["weld"].setdefault(k, {})["D"] = res["D"]
    (st["anchor"] if kind == "base" else st["bolt"])["d"] = res["d"]


def full_state(j: dict) -> dict:
    k = KINDS[j["kind"]]
    return k["merge"](k["base"], j["state"])


def evaluate(j: dict, loads: list | None = None):
    """(state đã chuẩn hoá, kết quả) — loads: chỉ tính các tổ hợp này (None = tất cả)."""
    st = full_state(j)
    if loads is not None:
        st["loads"] = loads
    R = KINDS[j["kind"]]["compute"](st)
    return st, R


def type_label(j: dict) -> str:
    st = j["state"]
    if j["kind"] == "knee":
        align = (st.get("plate") or {}).get("alignment", "vertical")
        return {"vertical": "Knee đứng", "perpendicular": "Knee xiên", "horizontal": "Knee ngang", "bisector": "Knee xiên"}.get(align, "Knee")
    if j["kind"] == "base":
        return "Column base"
    return SPLICE_TYPE.get(st.get("type", "straight"), "Beam splice")


def members_text(j: dict) -> str:
    st = full_state(j)
    if j["kind"] == "knee":
        return f"Kèo {st['beam']['sec']} · Cột {st['col']['sec']}"
    if j["kind"] == "base":
        return f"Cột {st['col']['sec']}"
    b1, b2 = st["beam1"]["sec"], st["beam2"]["sec"]
    return b1 if st["beam2"].get("same", True) or b1 == b2 else f"{b1} | {b2}"


def connection_text(j: dict) -> str:
    st = full_state(j)
    p = st["plate"]
    if j["kind"] == "base":
        a = st["anchor"]
        return f"Bản đế {p['N']:g}×{p['B']:g}×{p['tp']:g} · {neo_count(a)} neo {BE.anchor_label(a['d'])} {a['grade']}"
    tp = p.get("tp") if j["kind"] == "knee" else (f"{p['tp1']:g}" if p["tp1"] == p["tp2"] else f"{p['tp1']:g}/{p['tp2']:g}")
    return f"Bản {tp} · M{st['bolt']['d']} {st['bolt']['grade']}"


def neo_count(a: dict) -> int:
    return 2 * max(int(a.get("nr", 1)), 1) * max(int(a.get("npr", 2)), 1)


class Project:
    def __init__(self, path: str | None = None):
        self.path = path
        self.joints: list[dict] = []
        self.dirty = False

    # ---------------------------------------------------------------- file
    @classmethod
    def load(cls, path: str) -> "Project":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        p = cls(path)
        p.joints = [dict(id=int(j["id"]), kind=j["kind"], state=j["state"]) for j in data.get("joints", []) if j.get("kind") in KINDS]
        return p

    def save(self, path: str | None = None):
        path = path or self.path or DEFAULT_PATH
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dict(app="LienKet", version=1, joints=self.joints), f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
        self.path, self.dirty = path, False

    def import_legacy(self) -> int:
        """Nhập danh sách đã lưu của tool cũ (knee_saved.json, splice_saved.json) nếu có."""
        n = 0
        for kind, path in LEGACY:
            try:
                with open(path, encoding="utf-8") as f:
                    items = json.load(f)
            except (OSError, ValueError):
                continue
            for it in items if isinstance(items, list) else []:
                st = it.get("state") or {}
                st.setdefault("name", it.get("name", ""))
                self.add(kind, st); n += 1
        return n

    # ---------------------------------------------------------------- nút
    def next_id(self) -> int:
        return max((j["id"] for j in self.joints), default=0) + 1

    def add(self, kind: str, state: dict) -> dict:
        jid = self.next_id()
        k = KINDS[kind]
        st = k["merge"](k["base"], state)          # lưu đủ thông số (kể cả tải mặc định)
        if not state.get("name"):                  # tên mặc định theo ID (bỏ tên mẫu trong BASE)
            st["name"] = f"{KINDS[kind]['prefix']}-{jid:02d}"
        st.setdefault("group", "Joints")
        j = dict(id=jid, kind=kind, state=st)
        self.joints.append(j); self.dirty = True
        return j

    def get(self, jid: int) -> dict | None:
        return next((j for j in self.joints if j["id"] == jid), None)

    def update(self, jid: int, state: dict):
        j = self.get(jid)
        if j:
            j["state"] = copy.deepcopy(state); self.dirty = True

    def delete(self, jid: int):
        self.joints = [j for j in self.joints if j["id"] != jid]; self.dirty = True

    def clear(self):
        self.joints = []; self.dirty = True

    def copy_joint(self, jid: int) -> dict | None:
        j = self.get(jid)
        if not j: return None
        st = copy.deepcopy(j["state"]); st["name"] = (st.get("name") or "") + " (copy)"
        return self.add(j["kind"], st)
