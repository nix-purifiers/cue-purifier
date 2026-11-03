# cue-purifier

Locked, Nix-resolved modules for CUE.

## Quickstart

```sh
nix shell 'github:nix-purifiers/cue-purifier'
cue-purifier lock
cue vet -c
cue export
```

CUE's native resolver selects the modules. Nix fetches their immutable OCI
manifests and blobs, and supplies their native module caches as readonly sources.
Your working tree stays mutable.

Commit `cue.mod/module.cue` and `cue-purifier.lock.json`. Source edits do not
require relocking. After changing dependency selection:

```sh
cue-purifier lock --update
```

The wrapper warns and runs ordinary, impure CUE when there is no purifier lock.
Invalid or stale locks fail. Install it through your normal Nix configuration if
you want it available beyond the temporary shell.

## Development

```sh
cue fmt
cue def
cue-purifier exec -- your-editor
cue-purifier prefetch
```

Private caches and SDK profiles use `XDG_CACHE_HOME`. CUE reads dependency sources
from the Nix store, with registry fetching disabled. User-defined workflows keep
their ordinary network access. Native `cue mod publish` checks the locked
dependencies before using your configured publication registry.

`--input path` tracks additional selection files. Use `--project` and `--lock`
for an external companion; wrappers accept `CUE_PURIFIER_PROJECT` and
`CUE_PURIFIER_LOCK`. Prepared sessions retain their dependency and SDK closures
for garbage collection.

The initial integration supports public OCI modules and CUE 0.17.1. Module
replacements need additional integration.

## Publication

```sh
cue-purifier bundle --version v0.1.0
cue-purifier publish --tag v0.1.0
```

The bundle contains the native OCI image layout produced by CUE. Publication
uploads the exact realized archive to an existing GitHub release. Reproducible
bundling currently requires `source: kind: "self"` in the module manifest;
ordinary native publication retains CUE's support for Git source selection.

## Building with Nix

The overlay provides a named builder:

```nix
pkgs.cue-purifier.buildCueProject {
  src = ./.;
}
```

It exposes evaluation-known `packages`, `tests`, `release` and `fetches`. The
project output includes native JSON and consolidated CUE definitions. Set
`version` when bundling a module outside major version zero.

## Credits

The purifier idea was inspired by nixcloud's
[cargo (libnix)](https://github.com/nixcloud/cargo).
