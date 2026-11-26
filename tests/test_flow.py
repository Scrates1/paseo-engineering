from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
FLOW_PATH = REPO_ROOT / "skills" / "paseo-engineering" / "scripts" / "flow.py"
FLOW_ZH_PATH = REPO_ROOT / "skills" / "zh-CN" / "paseo-engineering" / "scripts" / "flow.py"


def _load_flow():
    prev = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location("paseo_gatekeeper_flow", str(FLOW_PATH))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return module
    finally:
        sys.dont_write_bytecode = prev


flow = _load_flow()

MOCK_PASEO_SOURCE = r'''
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(os.environ["MOCK_PASEO_ROOT"])
root.mkdir(parents=True, exist_ok=True)
argv = sys.argv[1:]
home = None
if len(argv) >= 2 and argv[0] == "--home":
    home = argv[1]
    argv = argv[2:]
with (root / "calls.jsonl").open("a") as fh:
    fh.write(json.dumps({"argv": argv, "home": home, "paseo_host": os.environ.get("PASEO_HOST")}) + "\n")
mode = os.environ.get("MOCK_PASEO_MODE", "ok")
if mode == "daemon-down":
    sys.stderr.write("Error: connect ECONNREFUSED 127.0.0.1:6767 - is the daemon running?\n")
    sys.exit(1)
if mode == "fail":
    sys.stderr.write("Error: internal workspace failure\n")
    sys.exit(1)
if mode == "garbage" and argv[:2] == ["provider", "ls"]:
    print("this is not json")
    sys.exit(0)
db_path = root / "workspaces.json"
db = json.loads(db_path.read_text()) if db_path.exists() else {}


def opt(name):
    return argv[argv.index(name) + 1] if name in argv else None


def out(obj):
    print(json.dumps(obj))
    sys.exit(0)


if argv[:2] == ["project", "create"]:
    out({"projectId": "prj_mock", "path": argv[-1]})
if argv[:2] == ["workspace", "create"]:
    repo, branch, base = opt("--path"), opt("--new-branch"), opt("--base")
    actual = branch + "-1" if mode == "rename-branch" else branch
    ws_id = "wks_%d" % (len(db) + 1)
    wt = root / "worktrees" / ws_id
    wt.parent.mkdir(parents=True, exist_ok=True)
    res = subprocess.run(["git", "-C", repo, "worktree", "add", "-q", "-b", actual, str(wt), base],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0:
        sys.stderr.write(res.stderr.decode())
        sys.exit(1)
    db[ws_id] = str(wt)
    db_path.write_text(json.dumps(db))
    out({"workspaceId": ws_id, "cwd": str(wt), "background": "--background" in argv})
if argv[:2] == ["workspace", "archive"]:
    wt = db.get(argv[2])
    if wt and Path(wt).exists():
        shutil.rmtree(wt)
    out({"workspaceId": argv[2], "archived": True})
providers = json.loads(os.environ.get("MOCK_PASEO_PROVIDERS", "{}"))
if argv[:2] == ["provider", "ls"]:
    out([{"provider": p, "status": "available", "enabled": "Enabled"} for p in providers])
if argv[:2] == ["provider", "models"]:
    out([{"id": m, "model": m} for m in providers.get(argv[2], [])])
sys.stderr.write("unsupported mock call: %r\n" % (argv,))
sys.exit(2)
'''

WORKER = "claude/opus"
REVIEWER = "codex/gpt-6.1-sol"
REVIEWER_B = "antigravity/gemini-4-neon-xhigh"


@unittest.skipIf(os.name == "nt", "POSIX-only integration tests")
class FlowTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="flow-test-")).resolve()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.git(self.repo, "init", "-q")
        self.git(self.repo, "symbolic-ref", "HEAD", "refs/heads/main")
        for key, val in (("user.name", "Flow Test"), ("user.email", "flow@example.com"),
                         ("commit.gpgsign", "false"), ("core.autocrlf", "false")):
            self.git(self.repo, "config", key, val)
        (self.repo / "app.py").write_text("def answer():\n    return 41\n\n\ndef other():\n    return 1\n")
        (self.repo / "README.md").write_text("demo\n")
        self.git(self.repo, "add", "-A")
        self.git(self.repo, "commit", "-q", "-m", "initial")
        self.run_dir = self.tmp / "run"
        self.paseo_home = self.tmp / "paseo-home"
        self.mock_root = self.tmp / "paseo-mock"
        mock_bin = self.tmp / "bin" / "paseo"
        mock_bin.parent.mkdir()
        mock_bin.write_text(f"#!{sys.executable}\n" + MOCK_PASEO_SOURCE)
        mock_bin.chmod(0o755)
        self.env = mock.patch.dict(os.environ, {
            "PASEO_BIN": str(mock_bin),
            "MOCK_PASEO_ROOT": str(self.mock_root),
            "MOCK_PASEO_MODE": "ok",
            "MOCK_PASEO_PROVIDERS": "{}",
            "PASEO_HOST": "stale-host:1",
        })
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------------------------------------------------------------- helpers
    def git(self, cwd, *args) -> str:
        res = subprocess.run(["git", "-C", str(cwd)] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            raise AssertionError(f"git {args} failed: {res.stderr.decode()}")
        return res.stdout.decode().strip()

    def flow(self, *args, expect=0, glob=()):
        argv = ["--run-dir", str(self.run_dir), "--paseo-home", str(self.paseo_home)] + list(glob) + list(args)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = flow.main(argv)
            except SystemExit as exc:
                code = exc.code
        if expect is not None:
            self.assertEqual(code, expect, f"flow {args} -> {code}\nstdout:{out.getvalue()}\nstderr:{err.getvalue()}")
        return code, out.getvalue(), err.getvalue()

    def reject(self, *args, contains=None, glob=()):
        code, out, err = self.flow(*args, expect=None, glob=glob)
        self.assertNotEqual(code, 0, f"expected rejection for {args}: {out}")
        if contains:
            self.assertIn(contains, err + out)
        return err

    def state(self):
        return json.loads((self.run_dir / "state.json").read_text())

    def slice(self, sid):
        return self.state()["slices"][sid]

    def wt(self, sid) -> Path:
        return Path(self.slice(sid)["worktree"])

    def commit(self, cwd, rel, content, msg="change") -> str:
        path = Path(cwd) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        self.git(cwd, "add", "-A")
        self.git(cwd, "commit", "-q", "-m", msg)
        return self.git(cwd, "rev-parse", "HEAD")

    def calls(self):
        log = self.mock_root / "calls.jsonl"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]

    def ledger_snapshot(self):
        return ((self.run_dir / "state.json").read_bytes(), (self.run_dir / "status.md").read_bytes(),
                self.git(self.repo, "rev-parse", "HEAD"))

    def gear1_ready(self, slices="main-fix"):
        self.flow("init", "--repo", str(self.repo))
        self.flow("triage", "--symptom", "api returns 41", "--root", "answer() constant", "--gear", "1",
                  "--slices", slices)

    def implement(self, sid, branch, worker=WORKER, rel="app.py", content=None, backend="paseo"):
        self.flow("isolate", "--slice", sid, "--branch", branch, "--backend", backend)
        self.flow("assign-worker", "--slice", sid, "--model", worker)
        wt = self.wt(sid)
        if content is None:
            content = (wt / rel).read_text().replace("41", "42") if (wt / rel).exists() else "x\n"
        return self.commit(wt, rel, content, f"fix {sid}")

    def gear2_ready(self, slices="a,b"):
        self.flow("init", "--repo", str(self.repo))
        self.flow("triage", "--symptom", "slow endpoint", "--root", "n+1 query loop", "--gear", "2",
                  "--lenses", "performance")
        self.flow("record-explore", "--author-models", REVIEWER_B, "--summary", "two candidate roots")
        self.flow("record-redteam", "--model", REVIEWER, "--summary", "falsified candidate 2")
        self.flow("align", "--slices", slices, "--summary", "plan")
        self.flow("record-prereview", "--reviewer-a-model", REVIEWER, "--reviewer-b-model", REVIEWER_B,
                  "--planned-worker-models", WORKER, "--blockers", "0")
        self.assertEqual(self.state()["state"], "EXECUTION_READY")

    def pass_gear2(self, sid):
        for lens, model in (("A", REVIEWER), ("B", REVIEWER_B)):
            self.flow("enter-review", "--slice", sid, "--reviewer-model", model, "--lens", lens)
        for lens in ("A", "B"):
            self.flow("record-review", "--slice", sid, "--verdict", "PASS", "--blockers", "0", "--lens", lens)


