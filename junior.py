#!/usr/bin/env python3
"""Launch or continue a sterile Junior Codex session.

By default, this launcher resumes the newest session created inside Junior's
isolated Codex home.  ``--new`` deliberately starts a separate clean thread.
The two pre-repair Junior environments remain outside this runtime and are
never read or resumed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid


ROOT = Path(__file__).resolve().parent
JUNIOR_ROOT = ROOT / ".junior"
WORKSPACE = JUNIOR_ROOT / "workspace"
STERILE_ROOT = JUNIOR_ROOT / "sterile"
STERILE_HOME = STERILE_ROOT / "home"
CODEX_HOME = STERILE_ROOT / "codex-home"
SESSIONS_ROOT = CODEX_HOME / "sessions"
SQLITE_HOME = STERILE_ROOT / "sqlite"
RUNTIME_TMP = STERILE_ROOT / "tmp"
XDG_CONFIG_HOME = STERILE_ROOT / "xdg-config"
XDG_CACHE_HOME = STERILE_ROOT / "xdg-cache"
XDG_DATA_HOME = STERILE_ROOT / "xdg-data"
XDG_STATE_HOME = STERILE_ROOT / "xdg-state"
BROWSER_ROOT = STERILE_ROOT / "browser"
BROWSER_TMP = BROWSER_ROOT / "tmp"
BROWSER_RUNS_ROOT = BROWSER_ROOT / "runs"
BROWSER_RUNTIME = STERILE_ROOT / "browser-runtime"
BROWSER_SANDBOX_PROFILE = BROWSER_RUNTIME / "browser.sb"
BROWSER_PACKAGE = BROWSER_RUNTIME / "node_modules" / "@playwright" / "mcp"
BROWSER_PACKAGE_JSON = BROWSER_PACKAGE / "package.json"
BROWSER_ENTRYPOINT = BROWSER_PACKAGE / "cli.js"
BROWSER_PACKAGE_LOCK = BROWSER_RUNTIME / "package-lock.json"
BROWSER_NODE = Path("/opt/homebrew/bin/node")
BROWSER_SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")
BROWSER_CHROME = Path("/Applications/Google Chrome.app")
SYSTEM_USER_TMP = Path(tempfile.gettempdir()).resolve()

NORMAL_CODEX_HOME = Path.home() / ".codex"
SOURCE_AUTH = NORMAL_CODEX_HOME / "auth.json"
ISOLATED_AUTH = CODEX_HOME / "auth.json"

LEGACY_THREAD_IDS = frozenset(
    {
        "019ff75f-1769-7131-8081-4e6e4b067824",
        "019ff7be-f3a6-7003-85fd-99f1ce5fddd1",
    }
)
SESSION_ID_PATTERN = re.compile(
    r"(?P<id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$"
)

SAFE_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
SYSTEM_SKILLS_ROOT = CODEX_HOME / "skills" / ".system"
AUDITED_CODEX_VERSION = "codex-cli 0.145.0-alpha.22"
AUDITED_NODE_VERSION = "v24.6.0"
PLAYWRIGHT_MCP_VERSION = "0.0.79"
PLAYWRIGHT_MCP_INTEGRITY = (
    "sha512-VpqD4a3vFyGQMY9sh3UJiO6wjcurggkljKfAyCHL0QWGY5m6Ehr3MNsAAHPDHO//"
    "n13g0PCjpHatAOiulrqdZQ=="
)
PLAYWRIGHT_MCP_ENTRYPOINT_SHA256 = (
    "70dab09ab9a5bc1943fb78e2655f00af7349f9931073833919f19c5d7d786ad6"
)
BUNDLED_SYSTEM_SKILL_NAMES = (
    "imagegen",
    "openai-docs",
    "plugin-creator",
    "review-agent",
    "skill-creator",
    "skill-installer",
)
BROWSER_ENABLED_TOOLS = (
    "browser_close",
    "browser_resize",
    "browser_console_messages",
    "browser_handle_dialog",
    "browser_evaluate",
    "browser_drop",
    "browser_find",
    "browser_fill_form",
    "browser_press_key",
    "browser_type",
    "browser_navigate",
    "browser_navigate_back",
    "browser_network_requests",
    "browser_network_request",
    "browser_take_screenshot",
    "browser_snapshot",
    "browser_click",
    "browser_drag",
    "browser_hover",
    "browser_select_option",
    "browser_tabs",
    "browser_wait_for",
)


def fail(message: str) -> "NoReturn":
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def ensure_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)


def ensure_workspace_is_neutral() -> None:
    """Fail closed if a new thread would inherit workspace content."""

    WORKSPACE.mkdir(parents=True, exist_ok=True)

    allowed = {".git", ".browser-output"}
    unexpected = sorted(path.name for path in WORKSPACE.iterdir() if path.name not in allowed)
    if unexpected:
        joined = ", ".join(unexpected)
        fail(
            "Junior's workspace is not neutral. Quarantine or explicitly approve "
            f"these entries before launching a new thread: {joined}"
        )

    browser_output = WORKSPACE / ".browser-output"
    if browser_output.exists() and (
        not browser_output.is_dir() or any(browser_output.iterdir())
    ):
        fail("Junior's neutral browser-output directory is not empty")

    git_dir = WORKSPACE / ".git"
    if not git_dir.exists():
        result = subprocess.run(
            ["/usr/bin/git", "-C", str(WORKSPACE), "init", "-q"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            fail(f"could not initialize the neutral workspace: {result.stderr.strip()}")

    head = subprocess.run(
        ["/usr/bin/git", "-C", str(WORKSPACE), "rev-parse", "--verify", "HEAD"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if head.returncode == 0:
        fail("Junior's workspace has Git history; refusing to inherit it")


def ensure_workspace_exists() -> None:
    """Ensure the fixed isolated workspace exists without requiring it empty."""

    WORKSPACE.mkdir(parents=True, exist_ok=True)
    if WORKSPACE.is_symlink():
        fail("Junior's workspace may not be a symbolic link")


def sterile_session_files() -> list[tuple[Path, str]]:
    """Return isolated session paths and IDs without reading transcript content."""

    if not SESSIONS_ROOT.exists():
        return []

    sessions_root = SESSIONS_ROOT.resolve()
    sessions: list[tuple[Path, str]] = []
    for path in SESSIONS_ROOT.glob("**/*.jsonl"):
        resolved = path.resolve()
        if not resolved.is_relative_to(sessions_root):
            fail(f"session path escaped Junior's isolated store: {path}")
        match = SESSION_ID_PATTERN.search(path.name)
        if match is None:
            continue
        session_id = match.group("id")
        if session_id in LEGACY_THREAD_IDS:
            fail("a prohibited pre-repair Junior thread entered the sterile session store")
        sessions.append((path, session_id))
    return sessions


def latest_sterile_session_id() -> str | None:
    """Select the newest isolated session using file metadata only."""

    sessions = sterile_session_files()
    if not sessions:
        return None
    _, session_id = max(sessions, key=lambda item: item[0].stat().st_mtime_ns)
    return session_id


def validate_sterile_session_id(session_id: str) -> None:
    try:
        normalized = str(uuid.UUID(session_id))
    except ValueError:
        fail("invalid Junior session ID")
    if normalized != session_id or session_id in LEGACY_THREAD_IDS:
        fail("refusing to resume a non-sterile Junior session")
    if session_id not in {known_id for _, known_id in sterile_session_files()}:
        fail("refusing to resume a session outside Junior's isolated store")


def ensure_authentication_only() -> None:
    """Copy only normal Codex authentication into the sterile runtime."""

    ensure_private_directory(CODEX_HOME)

    if ISOLATED_AUTH.exists():
        ISOLATED_AUTH.chmod(0o600)
        return

    if not SOURCE_AUTH.is_file():
        fail(
            "normal Codex authentication was not found; authenticate normal Codex "
            "first, then retry"
        )

    temporary = CODEX_HOME / ".auth.json.new"
    shutil.copyfile(SOURCE_AUTH, temporary)
    temporary.chmod(0o600)
    temporary.replace(ISOLATED_AUTH)


def discovered_system_skills() -> list[Path]:
    if not SYSTEM_SKILLS_ROOT.exists():
        return []
    return sorted(SYSTEM_SKILLS_ROOT.glob("*/SKILL.md"))


def expected_system_skills() -> list[Path]:
    return [SYSTEM_SKILLS_ROOT / name / "SKILL.md" for name in BUNDLED_SYSTEM_SKILL_NAMES]


def toml_string(value: str | Path) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_browser_sandbox_profile() -> str:
    """Return the OS-enforced file boundary for Playwright and Chrome."""

    metadata_paths = (
        Path("/Applications"),
        Path("/etc"),
        Path("/opt"),
        Path("/private"),
        Path("/private/etc"),
        Path("/private/var"),
        Path("/Users"),
        Path("/Users/jryear"),
        Path("/Users/jryear/Library"),
        Path("/Users/jryear/Library/Application Support"),
        Path("/Users/jryear/Library/Application Support/Google"),
        Path("/Users/jryear/Library/Application Support/Google/Chrome"),
        Path("/Users/jryear/Library/Application Support/Google/Chrome/Crashpad"),
        ROOT,
        JUNIOR_ROOT,
        STERILE_ROOT,
        WORKSPACE,
        Path("/var"),
    )
    metadata_subpaths = (
        Path("/Users/jryear/Library/Application Support/Google/Chrome/Crashpad"),
        SYSTEM_USER_TMP,
    )
    readable_paths = (
        Path("/System"),
        Path("/Library"),
        BROWSER_CHROME,
        Path("/opt/homebrew"),
        Path("/usr"),
        Path("/bin"),
        Path("/sbin"),
        Path("/private/etc"),
        Path("/private/var/db"),
        Path("/dev"),
        BROWSER_RUNTIME,
        BROWSER_ROOT,
    )
    writable_paths = (Path("/dev"), BROWSER_ROOT)
    chrome_temp_pattern = (
        "^"
        + re.escape(str(SYSTEM_USER_TMP))
        + r"/com\.google\.Chrome\.[^/]+(/.*)?$"
    )

    lines = [
        "(version 1)",
        "",
        "; Network and process operations remain available to the dedicated",
        "; browser. File access is denied unless explicitly allowed below.",
        "(allow default)",
        "(deny file-read* file-write*)",
        "",
        "(allow file-read-metadata",
    ]
    lines.extend(f"  (literal {toml_string(path)})" for path in metadata_paths)
    lines.extend(f"  (subpath {toml_string(path)})" for path in metadata_subpaths)
    lines.extend([")", "", "(allow file-read*", '  (literal "/")'])
    lines.extend(f"  (subpath {toml_string(path)})" for path in readable_paths)
    lines.extend([")", "", "(allow file-write*"])
    lines.extend(f"  (subpath {toml_string(path)})" for path in writable_paths)
    lines.extend(
        [
            ")",
            "",
            "(allow file-read* file-write*",
            f'  (regex #"{chrome_temp_pattern}"))',
            "",
        ]
    )
    return "\n".join(lines)


def ensure_browser_runtime() -> Path:
    """Verify the pinned MCP package and create a fresh ephemeral run root."""

    for required in (
        BROWSER_NODE,
        BROWSER_SANDBOX_EXEC,
        BROWSER_CHROME,
        BROWSER_PACKAGE_JSON,
        BROWSER_ENTRYPOINT,
        BROWSER_PACKAGE_LOCK,
    ):
        if not required.exists():
            fail(f"Junior browser runtime is incomplete: missing {required}")
        if (
            required in (BROWSER_PACKAGE_JSON, BROWSER_ENTRYPOINT, BROWSER_PACKAGE_LOCK)
            and required.is_symlink()
        ):
            fail(f"Junior browser runtime path may not be a symbolic link: {required}")

    observed_node = subprocess.run(
        [str(BROWSER_NODE), "--version"], capture_output=True, text=True
    )
    if observed_node.returncode != 0 or observed_node.stdout.strip() != AUDITED_NODE_VERSION:
        fail(
            "Node version drifted from the audited browser boundary: "
            f"expected {AUDITED_NODE_VERSION!r}, observed {observed_node.stdout.strip()!r}"
        )

    package = json.loads(BROWSER_PACKAGE_JSON.read_text())
    if package.get("name") != "@playwright/mcp" or package.get("version") != PLAYWRIGHT_MCP_VERSION:
        fail("Junior browser MCP package does not match the audited pinned version")
    entrypoint_hash = hashlib.sha256(BROWSER_ENTRYPOINT.read_bytes()).hexdigest()
    if entrypoint_hash != PLAYWRIGHT_MCP_ENTRYPOINT_SHA256:
        fail("Junior browser MCP entrypoint failed its integrity check")

    lock = json.loads(BROWSER_PACKAGE_LOCK.read_text())
    locked = lock.get("packages", {}).get("node_modules/@playwright/mcp", {})
    if (
        locked.get("version") != PLAYWRIGHT_MCP_VERSION
        or locked.get("integrity") != PLAYWRIGHT_MCP_INTEGRITY
    ):
        fail("Junior browser lockfile failed its integrity check")

    ensure_private_directory(BROWSER_ROOT)
    ensure_private_directory(BROWSER_TMP)
    ensure_private_directory(BROWSER_RUNS_ROOT)
    profile = render_browser_sandbox_profile()
    temporary_profile = BROWSER_RUNTIME / ".browser.sb.new"
    temporary_profile.write_text(profile)
    temporary_profile.chmod(0o600)
    temporary_profile.replace(BROWSER_SANDBOX_PROFILE)

    run_root = BROWSER_RUNS_ROOT / str(uuid.uuid4())
    ensure_private_directory(run_root)
    return run_root


def render_config(
    skill_paths: list[Path], *, browser_run_root: Path | None = None
) -> str:
    """Return the complete fail-closed config; no external config is layered."""

    workspace = str(WORKSPACE).replace("\\", "\\\\").replace('"', '\\"')
    sqlite_home = str(SQLITE_HOME).replace("\\", "\\\\").replace('"', '\\"')
    approval_policy = (
        "approval_policy = { granular = { sandbox_approval = false, rules = false, "
        "mcp_elicitations = true, request_permissions = false, "
        "skill_approval = false } }"
        if browser_run_root is not None
        else 'approval_policy = "never"'
    )

    lines = [
        'model = "gpt-5.6-sol"',
        'personality = "none"',
        approval_policy,
        'web_search = "disabled"',
        'cli_auth_credentials_store = "file"',
        'history.persistence = "none"',
        'default_permissions = "junior-sterile"',
        f'sqlite_home = "{sqlite_home}"',
        'project_doc_max_bytes = 0',
        'project_doc_fallback_filenames = []',
        'disable_paste_burst = false',
        '',
        '[apps._default]',
        'enabled = false',
        '',
        '[memories]',
        'use_memories = false',
        'generate_memories = false',
        'disable_on_external_context = true',
        '',
        '[features]',
        'apps = false',
        'auth_elicitation = false',
        'browser_use = false',
        'browser_use_external = false',
        'browser_use_full_cdp_access = false',
        'code_mode = false',
        'code_mode_host = false',
        'computer_use = false',
        'enable_mcp_apps = false',
        'goals = false',
        'hooks = false',
        'image_generation = false',
        'in_app_browser = false',
        'memories = false',
        'multi_agent = false',
        'plugin_sharing = false',
        'plugins = false',
        'remote_plugin = false',
        'shell_snapshot = false',
        'skill_mcp_dependency_install = false',
        'skill_search = false',
        'tool_call_mcp_elicitation = false',
        'workspace_dependencies = false',
        '',
        '[permissions.junior-sterile]',
        'description = "Only the neutral Junior workspace and minimal runtime files."',
        'extends = ":workspace"',
        '',
        '[permissions.junior-sterile.filesystem]',
        '":root" = "deny"',
        '":minimal" = "read"',
        '":tmpdir" = "deny"',
        '":slash_tmp" = "deny"',
        '"/Users/jryear" = "deny"',
        '',
        '[permissions.junior-sterile.filesystem.":workspace_roots"]',
        '"." = "write"',
        '".git" = "read"',
        '".codex" = "deny"',
        '".agents" = "deny"',
        '"AGENTS.md" = "deny"',
        '"AGENTS.override.md" = "deny"',
        '',
        '[permissions.junior-sterile.network]',
        'enabled = false',
        '',
        '[shell_environment_policy]',
        'inherit = "none"',
        '',
        '[shell_environment_policy.set]',
        f'HOME = "{workspace}"',
        f'TMPDIR = "{workspace}"',
        f'PATH = "{SAFE_PATH}"',
        'GIT_CONFIG_GLOBAL = "/dev/null"',
        'GIT_CONFIG_SYSTEM = "/dev/null"',
        'ZDOTDIR = "/dev/null"',
    ]

    for path in skill_paths:
        escaped = str(path).replace("\\", "\\\\").replace('"', '\\"')
        lines.extend(
            [
                '',
                '[[skills.config]]',
                f'path = "{escaped}"',
                'enabled = false',
            ]
        )

    if browser_run_root is not None:
        browser_args = [
            "-f",
            str(BROWSER_SANDBOX_PROFILE),
            str(BROWSER_NODE),
            str(BROWSER_ENTRYPOINT),
            "--browser",
            "chrome",
            "--headless",
            "--isolated",
            "--no-sandbox",
            "--block-service-workers",
            "--codegen",
            "none",
            "--image-responses",
            "allow",
            "--output-dir",
            str(browser_run_root),
        ]
        rendered_args = ", ".join(toml_string(value) for value in browser_args)
        rendered_tools = ", ".join(
            toml_string(value) for value in BROWSER_ENABLED_TOOLS
        )
        lines.extend(
            [
                "",
                "[mcp_servers.junior_browser]",
                f"command = {toml_string(BROWSER_SANDBOX_EXEC)}",
                f"args = [{rendered_args}]",
                f"cwd = {toml_string(BROWSER_ROOT)}",
                "enabled = true",
                "required = true",
                "startup_timeout_sec = 20",
                "tool_timeout_sec = 90",
                'default_tools_approval_mode = "writes"',
                f"enabled_tools = [{rendered_tools}]",
                "",
                "[mcp_servers.junior_browser.env]",
                f"HOME = {toml_string(BROWSER_ROOT)}",
                f"TMPDIR = {toml_string(BROWSER_TMP)}",
                f"PATH = {toml_string(SAFE_PATH)}",
                f"XDG_CONFIG_HOME = {toml_string(BROWSER_ROOT / 'xdg-config')}",
                f"XDG_CACHE_HOME = {toml_string(BROWSER_ROOT / 'xdg-cache')}",
                f"XDG_DATA_HOME = {toml_string(BROWSER_ROOT / 'xdg-data')}",
                f"XDG_STATE_HOME = {toml_string(BROWSER_ROOT / 'xdg-state')}",
            ]
        )

    return "\n".join(lines) + "\n"


def write_config(skill_paths: list[Path], *, browser_run_root: Path | None = None) -> None:
    content = render_config(skill_paths, browser_run_root=browser_run_root)
    temporary = CODEX_HOME / ".config.toml.new"
    temporary.write_text(content)
    temporary.chmod(0o600)
    temporary.replace(CODEX_HOME / "config.toml")


def codex_environment() -> dict[str, str]:
    """Build a new environment instead of inheriting the operator's shell."""

    environment = {
        "CODEX_HOME": str(CODEX_HOME),
        "CODEX_SQLITE_HOME": str(SQLITE_HOME),
        "HOME": str(STERILE_HOME),
        "TMPDIR": str(RUNTIME_TMP),
        "PATH": SAFE_PATH,
        "SHELL": "/bin/zsh",
        "ZDOTDIR": str(STERILE_HOME),
        "XDG_CONFIG_HOME": str(XDG_CONFIG_HOME),
        "XDG_CACHE_HOME": str(XDG_CACHE_HOME),
        "XDG_DATA_HOME": str(XDG_DATA_HOME),
        "XDG_STATE_HOME": str(XDG_STATE_HOME),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "LC_CTYPE": os.environ.get("LC_CTYPE", "UTF-8"),
        "TERM": os.environ.get("TERM", "xterm-256color"),
    }
    return environment


