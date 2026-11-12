{
  lib,
  stdenvNoCC,
  makeWrapper,
  python3,
  nix,
  gh,
  git,
  cacert,
  cue,
  helper,
  sdkVersion,
  nixpkgsSrc,
  purifierSrc,
}:
stdenvNoCC.mkDerivation {
  pname = "cue-purifier";
  version = "0.1.0";
  src = ../..;
  nativeBuildInputs = [ makeWrapper ];
  dontBuild = true;
  installPhase = ''
    mkdir -p "$out/bin" "$out/lib/cue-purifier"
    cp -r cue_purifier pkgs lib-overlays native "$out/lib/cue-purifier/"
    install -m755 bin/cue-purifier "$out/bin/cue-purifier"
    for file in realize release; do
      substituteInPlace "$out/lib/cue-purifier/pkgs/build-cue-project/$file.nix" --replace-fail '@nixpkgs@' '${nixpkgsSrc}' --replace-fail '@purifier@' '${purifierSrc}'
    done
    wrapProgram "$out/bin/cue-purifier" \
      --prefix PATH : ${
        lib.makeBinPath [
          python3
          nix
          gh
          git
        ]
      } \
      --set-default SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt \
      --set-default CUE_PURIFIER_GH ${gh}/bin/gh \
      --set CUE_PURIFIER_ORIGINAL ${lib.getExe cue} \
      --set CUE_PURIFIER_HELPER ${helper}/bin/cue-purifier-native \
      --set CUE_PURIFIER_SDK_VERSION ${sdkVersion} \
      --set CUE_PURIFIER_SDK "$out"
    makeWrapper "$out/bin/cue-purifier" "$out/bin/cue" --add-flags --native
  '';
  meta = {
    description = "Native CUE with locked Nix-resolved modules";
    homepage = "https://nix-purifiers.github.io/";
    license = lib.licenses.mit;
    platforms = [
      "x86_64-linux"
      "aarch64-linux"
    ];
    mainProgram = "cue-purifier";
  };
}
