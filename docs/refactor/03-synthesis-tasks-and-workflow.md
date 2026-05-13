# Step 3: Synthesis Tasks and Workflow

## Goal
Extract PDM -> TDM -> ESM orchestration into explicit workflow code that generates domain tasks from a `SynthesisStudy`.

## Scope
- Introduce `SynthesisTask` as the immutable description of one PDM, TDM, or ESM solve.
- Add workflow builders that generate PDM tasks from `DesignSpace`, TDM tasks from successful PDM outcomes, and ESM tasks from successful TDM outcomes.
- Preserve the current sequencing and filtering behavior.
- Keep execution local and equivalent to the current multiprocessing path.

## Checklist
- [x] Define `SynthesisTask` with stable task ID, method, parent task IDs, case reference, stage selection, solver choice, objective, restrictions, and numerical settings.
- [x] Add a workflow module that builds initial PDM tasks.
- [x] Add downstream task builders for TDM and ESM.
- [x] Preserve current defaults: PDM and TDM use `couenne`; ESM uses `ipopt-pyomo`; ESM uses non-isothermal NLP with evolution enabled.
- [x] Replace parent object handoff with explicit task lineage and extracted topology/restriction data.
- [x] Add a fake executor for workflow tests.
- [x] Test that failed PDM tasks do not produce TDM tasks and failed TDM tasks do not produce ESM tasks.
- [x] Test attempted-job counts against the current formula for representative design spaces.

## Review Criteria
- Orchestration no longer lives in `OpenHENS._get_optimal_network()`.
- `SynthesisTask` objects are serializable and reconstructible without GEKKO model objects.
- Task IDs are deterministic for the same study inputs.
- Workflow tests do not require installed solvers.

## Definition of Done
- Fast workflow tests prove stage ordering, dependency handling, and attempted-job counting.
- The `OpenHENS` facade delegates orchestration to the workflow module.
- No solver-heavy regression behavior is changed yet.

## Review Record
- Implementation agent: `019e1f79-cc54-75a1-8952-fab8e5c4f3e2`
- Reviewer agents: `019e1f81-cdb5-7fc3-8ea6-016e22acad40`, `019e1f86-0899-71f0-b383-73575fead00d`, `019e1f89-3228-7b50-a3ac-8e327b7029bf`
- Review date: 2026-05-13
- Initial verdicts: FAIL, FAIL
- Findings resolved:
  - Downstream tasks could originally be generated from successful upstream outcomes without durable topology/restriction data.
  - Local downstream task construction originally required a live parent `HeatExchangerNetworkProblem`; it now uses explicit `SynthesisTask.stages` and serialized restrictions.
  - A live-problem topology fallback helper was removed after the final reviewer noted it was unused and risky.
- Final verdict: PASS
- Blocking findings: none remaining
- Commands run after final fixes:
  - `uv run pytest openhens/tests/test_workflow.py -m "not solver"` passed with 10 tests.
  - `uv run pytest -m "not solver"` passed with 40 tests.
- Resolution: Step 3 accepted; proceed to Step 4.
