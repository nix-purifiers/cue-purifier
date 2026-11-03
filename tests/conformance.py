"""Use original CUE commands and native OCI packages on readonly Nix modules."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

repo = Path(__file__).resolve().parent.parent
sdk = Path(
    subprocess.check_output(
        ["nix", "build", str(repo) + "#", "--no-link", "--print-out-paths"], text=True
    ).strip()
)


def call(root, *args, env=None, expected=0):
    print("native", args, flush=True)
    result = subprocess.run(
        [sdk / "bin" / args[0], *args[1:]],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == expected, (args, result)
    return result


with tempfile.TemporaryDirectory(prefix="cue proof with spaces ") as temporary:
    temp = Path(temporary)
    root = temp / "project"
    shutil.copytree(repo / "examples/minimal", root)
    cache_home = temp / "xdg-cache"
    env = dict(
        os.environ,
        XDG_CACHE_HOME=str(cache_home),
        CUE_CACHE_DIR=str(temp / "poison"),
        CUE_REGISTRY="unlocked-host-registry.invalid",
    )
    assert json.loads(call(root, "cue", "export", env=env).stdout)["answer"] == 42
    source = root / "proof.cue"
    original = source.read_text()
    source.write_text(original.replace("answer: 42", "answer: 43"))
    assert json.loads(call(root, "cue", "export", env=env).stdout)["answer"] == 43
    source.write_text(original)
    assert json.loads(call(root, "cue", "export", env=env).stdout)["answer"] == 42
    call(root, "cue", "vet", "-c", env=env)
    call(root, "cue", "def", env=env)
    source.write_text(original.replace("port: 42", "port: 2147483648"))
    invalid = call(root, "cue", "vet", "-c", env=env, expected=1)
    assert (
        "2147483648" in invalid.stderr
        and "2147483647" in invalid.stderr
        and "proof.cue" in invalid.stderr
    ), invalid
    source.write_text(original)
    call(root, "cue", "fmt", env=env)
    profile = next(cache_home.glob("cue-purifier/*/*/environment-profile"))
    metadata = json.loads(profile.resolve().read_text())
    manifest = json.loads((Path(metadata["output"]) / "manifest.json").read_text())
    record = manifest["packages"][0]
    native_cache = profile.parent / "cache"
    alias = native_cache / record["cue"]["extract"]
    assert alias.is_symlink() and str(alias.resolve()).startswith("/nix/store/")
    refs = subprocess.check_output(
        ["nix-store", "-q", "--requisites", str(profile.resolve())], text=True
    )
    assert str(sdk) in refs and manifest["tree"] in refs
    native = next(
        Path(p) / "bin/cue" for p in refs.splitlines() if p.endswith("-cue-0.17.1")
    )
    helper = next(
        Path(p) / "bin/cue-purifier-native"
        for p in refs.splitlines()
        if p.endswith("-cue-purifier-native-0.17.1")
    )
    # Remove both source and cached archive: native none-registry mode fails closed.
    target = alias.resolve()
    archive_link = native_cache / (record["cue"]["download"] + ".zip")
    archive_target = archive_link.resolve()
    alias.unlink()
    archive_link.unlink()
    frozen = dict(os.environ, CUE_REGISTRY="none", CUE_CACHE_DIR=str(native_cache))
    missing = subprocess.run(
        [native, "export"], cwd=root, env=frozen, text=True, capture_output=True
    )
    assert missing.returncode and "cannot fetch" in missing.stderr, missing
    alias.symlink_to(target, target_is_directory=True)
    archive_link.symlink_to(archive_target)
    call(root, "cue", "mod", "tidy", env=env, expected=1)
    native_manifest = root / "cue.mod/module.cue"
    before = native_manifest.read_text()
    native_manifest.write_text(before + "\n// stale selection input\n")
    assert (
        "Selection inputs changed"
        in call(root, "cue", "export", env=env, expected=1).stderr
    )
    native_manifest.write_text(before)
    (root / "cue.mod/local-module.cue").write_text("deps: {}\n")
    assert "replacements" in call(root, "cue", "export", env=env, expected=1).stderr
    (root / "cue.mod/local-module.cue").unlink()
    assert (
        json.loads(call(temp, "cue", "-C", str(root), "export", env=env).stdout)[
            "answer"
        ]
        == 42
    )
    subdir = root / "subdir"
    subdir.mkdir()
    assert (
        json.loads(call(subdir, "cue", "export", "..", env=env).stdout)["answer"] == 42
    )
    companion = temp / "external.json"
    (root / "cue-purifier.lock.json").rename(companion)
    external = dict(
        env, CUE_PURIFIER_PROJECT=str(root), CUE_PURIFIER_LOCK=str(companion)
    )
    assert (
        json.loads(call(subdir, "cue", "export", "..", env=external).stdout)["answer"]
        == 42
    )
    archive = Path(
        call(root, "cue-purifier", "bundle", "--lock", str(companion)).stdout.strip()
    )
    fake_gh = temp / "fake-gh"
    fake_gh.write_text(
        "#!/usr/bin/env python3\nimport pathlib,sys\n"
        "assert sys.argv[1:4]==['release','upload','v0.1.0']\n"
        "pathlib.Path(__file__).with_suffix('.uploaded').write_bytes(pathlib.Path(sys.argv[4]).read_bytes())\n"
    )
    fake_gh.chmod(0o755)
    call(
        root,
        "cue-purifier",
        "publish",
        "--lock",
        str(companion),
        "--tag",
        "v0.1.0",
        env=dict(env, CUE_PURIFIER_GH=str(fake_gh)),
    )
    assert fake_gh.with_suffix(".uploaded").read_bytes() == archive.read_bytes()
    layout = temp / "oci"
    layout.mkdir()
    with tarfile.open(archive) as tar:
        tar.extractall(layout, filter="data")
    index = json.loads((layout / "index.json").read_text())
    digest = index["manifests"][0]["digest"]
    manifest_bytes = (layout / "blobs" / digest.replace(":", "/")).read_bytes()
    assert "sha256:" + hashlib.sha256(manifest_bytes).hexdigest() == digest
    published = json.loads(manifest_bytes)
    spec = {
        "module": "purifier.example/proof@v0",
        "version": "v0.1.0",
        "manifest": manifest_bytes.decode(),
        "manifestDigest": digest,
    }
    spec_file = temp / "published.json"
    spec_file.write_text(json.dumps(spec))
    module = temp / "ordinary-module"
    subprocess.run(
        [
            helper,
            "unpack",
            spec_file,
            layout / "blobs" / published["layers"][0]["digest"].replace(":", "/"),
            layout / "blobs" / published["layers"][1]["digest"].replace(":", "/"),
            module,
        ],
        check=True,
    )
    # A separate root consumes the native published CUE module with the original CLI.
    consumer = temp / "consumer"
    (consumer / "cue.mod").mkdir(parents=True)
    (consumer / "cue.mod/module.cue").write_text(
        'module:"consumer.example@v0"\nlanguage:version:"v0.17.0"\ndeps:"purifier.example/proof@v0":{v:"v0.1.0",default:true}\n'
    )
    consumer_source = consumer / "proof.cue"
    consumer_source.write_text(
        'package consumer\nimport "purifier.example/proof"\nanswer:proof.answer\n'
    )
    for name, target in [
        ("mod/extract/purifier.example/proof@v0.1.0", module / "source"),
        ("mod/download/purifier.example/proof/@v/v0.1.0.mod", module / "module.cue"),
        ("mod/download/purifier.example/proof/@v/v0.1.0.zip", module / "archive.zip"),
    ]:
        path = native_cache / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target, target_is_directory=target.is_dir())
    output = subprocess.check_output(
        [native, "export"], cwd=consumer, env=frozen, text=True
    )
    assert json.loads(output)["answer"] == 42
    consumer_source.write_text(
        'package consumer\nimport "purifier.example/proof"\nanswer:43 & proof.answer\n'
    )
    conflict = subprocess.run(
        [native, "export"], cwd=consumer, env=frozen, text=True, capture_output=True
    )
    assert conflict.returncode and "42" in conflict.stderr and "43" in conflict.stderr
    # Native publication retains the user's chosen root registry and exact OCI content.
    publication = dict(
        external, CUE_REGISTRY="purifier.example/proof=registry.invalid,none"
    )
    native_oci = temp / "native-oci"
    call(
        root,
        "cue",
        "mod",
        "publish",
        "v0.1.0",
        "--out",
        str(native_oci),
        env=publication,
    )
    native_index = json.loads((native_oci / "index.json").read_text())
    assert native_index["manifests"][0]["digest"] == digest
    fallback = temp / "fallback"
    fallback.mkdir()
    assert "ordinary impure" in call(fallback, "cue", "version").stderr
    fake = temp / "fake-native"
    fake.write_text("#!/bin/sh\nprintf native-out\nprintf native-err >&2\nexit 7\n")
    fake.chmod(0o755)
    direct = dict(
        os.environ,
        PYTHONPATH=str(sdk / "lib/cue-purifier"),
        CUE_PURIFIER_ORIGINAL=str(fake),
    )
    result = subprocess.run(
        ["python3", "-m", "cue_purifier.cli", "--native"],
        cwd=fallback,
        env=direct,
        text=True,
        capture_output=True,
    )
    assert (
        result.returncode == 7
        and result.stdout == "native-out"
        and result.stderr.endswith("native-err")
    ), result
print(
    "Native CUE export/vet/def, immutable schemas, OCI consumer/publication, source edits, GC and fallback passed"
)
