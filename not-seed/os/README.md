# exos — a machine that is rebuilt from what is asked of it

First step, deliberately small. A NixOS base with nothing installed beyond the
agent. Everything else the machine can do comes from a list of asks
(`/var/lib/exos/asked.json`); each ask rebuilds the whole system into a new
generation and leaves a check behind. If the build fails, or the ask's check
fails, or the ask is interrupted, the machine is put back on exactly the system
it was running before and the list is restored.

    nix-build vm.nix -o result        # needs Nix; pins nixpkgs via pin.nix
    ./result/bin/run-exos-vm          # boots to the desktop: an empty screen and a prompt

The screen holds one strip to type into and nothing else. Say what you need
there in plain words (`I need to look at images`); the machine is rebuilt and,
if the ask has something to show, a window opens below the strip. `undo`,
`check` and an empty-handed `exos` work there too, without the word `exos`.
Super+q closes the focused window, Super+space moves the keyboard between the
prompt and the windows. That is the whole interface.

A root console is on the serial line (QEMU: View > serial0), and is the only
interface if `desktop = false` is set at the top of `configuration.nix`:

    exos "I need to edit video"       # rebuilds; ffmpeg now exists
    exos "a tool that shows the biggest files in a folder"
    exos                              # what this machine is, and why
    exos undo                         # the system as it was before the last kept ask
    exos check                        # re-run every check left by earlier asks

Files: `system.nix` (the machine), `desktop.nix` (the empty screen and its
prompt: sway, one terminal, no bar), `configuration.nix` (machine + the VM it runs
in), `exos.py` (the agent), `model-standin.py` (a lookup table filling the model
contract), `model-openai.py` (a real one), `pin.nix` (the package set),
`test_agent.py` (the agent's bookkeeping against a fake Nix; `python3 test_agent.py`).

## What the agent holds to

- The running machine is the truth. Every system carries the list it was built
  from; if the list on disk ever disagrees (an ask was killed, the machine
  restarted into another system), the list is reset from the machine and undo
  history is cleared.
- Going back means activating one specific earlier system, never "the previous
  generation number". If that cannot be done, it says so and names what is running.
- A change must come with a check, and not a blank or `true` one. Checks get 60
  seconds and no input. Checks already failing before an ask are reported and
  not blamed on it.
- What was asked for never replaces something the base provides: asked packages
  and tools lose every name collision, and a tool may not take an existing name.
- A check passing means only that its command exited 0. The model writes the
  check, so it can still be a weak one.

## The model contract

Any executable. JSON on stdin `{"ask", "asked", "error"?}`; JSON on stdout with
any of `say`, `packages` (nixpkgs attribute names), `tool` (`name`, `source`),
`check` (a shell command that must succeed; required with any change), `open`
(a program and plain arguments, no shell syntax; started on the desktop once the
ask has succeeded, so that a window appears; allowed on its own, to show
something the machine already has; on the console it is only printed). If a
rebuild fails, the model is asked once more with the error. Chosen by
`EXOS_MODEL` or `/var/lib/exos/model`; default is the stand-in.

### A real model (OpenAI)

Start the VM with a host folder holding the key in a file named `omarchy`:

    EXOS_SECRETS=$PWD/../secrets ./result/bin/run-exos-vm

then on the machine's root console, once:

    echo exos-model-openai > /var/lib/exos/model

and ask as usual, from the desktop prompt or the console. (`EXOS_MODEL` also
selects the model, but only on the root console: the desktop prompt runs `exos`
through sudo, which drops it. The OpenAI model name is `EXOS_OPENAI_MODEL`,
default `gpt-5.4-mini`, with the same limitation.)

## Observed (emulated, no hardware virtualisation)

- boot to prompt: 66 s
- "I need to edit video": 4 m 29 s, `ffmpeg -version` then works
- tool ask: `biggest /etc` works afterwards
- after an independent review broke rollback and undo (they followed
  generation numbers and could land on the wrong system), both were rewritten.
  Re-run in the VM: video ask, tool ask, `undo`, then an ask whose check fails.
  Result: tool gone, ffmpeg present, the rejected package absent, list identical
  to the one the running system was built from, profile pointing at that system.
- `test_agent.py`: 15 cases against a fake Nix, including every sequence the
  review broke, interruption, a killed ask, hostile replies and a hanging check.
  Removing a fix makes its test fail (checked for six of them; clearing undo
  history on reconcile has no test).
- real model (gpt-5.4-mini), "I want to read PDFs from the command line": first
  answer named a package that does not exist; the agent sent the error back, the
  second answer (`poppler-utils`) built and its check passed. 9 m 11 s for both.

- desktop: prompt on screen 78 s after power-on. "I need to look at images"
  typed into it: 8 m 26 s, then the viewer window opens by itself
  (`shots/1-empty-at-boot.png`, `2-ask-typed.png`, `3-after-ask-window.png`).
  Typing and drawing are immediate enough to use; rebuilds are the wait.

## Not there yet

- The fixes above were verified by their author, not re-reviewed.
- One real ask through a real model, once. Not a measure of how often it gets
  things right. The `EXOS_SECRETS` key-file route is untested (here the key was
  supplied by a proxy instead).
- The desktop session is an ordinary account (`person`) that may run `exos`,
  and only `exos`, as root without a password. That keeps the session's own
  programs from being root; it does not restrain the person, since an ask can
  produce a tool or a check that runs as root. The serial line and the other
  virtual consoles still log in as root automatically.
- The desktop is sway-specific: `exos` opens windows with `swaymsg exec`.
  A new window takes the keyboard; nothing restores windows after a reboot.
  The prompt strip is a fixed 150 px and shows only the last few lines.
- `configuration.nix` forces software drawing (`WLR_RENDERER=pixman`) because the
  VM has no graphics card; on real hardware that line should go.
- Generations do not survive a reboot in this VM form (it boots a fixed kernel
  and system directly), so after a restart the machine is the base again and
  the list is reset to match. Needs a real disk install.
- If activating a system fails partway, the machine can be left between two
  systems; the agent reports that it could not return but cannot repair it.
- Everything ever asked, tool sources included, is sent to the model on each ask.
- The agent itself runs as root and is not yet its own account.
- Checks and tool source come straight from the model and run unsandboxed.
- `here.nix` / `here-ca.crt` are generated per host for a proxy and are ignored
  by git; without them the VM uses the network directly.