class NormalizeFamilyTest(unittest.TestCase):
    def test_family_table(self) -> None:
        table = {
            "antigravity/claude-opus-5-5-high": "anthropic",
            "antigravity/gemini-4-neon-xhigh": "google",
            "claude/opus": "anthropic",
            "claude-sonnet-5-5": "anthropic",
            "anthropic/haiku": "anthropic",
            "openai/gpt-6.1-sol": "openai",
            "codex/gpt-6.1-sol": "openai",
            "  CODEX/GPT-6.1-SOL ": "openai",
            "o3-mini": "openai",
            "opencode/deepseek-v4": "deepseek",
            "qwen3-coder": "qwen",
            "antigravity/mystery-model": "other:mystery",
            "codex/default": "openai",
        }
        for spec, fam in table.items():
            with self.subTest(spec=spec):
                self.assertEqual(flow.normalize_family(spec), fam)
        self.assertNotEqual(flow.normalize_family("antigravity/claude-opus-5-5-high"),
                            flow.normalize_family("antigravity/gemini-4-neon-xhigh"))
        with self.assertRaises(flow.FlowError):
            flow.normalize_family("   ")


class SnapshotTest(FlowTestBase):
    def test_snapshot_detects_untracked_content_and_tracked_edits(self) -> None:
        (self.repo / "notes.txt").write_text("aaaa")
        s1 = flow.compute_repo_snapshot(self.repo)
        self.assertFalse(s1["is_clean"])
        self.assertRegex(s1["head_sha"], r"^[0-9a-f]{40}$")
        (self.repo / "notes.txt").write_text("bbbb")
        s2 = flow.compute_repo_snapshot(self.repo)
        self.assertEqual(s1["head_sha"], s2["head_sha"])
        self.assertNotEqual(s1["diff_hash"], s2["diff_hash"])
        (self.repo / "notes.txt").unlink()
        clean = flow.compute_repo_snapshot(self.repo)
        self.assertTrue(clean["is_clean"])
        (self.repo / "README.md").write_text("edited\n")
        self.assertNotEqual(flow.compute_repo_snapshot(self.repo)["diff_hash"], clean["diff_hash"])


