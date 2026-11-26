# Gear 2 · Deep Engineering Solve (1 → N: Complex Problems in Existing Systems)

Use for subtle root causes, multi-path architectural trade-offs, cross-module or upstream dependency changes, recurring regressions, or strict performance/precision targets. Explicitly orchestrates **`[Explorer]`**, **`[Red-Team]`**, **`[Worker]`**, and **`[Reviewer]`** Paseo sessions alongside active `lens-*.md` hard-constraint cards.

---

## Part 1: Multi-Agent Orthogonal Discovery, Cross-Model Falsification & Alignment

### Step 1 · Fact & Invariant Grounding (Coordinator / `[Triage]` Read-Only)

Establish objective ground truth before proposing designs:

- Trace actual execution/data flows, state machines, prior commits, and previously reverted experiments; run `python3 <skill-dir>/scripts/flow.py --task-id <task-id> init --repo <repo-root>` then `triage --symptom <X> --root <Y> --gear 2` so the Gatekeeper atomically maintains `$PASEO_HOME/runs/<task-id>/state.json` + `status.md` (default `~/.paseo/runs/<task-id>/`).
- Lock down non-negotiable **invariants** and domain-lens baselines/denominators, restating the core contradiction.

### Step 2 · Parallel Three-Paradigm Ideation (Paseo `[Explorer]` Read-Only Sessions)

For cross-module or high-complexity problems, launch 2–3 parallel read-only `[Explorer]` sessions via Paseo (titled e.g. `[Explorer-A] Incremental`, `[Explorer-B] Structural`, `[Explorer-C] Boundary-Shift`; use at most `N-1` available model families so ≥1 distinct family remains available for Red-Team falsification) spanning three orthogonal paradigms, then log the discovery with `record-explore --author-models <csv> --summary <text>` (`TRIAGED` → `EXPLORED`):

- **Paradigm A · Incremental / Local**: Smallest blast radius using existing hooks; lowest risk, bounded ceiling.
- **Paradigm B · Structural / Model**: Reshape data structures, indexes, state machines, or abstractions to eliminate an entire failure class.
- **Paradigm C · Boundary-Shift / Elimination**: Step outside the local module—eliminate invalid states or wasted work upstream in producers, internal dependency libraries (decompiling or cloning upstream source as needed), build pipelines, or protocols.

### Step 3 · Cross-Model Red-Team Falsification (Paseo `[Red-Team]` Read-Only Session)

Launch **read-only `[Red-Team]` session(s) from a different model family than each candidate's authoring `[Explorer]`**, passing candidate designs and live source paths with the sole mandate to falsify them. Record each pass with `record-redteam --model <provider/model> --summary <text>` (`EXPLORED` → `FALSIFIED`); the Gatekeeper requires, for every family that authored candidates, at least one Red-Team model from a different family (a verified `--single-family-host` is the only exception):

