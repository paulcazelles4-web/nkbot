# language: Python 3.11+
# stable bootstrap — full single-file bot from known-good commit
import urllib.request, sys, traceback
URL = "https://raw.githubusercontent.com/paulcazelles4-web/nkbot/928b3d81b79485750d25eb931e7aeafcbfbb2c2c/bot.py"
try:
    code = urllib.request.urlopen(URL, timeout=30).read().decode("utf-8")
    if "commands.Bot" not in code or len(code) < 1000:
        raise RuntimeError(f"bad payload len={len(code)}")
    exec(compile(code, "bot.py", "exec"), globals())
except Exception:
    traceback.print_exc()
    print("BOOTSTRAP FAILED", file=sys.stderr)
    raise