class GearOneFlowTest(FlowTestBase):
    def test_gear1_happy_path_with_paseo_backend(self) -> None:
        self.gear1_ready()
        st = self.state()
        self.assertEqual((st["state"], st["gear"], st["aligned_slices"]), ("EXECUTION_READY", 1, ["main-fix"]))
        for name in ("state.json", "status.md"):
            self.assertEqual((self.run_dir / name).stat().st_mode & 0o777, 0o600)
        head = self.implement("main-fix", "fix/answer")
        sl = self.slice("main-fix")
        self.assertEqual(sl["backend"], "paseo")
        self.assertEqual(sl["workspace_id"], "wks_1")
        self.assertEqual(self.git(self.wt("main-fix"), "rev-parse", "--abbrev-ref", "HEAD"), "fix/answer")
        self.flow("enter-review", "--slice", "main-fix", "--reviewer-model", REVIEWER)
        self.flow("record-review", "--slice", "main-fix", "--verdict", "PASS", "--blockers", "0")
        self.assertEqual(self.slice("main-fix")["approved_head_sha"], head)
        self.flow("integrate", "--slice", "main-fix")
        st = self.state()
        self.assertEqual(st["state"], "MERGED_PENDING_VERIFY")
        self.assertEqual(st["expected_main_head_sha"], head)
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), head)
        wt = self.wt("main-fix")
        self.flow("verify-integration", "--cmd", "grep -q 42 app.py")
        self.assertEqual(self.state()["state"], "COMPLETED")
        self.assertFalse(wt.exists())
        self.assertEqual(self.git(self.repo, "branch", "--list", "fix/answer"), "")
        calls = self.calls()
        self.assertIn(["workspace", "archive", "wks_1"], [c["argv"] for c in calls])
        create = [c["argv"] for c in calls if c["argv"][:2] == ["workspace", "create"]][0]
        self.assertIn("--no-background", create)
        self.assertEqual(create[create.index("--base") + 1], st["initial_base_sha"])
        for call in calls:
            self.assertEqual(call["home"], str(self.paseo_home))
            self.assertIsNone(call["paseo_host"])
        _, out, _ = self.flow("status", "--json")
        self.assertEqual(json.loads(out)["state"], "COMPLETED")

    def test_verify_integration_failure_keeps_worktree(self) -> None:
        self.gear1_ready()
        self.implement("main-fix", "fix/answer")
        self.flow("enter-review", "--slice", "main-fix", "--reviewer-model", REVIEWER)
        self.flow("record-review", "--slice", "main-fix", "--verdict", "PASS", "--blockers", "0")
        self.flow("integrate", "--slice", "main-fix")
        self.flow("verify-integration", "--cmd", "exit 3", expect=flow.EXIT_VERIFY_FAILED)
        self.assertEqual(self.state()["state"], "MERGED_PENDING_VERIFY")
        self.assertTrue(self.wt("main-fix").exists())

    def test_same_family_review_blocked_and_cross_family_router_allowed(self) -> None:
        self.gear1_ready()
        self.implement("main-fix", "fix/answer", worker="antigravity/claude-opus-5-5-high")
        self.reject("enter-review", "--slice", "main-fix", "--reviewer-model", "claude/opus", contains="HARD GATE #2")
        self.reject("enter-review", "--slice", "main-fix", "--reviewer-model", "claude-sonnet-5-5")
        self.flow("enter-review", "--slice", "main-fix", "--reviewer-model", "antigravity/gemini-4-neon-xhigh")
        self.assertEqual(self.slice("main-fix")["state"], "IN_REVIEW")

    def test_uncommitted_zero_commit_and_post_review_injection_blocked(self) -> None:
        self.gear1_ready()
        self.flow("isolate", "--slice", "main-fix", "--branch", "fix/answer")
        self.flow("assign-worker", "--slice", "main-fix", "--model", WORKER)
        self.reject("enter-review", "--slice", "main-fix", "--reviewer-model", REVIEWER, contains="no commits")
        wt = self.wt("main-fix")
        (wt / "app.py").write_text("dirty\n")
        self.reject("enter-review", "--slice", "main-fix", "--reviewer-model", REVIEWER, contains="uncommitted")
        self.git(wt, "commit", "-q", "-am", "fix")
        self.flow("enter-review", "--slice", "main-fix", "--reviewer-model", REVIEWER)
        self.commit(wt, "extra.txt", "sneaky\n", "during review")
        self.reject("record-review", "--slice", "main-fix", "--verdict", "PASS", "--blockers", "0", contains="moved")
        self.git(wt, "reset", "-q", "--hard", "HEAD~1")
        self.flow("record-review", "--slice", "main-fix", "--verdict", "PASS", "--blockers", "0")
        self.commit(wt, "extra.txt", "unreviewed\n", "after approval")
        self.reject("integrate", "--slice", "main-fix", contains="approved_head_sha")
        self.assertEqual(self.state()["state"], "EXECUTION_READY")

    def test_zero_fix_resubmission_and_blocking_requirements(self) -> None:
        self.gear1_ready()
        self.implement("main-fix", "fix/answer")
        self.flow("enter-review", "--slice", "main-fix", "--reviewer-model", REVIEWER)
        self.reject("record-review", "--slice", "main-fix", "--verdict", "BLOCKING", "--blockers", "1")
        self.reject("record-review", "--slice", "main-fix", "--verdict", "BLOCKING", "--blockers", "0",
                    "--counterexample", "x")
        self.reject("record-review", "--slice", "main-fix", "--verdict", "PASS", "--blockers", "2")
        self.flow("record-review", "--slice", "main-fix", "--verdict", "BLOCKING", "--blockers", "1",
                  "--counterexample", "answer(-1) crashes")
        self.assertEqual(self.slice("main-fix")["state"], "CHANGES_REQUESTED")
        self.reject("enter-review", "--slice", "main-fix", "--reviewer-model", REVIEWER, contains="zero-fix")
        self.commit(self.wt("main-fix"), "app.py", "def answer():\n    return 42\n", "real fix")
        self.flow("enter-review", "--slice", "main-fix", "--reviewer-model", REVIEWER)

    def test_gear1_two_blocking_rounds_escalate_and_assign_cannot_reset(self) -> None:
        self.gear1_ready()
        self.implement("main-fix", "fix/answer")
        for i in range(2):
            if i:
                self.commit(self.wt("main-fix"), "app.py", f"v{i}\n", f"attempt {i}")
            self.flow("enter-review", "--slice", "main-fix", "--reviewer-model", REVIEWER)
            self.flow("record-review", "--slice", "main-fix", "--verdict", "BLOCKING", "--blockers", "1",
                      "--counterexample", f"counterexample {i}")
        st = self.state()
        self.assertEqual(st["slices"]["main-fix"]["state"], "MUST_ESCALATE_GEAR2")
        self.assertEqual((st["gear"], st["state"]), (2, "TRIAGED"))
        self.reject("assign-worker", "--slice", "main-fix", "--model", "codex/gpt-6.1-sol", contains="assign-worker is only legal")
        self.reject("integrate", "--slice", "main-fix")
        self.flow("discard-slice", "--slice", "main-fix", "--reason", "escalated")
        self.assertEqual(self.git(self.repo, "branch", "--list", "fix/answer"), "")

    def test_gear1_two_verify_failures_escalate(self) -> None:
        self.gear1_ready()
        self.implement("main-fix", "fix/answer")
        self.flow("record-verify-fail", "--slice", "main-fix", "--summary", "unit tests red")
        self.assertEqual(self.slice("main-fix")["state"], "IMPLEMENTING")
        self.flow("record-verify-fail", "--slice", "main-fix", "--summary", "still red")
        st = self.state()
        self.assertEqual(st["slices"]["main-fix"]["state"], "MUST_ESCALATE_GEAR2")
        self.assertEqual((st["gear"], st["state"]), (2, "TRIAGED"))

    def test_main_repo_drift_is_blocked(self) -> None:
        (self.repo / "scratch.txt").write_text("1111")
        self.gear1_ready()
        (self.repo / "scratch.txt").write_text("2222")
        self.reject("isolate", "--slice", "main-fix", "--branch", "fix/a", contains="working tree changed")
        (self.repo / "scratch.txt").write_text("1111")
        self.implement("main-fix", "fix/a")
        (self.repo / "README.md").write_text("rogue edit\n")
        self.reject("enter-review", "--slice", "main-fix", "--reviewer-model", REVIEWER, contains="HARD GATE")
        self.git(self.repo, "checkout", "--", "README.md")
        self.commit(self.repo, "rogue.txt", "rogue\n", "rogue commit")
        self.reject("enter-review", "--slice", "main-fix", "--reviewer-model", REVIEWER, contains="HEAD drifted")

    def test_triage_validation_and_ledger_reinit_refused(self) -> None:
        self.flow("init", "--repo", str(self.repo))
        self.reject("init", "--repo", str(self.repo), contains="already exists")
        self.reject("triage", "--symptom", " ", "--root", "x", "--gear", "1")
        self.reject("triage", "--symptom", "same", "--root", "same", "--gear", "1", contains="same-site")
        self.flow("triage", "--symptom", "same", "--root", "same", "--gear", "1", "--same-site-justified", "config typo")
        self.reject("triage", "--symptom", "a", "--root", "b", "--gear", "2", contains="--re-triage")
        self.reject("init", "--repo", str(self.repo), glob=["--run-dir", str(self.repo / "inner")])

    def test_re_triage_supersedes_slices(self) -> None:
        self.gear1_ready()
        self.implement("main-fix", "fix/answer")
        self.flow("triage", "--symptom", "a", "--root", "b", "--gear", "2", "--re-triage")
        self.assertEqual(self.slice("main-fix")["state"], "SUPERSEDED")
        self.reject("assign-worker", "--slice", "main-fix", "--model", WORKER)
        self.reject("enter-review", "--slice", "main-fix", "--reviewer-model", REVIEWER)
        self.flow("discard-slice", "--slice", "main-fix", "--reason", "superseded")
        self.assertFalse(Path(self.slice("main-fix")["worktree"]).exists())


