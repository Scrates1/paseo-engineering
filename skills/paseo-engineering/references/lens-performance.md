# Performance Hard-Constraint Lens

Attach mandatory rules whenever optimizing latency, throughput, memory/RSS, GC pressure, or lock contention. Performance work is uniquely vulnerable to measurement noise, denominator illusions, and silent quality degradation:

## 1. End-to-End Denominator & Amdahl Ceiling First

- **No denominator illusions**: Quantify the target phase's true share of **end-to-end wall time** or **live heap / peak RSS** from real stage logs or full-run profiles before proposing code changes.
- **Separate sampling from wall-clock**: CPU flamegraph width measures sampled stack weight, not guaranteed wall-time savings; allocation flamegraphs (TLAB refill weight) do not equal post-GC live heap or peak RSS.
- **Amdahl cutoff**: Reject local micro-optimizations whose theoretical end-to-end ceiling sits inside run-to-run noise (e.g., `<5%`) while adding non-trivial state complexity.

## 2. Cache, Index & Concurrency Proofs

Before introducing any cache, pre-filter index, or incremental structure, prove all four properties:

1. **Key & Identity Semantics**: Value equality vs. object identity, ensuring large graph objects are not retained past their lifecycle.
2. **Invalidation Completeness**: Enumerate every mutation entry point across the repo and upstream libraries (lazy loading, synthetic generation, reflection).
3. **Exception & Retry Conservation**: Preserve identical fallback, retry opportunities, and diagnostic counts on missing dependencies (`Phantom` / unresolved symbols) or partial failures.
4. **Lock Ordering & Visibility**: Prevent lock-order inversions and non-atomic publication races under concurrent execution.

## 3. Artifact Entry-Level Purity

- Use isolated local package directories when building modified upstream dependencies; never overwrite shared `~/.m2` or global caches.
- Diff candidate vs. baseline runtime archives entry-by-entry (e.g., JAR/ZIP SHA-256 diff): only expected target class families (including inner/anonymous classes) may differ—no accidental class shadowing, dropped classes, or compiler drift.

## 4. Controlled Benchmarking & Mutual Exclusion

- **Freeze control variables**: Identical inputs, runtime version, heap flags, thread counts, and packaging layout across baseline and candidate runs.
- **Physical isolation**: Never overlap timed runs with heavy builds or test suites; acquire an exclusive lockfile, pin CPU/NUMA affinity where supported, and log background host load.
- **No heavy profilers in official timing**: Run high-overhead profilers/tracers in dedicated diagnostic passes, separate from official wall-time/RSS acceptance runs.

## 5. Zero Output/Diagnostic Drift & Clean Revert on Miss

- **Never trade semantics for speed silently**: Do not drop rules/features, tighten timeouts to abort early, or swallow diagnostics unless explicitly authorized as a lossy trade-off.
- **Full multiset equivalence**: Verify complete output multisets (not merely total counts or exit code `0`) plus all internal error, timeout, and degradation counters.
- **Independent data audit & clean withdrawal**: Have an independent read-only subagent audit raw logs, timestamps, and equivalence diffs; if targets are missed or memory/quality regresses, archive evidence first and revert workspace/artifacts cleanly.
