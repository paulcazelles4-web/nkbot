# language: Python 3.11+
import zlib, base64
from pathlib import Path
raw = "".join(Path(__file__).with_name(f"y{i}.b64").read_text(encoding="utf-8") for i in range(26))
src = zlib.decompress(base64.b64decode(raw)).decode()
# hotfix: channel var is CCN, not CODE_CH
src = src.replace("#{CODE_CH}", "#{CCN}")
exec(compile(src, "bot.py", "exec"), globals())