class PaseoBackendTest(FlowTestBase):
    def test_existing_branch_is_refused_before_paseo_call(self) -> None:
        self.gear1_ready()
        self.git(self.repo, "branch", "fix/answer")
        self.reject("isolate", "--slice", "main-fix", "--branch", "fix/answer", contains="already exists")
        self.assertFalse([c for c in self.calls() if c["argv"][:2] == ["workspace", "create"]])

    def test_silent_branch_rename_is_detected_and_rolled_back(self) -> None:
        self.gear1_ready()
        os.environ["MOCK_PASEO_MODE"] = "rename-branch"
        self.reject("isolate", "--slice", "main-fix", "--branch", "fix/answer", contains="silent rename")
        self.assertEqual(self.git(self.repo, "branch", "--list", "fix/answer*"), "")
        self.assertNotIn("main-fix", self.state()["slices"])
        self.assertFalse((self.mock_root / "worktrees" / "wks_1").exists())

    def test_paseo_backend_fails_hard_and_auto_falls_back_only_when_daemon_down(self) -> None:
        self.gear1_ready()
        os.environ["MOCK_PASEO_MODE"] = "daemon-down"
        self.reject("isolate", "--slice", "main-fix", "--branch", "fix/answer", "--backend", "paseo",
                    contains="--backend paseo failed hard")
        self.assertEqual(self.git(self.repo, "branch", "--list", "fix/answer"), "")
        os.environ["MOCK_PASEO_MODE"] = "fail"
        self.reject("isolate", "--slice", "main-fix", "--branch", "fix/answer", "--backend", "auto",
                    contains="internal workspace failure")
        os.environ["MOCK_PASEO_MODE"] = "daemon-down"
        self.flow("isolate", "--slice", "main-fix", "--branch", "fix/answer", "--backend", "auto")
        sl = self.slice("main-fix")
        self.assertEqual(sl["backend"], "git")
        self.assertEqual(Path(sl["worktree"]), (self.run_dir / "worktrees" / "main-fix").resolve())

    def test_missing_binary(self) -> None:
        self.gear1_ready()
        os.environ["PASEO_BIN"] = str(self.tmp / "nope" / "paseo")
        self.reject("isolate", "--slice", "main-fix", "--branch", "fix/a", "--backend", "paseo")
        self.flow("isolate", "--slice", "main-fix", "--branch", "fix/a")
        self.assertEqual(self.slice("main-fix")["backend"], "git")

    def test_discard_archives_and_deletes_branch_then_reisolate(self) -> None:
        self.gear1_ready()
        self.flow("isolate", "--slice", "main-fix", "--branch", "fix/answer", "--background")
        create = [c["argv"] for c in self.calls() if c["argv"][:2] == ["workspace", "create"]][0]
        self.assertIn("--background", create)
        wt = self.wt("main-fix")
        self.reject("discard-slice", "--slice", "main-fix", "--reason", "  ")
        self.flow("discard-slice", "--slice", "main-fix", "--reason", "wrong approach")
        self.assertFalse(wt.exists())
        self.assertEqual(self.git(self.repo, "branch", "--list", "fix/answer"), "")
        self.assertIn(["workspace", "archive", "wks_1"], [c["argv"] for c in self.calls()])
        self.flow("isolate", "--slice", "main-fix", "--branch", "fix/answer")
        self.assertEqual(len(self.state()["slice_archive"]), 1)

    def test_single_family_host_is_verified_not_self_reported(self) -> None:
        self.gear1_ready()
        self.implement("main-fix", "fix/answer")
        os.environ["MOCK_PASEO_PROVIDERS"] = json.dumps({"claude": ["opus"], "codex": ["gpt-6.1-sol"]})
        self.reject("enter-review", "--slice", "main-fix", "--reviewer-model", "claude/sonnet", "--single-family-host",
                    contains="REJECTED")
        os.environ["MOCK_PASEO_PROVIDERS"] = json.dumps({"claude": ["opus"], "antigravity": ["gemini-4-neon-xhigh"]})
        self.reject("enter-review", "--slice", "main-fix", "--reviewer-model", "claude/sonnet", "--single-family-host",
                    contains="2 distinct model families")
        os.environ["MOCK_PASEO_PROVIDERS"] = json.dumps({"claude": ["opus", "sonnet"]})
        self.flow("enter-review", "--slice", "main-fix", "--reviewer-model", "claude/sonnet", "--single-family-host")
        self.assertTrue(self.slice("main-fix")["active_lenses"]["default"]["single_family_host"])

    def test_online_models_json_flag_is_removed(self) -> None:
        self.gear1_ready()
        path = self.tmp / "fake.json"
        path.write_text(json.dumps(["claude/opus"]))
        before = (self.run_dir / "state.json").read_bytes()
        self.reject("status", glob=["--online-models-json", str(path)])
        self.assertEqual((self.run_dir / "state.json").read_bytes(), before)
        self.assertFalse(hasattr(flow.Ctx(self.run_dir, None), "online_models_json"))

    def test_single_family_host_rejects_empty_unparseable_and_foreign_family(self) -> None:
        self.gear1_ready()
        self.implement("main-fix", "fix/answer")
        args = ("enter-review", "--slice", "main-fix", "--reviewer-model", "claude/sonnet", "--single-family-host")
        os.environ["MOCK_PASEO_PROVIDERS"] = "{}"
        self.reject(*args, contains="0 online model families")
        os.environ["MOCK_PASEO_PROVIDERS"] = json.dumps({"claude": []})
        self.reject(*args, contains="0 online model families")
        os.environ["MOCK_PASEO_PROVIDERS"] = json.dumps({"codex": ["gpt-6.1-sol"]})
        self.reject(*args, contains="not the sole online family")
        os.environ["MOCK_PASEO_PROVIDERS"] = json.dumps({"claude": ["opus"]})
        os.environ["MOCK_PASEO_MODE"] = "garbage"
        self.reject(*args, contains="cannot verify")
        os.environ["MOCK_PASEO_MODE"] = "daemon-down"
        self.reject(*args, contains="cannot verify")
        self.assertEqual(self.slice("main-fix")["state"], "IMPLEMENTING")


