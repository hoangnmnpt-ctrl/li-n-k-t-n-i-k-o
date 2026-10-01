"""
Tạo file khuôn ram_proto.rcnx (1 knee MEPlateKneeBCF) từ một file .rcnx có sẵn của RAM Connection.
File nguồn chỉ được ĐỌC (mode=ro). Chạy lại khi đổi phiên bản RAM Connection:
    python tools/make_ram_proto.py "<đường dẫn .rcnx>" [CnxID]
"""

import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "ram_proto.rcnx")


def main(src: str, cnx_id: int | None = None):
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    if os.path.exists(OUT):
        os.remove(OUT)
    d = sqlite3.connect(OUT)
    s.backup(d)
    s.close()
    rows = d.execute("select CnxRef, CnxJoint, CnxID from Cnx").fetchall()
    knee = None
    for ref, joint, cid in rows:
        cls = d.execute(f'select PropertyValue from "{ref}" where PropertyName=\'ClassName\'').fetchone()
        if cls and cls[0] == "Bentley.AISC.MEPlateKneeBCF" and (cnx_id is None or cid == cnx_id):
            knee = (ref, joint, cid)
            break
    if not knee:
        raise SystemExit("Không tìm thấy connection MEPlateKneeBCF trong file nguồn.")
    ref, joint, cid = knee
    for r, _j, _c in rows:
        if r != ref:
            d.execute(f'drop table if exists "{r}"')
            d.execute(f'drop table if exists "{r}_Loads"')
    d.execute("delete from Cnx where CnxRef != ?", (ref,))
    # CnxJoint = số thứ tự dòng của nút trong bảng Joints; JointID của nút = CnxID
    d.execute("delete from Joints where JointID != ?", (cid,))
    d.execute("delete from Joints_Estados where Joints != ?", (cid,))
    d.execute("delete from ConnectionObjects where PropertyName != 'ConnectionVersion'")
    d.execute("insert into ConnectionObjects values ('1', 0, ?)", (ref,))
    d.execute("drop table if exists Thumbnail")
    d.commit()
    d.execute("vacuum")
    d.commit()
    print("OK ->", OUT.encode("ascii", "replace").decode(), "| proto:", ref, "joint", joint)
    print("Joints_Estados cols:", [r[1] for r in d.execute("pragma table_info(Joints_Estados)")])
    print("JE row:", d.execute("select * from Joints_Estados").fetchall())
    print("Cnx:", d.execute("select * from Cnx").fetchall(), [r[1] for r in d.execute("pragma table_info(Cnx)")])
    print("tables:", [r[0] for r in d.execute("select name from sqlite_master where type='table'")])
    d.close()


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else None)
