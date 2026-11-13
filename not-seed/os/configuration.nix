# What gets built: the machine, plus where it is running.
{ modulesPath, lib, ... }: {
  imports = [ ./system.nix (modulesPath + "/virtualisation/qemu-vm.nix") ]
    ++ lib.optional (builtins.pathExists ./here.nix) ./here.nix;
  boot.loader.grub.enable = false;   # this VM boots its kernel directly
  virtualisation = {
    memorySize = lib.mkDefault 6144; cores = lib.mkDefault 4; diskSize = lib.mkDefault 12288;
    graphics = lib.mkDefault false; writableStoreUseTmpfs = false;
  };
}
