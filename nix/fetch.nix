{
  lib,
  runCommand,
  helper,
  writeText,
  cacert,
}:
entry:
runCommand "cue-native-module"
  {
    outputHashMode = "recursive";
    outputHashAlgo = "sha256";
    outputHash = entry.hash;
    impureEnvVars = lib.fetchers.proxyImpureEnvVars;
    SSL_CERT_FILE = "${cacert}/etc/ssl/certs/ca-bundle.crt";
  }
  ''
    export HOME="$TMPDIR/home" CUE_CONFIG_DIR="$TMPDIR/config" CUE_CACHE_DIR="$TMPDIR/cache"
    mkdir -p "$HOME" "$CUE_CONFIG_DIR" "$CUE_CACHE_DIR"
    if [ -n "''${NIX_SSL_CERT_FILE:-}" ]; then export SSL_CERT_FILE="$NIX_SSL_CERT_FILE"; fi
    ${helper}/bin/cue-purifier-native fetch ${writeText "cue-native-origin.json" (builtins.toJSON entry.cue)} "$out"
  ''
