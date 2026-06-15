# Step 4: Solver Wrapper and Task Outcomes

## Goal
Centralize solver setup and convert solved model objects into stable `TaskOutcome` and `NetworkSolution` records.

## Scope
- Add a solver wrapper/helper around the existing GEKKO/Pyomo setup.
- Preserve current solver names, tolerances, and model equations.
- Introduce `TaskOutcome` for one task result and `NetworkSolution` for solved HEN topology and metrics.
- Keep full GEKKO model objects out of durable results.

## Checklist
- [ ] Add a solver setup helper that applies current `couenne`, `ipopt-pyomo`, `apopt`, and `ipopt-GEKKO` behavior.
- [ ] Record solver name, extension, status, objective value, solve time, and failure reason.
- [ ] Convert successful PDM/TDM/ESM solved cases into `NetworkSolution` records.
- [ ] Capture topology, duties, temperatures, utility loads, areas, unit counts, TAC, `dQ/dA`, and method lineage needed for reporting.
- [ ] Convert verification failures into failed `TaskOutcome` records with reasons.
- [ ] Add tests for outcome serialization and failure records using fake solved cases.
- [ ] Ensure the new result objects are JSON-compatible.

## Review Criteria
- Solver defaults and mathematical behavior remain unchanged.
- `TaskOutcome` is useful without loading a pickle or importing GEKKO.
- Failure outcomes preserve enough context to diagnose missing solvers, infeasible models, and verification failures.
- Result extraction is covered by tests independent of expensive benchmark solves.

## Definition of Done
- Successful and failed task outcomes serialize to JSON-compatible dictionaries.
- Verification results are included in `TaskOutcome`.
- Existing model classes still solve with the same backend behavior under the new wrapper.

## Review Record
- Implementation agent: `019e1f8c-2b7c-7741-be54-bf6c7b90d8bf`
- Reviewer agents: `019e1f93-c017-7643-8d1a-c187c54f159b`, `019e1f98-f487-7411-bed1-73ca9b9d0f7b`
- Review date: 2026-05-13
- Initial verdict: FAIL
- Findings resolved:
  - Default `solve()` no longer writes pickled full problem objects; durable outcomes are retained as `workflow_result`, `task_outcomes`, and `network_solutions`.
  - `NetworkSolution` now includes non-isothermal match outlet temperatures from `T_h_out_x` and `T_c_out_y`.
  - Build/solve failure reasons preserve original error text where available.
  - Solver wrapper behavior is covered by fake-model tests for Pyomo and GEKKO solver options, success metadata, exception metadata, and non-success status metadata.
- Final verdict: PASS
- Blocking findings: none remaining
- Commands run after final fixes:
  - `uv run pytest openhens/tests/test_solvers.py -m "not solver"` passed with 5 tests.
  - `uv run pytest -m "not solver"` passed with 48 tests.
- Resolution: Step 4 accepted; proceed to Step 5.
