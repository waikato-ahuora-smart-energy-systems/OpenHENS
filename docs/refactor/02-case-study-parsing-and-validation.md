# Step 2: Case Study Parsing and Validation

## Goal
Move CSV reading and input validation into `CaseStudy` so model classes receive validated domain data instead of parsing files themselves.

## Scope
- Implement `CaseStudy.from_csv(path)`.
- Parse the current example CSV schema for process streams, utilities, and exchanger cost rows.
- Preserve support for optional temperature-contribution columns.
- Add strict validation for required rows, numeric fields, stream direction, utilities, and exchanger economics.
- Leave `StageWiseModel` and `PinchDecompModel` behavior unchanged except for using validated data through an adapter if required.

## Checklist
- [ ] Define Pydantic models for hot streams, cold streams, hot utility, cold utility, and exchanger economics.
- [ ] Add a CSV parser that detects the current semicolon-delimited workbook-export shape.
- [ ] Validate hot streams cool down and cold streams heat up.
- [ ] Validate heat capacity flow rates, heat-transfer coefficients, utility costs, and area cost parameters are present and non-negative where appropriate.
- [ ] Produce clear validation errors with row context.
- [ ] Add tests using at least the Four-stream and Nine-stream CSV files.
- [ ] Add negative tests for missing utilities, bad numeric values, impossible stream direction, and missing exchanger cost rows.
- [ ] Add a compatibility adapter so existing model constructors can still receive the arrays they expect.

## Review Criteria
- All currently tracked example CSV files either parse successfully or fail with an intentional documented reason.
- CSV parsing is no longer hidden inside `GenericHENModel.get_model_parameters_from_file()` for the new workflow.
- The parser does not silently default missing required values.
- Unit conventions are documented near the parser or public model fields.

## Definition of Done
- Fast tests cover successful parsing and validation failures.
- Four-stream and Nine-stream `CaseStudy.from_csv()` outputs include the same stream, utility, and cost data currently consumed by the solver.
- New validation messages identify the field and row or section that failed.

## Review Record
- Implementation agent: `019e1f68-d874-7c70-a023-d91559bc1357`
- Reviewer agents: `019e1f71-ef34-7283-986b-f9c8abfd6081`, `019e1f76-6ff4-7621-8d95-5ce372a737e1`
- Review date: 2026-05-13
- Initial verdict: PASS with one low compatibility caveat
- Finding resolved:
  - Legacy stream-name arrays originally trimmed trailing spaces from `Description` cells; this was fixed by preserving raw description text in the compatibility adapter.
- Final verdict: PASS
- Blocking findings: none
- Commands reported by reviewers:
  - `uv run pytest -m "not solver"` passed with 25 tests before follow-up changes.
  - `rtk .venv/bin/pytest -q` passed with 30 tests after follow-up changes.
- Resolution: Step 2 accepted; proceed to Step 3.
