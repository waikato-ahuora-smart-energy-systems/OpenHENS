from openhens.solvers import configure_gekko_solver, solve_gekko_model


class FakeOptions:
    SOLVER_EXTENSION = None
    SOLVER = None
    MAX_ITER = None
    RTOL = None
    OTOL = None
    SOLVESTATUS = 1
    objfcnval = 42.0


class FakeModel:
    def __init__(self) -> None:
        self.options = FakeOptions()
        self.solver_options = []
        self.solve_calls = []

    def solve(self, *, disp, debug):
        self.solve_calls.append({"disp": disp, "debug": debug})


class FakeSolverFactory:
    def __init__(self, name: str) -> None:
        self.name = name

    def available(self):
        return True


def test_configure_pyomo_solvers_preserves_legacy_extension(monkeypatch) -> None:
    requested = []

    def fake_solver_factory(name: str):
        requested.append(name)
        return FakeSolverFactory(name)

    monkeypatch.setattr("openhens.solvers.SolverFactory", fake_solver_factory)

    couenne_model = FakeModel()
    couenne_run = configure_gekko_solver(couenne_model, "couenne")

    assert couenne_model.options.SOLVER_EXTENSION == "pyomo"
    assert couenne_model.options.SOLVER == "couenne"
    assert couenne_run.name == "couenne"
    assert couenne_run.extension == "pyomo"

    ipopt_model = FakeModel()
    configure_gekko_solver(ipopt_model, "ipopt-pyomo")

    assert ipopt_model.options.SOLVER_EXTENSION == "pyomo"
    assert ipopt_model.options.SOLVER == "ipopt"
    assert requested == ["couenne", "ipopt"]


def test_configure_gekko_solvers_preserves_legacy_options() -> None:
    apopt_model = FakeModel()
    apopt_run = configure_gekko_solver(apopt_model, "apopt")

    assert apopt_model.options.SOLVER_EXTENSION == 0
    assert apopt_model.options.SOLVER == "apopt"
    assert apopt_model.options.MAX_ITER == 1000
    assert apopt_model.options.RTOL == 1e-2
    assert apopt_model.options.OTOL == 1e-2
    assert apopt_run.extension == 0

    ipopt_model = FakeModel()
    configure_gekko_solver(ipopt_model, "ipopt-GEKKO")

    assert ipopt_model.options.SOLVER_EXTENSION == 0
    assert ipopt_model.options.SOLVER == "ipopt"
    assert "tol 1e-3" in ipopt_model.solver_options
    assert "max_iter 1000" in ipopt_model.solver_options


def test_solve_gekko_model_records_success_metadata() -> None:
    model = FakeModel()
    model.options.SOLVER_EXTENSION = "pyomo"

    run = solve_gekko_model(model, solver_name="couenne", disp=False, debug=0)

    assert model.solve_calls == [{"disp": False, "debug": 0}]
    assert run.name == "couenne"
    assert run.extension == "pyomo"
    assert run.status == 1
    assert run.objective_value == 42.0
    assert run.failure_reason is None
    assert run.solve_time is not None


def test_solve_gekko_model_records_failure_metadata() -> None:
    class FailingModel(FakeModel):
        def solve(self, *, disp, debug):
            raise RuntimeError("solver exploded")

    run = solve_gekko_model(FailingModel(), solver_name="apopt")

    assert run.name == "apopt"
    assert run.failure_reason == "solver exploded"


def test_solve_gekko_model_records_non_success_status() -> None:
    model = FakeModel()
    model.options.SOLVESTATUS = 0

    run = solve_gekko_model(model, solver_name="couenne")

    assert run.status == 0
    assert run.failure_reason == "solver status 0"
