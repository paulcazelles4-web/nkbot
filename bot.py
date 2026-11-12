# language: Python 3.11+
from pathlib import Path
_p = Path(__file__).resolve().parent
exec(compile((_p/"part1.py.txt").read_text(encoding="utf-8")+(_p/"part2.py.txt").read_text(encoding="utf-8"), "bot.py", "exec"), globals())
