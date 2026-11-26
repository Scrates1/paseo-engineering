# Paseo Engineering

<div align="center">
  <p><strong>A universal root-cause triage & cross-model isolated multi-agent engineering harness skill for Paseo, Antigravity, Codex, and `.agents`.</strong></p>
  <p>
    <strong>English</strong> · <a href="README.zh-CN.md">简体中文</a>
  </p>
  <p>
    <img src="https://img.shields.io/badge/architecture-Soft%20Skill%20%2B%20Hard%20Gatekeeper-2563EB?style=flat-square" alt="Soft Skill + Hard Gatekeeper">
    <img src="https://img.shields.io/badge/isolation-Paseo%20Managed%20Worktree%20%2B%20Cross--Model-7C3AED?style=flat-square" alt="Paseo Managed Worktree + Cross-Model">
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

A fourth failure follows: **rules written only in prompts get skipped under pressure**—a worker "reviews" itself, appends a commit after approval, or merges with a blocker still open.

**Paseo Engineering** solves this by separating **who diagnoses, who explores, who attacks, who writes code in an isolated Paseo-managed worktree, and who audits from a different model family**—and by enforcing the critical checkpoints with a deterministic Gatekeeper state machine (`scripts/flow.py`) instead of trusting prompt discipline. Depth adapts across three execution gears while the main checkout stays untouched.

---

## Six Specialized Agent Roles & Authority Boundaries

Except for trivial copy edits, **the primary session never acts as both orchestrator and feature/fix code writer**. Every task is executed by six specialized roles with explicit workspace and model-family boundaries:

| Role | Core Function (What It Does) | Workspace & Write Boundary | Input → Deliverable | Model-Family Pairing Rule |
| :--- | :--- | :--- | :--- | :--- |
| **`Coordinator`**<br>*(Primary Session)* | Grounds user intent, snapshots main checkout (`MAIN_DIFF_HASH`), drives the Gatekeeper (`scripts/flow.py`) and its on-disk `state.json` + `status.md` ledger, cuts Paseo-managed isolated worktrees, dispatches Paseo child sessions, performs **conflict-free** serial merges, and runs final integration checks. | Read-only anchor + conflict-free merge in main checkout. **Never writes feature/fix code or hand-edits merge conflicts.** | User request → Dispatch briefs, merged code & final verification report | Primary session model |
| **`[Triage]`**<br>*Essence Diagnostician* | Traces the causal chain backward from **symptom site `X`** to **first broken invariant `Y`**, sweeps the repo for sibling defects, slices compound tasks, and picks the execution gear + domain lenses. | **Read-only bound** (prompt + `MAIN_DIFF_HASH` verified; no file edits or artifact-emitting builds in main checkout). | Raw symptom / stack / logs → *Essence Triage & Dispatch Card* | Coordinator read-only when localized; dedicated scout session(s) when cross-cutting |
| **`[Explorer]`**<br>*Orthogonal Explorer* | **Gear 2**: Diverges across 3 orthogonal paradigms (*Incremental* / *Structural* / *Boundary-Shift*).<br>**Gear 3**: Runs parallel *Outward Landscape* × *Inward Hard-Sample* recon. | **Read-only bound**. | Grounded invariants → Candidate options or R&D route matrix | Parallel models across at most `N-1` families (reserving ≥1 distinct family for Red-Team) |
| **`[Red-Team]`**<br>*Adversarial Skeptic* | Attempts to **falsify** `[Explorer]` proposals against live source/bytecode (duplication check, unguarded bypass entry points, true end-to-end ceiling) or runs a **Pre-Mortem** on real hard samples. | **Read-only bound**. | Candidate designs + raw repo paths → Constructible counterexamples & pruning list | **Mandatory cross-family from each candidate's authoring `[Explorer]`** |
| **`[Worker]`**<br>*Isolated Implementer* | `1 Worker = 1 Branch = 1 Isolated Worktree`. Dynamically verifies the root-cause hypothesis first (**right to challenge & re-triage** if refuted), then writes root fixes + counterexample tests (or throwaway PoC spikes) and commits cleanly on the branch. | **Read/write strictly inside its managed worktree (`--workspace <id> --cwd <wt>`) & isolated local package cache**; never touches main checkout, global caches, or `git push`. | Dispatch card + isolated worktree → Clean branch commits, counterexample tests & raw logs | Strong coding / reasoning model matched to domain |
| **`[Reviewer]`**<br>*Cross-Model Auditor* | Runs Dual-Lens Pre-Review (design contract), Dual-Lens Post-Review on committed `git diff <SLICE_BASE>...HEAD` (*Lens A: semantics/concurrency* · *Lens B: counterexamples/artifact purity*), and mandatory raw PoC/benchmark data audits. | **Read-only bound** (prompt + main/worktree snapshot verified; audits raw worktree files, diffs & logs directly—never summaries). | Committed worktree diff + raw test/benchmark logs → `PASS` or evidence-backed `BLOCKING` | **Mandatory cross-family from the corresponding `[Worker]`** *(Opus reviewing Sonnet does NOT count)* |

