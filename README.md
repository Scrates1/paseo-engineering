# Paseo Engineering

<div align="center">
  <p><strong>A universal root-cause triage & cross-model isolated multi-agent engineering harness skill for Paseo, Antigravity, Codex, and `.agents`.</strong></p>
  <p>
    <strong>English</strong> · <a href="README.zh-CN.md">简体中文</a>
  </p>
  <p>
    <img src="https://img.shields.io/badge/architecture-Soft%20Harness%20%2B%20Skill-2563EB?style=flat-square" alt="Soft Harness + Skill">
    <img src="https://img.shields.io/badge/isolation-Git%20Worktree%20%2B%20Cross--Model-7C3AED?style=flat-square" alt="Git Worktree + Cross-Model">
    <img src="https://img.shields.io/badge/runtimes-Paseo%20%7C%20Antigravity%20%7C%20Codex-0F766E?style=flat-square" alt="Supported Runtimes">
    <img src="https://img.shields.io/badge/license-MIT-16A34A?style=flat-square" alt="MIT License">
  </p>
</div>

---

## Why This Exists

Single-agent coding workflows—and naive homogeneous multi-agent swarms—fail on real engineering problems for three structural reasons:

1. **Judge-and-Writer Conflict ("Small Task" Band-Aids)**: When a write-capable agent decides for itself whether a bug is "small," it has a built-in incentive to slap `if (x == null) return;` onto the crash site instead of tracing where the invariant actually broke upstream.
2. **Same-Model Blind Spots & Self-Review**: When the same model proposes, implements, and reviews its own code, confirmation bias rationalizes away hidden invalidation paths, lock-order inversions, and low Amdahl ceilings.
3. **Mismatched Ceremony**: Running 5-stage ceremony on a localized one-cause bug wastes 20 minutes; skipping throwaway PoC spikes on uncharted `0 → 1` ideas wastes days polishing unviable architectures.

**Paseo Engineering** solves this by separating **who diagnoses, who explores, who attacks, who writes code in an isolated Git worktree, and who audits from a different model family**—adapting depth across three execution gears while preserving the main checkout untouched.

---

## Six Specialized Agent Roles & Authority Boundaries

Except for trivial copy edits, **the primary session never acts as both orchestrator and feature/fix code writer**. Every task is executed by six specialized roles with explicit workspace and model-family boundaries:

| Role | Core Function (What It Does) | Workspace & Write Boundary | Input → Deliverable | Model-Family Pairing Rule |
| :--- | :--- | :--- | :--- | :--- |
| **`Coordinator`**<br>*(Primary Session)* | Grounds user intent, snapshots main checkout (`MAIN_DIFF_HASH`), maintains the on-disk `status.md` ledger, cuts isolated Git worktrees, dispatches Paseo child sessions, performs **conflict-free** serial merges, and runs final integration checks. | Read-only anchor + conflict-free merge in main checkout. **Never writes feature/fix code or hand-edits merge conflicts.** | User request → Dispatch briefs, merged code & final verification report | Primary session model |
| **`[Triage]`**<br>*Essence Diagnostician* | Traces the causal chain backward from **symptom site `X`** to **first broken invariant `Y`**, sweeps the repo for sibling defects, slices compound tasks, and picks the execution gear + domain lenses. | **Read-only bound** (prompt + `MAIN_DIFF_HASH` verified; no file edits or artifact-emitting builds in main checkout). | Raw symptom / stack / logs → *Essence Triage & Dispatch Card* | Coordinator read-only when localized; dedicated scout session(s) when cross-cutting |
| **`[Explorer]`**<br>*Orthogonal Explorer* | **Gear 2**: Diverges across 3 orthogonal paradigms (*Incremental* / *Structural* / *Boundary-Shift*).<br>**Gear 3**: Runs parallel *Outward Landscape* × *Inward Hard-Sample* recon. | **Read-only bound**. | Grounded invariants → Candidate options or R&D route matrix | Parallel models across at most `N-1` families (reserving ≥1 distinct family for Red-Team) |
| **`[Red-Team]`**<br>*Adversarial Skeptic* | Attempts to **falsify** `[Explorer]` proposals against live source/bytecode (duplication check, unguarded bypass entry points, true end-to-end ceiling) or runs a **Pre-Mortem** on real hard samples. | **Read-only bound**. | Candidate designs + raw repo paths → Constructible counterexamples & pruning list | **Mandatory cross-family from each candidate's authoring `[Explorer]`** |
| **`[Worker]`**<br>*Isolated Implementer* | `1 Worker = 1 Branch = 1 Isolated Worktree`. Dynamically verifies the root-cause hypothesis first (**right to challenge & re-triage** if refuted), then writes root fixes + counterexample tests (or throwaway PoC spikes) and commits cleanly on the branch. | **Read/write strictly inside its `--cwd` isolated worktree & isolated local package cache**; never touches main checkout, global caches, or `git push`. | Dispatch card + isolated worktree → Clean branch commits, counterexample tests & raw logs | Strong coding / reasoning model matched to domain |
| **`[Reviewer]`**<br>*Cross-Model Auditor* | Runs Dual-Lens Pre-Review (design contract), Dual-Lens Post-Review on committed `git diff <SLICE_BASE>...HEAD` (*Lens A: semantics/concurrency* · *Lens B: counterexamples/artifact purity*), and mandatory raw PoC/benchmark data audits. | **Read-only bound** (prompt + main/worktree snapshot verified; audits raw worktree files, diffs & logs directly—never summaries). | Committed worktree diff + raw test/benchmark logs → `PASS` or evidence-backed `BLOCKING` | **Mandatory cross-family from the corresponding `[Worker]`** *(Opus reviewing Sonnet does NOT count)* |