class GearTwoFlowTest(FlowTestBase):
    def test_gear2_two_slices_dual_lens_conflict_rebase_and_rereview(self) -> None:
        self.gear2_ready()
        self.reject("isolate", "--slice", "zzz", "--branch", "feat/zzz", contains="aligned_slices")
        self.implement("a", "feat/a", content="def answer():\n    return 42\n")
        self.implement("b", "feat/b", content="def answer():\n    return 43\n")
        self.reject("enter-review", "--slice", "a", "--reviewer-model", REVIEWER, "--lens", "default", contains="not allowed")
        self.flow("enter-review", "--slice", "a", "--reviewer-model", REVIEWER, "--lens", "A")
        self.flow("record-review", "--slice", "a", "--verdict", "PASS", "--blockers", "0", "--lens", "A")
        self.assertEqual(self.slice("a")["state"], "IN_REVIEW")
        self.reject("integrate", "--slice", "a")
        self.reject("enter-review", "--slice", "a", "--reviewer-model", WORKER, "--lens", "B", contains="HARD GATE #2")
        self.flow("enter-review", "--slice", "a", "--reviewer-model", REVIEWER_B, "--lens", "B")
        self.flow("record-review", "--slice", "a", "--verdict", "PASS", "--blockers", "0", "--lens", "B")
        self.assertEqual(self.slice("a")["state"], "REVIEW_PASSED")
        self.pass_gear2("b")
        self.flow("integrate", "--slice", "a")
        main_after_a = self.git(self.repo, "rev-parse", "HEAD")
        self.assertEqual(self.state()["state"], "EXECUTION_READY")
        code, _, err = self.flow("integrate", "--slice", "b", expect=flow.EXIT_CONFLICT)
        self.assertIn("NEEDS_REBASE", err)
        self.assertEqual(self.slice("b")["state"], "NEEDS_REBASE")
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), main_after_a)
        self.assertEqual(self.git(self.repo, "status", "--porcelain"), "")
        self.reject("integrate", "--slice", "b")
        wtb = self.wt("b")
        self.reject("mark-rebased", "--slice", "b", "--new-slice-base", self.state()["initial_base_sha"])
        self.git(wtb, "reset", "-q", "--hard", main_after_a)
        self.commit(wtb, "other.txt", "independent\n", "rebased fix b")
        self.flow("mark-rebased", "--slice", "b", "--new-slice-base", main_after_a)
        sl = self.slice("b")
        self.assertEqual((sl["state"], sl["approved_head_sha"], sl["lens_passes"]), ("IMPLEMENTING", None, {}))
        self.reject("integrate", "--slice", "b")
        self.pass_gear2("b")
        self.flow("integrate", "--slice", "b")
        self.assertEqual(self.state()["state"], "MERGED_PENDING_VERIFY")
        self.flow("verify-integration", "--cmd", "test -f other.txt && grep -q 42 app.py")
        self.assertEqual(self.state()["state"], "COMPLETED")
        for sid, br in (("a", "feat/a"), ("b", "feat/b")):
            self.assertFalse(self.wt(sid).exists())
            self.assertEqual(self.git(self.repo, "branch", "--list", br), "")

    def test_gear2_round_cap_cannot_be_bypassed(self) -> None:
        self.gear2_ready(slices="a")
        self.implement("a", "feat/a")
        for i in range(2):
            if i:
                self.commit(self.wt("a"), "app.py", f"attempt {i}\n", f"attempt {i}")
            self.flow("enter-review", "--slice", "a", "--reviewer-model", REVIEWER, "--lens", "A")
            self.flow("record-review", "--slice", "a", "--verdict", "BLOCKING", "--blockers", "2", "--lens", "A",
                      "--counterexample", "race on concurrent calls")
        self.assertEqual(self.slice("a")["state"], "ROUND_CAP_REACHED")
        self.reject("assign-worker", "--slice", "a", "--model", WORKER, contains="round caps")
        self.reject("enter-review", "--slice", "a", "--reviewer-model", REVIEWER, "--lens", "A")
        self.reject("record-review", "--slice", "a", "--verdict", "PASS", "--blockers", "0", "--lens", "A")
        self.reject("resolve-dispute", "--slice", "a", "--action", "approve", "--reason", "trust me")
        self.reject("resolve-dispute", "--slice", "a", "--action", "user-escalate", "--reason", " ")
        self.flow("resolve-dispute", "--slice", "a", "--action", "user-escalate", "--reason", "need ruling")
        self.assertEqual(self.slice("a")["state"], "AWAITING_USER_RULING")
        self.reject("integrate", "--slice", "a")
        self.flow("reset-rounds", "--slice", "a", "--reason", "user grants one more round")
        sl = self.slice("a")
        self.assertEqual((sl["state"], sl["review_rounds"]), ("CHANGES_REQUESTED", 1))
        self.reject("enter-review", "--slice", "a", "--reviewer-model", REVIEWER, "--lens", "A", contains="zero-fix")
        self.commit(self.wt("a"), "app.py", "final\n", "final fix")
        self.pass_gear2("a")
        self.assertEqual(self.slice("a")["state"], "REVIEW_PASSED")

    def test_round_cap_discard_cannot_reset_counters_in_same_epoch(self) -> None:
        self.gear2_ready(slices="a")
        self.implement("a", "feat/a")
        for i in range(2):
            if i:
                self.commit(self.wt("a"), "app.py", f"attempt {i}\n")
            self.flow("enter-review", "--slice", "a", "--reviewer-model", REVIEWER, "--lens", "A")
            self.flow("record-review", "--slice", "a", "--verdict", "BLOCKING", "--blockers", "1", "--lens", "A",
                      "--counterexample", "bug")
        self.flow("resolve-dispute", "--slice", "a", "--action", "discard", "--reason", "drop")
        self.assertEqual(self.git(self.repo, "branch", "--list", "feat/a"), "")
        self.reject("isolate", "--slice", "a", "--branch", "feat/a2", contains="round cap")

    def test_round_cap_re_triage_supersedes(self) -> None:
        self.gear2_ready(slices="a")
        self.implement("a", "feat/a")
        for i in range(2):
            if i:
                self.commit(self.wt("a"), "app.py", f"attempt {i}\n")
            self.flow("enter-review", "--slice", "a", "--reviewer-model", REVIEWER, "--lens", "A")
            self.flow("record-review", "--slice", "a", "--verdict", "BLOCKING", "--blockers", "1", "--lens", "A",
                      "--counterexample", "bug")
        self.flow("resolve-dispute", "--slice", "a", "--action", "re-triage", "--reason", "wrong root")
        st = self.state()
        self.assertEqual((st["slices"]["a"]["state"], st["state"], st["aligned_slices"]), ("SUPERSEDED", "TRIAGED", []))
        self.reject("integrate", "--slice", "a")

    def test_redteam_and_prereview_family_gates(self) -> None:
        self.flow("init", "--repo", str(self.repo))
        self.flow("triage", "--symptom", "s", "--root", "r", "--gear", "2")
        self.flow("record-explore", "--author-models", "claude/opus,codex/gpt-6.1-sol", "--summary", "e")
        self.flow("record-redteam", "--model", "claude-sonnet-5-5", "--summary", "partial")
        self.assertEqual(self.state()["state"], "EXPLORED")
        self.flow("record-redteam", "--model", "antigravity/gemini-4-neon-xhigh", "--summary", "full")
        self.assertEqual(self.state()["state"], "FALSIFIED")
        self.flow("align", "--slices", "a")
        self.reject("record-prereview", "--reviewer-a-model", REVIEWER, "--reviewer-b-model", REVIEWER_B,
                    "--planned-worker-models", WORKER, "--blockers", "1", contains="blocker")
        self.reject("record-prereview", "--reviewer-a-model", "claude-sonnet-5-5", "--reviewer-b-model", REVIEWER_B,
                    "--planned-worker-models", WORKER, "--blockers", "0", contains="HARD GATE")
        self.reject("isolate", "--slice", "a", "--branch", "feat/a", contains="EXECUTION_READY")
        self.flow("record-prereview", "--reviewer-a-model", REVIEWER, "--reviewer-b-model", REVIEWER_B,
                  "--planned-worker-models", WORKER, "--blockers", "0")

    def test_redteam_same_single_family_rejected(self) -> None:
        self.flow("init", "--repo", str(self.repo))
        self.flow("triage", "--symptom", "s", "--root", "r", "--gear", "2")
        self.flow("record-explore", "--author-models", "claude/opus", "--summary", "e")
        self.reject("record-redteam", "--model", "antigravity/claude-opus-5-5-high", "--summary", "x", contains="heterogeneous")
        os.environ["MOCK_PASEO_PROVIDERS"] = json.dumps({"claude": ["opus"], "codex": ["gpt-6.1-sol"]})
        self.reject("record-redteam", "--model", "claude/sonnet", "--summary", "x", "--single-family-host",
                    contains="REJECTED")
        os.environ["MOCK_PASEO_PROVIDERS"] = json.dumps({"claude": ["opus", "sonnet"]})
        self.flow("record-redteam", "--model", "claude/sonnet", "--summary", "x", "--single-family-host")
        self.assertEqual(self.state()["state"], "FALSIFIED")

    def test_probe_is_evidence_only(self) -> None:
        self.flow("init", "--repo", str(self.repo))
        self.flow("triage", "--symptom", "s", "--root", "r", "--gear", "2")
        self.reject("isolate", "--slice", "p1", "--branch", "probe/p1", "--kind", "probe")
        self.flow("record-explore", "--author-models", REVIEWER_B, "--summary", "e")
        self.reject("isolate", "--slice", "p1", "--branch", "spike/p1", "--kind", "spike")
        self.flow("isolate", "--slice", "p1", "--branch", "probe/p1", "--kind", "probe")
        self.flow("assign-worker", "--slice", "p1", "--model", WORKER)
        self.commit(self.wt("p1"), "probe.txt", "measurement\n")
        self.reject("enter-review", "--slice", "p1", "--reviewer-model", REVIEWER, "--lens", "A")
        self.flow("enter-review", "--slice", "p1", "--reviewer-model", REVIEWER, "--lens", "audit")
        self.flow("record-review", "--slice", "p1", "--verdict", "PASS", "--blockers", "0", "--lens", "audit")
        self.assertEqual(self.slice("p1")["state"], "SPIKE_AUDITED")
        self.reject("integrate", "--slice", "p1", contains="never be merged")
        self.flow("discard-slice", "--slice", "p1", "--reason", "evidence captured")
        self.assertEqual(self.git(self.repo, "branch", "--list", "probe/p1"), "")

    def test_user_override_only_bypasses_routing(self) -> None:
        self.flow("init", "--repo", str(self.repo))
        self.flow("triage", "--symptom", "s", "--root", "r", "--gear", "2")
        self.reject("isolate", "--slice", "a", "--branch", "feat/a")
        self.reject("isolate", "--slice", "a", "--branch", "feat/a", "--user-override", "   ")
        self.flow("isolate", "--slice", "a", "--branch", "feat/a", "--user-override", "user said run directly")
        st = self.state()
        self.assertEqual((st["state"], st["aligned_slices"]), ("EXECUTION_READY", ["a"]))
        self.assertEqual(st["overrides"][0]["reason"], "user said run directly")
        self.flow("assign-worker", "--slice", "a", "--model", WORKER)
        self.commit(self.wt("a"), "app.py", "x\n")
        self.reject("enter-review", "--slice", "a", "--reviewer-model", "claude/sonnet", "--lens", "A",
                    "--user-override", "please")
        self.reject("enter-review", "--slice", "a", "--reviewer-model", "claude/sonnet", "--lens", "A")
        self.reject("integrate", "--slice", "a", "--user-override", "please")

    def test_dirty_main_requires_into_worktree_and_cherry_picks(self) -> None:
        (self.repo / "README.md").write_text("user wip\n")
        (self.repo / "local.cfg").write_text("secret=1\n")
        self.gear1_ready()
        self.assertFalse(self.state()["main_initially_clean"])
        self.flow("isolate", "--slice", "main-fix", "--branch", "fix/answer", "--apply-dirty-patch")
        sl = self.slice("main-fix")
        wt = Path(sl["worktree"])
        self.assertTrue(sl["has_dirty_patch"])
        self.assertNotEqual(sl["slice_base"], sl["base_sha"])
        self.assertEqual((wt / "local.cfg").read_text(), "secret=1\n")
        self.assertEqual((wt / "README.md").read_text(), "user wip\n")
        self.flow("assign-worker", "--slice", "main-fix", "--model", WORKER)
        self.commit(wt, "app.py", "def answer():\n    return 42\n", "fix")
        self.flow("enter-review", "--slice", "main-fix", "--reviewer-model", REVIEWER)
        self.flow("record-review", "--slice", "main-fix", "--verdict", "PASS", "--blockers", "0")
        self.reject("integrate", "--slice", "main-fix", contains="--into-worktree")
        integ = self.tmp / "integration"
        self.git(self.repo, "worktree", "add", "-q", "--detach", str(integ), self.state()["expected_main_head_sha"])
        self.flow("integrate", "--slice", "main-fix", "--into-worktree", str(integ))
        self.assertIn("42", (integ / "app.py").read_text())
        self.assertFalse((integ / "local.cfg").exists())
        self.assertEqual((integ / "README.md").read_text(), "demo\n")
        self.assertEqual((self.repo / "README.md").read_text(), "user wip\n")
        self.assertIn("41", (self.repo / "app.py").read_text())
        self.assertEqual(self.state()["state"], "MERGED_PENDING_VERIFY")
        self.flow("verify-integration", "--cmd", "grep -q 42 app.py")
        self.assertEqual(self.state()["state"], "COMPLETED")
        self.assertFalse(wt.exists())


