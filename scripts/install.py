#!/usr/bin/env python3
"""Cross-platform non-destructive installer for the paseo-engineering skill & Paseo profiles."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_NAME = "paseo-engineering"
REPO_ROOT = Path(__file__).resolve().parent.parent
BLOCK_START = "<!-- paseo-engineering:start -->"
BLOCK_END = "<!-- paseo-engineering:end -->"
BLOCK_RE = re.compile(
    re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END),
    re.DOTALL,
)


IGNORE_BUILD_ARTIFACTS = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")


def make_scripts_executable(dst: Path) -> None:
    """Ensure installed helper scripts (scripts/*.py) are executable on POSIX hosts."""
    if os.name == "nt":
        return
    scripts_dir = dst / "scripts"
    if not scripts_dir.is_dir():
        return
    for script in scripts_dir.glob("*.py"):
        if script.is_file() and not script.is_symlink():
            script.chmod(0o755)


def copy_skill_tree(src: Path, dst: Path, dry_run: bool) -> None:
    if src.resolve() == dst.resolve():
        print(f"Skill already at canonical path {dst}; skipping self-copy.")
        return
    if dry_run:
        print(f"[dry-run] Copy skill {src} -> {dst}")
        return
    if dst.is_symlink() or dst.is_file():
        dst.unlink()
    elif dst.is_dir():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, ignore=IGNORE_BUILD_ARTIFACTS)
    make_scripts_executable(dst)
    print(f"Installed skill files to {dst}")


def link_or_copy(src: Path, dst: Path, copy_mode: bool, dry_run: bool) -> None:
    # Check parent overlap without following an existing dst symlink first
    dst_non_symlink = dst.parent.resolve() / dst.name if dst.parent.exists() else dst
    if dst_non_symlink == src.resolve():
        print(f"Skipping discovery target identical to canonical path: {dst}")
        return
    if dry_run:
        action = "Copy" if copy_mode else "Symlink"
        print(f"[dry-run] {action} {dst} -> {src}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink() or dst.is_file():
        dst.unlink()
    elif dst.is_dir():
        shutil.rmtree(dst)

    if not copy_mode:
        try:
            dst.symlink_to(src, target_is_directory=True)
            print(f"Linked {dst} -> {src}")
            return
        except OSError:
            pass
    shutil.copytree(src, dst, ignore=IGNORE_BUILD_ARTIFACTS)
    make_scripts_executable(dst)
    print(f"Copied {dst} <- {src}")


def upsert_system_prompt(existing: str | None, managed_block: str) -> str:
    if not existing or not existing.strip():
        return managed_block
    if BLOCK_RE.search(existing):
        return BLOCK_RE.sub(lambda _: managed_block, existing, count=1)
    # Clean up any malformed/unclosed marker remnants before prepending
    cleaned = existing.replace(BLOCK_START, "").replace(BLOCK_END, "").strip()
    if not cleaned:
        return managed_block
    return managed_block + "\n\n" + cleaned


def upsert_profiles(existing: list[dict] | None, managed: list[dict]) -> list[dict]:
    current = list(existing) if isinstance(existing, list) else []
    managed_by_id = {p["id"]: p for p in managed}
    seen: set[str] = set()
    merged: list[dict] = []
    for item in current:
        pid = item.get("id") if isinstance(item, dict) else None
        if pid in managed_by_id:
            if pid not in seen:
                merged.append(managed_by_id[pid])
                seen.add(pid)
        else:
            merged.append(item)
    for p in managed:
        if p["id"] not in seen:
            merged.append(p)
            seen.add(p["id"])
    return merged


def write_file_atomic_mode(path: Path, content: str, mode: int) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(str(tmp_path), flags, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.chmod(tmp_path, mode)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
    tmp_path.replace(path)


def update_paseo_config(paseo_home: Path, skill_md_path: Path, lang: str, dry_run: bool) -> bool:
    cfg_path = paseo_home / "config.json"
    if not cfg_path.is_file():
        print(f"Paseo config not found at {cfg_path}; skipping config.json update (skill files still installed).")
        return False

    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Error: {cfg_path} is not valid JSON ({exc}); leaving config untouched.", file=sys.stderr)
        return False

    profile_file = REPO_ROOT / "profiles" / (
        "paseo-profiles.zh-CN.json" if lang == "zh-CN" else "paseo-profiles.en.json"
    )
    tpl = json.loads(profile_file.read_text(encoding="utf-8"))
    managed_block = tpl["appendSystemPromptTemplate"].replace("{{SKILL_PATH}}", str(skill_md_path))
    managed_profiles = tpl["agentProfiles"]

    if dry_run:
        print(f"[dry-run] Non-destructively upsert prompt block & {len(managed_profiles)} profiles in {cfg_path} (lang={lang})")
        return False

    st_mode = cfg_path.stat().st_mode & 0o777
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bak_path = paseo_home / f"config.json.before-{SKILL_NAME}-{stamp}.bak"
    write_file_atomic_mode(bak_path, cfg_path.read_text(encoding="utf-8"), st_mode)

    daemon = data.setdefault("daemon", {})
    daemon["appendSystemPrompt"] = upsert_system_prompt(daemon.get("appendSystemPrompt"), managed_block)
    daemon["agentProfiles"] = upsert_profiles(daemon.get("agentProfiles"), managed_profiles)

    serialized = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    write_file_atomic_mode(cfg_path, serialized, st_mode)
    (paseo_home / "runs").mkdir(parents=True, exist_ok=True)
    print(f"Updated {cfg_path} (backup saved to {bak_path})")
    return True


def try_reload_paseo(user_home: Path, paseo_home: Path, dry_run: bool, skip_reload: bool) -> None:
    if dry_run or skip_reload:
        return
    paseo_bin = shutil.which("paseo")
    if not paseo_bin:
        candidate = user_home / ".local" / "bin" / "paseo"
        if candidate.is_file():
            paseo_bin = str(candidate)
    if not paseo_bin:
        print("Note: 'paseo' CLI not on PATH; run 'paseo reload' manually if a Paseo daemon is active.")
        return
    res = subprocess.run(
        [paseo_bin, "--home", str(paseo_home), "reload"],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode == 0:
        print("Reloaded Paseo daemon configuration live.")
    else:
        print(f"Note: 'paseo reload' exited with {res.returncode}: {res.stderr.strip() or res.stdout.strip()}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install paseo-engineering globally across Paseo, Antigravity, Codex, and .agents.")
    parser.add_argument("--lang", choices=["en", "zh", "zh-CN"], default="en", help="Skill & profile language edition (default: en)")
    parser.add_argument("--home", type=Path, default=Path.home(), help="Target user home directory (default: ~)")
    parser.add_argument("--paseo-home", type=Path, default=None, help="Override Paseo home directory (default: <home>/.paseo)")
    parser.add_argument("--copy", action="store_true", help="Copy directories instead of creating symlinks")
    parser.add_argument("--no-paseo-config", action="store_true", help="Do not modify Paseo config.json")
    parser.add_argument("--no-reload", action="store_true", help="Do not invoke 'paseo reload'")
    parser.add_argument("--dry-run", action="store_true", help="Print planned operations without writing files")
    args = parser.parse_args(argv)

    lang = "zh-CN" if args.lang in ("zh", "zh-CN") else "en"
    src_skill = (
        REPO_ROOT / "skills" / "zh-CN" / SKILL_NAME
        if lang == "zh-CN"
        else REPO_ROOT / "skills" / SKILL_NAME
    )
    if not (src_skill / "SKILL.md").is_file():
        print(f"Error: skill source missing at {src_skill}", file=sys.stderr)
        return 1

    user_home = args.home.expanduser().resolve()
    paseo_home = args.paseo_home.expanduser().resolve() if args.paseo_home else user_home / ".paseo"
    canonical_dst = paseo_home / "skills" / SKILL_NAME

    copy_skill_tree(src_skill, canonical_dst, args.dry_run)

    discovery_targets = [
        user_home / ".gemini" / "config" / "skills" / SKILL_NAME,
        user_home / ".codex" / "skills" / SKILL_NAME,
        user_home / ".agents" / "skills" / SKILL_NAME,
    ]
    for target in discovery_targets:
        link_or_copy(canonical_dst, target, args.copy or os.name == "nt", args.dry_run)

    if not args.no_paseo_config:
        updated = update_paseo_config(paseo_home, canonical_dst / "SKILL.md", lang, args.dry_run)
        if updated:
            try_reload_paseo(user_home, paseo_home, args.dry_run, args.no_reload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
