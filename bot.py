# language: Python 3.11+
from pathlib import Path
_p=Path(__file__).resolve().parent
src="".join((_p/f"s{i}.py.txt").read_text(encoding="utf-8") for i in range(4))
exec(compile(src,"bot.py","exec"),globals())
