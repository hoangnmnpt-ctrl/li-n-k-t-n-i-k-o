"""
In cấu trúc file RAM Connection (.rcnx) ra file .txt: mỗi connection (ClassName, template, nút bấm, nút Joints)
và toàn bộ thuộc tính + bảng tải. Dùng để lập bảng map thông số tool → RAM cho loại liên kết mới (Base plate, Splice…).
File nguồn chỉ được ĐỌC (mode=ro):
    python tools/dump_rcnx.py "<đường dẫn .rcnx>" [file_ra.txt]
"""

import os
import sqlite3
import sys


def dump(src: str) -> str:
    db = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    out = [f"# {os.path.basename(src)}"]
    for t in ("ModelProperties", "ModelData_LoadConditions", "ConnectionObjects"):
        out.append(f"\n## {t}")
        out += [f"  {r}" for r in db.execute(f"select * from {t}")]
    jcols = [r[1] for r in db.execute("pragma table_info(Joints)")]
    joints = {r[jcols.index("JointID")]: dict(zip(jcols, r)) for r in db.execute("select * from Joints")}
    ccols = [r[1] for r in db.execute("pragma table_info(Cnx)")]
    for row in db.execute("select * from Cnx").fetchall():
        c = dict(zip(ccols, row))
        ref = c["CnxRef"]
        cls = db.execute(f'select PropertyValue from "{ref}" where PropertyName=\'ClassName\'').fetchone()
        out.append(f"\n\n## Cnx {c['CnxID']} — {cls[0] if cls else '?'}")
        out.append(f"  Cnx: {c}")
        out.append(f"  Joint: {joints.get(c['CnxID'])}")
        out.append("  Joints_Estados: " + str(db.execute("select * from Joints_Estados where Joints=?", (c["CnxID"],)).fetchall()))
        out.append("  ### Properties (PropertyName | PropertyType | PropertyValue)")
        out += [f"    {n} | {t} | {v}" for n, t, v in db.execute(f'select * from "{ref}"')]
        out.append("  ### Loads")
        out += [f"    {n} | {t} | {v}" for n, t, v in db.execute(f'select * from "{ref}_Loads"')]
    db.close()
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    txt = dump(sys.argv[1])
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(sys.argv[1])[0] + "_dump.txt"
    with open(dst, "w", encoding="utf-8") as f:
        f.write(txt)
    print(f"Đã ghi {dst}")
