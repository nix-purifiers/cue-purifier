{
  root,
  lockFile,
  sdk,
}:
let
  nixpkgsSrc = /. + "@nixpkgs@";
  pkgs = import nixpkgsSrc { };
  scope = import ./scope.nix {
    inherit pkgs nixpkgsSrc;
    purifierSrc = /. + "@purifier@";
  };
  src = /. + root;
  lock = import ./read-lock.nix { inherit (pkgs) lib; } {
    inherit src;
    lockFile = /. + lockFile;
  };
  environment = scope.callPackage ./environment.nix { } { inherit lock src; };
in
pkgs.writeText "cue-environment-profile.json" (
  builtins.toJSON {
    output = environment.output;
    sdk = builtins.storePath sdk;
  }
)
