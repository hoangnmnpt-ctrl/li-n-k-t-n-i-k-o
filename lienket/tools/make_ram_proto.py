"""
Tạo file khuôn ram_proto.rcnx từ một file .rcnx có sẵn của RAM Connection: giữ 1 connection cho mỗi loại tool xuất được
(Knee MEPlateKneeBCF, chân cột BasePlate, nối dầm / apex MEPlateBeamSplice), bỏ mọi connection khác.
File nguồn chỉ được ĐỌC (mode=ro). Chạy lại khi đổi phiên bản RAM Connection:
    python tools/make_ram_proto.py "<đường dẫn .rcnx>" [Class=CnxID ...]
ví dụ: python tools/make_ram_proto.py RAM.rcnx Bentley.AISC.BasePlate=1 Bentley.AISC.MEPlateBeamSplice=20
"""

import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "ram_proto.rcnx")
CLASSES = ("Bentley.AISC.MEPlateKneeBCF", "Bentley.AISC.BasePlate", "Bentley.AISC.MEPlateBeamSplice")


def main(src: str, want: dict | None = None, out: str = OUT):
    want = want or {}
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    if os.path.exists(out):
        os.remove(out)
    d = sqlite3.connect(out)
    s.backup(d)
    s.close()
    rows = d.execute("select CnxRef, CnxJoint, CnxID from Cnx order by CnxJoint").fetchall()
    keep = {}
    for ref, joint, cid in rows:
        cls = d.execute(f'select PropertyValue from "{ref}" where PropertyName=\'ClassName\'').fetchone()
        cls = cls[0] if cls else ""
        if cls in CLASSES and cls not in keep and want.get(cls, cid) == cid:
            keep[cls] = (ref, cid)
    miss = [c for c in CLASSES if c not in keep]
    if miss:
        print("Thiếu khuôn:", ", ".join(miss))
    refs = {r for r, _ in keep.values()}
    ids = [c for _, c in keep.values()]
    for r, _j, _c in rows:
        if r not in refs:
            d.execute(f'drop table if exists "{r}"')
            d.execute(f'drop table if exists "{r}_Loads"')
    d.execute(f"delete from Cnx where CnxID not in ({','.join('?' for _ in ids)})", ids)
    d.execute(f"delete from Joints where JointID not in ({','.join('?' for _ in ids)})", ids)
    d.execute(f"delete from Joints_Estados where Joints not in ({','.join('?' for _ in ids)})", ids)
    # CnxJoint = số thứ tự dòng của nút trong bảng Joints (1…); JointID = CnxID
    for i, (cid,) in enumerate(d.execute("select CnxID from Cnx order by CnxJoint").fetchall(), 1):
        d.execute("update Cnx set CnxJoint=? where CnxID=?", (i, cid))
    d.execute("delete from ConnectionObjects where PropertyName != 'ConnectionVersion'")
    for i, (ref,) in enumerate(d.execute("select CnxRef from Cnx order by CnxJoint").fetchall(), 1):
        d.execute("insert into ConnectionObjects values (?, 0, ?)", (str(i), ref))
    d.execute("drop table if exists Thumbnail")
    d.commit()
    d.execute("vacuum")
    d.commit()
    print("OK ->", out.encode("ascii", "replace").decode())
    for cls, (ref, cid) in keep.items():
        print(f"  {cls}: CnxID {cid} {ref}")
    d.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1], {k: int(v) for k, v in (a.split("=", 1) for a in sys.argv[2:])})
