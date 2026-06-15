# Step 1: Project Baseline and Public API

## Goal
Establish the modern package baseline and introduce the public DDD-style entry objects without changing solver behavior.

## Scope
- Add `pyproject.toml` managed with `uv`, including current runtime dependencies, `pydantic v2`, and pytest marker configuration.
- Remove `requirements.txt` and `setup.py`; `pyproject.toml` and `uv.lock` become the only supported package/dependency metadata.
- Introduce public Pydantic models: `SynthesisStudy`, `DesignSpace`, `MethodSequence`, `SolveSetup`, and `StudyOutputs`.
- Keep `CaseStudy` as a shell type in this step; full CSV parsing happens in Step 2.
- Update `openhens.__init__` to export the new public API.
- Keep `OpenHENS` as the facade, accepting `SynthesisStudy`.

## Checklist
- [ ] Add `pyproject.toml` with package metadata, dependencies, pytest config, and solver regression marker.
- [ ] Generate `uv.lock`.
- [ ] Delete `requirements.txt` and `setup.py`.
- [ ] Add a module for public domain entry objects.
- [ ] Implement validation for design grids, stage selection, solver names, output formats, and positive tolerances.
- [ ] Add `MethodSequence.standard_pdm_tdm_esm()`.
- [ ] Add `SolveSetup.local()` defaults matching current behavior.
- [ ] Add `StudyOutputs` defaults for JSON and CSV outputs, with Excel and plots disabled by default.
- [ ] Update `OpenHENS` construction to accept `SynthesisStudy`.
- [ ] Add unit tests for model construction and validation failures.

## Review Criteria
- Public names match the agreed vocabulary: `SynthesisStudy`, `CaseStudy`, `DesignSpace`, `MethodSequence`, `SolveSetup`, `StudyOutputs`, `StudyOutcome`, `SolutionPortfolio`, `NetworkSolution`, and `StudyManifest`.
- Dependency and package metadata live only in `pyproject.toml` and `uv.lock`.
- No mathematical model construction or solver defaults change in this step.
- Validation errors are clear enough for engineering users to fix invalid inputs.
- The old mutable `OpenHensOptions` no longer drives the preferred API.

## Definition of Done
- `uv run pytest -m "not solver"` passes for the new API tests.
- `from openhens import SynthesisStudy, CaseStudy, DesignSpace, MethodSequence, SolveSetup, StudyOutputs, OpenHENS` works.
- A minimal `SynthesisStudy` can be constructed and passed to `OpenHENS` without starting a solve.
- README installation notes mention `uv` as the preferred path.

## Review Record
- Implementation agent: `019e1f60-77d9-7712-a1d3-90441ba40d7b`
- Reviewer agent: `019e1f65-d1fa-7550-8ceb-79fbf2b5da81`
- Review date: 2026-05-13
- Verdict: PASS
- Blocking findings: none
- Commands reported by reviewer:
  - `uv run pytest -m "not solver"` passed with 15 tests.
  - `uv lock --check` passed.
  - Public API import smoke test passed.
- Resolution: Step 1 accepted; proceed to Step 2.