### Role Participation Across the Three Gears

| Gear | Problem Essence | Active Roles & Paseo Topology | Human Stops |
| :--- | :--- | :--- | :---: |
| **Gear 1 · Fast Root Fix** | Single unambiguous root omission; zero architectural trade-offs | `Coordinator` + `[Triage]` → `1 Isolated [Worker]` → `1 Cross-Model [Reviewer]` → Conflict-free serial merge | **`0`** *(auto-escalates to Gear 2 after 2 unresolved rounds)* |
| **Gear 2 · Deep Solve (`1 → N`)** | Subtle bottlenecks, systemic bugs/FN/FP, cross-module or upstream library trade-offs | `Coordinator` + `[Triage]` → `2–3 [Explorer]s` → `Cross-Model [Red-Team]` → **[Stop]** → `2 Pre-[Reviewer]s` → `1–2 Isolated [Worker]s` → `2 Cross-Model Post-[Reviewer]s` (+ Data Audit) → Conflict-free serial merge | **`1`** *(at surviving trade-off table)* |
| **Gear 3 · Explore & Spike (`0 → 1`)** | Uncharted capability or unproven R&D direction | `Coordinator` + `[Triage]` → `[Explorer-Outward]` + `[Explorer-Inward]` → `Cross-Model [Red-Team]` → **[Stop 1]** → `Isolated [Worker-Spike]` + `Cross-Model [Reviewer-Audit]` → **[Stop 2: Go / Pivot / Kill]** *(Go discards draft spike & enters Gear 2 Part 2)* | **`2`** *(Spike Contract & Go/Kill)* |

---

## Soft Protocol + Hard Gatekeeper

Prompts alone cannot stop a tired agent from skipping a gate. Paseo Engineering therefore pairs two layers:

