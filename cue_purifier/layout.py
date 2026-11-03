"""Place readonly native module artifacts beside private mutable CUE locks."""

import json
from pathlib import Path
import sys


def install(cache, packages):
    cache = Path(cache)
    for record in packages:
        cue = record["cue"]
        package = Path(record["package"])
        for name, target in (
            (cue["extract"], package / "source"),
            (cue["download"] + ".mod", package / "module.cue"),
            (cue["download"] + ".zip", package / "archive.zip"),
        ):
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise ValueError("Unsafe native cache location")
            alias = cache / name
            alias.parent.mkdir(parents=True, exist_ok=True)
            if alias.is_symlink():
                if alias.resolve() != target.resolve():
                    raise ValueError("Private CUE cache differs from the Nix module")
            elif alias.exists():
                raise ValueError("Unexpected writable CUE module cache")
            else:
                alias.symlink_to(target.resolve(), target_is_directory=target.is_dir())


if __name__ == "__main__":
    install(sys.argv[1], json.loads(Path(sys.argv[2]).read_text()))
