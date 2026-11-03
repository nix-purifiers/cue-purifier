import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from .capture import capture
from .common import load, run
from .runtime import prepare


def locate(project=None, companion=None):
    root = Path(project or os.environ.get("CUE_PURIFIER_PROJECT", Path.cwd())).resolve()
    external = companion or os.environ.get("CUE_PURIFIER_LOCK")
    if external:
        return root, Path(external).resolve()
    if project or os.environ.get("CUE_PURIFIER_PROJECT"):
        return root, root / "cue-purifier.lock.json"
    for directory in [root, *root.parents]:
        if (directory / "cue-purifier.lock.json").exists():
            return directory, directory / "cue-purifier.lock.json"
    return root, root / "cue-purifier.lock.json"


def chdir_args(args):
    if args and args[0] in ("-C", "--chdir"):
        if len(args) < 2:
            raise ValueError("The native chdir option requires a directory")
        os.chdir(args[1])
        return args[2:]
    if args and args[0].startswith("--chdir="):
        os.chdir(args[0].split("=", 1)[1])
        return args[1:]
    return args


def main_impl():
    args = sys.argv[1:]
    if args and args[0] == "--native":
        rest = chdir_args(args[1:])
        root, companion = locate()
        original = os.environ["CUE_PURIFIER_ORIGINAL"]
        if not companion.exists():
            print(
                "cue-purifier: no lockfile; using ordinary impure cue", file=sys.stderr
            )
            os.execv(original, [original, *rest])
        words = [a for a in rest if not a.startswith("-")]
        if (
            len(words) > 1
            and words[0] == "mod"
            and words[1] in ("tidy", "get", "edit", "init", "fix", "rename")
        ):
            raise ValueError(
                "Change the native module manifest and run cue-purifier lock --update for dependency selection"
            )
        env = prepare(root, companion)
        if words[:2] == ["mod", "publish"]:
            run([original, "mod", "tidy", "--check"], cwd=root, env=env)
            env["CUE_REGISTRY"] = env["CUE_PURIFIER_REGISTRY"]
        os.execve(original, [original, *rest], env)
    parser = argparse.ArgumentParser(description="Lock native CUE modules into Nix")
    parser.add_argument(
        "action", choices=["lock", "prefetch", "exec", "bundle", "publish"]
    )
    parser.add_argument("--project", type=Path)
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--version", default="v0.1.0")
    parser.add_argument("--tag")
    opts, remaining = parser.parse_known_args(args)
    root, companion = locate(opts.project, opts.lock)
    if opts.action == "lock":
        if remaining:
            parser.error("Unexpected arguments: " + " ".join(remaining))
        capture(root, companion, opts.update, opts.input)
    elif opts.action in ("prefetch", "exec"):
        env = prepare(root, companion)
        if opts.action == "exec":
            if remaining and remaining[0] == "--":
                remaining = remaining[1:]
            if not remaining:
                parser.error("exec requires a command")
            env.update(CUE_PURIFIER_PROJECT=str(root), CUE_PURIFIER_LOCK=str(companion))
            os.execvpe(remaining[0], remaining, env)
    else:
        load(root, companion)
        expression = (
            "import "
            + json.dumps(
                os.environ["CUE_PURIFIER_SDK"] + "/lib/cue-purifier/nix/release.nix"
            )
            + " {root="
            + json.dumps(str(root))
            + ";lockFile="
            + json.dumps(str(companion))
            + ";version="
            + json.dumps(opts.version)
            + ";}"
        )
        result = run(
            [
                "nix",
                "build",
                "--impure",
                "--expr",
                expression,
                "--no-link",
                "--print-out-paths",
            ]
        )
        artifact = Path(result.strip()) / "cue-module.tar.gz"
        if opts.action == "bundle":
            print(artifact)
        else:
            if not opts.tag:
                parser.error("publish requires --tag")
            subprocess.run(
                [
                    os.environ.get("CUE_PURIFIER_GH", "gh"),
                    "release",
                    "upload",
                    opts.tag,
                    str(artifact),
                    "--clobber",
                ],
                cwd=root,
                check=True,
            )


def main():
    try:
        main_impl()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        print("cue-purifier: " + str(error), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
