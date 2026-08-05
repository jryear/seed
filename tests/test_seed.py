#!/usr/bin/env python3
"""Reality audit for seed v0.3.1 — 19 points exercised by 39 tests.

 1. one-time repository initialization
 2. valid field-level delta ingestion
 3. perturbation probe behavior (transfers / fragile / unreachable)
 4. deterministic field merge
 5. history preservation
 6. truthful git commit reporting
 7. restart and crash recovery (idempotent replay)
 8. concurrent-delta handling (ordered, last-write-wins)
 9. carry-bound enforcement (blocks, seed untouched)
10. clean handoff into the next session
11. probe directives excluded from the carry projection
12. structured probe evidence retained in append-only JSONL
13. unknown fields held instead of extending the schema
14. duplicate headings held instead of silently collapsing
15. setup failure reported truthfully
16. complete evidence schema and fail-closed verdict parsing
17. allowlisted Git commits and initialization
18. collision-safe held and archived evidence
19. empty-update and indented-probe validation

Run:  python3 tests/test_seed.py
Uses a fake local Ollama server for probe tests — no models needed.
"""
import http.server, importlib.util, json, os, shutil, subprocess, sys, tempfile, threading, unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

SRC = Path(__file__).resolve().parent.parent  # the seed/ folder

DELTA = "## L2 Pending Decision\nShip the seed loop.\n"
DELTA2 = "## L2 Pending Decision\nSecond writer wins.\n"
JSON_NULL = object()