1. **Premise & Duplication Audit**: Do assumed invariants hold in current code? Does `main`/`develop` already implement part of this or conflict with it?
2. **Bypass & Counterexample Hunt**: Search repo-wide for unguarded entry points, lock-order inversions, cache invalidation gaps, exception/degradation swallowing, or missing-dependency (`Phantom` / unresolved symbol) traps.
3. **Value-vs-Complexity Challenge**: Does the true end-to-end gain justify the complexity? Prune both low-ceiling band-aids and over-engineered abstractions.
4. **Autonomous Micro-Probe (Zero Extra Human Stops)**: If a candidate hinges on a single unverified runtime fact, the Coordinator may cut a temporary isolated worktree (`isolate --kind probe`, legal only in `EXPLORED` / `FALSIFIED`) and run a 10-minute disposable `[Worker]` micro-probe directly (without entering [mode-explore-spike.md](mode-explore-spike.md)'s human checkpoints), feeding empirical facts straight into Step 4.

### Step 4 · Trade-off Synthesis & Human Alignment (Single Default Stop)

- Prune falsified options (logging one-line rejection reasons) and present a concise table: **Root Location (incl. cross-repo) | Mechanism | Expected Ceiling | Red-Team Verified Risks & Trade-offs**.
- **Pause once for user alignment** (proceed autonomously if pre-authorized, recording `align --auto-authorized`; drop back to Gear 1 via `triage --re-triage` if falsification proves a trivial omission). Record the agreed slices with `align --slices <csv> --summary <text>` (`FALSIFIED` → `ALIGNED`).

---

## Part 2: Isolated Worktree Implementation & Cross-Model Dual-Review Loop

Part 2 is driven by the Gatekeeper (`scripts/flow.py`; see Section 4 of `SKILL.md`). `<skill-dir>` is the installed skill directory; every command below accepts `--task-id <task-id>` (or `--run-dir <dir>`) and rejects out-of-order calls.

### Stage 1 · Dual-Lens Pre-Review (2 Parallel Paseo `[Reviewer]` Read-Only Sessions)

Draft a falsifiable implementation spec (invariants, counterexamples, exact file scope, verification protocol) and spawn two parallel read-only Paseo pre-review sessions (at least one from a different model family than the planned `[Worker]`):

- **`[Reviewer-Pre-A]` (Semantics & Invariants)**: Behavioral equivalence, state lifecycle, concurrency safety, exception/degradation conservation, compatibility.
- **`[Reviewer-Pre-B]` (Verifiability & Isolation)**: Counterexample test effectiveness, worktree/package-cache zero-pollution plan, fairness of empirical comparisons.
- **Entry Gate**: Fold all evidence-backed `BLOCKING` items into the revised spec, then record it with `record-prereview --reviewer-a-model <m1> --reviewer-b-model <m2> --planned-worker-models <csv> --blockers <n>`. The Gatekeeper moves `ALIGNED` → `EXECUTION_READY` only when `blockers == 0` and **both** reviewers belong to model families distinct from every planned `[Worker]` family (a verified `--single-family-host` is the only exception when just one family is online).

### Stage 2 · Parallel Isolated Worktree Implementation (Paseo `[Worker]` Sessions)

- `init` already pinned `BASE_SHA` and the main-checkout snapshot (`main_diff_hash`). Cut one Paseo-native managed worktree per orthogonal slice (`id` must be in the `align --slices` list):
  ```bash
  python3 <skill-dir>/scripts/flow.py --task-id <task-id> isolate --slice <slice> --branch <new-branch> --kind production [--backend auto|paseo|git] [--apply-dirty-patch]
  ```
  `auto` runs `paseo project create` + `paseo workspace create --isolation worktree --mode branch-off --new-branch <new-branch> --base <BASE_SHA>` and records `workspaceId`, `cwd`, and `slice_base`; it falls back to `git worktree add -b` only for external repos or when Paseo is unavailable. If the task depends on uncommitted main-checkout edits, `--apply-dirty-patch` commits them as a standalone `SLICE_BASE` (merge later via `integrate --into-worktree`). Configure isolated local package caches whenever package-writing commands or upstream library builds are involved.
- Spawn each `[Worker]` bound to **both** the managed Workspace and the directory (`paseo run --no-wait -q --provider <p> --model <m> --workspace <workspaceId> --cwd <wt> --title "[Worker] <slice>"`; max 2 concurrent writers by default) and register it: `assign-worker --slice <slice> --model <provider/model> --agent-id <id>`.
- **Right to Challenge**: `[Worker]` verifies the root hypothesis first and returns empirical evidence to the Coordinator if refuted (then `triage --re-triage`).
- **Counterexamples First & Clean Commits**: `[Worker]` implements automated counterexample tests for every trap surfaced in Step 3 and Stage 1 alongside standard regressions (serializing heavy test runs against host load), and commits cleanly on the isolated branch with zero untracked residue. Failed build/test rounds go through `record-verify-fail --slice <slice> --summary <text>`.

### Stage 3 · Cross-Model Dual Post-Review, Data Audit & Conflict-Free Serial Integration

- **Mandatory Cross-Model Post-Review (Dual Lens on One Commit)**: Run `enter-review --slice <slice> --reviewer-model <provider/model> --lens A`; the Gatekeeper verifies the main checkout still matches its snapshot, `git -C <wt> status --porcelain` is empty, `<SLICE_BASE>..HEAD` has commits, the reviewer's model family differs from the `[Worker]`'s, and `HEAD` is not the previously rejected one, then records `wt_head_sha`. Add the second reviewer with `enter-review ... --lens B` on that **same `wt_head_sha`**. Spawn two parallel read-only sessions **from a different model family than `[Worker]`** (bound with `--workspace <workspaceId> --cwd <wt>`), passing raw worktree paths, `git diff <SLICE_BASE>...HEAD`, and test logs:
  - **`[Reviewer-Post-A]` (`--lens A`)**: Line-by-line diff audit for semantic equivalence, lock ordering, and edge-case degradation;
  - **`[Reviewer-Post-B]` (`--lens B`)**: Audit of counterexample test coverage, archive entry-level purity, and zero main-checkout/cache pollution.
  - Each reviewer's verdict is recorded with `record-review --slice <slice> --verdict PASS|BLOCKING --blockers <n> --lens A|B [--counterexample <text>]`, which re-verifies that `HEAD == wt_head_sha` and the worktree is clean (so a reviewer cannot mutate it). The slice reaches `REVIEW_PASSED` (pinning `approved_head_sha`) **only when both `A` and `B` have passed on the same `wt_head_sha`**.
  - `BLOCKING` needs a non-empty constructible counterexample. Route it back to the isolated `[Worker]` (`CHANGES_REQUESTED`) to commit fixes, then have the **same cross-model `[Reviewer]` audit both the incremental fix and the full `git diff <SLICE_BASE>...HEAD`** via a fresh `enter-review` until `0 BLOCKING`. After **2 rejected rounds** the slice becomes `ROUND_CAP_REACHED`: only `resolve-dispute --action re-triage|discard|user-escalate --reason <text>` is legal (never merge with an open valid `BLOCKING`).
- **Controlled Empirical Comparison & Independent Data Audit**: Execute before/after verification per active `lens-*.md`; for benchmarks or large datasets, spawn an independent read-only `[Reviewer-Audit]` to verify raw logs and calculations.
- **Conflict-Free Serial Merge or Clean Discard**: Once all gates pass, the **Coordinator** runs `integrate --slice <slice> [--into-worktree <clean-wt>]` serially without hand-editing conflicts. The Gatekeeper requires `REVIEW_PASSED`, `0` open blockers, and that both the worktree and the branch ref still equal `approved_head_sha`; it prefers `--ff-only`, otherwise dry-runs the merge and, on conflict, aborts to `NEEDS_REBASE`. In that case the original `[Worker]` rebases onto the new target tip inside its worktree and re-runs tests; the Coordinator records `mark-rebased --slice <slice> --new-slice-base <sha>`, which wipes the prior approval so a full cross-model re-review runs on the new `git diff <SLICE_BASE>...HEAD` before another `integrate`.
- **Final Verification & Archive**: When every aligned slice is `INTEGRATED`, the task enters `MERGED_PENDING_VERIFY`. Run `verify-integration --cmd "<integration-test-command>"` on the merged tree: only on exit code `0` does it `paseo workspace archive <workspaceId>` (or `git worktree remove`) every integrated slice, confirm the directories are gone, delete the temporary branches, and mark the task `COMPLETED`. If empirical targets fail, archive evidence first, then `discard-slice --slice <slice> --reason <text>` to remove the managed worktree/branch cleanly.
