{ lib }:
{
  src,
  lockFile ? src + "/cue-purifier.lock.json",
}:
let
  raw = if builtins.pathExists lockFile then builtins.fromJSON (builtins.readFile lockFile) else { };
  data = if builtins.isAttrs raw then raw else { };
  entries = data.entries or [ ];
  relative =
    s:
    builtins.isString s
    && s != ""
    && !(lib.hasPrefix "/" s)
    && !(builtins.elem ".." (lib.splitString "/" s));
  shape =
    (data.version or null) == 1
    && (data.purifier or null) == "cue"
    && builtins.isString (data.sdk or null)
    && builtins.isAttrs (data.native or null)
    && builtins.isString (data.native.module or null)
    && builtins.isList entries
    && builtins.all (
      e:
      builtins.isAttrs e
      && builtins.isAttrs (e.cue or null)
      && builtins.isString (e.cue.module or null)
      && builtins.isString (e.cue.version or null)
      && builtins.isString (e.cue.manifest or null)
      && (e.cue.manifestDigest or null) == "sha256:${builtins.hashString "sha256" e.cue.manifest}"
      && relative (e.cue.extract or null)
      && lib.hasPrefix "mod/extract/" e.cue.extract
      && relative (e.cue.download or null)
      && lib.hasPrefix "mod/download/" e.cue.download
      && (e.path or null) == "modules/${lib.removePrefix "mod/extract/" e.cue.extract}"
      && builtins.isAttrs (e.cue.location or null)
      && builtins.isString (e.cue.location.Host or null)
      && builtins.isString (e.cue.location.Repository or null)
      && builtins.isBool (e.cue.location.Insecure or null)
      &&
        (e.url or null) == "oci:${e.cue.location.Host}/${e.cue.location.Repository}@${e.cue.manifestDigest}"
      && (e.mirrors or null) == [ ]
      && builtins.isString (e.hash or null)
      && builtins.match "sha256-[A-Za-z0-9+/]{43}=" e.hash != null
    ) entries
    && builtins.isAttrs (data.inputs or null)
    && builtins.isList (data.extraInputs or null)
    && builtins.all relative data.extraInputs;
  valid =
    shape
    && !(builtins.pathExists (src + "/cue.mod/local-module.cue"))
    && builtins.length entries == builtins.length (lib.unique (map (e: e.cue.module) entries))
    &&
      builtins.attrNames data.inputs
      == builtins.sort builtins.lessThan (lib.unique ([ "cue.mod/module.cue" ] ++ data.extraInputs))
    && builtins.all (
      name:
      relative name
      && builtins.pathExists (src + "/${name}")
      && builtins.hashFile "sha256" (src + "/${name}") == (data.inputs.${name}.sha256 or null)
    ) (builtins.attrNames data.inputs);
in
{
  purifier = "cue";
  inherit data entries;
  outputs = {
    packages = [
      "default"
      "environment"
      "project"
    ];
    tests = [ "default" ];
    release = [ "default" ];
  };
  problems = lib.optional (!valid) "Invalid or stale CUE lock; update the lock";
}
