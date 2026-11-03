{
  lib,
  runCommand,
  writeText,
  python3,
  purifier,
  nativeFetch,
  fetchgit,
  sdkVersion,
  helper,
  cue,
  gnutar,
  gzip,
}@scope:
{
  src,
  lockFile ? src + "/cue-purifier.lock.json",
  fetchers ? { },
  nativeBuildInputs ? [ ],
  doCheck ? false,
  checkCommand ? "",
  version ? "v0.1.0",
}:
let
  lock = purifier.checkLock (import ./read-lock.nix { inherit lib; } { inherit src lockFile; });
  prepared = import ./environment.nix scope { inherit lock src fetchers; };
  source = lib.cleanSourceWith {
    inherit src;
    filter =
      path: type:
      !(builtins.elem (baseNameOf path) [
        ".git"
        "result"
        "__pycache__"
      ]);
  };
  project = runCommand "cue-project" { nativeBuildInputs = [ cue ] ++ nativeBuildInputs; } ''
    cp -pr ${source} source
    chmod -R u+w source
    cd source
    export CUE_REGISTRY=none CUE_CACHE_DIR="$TMPDIR/cache"
    ${python3}/bin/python3 ${../cue_purifier/layout.py} "$CUE_CACHE_DIR" ${prepared.packageFile}
    test -e ${prepared.output}/manifest.json
    mkdir -p "$out"
    cue vet -c
    cue export --outfile "$out/output.json"
    cue def --outfile "$out/definition.cue"
    ${lib.optionalString doCheck checkCommand}
    mkdir -p "$out/source"
    cp -pr ${source}/. "$out/source/"
  '';
  release =
    runCommand "cue-native-release"
      {
        nativeBuildInputs = [
          cue
          gnutar
          gzip
        ];
      }
      ''
            cp -pr ${source} source
            chmod -R u+w source
            cd source
            export CUE_CACHE_DIR="$TMPDIR/cache"
            ${python3}/bin/python3 ${../cue_purifier/layout.py} "$CUE_CACHE_DIR" ${prepared.packageFile}
            test -e ${prepared.output}/manifest.json
        export CUE_REGISTRY=${
          lib.escapeShellArg (
            (builtins.head (lib.splitString "@" lock.data.native.module)) + "=registry.invalid,none"
          )
        }
            mkdir -p "$out"
            cue mod publish ${lib.escapeShellArg version} --out "$out/oci"
            tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -czf "$out/cue-module.tar.gz" -C "$out/oci" .
      '';
in
{
  packages = {
    default = project;
    inherit project;
    environment = prepared.output;
  };
  tests = project;
  inherit release;
  fetches = lock.entries;
}
