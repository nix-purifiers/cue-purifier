{ cue }:
cue.overrideAttrs (old: {
  pname = "cue-purifier-native";
  subPackages = [ "cmd/cue-purifier-native" ];
  postPatch = (old.postPatch or "") + ''
    mkdir -p cmd/cue-purifier-native
    cp ${../native/main.go} cmd/cue-purifier-native/main.go
    chmod u+w cmd/cue-purifier-native/main.go
    gofmt -w cmd/cue-purifier-native/main.go
  '';
  postInstall = "";
  ldflags = [
    "-s"
    "-w"
  ];
})
