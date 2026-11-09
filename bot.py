# language: Python 3.11+
from pathlib import Path
src = "".join(Path(__file__).with_name(f"q{i}.py").read_text(encoding="utf-8") for i in range(3))
exec(compile(src, "bot.py", "exec"), globals())
