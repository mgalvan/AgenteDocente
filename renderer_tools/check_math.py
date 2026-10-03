"""Offline build check: fail deployment build if math dependencies are missing."""
import base64
import json
from pathlib import Path
import subprocess

formula = r"\begin{cases}x+y+z=6\\2x-y+z=3\\3x+2y-z=4\end{cases}"
result = subprocess.run(
    ["node", str(Path(__file__).with_name("formula.cjs"))],
    input=json.dumps({"latex": formula}), text=True, capture_output=True, timeout=30,
)
if result.returncode:
    raise RuntimeError(result.stderr)
data = json.loads(result.stdout)
assert "<svg" in data["svg"] and base64.b64decode(data["png"]).startswith(b"\x89PNG\r\n\x1a\n")
assert data["width"] > 0 and data["height"] > 0
print("Rendering matematico SVG e PNG: OK")
