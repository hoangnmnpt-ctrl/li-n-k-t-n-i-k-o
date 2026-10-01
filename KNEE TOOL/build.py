"""Gộp src/knee_engine.js vào src/knee_ui.html → Knee_AISC360-10.html (1 file, chạy offline)."""
from pathlib import Path

root = Path(__file__).parent
ui = (root / "src" / "knee_ui.html").read_text(encoding="utf-8")
engine = (root / "src" / "knee_engine.js").read_text(encoding="utf-8")
tag = '<script src="knee_engine.js"></script>'
assert tag in ui, "Không tìm thấy thẻ script engine trong UI"
out = ui.replace(tag, "<script>\n" + engine + "\n</script>")
(root / "Knee_AISC360-10.html").write_text(out, encoding="utf-8")
print("OK", len(out), "bytes")
