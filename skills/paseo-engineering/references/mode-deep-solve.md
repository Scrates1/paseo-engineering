# Gear 2 · Deep Engineering Solve (1 → N: Complex Problems in Existing Systems)

Use for subtle root causes, multi-path architectural trade-offs, cross-module or upstream dependency changes, recurring regressions, or strict performance/precision targets. Explicitly orchestrates **`[Explorer]`**, **`[Red-Team]`**, **`[Worker]`**, and **`[Reviewer]`** Paseo sessions alongside active `lens-*.md` hard-constraint cards.

---

## Part 1: Multi-Agent Orthogonal Discovery, Cross-Model Falsification & Alignment

### Step 1 · Fact & Invariant Grounding (Coordinator / `[Triage]` Read-Only)

Establish objective ground truth before proposing designs:

- Trace actual execution/data flows, state machines, prior commits, and previously reverted experiments; initialize `$PASEO_HOME/runs/<task-id>/status.md` (default `~/.paseo/runs/<task-id>/status.md`).
- Lock down non-negotiable **invariants** and domain-lens baselines/denominators, restating the core contradiction.

### Step 2 · Parallel Three-Paradigm Ideation (Paseo `[Explorer]` Read-Only Sessions)

For cross-module or high-complexity problems, launch 2–3 parallel read-only `[Explorer]` sessions via Paseo (titled e.g. `[Explorer-A] Incremental`, `[Explorer-B] Structural`, `[Explorer-C] Boundary-Shift`; use at most `N-1` available model families so ≥1 distinct family remains available for Red-Team falsification) spanning three orthogonal paradigms:

- **Paradigm A · Incremental / Local**: Smallest blast radius using existing hooks; lowest risk, bounded ceiling.
- **Paradigm B · Structural / Model**: Reshape data structures, indexes, state machines, or abstractions to eliminate an entire failure class.
- **Paradigm C · Boundary-Shift / Elimination**: Step outside the local module—eliminate invalid states or wasted work upstream in producers, internal dependency libraries (decompiling or cloning upstream source as needed), build pipelines, or protocols.

### Step 3 · Cross-Model Red-Team Falsification (Paseo `[Red-Team]` Read-Only Session)

Launch **read-only `[Red-Team]` session(s) from a different model family than each candidate's authoring `[Explorer]`**, passing candidate designs and live source paths with the sole mandate to falsify them:

1. **Premise & Duplication Audit**: Do assumed invariants hold in current code? Does `main`/`develop` already implement part of this or conflict with it?
2. **Bypass & Counterexample Hunt**: Search repo-wide for unguarded entry points, lock-order inversions, cache invalidation gaps, exception/degradation swallowing, or missing-dependency (`Phantom` / unresolved symbol) traps.
3. **Value-vs-Complexity Challenge**: Does the true end-to-end gain justify the complexity? Prune both low-ceiling band-aids and over-engineered abstractions.
4. **Autonomous Micro-Probe (Zero Extra Human Stops)**: If a candidate hinges on a single unverified runtime fact, the Coordinator may cut a temporary isolated worktree and run a 10-minute disposable `[Worker]` micro-probe directly (without entering [mode-explore-spike.md](mode-explore-spike.md)'s human checkpoints), feeding empirical facts straight into Step 4.

### Step 4 · Trade-off Synthesis & Human Alignment (Single Default Stop)

- Prune falsified options (logging one-line rejection reasons) and present a concise table: **Root Location (incl. cross-repo) | Mechanism | Expected Ceiling | Red-Team Verified Risks & Trade-offs**.
- **Pause once for user alignment** (proceed autonomously if pre-authorized; drop back to Gear 1 if falsification proves a trivial omission).

---

## Part 2: Isolated Worktree Implementation & Cross-Model Dual-Review Loop

### Stage 1 · Dual-Lens Pre-Review (2 Parallel Paseo `[Reviewer]` Read-Only Sessions)

Draft a falsifiable implementation spec (invariants, counterexamples, exact file scope, verification protocol) and spawn two parallel read-only Paseo pre-review sessions (at least one from a different model family than the planned `[Worker]`):

- **`[Reviewer-Pre-A]` (Semantics & Invariants)**: Behavioral equivalence, state lifecycle, concurrency safety, exception/degradation conservation, compatibility.
- **`[Reviewer-Pre-B]` (Verifiability & Isolation)**: Counterexample test effectiveness, worktree/package-cache zero-pollution plan, fairness of empirical comparisons.
- **Entry Gate**: Fold all evidence-backed `BLOCKING` items into the revised spec and update `status.md` before cutting worktrees.

### Stage 2 · Parallel Isolated Worktree Implementation (Paseo `[Worker]` Sessions)

- Capture `MAIN_DIFF_HASH` of the main checkout, cut a dedicated branch and worktree per orthogonal slice (`git worktree add -b <slice> <worktree-path> <BASE_SHA>`, setting `SLICE_BASE = BASE_SHA`, or committing any required main-checkout dirty patch first as `SLICE_BASE`; configure isolated local package caches whenever package-writing commands or upstream library builds are involved), and spawn `[Worker]` bound via `--cwd <worktree-path>` (max 2 concurrent writers by default).
- **Right to Challenge**: `[Worker]` verifies the root hypothesis first and returns empirical evidence to the Coordinator if refuted.
- **Counterexamples First & Clean Commits**: `[Worker]` implements automated counterexample tests for every trap surfaced in Step 3 and Stage 1 alongside standard regressions (serializing heavy test runs against host load), and commits cleanly on the isolated branch with zero untracked residue.

### Stage 3 · Cross-Model Dual Post-Review, Data Audit & Conflict-Free Serial Integration

- **Mandatory Cross-Model Post-Review**: Verify main checkout matches `MAIN_DIFF_HASH`, `git -C <wt> status --porcelain` is empty, and `<SLICE_BASE>..HEAD` has commits (recording `WT_HEAD_SHA`); then spawn two parallel read-only sessions **from a different model family than `[Worker]`**, passing raw worktree paths, `git diff <SLICE_BASE>...HEAD`, and test logs (re-verifying `WT_HEAD_SHA` unchanged afterward):
  - **`[Reviewer-Post-A]`**: Line-by-line diff audit for semantic equivalence, lock ordering, and edge-case degradation;
  - **`[Reviewer-Post-B]`**: Audit of counterexample test coverage, archive entry-level purity, and zero main-checkout/cache pollution.
  - Route valid `BLOCKING` defects back to the isolated `[Worker]` to commit fixes, then have the **same cross-model `[Reviewer]` audit both the incremental fix and the full `git diff <SLICE_BASE>...HEAD`** until `0 BLOCKING` (re-triage or discard the slice if genuine defects remain unfixed after 2 rounds; never merge with an open valid `BLOCKING`).
- **Controlled Empirical Comparison & Independent Data Audit**: Execute before/after verification per active `lens-*.md`; for benchmarks or large datasets, spawn an independent read-only `[Reviewer-Audit]` to verify raw logs and calculations.
- **Conflict-Free Serial Merge or Clean Discard**: Once all gates pass, the **Coordinator** integrates `<SLICE_BASE>..HEAD` serially without hand-editing conflicts (if a later slice conflicts with an earlier merged slice, its original `[Worker]` rebases onto `NEW_TARGET_SHA`, updates `SLICE_BASE = NEW_TARGET_SHA`, re-runs tests, and passes cross-model `[Reviewer]` re-audit on the new `git diff <SLICE_BASE>...HEAD` before clean merge), re-runs integration checks on the merged tree, and removes temporary worktrees; if empirical targets fail, archive evidence first and delete the isolated worktree/branch cleanly.
