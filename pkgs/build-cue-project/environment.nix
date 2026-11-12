{
  lib,
  runCommand,
  fetchgit,
  writeText,
  python3,
  purifier,
  nativeFetch,
  sdkVersion,
  helper,
  ...
}:
{
  lock,
  src,
  fetchers ? { },
}:
let
  checked = purifier.checkLock lock;
  selectionSource = lib.fileset.toSource {
    root = src;
    fileset = lib.fileset.unions (
      map (name: src + "/${name}") (builtins.attrNames checked.data.inputs)
    );
  };
  nativeURLFetch =
    args:
    let
      matches = builtins.filter (e: e.hash == args.hash && builtins.elem e.url args.urls) checked.entries;
    in
    assert lib.assertMsg (builtins.length matches == 1) "CUE module fetch is ambiguous";
    nativeFetch (builtins.head matches);
  tree = purifier.tree (
    {
      name = "cue-locked-modules";
      entries = checked.entries;
      fetchurl = nativeURLFetch;
      inherit
        runCommand
        fetchgit
        writeText
        python3
        ;
    }
    // fetchers
  );
  packages = map (e: {
    cue = e.cue;
    package = "${tree}/${e.path}";
  }) checked.entries;
  packageFile = writeText "cue-packages.json" (builtins.toJSON packages);
  validated = runCommand "cue-native-selection-validated" { } ''
    export CUE_REGISTRY=none CUE_CACHE_DIR="$TMPDIR/cache"
    ${python3}/bin/python3 ${../../cue_purifier/layout.py} "$CUE_CACHE_DIR" ${packageFile}
    ${helper}/bin/cue-purifier-native check ${selectionSource} ${writeText "cue-lock.json" (builtins.toJSON checked.data)}
    touch "$out"
  '';
  manifest = writeText "cue-environment.json" (
    builtins.toJSON {
      inherit tree packages;
      sdk = sdkVersion;
    }
  );
  output = runCommand "cue-locked-environment" { } ''
    test -e ${validated}
    mkdir -p "$out"
    ln -s ${manifest} "$out/manifest.json"
  '';
in
assert lib.assertMsg (checked.data.sdk == sdkVersion) "CUE SDK changed; update the lock";
{
  inherit
    tree
    output
    packages
    packageFile
    ;
}
