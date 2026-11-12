{
  pkgs,
  nixpkgsSrc,
  purifierSrc,
}:
pkgs.lib.makeScope pkgs.newScope (scope: {
  helper = scope.callPackage ./build-cue-project/helper.nix { };
  purifier = import (purifierSrc + "/nix/lib") { inherit (pkgs) lib; };
  sdkVersion = builtins.hashString "sha256" (
    builtins.toJSON {
      nixpkgs = toString nixpkgsSrc;
      cue = toString pkgs.cue.src;
      helper = builtins.hashFile "sha256" ../native/main.go;
    }
  );
  nativeFetch = scope.callPackage ./build-cue-project/fetch.nix { };
  cli = scope.callPackage ./cli/default.nix { inherit nixpkgsSrc purifierSrc; };
  buildCueProject = scope.callPackage ./build-cue-project/default.nix { };
})
