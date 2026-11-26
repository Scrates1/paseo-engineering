from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import install

EXPECTED_REL_FILES = {
    Path("SKILL.md"),
    Path("references/lens-bug-precision.md"),
    Path("references/lens-performance.md"),
    Path("references/lens-refactor-arch.md"),
    Path("references/mode-deep-solve.md"),
    Path("references/mode-explore-spike.md"),
}

FORBIDDEN_PATTERNS = [
    re.compile(r"(?<![A-Za-z0-9])/(?:Users|home|data)/[A-Za-z0-9._-]+/"),
    re.compile(r"\b192\.168\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{16,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{12,}\b"),
]

# Verified SHA-256 digests of non-public environment/project tokens so this test file stays 100% generic
FORBIDDEN_TOKEN_SHA256 = {
    "68d5ebb80c409e543c5aa5f5cc7500a2e1a2e4f349391747d739dca8e0a727db",
    "8d47e4b4255b3190cf999eea3fd3d4aac797c865e514f51d26d73fa46a101f5d",
    "b9d7b147c23ed3959eb32985022418185b20c00d138da6714ed4b062fabacd42",
    "be769620fd8efdb25c2b352ecd20a6338c481cf674a6d3d759451dc181b15b47",
}
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{3,}")


def scan_text_violations(text: str) -> list[str]:
    hits: list[str] = []
    for pat in FORBIDDEN_PATTERNS:
        if pat.search(text):
            hits.append(f"pattern:{pat.pattern}")
    for tok in TOKEN_RE.findall(text):
        digest = hashlib.sha256(tok.lower().encode("utf-8")).hexdigest()
        if digest in FORBIDDEN_TOKEN_SHA256:
            hits.append(f"token_sha256:{digest[:12]}")
    return hits


class RepoValidationTest(unittest.TestCase):
    def test_en_and_zh_skill_file_parity(self) -> None:
        en_root = REPO_ROOT / "skills" / "paseo-engineering"
        zh_root = REPO_ROOT / "skills" / "zh-CN" / "paseo-engineering"
        en_files = {p.relative_to(en_root) for p in en_root.rglob("*.md")}
        zh_files = {p.relative_to(zh_root) for p in zh_root.rglob("*.md")}
        self.assertEqual(en_files, EXPECTED_REL_FILES)
        self.assertEqual(zh_files, EXPECTED_REL_FILES)

    def test_skill_frontmatter(self) -> None:
        for skill_md in [
            REPO_ROOT / "skills" / "paseo-engineering" / "SKILL.md",
            REPO_ROOT / "skills" / "zh-CN" / "paseo-engineering" / "SKILL.md",
        ]:
            content = skill_md.read_text(encoding="utf-8")
            self.assertTrue(content.startswith("---\nname: paseo-engineering\ndescription:"), f"Invalid frontmatter in {skill_md}")

    def test_all_relative_markdown_links_resolve(self) -> None:
        md_files = list(REPO_ROOT.rglob("*.md"))
        self.assertGreaterEqual(len(md_files), 14)
        link_re = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        for md in md_files:
            text = md.read_text(encoding="utf-8")
            for match in link_re.finditer(text):
                target = match.group(1).split("#", 1)[0].strip()
                if not target or target.startswith(("http://", "https://", "mailto:")):
                    continue
                resolved = (md.parent / target).resolve()
                self.assertTrue(resolved.exists(), f"Broken link '{target}' in {md.relative_to(REPO_ROOT)}")

    def test_privacy_scanner_catches_synthetic_violations(self) -> None:
        for bad in [
            "path /" + "home/alice/work",
            "mount /" + "data/runner/cache",
            "host 192.168" + ".10.25",
            "secret ghp_" + ("A" * 28),
        ]:
            self.assertTrue(scan_text_violations(bad), f"Scanner failed to flag: {bad}")

    def test_no_private_paths_or_internal_identifiers_across_all_files(self) -> None:
        for path in REPO_ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
                continue
            violations = scan_text_violations(path.read_text(encoding="utf-8"))
            self.assertEqual(violations, [], f"Privacy violation {violations} in {path.relative_to(REPO_ROOT)}")

    def test_installer_in_isolated_temp_home_and_preserves_existing_config(self) -> None:
        for lang in ("en", "zh-CN"):
            with tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp) / "home"
                paseo_dir = home / ".paseo"
                paseo_dir.mkdir(parents=True)
                cfg = paseo_dir / "config.json"
                initial = {
                    "version": 1,
                    "daemon": {
                        "listen": "127.0.0.1:6767",
                        "appendSystemPrompt": "<!-- paseo-engineering:start -->\nbroken unclosed\n<!-- paseo-shared:start -->\nexisting shared rule\n<!-- paseo-shared:end -->",
                        "agentProfiles": [
                            {"id": "user_custom", "name": "Custom", "provider": "codex", "model": "gpt-6.1-sol"},
                            {"id": "paseo_auto_dev_worker", "name": "Shared Worker", "provider": "codex", "model": "gpt-6.1-sol"},
                        ],
                    },
                }
                cfg.write_text(json.dumps(initial), encoding="utf-8")
                cfg.chmod(0o600)

                rc = install.main(["--lang", lang, "--home", str(home), "--no-reload"])
                self.assertEqual(rc, 0)
                rc2 = install.main(["--lang", lang, "--home", str(home), "--no-reload"])
                self.assertEqual(rc2, 0)

                canonical = paseo_dir / "skills" / "paseo-engineering" / "SKILL.md"
                self.assertTrue(canonical.is_file())
                for rel in [
                    ".gemini/config/skills/paseo-engineering/SKILL.md",
                    ".codex/skills/paseo-engineering/SKILL.md",
                    ".agents/skills/paseo-engineering/SKILL.md",
                ]:
                    self.assertTrue((home / rel).is_file(), f"Missing {rel}")

                updated = json.loads(cfg.read_text(encoding="utf-8"))
                prompt = updated["daemon"]["appendSystemPrompt"]
                self.assertEqual(prompt.count("<!-- paseo-engineering:start -->"), 1)
                self.assertEqual(prompt.count("<!-- paseo-engineering:end -->"), 1)
                self.assertIn("<!-- paseo-shared:start -->\nexisting shared rule\n<!-- paseo-shared:end -->", prompt)
                self.assertIn(str(canonical), prompt)

                profile_ids = [p["id"] for p in updated["daemon"]["agentProfiles"]]
                self.assertEqual(len(profile_ids), len(set(profile_ids)))
                self.assertIn("user_custom", profile_ids)
                self.assertIn("paseo_auto_dev_worker", profile_ids)
                self.assertEqual(len(profile_ids), 10)
                self.assertEqual(cfg.stat().st_mode & 0o777, 0o600)

    def test_installer_overlapping_paseo_home_does_not_self_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            codex_home = home / ".codex"
            rc = install.main(["--lang", "en", "--home", str(home), "--paseo-home", str(codex_home), "--no-reload"])
            self.assertEqual(rc, 0)
            target = codex_home / "skills" / "paseo-engineering"
            self.assertFalse(target.is_symlink())
            self.assertTrue((target / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
