import json
import sys
import time
from pathlib import Path

try:
    data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
except Exception:
    data = {"error": "bad stdin"}
p = Path(__file__).resolve().parent.parent / "spike" / "hooklog.jsonl"
p.parent.mkdir(exist_ok=True)
with open(p, "a", encoding="utf-8") as f:
    f.write(json.dumps({"ts": time.time(), "raw": data}, ensure_ascii=False) + "\n")
sys.exit(0)
