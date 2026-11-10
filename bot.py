# language: Python 3.11+
import zlib, base64
from pathlib import Path
raw = "".join(Path(__file__).with_name(f"c{i}.txt").read_text(encoding="utf-8") for i in range(20))
exec(compile(zlib.decompress(base64.b64decode(raw)), "bot.py", "exec"), globals())