### Role Participation Across the Three Gears

| Gear | Problem Essence | Active Roles & Paseo Topology | Human Stops |
| :--- | :--- | :--- | :---: |
| **Gear 1 · Fast Root Fix** | Single unambiguous root omission; zero architectural trade-offs | `Coordinator` + `[Triage]` → `1 Isolated [Worker]` → `1 Cross-Model [Reviewer]` → Conflict-free serial merge | **`0`** *(auto-escalates to Gear 2 after 2 unresolved rounds)* |
| **Gear 2 · Deep Solve (`1 → N`)** | Subtle bottlenecks, systemic bugs/FN/FP, cross-module or upstream library trade-offs | `Coordinator` + `[Triage]` → `2–3 [Explorer]s` → `Cross-Model [Red-Team]` → **[Stop]** → `2 Pre-[Reviewer]s` → `1–2 Isolated [Worker]s` → `2 Cross-Model Post-[Reviewer]s` (+ Data Audit) → Conflict-free serial merge | **`1`** *(at surviving trade-off table)* |
| **Gear 3 · Explore & Spike (`0 → 1`)** | Uncharted capability or unproven R&D direction | `Coordinator` + `[Triage]` → `[Explorer-Outward]` + `[Explorer-Inward]` → `Cross-Model [Red-Team]` → **[Stop 1]** → `Isolated [Worker-Spike]` + `Cross-Model [Reviewer-Audit]` → **[Stop 2: Go / Pivot / Kill]** *(Go discards draft spike & enters Gear 2 Part 2)* | **`2`** *(Spike Contract & Go/Kill)* |

---

## Isolated Worktree Code Management & Cross-Model Review Lifecycle

All code-producing gears manage branches, worktrees, and cross-model reviews through a strict five-step Paseo protocol—so your main checkout and global caches (`~/.m2`, virtualenvs) remain untouched even when an experiment is discarded:

```mermaid
sequenceDiagram
    actor User
    participant Coord as Coordinator (Main Checkout)
    participant Triage as [Triage / Explorer + Red-Team]
    participant Worker as [Worker] (Model Family A<br/>Isolated Worktree --cwd)
    participant Rev as [Reviewer] (Model Family B<br/>Read-Only Cross-Model)

    User->>Coord: Describe bug / bottleneck / feature / R&D goal
    Coord->>Triage: Read-only causal trace (plus Gear 2/3 ideation + falsification)
    Triage-->>Coord: Essence Triage Card (Root Y, anti-band-aid rule, sibling sites)
    opt Gear 2 or Gear 3 Checkpoint
        Coord->>User: Present surviving options / Spike Contract for alignment
        User->>Coord: Approve target slice(s)
    end
    Coord->>Coord: Capture MAIN_DIFF_HASH & git worktree add -b <slice> <isolated-path>
    Coord->>Worker: paseo run --cwd <isolated-path> (Dispatch Card + active Lens)
    Worker->>Worker: 1. Verify root hypothesis (re-triage if refuted)<br/>2. Fix at root Y + counterexample tests + clean git commit
    Worker-->>Coord: Committed slice branch + raw test logs
    Coord->>Coord: Verify MAIN_DIFF_HASH intact, worktree clean & <SLICE_BASE>..HEAD > 0
    Coord->>Rev: paseo run (Cross-Model) + raw git diff <SLICE_BASE>...HEAD + neutral questions
    loop Until 0 BLOCKING (max 2 rounds; Gear 1 auto-escalates to Gear 2)
        Rev-->>Coord: BLOCKING + constructible counterexample
        Coord->>Worker: Commit fix in isolated worktree & re-run tests
        Worker-->>Coord: Updated branch commits & raw logs
        Coord->>Rev: Re-audit both incremental fix and full git diff <SLICE_BASE>...HEAD
    end
    Rev-->>Coord: PASS (0 BLOCKING) + verify worktree HEAD unchanged
    Coord->>Coord: Conflict-free serial merge (Worker rebases + re-reviews on conflict), integration check & cleanup
    Coord->>User: Report root cause, verification evidence & Paseo session IDs
```

