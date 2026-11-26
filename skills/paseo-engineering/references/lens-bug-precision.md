# Bug & Precision Hard-Constraint Lens

Attach mandatory rules when fixing subtle bugs, crashes, deadlocks, data corruption, or static/dynamic analysis false negatives (FN) and false positives (FP).

## 1. Causal Proof & Red-Green Reproduction First

- **Reproduce before editing**: Build a minimal reproduction test or harness first whenever feasible, verifying it **fails deterministically for the expected reason before the fix (Red)** and **passes after the fix (Green)**.
- **Honest bounds when non-deterministic**: For rare race conditions or environment-bound failures that cannot be reproduced deterministically, document the complete static state-transition proof and log evidence, and explicitly flag the non-reproduced boundary in the final report.

## 2. Fix Broken Invariants, Never Mask Symptoms

- Trace backward along data/control flow to the **exact site where the design invariant was first violated**:
  - If an upstream producer emitted an illegal state, null reference, or broken model, fix the upstream contract (or formally define the domain state);
  - **Never** paper over upstream corruption at downstream consumers via null short-circuits, broad `try-catch` swallowing, or benchmark-specific name/constant hardcoding.

## 3. Repository-Wide Sibling Sweep

- Abstract the structural signature of the bug (unpaired resource lifecycle, unreset state field, sibling API family, asymmetric serialize/deserialize branch) and sweep the repository:
  - Fix bounded, low-risk sibling defects in the same change with tests;
  - Surface complex cross-module siblings explicitly to the coordinator/user rather than leaving silent landmines.

## 4. Bidirectional Regression Guard (Precision × Recall)

- **When fixing false negatives / relaxing guards**: Always add structurally similar **negative counterexamples** proving the broader logic does not introduce false positives or unsafe bypasses.
- **When fixing false positives / tightening guards**: Always run or add **positive baseline cases** proving true detections and core behaviors remain intact.
