"""Shared solver setup and run metadata helpers."""

from __future__ import annotations

import time
from typing import Any

from pyomo.environ import SolverFactory

from .domain import SolverRun


PYOMO_SOLVERS = {"couenne", "ipopt-pyomo"}
GEKKO_SOLVERS = {"ipopt-GEKKO", "apopt"}


def configure_gekko_solver(model: Any, solver_name: str) -> SolverRun:
    """Apply the legacy GEKKO/Pyomo solver options to a model."""

    if solver_name in PYOMO_SOLVERS:
        extension: str | int | None = "pyomo"
    elif solver_name in GEKKO_SOLVERS:
        extension = 0
    else:
        extension = getattr(model.options, "SOLVER_EXTENSION", None)

    model.options.SOLVER_EXTENSION = extension
    model.options.SOLVER = solver_name.split("-")[0]

    if solver_name == "ipopt-GEKKO":
        model.solver_options = [
            "tol 1e-3",
            "acceptable_tol 1e-2",
            "constr_viol_tol 1e-2",
            "acceptable_constr_viol_tol 1e-1",
            "compl_inf_tol 1e-2",
            "max_iter 1000",
            "print_level 5",
        ]

    if solver_name == "apopt":
        model.options.MAX_ITER = 1000
        model.options.RTOL = 1e-2
        model.options.OTOL = 1e-2

    if model.options.SOLVER_EXTENSION == "pyomo":
        SolverFactory(model.options.SOLVER).available()

    return SolverRun(name=solver_name, extension=extension)


def solve_gekko_model(
    model: Any,
    *,
    solver_name: str,
    disp: bool = False,
    debug: int = 0,
) -> SolverRun:
    """Run GEKKO solve and return JSON-compatible metadata."""

    extension = getattr(model.options, "SOLVER_EXTENSION", None)
    start = time.time()
    failure_reason = None
    try:
        model.solve(disp=disp, debug=debug)
    except Exception as exc:  # GEKKO/Pyomo exceptions are converted to outcome metadata.
        failure_reason = str(exc) or exc.__class__.__name__
    solve_time = time.time() - start

    status = getattr(model.options, "SOLVESTATUS", None)
    objective_value = getattr(model.options, "objfcnval", None)
    if failure_reason is None and status != 1:
        failure_reason = f"solver status {status}"

    return SolverRun(
        name=solver_name,
        extension=extension,
        status=status,
        objective_value=_as_float_or_none(objective_value),
        solve_time=solve_time,
        failure_reason=failure_reason,
    )


def _as_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
