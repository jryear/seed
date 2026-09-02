#!/usr/bin/env python3
"""Static and unit checks for Junior's sterile launcher."""

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "junior.py"
LEGACY_IDS = {
    "019ff75f-1769-7131-8081-4e6e4b067824",
    "019ff7be-f3a6-7003-85fd-99f1ce5fddd1",
}
STERILE_ID = "019ff836-3aa8-73a1-8997-fe3e385a7889"


def load_launcher():
    spec = importlib.util.spec_from_file_location("junior_launcher", LAUNCHER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class JuniorIsolationTest(unittest.TestCase):
    def setUp(self):
        self.launcher = load_launcher()

    def test_new_thread_command_cannot_resume_or_fork(self):
        command = self.launcher.build_new_thread_command("/opt/homebrew/bin/codex")
        self.assertNotIn("resume", command)
        self.assertNotIn("fork", command)
        for thread_id in LEGACY_IDS:
            self.assertNotIn(thread_id, command)

    def test_web_is_an_explicit_native_search_flag(self):
        offline = self.launcher.build_new_thread_command("/opt/homebrew/bin/codex")
        online = self.launcher.build_new_thread_command(
            "/opt/homebrew/bin/codex", enable_web=True
        )
        self.assertNotIn("--search", offline)
        self.assertIn("--search", online)
        self.assertNotIn("danger-full-access", online)
        self.assertNotIn("--add-dir", online)

    def test_resume_command_accepts_only_session_from_sterile_store(self):
        with tempfile.TemporaryDirectory() as directory:
            sessions_root = Path(directory) / "sessions"
            session = sessions_root / "2026" / "08" / "12" / f"rollout-{STERILE_ID}.jsonl"
            session.parent.mkdir(parents=True)
            session.touch()
            with mock.patch.object(self.launcher, "SESSIONS_ROOT", sessions_root):
                command = self.launcher.build_resume_thread_command(
                    "/opt/homebrew/bin/codex", STERILE_ID, enable_web=True
                )

        self.assertIn("resume", command)
        self.assertEqual(command[-1], STERILE_ID)
        self.assertLess(command.index("--search"), command.index("resume"))
        for thread_id in LEGACY_IDS:
            self.assertNotIn(thread_id, command)

    def test_resume_rejects_legacy_or_unknown_session(self):
        with tempfile.TemporaryDirectory() as directory:
            sessions_root = Path(directory) / "sessions"
            sessions_root.mkdir()
            with mock.patch.object(self.launcher, "SESSIONS_ROOT", sessions_root):
                with self.assertRaises(SystemExit):
                    self.launcher.build_resume_thread_command(
                        "/opt/homebrew/bin/codex", next(iter(LEGACY_IDS))
                    )
                with self.assertRaises(SystemExit):
                    self.launcher.build_resume_thread_command(
                        "/opt/homebrew/bin/codex", STERILE_ID
                    )

    def test_latest_session_selection_uses_only_file_metadata(self):
        older_id = "019ff827-25a8-7d62-b235-68ffe2b5f20b"
        with tempfile.TemporaryDirectory() as directory:
            sessions_root = Path(directory) / "sessions"
            sessions_root.mkdir()
            older = sessions_root / f"rollout-{older_id}.jsonl"
            newer = sessions_root / f"rollout-{STERILE_ID}.jsonl"
            older.write_text("content must not affect selection\n")
            newer.write_text("different content\n")
            os.utime(older, ns=(1, 1))
            os.utime(newer, ns=(2, 2))
            with mock.patch.object(self.launcher, "SESSIONS_ROOT", sessions_root):
                selected = self.launcher.latest_sterile_session_id()

        self.assertEqual(selected, STERILE_ID)

    def test_default_continues_and_new_is_explicit(self):
        self.assertFalse(self.launcher.parse_args([]).new)
        self.assertFalse(self.launcher.parse_args([]).web)
        self.assertFalse(self.launcher.parse_args([]).browser)
        self.assertTrue(self.launcher.parse_args(["--new"]).new)
        self.assertTrue(self.launcher.parse_args(["--web"]).web)
        self.assertTrue(self.launcher.parse_args(["--browser"]).browser)

    def test_config_disables_inherited_capabilities(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory) / "skill" / "SKILL.md"
            skill.parent.mkdir()
            skill.write_text("fixture\n")
            config = self.launcher.render_config([skill])

        required = {
            'apps = false',
            'memories = false',
            'use_memories = false',
            'generate_memories = false',
            'multi_agent = false',
            'plugins = false',
            'remote_plugin = false',
            'skill_search = false',
            'skill_mcp_dependency_install = false',
            'hooks = false',
            'goals = false',
            'web_search = "disabled"',
            'enabled = false',
            '":root" = "deny"',
            '":minimal" = "read"',
            '"/Users/jryear" = "deny"',
            '"." = "write"',
            'inherit = "none"',
            str(skill),
        }
        for value in required:
            self.assertIn(value, config)
        self.assertNotIn("mcp_servers", config)

    def test_browser_mode_adds_only_the_isolated_pinned_mcp(self):
        run_root = self.launcher.BROWSER_RUNS_ROOT / "test-run"
        config = self.launcher.render_config([], browser_run_root=run_root)

        self.assertEqual(config.count("[mcp_servers."), 2)
        self.assertIn("[mcp_servers.junior_browser]", config)
        self.assertIn(str(self.launcher.BROWSER_SANDBOX_EXEC), config)
        self.assertIn(str(self.launcher.BROWSER_ENTRYPOINT), config)
        self.assertIn('"--headless"', config)
        self.assertIn('"--isolated"', config)
        self.assertIn('"--no-sandbox"', config)
        self.assertIn(str(run_root), config)
        self.assertIn('default_tools_approval_mode = "writes"', config)
        self.assertIn("mcp_elicitations = true", config)
        self.assertIn("sandbox_approval = false", config)
        self.assertNotIn('approval_policy = "never"', config)
        self.assertNotIn("browser_run_code_unsafe", config)
        self.assertNotIn("browser_file_upload", config)
        self.assertNotIn("cloudflare", config.lower())
        self.assertIn('plugins = false', config)
        self.assertIn('memories = false', config)

    def test_browser_os_sandbox_does_not_grant_workspace_or_parent_data(self):
        profile = self.launcher.render_browser_sandbox_profile()

        self.assertIn("(deny file-read* file-write*)", profile)
        self.assertIn(f'(subpath "{self.launcher.BROWSER_RUNTIME}")', profile)
        self.assertNotIn(f'(subpath "{self.launcher.WORKSPACE}")', profile)
        self.assertNotIn(f'(subpath "{self.launcher.ROOT}")', profile)
        self.assertIn(f'(literal "{self.launcher.WORKSPACE}")', profile)

    def test_neutral_workspace_allows_only_empty_browser_bootstrap(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            workspace.mkdir()
            (workspace / ".browser-output").mkdir()
            with mock.patch.object(self.launcher, "WORKSPACE", workspace):
                self.launcher.ensure_workspace_is_neutral()

            (workspace / ".browser-output" / "inherited.txt").write_text("state\n")
            with mock.patch.object(self.launcher, "WORKSPACE", workspace):
                with self.assertRaises(SystemExit):
                    self.launcher.ensure_workspace_is_neutral()

    def test_all_audited_bundled_skills_are_disabled_before_they_exist(self):
        config = self.launcher.render_config(self.launcher.expected_system_skills())
        for name in self.launcher.BUNDLED_SYSTEM_SKILL_NAMES:
            expected = self.launcher.SYSTEM_SKILLS_ROOT / name / "SKILL.md"
            self.assertIn(str(expected), config)
        self.assertEqual(config.count("[[skills.config]]"), 6)

    def test_codex_version_is_pinned_for_skill_inventory(self):
        self.assertEqual(
            self.launcher.AUDITED_CODEX_VERSION,
            "codex-cli 0.145.0-alpha.22",
        )

    def test_environment_is_allowlisted_not_inherited(self):
        hostile = {
            "OPENAI_API_KEY": "must-not-pass",
            "CLOUDFLARE_API_TOKEN": "must-not-pass",
            "CODEX_HOME": "/Users/example/.codex",
            "HOME": "/Users/example",
            "PATH": "/hostile/bin",
        }
        with mock.patch.dict(os.environ, hostile, clear=True):
            environment = self.launcher.codex_environment()

        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("CLOUDFLARE_API_TOKEN", environment)
        self.assertEqual(environment["CODEX_HOME"], str(self.launcher.CODEX_HOME))
        self.assertEqual(environment["HOME"], str(self.launcher.STERILE_HOME))
        self.assertEqual(environment["PATH"], self.launcher.SAFE_PATH)
        self.assertNotEqual(environment["CODEX_HOME"], "/Users/example/.codex")

    def test_workspace_rejects_non_neutral_content(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            workspace.mkdir()
            (workspace / "inherited.txt").write_text("state\n")
            with mock.patch.object(self.launcher, "WORKSPACE", workspace):
                with self.assertRaises(SystemExit):
                    self.launcher.ensure_workspace_is_neutral()

    def test_auth_copy_is_the_only_normal_codex_read(self):
        source = LAUNCHER.read_text()
        self.assertIn('NORMAL_CODEX_HOME / "auth.json"', source)
        self.assertNotIn("copytree(NORMAL_CODEX_HOME", source)
        self.assertNotIn("sessions", self.launcher.ensure_authentication_only.__doc__ or "")

    def test_root_bridge_has_no_thread_continuation(self):
        bridge = (ROOT / "junior").read_text()
        self.assertNotIn("codex resume", bridge)
        self.assertNotIn("thread_id", bridge)
        self.assertNotIn("CODEX_HOME", bridge)

    def test_root_bridge_keeps_live_tui_in_tmux(self):
        bridge = (ROOT / "junior").read_text()
        self.assertIn('tmux_session="junior-sterile"', bridge)
        self.assertIn('attach-session -t "=$tmux_session"', bridge)
        self.assertIn('new-session -s "$tmux_session"', bridge)
        self.assertIn('if [[ "${1:-}" == "--new" ]]', bridge)
        self.assertIn("exit it before relaunching with options", bridge)


if __name__ == "__main__":
    unittest.main(verbosity=2)