class GearThreeFlowTest(FlowTestBase):
    def spike_audited(self, tag):
        self.run_dir = self.tmp / f"run-{tag}"
        self.flow("init", "--repo", str(self.repo))
        self.flow("triage", "--symptom", "unknown perf ceiling", "--root", "unknown", "--gear", "3")
        self.flow("record-explore", "--author-models", WORKER, "--summary", "recon")
        self.flow("record-redteam", "--model", REVIEWER_B, "--summary", "premortem")
        self.reject("align", "--slices", "s1")
        self.flow("align", "--slices", "s1", "--spike-hypothesis", "cache helps", "--spike-samples", "3 runs",
                  "--go-criteria", ">20% faster")
        self.reject("isolate", "--slice", "s1", "--branch", f"spike/{tag}", "--kind", "production")
        self.flow("isolate", "--slice", "s1", "--branch", f"spike/{tag}", "--kind", "spike")
        self.flow("assign-worker", "--slice", "s1", "--model", WORKER)
        self.commit(self.wt("s1"), "bench.txt", "numbers\n")
        self.flow("enter-review", "--slice", "s1", "--reviewer-model", REVIEWER_B, "--lens", "audit")
        self.flow("record-review", "--slice", "s1", "--verdict", "PASS", "--blockers", "0", "--lens", "audit")
        self.assertEqual(self.slice("s1")["state"], "SPIKE_AUDITED")
        self.reject("integrate", "--slice", "s1", contains="never be merged")

    def test_spike_go(self) -> None:
        self.spike_audited("go")
        wt = self.wt("s1")
        self.flow("decide-spike", "--slice", "s1", "--decision", "go", "--summary", "win", "--slices", "prod")
        st = self.state()
        self.assertEqual((st["gear"], st["state"], st["aligned_slices"]), (2, "ALIGNED", ["prod"]))
        self.assertFalse(wt.exists())
        self.assertEqual(self.git(self.repo, "branch", "--list", "spike/go"), "")
        self.reject("isolate", "--slice", "prod", "--branch", "feat/prod")
        self.flow("record-prereview", "--reviewer-a-model", REVIEWER, "--reviewer-b-model", REVIEWER_B,
                  "--planned-worker-models", WORKER, "--blockers", "0")
        self.flow("isolate", "--slice", "prod", "--branch", "feat/prod")

    def test_spike_go_default_slices_and_realign_in_aligned(self) -> None:
        self.spike_audited("godefault")
        self.flow("decide-spike", "--slice", "s1", "--decision", "go", "--summary", "win")
        st = self.state()
        self.assertEqual((st["gear"], st["state"], st["aligned_slices"]), (2, "ALIGNED", ["s1-prod"]))
        self.flow("align", "--slices", "api,db", "--summary", "split production work")
        st = self.state()
        self.assertEqual((st["state"], st["aligned_slices"]), ("ALIGNED", ["api", "db"]))
        self.flow("record-prereview", "--reviewer-a-model", REVIEWER, "--reviewer-b-model", REVIEWER_B,
                  "--planned-worker-models", WORKER, "--blockers", "0")
        self.reject("isolate", "--slice", "s1-prod", "--branch", "feat/old")
        self.flow("isolate", "--slice", "api", "--branch", "feat/api")

    def test_spike_pivot(self) -> None:
        self.spike_audited("pivot")
        self.flow("decide-spike", "--slice", "s1", "--decision", "pivot", "--summary", "try other")
        self.assertEqual(self.state()["state"], "PREMORTEM_DONE")
        self.assertEqual(self.git(self.repo, "branch", "--list", "spike/pivot"), "")

    def test_spike_kill(self) -> None:
        self.spike_audited("kill")
        self.flow("decide-spike", "--slice", "s1", "--decision", "kill", "--summary", "dead end")
        self.assertEqual(self.state()["state"], "DISCARDED")
        self.assertEqual(self.git(self.repo, "branch", "--list", "spike/kill"), "")


