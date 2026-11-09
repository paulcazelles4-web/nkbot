# language: Python 3.11+
from pathlib import Path
raw = bytes.fromhex("".join(Path(__file__).with_name(f"h{i}.txt").read_text(encoding="utf-8") for i in range(8)))
exec(compile(raw.decode("utf-8"), "bot.py", "exec"), globals())