def codex_binary() -> str:
    candidate = shutil.which("codex", path=SAFE_PATH)
    if candidate is None:
        fail("Codex CLI was not found on the fixed safe PATH")
    return str(Path(candidate).resolve())


def run_checked(command: list[str], environment: dict[str, str]) -> subprocess.CompletedProcess:
    result = subprocess.run(command, env=environment, capture_output=True, text=True)
    if result.returncode != 0:
        failure = result.stderr.strip() or result.stdout.strip() or "unknown failure"
        fail(f"preflight command failed: {failure}")
    return result


def prepare_sterile_runtime(
    *, require_neutral_workspace: bool, enable_browser: bool = False
) -> tuple[str, dict[str, str]]:
    os.umask(0o077)

    for path in (
        STERILE_ROOT,
        STERILE_HOME,
        CODEX_HOME,
        SQLITE_HOME,
        RUNTIME_TMP,
        XDG_CONFIG_HOME,
        XDG_CACHE_HOME,
        XDG_DATA_HOME,
        XDG_STATE_HOME,
    ):
        ensure_private_directory(path)

    if require_neutral_workspace:
        ensure_workspace_is_neutral()
    else:
        ensure_workspace_exists()
    ensure_authentication_only()
    browser_run_root = ensure_browser_runtime() if enable_browser else None
    write_config(discovered_system_skills(), browser_run_root=browser_run_root)

    binary = codex_binary()
    environment = codex_environment()

    version = run_checked([binary, "--version"], environment).stdout.strip()
    if version != AUDITED_CODEX_VERSION:
        fail(
            "Codex version drifted from the audited isolation boundary: "
            f"expected {AUDITED_CODEX_VERSION!r}, observed {version!r}"
        )

    # Login status causes this Codex build to materialize its bundled system
    # skills in some execution paths but not others. The audited version's six
    # known paths are disabled even before they exist, then checked again.
    write_config(expected_system_skills(), browser_run_root=browser_run_root)
    run_checked([binary, "login", "status"], environment)
    discovered = discovered_system_skills()
    unknown = sorted({path.parent.name for path in discovered} - set(BUNDLED_SYSTEM_SKILL_NAMES))
    if unknown:
        fail(f"unknown bundled system skill(s) appeared: {', '.join(unknown)}")
    write_config(expected_system_skills(), browser_run_root=browser_run_root)

    # Ask this installed CLI for the effective feature values.
    # (`--strict-config` is accepted by TUI/exec, but this build rejects it on
    # the read-only `features` subcommand. The new-thread command keeps it.)
    features = run_checked([binary, "features", "list"], environment)
    effective = {
        fields[0]: fields[-1]
        for line in features.stdout.splitlines()
        if len(fields := line.split()) >= 3
    }
    for feature in (
        "apps",
        "auth_elicitation",
        "browser_use",
        "computer_use",
        "goals",
        "hooks",
        "image_generation",
        "in_app_browser",
        "memories",
        "multi_agent",
        "plugins",
        "remote_plugin",
        "shell_snapshot",
        "skill_mcp_dependency_install",
        "skill_search",
        "tool_call_mcp_elicitation",
        "workspace_dependencies",
    ):
        if effective.get(feature) != "false":
            fail(f"feature {feature} is not effectively disabled")
    mcp = run_checked([binary, "mcp", "list"], environment)
    if enable_browser:
        if mcp.stdout.count("junior_browser") != 1:
            fail("the isolated Junior browser MCP did not configure exactly as expected")
        if "cloudflare" in mcp.stdout.lower():
            fail("Cloudflare entered the Junior browser capability surface")
    elif "No MCP servers configured" not in mcp.stdout:
        fail("the sterile Codex home unexpectedly has an MCP server configured")

    return binary, environment


