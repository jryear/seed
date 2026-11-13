# The machine. Everything it can do beyond the base comes from the list of
# what has been asked of it (asked.json); nothing else is installed.
{ lib, pkgs, ... }:
let
  pkgsSrc = fetchTarball (import ./pin.nix);
  askedFile = /var/lib/exos/asked.json;
  asked = if builtins.pathExists askedFile
          then builtins.fromJSON (builtins.readFile askedFile) else [ ];
  pkgOf = name: lib.getAttrFromPath (lib.splitString "." name) pkgs;
  toolOf = t: pkgs.writeTextFile {
    name = t.name; executable = true; destination = "/bin/${t.name}"; text = t.source;
  };
  exos = pkgs.writeScriptBin "exos"
    ("#!${pkgs.python3}/bin/python3\n" + builtins.readFile ./exos.py);
  standin = pkgs.writeScriptBin "exos-model-standin"
    ("#!${pkgs.python3}/bin/python3\n" + builtins.readFile ./model-standin.py);
in {
  system.stateVersion = "26.11";
  networking.hostName = "exos";

  environment.systemPackages = [ exos standin ]
    ++ lib.concatMap (a: map pkgOf (a.packages or [ ])) asked
    ++ map (a: toolOf a.tool) (builtins.filter (a: a ? tool) asked);

  # Each generation carries the description it was built from, and the
  # sources needed to build the next one.
  environment.etc."exos-asked.json".text = builtins.toJSON asked;
  environment.etc."exos".source = lib.cleanSource ./.;
  nix.nixPath = [ "nixpkgs=${pkgsSrc}" "nixos-config=/etc/exos/configuration.nix" ];
  nix.settings.experimental-features = [ "nix-command" ];

  documentation.enable = false;
  services.getty.autologinUser = "root";
  users.motd = "exos: say what you need, e.g.  exos \"I need to edit video\"";
}
