(import ((fetchTarball (import ./pin.nix)) + "/nixos") { configuration = ./configuration.nix; }).vm