---

## Progressive-Disclosure Skill Modules & Domain Lenses

Only the compact router in `SKILL.md` loads initially; detailed mode runbooks and domain constraint cards load on demand:

| Layer | File | Core Rules Enforced |
| :--- | :--- | :--- |
| **Core Router & Lifecycle** | [`SKILL.md`](skills/paseo-engineering/SKILL.md) | Six-role boundaries, cross-model-family rule, Stage 00 Essence Triage, Gear 1 loop, and 5-step isolated worktree lifecycle. |
| **Gear 2 Mode (`1 → N`)** | [`mode-deep-solve.md`](skills/paseo-engineering/references/mode-deep-solve.md) | 3-paradigm `[Explorer]` divergence, `[Red-Team]` code falsification, dual-lens pre/post reviews, and clean withdrawal on missed gates. |
| **Gear 3 Mode (`0 → 1`)** | [`mode-explore-spike.md`](skills/paseo-engineering/references/mode-explore-spike.md) | Outward × inward `[Explorer]` recon, pre-mortem, Spike Contract, mandatory cross-model PoC data audit, and Go → Gear 2 handoff. |
| **Performance Lens** | [`lens-performance.md`](skills/paseo-engineering/references/lens-performance.md) | True end-to-end denominator & Amdahl `<5%` cutoff, cache invalidation proofs, archive entry-level SHA diff, lock/CPU-isolated timing, zero output/diagnostic multiset drift. |
| **Bug & Precision Lens** | [`lens-bug-precision.md`](skills/paseo-engineering/references/lens-bug-precision.md) | Red-Green deterministic reproduction first, upstream invariant fixes (no symptom short-circuits), sibling sweep, bidirectional FN × FP regression guards. |
| **Refactor & Arch Lens** | [`lens-refactor-arch.md`](skills/paseo-engineering/references/lens-refactor-arch.md) | Reflection/SPI/external contract inventory, single-track convergence (delete obsolete tracks), observable snapshot equivalence. |

---

## Quick Start

Requires Python 3.8+ (zero external dependencies; Linux / macOS / Windows).

```bash
git clone https://github.com/Scrates1/paseo-engineering.git
cd paseo-engineering

# Install English edition globally (Paseo + Antigravity + Codex + ~/.agents)
python3 scripts/install.py --lang en

# Or install Simplified Chinese edition globally
python3 scripts/install.py --lang zh-CN
```

What `install.py` configures safely (non-destructively):
- Installs canonical skill files to `~/.paseo/skills/paseo-engineering/`;
- Links (or copies with `--copy` / on Windows) into `~/.gemini/config/skills/`, `~/.codex/skills/`, and `~/.agents/skills/`;
- Atomically backs up `~/.paseo/config.json` (preserving `0600` permissions), **non-destructively upserts** the `<!-- paseo-engineering:start/end -->` prompt block and `paseo_eng_*` role profiles while keeping any existing shared blocks or custom profiles intact, and runs `paseo reload` live. *(Check `paseo provider models <provider>` to adjust default model IDs in `profiles/` if your host exposes different model tiers.)*

Preview planned actions without writing files:

```bash
python3 scripts/install.py --dry-run
```

---

## Day-to-Day Steering Shortcuts

New Paseo sessions route tasks automatically—you can also steer explicitly in plain language:

| Goal | Phrase to append |
| :--- | :--- |
| Discovery & Red-Team falsification only (no code edits) | *"Run Part 1 discovery and Red-Team falsification only; don't edit code yet."* |
| Unattended overnight run | *"Pick the strongest root-cause option that survives Red-Team falsification and run end-to-end."* |
| Force full Gear 2 rigor on a deceptive bug | *"Do not patch symptoms—run Gear 2 multi-agent discovery and cross-model review."* |
| Resume after daemon restart or quota failover | *"Read the run ledger (`status.md`) and continue the current task."* |
| Standalone CLI (`agy` / `codex`) outside Paseo UI | Mention `paseo-engineering` (or `$paseo-engineering` in Codex). |

---

## Validation

```bash
python3 -m unittest discover -s tests -v
```

---

## License

Released under the [MIT License](LICENSE).
