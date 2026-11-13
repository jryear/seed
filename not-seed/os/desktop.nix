# The desktop: an empty screen with one place to say what you need. No bar, no
# menu, no launcher. A window exists only because an ask opened it ("open" in
# the model contract). Mod(Super)+q closes the focused window; Mod+space moves
# the keyboard between the prompt and the windows; the mouse works too.
{ pkgs, ... }:
let
  prompt = pkgs.writeShellScriptBin "exos-prompt" ''
    set -f
    while IFS= read -e -r -p '> ' line; do
      [ -n "$line" ] && sudo exos $line
    done
  '';
  # the prompt is the one fixed thing on screen: if it is closed it comes back
  promptWindow = pkgs.writeShellScript "exos-prompt-window" ''
    while :; do foot --app-id prompt --font monospace:size=12 -o pad=12x8 exos-prompt; done
  '';
in {
  environment.systemPackages = [ pkgs.sway pkgs.foot prompt ];
  fonts.packages = [ pkgs.dejavu_fonts ];
  hardware.graphics.enable = true;

  # The strip along the top is the prompt; asked-for windows tile below it.
  environment.etc."sway/config".text = ''
    output * bg #101010 solid_color
    default_border none
    default_floating_border none
    gaps top 150
    for_window [app_id="prompt"] floating enable, resize set width 100 ppt height 150 px, move absolute position 0 0
    bindsym Mod4+q kill
    bindsym Mod4+space focus mode_toggle
    exec ${promptWindow}
  '';

  # Straight into the session, as an ordinary account, no login screen.
  users.users.person.isNormalUser = true;
  services.greetd = {
    enable = true;
    settings.default_session = { command = "sway"; user = "person"; };
  };

  # The session is not root, but rebuilding the machine needs root: the person
  # may run exos, and only exos, as root. This is not a security boundary --
  # whoever can ask can have a tool or a check run as root.
  security.sudo.extraRules = [{
    users = [ "person" ];
    commands = [{ command = "/run/current-system/sw/bin/exos"; options = [ "NOPASSWD" ]; }];
  }];
  security.sudo.extraConfig = "Defaults env_keep += SWAYSOCK";   # so exos can open windows in the session
}
