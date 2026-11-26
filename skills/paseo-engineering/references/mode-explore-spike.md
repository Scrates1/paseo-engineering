# Gear 3 · Explore & Spike (0 → 1: Multi-Agent Recon, Pre-Mortem & Isolated PoC)

Use when exploring a new technical direction, introducing a novel mechanism/algorithm, evaluating competing architectures, or testing unproven hypotheses on real workloads. Core principle: **orchestrate Paseo roles to spend 10% effort on outward/inward recon, cross-model pre-mortem, an isolated throwaway PoC, and mandatory cross-model data audit before invoking heavy Gear 2 production gates**.

---

## Step 1 · Parallel External × Internal Recon (2 Paseo `[Explorer]` Read-Only Sessions)

Run `python3 <skill-dir>/scripts/flow.py --task-id <task-id> init --repo <repo-root>` and `triage --symptom <X> --root <Y> --gear 3` so the Gatekeeper maintains `$PASEO_HOME/runs/<task-id>/state.json` + `status.md` (default `~/.paseo/runs/<task-id>/`), then spawn two complementary read-only Paseo Explorer sessions (reserving ≥1 distinct model family for Red-Team) and log them with `record-explore --author-models <csv> --summary <text>` (`TRIAGED` → `RECON_DONE`):

- **`[Explorer-Outward]` · External Landscape Survey**:
  - Survey 2–4 representative approaches across production systems, open-source tools, protocols, or literature.
  - Strip marketing claims: extract **core assumptions, structural ceilings (what it fundamentally cannot solve), known engineering failure modes, and maintenance cost**.
- **`[Explorer-Inward]` · Internal Workload & Substrate Audit**:
  - Extract **3–5 representative hard pain-point samples** from real repository workloads (never toy examples).
  - Map host extension points, input shapes, and hard CPU/RAM/latency budgets.

## Step 2 · Cross-Model Red-Team Pre-Mortem (Paseo `[Red-Team]` Read-Only Session)

Launch **read-only `[Red-Team]` session(s) from a different model family than `[Explorer]`** and record them with `record-redteam --model <provider/model> --summary <text>` (`RECON_DONE` → `PREMORTEM_DONE`; the Gatekeeper rejects a Red-Team model from the same family as the explorers unless a verified `--single-family-host` applies):

- **Framing**: *"Assume this direction failed and was abandoned 6 months from now—what killed it?"*
- Collide each external route from `[Explorer-Outward]` against the real hard samples and substrate constraints from `[Explorer-Inward]`, pruning paper-pretty mismatches down to 1–2 falsifiable candidates.

## Step 3 · Checkpoint 1: Lock the Minimal Falsifiable Spike Contract

Present a concise **Direction Matrix & Spike Proposal** and **pause for Checkpoint 1**:

- Pick 1 (or 2) routes to prototype;
- Lock the **Spike Contract**: (1) single core hypothesis under test; (2) exact real hard samples; (3) quantitative/qualitative **Go** vs. **Kill** thresholds. *(Conclude here if the user requested research only.)* Record the ruling with `python3 <skill-dir>/scripts/flow.py --task-id <task-id> align --slices <spike-slice> --spike-hypothesis <h> --spike-samples <s> --go-criteria <g>` (`PREMORTEM_DONE` → `EXECUTION_READY`); all three contract fields must be non-empty.

## Step 4 · Isolated Managed Worktree Throwaway PoC + Mandatory Cross-Model Data Audit

- The Gatekeeper (`scripts/flow.py`) pinned `BASE_SHA` and the main-checkout snapshot at `init`. Cut a dedicated temporary Paseo-native managed worktree per route (two parallel slices for A/B shootouts, with isolated package caches):
  ```bash
  python3 <skill-dir>/scripts/flow.py --task-id <task-id> isolate --slice <spike-slice> --branch spike/<topic> --kind spike [--backend auto|paseo|git]
  ```
  `kind spike` is legal only in Gear 3 `EXECUTION_READY` for a slice named in `align --slices`. `auto` uses `paseo project create` + `paseo workspace create --isolation worktree --mode branch-off --new-branch spike/<topic> --base <BASE_SHA>` (falling back to `git worktree add -b` only for external repos or when Paseo is unavailable). Launch `[Worker]` bound to both the Workspace and the directory (`paseo run --no-wait -q --workspace <workspaceId> --cwd <wt> --title "[Worker-Spike] <route>"`) and register it with `assign-worker --slice <spike-slice> --model <provider/model>`.
- **Skip production polish, enforce mandatory cross-model data audit**:
  - Skip broad edge-case polish and style ceremony to reach real signal fast and commit on the spike branch;
  - **Never fake signal**: no hardcoded sample answers, synthetic stubs, or cherry-picked easy inputs. Once `[Worker]` finishes, the Coordinator **must launch a cross-model-family read-only `[Reviewer-Audit]`** to verify the spike contains no hardcoded shortcuts, the main checkout still matches its snapshot, and raw logs/latency/memory/hit metrics are genuine. Gate it with `enter-review --slice <spike-slice> --reviewer-model <provider/model> --lens audit` (clean, committed worktree and a family different from the `[Worker]`'s) and record the outcome with `record-review --slice <spike-slice> --verdict PASS|BLOCKING --blockers <n> --lens audit`; a `PASS` moves the slice to `SPIKE_AUDITED`.
- A `spike` / `probe` slice can **never** be passed to `integrate`: raw prototype code is not mergeable by construction.

## Step 5 · Checkpoint 2: Go / Pivot / Kill Handoff

Report cross-model-audited PoC measurements and observed ceilings, then **pause for Checkpoint 2** and record the ruling with `decide-spike --slice <spike-slice> --decision go|pivot|kill [--slices <prod-slices>] --summary <text>` (requires `SPIKE_AUDITED`). Whatever the decision, the Gatekeeper archives the spike workspace (`paseo workspace archive`, or `git worktree remove`) and deletes the `spike/<topic>` branch:

- **Go (Commit to Production)**: Never merge raw prototype code into `main`. Use `decide-spike --slice <spike-slice> --decision go --slices <prod-slices> --summary <text>`, where `--slices` lists the **fresh production slices** adopted after the switch to Gear 2 (omitted, it defaults to `<spike-slice>-prod`). The task moves to Gear 2 `ALIGNED`: record `record-prereview` (Cross-Model Dual Pre-Review), then `isolate --kind production` a **fresh** managed worktree and continue with **Part 2 of [mode-deep-solve.md](mode-deep-solve.md)** (Stage 2 Implementation & Counterexamples → Stage 3 Cross-Model Dual Post-Review & Conflict-Free Serial Merge).
- **Pivot**: The task returns to `PREMORTEM_DONE`; archive findings in `status.md` and go back to **Step 3** to confirm an updated Spike Contract with the user (`align --spike-hypothesis ...` again) before running the next probe.
- **Kill (Fail Cheaply)**: Archive empirical proof of infeasibility; the task becomes `DISCARDED` with the temporary spike worktree/branch removed and the main checkout untouched.