class PostReviewHardeningTest(FlowTestBase):
    """Regression suite for the cross-model post-review blockers on the first gatekeeper commit."""

    def test_every_mutating_command_rechecks_main_snapshot(self) -> None:
        (self.repo / "notes.txt").write_text("a")
        self.flow("init", "--repo", str(self.repo))
        before = self.ledger_snapshot()
        (self.repo / "notes.txt").write_text("ab")
        self.reject("triage", "--symptom", "s", "--root", "r", "--gear", "2", contains="working tree changed")
        self.assertEqual(self.ledger_snapshot(), before)
        (self.repo / "notes.txt").write_text("a")
        self.flow("triage", "--symptom", "s", "--root", "r", "--gear", "2")
        before = self.ledger_snapshot()
        (self.repo / "notes.txt").write_text("ab")
        self.reject("record-explore", "--author-models", WORKER, "--summary", "e", contains="working tree changed")
        self.assertEqual(self.ledger_snapshot(), before)
        self.assertEqual(self.state()["state"], "TRIAGED")
        (self.repo / "notes.txt").write_text("a")
        self.commit(self.repo, "rogue.txt", "rogue\n", "rogue")
        before = self.ledger_snapshot()
        self.reject("record-explore", "--author-models", WORKER, "--summary", "e", contains="HEAD drifted")
        self.reject("triage", "--symptom", "s", "--root", "r", "--gear", "1", "--re-triage", contains="HEAD drifted")
        self.assertEqual(self.ledger_snapshot(), before)
        self.flow("status")

    def test_gear2_worker_family_bound_to_prereview_credentials(self) -> None:
        self.gear2_ready(slices="a")
        self.assertEqual(self.state()["prereview_reviewer_families"], ["google", "openai"])
        self.flow("isolate", "--slice", "a", "--branch", "feat/a")
        for model in (REVIEWER, "codex/gpt-6.2-astra", REVIEWER_B, "gemini-4-carbon-high"):
            self.reject("assign-worker", "--slice", "a", "--model", model, contains="pre-reviewer families")
        self.reject("assign-worker", "--slice", "a", "--model", "gpt-6.1-sol", "--provider", "codex")
        self.assertEqual(self.slice("a")["state"], "ISOLATED")
        self.flow("assign-worker", "--slice", "a", "--model", WORKER)
        self.reject("assign-worker", "--slice", "a", "--model", REVIEWER, contains="pre-reviewer families")
        self.assertEqual(self.slice("a")["worker_family"], "anthropic")
        self.flow("triage", "--symptom", "s", "--root", "r", "--gear", "2", "--re-triage")
        st = self.state()
        for key in ("prereview", "prereview_reviewer_families", "prereview_single_family"):
            self.assertNotIn(key, st)

    def test_prereview_single_family_exemption_is_verified(self) -> None:
        self.flow("init", "--repo", str(self.repo))
        self.flow("triage", "--symptom", "s", "--root", "r", "--gear", "2")
        self.flow("align", "--slices", "a", "--user-override", "user said run directly")
        self.flow("align", "--slices", "a,b")
        args = ("record-prereview", "--reviewer-a-model", "claude/sonnet", "--reviewer-b-model", "claude-haiku-5",
                "--planned-worker-models", WORKER, "--blockers", "0")
        self.reject(*args, contains="HARD GATE")
        os.environ["MOCK_PASEO_PROVIDERS"] = json.dumps({"claude": ["opus"], "codex": ["gpt-6.1-sol"]})
        self.reject(*args, "--single-family-host", contains="REJECTED")
        os.environ["MOCK_PASEO_PROVIDERS"] = json.dumps({"claude": ["opus", "sonnet", "haiku"]})
        self.flow(*args, "--single-family-host")
        st = self.state()
        self.assertEqual((st["prereview_reviewer_families"], st["prereview_single_family"]), (["anthropic"], True))
        self.flow("isolate", "--slice", "a", "--branch", "feat/a")
        self.flow("assign-worker", "--slice", "a", "--model", WORKER)

    def _dirty_main_integrated_into_worktree(self):
        (self.repo / "README.md").write_text("user wip\n")
        (self.repo / "local.cfg").write_text("secret=1\n")
        self.gear1_ready()
        self.flow("isolate", "--slice", "main-fix", "--branch", "fix/answer", "--apply-dirty-patch")
        self.flow("assign-worker", "--slice", "main-fix", "--model", WORKER)
        self.commit(self.wt("main-fix"), "app.py", "def answer():\n    return 42\n", "fix")
        self.flow("enter-review", "--slice", "main-fix", "--reviewer-model", REVIEWER)
        self.flow("record-review", "--slice", "main-fix", "--verdict", "PASS", "--blockers", "0")
        integ = self.tmp / "integration"
        self.git(self.repo, "worktree", "add", "-q", "--detach", str(integ), self.state()["expected_main_head_sha"])
        self.flow("integrate", "--slice", "main-fix", "--into-worktree", str(integ))
        self.assertEqual(self.state()["state"], "MERGED_PENDING_VERIFY")
        return integ

    def test_verify_integration_into_worktree_integrity_before_and_after_cmd(self) -> None:
        integ = self._dirty_main_integrated_into_worktree()
        wt = self.wt("main-fix")

        def assert_pending():
            self.assertEqual(self.state()["state"], "MERGED_PENDING_VERIFY")
            self.assertTrue(wt.exists())
            self.assertNotEqual(self.git(self.repo, "branch", "--list", "fix/answer"), "")

        (integ / "junk.txt").write_text("x")
        before = self.ledger_snapshot()
        self.reject("verify-integration", "--cmd", "exit 0", contains="untracked")
        self.assertEqual(self.ledger_snapshot(), before)
        (integ / "junk.txt").unlink()
        (integ / "app.py").write_text("tampered\n")
        self.reject("verify-integration", "--cmd", "exit 0", contains="before --cmd")
        self.git(integ, "checkout", "--", "app.py")
        (self.repo / "local.cfg").write_text("secret=2\n")
        self.reject("verify-integration", "--cmd", "exit 0", contains="working tree changed")
        (self.repo / "local.cfg").write_text("secret=1\n")
        assert_pending()
        self.flow("verify-integration", "--cmd", "touch leftover.txt", expect=flow.EXIT_VERIFY_FAILED)
        assert_pending()
        self.assertIn("after --cmd", self.state()["verifications"][-1]["integrity_failure"])
        (integ / "leftover.txt").unlink()
        self.flow("verify-integration", "--cmd", "echo more >> app.py", expect=flow.EXIT_VERIFY_FAILED)
        assert_pending()
        self.git(integ, "checkout", "--", "app.py")
        self.flow("verify-integration", "--cmd", "grep -q 42 app.py")
        self.assertEqual(self.state()["state"], "COMPLETED")
        self.assertFalse(wt.exists())

    def test_verify_integration_in_place_rejects_cmd_that_dirties_repo(self) -> None:
        self.gear1_ready()
        self.implement("main-fix", "fix/answer")
        self.flow("enter-review", "--slice", "main-fix", "--reviewer-model", REVIEWER)
        self.flow("record-review", "--slice", "main-fix", "--verdict", "PASS", "--blockers", "0")
        self.flow("integrate", "--slice", "main-fix")
        wt = self.wt("main-fix")
        self.flow("verify-integration", "--cmd", "echo x >> README.md", expect=flow.EXIT_VERIFY_FAILED)
        self.assertEqual(self.state()["state"], "MERGED_PENDING_VERIFY")
        self.assertTrue(wt.exists())
        self.git(self.repo, "checkout", "--", "README.md")
        self.flow("verify-integration", "--cmd", "touch build.log", expect=flow.EXIT_VERIFY_FAILED)
        self.assertEqual(self.state()["state"], "MERGED_PENDING_VERIFY")
        self.assertTrue(wt.exists())
        (self.repo / "build.log").unlink()
        self.flow("verify-integration", "--cmd", "grep -q 42 app.py")
        self.assertEqual(self.state()["state"], "COMPLETED")
        self.assertFalse(wt.exists())

    def test_mark_rebased_tracks_latest_target_head(self) -> None:
        self.gear2_ready(slices="a,b,c")
        self.implement("a", "feat/a", content="def answer():\n    return 42\n")
        self.implement("b", "feat/b", content="def answer():\n    return 43\n")
        self.implement("c", "feat/c", rel="c.txt", content="independent\n")
        for sid in ("a", "b", "c"):
            self.pass_gear2(sid)
        self.flow("integrate", "--slice", "a")
        head_a = self.git(self.repo, "rev-parse", "HEAD")
        self.flow("integrate", "--slice", "b", expect=flow.EXIT_CONFLICT)
        self.assertEqual(self.slice("b")["required_rebase_target"], head_a)
        self.flow("integrate", "--slice", "c")
        head_c = self.git(self.repo, "rev-parse", "HEAD")
        self.assertNotEqual(head_a, head_c)
        self.assertEqual(self.state()["expected_main_head_sha"], head_c)
        wtb = self.wt("b")
        self.git(wtb, "reset", "-q", "--hard", head_c)
        self.commit(wtb, "b.txt", "b rebased\n", "rebased b")
        self.reject("mark-rebased", "--slice", "b", "--new-slice-base", head_a, contains="rebase target")
        self.flow("mark-rebased", "--slice", "b", "--new-slice-base", head_c)
        self.pass_gear2("b")
        self.flow("integrate", "--slice", "b")
        self.assertEqual(self.state()["state"], "MERGED_PENDING_VERIFY")
        self.flow("verify-integration", "--cmd", "test -f b.txt && test -f c.txt && grep -q 42 app.py")
        self.assertEqual(self.state()["state"], "COMPLETED")

    def test_user_override_ledger_cannot_bypass_physical_gates(self) -> None:
        self.flow("init", "--repo", str(self.repo))
        self.flow("triage", "--symptom", "s", "--root", "r", "--gear", "2")
        self.flow("isolate", "--slice", "a", "--branch", "feat/a", "--user-override", "user said run directly")
        self.flow("assign-worker", "--slice", "a", "--model", WORKER)
        self.commit(self.wt("a"), "app.py", "def answer():\n    return 42\n")

        def blocked(*args, contains=None):
            before = self.ledger_snapshot()
            sl = self.slice("a")
            self.reject(*args, contains=contains)
            after = self.slice("a")
            self.assertEqual(self.ledger_snapshot(), before)
            self.assertEqual((after["state"], after["approved_head_sha"]), (sl["state"], sl["approved_head_sha"]))

        for parser_reject in (("enter-review", "--slice", "a", "--reviewer-model", REVIEWER, "--lens", "A",
                               "--user-override", "please"),
                              ("integrate", "--slice", "a", "--user-override", "please")):
            blocked(*parser_reject)
        blocked("enter-review", "--slice", "a", "--reviewer-model", "claude/sonnet", "--lens", "A", contains="HARD GATE #2")
        blocked("enter-review", "--slice", "a", "--reviewer-model", "antigravity/claude-opus-5-5-high", "--lens", "B",
                contains="HARD GATE #2")
        blocked("integrate", "--slice", "a", contains="HARD GATE #5")
        self.flow("enter-review", "--slice", "a", "--reviewer-model", REVIEWER, "--lens", "A")
        self.flow("record-review", "--slice", "a", "--verdict", "PASS", "--blockers", "0", "--lens", "A")
        blocked("integrate", "--slice", "a", contains="HARD GATE #5")
        self.assertIsNone(self.slice("a")["approved_head_sha"])

        self.run_dir = self.tmp / "run-spike"
        self.flow("init", "--repo", str(self.repo))
        self.flow("triage", "--symptom", "s", "--root", "r", "--gear", "3")
        self.flow("record-explore", "--author-models", WORKER, "--summary", "recon")
        self.flow("align", "--slices", "a", "--spike-hypothesis", "h", "--spike-samples", "s", "--go-criteria", "g",
                  "--user-override", "skip premortem per user")
        self.flow("isolate", "--slice", "a", "--branch", "spike/a", "--kind", "spike")
        self.flow("assign-worker", "--slice", "a", "--model", WORKER)
        self.commit(self.wt("a"), "bench.txt", "numbers\n")
        blocked("enter-review", "--slice", "a", "--reviewer-model", "claude/sonnet", "--lens", "audit",
                contains="HARD GATE #2")
        self.flow("enter-review", "--slice", "a", "--reviewer-model", REVIEWER, "--lens", "audit")
        self.flow("record-review", "--slice", "a", "--verdict", "PASS", "--blockers", "0", "--lens", "audit")
        blocked("integrate", "--slice", "a", contains="never be merged")
        blocked("integrate", "--slice", "a", "--user-override", "merge it anyway")
        self.assertEqual(self.slice("a")["state"], "SPIKE_AUDITED")
        self.assertNotEqual(self.git(self.repo, "branch", "--list", "spike/a"), "")


