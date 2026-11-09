# language: Python 3.11+
from pathlib import Path
src = "".join(Path(__file__).with_name(f"s{i}.txt").read_text(encoding="utf-8") for i in range(16))
exec(compile(src, "bot.py", "exec"), globals())