def build_base_thread_command(binary: str, *, enable_web: bool) -> list[str]:
    command = [
        binary,
        "--strict-config",
        "--cd",
        str(WORKSPACE),
        "--model",
        "gpt-5.6-sol",
    ]
    if enable_web:
        command.append("--search")
    return command


def build_new_thread_command(binary: str, *, enable_web: bool = False) -> list[str]:
    command = build_base_thread_command(binary, enable_web=enable_web)

    forbidden = {"resume", "fork", *LEGACY_THREAD_IDS}
    if forbidden.intersection(command):
        fail("internal error: a continuation path entered the new-thread command")

    return command


def build_resume_thread_command(
    binary: str, session_id: str, *, enable_web: bool = False
) -> list[str]:
    validate_sterile_session_id(session_id)
    return build_base_thread_command(binary, enable_web=enable_web) + [
        "resume", session_id
    ]


def print_preflight(
    session_id: str | None, *, enable_web: bool, enable_browser: bool
) -> None:
    skill_count = len(BUNDLED_SYSTEM_SKILL_NAMES)
    print("Junior sterile preflight: PASS")
    print(f"workspace={WORKSPACE}")
    print(f"isolated_codex_home={CODEX_HOME}")
    print("thread_mode=resume-latest-sterile-or-new")
    print(f"continuation_available={'yes' if session_id else 'no'}")
    print(f"web_search={'live-on-launch' if enable_web else 'disabled'}")
    print(f"browser={'isolated-ephemeral-playwright' if enable_browser else 'disabled'}")
    print(f"mcp_servers={'1 (junior_browser only)' if enable_browser else '0'}")
    print("plugins=disabled")
    print("memories=disabled")
    print(f"system_skills_disabled={skill_count}")
    print("filesystem=:root-deny + :minimal-read + workspace-write")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="validate isolation without starting a model thread",
    )
    parser.add_argument(
        "--new",
        action="store_true",
        help="start a separate clean Junior thread instead of continuing",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="enable native live web search without enabling shell network access",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="enable an ephemeral OS-sandboxed browser without Chrome profile access",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    session_id = None if args.new else latest_sterile_session_id()
    binary, environment = prepare_sterile_runtime(
        require_neutral_workspace=args.new or session_id is None,
        enable_browser=args.browser,
    )

    if args.preflight:
        print_preflight(
            session_id, enable_web=args.web, enable_browser=args.browser
        )
        return 0

    os.chdir(WORKSPACE)
    if session_id is not None:
        print("Continuing the latest sterile Junior thread.")
        command = build_resume_thread_command(binary, session_id, enable_web=args.web)
    else:
        print("Launching a brand-new sterile Junior thread.")
        command = build_new_thread_command(binary, enable_web=args.web)
    os.execve(binary, command, environment)
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
