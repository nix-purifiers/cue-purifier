import hashlib
import json
import os
from pathlib import Path
import subprocess


def run(args, **kwargs):
    result = subprocess.run(args, text=True, capture_output=True, **kwargs)
    if result.returncode:
        raise ValueError(result.stdout + result.stderr)
    return result.stdout


def write(path, text):
    path = Path(path)
    if path.is_file() and path.read_text() == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text)
    temporary.replace(path)


def inputs(root, extra):
    result = {}
    for name in sorted(set(["cue.mod/module.cue", *extra])):
        path = root / name
        if (
            Path(name).is_absolute()
            or ".." in Path(name).parts
            or not path.is_file()
            or path.is_symlink()
        ):
            raise ValueError("Selection inputs must be regular project files")
        result[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return result


def environment(state, frozen=False):
    env = dict(os.environ)
    cache = state / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    registry = env.get("CUE_REGISTRY", "")
    if registry == "none":
        registry = env.get("CUE_PURIFIER_REGISTRY", "none")
    env.update(CUE_CACHE_DIR=str(cache), CUE_PURIFIER_REGISTRY=registry)
    if frozen:
        env["CUE_REGISTRY"] = "none"
    return env


def load(root, companion):
    data = json.loads(companion.read_text())
    if data.get("version") != 1 or data.get("purifier") != "cue":
        raise ValueError("Unsupported CUE lock")
    if data["sdk"] != os.environ["CUE_PURIFIER_SDK_VERSION"]:
        raise ValueError("CUE frontend SDK changed; update the lock")
    if inputs(root, data["extraInputs"]) != data["inputs"]:
        raise ValueError("Selection inputs changed; update the lock")
    native = json.loads(run([os.environ["CUE_PURIFIER_HELPER"], "inspect", str(root)]))
    if native != data["native"]:
        raise ValueError("Native CUE metadata differs from the lock")
    for entry in data["entries"]:
        cue = entry["cue"]
        for name in (entry["path"], cue["extract"], cue["download"]):
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise ValueError("Unsafe CUE module cache path")
        if hashlib.sha256(cue["manifest"].encode()).hexdigest() != cue[
            "manifestDigest"
        ].removeprefix("sha256:"):
            raise ValueError("CUE OCI manifest digest differs from the lock")
    return data
