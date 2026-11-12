final: prev: {
  cue-purifier = {
    readLock = import ./read-lock.nix { lib = final; };
  };
}
