"""Re-fetch immutable OCI blobs and reproduce the actual native module package."""

import json
from pathlib import Path
import subprocess

repo = Path(__file__).resolve().parent.parent
system = subprocess.check_output(
    ["nix", "eval", "--impure", "--raw", "--expr", "builtins.currentSystem"], text=True
).strip()
output = subprocess.check_output(
    [
        "nix",
        "build",
        "--no-link",
        "--print-out-paths",
        str(repo) + "#checks." + system + ".environment",
    ],
    text=True,
).strip()
manifest = json.loads((Path(output) / "manifest.json").read_text())
for record in manifest["packages"]:
    module = Path(record["package"]).resolve()
    drv = subprocess.check_output(
        ["nix-store", "-q", "--deriver", str(module)], text=True
    ).strip()
    subprocess.run(["nix-store", "--realise", drv, "--check"], check=True)
print("Immutable CUE OCI blobs and native module extraction reproduced identically")
