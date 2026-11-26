# Gear 3 · Explore & Spike (0 → 1: Multi-Agent Recon, Pre-Mortem & Isolated PoC)

Use when exploring a new technical direction, introducing a novel mechanism/algorithm, evaluating competing architectures, or testing unproven hypotheses on real workloads. Core principle: **orchestrate Paseo roles to spend 10% effort on outward/inward recon, cross-model pre-mortem, an isolated throwaway PoC, and mandatory cross-model data audit before invoking heavy Gear 2 production gates**.

---

## Step 1 · Parallel External × Internal Recon (2 Paseo `[Explorer]` Read-Only Sessions)

Initialize `$PASEO_HOME/runs/<task-id>/status.md` (default `~/.paseo/runs/<task-id>/status.md`) and spawn two complementary read-only Paseo Explorer sessions (reserving ≥1 distinct model family for Red-Team):

- **`[Explorer-Outward]` · External Landscape Survey**:
  - Survey 2–4 representative approaches across production systems, open-source tools, protocols, or literature.
  - Strip marketing claims: extract **core assumptions, structural ceilings (what it fundamentally cannot solve), known engineering failure modes, and maintenance cost**.
- **`[Explorer-Inward]` · Internal Workload & Substrate Audit**:
  - Extract **3–5 representative hard pain-point samples** from real repository workloads (never toy examples).
  - Map host extension points, input shapes, and hard CPU/RAM/latency budgets.

## Step 2 · Cross-Model Red-Team Pre-Mortem (Paseo `[Red-Team]` Read-Only Session)

Launch **read-only `[Red-Team]` session(s) from a different model family than `[Explorer]`**:

- **Framing**: *"Assume this direction failed and was abandoned 6 months from now—what killed it?"*
- Collide each external route from `[Explorer-Outward]` against the real hard samples and substrate constraints from `[Explorer-Inward]`, pruning paper-pretty mismatches down to 1–2 falsifiable candidates.

## Step 3 · Checkpoint 1: Lock the Minimal Falsifiable Spike Contract

Present a concise **Direction Matrix & Spike Proposal** and **pause for Checkpoint 1**:

- Pick 1 (or 2) routes to prototype;
- Lock the **Spike Contract**: (1) single core hypothesis under test; (2) exact real hard samples; (3) quantitative/qualitative **Go** vs. **Kill** thresholds. *(Conclude here if the user requested research only.)*

## Step 4 · Isolated Worktree Throwaway PoC + Mandatory Cross-Model Data Audit

- Capture `MAIN_DIFF_HASH`, cut dedicated temporary worktrees (`git worktree add -b spike/<topic> <spike-worktree> <BASE_SHA>`; two parallel worktrees for A/B shootouts, with isolated package caches), and launch `[Worker]` bound via `--cwd` (titled `[Worker-Spike] <route>`).
- **Skip production polish, enforce mandatory cross-model data audit**:
  - Skip broad edge-case polish and style ceremony to reach real signal fast and commit on the spike branch;
  - **Never fake signal**: no hardcoded sample answers, synthetic stubs, or cherry-picked easy inputs. Once `[Worker]` finishes, the Coordinator **must launch a cross-model-family read-only `[Reviewer-Audit]`** to verify the spike contains no hardcoded shortcuts, the main checkout matches `MAIN_DIFF_HASH`, and raw logs/latency/memory/hit metrics are genuine.

## Step 5 · Checkpoint 2: Go / Pivot / Kill Handoff

Report cross-model-audited PoC measurements and observed ceilings, then **pause for Checkpoint 2**:

- **Go (Commit to Production)**: Remove/archive the disposable spike worktree/branch (never merge raw prototype code into `main`) and transition into **Part 2 of [mode-deep-solve.md](mode-deep-solve.md)** (Stage 1 Cross-Model Dual Pre-Review → Stage 2 Fresh Isolated Worktree Implementation & Counterexamples → Stage 3 Cross-Model Dual Post-Review & Conflict-Free Serial Merge).
- **Pivot**: Archive findings in `status.md`, remove the old spike worktree, and return to **Step 3** to confirm the updated Spike Contract with the user before running the next probe.
- **Kill (Fail Cheaply)**: Archive empirical proof of infeasibility and remove temporary spike worktrees/branches cleanly.
