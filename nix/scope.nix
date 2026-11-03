{
  pkgs,
  nixpkgsSrc,
  purifierSrc,
}:
pkgs.lib.makeScope pkgs.newScope (scope: {
  helper = scope.callPackage ./helper.nix { };
  purifier = import (purifierSrc + "/nix/lib") { inherit (pkgs) lib; };
  sdkVersion = builtins.hashString "sha256" (
    builtins.toJSON {
      nixpkgs = toString nixpkgsSrc;
      cue = toString pkgs.cue.src;
      helper = builtins.hashFile "sha256" ../native/main.go;
    }
  );
  nativeFetch = scope.callPackage ./fetch.nix { };
  cli = scope.callPackage ./cli.nix { inherit nixpkgsSrc purifierSrc; };
  buildCueProject = scope.callPackage ./build-project.nix { };
})
