#!/usr/bin/env python3
"""Gatekeeper state machine for the paseo-engineering skill.

Zero external dependencies (Python 3.8+ standard library only).

Usage:
    python3 <skill-dir>/scripts/flow.py [--run-dir DIR | --task-id ID [--paseo-home DIR]] <subcommand> [args]

The ledger lives in ``<run_dir>/state.json`` and ``<run_dir>/status.md`` (both mode 0600).
Default ``run_dir`` is ``${PASEO_HOME:-~/.paseo}/runs/<task-id>``.

Physical safety gates enforced here can never be bypassed by ``--user-override``:
  (a) cross-model-family review, (b) a clean, committed ``approved_head_sha`` with zero open
  blockers before merge, (c) ``spike``/``probe`` slices are never mergeable, and
  (d) conflict-free merges only (conflicts abort cleanly and send the slice to ``NEEDS_REBASE``).
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

try:  # POSIX advisory locking; silently unavailable on Windows.
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore

SCHEMA_VERSION = 1
ROUND_CAP = 2
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
LENSES = ("default", "A", "B", "audit")
KINDS = ("production", "spike", "probe")
WORK_STATES = ("ISOLATED", "IMPLEMENTING", "CHANGES_REQUESTED")
TERMINAL_SLICE_STATES = ("INTEGRATED", "DISCARDED", "SPIKE_CLOSED")
EXIT_GATE = 2
EXIT_CONFLICT = 3
EXIT_VERIFY_FAILED = 4

DAEMON_DOWN_RE = re.compile(
    r"econnrefused|not running|could not connect|cannot connect|couldn't connect|unable to connect|"
    r"failed to connect|connection refused|no daemon|daemon (?:is )?(?:not|unavailable|offline|down)|"
    r"is the daemon running",
    re.IGNORECASE,
)

# Providers that only ever serve a single model family. Multi-family routers (e.g. antigravity,
# opencode, copilot) are deliberately absent so distinct models are never grouped by router name.
SINGLE_FAMILY_PROVIDERS = {
    "claude": "anthropic",
    "anthropic": "anthropic",
    "codex": "openai",
    "openai": "openai",
    "gemini": "google",
    "google": "google",
    "deepseek": "deepseek",
    "qwen": "qwen",
}


class FlowError(Exception):
    """A rejected transition. ``save`` persists ledger mutations made before the failure."""

    def __init__(self, message: str, code: int = EXIT_GATE, save: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.save = save


class PaseoUnavailable(FlowError):
    """Paseo CLI missing or daemon not reachable (the only condition allowing auto fallback)."""


class Ctx:
    def __init__(self, run_dir: Path, paseo_home: Optional[str], online_models_json: Optional[str]) -> None:
        self.run_dir = run_dir
        self.paseo_home = paseo_home
        self.online_models_json = online_models_json


# --------------------------------------------------------------------------------------------
# Generic helpers
# --------------------------------------------------------------------------------------------


def now_iso() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def decode(data: bytes) -> str:
    return data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data)


def non_empty(value: Optional[str], name: str) -> str:
    text = (value or "").strip()
    if not text:
        raise FlowError(f"{name} must be a non-empty value")
    return text


def parse_csv(value: Optional[str]) -> List[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def validate_id(value: str, what: str = "slice id") -> str:
    text = (value or "").strip()
    if not ID_RE.match(text):
        raise FlowError(f"invalid {what} {value!r}: use [A-Za-z0-9._-], max 64 chars")
    return text


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_env() -> Dict[str, str]:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    return env


def git_raw(repo: Any, *args: str, input_bytes: Optional[bytes] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo)] + list(args),
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_git_env(),
    )


def git_bytes(repo: Any, *args: str) -> bytes:
    res = git_raw(repo, *args)
    if res.returncode != 0:
        raise FlowError(f"git {' '.join(args)} failed in {repo}: {decode(res.stderr).strip()}")
    return res.stdout


def git_out(repo: Any, *args: str) -> str:
    return decode(git_bytes(repo, *args)).strip()


def git_ok(repo: Any, *args: str) -> bool:
    return git_raw(repo, *args).returncode == 0


def identity_args(repo: Any) -> List[str]:
    res = git_raw(repo, "config", "user.email")
    if res.returncode == 0 and decode(res.stdout).strip():
        return []
    return ["-c", "user.name=Paseo Gatekeeper", "-c", "user.email=gatekeeper@localhost"]


def git_common_dir(path: Any) -> Path:
    raw = git_out(path, "rev-parse", "--git-common-dir")
    p = Path(raw)
    if not p.is_absolute():
        p = Path(path) / p
    return p.resolve()


def branch_exists(repo: Any, branch: str) -> bool:
    return git_ok(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}")


def list_branches(repo: Any) -> List[str]:
    out = git_out(repo, "for-each-ref", "--format=%(refname)", "refs/heads")
    return [line[len("refs/heads/"):] for line in out.splitlines() if line.startswith("refs/heads/")]


def is_ancestor(repo: Any, ancestor: str, descendant: str) -> bool:
    return git_ok(repo, "merge-base", "--is-ancestor", ancestor, descendant)


def wt_is_clean(wt: Any) -> bool:
    return git_out(wt, "status", "--porcelain") == ""


def diff_sha(wt: Any, base: str, tip: str) -> str:
    return sha256_bytes(git_bytes(wt, "diff", "--binary", "--no-ext-diff", "--no-color", f"{base}..{tip}"))


# --------------------------------------------------------------------------------------------
# Core helper rules
# --------------------------------------------------------------------------------------------


def compute_repo_snapshot(repo_root: Any) -> Dict[str, Any]:
    """Return ``{head_sha, is_clean, diff_hash}`` covering tracked AND untracked content."""
    repo = Path(repo_root)
    head = git_out(repo, "rev-parse", "--verify", "HEAD")
    status = git_bytes(repo, "status", "--porcelain=v1", "-z", "-uall")
    diff = git_bytes(repo, "diff", "--binary", "--no-ext-diff", "--no-color", "HEAD")
    others = git_bytes(repo, "ls-files", "--others", "--exclude-standard", "-z")
    h = hashlib.sha256()
    for label, blob in ((b"status", status), (b"diff", diff)):
        h.update(label + b"\0" + str(len(blob)).encode() + b"\0" + blob)
    rels = sorted(p for p in others.split(b"\0") if p)
    for rel in rels:
        full = repo / os.fsdecode(rel)
        try:
            st = os.lstat(str(full))
        except OSError:
            flag, digest = b"missing", sha256_bytes(b"")
        else:
            if stat.S_ISLNK(st.st_mode):
                flag, digest = b"symlink", sha256_bytes(os.fsencode(os.readlink(str(full))))
            elif stat.S_ISREG(st.st_mode):
                fh = hashlib.sha256()
                with open(str(full), "rb") as handle:
                    for chunk in iter(lambda: handle.read(1 << 20), b""):
                        fh.update(chunk)
                flag, digest = ("file:%o" % (st.st_mode & 0o777)).encode(), fh.hexdigest()
            else:
                flag, digest = b"other", sha256_bytes(b"")
        h.update(b"untracked\0" + rel + b"\0" + flag + b"\0" + digest.encode() + b"\0")
    return {"head_sha": head, "is_clean": status == b"", "diff_hash": h.hexdigest()}


def verify_main(st: Dict[str, Any]) -> Dict[str, Any]:
    snap = compute_repo_snapshot(st["repo_root"])
    if snap["head_sha"] != st["expected_main_head_sha"]:
        raise FlowError(
            "HARD GATE: main repository HEAD drifted from the ledger "
            f"(expected {st['expected_main_head_sha']}, found {snap['head_sha']}); rogue commits are not allowed"
        )
    if snap["diff_hash"] != st["main_diff_hash"]:
        raise FlowError(
            "HARD GATE: main repository working tree changed since it was recorded "
            "(tracked edits, staged changes, or untracked file content differ)"
        )
    return snap


def normalize_family(model_spec: Optional[str]) -> str:
    spec = (model_spec or "").strip().lower()
    if not spec:
        raise FlowError("model spec must be non-empty")
    if "/" in spec:
        provider, name = spec.split("/", 1)
    else:
        provider, name = "", spec
    provider, name = provider.strip(), name.strip()
    if (
        "claude" in name
        or name.startswith("claude-")
        or (provider in ("claude", "anthropic") and any(t in name for t in ("opus", "sonnet", "haiku")))
    ):
        return "anthropic"
    if name.startswith(("gpt-", "codex", "o1", "o3", "o4")) or "gpt-" in name or "codex" in name:
        return "openai"
    if "gemini" in name:
        return "google"
    if "deepseek" in name:
        return "deepseek"
    if "qwen" in name:
        return "qwen"
    if provider in SINGLE_FAMILY_PROVIDERS:
        return SINGLE_FAMILY_PROVIDERS[provider]
    head = name.split("-", 1)[0] or provider or "unknown"
    return f"other:{head}"


# --------------------------------------------------------------------------------------------
# Paseo CLI integration
# --------------------------------------------------------------------------------------------


def find_paseo_bin() -> Optional[str]:
    env_bin = os.environ.get("PASEO_BIN", "").strip()
    if env_bin:
        p = Path(env_bin).expanduser()
        return str(p) if p.is_file() and os.access(str(p), os.X_OK) else None
    found = shutil.which("paseo")
    if found:
        return found
    cand = Path.home() / ".local" / "bin" / "paseo"
    if cand.is_file() and os.access(str(cand), os.X_OK):
        return str(cand)
    return None


def run_paseo(ctx: Ctx, argv: List[str]) -> str:
    binary = find_paseo_bin()
    if not binary:
        raise PaseoUnavailable("paseo CLI not found (PASEO_BIN / PATH / ~/.local/bin/paseo)")
    cmd = [binary]
    env = dict(os.environ)
    if ctx.paseo_home:
        cmd += ["--home", str(ctx.paseo_home)]
        env.pop("PASEO_HOST", None)
    cmd += argv
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    except OSError as exc:
        raise PaseoUnavailable(f"cannot execute paseo CLI: {exc}")
    out, err = decode(res.stdout), decode(res.stderr)
    if res.returncode != 0:
        msg = (err.strip() or out.strip() or f"exit {res.returncode}")
        if DAEMON_DOWN_RE.search(msg):
            raise PaseoUnavailable(f"paseo daemon unavailable: {msg}")
        raise FlowError(f"paseo {' '.join(argv)} failed (exit {res.returncode}): {msg}")
    return out


def parse_json_output(text: str) -> Any:
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except ValueError:
        pass
    for idx, ch in enumerate(stripped):
        if ch in "[{":
            try:
                return json.loads(stripped[idx:])
            except ValueError:
                continue
    raise FlowError(f"could not parse JSON from paseo output: {stripped[:200]!r}")


def pick_field(obj: Any, *keys: str) -> Optional[str]:
    if isinstance(obj, list) and len(obj) == 1:
        obj = obj[0]
    if not isinstance(obj, dict):
        return None
    for key in keys:
        val = obj.get(key)
        if isinstance(val, (str, int)) and str(val):
            return str(val)
    for nest in ("workspace", "project", "data", "result"):
        if isinstance(obj.get(nest), dict):
            found = pick_field(obj[nest], *keys)
            if found:
                return found
    return None


def _flatten_models(data: Any) -> List[str]:
    specs: List[str] = []
    if isinstance(data, dict):
        for provider, models in data.items():
            for m in models if isinstance(models, list) else [models]:
                specs.append(f"{provider}/{m}")
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                specs.append(item)
            elif isinstance(item, dict):
                provider = item.get("provider") or ""
                model = item.get("id") or item.get("model") or ""
                specs.append(f"{provider}/{model}" if provider else str(model))
    return [s for s in specs if s.strip()]


def online_model_specs(ctx: Ctx) -> List[str]:
    if ctx.online_models_json:
        return _flatten_models(json.loads(Path(ctx.online_models_json).read_text(encoding="utf-8")))
    providers = parse_json_output(run_paseo(ctx, ["provider", "ls", "--json"]))
    specs: List[str] = []
    for item in providers if isinstance(providers, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("provider") or item.get("id") or "").strip()
        status = str(item.get("status", "")).lower()
        enabled = str(item.get("enabled", "enabled")).lower()
        if not name or status != "available" or enabled in ("disabled", "false"):
            continue
        models = parse_json_output(run_paseo(ctx, ["provider", "models", name, "--json"]))
        for m in models if isinstance(models, list) else []:
            mid = m.get("id") or m.get("model") if isinstance(m, dict) else m
            if mid:
                specs.append(f"{name}/{mid}")
    return specs


def verify_single_family_host(ctx: Ctx) -> List[str]:
    try:
        specs = online_model_specs(ctx)
    except (FlowError, OSError, ValueError) as exc:
        raise FlowError(f"--single-family-host REJECTED: cannot verify online model families ({exc})")
    families = sorted({normalize_family(s) for s in specs})
    if len(families) >= 2:
        raise FlowError(
            f"--single-family-host REJECTED: {len(families)} distinct model families are online "
            f"({', '.join(families)}); use a reviewer from a different family instead"
        )
    return families


def paseo_create_worktree(ctx: Ctx, repo: Path, branch: str, base: str, background: bool) -> Tuple[str, str, Path]:
    proj = parse_json_output(run_paseo(ctx, ["project", "create", "--json", str(repo)]))
    project_id = pick_field(proj, "projectId", "id")
    if not project_id:
        raise FlowError(f"paseo project create returned no projectId: {proj!r}")
    argv = [
        "workspace", "create", "--isolation", "worktree", "--project", project_id, "--path", str(repo),
        "--mode", "branch-off", "--new-branch", branch, "--base", base,
        "--background" if background else "--no-background", "--json",
    ]
    ws = parse_json_output(run_paseo(ctx, argv))
    ws_id = pick_field(ws, "workspaceId", "id")
    cwd = pick_field(ws, "cwd", "worktreeRoot", "path")
    if not ws_id or not cwd:
        if ws_id:
            with contextlib.suppress(FlowError):
                run_paseo(ctx, ["workspace", "archive", ws_id])
        raise FlowError(f"paseo workspace create returned no workspaceId/cwd: {ws!r}")
    return project_id, ws_id, Path(cwd)


# --------------------------------------------------------------------------------------------
# Ledger I/O
# --------------------------------------------------------------------------------------------


def resolve_run_dir(args: argparse.Namespace) -> Path:
    if args.run_dir:
        return Path(args.run_dir).expanduser().resolve()
    if args.task_id:
        task_id = validate_id(args.task_id, "task id")
        if args.paseo_home:
            home = Path(args.paseo_home).expanduser()
        else:
            home = Path(os.environ.get("PASEO_HOME") or str(Path.home() / ".paseo")).expanduser()
        return (home / "runs" / task_id).resolve()
    raise FlowError("one of --run-dir or --task-id is required")


def write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(str(tmp), 0o600)
        os.replace(str(tmp), str(path))
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def load_state(run_dir: Path) -> Dict[str, Any]:
    path = run_dir / "state.json"
    if not path.is_file():
        raise FlowError(f"no gatekeeper ledger at {path}; run 'init --repo <path>' first")
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(run_dir: Path, st: Dict[str, Any]) -> None:
    st["updated_at"] = now_iso()
    write_private(run_dir / "state.json", json.dumps(st, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    write_private(run_dir / "status.md", render_status(st))


@contextlib.contextmanager
def ledger_lock(run_dir: Path) -> Iterator[None]:
    run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if fcntl is None:
        yield
        return
    fd = os.open(str(run_dir / ".lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def log_event(st: Dict[str, Any], cmd: str, detail: str) -> None:
    st.setdefault("events", []).append({"at": now_iso(), "cmd": cmd, "detail": detail})


# --------------------------------------------------------------------------------------------
# State helpers
# --------------------------------------------------------------------------------------------


def get_slice(st: Dict[str, Any], sid: str) -> Dict[str, Any]:
    sl = st.get("slices", {}).get(sid)
    if not sl:
        raise FlowError(f"unknown slice {sid!r}")
    return sl


def set_slice_state(sl: Dict[str, Any], new: str, note: str = "") -> None:
    sl["state"] = new
    sl.setdefault("history", []).append({"at": now_iso(), "state": new, "note": note})


def require_gear_state(st: Dict[str, Any], allowed: Dict[int, Tuple[str, ...]], cmd: str) -> None:
    gear = st.get("gear")
    if gear not in allowed or st["state"] not in allowed[gear]:
        legal = "; ".join(f"gear {g}: {', '.join(s)}" for g, s in allowed.items())
        raise FlowError(f"{cmd} is not legal in task state {st['state']} (gear {gear}); legal: {legal}")


def bump_epoch(st: Dict[str, Any]) -> None:
    st["alignment_epoch"] = int(st.get("alignment_epoch", 0)) + 1


def invalidate_credentials(st: Dict[str, Any], reason: str) -> None:
    for key in ("explore", "redteam", "prereview", "alignment", "spike"):
        st.pop(key, None)
    st["aligned_slices"] = []
    for sl in st.get("slices", {}).values():
        if sl["state"] not in TERMINAL_SLICE_STATES and sl["state"] != "SUPERSEDED":
            set_slice_state(sl, "SUPERSEDED", reason)
    bump_epoch(st)


def escalate_to_gear2(st: Dict[str, Any], sl: Dict[str, Any], reason: str) -> None:
    invalidate_credentials(st, f"superseded by Gear 1 -> Gear 2 escalation ({reason})")
    sl["capped"] = True
    set_slice_state(sl, "MUST_ESCALATE_GEAR2", reason)
    st["gear"] = 2
    st["state"] = "TRIAGED"


def maybe_hit_cap(st: Dict[str, Any], sl: Dict[str, Any], rounds: int, what: str) -> str:
    if rounds < ROUND_CAP:
        return ""
    if st.get("gear") == 1:
        escalate_to_gear2(st, sl, f"{rounds} {what} rounds in Gear 1")
        return "MUST_ESCALATE_GEAR2: task re-routed to Gear 2 (state TRIAGED)"
    sl["capped"] = True
    set_slice_state(sl, "ROUND_CAP_REACHED", f"{rounds} {what} rounds")
    return "ROUND_CAP_REACHED: use resolve-dispute (re-triage | discard | user-escalate)"


def cleanup_slice(ctx: Ctx, st: Dict[str, Any], sl: Dict[str, Any]) -> List[str]:
    repo = st["repo_root"]
    notes: List[str] = []
    wt = Path(sl["worktree"]) if sl.get("worktree") else None
    if sl.get("backend") == "paseo" and sl.get("workspace_id") and not sl.get("archived"):
        try:
            run_paseo(ctx, ["workspace", "archive", sl["workspace_id"]])
            sl["archived"] = True
        except FlowError as exc:
            notes.append(f"paseo workspace archive failed ({exc}); falling back to git worktree remove")
    if wt is not None and wt.exists():
        if sl.get("backend") == "paseo":
            notes.append("worktree directory still present after paseo archive; forcing git worktree remove")
        git_raw(repo, "worktree", "remove", "--force", str(wt))
    if wt is not None and wt.exists():
        raise FlowError(f"cleanup failed: worktree directory {wt} still exists")
    git_raw(repo, "worktree", "prune")
    if sl.get("branch") and branch_exists(repo, sl["branch"]):
        res = git_raw(repo, "branch", "-D", sl["branch"])
        if res.returncode != 0 or branch_exists(repo, sl["branch"]):
            raise FlowError(f"cleanup failed: could not delete branch {sl['branch']}: {decode(res.stderr).strip()}")
    sl["cleaned_at"] = now_iso()
    sl["cleanup_notes"] = notes
    return notes


# --------------------------------------------------------------------------------------------
# Subcommands
# --------------------------------------------------------------------------------------------


def resolve_init_repo(run_dir: Path, repo: str) -> Path:
    repo_in = Path(repo).expanduser().resolve()
    repo_root = Path(git_out(repo_in, "rev-parse", "--show-toplevel")).resolve()
    run_dir = run_dir.resolve()
    if run_dir == repo_root or repo_root in run_dir.parents:
        raise FlowError("run directory must live outside the repository (it would perturb the main snapshot)")
    return repo_root


def cmd_init(ctx: Ctx, args: argparse.Namespace) -> Dict[str, Any]:
    if (ctx.run_dir / "state.json").exists():
        raise FlowError(f"ledger already exists at {ctx.run_dir}; refusing to reset gates (use a new --task-id)")
    repo_root = resolve_init_repo(ctx.run_dir, args.repo)
    snap = compute_repo_snapshot(repo_root)
    st: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": now_iso(),
        "repo_root": str(repo_root),
        "paseo_home": ctx.paseo_home,
        "initial_base_sha": snap["head_sha"],
        "expected_main_head_sha": snap["head_sha"],
        "main_diff_hash": snap["diff_hash"],
        "main_initially_clean": snap["is_clean"],
        "state": "INIT",
        "gear": None,
        "aligned_slices": [],
        "alignment_epoch": 0,
        "slices": {},
        "slice_archive": [],
        "overrides": [],
        "events": [],
    }
    return st


def cmd_triage(ctx: Ctx, st: Dict[str, Any], a: argparse.Namespace) -> str:
    if st["state"] == "COMPLETED":
        raise FlowError("task already COMPLETED; start a new task id")
    if st["state"] != "INIT" and not a.re_triage:
        raise FlowError(f"triage already recorded (state {st['state']}); pass --re-triage to re-route")
    symptom = non_empty(a.symptom, "--symptom")
    root = non_empty(a.root, "--root")
    justified = (a.same_site_justified or "").strip()
    if symptom == root and not justified:
        raise FlowError("symptom site equals root site (plaster-patch risk); provide --same-site-justified <reason>")
    if st["state"] != "INIT":
        invalidate_credentials(st, "re-triage")
    else:
        bump_epoch(st)
    st["gear"] = a.gear
    st["triage"] = {
        "symptom": symptom, "root": root, "gear": a.gear, "lenses": parse_csv(a.lenses),
        "summary": (a.summary or "").strip(), "same_site_justified": justified, "at": now_iso(),
        "re_triage": bool(a.re_triage),
    }
    if a.gear == 1:
        slices = [validate_id(s) for s in parse_csv(a.slices or "main-fix")]
        if not slices:
            raise FlowError("--slices must list at least one slice id")
        st["aligned_slices"] = slices
        st["state"] = "EXECUTION_READY"
    else:
        st["aligned_slices"] = []
        st["state"] = "TRIAGED"
    return f"triaged as Gear {a.gear}; task state {st['state']}"


def cmd_record_explore(ctx: Ctx, st: Dict[str, Any], a: argparse.Namespace) -> str:
    require_gear_state(st, {2: ("TRIAGED",), 3: ("TRIAGED",)}, "record-explore")
    models = parse_csv(a.author_models)
    if not models:
        raise FlowError("--author-models must list at least one model")
    families = sorted({normalize_family(m) for m in models})
    st["explore"] = {"models": models, "families": families, "summary": non_empty(a.summary, "--summary"), "at": now_iso()}
    st["state"] = "EXPLORED" if st["gear"] == 2 else "RECON_DONE"
    return f"explore recorded (families: {', '.join(families)}); task state {st['state']}"


def cmd_record_redteam(ctx: Ctx, st: Dict[str, Any], a: argparse.Namespace) -> str:
    require_gear_state(st, {2: ("EXPLORED", "FALSIFIED"), 3: ("RECON_DONE", "PREMORTEM_DONE")}, "record-redteam")
    explore = st.get("explore")
    if not explore:
        raise FlowError("record-explore must precede record-redteam")
    summary = non_empty(a.summary, "--summary")
    model = non_empty(a.model, "--model")
    fam = normalize_family(model)
    explore_fams = set(explore["families"])
    verified = False
    if a.single_family_host:
        verify_single_family_host(ctx)
        verified = True
    if not {f for f in explore_fams if f != fam} and not verified:
        raise FlowError(
            f"HARD GATE: red-team model family {fam!r} matches every explorer family "
            f"({', '.join(sorted(explore_fams))}); red-team must be heterogeneous"
        )
    rt = st.setdefault("redteam", {"entries": []})
    rt["entries"].append({"model": model, "family": fam, "summary": summary, "single_family_host": verified, "at": now_iso()})
    entry_fams = [e["family"] for e in rt["entries"]]
    any_verified = any(e.get("single_family_host") for e in rt["entries"])
    missing = sorted(f for f in explore_fams if not any(ef != f for ef in entry_fams))
    if any_verified or not missing:
        st["state"] = "FALSIFIED" if st["gear"] == 2 else "PREMORTEM_DONE"
        return f"red-team coverage complete; task state {st['state']}"
    return f"red-team recorded; coverage still missing a heterogeneous challenger for: {', '.join(missing)}"


def cmd_align(ctx: Ctx, st: Dict[str, Any], a: argparse.Namespace) -> str:
    override = None
    if a.user_override is not None:
        override = non_empty(a.user_override, "--user-override")
    normal = {2: ("FALSIFIED",), 3: ("PREMORTEM_DONE",)}
    relaxed = {2: ("TRIAGED", "EXPLORED", "FALSIFIED"), 3: ("TRIAGED", "RECON_DONE", "PREMORTEM_DONE")}
    try:
        require_gear_state(st, normal, "align")
    except FlowError:
        if not override:
            raise
        require_gear_state(st, relaxed, "align (with --user-override)")
        st["overrides"].append({"cmd": "align", "from_state": st["state"], "reason": override, "at": now_iso()})
    slices = [validate_id(s) for s in parse_csv(a.slices)]
    if not slices:
        raise FlowError("--slices must list at least one slice id")
    if st["gear"] == 3:
        st["spike"] = {
            "hypothesis": non_empty(a.spike_hypothesis, "--spike-hypothesis"),
            "samples": non_empty(a.spike_samples, "--spike-samples"),
            "go_criteria": non_empty(a.go_criteria, "--go-criteria"),
        }
        st["state"] = "EXECUTION_READY"
    else:
        st["state"] = "ALIGNED"
    st["aligned_slices"] = slices
    st["alignment"] = {"summary": (a.summary or "").strip(), "auto_authorized": bool(a.auto_authorized), "at": now_iso()}
    st.pop("prereview", None)
    bump_epoch(st)
    return f"aligned slices {', '.join(slices)}; task state {st['state']}"


def cmd_record_prereview(ctx: Ctx, st: Dict[str, Any], a: argparse.Namespace) -> str:
    require_gear_state(st, {2: ("ALIGNED",)}, "record-prereview")
    m1 = non_empty(a.reviewer_a_model, "--reviewer-a-model")
    m2 = non_empty(a.reviewer_b_model, "--reviewer-b-model")
    planned = parse_csv(a.planned_worker_models)
    if not planned:
        raise FlowError("--planned-worker-models must list at least one model")
    if a.blockers < 0:
        raise FlowError("--blockers must be >= 0")
    if a.blockers != 0:
        raise FlowError(f"pre-review reports {a.blockers} open blocker(s); resolve them and re-run record-prereview")
    worker_fams = {normalize_family(m) for m in planned}
    clashes = [m for m in (m1, m2) if normalize_family(m) in worker_fams]
    verified = False
    if a.single_family_host:
        verify_single_family_host(ctx)
        verified = True
    if clashes and not verified:
        raise FlowError(
            f"HARD GATE: pre-reviewer(s) {', '.join(clashes)} share a model family with planned workers "
            f"({', '.join(sorted(worker_fams))})"
        )
    st["prereview"] = {
        "reviewer_a": m1, "reviewer_b": m2, "planned_workers": planned, "blockers": 0,
        "single_family_host": verified, "at": now_iso(),
    }
    st["state"] = "EXECUTION_READY"
    return "pre-review passed; task state EXECUTION_READY"


def _apply_dirty_patch(repo: Path, wt: Path) -> None:
    diff = git_bytes(repo, "diff", "--binary", "--no-ext-diff", "--no-color", "HEAD")
    if diff:
        res = git_raw(wt, "apply", "--binary", "--whitespace=nowarn", "-", input_bytes=diff)
        if res.returncode != 0:
            raise FlowError(f"failed to apply main-repo tracked changes into worktree: {decode(res.stderr).strip()}")
    others = git_bytes(repo, "ls-files", "--others", "--exclude-standard", "-z")
    for rel in sorted(p for p in others.split(b"\0") if p):
        src = repo / os.fsdecode(rel)
        dst = wt / os.fsdecode(rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_symlink():
            os.symlink(os.readlink(str(src)), str(dst))
        elif src.is_file():
            shutil.copy2(str(src), str(dst))
    git_bytes(wt, "add", "-A")
    res = git_raw(wt, *identity_args(wt), "commit", "--no-verify", "-q", "-m",
                  "gatekeeper: carry uncommitted main-repo changes (dirty patch)")
    if res.returncode != 0:
        raise FlowError(f"failed to commit dirty patch: {decode(res.stderr).strip() or decode(res.stdout).strip()}")


def _verify_new_worktree(repo: Path, wt: Path, branch: str, base: str) -> None:
    if not wt.is_dir():
        raise FlowError(f"worktree directory {wt} does not exist after creation")
    top = Path(git_out(wt, "rev-parse", "--show-toplevel")).resolve()
    if top != wt.resolve():
        raise FlowError(f"{wt} is not the top-level of a git worktree (found {top})")
    if git_common_dir(wt) != git_common_dir(repo):
        raise FlowError(f"{wt} is not a worktree of {repo}")
    actual = git_out(wt, "rev-parse", "--abbrev-ref", "HEAD")
    if actual != branch:
        raise FlowError(f"worktree is on branch {actual!r} instead of requested {branch!r} (silent rename trap)")
    head = git_out(wt, "rev-parse", "HEAD")
    if head != base:
        raise FlowError(f"worktree HEAD {head} does not match requested base {base} (base ignored)")


def _rollback_isolation(ctx: Ctx, repo: Path, ws_id: Optional[str], wt: Optional[Path], before: List[str]) -> None:
    if ws_id:
        with contextlib.suppress(FlowError):
            run_paseo(ctx, ["workspace", "archive", ws_id])
    if wt is not None and wt.exists():
        git_raw(repo, "worktree", "remove", "--force", str(wt))
    git_raw(repo, "worktree", "prune")
    for name in set(list_branches(repo)) - set(before):
        git_raw(repo, "branch", "-D", name)


def cmd_isolate(ctx: Ctx, st: Dict[str, Any], a: argparse.Namespace) -> str:
    sid = validate_id(a.slice)
    kind, gear, tstate = a.kind, st.get("gear"), st["state"]
    override = None
    if a.user_override is not None:
        override = non_empty(a.user_override, "--user-override")
    if kind == "probe":
        if not (gear == 2 and tstate in ("EXPLORED", "FALSIFIED")):
            raise FlowError("probe slices are only allowed in Gear 2 EXPLORED or FALSIFIED")
    elif kind == "spike":
        if not (gear == 3 and tstate == "EXECUTION_READY"):
            raise FlowError("spike slices are only allowed in Gear 3 EXECUTION_READY")
        if sid not in st["aligned_slices"]:
            raise FlowError(f"slice {sid!r} is not in aligned_slices {st['aligned_slices']}")
    else:
        if gear not in (1, 2):
            raise FlowError("production slices are only allowed in Gear 1 or Gear 2")
        if tstate == "EXECUTION_READY" and sid in st["aligned_slices"]:
            pass
        elif override and (tstate == "EXECUTION_READY" or (gear == 2 and tstate in ("TRIAGED", "EXPLORED", "FALSIFIED", "ALIGNED"))):
            st["overrides"].append({"cmd": "isolate", "slice": sid, "from_state": tstate, "reason": override, "at": now_iso()})
        elif tstate != "EXECUTION_READY":
            raise FlowError(f"production slices require task state EXECUTION_READY (current {tstate})")
        else:
            raise FlowError(f"slice {sid!r} is not in aligned_slices {st['aligned_slices']}")

    prev = st["slices"].get(sid)
    inherited = (0, 0)
    if prev:
        if prev["state"] != "DISCARDED":
            raise FlowError(f"slice {sid!r} already exists in state {prev['state']}; discard-slice it first")
        if prev.get("epoch") == st.get("alignment_epoch"):
            if prev.get("capped"):
                raise FlowError(
                    f"slice {sid!r} hit its round cap/escalation in this alignment epoch; "
                    "re-triage or re-align before re-isolating (round caps cannot be reset by discard)"
                )
            inherited = (int(prev.get("review_rounds", 0)), int(prev.get("verify_fail_rounds", 0)))

    branch = non_empty(a.branch, "--branch")
    if not git_ok(st["repo_root"], "check-ref-format", "--branch", branch):
        raise FlowError(f"invalid branch name {branch!r}")
    snap = verify_main(st)
    repo = Path(st["repo_root"])
    if branch_exists(repo, branch):
        raise FlowError(
            f"branch refs/heads/{branch} already exists; refusing (Paseo would silently rename the branch "
            "or ignore --base). Choose a fresh branch name"
        )
    base = st["expected_main_head_sha"]
    if not SHA_RE.match(base):
        raise FlowError(f"expected_main_head_sha {base!r} is not a 40-hex SHA")

    before = list_branches(repo)
    used = a.backend
    notes: List[str] = []
    ws_id: Optional[str] = None
    proj_id: Optional[str] = None
    wt: Optional[Path] = None
    try:
        if a.backend in ("paseo", "auto"):
            try:
                proj_id, ws_id, wt = paseo_create_worktree(ctx, repo, branch, base, a.background)
                used = "paseo"
            except PaseoUnavailable as exc:
                if a.backend == "paseo":
                    raise FlowError(f"--backend paseo failed hard: {exc}")
                notes.append(f"auto backend fell back to git worktree: {exc}")
                used = "git"
        if used == "git":
            wt = Path(a.worktree_dir).expanduser() if a.worktree_dir else ctx.run_dir / "worktrees" / sid
            wt = wt.resolve()
            if wt.exists() and (not wt.is_dir() or any(wt.iterdir())):
                raise FlowError(f"worktree directory {wt} already exists and is not empty")
            wt.parent.mkdir(parents=True, exist_ok=True)
            res = git_raw(repo, "worktree", "add", "-b", branch, str(wt), base)
            if res.returncode != 0:
                raise FlowError(f"git worktree add failed: {decode(res.stderr).strip()}")
        assert wt is not None
        wt = wt.resolve()
        _verify_new_worktree(repo, wt, branch, base)
        slice_base, dirty_sha, has_dirty = base, None, False
        if a.apply_dirty_patch and not snap["is_clean"]:
            _apply_dirty_patch(repo, wt)
            slice_base = git_out(wt, "rev-parse", "HEAD")
            dirty_sha = diff_sha(wt, base, slice_base)
            has_dirty = True
        elif a.apply_dirty_patch:
            notes.append("--apply-dirty-patch ignored: main repository is clean")
    except FlowError:
        _rollback_isolation(ctx, repo, ws_id, wt, before)
        raise

    if prev:
        st["slice_archive"].append(prev)
    sl: Dict[str, Any] = {
        "id": sid, "kind": kind, "branch": branch, "backend": used, "worktree": str(wt),
        "workspace_id": ws_id, "project_id": proj_id, "base_sha": base, "slice_base": slice_base,
        "has_dirty_patch": has_dirty, "dirty_patch_sha": dirty_sha, "epoch": st.get("alignment_epoch"),
        "state": "ISOLATED", "worker_model": None, "worker_family": None, "worker_agent_id": None,
        "author_families": [], "review_rounds": inherited[0], "verify_fail_rounds": inherited[1],
        "wt_head_sha": None, "last_rejected_wt_head_sha": None, "approved_head_sha": None,
        "open_blockers": 0, "active_lenses": {}, "lens_passes": {}, "reviews": [], "verify_failures": [],
        "capped": False, "created_at": now_iso(), "notes": notes, "history": [],
    }
    set_slice_state(sl, "ISOLATED", f"backend={used}")
    st["slices"][sid] = sl
    if kind == "production" and sid not in st["aligned_slices"]:
        st["aligned_slices"].append(sid)
    if kind == "production" and override and st["state"] != "EXECUTION_READY":
        notes.append(f"user override skipped checkpoints from {st['state']}")
        st["state"] = "EXECUTION_READY"
    extra = f" ({'; '.join(notes)})" if notes else ""
    return f"slice {sid} isolated via {used} at {wt} on {branch} (base {slice_base[:12]}){extra}"


def cmd_assign_worker(ctx: Ctx, st: Dict[str, Any], a: argparse.Namespace) -> str:
    sl = get_slice(st, validate_id(a.slice))
    if sl["state"] not in WORK_STATES:
        raise FlowError(
            f"assign-worker is only legal in {'/'.join(WORK_STATES)} (slice is {sl['state']}); "
            "round caps and escalations cannot be reset by re-assigning"
        )
    model = non_empty(a.model, "--model")
    provider = (a.provider or "").strip()
    full = f"{provider}/{model}" if provider and "/" not in model else model
    fam = normalize_family(full)
    sl["worker_model"] = full
    sl["worker_family"] = fam
    sl["worker_agent_id"] = a.agent_id
    if fam not in sl["author_families"]:
        sl["author_families"].append(fam)
    if sl["state"] == "ISOLATED":
        set_slice_state(sl, "IMPLEMENTING", f"worker {full}")
    return f"worker {full} (family {fam}) assigned to {sl['id']}; slice state {sl['state']}"


def cmd_record_verify_fail(ctx: Ctx, st: Dict[str, Any], a: argparse.Namespace) -> str:
    sl = get_slice(st, validate_id(a.slice))
    if sl["state"] not in ("IMPLEMENTING", "CHANGES_REQUESTED"):
        raise FlowError(f"record-verify-fail requires IMPLEMENTING or CHANGES_REQUESTED (slice is {sl['state']})")
    summary = non_empty(a.summary, "--summary")
    sl["verify_fail_rounds"] = int(sl.get("verify_fail_rounds", 0)) + 1
    sl["verify_failures"].append({"summary": summary, "at": now_iso()})
    msg = maybe_hit_cap(st, sl, sl["verify_fail_rounds"], "build/test failure")
    return f"verify failure #{sl['verify_fail_rounds']} recorded for {sl['id']}" + (f"; {msg}" if msg else "")


def _allowed_lenses(st: Dict[str, Any], sl: Dict[str, Any]) -> Tuple[str, ...]:
    if sl["kind"] in ("spike", "probe"):
        return ("audit", "default")
    return ("A", "B") if st.get("gear") == 2 else ("default",)


def cmd_enter_review(ctx: Ctx, st: Dict[str, Any], a: argparse.Namespace) -> str:
    sl = get_slice(st, validate_id(a.slice))
    lens = a.lens
    allowed = _allowed_lenses(st, sl)
    if lens not in allowed:
        raise FlowError(f"lens {lens!r} not allowed for this slice (allowed: {', '.join(allowed)})")
    if sl["state"] in ("IMPLEMENTING", "CHANGES_REQUESTED"):
        fresh = True
    elif (
        sl["state"] == "IN_REVIEW" and sl["kind"] == "production" and st.get("gear") == 2
        and lens not in sl["active_lenses"] and lens not in sl["lens_passes"]
    ):
        fresh = False
    else:
        raise FlowError(f"enter-review is not legal for slice state {sl['state']} with lens {lens}")
    if not sl.get("worker_family"):
        raise FlowError("assign-worker must be recorded before review")
    reviewer = non_empty(a.reviewer_model, "--reviewer-model")
    rev_fam = normalize_family(reviewer)
    verified = False
    if a.single_family_host:
        verify_single_family_host(ctx)
        verified = True
    if rev_fam in sl["author_families"] and not verified:
        raise FlowError(
            f"HARD GATE #2: reviewer family {rev_fam!r} equals a worker family of this slice "
            f"({', '.join(sl['author_families'])}); cross-family review is mandatory"
        )
    verify_main(st)
    wt = Path(sl["worktree"])
    if not wt.is_dir():
        raise FlowError(f"slice worktree {wt} is missing")
    if not wt_is_clean(wt):
        raise FlowError("HARD GATE #3: slice worktree has uncommitted changes; commit before review")
    if git_out(wt, "rev-parse", "--abbrev-ref", "HEAD") != sl["branch"]:
        raise FlowError(f"HARD GATE #3: slice worktree is not on branch {sl['branch']}")
    if not is_ancestor(wt, sl["slice_base"], "HEAD"):
        raise FlowError("HARD GATE #3: slice_base is not an ancestor of HEAD (history rewritten; use mark-rebased)")
    count = int(git_out(wt, "rev-list", "--count", f"{sl['slice_base']}..HEAD"))
    if count <= 0:
        raise FlowError("HARD GATE #3: no commits on top of slice_base; nothing to review")
    head = git_out(wt, "rev-parse", "HEAD")
    if head == sl.get("last_rejected_wt_head_sha"):
        raise FlowError("HARD GATE #3: HEAD equals the last rejected commit; zero-fix re-submission is blocked")
    if not fresh and head != sl.get("wt_head_sha"):
        raise FlowError("second lens must review the same wt_head_sha as the first lens")
    if fresh:
        sl["active_lenses"] = {}
        sl["lens_passes"] = {}
    sl["wt_head_sha"] = head
    sl["active_lenses"][lens] = {
        "reviewer_model": reviewer, "family": rev_fam, "agent_id": a.reviewer_agent_id,
        "wt_head_sha": head, "single_family_host": verified, "at": now_iso(),
    }
    if sl["state"] != "IN_REVIEW":
        set_slice_state(sl, "IN_REVIEW", f"lens {lens} by {reviewer}")
    return f"slice {sl['id']} IN_REVIEW (lens {lens}, reviewer family {rev_fam}, head {head[:12]})"


def cmd_record_review(ctx: Ctx, st: Dict[str, Any], a: argparse.Namespace) -> str:
    sl = get_slice(st, validate_id(a.slice))
    lens = a.lens
    if sl["state"] != "IN_REVIEW":
        raise FlowError(f"record-review requires IN_REVIEW (slice is {sl['state']})")
    if lens not in sl["active_lenses"]:
        raise FlowError(f"no active review for lens {lens!r} (active: {', '.join(sl['active_lenses']) or 'none'})")
    verify_main(st)
    wt = Path(sl["worktree"])
    if git_out(wt, "rev-parse", "HEAD") != sl["wt_head_sha"]:
        raise FlowError("HARD GATE: slice HEAD moved during review; the review no longer applies")
    if not wt_is_clean(wt):
        raise FlowError("HARD GATE: slice worktree has uncommitted changes during review")
    if a.blockers < 0:
        raise FlowError("--blockers must be >= 0")
    entry = {
        "lens": lens, "verdict": a.verdict, "blockers": a.blockers, "wt_head_sha": sl["wt_head_sha"],
        "reviewer": sl["active_lenses"][lens], "counterexample": (a.counterexample or "").strip(),
        "summary": (a.summary or "").strip(), "at": now_iso(),
    }
    if a.verdict == "BLOCKING":
        if a.blockers < 1:
            raise FlowError("BLOCKING verdict requires --blockers >= 1")
        if not entry["counterexample"]:
            raise FlowError("BLOCKING verdict requires a non-empty --counterexample")
        sl["reviews"].append(entry)
        sl["last_rejected_wt_head_sha"] = sl["wt_head_sha"]
        sl["lens_passes"] = {}
        sl["active_lenses"] = {}
        sl["open_blockers"] = a.blockers
        sl["review_rounds"] = int(sl.get("review_rounds", 0)) + 1
        msg = maybe_hit_cap(st, sl, sl["review_rounds"], "blocking review")
        if not msg:
            set_slice_state(sl, "CHANGES_REQUESTED", f"lens {lens} BLOCKING")
            msg = "CHANGES_REQUESTED"
        return f"review round {sl['review_rounds']} BLOCKING for {sl['id']}: {msg}"
    if a.blockers != 0:
        raise FlowError("PASS verdict requires --blockers 0")
    sl["reviews"].append(entry)
    sl["active_lenses"].pop(lens, None)
    sl["lens_passes"][lens] = sl["wt_head_sha"]
    head = sl["wt_head_sha"]
    if sl["kind"] in ("spike", "probe"):
        sl["active_lenses"] = {}
        set_slice_state(sl, "SPIKE_AUDITED", f"lens {lens} PASS")
        return f"{sl['kind']} {sl['id']} audited (evidence only, never mergeable)"
    if st.get("gear") == 2:
        if sl["lens_passes"].get("A") == head and sl["lens_passes"].get("B") == head:
            sl["approved_head_sha"] = head
            sl["open_blockers"] = 0
            sl["active_lenses"] = {}
            set_slice_state(sl, "REVIEW_PASSED", "lenses A+B PASS")
            return f"slice {sl['id']} REVIEW_PASSED (A+B) approved_head_sha={head}"
        waiting = [x for x in ("A", "B") if sl["lens_passes"].get(x) != head]
        return f"lens {lens} PASS recorded; still awaiting lens {', '.join(waiting)} on {head[:12]}"
    sl["approved_head_sha"] = head
    sl["open_blockers"] = 0
    sl["active_lenses"] = {}
    set_slice_state(sl, "REVIEW_PASSED", f"lens {lens} PASS")
    return f"slice {sl['id']} REVIEW_PASSED approved_head_sha={head}"


def cmd_resolve_dispute(ctx: Ctx, st: Dict[str, Any], a: argparse.Namespace) -> str:
    sl = get_slice(st, validate_id(a.slice))
    if sl["state"] != "ROUND_CAP_REACHED":
        raise FlowError(f"resolve-dispute requires ROUND_CAP_REACHED (slice is {sl['state']})")
    reason = non_empty(a.reason, "--reason")
    sl.setdefault("disputes", []).append({"action": a.action, "reason": reason, "at": now_iso()})
    if a.action == "re-triage":
        invalidate_credentials(st, f"dispute re-triage: {reason}")
        st["state"] = "TRIAGED"
        return f"slice {sl['id']} SUPERSEDED; task returned to TRIAGED (discard superseded slices)"
    if a.action == "discard":
        cleanup_slice(ctx, st, sl)
        set_slice_state(sl, "DISCARDED", reason)
        return f"slice {sl['id']} DISCARDED (worktree and branch removed)"
    set_slice_state(sl, "AWAITING_USER_RULING", reason)
    return f"slice {sl['id']} AWAITING_USER_RULING (user may: triage --re-triage | discard-slice | reset-rounds)"


def cmd_reset_rounds(ctx: Ctx, st: Dict[str, Any], a: argparse.Namespace) -> str:
    sl = get_slice(st, validate_id(a.slice))
    if sl["state"] != "AWAITING_USER_RULING":
        raise FlowError(f"reset-rounds requires AWAITING_USER_RULING (slice is {sl['state']})")
    reason = non_empty(a.reason, "--reason")
    sl["review_rounds"] = min(int(sl.get("review_rounds", 0)), ROUND_CAP - 1)
    sl["verify_fail_rounds"] = min(int(sl.get("verify_fail_rounds", 0)), ROUND_CAP - 1)
    sl["capped"] = False
    sl.setdefault("user_rulings", []).append({"reason": reason, "at": now_iso()})
    set_slice_state(sl, "CHANGES_REQUESTED", f"user ruling: {reason}")
    return f"slice {sl['id']} granted one more round (CHANGES_REQUESTED); a fresh fix + enter-review + PASS is required"


def _abort_and_restore(target: Path, target_head: str, op: str) -> None:
    res = git_raw(target, op, "--abort")
    if res.returncode != 0:
        git_raw(target, "reset", "--merge")
    if git_out(target, "rev-parse", "HEAD") != target_head or not wt_is_clean(target):
        raise FlowError(f"CRITICAL: could not restore {target} to {target_head} after aborted {op}", code=EXIT_CONFLICT, save=True)


def cmd_integrate(ctx: Ctx, st: Dict[str, Any], a: argparse.Namespace) -> str:
    sl = get_slice(st, validate_id(a.slice))
    if sl["kind"] != "production":
        raise FlowError(f"HARD GATE #5: {sl['kind']} slices are evidence-only and can never be merged")
    if sl["state"] != "REVIEW_PASSED" or int(sl.get("open_blockers", 0)) != 0 or not sl.get("approved_head_sha"):
        raise FlowError(f"HARD GATE #5: slice must be REVIEW_PASSED with 0 open blockers (state {sl['state']})")
    if st["state"] != "EXECUTION_READY":
        raise FlowError(f"integrate requires task state EXECUTION_READY (current {st['state']})")
    approved = sl["approved_head_sha"]
    snap = verify_main(st)
    repo = Path(st["repo_root"])
    wt = Path(sl["worktree"])
    if not wt.is_dir() or not wt_is_clean(wt):
        raise FlowError("HARD GATE #5: slice worktree missing or dirty")
    if git_out(wt, "rev-parse", "HEAD") != approved:
        raise FlowError("HARD GATE #5: slice HEAD differs from approved_head_sha (unreviewed commits)")
    if git_out(repo, "rev-parse", f"refs/heads/{sl['branch']}") != approved:
        raise FlowError("HARD GATE #5: branch ref differs from approved_head_sha (unreviewed commits)")

    if a.into_worktree:
        target = Path(a.into_worktree).expanduser().resolve()
        if not target.is_dir():
            raise FlowError(f"--into-worktree {target} does not exist")
        if target == repo:
            raise FlowError("--into-worktree must be a separate clean worktree, not the main repository")
        if any(Path(s["worktree"]).resolve() == target for s in st["slices"].values() if s.get("worktree")):
            raise FlowError("--into-worktree must not be a slice worktree")
        if git_common_dir(target) != git_common_dir(repo):
            raise FlowError(f"--into-worktree {target} is not a worktree of {repo}")
        if not wt_is_clean(target):
            raise FlowError(f"--into-worktree {target} is not clean")
        prev_target = st.get("integration_target")
        if prev_target and prev_target != str(target):
            raise FlowError(f"integration target already fixed to {prev_target}")
        expected = st.get("integration_head_sha") or st["expected_main_head_sha"]
        if git_out(target, "rev-parse", "HEAD") != expected:
            raise FlowError(f"--into-worktree HEAD must equal {expected}")
        in_place = False
    else:
        if sl.get("has_dirty_patch") or not snap["is_clean"]:
            raise FlowError(
                "main repository has uncommitted user changes; refusing in-place merge. "
                "Pass --into-worktree <clean_wt_path>"
            )
        prev_target = st.get("integration_target")
        if prev_target and prev_target != str(repo):
            raise FlowError(f"integration target already fixed to {prev_target}; pass --into-worktree")
        target = repo
        in_place = True

    target_head = git_out(target, "rev-parse", "HEAD")
    ident = identity_args(target)
    if not sl.get("has_dirty_patch"):
        if is_ancestor(target, target_head, approved):
            res = git_raw(target, "merge", "--ff-only", approved)
            if res.returncode != 0:
                raise FlowError(f"fast-forward merge failed: {decode(res.stderr).strip()}")
            how = "fast-forward"
        else:
            res = git_raw(target, *ident, "merge", "--no-commit", "--no-ff", approved)
            if res.returncode != 0:
                _abort_and_restore(target, target_head, "merge")
                sl["required_rebase_target"] = target_head
                set_slice_state(sl, "NEEDS_REBASE", f"merge conflict onto {target_head[:12]}")
                raise FlowError(
                    f"merge conflict: aborted cleanly; slice {sl['id']} -> NEEDS_REBASE onto {target_head}",
                    code=EXIT_CONFLICT, save=True,
                )
            res = git_raw(target, *ident, "commit", "--no-verify", "-q", "-m",
                          f"Merge gatekeeper slice {sl['id']} ({sl['branch']}) at {approved[:12]}")
            if res.returncode != 0:
                _abort_and_restore(target, target_head, "merge")
                raise FlowError(f"merge commit failed: {decode(res.stderr).strip() or decode(res.stdout).strip()}")
            how = "merge"
    else:
        res = git_raw(target, *ident, "cherry-pick", f"{sl['slice_base']}..{approved}")
        if res.returncode != 0:
            _abort_and_restore(target, target_head, "cherry-pick")
            sl["required_rebase_target"] = target_head
            set_slice_state(sl, "NEEDS_REBASE", f"cherry-pick conflict onto {target_head[:12]}")
            raise FlowError(
                f"cherry-pick conflict: aborted cleanly; slice {sl['id']} -> NEEDS_REBASE onto {target_head}",
                code=EXIT_CONFLICT, save=True,
            )
        how = "cherry-pick"

    new_head = git_out(target, "rev-parse", "HEAD")
    if in_place:
        after = compute_repo_snapshot(repo)
        st["expected_main_head_sha"] = after["head_sha"]
        st["main_diff_hash"] = after["diff_hash"]
    else:
        st["integration_head_sha"] = new_head
    st["integration_target"] = str(target)
    sl["integrated_sha"] = new_head
    set_slice_state(sl, "INTEGRATED", f"{how} into {target}")
    if st["aligned_slices"] and all(st["slices"].get(i, {}).get("state") == "INTEGRATED" for i in st["aligned_slices"]):
        st["state"] = "MERGED_PENDING_VERIFY"
    return f"slice {sl['id']} INTEGRATED via {how} (target HEAD {new_head[:12]}); task state {st['state']}"


def cmd_mark_rebased(ctx: Ctx, st: Dict[str, Any], a: argparse.Namespace) -> str:
    sl = get_slice(st, validate_id(a.slice))
    if sl["state"] != "NEEDS_REBASE":
        raise FlowError(f"mark-rebased requires NEEDS_REBASE (slice is {sl['state']})")
    verify_main(st)
    wt = Path(sl["worktree"])
    target = sl.get("required_rebase_target") or st["expected_main_head_sha"]
    res = git_raw(wt, "rev-parse", "--verify", f"{a.new_slice_base}^{{commit}}")
    if res.returncode != 0:
        raise FlowError(f"unknown commit {a.new_slice_base!r}")
    new_base = decode(res.stdout).strip()
    if not sl.get("has_dirty_patch"):
        if new_base != target:
            raise FlowError(f"--new-slice-base must equal the rebase target {target}")
        if not is_ancestor(wt, new_base, "HEAD"):
            raise FlowError("new slice base is not an ancestor of the slice HEAD; rebase first")
    else:
        parent = git_out(wt, "rev-parse", f"{new_base}^")
        if parent != target:
            raise FlowError(f"dirty-patch base parent must equal the rebase target {target}")
        if diff_sha(wt, target, new_base) != sl.get("dirty_patch_sha"):
            raise FlowError("dirty-patch base content differs from the recorded dirty patch (hidden edits blocked)")
        if not is_ancestor(wt, new_base, "HEAD"):
            raise FlowError("new slice base is not an ancestor of the slice HEAD; rebase first")
    sl["slice_base"] = new_base
    sl["approved_head_sha"] = None
    sl["lens_passes"] = {}
    sl["active_lenses"] = {}
    sl["wt_head_sha"] = None
    set_slice_state(sl, "IMPLEMENTING", f"rebased onto {new_base[:12]}")
    return f"slice {sl['id']} rebased onto {new_base[:12]}; full cross-family review required again"


def cmd_verify_integration(ctx: Ctx, st: Dict[str, Any], a: argparse.Namespace) -> str:
    if st["state"] != "MERGED_PENDING_VERIFY":
        raise FlowError(f"verify-integration requires MERGED_PENDING_VERIFY (current {st['state']})")
    cmd = non_empty(a.cmd, "--cmd")
    target = st.get("integration_target") or st["repo_root"]
    if target == st["repo_root"]:
        verify_main(st)
    elif git_out(target, "rev-parse", "HEAD") != st.get("integration_head_sha"):
        raise FlowError("integration worktree HEAD drifted from the ledger")
    res = subprocess.run(cmd, shell=True, cwd=target, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = decode(res.stdout)
    if output:
        print(output[-4000:], end="" if output.endswith("\n") else "\n")
    st.setdefault("verifications", []).append({"cmd": cmd, "exit_code": res.returncode, "at": now_iso()})
    if res.returncode != 0:
        raise FlowError(f"verification command exited {res.returncode}; task stays MERGED_PENDING_VERIFY",
                        code=EXIT_VERIFY_FAILED, save=True)
    cleaned = []
    for sl in st["slices"].values():
        if sl["state"] == "INTEGRATED" and not sl.get("cleaned_at"):
            cleanup_slice(ctx, st, sl)
            cleaned.append(sl["id"])
    st["state"] = "COMPLETED"
    leftovers = [s["id"] for s in st["slices"].values() if not s.get("cleaned_at") and s["state"] != "DISCARDED"]
    tail = f"; WARNING uncleaned slices remain: {', '.join(leftovers)} (discard-slice them)" if leftovers else ""
    return f"verification passed; cleaned {', '.join(cleaned) or 'nothing'}; task COMPLETED{tail}"


def cmd_decide_spike(ctx: Ctx, st: Dict[str, Any], a: argparse.Namespace) -> str:
    sl = get_slice(st, validate_id(a.slice))
    if sl["kind"] != "spike" or sl["state"] != "SPIKE_AUDITED":
        raise FlowError(f"decide-spike requires a SPIKE_AUDITED spike slice (kind {sl['kind']}, state {sl['state']})")
    if st.get("gear") != 3 or st["state"] != "EXECUTION_READY":
        raise FlowError(f"decide-spike requires Gear 3 EXECUTION_READY (current gear {st.get('gear')} {st['state']})")
    summary = non_empty(a.summary, "--summary")
    others = [s["id"] for s in st["slices"].values()
              if s is not sl and s["state"] not in TERMINAL_SLICE_STATES]
    if others:
        raise FlowError(f"decide or discard other active slices first: {', '.join(others)}")
    new_slices: List[str] = []
    if a.decision == "go":
        new_slices = [validate_id(s) for s in parse_csv(a.slices)]
        if not new_slices:
            raise FlowError("decision 'go' requires --slices <csv> naming the fresh production slices")
    cleanup_slice(ctx, st, sl)
    sl["spike_decision"] = {"decision": a.decision, "summary": summary, "at": now_iso()}
    set_slice_state(sl, "SPIKE_CLOSED", a.decision)
    st.setdefault("spike", {})["decision"] = a.decision
    if a.decision == "go":
        st["gear"] = 2
        st["state"] = "ALIGNED"
        st["aligned_slices"] = new_slices
        st.pop("prereview", None)
        bump_epoch(st)
    elif a.decision == "pivot":
        st["state"] = "PREMORTEM_DONE"
        st["aligned_slices"] = []
    else:
        st["state"] = "DISCARDED"
        st["aligned_slices"] = []
    return f"spike {sl['id']} closed ({a.decision}); task gear {st['gear']} state {st['state']}"


def cmd_discard_slice(ctx: Ctx, st: Dict[str, Any], a: argparse.Namespace) -> str:
    sl = get_slice(st, validate_id(a.slice))
    if sl["state"] in TERMINAL_SLICE_STATES:
        raise FlowError(f"slice {sl['id']} is already {sl['state']}")
    reason = non_empty(a.reason, "--reason")
    cleanup_slice(ctx, st, sl)
    sl["discard_reason"] = reason
    set_slice_state(sl, "DISCARDED", reason)
    return f"slice {sl['id']} DISCARDED (worktree and branch removed)"


# --------------------------------------------------------------------------------------------
# Status rendering
# --------------------------------------------------------------------------------------------


def next_commands(st: Dict[str, Any]) -> List[str]:
    s, gear = st["state"], st.get("gear")
    task_next = {
        "INIT": ["triage --symptom <site> --root <site> --gear <1|2|3>"],
        "TRIAGED": ["record-explore --author-models <csv> --summary <text>"],
        "EXPLORED": ["record-redteam --model <m> --summary <text>", "isolate --kind probe ..."],
        "FALSIFIED": ["align --slices <csv>", "record-redteam --model <m> --summary <text>", "isolate --kind probe ..."],
        "RECON_DONE": ["record-redteam --model <m> --summary <text>"],
        "PREMORTEM_DONE": ["align --slices <csv> --spike-hypothesis <h> --spike-samples <s> --go-criteria <g>"],
        "ALIGNED": ["record-prereview --reviewer-a-model <m1> --reviewer-b-model <m2> --planned-worker-models <csv> --blockers 0"],
        "MERGED_PENDING_VERIFY": ["verify-integration --cmd <shell_cmd>"],
    }
    out = list(task_next.get(s, []))
    if s == "EXECUTION_READY":
        kind = "spike" if gear == 3 else "production"
        for sid in st.get("aligned_slices", []):
            sl = st["slices"].get(sid)
            if not sl or sl["state"] == "DISCARDED":
                out.append(f"isolate --slice {sid} --branch <branch> --kind {kind}")
    if s not in ("INIT", "COMPLETED"):
        out.append("triage --re-triage ...")
    per_state = {
        "ISOLATED": ["assign-worker"],
        "IMPLEMENTING": ["enter-review", "record-verify-fail", "assign-worker"],
        "CHANGES_REQUESTED": ["enter-review", "record-verify-fail", "assign-worker"],
        "IN_REVIEW": ["record-review", "enter-review (second lens)"],
        "REVIEW_PASSED": ["integrate"],
        "NEEDS_REBASE": ["mark-rebased"],
        "ROUND_CAP_REACHED": ["resolve-dispute"],
        "AWAITING_USER_RULING": ["reset-rounds", "discard-slice"],
        "SPIKE_AUDITED": ["decide-spike", "discard-slice"],
        "SUPERSEDED": ["discard-slice"],
        "MUST_ESCALATE_GEAR2": ["discard-slice"],
    }
    for sid, sl in sorted(st.get("slices", {}).items()):
        for c in per_state.get(sl["state"], []):
            if sl["kind"] == "probe" and c == "decide-spike":
                continue
            out.append(f"{c} --slice {sid}")
    return out


def status_payload(st: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "state": st["state"],
        "gear": st.get("gear"),
        "repo_root": st["repo_root"],
        "expected_main_head_sha": st["expected_main_head_sha"],
        "aligned_slices": st.get("aligned_slices", []),
        "slices": {
            sid: {k: sl.get(k) for k in ("kind", "state", "branch", "worktree", "backend", "review_rounds",
                                         "verify_fail_rounds", "approved_head_sha")}
            for sid, sl in st.get("slices", {}).items()
        },
        "next": next_commands(st),
    }


def render_status(st: Dict[str, Any]) -> str:
    lines = [
        "# Gatekeeper status",
        "",
        f"- Task state: **{st['state']}** (gear {st.get('gear')})",
        f"- Repository: `{st['repo_root']}`",
        f"- Expected main HEAD: `{st['expected_main_head_sha']}`",
        f"- Aligned slices: {', '.join(st.get('aligned_slices', [])) or '-'}",
        f"- Updated: {st.get('updated_at', '-')}",
        "",
        "## Slices",
        "",
        "| id | kind | state | branch | review/verify rounds | worktree |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for sid, sl in sorted(st.get("slices", {}).items()):
        lines.append(
            f"| {sid} | {sl['kind']} | {sl['state']} | `{sl['branch']}` | "
            f"{sl.get('review_rounds', 0)}/{sl.get('verify_fail_rounds', 0)} | `{sl.get('worktree')}` |"
        )
    lines += ["", "## Next legal commands", ""]
    lines += [f"- `{c}`" for c in next_commands(st)] or ["- (none)"]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="flow.py", description="paseo-engineering gatekeeper state machine")
    p.add_argument("--run-dir", help="ledger directory")
    p.add_argument("--task-id", help="task id (ledger at ${PASEO_HOME:-~/.paseo}/runs/<task-id>)")
    p.add_argument("--paseo-home", help="Paseo home; passed as --home to every paseo CLI call")
    p.add_argument("--online-models-json", help="offline list of online models (testing/air-gapped hosts)")
    sub = p.add_subparsers(dest="command")
    sub.required = True

    s = sub.add_parser("init")
    s.add_argument("--repo", required=True)

    s = sub.add_parser("triage")
    s.add_argument("--symptom", required=True)
    s.add_argument("--root", required=True)
    s.add_argument("--gear", type=int, choices=(1, 2, 3), required=True)
    s.add_argument("--lenses")
    s.add_argument("--slices")
    s.add_argument("--summary")
    s.add_argument("--same-site-justified")
    s.add_argument("--re-triage", action="store_true")

    s = sub.add_parser("record-explore")
    s.add_argument("--author-models", required=True)
    s.add_argument("--summary", required=True)

    s = sub.add_parser("record-redteam")
    s.add_argument("--model", required=True)
    s.add_argument("--summary", required=True)
    s.add_argument("--single-family-host", action="store_true")

    s = sub.add_parser("align")
    s.add_argument("--slices", required=True)
    s.add_argument("--summary")
    s.add_argument("--auto-authorized", action="store_true")
    s.add_argument("--spike-hypothesis")
    s.add_argument("--spike-samples")
    s.add_argument("--go-criteria")
    s.add_argument("--user-override", help="non-empty reason; may only bypass routing/checkpoint order")

    s = sub.add_parser("record-prereview")
    s.add_argument("--reviewer-a-model", required=True)
    s.add_argument("--reviewer-b-model", required=True)
    s.add_argument("--planned-worker-models", required=True)
    s.add_argument("--blockers", type=int, required=True)
    s.add_argument("--single-family-host", action="store_true")

    s = sub.add_parser("isolate")
    s.add_argument("--slice", required=True)
    s.add_argument("--branch", required=True)
    s.add_argument("--kind", choices=KINDS, default="production")
    s.add_argument("--backend", choices=("auto", "paseo", "git"), default="auto")
    s.add_argument("--worktree-dir")
    bg = s.add_mutually_exclusive_group()
    bg.add_argument("--background", dest="background", action="store_true")
    bg.add_argument("--no-background", dest="background", action="store_false")
    s.set_defaults(background=False)
    s.add_argument("--apply-dirty-patch", action="store_true")
    s.add_argument("--user-override", help="non-empty reason; may only bypass routing/checkpoint order")

    s = sub.add_parser("assign-worker")
    s.add_argument("--slice", required=True)
    s.add_argument("--model", required=True)
    s.add_argument("--agent-id")
    s.add_argument("--provider")

    s = sub.add_parser("record-verify-fail")
    s.add_argument("--slice", required=True)
    s.add_argument("--summary", required=True)

    s = sub.add_parser("enter-review")
    s.add_argument("--slice", required=True)
    s.add_argument("--reviewer-model", required=True)
    s.add_argument("--lens", choices=LENSES, default="default")
    s.add_argument("--reviewer-agent-id")
    s.add_argument("--single-family-host", action="store_true")

    s = sub.add_parser("record-review")
    s.add_argument("--slice", required=True)
    s.add_argument("--verdict", choices=("PASS", "BLOCKING"), required=True)
    s.add_argument("--blockers", type=int, required=True)
    s.add_argument("--lens", choices=LENSES, default="default")
    s.add_argument("--counterexample")
    s.add_argument("--summary")

    s = sub.add_parser("resolve-dispute")
    s.add_argument("--slice", required=True)
    s.add_argument("--action", choices=("re-triage", "discard", "user-escalate"), required=True)
    s.add_argument("--reason", required=True)

    s = sub.add_parser("reset-rounds")
    s.add_argument("--slice", required=True)
    s.add_argument("--reason", required=True)

    s = sub.add_parser("integrate")
    s.add_argument("--slice", required=True)
    s.add_argument("--into-worktree")

    s = sub.add_parser("mark-rebased")
    s.add_argument("--slice", required=True)
    s.add_argument("--new-slice-base", required=True)

    s = sub.add_parser("verify-integration")
    s.add_argument("--cmd", required=True)

    s = sub.add_parser("decide-spike")
    s.add_argument("--slice", required=True)
    s.add_argument("--decision", choices=("go", "pivot", "kill"), required=True)
    s.add_argument("--summary", required=True)
    s.add_argument("--slices", help="fresh production slice ids (required for go)")

    s = sub.add_parser("discard-slice")
    s.add_argument("--slice", required=True)
    s.add_argument("--reason", required=True)

    s = sub.add_parser("status")
    s.add_argument("--json", action="store_true")
    return p


HANDLERS = {
    "triage": cmd_triage,
    "record-explore": cmd_record_explore,
    "record-redteam": cmd_record_redteam,
    "align": cmd_align,
    "record-prereview": cmd_record_prereview,
    "isolate": cmd_isolate,
    "assign-worker": cmd_assign_worker,
    "record-verify-fail": cmd_record_verify_fail,
    "enter-review": cmd_enter_review,
    "record-review": cmd_record_review,
    "resolve-dispute": cmd_resolve_dispute,
    "reset-rounds": cmd_reset_rounds,
    "integrate": cmd_integrate,
    "mark-rebased": cmd_mark_rebased,
    "verify-integration": cmd_verify_integration,
    "decide-spike": cmd_decide_spike,
    "discard-slice": cmd_discard_slice,
}


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run_dir = resolve_run_dir(args)
        ctx = Ctx(run_dir, args.paseo_home, args.online_models_json)
        if args.command == "init":
            resolve_init_repo(run_dir, args.repo)  # validate before creating anything on disk
        with ledger_lock(run_dir):
            if args.command == "init":
                st = cmd_init(ctx, args)
                log_event(st, "init", f"repo={st['repo_root']} head={st['expected_main_head_sha']}")
                save_state(run_dir, st)
                print(f"[flow] OK: ledger initialised at {run_dir} (head {st['expected_main_head_sha'][:12]}, "
                      f"clean={st['main_initially_clean']})")
                return 0
            st = load_state(run_dir)
            if not ctx.paseo_home:
                ctx.paseo_home = st.get("paseo_home")
            if args.command == "status":
                if args.json:
                    print(json.dumps(status_payload(st), indent=2, ensure_ascii=False))
                else:
                    print(render_status(st), end="")
                return 0
            try:
                msg = HANDLERS[args.command](ctx, st, args)
            except FlowError as exc:
                if exc.save:
                    log_event(st, args.command, f"FAILED: {exc}")
                    save_state(run_dir, st)
                raise
            log_event(st, args.command, msg)
            save_state(run_dir, st)
            print(f"[flow] OK: {msg}")
            return 0
    except FlowError as exc:
        print(f"[flow] REJECTED: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
