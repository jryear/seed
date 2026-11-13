# What gets built: the machine, plus where it is running.
{ modulesPath, lib, ... }: {
  imports = [ ./system.nix (modulesPath + "/virtualisation/qemu-vm.nix") ]
    ++ lib.optional (builtins.pathExists ./here.nix) ./here.nix;
  boot.loader.grub.enable = false;   # this VM boots its kernel directly
  # A host folder of keys, if EXOS_SECRETS names one when the VM is started.
  virtualisation.sharedDirectories.secrets = {
    source = "\"\${EXOS_SECRETS:-$TMPDIR}\""; target = "/run/exos-secrets";
  };
  virtualisation = {
    memorySize = lib.mkDefault 6144; cores = lib.mkDefault 4; diskSize = lib.mkDefault 12288;
    graphics = lib.mkDefault false; writableStoreUseTmpfs = false;
  };
}
