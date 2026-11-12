{
  description = "Locked, Nix-resolved modules for CUE";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.purifier = {
    url = "github:nix-purifiers/purifier";
    flake = false;
  };
  outputs =
    {
      self,
      nixpkgs,
      purifier,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAll = nixpkgs.lib.genAttrs systems;
      overlay = final: prev: {
        cue-purifier = import ./pkgs/default.nix {
          pkgs = final;
          nixpkgsSrc = nixpkgs;
          purifierSrc = purifier;
        };
      };
      pkgsFor =
        system:
        import nixpkgs {
          inherit system;
          overlays = [ overlay ];
        };
    in
    {
      overlays.default = overlay;
      packages = forAll (system: {
        default = (pkgsFor system).cue-purifier.cli;
        cli = self.packages.${system}.default;
      });
      apps = forAll (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/cue-purifier";
          meta.description = "Lock native CUE modules";
        };
      });
      lib.cue-purifier = (nixpkgs.lib.extend (import ./lib-overlays/default)).cue-purifier;
      checks = forAll (
        system:
        let
          p = pkgsFor system;
          b = p.cue-purifier.buildCueProject {
            src = ./examples/minimal;
            doCheck = true;
            checkCommand = ''${p.python3}/bin/python3 -c 'import json,os; assert json.load(open(os.environ["out"]+"/output.json"))["answer"]==42' '';
          };
        in
        {
          json-projection =
            import ((import (purifier + "/nix/lib") { lib = nixpkgs.lib; }).testFixtures.jsonConsumer)
              {
                pkgs = p;
                producer = b.packages.project;
                expectedKey = "answer";
                expectedValue = 42;
              };
          inherit (b.packages) environment project;
          release = b.release;
          cli = self.packages.${system}.default;
        }
      );
      formatter = forAll (system: (pkgsFor system).nixfmt-tree);
    };
}
