# What gets built: the machine, plus where it is running.
{ modulesPath, lib, ... }:
let
  desktop = true;   # false: console only, boots to a root prompt in the terminal
in {
  imports = [ ./system.nix (modulesPath + "/virtualisation/qemu-vm.nix") ]
    ++ lib.optional desktop ./desktop.nix
    ++ lib.optional (builtins.pathExists ./here.nix) ./here.nix;
  boot.loader.grub.enable = false;   # this VM boots its kernel directly
  # A host folder of keys, if EXOS_SECRETS names one when the VM is started.
  virtualisation.sharedDirectories.secrets = {
    source = "\"\${EXOS_SECRETS:-$TMPDIR/xchg}\""; target = "/run/exos-secrets";
  };
  virtualisation = {
    memorySize = lib.mkDefault 6144; cores = lib.mkDefault 4; diskSize = lib.mkDefault 12288;
    graphics = lib.mkDefault desktop; writableStoreUseTmpfs = false;
  };
  # The VM has no graphics card: the desktop is drawn in software.
  environment.sessionVariables = lib.mkIf desktop { WLR_RENDERER = "pixman"; WLR_NO_HARDWARE_CURSORS = "1"; };
  # The root console stays reachable on the serial line when the screen is the desktop.
  systemd.services."serial-getty@ttyS0" = { enable = true; wantedBy = [ "getty.target" ]; };
}
