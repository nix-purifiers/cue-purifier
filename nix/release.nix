{
  root,
  lockFile,
  version ? "v0.1.0",
}:
let
  nixpkgsSrc = /. + "@nixpkgs@";
  pkgs = import nixpkgsSrc { };
  scope = import ./scope.nix {
    inherit pkgs nixpkgsSrc;
    purifierSrc = /. + "@purifier@";
  };
in
(scope.buildCueProject {
  src = /. + root;
  lockFile = /. + lockFile;
  inherit version;
}).release
