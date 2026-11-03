"""Inspect all fetches without IFD and reject stale selection/OCI metadata."""

import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

repo = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary) / "project"
    shutil.copytree(repo / "examples/minimal", root)
    companion = root / "cue-purifier.lock.json"
    original = json.loads(companion.read_text())

    def inspect():
        expression = f"let f=builtins.getFlake {json.dumps(str(repo))};lock=f.lib.cue-purifier.readLock {{src=/. + {json.dumps(str(root))};}};in {{inherit(lock)problems outputs;}}"
        return json.loads(
            subprocess.check_output(
                [
                    "nix",
                    "eval",
                    "--impure",
                    "--json",
                    "--option",
                    "allow-import-from-derivation",
                    "false",
                    "--expr",
                    expression,
                ],
                text=True,
            )
        )

    assert inspect()["problems"] == []
    assert inspect()["outputs"]["packages"] == ["default", "environment", "project"]
    companion.unlink()
    assert inspect()["problems"]
    for mutation in [
        lambda d: d.update(purifier="other"),
        lambda d: d["entries"][0].update(hash="invalid"),
        lambda d: d["entries"][0].update(path="../escape"),
        lambda d: d["entries"][0]["cue"].update(manifest="{}"),
        lambda d: d.update(sdk=None),
    ]:
        data = copy.deepcopy(original)
        mutation(data)
        companion.write_text(json.dumps(data))
        assert inspect()["problems"]
    companion.write_text(json.dumps(original))
    local = root / "cue.mod/local-module.cue"
    local.write_text("deps:{}\n")
    assert inspect()["problems"]
    local.unlink()
    (root / "cue.mod/module.cue").write_text("// stale\n")
    assert inspect()["problems"]
print("Native CUE lock protocol and immutable OCI binding passed without IFD")
