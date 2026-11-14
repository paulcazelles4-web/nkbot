# language: Python 3.11+
import zlib, base64
from pathlib import Path
_p = "".join(Path(__file__).with_name(f"u{i}.b64").read_text(encoding="utf-8") for i in range(38))
src = zlib.decompress(base64.b64decode(_p)).decode()
exec(open(__file__).read().split('exec(compile')[0].replace('src = zlib.decompress(base64.b64decode(_p)).decode()','pass') if False else '')
