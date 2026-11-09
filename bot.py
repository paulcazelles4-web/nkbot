# language: Python 3.11+
import zlib, base64
from pathlib import Path
parts = []
for i in range(3):
    parts.append(Path(__file__).with_name(f"c{i}.txt").read_text(encoding="utf-8"))
code = zlib.decompress(base64.b64decode("".join(parts))).decode()
exec(compile(code, "bot.py", "exec"), globals())