| Layer | Component | Responsibility |
| :--- | :--- | :--- |
| **Soft protocol** | The Skill (`SKILL.md` + `references/`) | Role boundaries, essence triage, gear routing, domain lenses, and *judgment* (which root is real, which counterexample is valid). |
| **Hard gatekeeper** | `scripts/flow.py` — a stdlib-only (Python 3.8+) state machine | Atomically maintains `$PASEO_HOME/runs/<task-id>/state.json` + `status.md` and **rejects illegal transitions with deterministic code**. |
| **Native isolation** | Paseo managed worktree (`paseo workspace create --isolation worktree --mode branch-off`) | Every write slice gets its own `workspaceId` **and** physical directory; roles launch with `paseo run --workspace <workspaceId> --cwd <wt>`, so metadata and filesystem are both isolated (passing only `--cwd` can leave a session attached to the parent's workspace). Falls back to `git worktree add` only for external repos or when Paseo is unavailable. |

### Five Deterministic Code Gates

| # | Violation Hard-Blocked | Enforcement |
| :--- | :--- | :--- |
| 1 | **Same-family review** (self-review rubber-stamp) | `enter-review` rejects a reviewer whose normalized model family equals the `[Worker]`'s; a `--single-family-host` self-report is rejected when ≥ 2 families are online. |
| 2 | **Uncommitted work, or unreviewed commits added after review** | Requires a clean worktree with commits beyond `SLICE_BASE`; `record-review` / `integrate` re-check `HEAD == wt_head_sha / approved_head_sha`; zero-fix resubmission of a rejected `HEAD` is refused. |
| 3 | **Main-checkout tampering** (including byte edits to untracked files) | Every checkpoint compares `HEAD` and `main_diff_hash` (status + binary diff + SHA-256 of each untracked file) with the snapshot. |
| 4 | **Bypassing the 2-round cap** | Round counters live in `state.json`: Gear 1 auto-escalates to Gear 2; Gear 2/3 land in `ROUND_CAP_REACHED`, leaving only `resolve-dispute` (re-triage / discard / user-escalate). |
| 5 | **Merging a sick or conflicting slice, or a `spike` / `probe` branch** | `integrate` demands `kind == production`, `REVIEW_PASSED`, `0` open blockers and a pinned `approved_head_sha`, dry-runs the merge, and aborts to `NEEDS_REBASE` on conflict. |

Escape hatches stay bounded: `--re-triage` changes course legitimately, and `--user-override "<reason>"` may skip only **workflow order / routing**—never the cross-family rule, the clean-approved-commit rule, `spike`/`probe` non-mergeability, or conflict-free merging.

---

## Gatekeeper-Driven Lifecycle & Native Worktree Isolation

All code-producing gears follow one five-step protocol, with each checkpoint passing through `scripts/flow.py`—so your main checkout and global caches (`~/.m2`, virtualenvs) remain untouched even when an experiment is discarded:

1. **Snapshot & Isolate**: `init` → `triage` → (Gear 2/3: `record-explore` → `record-redteam` → `align` → `record-prereview`) → `isolate` cuts a Paseo-native managed worktree pinned to the explicit `BASE_SHA`.
2. **Dispatch**: `paseo run --workspace <workspaceId> --cwd <wt> ...` + `assign-worker` registers the `[Worker]` and its model family.
3. **Implement & Commit**: verify the root hypothesis → fix at root `Y` → counterexample tests → clean commits (`record-verify-fail` logs failed rounds).
4. **Cross-Model Review**: `enter-review` (family + clean-commit gates) → `record-review` (Gear 2: lenses `A` and `B` on the same `wt_head_sha`), capped at 2 rounds.
5. **Integrate or Discard**: `integrate` / `mark-rebased` → `verify-integration` (archives workspaces, deletes temp branches) · `decide-spike` · `discard-slice`.

```mermaid
sequenceDiagram
    actor User
    participant Coord as Coordinator (Main Checkout)
    participant Gate as Gatekeeper (scripts/flow.py)
    participant Triage as [Triage / Explorer + Red-Team]
    participant Worker as [Worker] (Model Family A<br/>Managed Worktree)
    participant Rev as [Reviewer] (Model Family B<br/>Read-Only Cross-Model)

    User->>Coord: Describe bug / bottleneck / feature / R&D goal
    Coord->>Gate: init + triage (symptom X, root Y, gear)
    Coord->>Triage: Read-only causal trace (plus Gear 2/3 ideation + falsification)
    Triage-->>Coord: Essence Triage Card (Root Y, anti-band-aid rule, sibling sites)
    opt Gear 2 or Gear 3
        Coord->>Gate: record-explore / record-redteam (family check)
        Coord->>User: Present surviving options / Spike Contract
        User->>Coord: Approve target slice(s)
        Coord->>Gate: align (+ record-prereview in Gear 2)
    end
    Coord->>Gate: isolate --slice --branch (paseo workspace create, branch-off BASE_SHA)
    Gate-->>Coord: workspaceId + managed worktree cwd
    Coord->>Worker: paseo run --workspace workspaceId --cwd wt (Dispatch Card + Lens)
    Coord->>Gate: assign-worker (records worker family)
    Worker->>Worker: 1. Verify root hypothesis (re-triage if refuted)<br/>2. Fix at root Y + counterexample tests + clean git commit
    Worker-->>Coord: Committed slice branch + raw test logs
    Coord->>Gate: enter-review (reviewer family != worker family, clean + committed, main snapshot intact)
    Gate-->>Coord: OK, wt_head_sha recorded
    Coord->>Rev: paseo run --workspace workspaceId + raw git diff SLICE_BASE...HEAD + neutral questions
    loop Until 0 BLOCKING (max 2 rounds; Gear 1 auto-escalates to Gear 2)
        Rev-->>Coord: BLOCKING + constructible counterexample
        Coord->>Gate: record-review BLOCKING (round counter++)
        Coord->>Worker: Commit fix in managed worktree & re-run tests
        Worker-->>Coord: Updated branch commits & raw logs
        Coord->>Gate: enter-review (new HEAD required)
    end
    Rev-->>Coord: PASS (Gear 2: lens A and B on same wt_head_sha)
    Coord->>Gate: record-review PASS (HEAD == wt_head_sha) -> REVIEW_PASSED
    Coord->>Gate: integrate (clean + approved_head_sha, conflict-free or NEEDS_REBASE)
    Coord->>Gate: verify-integration --cmd (archive workspaces, delete temp branches)
    Coord->>User: Report root cause, verification evidence & Paseo session IDs
```

---

## Progressive-Disclosure Skill Modules & Domain Lenses

Only the compact router in `SKILL.md` loads initially; detailed mode runbooks and domain constraint cards load on demand:

| Layer | File | Core Rules Enforced |
| :--- | :--- | :--- |
| **Core Router & Lifecycle** | [`SKILL.md`](skills/paseo-engineering/SKILL.md) | Six-role boundaries, cross-model-family rule, Stage 00 Essence Triage, Gear 1 loop, Gatekeeper subcommand map, and 5-step managed-worktree lifecycle. |
| **Gatekeeper State Machine** | `scripts/flow.py` *(inside the installed skill directory)* | Atomic `state.json` + `status.md` ledger, 5 deterministic code gates, Paseo-native `isolate` with `git worktree` fallback, bounded `--re-triage` / `--user-override`. |
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
- Installs canonical skill files (including the Gatekeeper `scripts/flow.py`, kept executable on POSIX) to `~/.paseo/skills/paseo-engineering/`;
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
| Resume after daemon restart or quota failover | *"Run `flow.py status` / read the run ledger (`status.md`) and continue the current task."* |
| Standalone CLI (`agy` / `codex`) outside Paseo UI | Mention `paseo-engineering` (or `$paseo-engineering` in Codex). |

---

## Validation

```bash
python3 -m unittest discover -s tests -v
```

---

## License

Released under the [MIT License](LICENSE).