def sh(cwd, *cmd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


class FakeOllama(http.server.BaseHTTPRequestHandler):
    """Answers /api/generate with a canned verdict set on the server object."""
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        canned = self.server.canned
        response = canned.pop(0) if isinstance(canned, list) else canned
        if response is None:
            body = b"not-json"
        else:
            body = json.dumps({"response": None if response is JSON_NULL else response}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def start_fake_ollama(canned):
    srv = http.server.HTTPServer(("127.0.0.1", 0), FakeOllama)
    srv.canned = canned
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def load_seedd(repo):
    spec = importlib.util.spec_from_file_location("seedd_under_test", repo / "bin" / "seedd.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SeedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = Path(self.tmp) / "seed"
        shutil.copytree(
            SRC, self.repo,
            ignore=shutil.ignore_patterns(".git", "tests", "history", "inbox",
                                          "*.lock", "__pycache__", "evidence.jsonl"),
        )
        (self.repo / "history").mkdir()
        (self.repo / "inbox").mkdir()
        for c in (["git", "init", "-q"],
                  ["git", "config", "user.email", "t@t"],
                  ["git", "config", "user.name", "t"],
                  ["git", "add", "-A"],
                  ["git", "commit", "-qm", "seed v0"]):
            r = sh(self.repo, *c)
            assert r.returncode == 0, r.stderr

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def seedd(self, env=None):
        e = dict(os.environ)
        if env:
            e.update(env)
        return subprocess.run(
            [sys.executable, "bin/seedd.py", "--once"],
            cwd=self.repo, capture_output=True, text=True, env=e,
        )

    def drop(self, content, name="d.md"):
        (self.repo / "inbox" / name).write_text(content)

    def seed_text(self):
        return (self.repo / "seed.md").read_text()

    # 1 — initialization
    def test_01_init(self):
        log = sh(self.repo, "git", "log", "--oneline")
        self.assertEqual(log.returncode, 0)
        self.assertIn("seed v0", log.stdout)
        self.assertTrue((self.repo / "seed.md").exists())

    # 2 — delta ingestion
    def test_02_ingest(self):
        self.drop(DELTA)
        r = self.seedd()
        self.assertIn("committed", r.stdout)
        self.assertIn("Ship the seed loop.", self.seed_text())
        self.assertEqual(list((self.repo / "inbox").glob("*")), [])
        self.assertEqual(len(list((self.repo / "history").glob("*.md"))), 1)
        status = sh(self.repo, "git", "status", "--porcelain")
        self.assertEqual(status.returncode, 0)
        self.assertEqual(status.stdout.strip(), "")

    # 3 — probe behavior
    def test_03a_probe_transfers(self):
        srv, url = start_fake_ollama("TRANSFERS — same bound applies.")
        try:
            self.drop(DELTA + "[probe] claim A || claim A with changed variable\n")
            r = self.seedd({"OLLAMA_URL": url})
            self.assertIn("probe:transfers", r.stdout)
            self.assertIn("committed", r.stdout)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_03b_probe_fragile_blocks(self):
        srv, url = start_fake_ollama("FRAGILE — conclusion diverges.")
        try:
            self.drop(DELTA + "[probe] claim A || claim A perturbed\n")
            r = self.seedd({"OLLAMA_URL": url})
            self.assertIn("HELD", r.stdout)
            self.assertNotIn("committed", r.stdout)
            self.assertNotIn("Ship the seed loop.", self.seed_text())
            held = list((self.repo / "inbox").glob("*.held.md"))
            self.assertEqual(len(held), 1)
            self.assertIn("HELD:", held[0].read_text())
        finally:
            srv.shutdown()
            srv.server_close()

    def test_03c_probe_unreachable_blocks(self):
        self.drop(DELTA + "[probe] claim A || claim A perturbed\n")
        r = self.seedd({"OLLAMA_URL": "http://127.0.0.1:1"})
        self.assertIn("HELD", r.stdout)
        self.assertNotIn("committed", r.stdout)
        self.assertNotIn("Ship the seed loop.", self.seed_text())

    def test_03d_malformed_probe_blocks(self):
        self.drop(DELTA + "[probe] claim with no perturbation\n")
        r = self.seedd()
        self.assertIn("HELD", r.stdout)
        self.assertNotIn("committed", r.stdout)

    # 4 — deterministic merge
    def test_04_deterministic(self):
        self.drop(DELTA)
        self.seedd()
        first = self.seed_text()
        self.drop(DELTA)
        self.seedd()
        self.assertEqual(first, self.seed_text())

    # 5 — history preservation
    def test_05_history(self):
        payload = DELTA + "\nextra evidence line kept verbatim\n"
        self.drop(payload)
        self.seedd()
        hist = list((self.repo / "history").glob("*.md"))
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0].read_text(), payload)

    # 6 — truthful git reporting
    def test_06_git_truth(self):
        os.rename(self.repo / ".git", self.repo / ".git.bak")
        self.drop(DELTA)
        r = self.seedd()
        self.assertIn("MERGED BUT NOT COMMITTED", r.stdout)
        self.assertNotIn("\ncommitted", "\n" + r.stdout.replace("MERGED BUT NOT COMMITTED", ""))
        self.assertIn("Ship the seed loop.", self.seed_text())  # disk state still advanced
        os.rename(self.repo / ".git.bak", self.repo / ".git")

    # 7 — crash recovery: seed already merged, delta still in inbox → replay is safe
    def test_07_crash_recovery(self):
        merged_early = self.seed_text().replace(
            "(The high-stakes decision this work serves; its stakes.)",
            "Ship the seed loop.",
        )
        (self.repo / "seed.md").write_text(merged_early)  # simulate crash after replace
        self.drop(DELTA)  # delta never left inbox
        r = self.seedd()
        self.assertIn("committed", r.stdout)
        self.assertEqual(self.seed_text().count("Ship the seed loop."), 1)
        self.assertEqual(list((self.repo / "inbox").glob("*")), [])

    # 8 — concurrent deltas: ordered processing, last write wins, both archived
    def test_08_concurrent(self):
        self.drop(DELTA, "a.md")
        self.drop(DELTA2, "b.md")
        r = self.seedd()
        self.assertEqual(r.stdout.count("committed"), 2)
        self.assertIn("Second writer wins.", self.seed_text())
        self.assertNotIn("Ship the seed loop.", self.seed_text())
        self.assertEqual(len(list((self.repo / "history").glob("*.md"))), 2)

    # 9 — carry bound blocks and leaves seed untouched
    def test_09_carry_bound(self):
        before = self.seed_text()
        self.drop("## L2 Pending Decision\n" + ("word " * 400))
        r = self.seedd()
        self.assertIn("HELD", r.stdout)
        self.assertIn("carry bound", r.stdout)
        self.assertEqual(before, self.seed_text())

    # 10 — clean handoff: fields intact, under bound, parseable
    def test_10_handoff(self):
        self.drop(DELTA)
        self.drop("## Last Delta & Observed Result\nCycle one committed.\n", "e.md")
        self.seedd()
        text = self.seed_text()
        for field in ("L4 Position & Trajectory", "L2 Pending Decision",
                      "L1 Problem Class & Mode", "Assumptions Most Likely Wrong",
                      "Last Delta & Observed Result"):
            self.assertIn(f"## {field}", text)
        self.assertIn("Cycle one committed.", text)
        self.assertLessEqual(len(text.split()), 300)


    # 11 — probe directives never enter the carry projection
    def test_11_probe_lines_stripped(self):
        srv, url = start_fake_ollama("TRANSFERS — holds either way.")
        try:
            self.drop("## L2 Pending Decision\nShip.\n[probe] claim A || claim A perturbed\n")
            r = self.seedd({"OLLAMA_URL": url})
            self.assertIn("committed", r.stdout)
            self.assertNotIn("[probe]", self.seed_text())
            hist = list((self.repo / "history").glob("*.md"))[0].read_text()
            self.assertIn("[probe]", hist)  # verbatim in the archive
        finally:
            srv.shutdown()
            srv.server_close()

    # 12 — probe evidence is retained as structured records, pass or fail
    def test_12_evidence_retained(self):
        srv, url = start_fake_ollama("TRANSFERS — same mechanism.")
        try:
            self.drop(DELTA + "[probe] claim A || claim A perturbed\n")
            self.seedd({"OLLAMA_URL": url})
        finally:
            srv.shutdown()
            srv.server_close()
        rec = json.loads(
            (self.repo / "evidence.jsonl").read_text().strip().splitlines()[-1])
        self.assertEqual(rec["outcome"], "transfers")
        for key in ("ts", "model", "claim", "perturbed",
                    "answer_original", "answer_perturbed", "verdict"):
            self.assertIn(key, rec)

        srv, url = start_fake_ollama("FRAGILE — diverges.")
        try:
            self.drop(DELTA + "[probe] claim B || claim B perturbed\n")
            self.seedd({"OLLAMA_URL": url})
        finally:
            srv.shutdown()
            srv.server_close()
        rec = json.loads(
            (self.repo / "evidence.jsonl").read_text().strip().splitlines()[-1])
        self.assertEqual(rec["outcome"], "fragile")

    # 13 — unknown fields are rejected, not silently created
    def test_13_unknown_field_held(self):
        self.drop("## Brand New Field\nsurprise state\n")
        r = self.seedd()
        self.assertIn("HELD", r.stdout)
        self.assertIn("unknown field", r.stdout)
        self.assertNotIn("surprise state", self.seed_text())

    # 14 — duplicate headings are a conflict, not a silent last-write
    def test_14_duplicate_field_held(self):
        self.drop("## L2 Pending Decision\nOption A\n\n## L2 Pending Decision\nOption B\n")
        r = self.seedd()
        self.assertIn("HELD", r.stdout)
        self.assertIn("duplicate", r.stdout)
        self.assertNotIn("Option", self.seed_text())

    # 15 — setup.sh never claims readiness when git fails
    def test_15_setup_truthful(self):
        bindir = Path(self.tmp) / "fakebin"
        bindir.mkdir()
        fake = bindir / "git"
        fake.write_text("#!/bin/sh\nexit 1\n")
        fake.chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = f"{bindir}:{env['PATH']}"
        fresh = Path(self.tmp) / "fresh"
        shutil.copytree(
            SRC, fresh,
            ignore=shutil.ignore_patterns(".git", "tests", "history", "inbox",
                                          "*.lock", "__pycache__", "evidence.jsonl"))
        r = subprocess.run(["bash", "setup.sh"], cwd=fresh,
                           capture_output=True, text=True, env=env)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("ready", r.stdout)
        self.assertIn("FAILED", r.stdout + r.stderr)

    # 16 — every probe outcome has one stable evidence schema and verdicts fail closed
    def test_16a_malformed_probe_evidence_schema(self):
        self.drop(DELTA + "[probe] claim with no perturbation\n")
        self.seedd()
        rec = json.loads((self.repo / "evidence.jsonl").read_text().splitlines()[-1])
        self.assertEqual(rec["outcome"], "malformed")
        for key in ("ts", "model", "claim", "perturbed",
                    "answer_original", "answer_perturbed", "verdict"):
            self.assertIn(key, rec)

    def test_16b_unreachable_probe_evidence_schema(self):
        self.drop(DELTA + "[probe] claim A || claim A perturbed\n")
        self.seedd({"OLLAMA_URL": "http://127.0.0.1:1"})
        rec = json.loads((self.repo / "evidence.jsonl").read_text().splitlines()[-1])
        self.assertEqual(rec["outcome"], "error")
        for key in ("ts", "model", "claim", "perturbed",
                    "answer_original", "answer_perturbed", "verdict", "error"):
            self.assertIn(key, rec)

    def test_16c_partial_answers_survive_verdict_error(self):
        srv, url = start_fake_ollama(["answer A", "answer B", None])
        try:
            self.drop(DELTA + "[probe] claim A || claim A perturbed\n")
            r = self.seedd({"OLLAMA_URL": url})
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertIn("HELD", r.stdout)
        rec = json.loads((self.repo / "evidence.jsonl").read_text().splitlines()[-1])
        self.assertEqual(rec["outcome"], "error")
        self.assertEqual(rec["answer_original"], "answer A")
        self.assertEqual(rec["answer_perturbed"], "answer B")
        self.assertIsNone(rec["verdict"])

    def test_16d_ambiguous_verdict_holds(self):
        srv, url = start_fake_ollama("MAYBE — insufficient evidence")
        try:
            self.drop(DELTA + "[probe] claim A || claim A perturbed\n")
            r = self.seedd({"OLLAMA_URL": url})
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertIn("HELD", r.stdout)
        self.assertNotIn("committed", r.stdout)
        self.assertNotIn("Ship the seed loop.", self.seed_text())
        rec = json.loads((self.repo / "evidence.jsonl").read_text().splitlines()[-1])
        self.assertEqual(rec["outcome"], "malformed")
        self.assertEqual(rec["verdict"], "MAYBE — insufficient evidence")

    def test_16e_conflicting_verdict_tokens_hold(self):
        srv, url = start_fake_ollama("TRANSFERS or FRAGILE — unclear")
        try:
            self.drop(DELTA + "[probe] claim A || claim A perturbed\n")
            r = self.seedd({"OLLAMA_URL": url})
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertIn("HELD", r.stdout)
        self.assertNotIn("committed", r.stdout)
        rec = json.loads((self.repo / "evidence.jsonl").read_text().splitlines()[-1])
        self.assertEqual(rec["outcome"], "malformed")

    def test_16f_non_string_verdict_is_recorded_and_held(self):
        srv, url = start_fake_ollama(["answer A", "answer B", JSON_NULL])
        try:
            self.drop(DELTA + "[probe] claim A || claim A perturbed\n")
            r = self.seedd({"OLLAMA_URL": url})
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertIn("HELD", r.stdout)
        rec = json.loads((self.repo / "evidence.jsonl").read_text().splitlines()[-1])
        self.assertEqual(rec["outcome"], "malformed")
        self.assertEqual(rec["answer_original"], "answer A")
        self.assertEqual(rec["answer_perturbed"], "answer B")
        self.assertIsNone(rec["verdict"])

    def test_16g_conflicts_anywhere_in_verdict_hold(self):
        for index, verdict in enumerate((
            "TRANSFERS\nFRAGILE — contradictory",
            "TRANSFERS — but FRAGILE under another reading",
        )):
            with self.subTest(verdict=verdict):
                srv, url = start_fake_ollama(verdict)
                try:
                    self.drop(DELTA + "[probe] claim A || claim A perturbed\n",
                              f"conflict-{index}.md")
                    r = self.seedd({"OLLAMA_URL": url})
                finally:
                    srv.shutdown()
                    srv.server_close()
                self.assertIn("HELD", r.stdout)
                self.assertNotIn("committed", r.stdout)

    def test_16h_empty_or_non_string_answers_hold(self):
        cases = (
            ["", "answer B", "TRANSFERS — coherent"],
            [JSON_NULL, "answer B", "TRANSFERS — coherent"],
            ["answer A", {"answer": "B"}, "TRANSFERS — coherent"],
        )
        for index, responses in enumerate(cases):
            with self.subTest(responses=responses):
                srv, url = start_fake_ollama(list(responses))
                try:
                    self.drop(DELTA + "[probe] claim A || claim A perturbed\n",
                              f"answer-{index}.md")
                    r = self.seedd({"OLLAMA_URL": url})
                finally:
                    srv.shutdown()
                    srv.server_close()
                self.assertIn("HELD", r.stdout)
                self.assertNotIn("committed", r.stdout)
                rec = json.loads((self.repo / "evidence.jsonl").read_text().splitlines()[-1])
                self.assertEqual(rec["outcome"], "malformed")

    def test_16i_probe_exit_code_contract(self):
        for verdict, expected in (("TRANSFERS — coherent", 0),
                                  ("FRAGILE — changed", 2),
                                  ("MAYBE — unclear", 3)):
            with self.subTest(verdict=verdict):
                srv, url = start_fake_ollama(verdict)
                try:
                    env = os.environ.copy()
                    env["OLLAMA_URL"] = url
                    r = subprocess.run(
                        [sys.executable, "bin/probe.py",
                         "[probe] claim A || claim A perturbed"],
                        cwd=self.repo, env=env, capture_output=True, text=True,
                    )
                finally:
                    srv.shutdown()
                    srv.server_close()
                self.assertEqual(r.returncode, expected, r.stdout + r.stderr)

    # 17 — Seed commits never sweep unrelated staged or untracked work
    def test_17_commit_is_allowlisted(self):
        (self.repo / "setup.sh").write_text((self.repo / "setup.sh").read_text() + "\n# unrelated\n")
        sh(self.repo, "git", "add", "setup.sh")
        (self.repo / "private.txt").write_text("must not enter seed history\n")
        self.drop(DELTA)
        r = self.seedd()
        self.assertIn("committed", r.stdout)
        committed = sh(self.repo, "git", "show", "--pretty=format:", "--name-only", "HEAD").stdout
        self.assertNotIn("setup.sh", committed)
        self.assertNotIn("private.txt", committed)
        staged = sh(self.repo, "git", "diff", "--cached", "--name-only").stdout
        self.assertIn("setup.sh", staged)
        self.assertTrue((self.repo / "private.txt").exists())

    def test_17b_setup_is_allowlisted(self):
        fresh = Path(self.tmp) / "setup-allowlist"
        shutil.copytree(
            SRC, fresh,
            ignore=shutil.ignore_patterns(".git", "history", "inbox", "*.lock",
                                          "__pycache__", "evidence.jsonl"))
        for c in (["git", "init", "-q"],
                  ["git", "config", "user.email", "t@t"],
                  ["git", "config", "user.name", "t"]):
            self.assertEqual(sh(fresh, *c).returncode, 0)
        (fresh / "private.txt").write_text("do not initialize me\n")
        (fresh / "bin" / "private.txt").write_text("do not initialize me\n")
        (fresh / "tests" / "private.txt").write_text("do not initialize me\n")
        hook = fresh / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\ngit add -- private.txt bin/private.txt tests/private.txt\n")
        hook.chmod(0o755)
        r = subprocess.run(["bash", "setup.sh"], cwd=fresh, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        committed = sh(fresh, "git", "show", "--pretty=format:", "--name-only", "HEAD").stdout
        self.assertNotIn("private.txt", committed)
        status = sh(fresh, "git", "status", "--porcelain").stdout
        self.assertIn("?? private.txt", status)
        self.assertIn("?? bin/private.txt", status)
        self.assertIn("?? tests/private.txt", status)

    def test_17c_seedd_disables_commit_hooks(self):
        (self.repo / "private.txt").write_text("hook must not commit me\n")
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\ngit add -- private.txt\n")
        hook.chmod(0o755)
        self.drop(DELTA)
        r = self.seedd()
        self.assertIn("committed", r.stdout)
        committed = sh(self.repo, "git", "show", "--pretty=format:", "--name-only", "HEAD").stdout
        self.assertNotIn("private.txt", committed)
        self.assertIn("?? private.txt", sh(self.repo, "git", "status", "--porcelain").stdout)

    def test_17d_evidence_path_must_be_a_regular_file(self):
        evidence = self.repo / "evidence.jsonl"
        evidence.mkdir()
        (evidence / "private.txt").write_text("must not be committed\n")
        before = self.seed_text()
        self.drop(DELTA)
        r = self.seedd()
        self.assertIn("HELD", r.stdout)
        self.assertIn("regular file", r.stdout)
        self.assertEqual(before, self.seed_text())
        self.assertEqual(len(sh(self.repo, "git", "log", "--oneline").stdout.splitlines()), 1)

    def test_17e_setup_rejects_non_regular_allowlist_path(self):
        fresh = Path(self.tmp) / "setup-nonregular"
        shutil.copytree(
            SRC, fresh,
            ignore=shutil.ignore_patterns(".git", "history", "inbox", "*.lock",
                                          "__pycache__", "evidence.jsonl"))
        for c in (["git", "init", "-q"],
                  ["git", "config", "user.email", "t@t"],
                  ["git", "config", "user.name", "t"]):
            self.assertEqual(sh(fresh, *c).returncode, 0)
        evidence = fresh / "evidence.jsonl"
        evidence.mkdir()
        (evidence / "private.txt").write_text("must not be committed\n")
        r = subprocess.run(["bash", "setup.sh"], cwd=fresh,
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("regular file", r.stdout + r.stderr)
        self.assertEqual(sh(fresh, "git", "log", "--oneline").returncode, 128)

    # 18 — held and archived evidence is collision-safe
    def test_18a_held_collision_preserves_both(self):
        prior = self.repo / "inbox" / "d.held.md"
        prior.write_text("prior held evidence\n")
        self.drop("## Brand New Field\nnew held evidence\n")
        self.seedd()
        held = sorted((self.repo / "inbox").glob("*.held.md"))
        self.assertEqual(len(held), 2)
        self.assertEqual(prior.read_text(), "prior held evidence\n")
        self.assertTrue(any("new held evidence" in path.read_text() for path in held))

    def test_18b_history_collision_preserves_both(self):
        module = load_seedd(self.repo)

        class FixedDateTime:
            @classmethod
            def now(cls):
                return datetime(2026, 8, 3, 12, 0, 0)

        module.datetime = FixedDateTime
        for value in ("First archive.", "Second archive."):
            delta = self.repo / "inbox" / "same.md"
            delta.write_text(f"## L2 Pending Decision\n{value}\n")
            module.commit(delta)
        history = sorted((self.repo / "history").glob("*.md"))
        self.assertEqual(len(history), 2)
        self.assertEqual({path.read_text() for path in history}, {
            "## L2 Pending Decision\nFirst archive.\n",
            "## L2 Pending Decision\nSecond archive.\n",
        })

    def test_18c_held_move_retries_atomic_race(self):
        module = load_seedd(self.repo)
        delta = self.repo / "inbox" / "race.md"
        delta.write_text("payload\n")
        real_link = os.link
        raced = False

        def racing_link(source, destination, *args, **kwargs):
            nonlocal raced
            if not raced:
                raced = True
                Path(destination).write_text("racer evidence\n")
                raise FileExistsError("injected race")
            return real_link(source, destination, *args, **kwargs)

        with mock.patch.object(module.os, "link", side_effect=racing_link):
            module.hold(delta, "test race")
        held = sorted((self.repo / "inbox").glob("race*.held.md"))
        self.assertEqual(len(held), 2)
        self.assertTrue(any(path.read_text() == "racer evidence\n" for path in held))
        self.assertTrue(any("payload" in path.read_text() for path in held))

    def test_18d_archive_move_retries_atomic_race(self):
        module = load_seedd(self.repo)

        class FixedDateTime:
            @classmethod
            def now(cls):
                return datetime(2026, 8, 3, 12, 0, 0)

        module.datetime = FixedDateTime
        delta = self.repo / "inbox" / "race.md"
        delta.write_text(DELTA)
        real_link = os.link
        raced = False

        def racing_link(source, destination, *args, **kwargs):
            nonlocal raced
            if not raced:
                raced = True
                Path(destination).write_text("racer evidence\n")
                raise FileExistsError("injected race")
            return real_link(source, destination, *args, **kwargs)

        with mock.patch.object(module.os, "link", side_effect=racing_link):
            module.commit(delta)
        history = sorted((self.repo / "history").glob("*.md"))
        self.assertEqual(len(history), 2)
        self.assertTrue(any(path.read_text() == "racer evidence\n" for path in history))
        self.assertTrue(any(path.read_text() == DELTA for path in history))

    def test_18e_destination_survives_source_unlink_race(self):
        module = load_seedd(self.repo)
        source = self.repo / "inbox" / "source.md"
        destination = self.repo / "history" / "destination.md"
        source.write_text("irreplaceable payload\n")
        real_link = os.link

        def link_then_source_is_unlinked(src, dst, *args, **kwargs):
            real_link(src, dst, *args, **kwargs)
            Path(src).unlink()

        with mock.patch.object(module.os, "link",
                               side_effect=link_then_source_is_unlinked):
            moved = module.move_no_clobber(source, lambda counter: destination)
        self.assertEqual(moved, destination)
        self.assertFalse(source.exists())
        self.assertEqual(destination.read_text(), "irreplaceable payload\n")

    # 19 — empty updates and indented directives cannot bypass validation
    def test_19a_no_field_delta_holds(self):
        self.drop("prose without a Seed field\n")
        r = self.seedd()
        self.assertIn("HELD", r.stdout)
        self.assertIn("no field", r.stdout)

    def test_19b_indented_probe_is_executed_and_stripped(self):
        srv, url = start_fake_ollama("TRANSFERS — same mechanism")
        try:
            self.drop("## L2 Pending Decision\nShip.\n  [probe] claim A || claim A perturbed\n")
            r = self.seedd({"OLLAMA_URL": url})
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertIn("probe:transfers", r.stdout)
        self.assertIn("committed", r.stdout)
        self.assertNotIn("[probe]", self.seed_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
