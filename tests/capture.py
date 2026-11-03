"""Use native public resolution and a native registry to test actual MVS."""

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request

repo = Path(__file__).resolve().parent.parent
sdk = Path(
    subprocess.check_output(
        ["nix", "build", str(repo) + "#", "--no-link", "--print-out-paths"], text=True
    ).strip()
)


def call(root, *args, env):
    result = subprocess.run(
        [sdk / "bin" / args[0], *args[1:]],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=300,
    )
    assert result.returncode == 0, result
    return result.stdout


with tempfile.TemporaryDirectory(prefix="cue native capture ") as temporary:
    temp = Path(temporary)
    root = temp / "public"
    shutil.copytree(repo / "examples/minimal", root)
    env = dict(
        os.environ,
        XDG_CACHE_HOME=str(temp / "xdg-cache"),
        CUE_CACHE_DIR=str(temp / "native-cache"),
    )
    companion = root / "cue-purifier.lock.json"
    original = json.loads(companion.read_text())
    companion.unlink()
    call(root, "cue-purifier", "lock", env=env)
    assert json.loads(companion.read_text())["entries"] == original["entries"]
    before = companion.read_bytes()
    call(root, "cue-purifier", "lock", env=env)
    assert companion.read_bytes() == before
    assert json.loads(call(root, "cue", "export", env=env))["answer"] == 42
    empty = temp / "empty"
    (empty / "cue.mod").mkdir(parents=True)
    (empty / "cue.mod/module.cue").write_text(
        'module:"empty.example@v0"\nlanguage:version:"v0.17.0"\n'
    )
    (empty / "proof.cue").write_text("package proof\nanswer:42\n")
    call(empty, "cue-purifier", "lock", env=env)
    assert json.loads((empty / "cue-purifier.lock.json").read_text())["entries"] == []
    assert json.loads(call(empty, "cue", "export", env=env))["answer"] == 42

    # Native publishing + resolving: an old transitive requirement must lose to
    # the newer direct version, without our wrapper choosing versions itself.
    fixture = temp / "fixture"
    fixture.mkdir()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    address = f"127.0.0.1:{port}"
    server_log = (temp / "registry.log").open("w")
    server = subprocess.Popen(
        [sdk / "bin/cue", "mod", "registry", address],
        cwd=fixture,
        stdout=server_log,
        stderr=server_log,
    )
    local = dict(
        env,
        CUE_REGISTRY=address + "+insecure",
        CUE_CACHE_DIR=str(temp / "registry-cache"),
    )

    def module(name, version, code, deps=""):
        directory = fixture / name
        (directory / "cue.mod").mkdir(parents=True, exist_ok=True)
        (directory / "cue.mod/module.cue").write_text(
            f'module:"proof.example/{name}@v0"\nlanguage:version:"v0.17.0"\nsource:kind:"self"\n'
            + deps
        )
        (directory / "schema.cue").write_text(code)
        call(directory, "cue", "mod", "tidy", env=local)
        call(directory, "cue", "mod", "publish", version, env=local)

    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(50):
            try:
                with opener.open("http://" + address + "/v2/", timeout=1):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise AssertionError("native CUE registry did not start")
        module("base", "v0.0.1", "package base\n#Answer:42\n")
        module("base", "v0.0.2", "package base\n#Answer:43\n")
        module(
            "template",
            "v0.0.1",
            'package template\nimport "proof.example/base"\n#Answer:base.#Answer\n',
            'deps:"proof.example/base@v0":{v:"v0.0.1",default:true}\n',
        )
        consumer = fixture / "consumer"
        (consumer / "cue.mod").mkdir(parents=True)
        (consumer / "cue.mod/module.cue").write_text(
            'module:"proof.example/consumer@v0"\nlanguage:version:"v0.17.0"\ndeps:{"proof.example/base@v0":{v:"v0.0.2",default:true},"proof.example/template@v0":{v:"v0.0.1",default:true}}\n'
        )
        source = consumer / "proof.cue"
        source.write_text(
            'package proof\nimport (\n"proof.example/base"\n"proof.example/template"\n)\nanswer:template.#Answer\ndirect:base.#Answer\n'
        )
        call(consumer, "cue-purifier", "lock", env=local)
        data = json.loads((consumer / "cue-purifier.lock.json").read_text())
        assert [(e["cue"]["module"], e["cue"]["version"]) for e in data["entries"]] == [
            ("proof.example/base@v0", "v0.0.2"),
            ("proof.example/template@v0", "v0.0.1"),
        ]
        assert json.loads(call(consumer, "cue", "export", env=local)) == {
            "answer": 43,
            "direct": 43,
        }
        source.write_text(
            source.read_text().replace(
                "answer:template.#Answer", "answer:template.#Answer + 1"
            )
        )
        assert json.loads(call(consumer, "cue", "export", env=local))["answer"] == 44
    finally:
        server.terminate()
        server.wait(timeout=5)
        server_log.close()
print(
    "Native CUE public capture, empty workspace and transitive MVS through Nix modules passed"
)
