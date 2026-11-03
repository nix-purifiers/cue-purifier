import fcntl
import hashlib
import json
import os
from pathlib import Path

from .common import environment, load, run
from .layout import install


def prepare(root, companion):
    data = load(root, companion)
    generation = hashlib.sha256(
        companion.read_bytes() + os.environ["CUE_PURIFIER_SDK"].encode()
    ).hexdigest()[:20]
    project_key = hashlib.sha256(str(root).encode()).hexdigest()[:20]
    cache_home = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    state = cache_home / "cue-purifier" / project_key / generation
    state.mkdir(parents=True, exist_ok=True)
    expression = (
        "import "
        + json.dumps(
            os.environ["CUE_PURIFIER_SDK"] + "/lib/cue-purifier/nix/realize.nix"
        )
        + " {root="
        + json.dumps(str(root))
        + ";lockFile="
        + json.dumps(str(companion))
        + ";sdk="
        + json.dumps(os.environ["CUE_PURIFIER_SDK"])
        + ";}"
    )
    profile = Path(
        run(
            [
                "nix",
                "build",
                "--impure",
                "--expr",
                expression,
                "--out-link",
                str(state / "environment-profile"),
                "--print-out-paths",
            ]
        ).strip()
    )
    manifest = json.loads(
        (Path(json.loads(profile.read_text())["output"]) / "manifest.json").read_text()
    )
    if manifest["sdk"] != data["sdk"]:
        raise ValueError("Prepared CUE SDK differs from the lock")
    env = environment(state, frozen=True)
    with (state / "initialization.lock").open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        install(env["CUE_CACHE_DIR"], manifest["packages"])
    run(
        [os.environ["CUE_PURIFIER_HELPER"], "check", str(root), str(companion)], env=env
    )
    env["PATH"] = (
        str(Path(os.environ["CUE_PURIFIER_SDK"]) / "bin") + os.pathsep + env["PATH"]
    )
    return env
