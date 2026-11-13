# exos — a machine that is rebuilt from what is asked of it

First step, deliberately small. A NixOS base with nothing installed beyond the
agent. Everything else the machine can do comes from a list of asks
(`/var/lib/exos/asked.json`); each ask rebuilds the whole system into a new
generation, leaves a check behind, and is rolled back if any check fails.

    nix-build vm.nix -o result        # needs Nix; pins nixpkgs via pin.nix
    ./result/bin/run-exos-vm          # boots to a root prompt on the console

    exos "I need to edit video"       # rebuilds; ffmpeg now exists
    exos "a tool that shows the biggest files in a folder"
    exos                              # what this machine is, and why
    exos undo                         # previous generation
    exos check                        # re-run every check left by earlier asks

Files: `system.nix` (the machine), `configuration.nix` (machine + the VM it runs
in), `exos.py` (the agent), `model-standin.py` (a lookup table filling the model
contract), `pin.nix` (the package set).

## The model contract

Any executable. JSON on stdin `{"ask", "asked"}`; JSON on stdout with any of
`say`, `packages` (nixpkgs attribute names), `tool` (`name`, `source`), `check`
(a shell command that must succeed). Chosen by `EXOS_MODEL` or
`/var/lib/exos/model`; default is the stand-in.

## Observed (emulated, no hardware virtualisation)

- boot to prompt: 66 s
- "I need to edit video": 4 m 29 s, `ffmpeg -version` then works
- tool ask: `biggest /etc` works afterwards
- an ask whose check fails: rolled back, machine and list unchanged
- `exos undo`: tool gone, ffmpeg still present, all checks pass

## Not there yet

- No real model: the stand-in knows three sentences.
- No desktop: console only.
- Generations do not survive a reboot in this VM form (it boots a fixed kernel
  and system directly). Needs a real disk install.
- Everything runs as root; the agent is not yet its own account.
- Checks and tool source come straight from the model and run unsandboxed.
- `here.nix` / `here-ca.crt` are generated per host for a proxy and are ignored
  by git; without them the VM uses the network directly.
