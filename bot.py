# language: Python 3.11+
import zlib, base64
from pathlib import Path
raw = "".join(Path(__file__).with_name(f"y{i}.b64").read_text(encoding="utf-8") for i in range(26))
src = zlib.decompress(base64.b64decode(raw)).decode()
repls = eval(zlib.decompress(base64.b64decode(Path(__file__).with_name("patches.b64").read_text())).decode())
for a,b in repls:
    src = src.replace(a,b)
exec(compile(src, "bot.py", "exec"), globals())
