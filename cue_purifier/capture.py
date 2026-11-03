import json
import os
from pathlib import Path
import tempfile

from .common import environment, inputs, load, run, write


def capture(root, companion, update=False, extra=()):
    if companion.exists() and not update:
        load(root, companion)
        return
    previous = json.loads(companion.read_text()) if companion.exists() else {}
    extra = list(extra or previous.get("extraInputs", []))
    helper = os.environ["CUE_PURIFIER_HELPER"]
    run([helper, "inspect", str(root)])
    with tempfile.TemporaryDirectory(prefix="cue-capture-") as temporary:
        state = Path(temporary)
        env = environment(state)
        run([os.environ["CUE_PURIFIER_ORIGINAL"], "mod", "tidy"], cwd=root, env=env)
        graph = json.loads(run([helper, "graph", str(root)], env=env))
        entries = []
        for i, cue in enumerate(graph["entries"]):
            spec = state / (str(i) + ".json")
            spec.write_text(json.dumps(cue))
            package = state / ("package-" + str(i))
            prefix = Path(env["CUE_CACHE_DIR"]) / cue["download"]
            run(
                [
                    helper,
                    "unpack",
                    str(spec),
                    str(prefix) + ".zip",
                    str(prefix) + ".mod",
                    str(package),
                ]
            )
            nar = run(["nix", "hash", "path", str(package)]).strip()
            location = cue["location"]
            entries.append(
                {
                    "path": "modules/" + cue["extract"].removeprefix("mod/extract/"),
                    "url": "oci:"
                    + location["Host"]
                    + "/"
                    + location["Repository"]
                    + "@"
                    + cue["manifestDigest"],
                    "hash": nar,
                    "mirrors": [],
                    "cue": cue,
                }
            )
        data = {
            "version": 1,
            "purifier": "cue",
            "sdk": os.environ["CUE_PURIFIER_SDK_VERSION"],
            "native": graph["native"],
            "entries": entries,
            "extraInputs": extra,
            "inputs": inputs(root, extra),
        }
        write(companion, json.dumps(data, indent=2, sort_keys=True) + "\n")