@unittest.skipIf(os.name == "nt", "POSIX permissions")
class CliSmokeTest(unittest.TestCase):
    def test_flow_scripts_are_executable_identical_and_runnable(self) -> None:
        self.assertEqual(FLOW_PATH.read_bytes(), FLOW_ZH_PATH.read_bytes())
        for path in (FLOW_PATH, FLOW_ZH_PATH):
            self.assertTrue(path.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3\n"))
            # Source-tree permissions depend on the cloner's umask (0775/0755/0700...): assert the
            # executable bit and the committed git index mode instead of an exact st_mode.
            self.assertTrue(os.access(str(path), os.X_OK), f"{path} is not executable")
            in_git = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "--is-inside-work-tree"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if in_git.returncode == 0:
                rel = str(path.relative_to(REPO_ROOT))
                entry = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files", "-s", "--", rel],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip()
                self.assertTrue(entry.startswith("100755 "), f"git index mode for {rel}: {entry!r}")
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        res = subprocess.run([sys.executable, str(FLOW_PATH), "--help"], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=env)
        self.assertEqual(res.returncode, 0, res.stderr.decode())
        self.assertIn(b"verify-integration", res.stdout)
        with tempfile.TemporaryDirectory() as tmp:
            res = subprocess.run([sys.executable, str(FLOW_PATH), "--run-dir", tmp, "status"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            self.assertEqual(res.returncode, 2)
            self.assertIn(b"init", res.stderr)


if __name__ == "__main__":
    unittest.main()
