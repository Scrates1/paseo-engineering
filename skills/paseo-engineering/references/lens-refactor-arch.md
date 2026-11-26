# Refactoring & Architecture Hard-Constraint Lens

Attach mandatory rules when decoupling core modules, replacing data structures, consolidating multi-track legacy code into a single track, or evolving public contracts.

## 1. Explicit & Implicit Dependency Inventory

Before splitting or replacing components, audit four categories of hidden coupling beyond static call graphs:

1. **Dynamic Mechanisms**: Reflection, serialization field names, annotation processors, SPI / DI wiring;
2. **External Contracts**: Persisted formats, CLI flags, environment variables, log/report parsers, cross-repo version pins;
3. **Concurrency & Lifecycle**: Initialization order, singleton/thread-local teardown, exception rollback guarantees;
4. **Test Coupling**: Existing tests asserting internal implementation classes or exact invocation counters.

## 2. Single-Track Convergence & Blast-Radius Control

- **Avoid permanent dual-trackrot**: Migrate in small, verifiable slices and **delete obsolete code paths once equivalence is proven** rather than leaving unmaintained parallel implementations.
- **Bounded feature flags**: When blast radius requires a transitional toggle, document the default mode, switching invariants, and explicit retirement criteria.
- **Separate structure from behavior changes**: Pure refactoring commits must preserve observable behavior; do not tangle large structural moves with new semantic changes in a single indivisible diff.

## 3. Observable Equivalence Baseline

- Capture baseline snapshots before refactoring (public API behavior, end-to-end output snapshots, error/diagnostic formats, key resource watermarks).
- Verify full regression and snapshot equivalence afterward; any intentional behavioral change or deprecation must be itemized explicitly during pre-review and final delivery.
