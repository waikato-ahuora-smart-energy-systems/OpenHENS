'''
__author__ = 'Keegan Hall and Tim Walmsley'
__credits__ = ['tbc']

Simultaneous synthesis, design and optimization followed by network evolution
for process heat exchanger networks given input data
'''

from .artifacts import write_study_artifacts
from .domain import CaseStudy, DesignSpace, MethodSequence, NetworkSolution, SolveSetup, StudyOutcome, StudyOutputs, SynthesisStudy
from .classes import HeatExchangerNetworkProblem
from .workflow import run_synthesis_workflow
import matplotlib.pyplot as plt
from pathlib import Path


from openhens.logger import openhens_log as logger, add_handler
import logging
import sys


class OpenHensOptions:
    """Legacy keyword-option container kept as the facade's compatibility layer.

    New code should prefer ``SynthesisStudy``. The facade still normalizes both
    entry styles through this object so the rest of the solve path can share one
    set of option names while the refactor is in progress.
    """

    def __init__(self, **kwargs) -> None:
        # default options
        self.input_folder: str = f'examples/cases/Four-stream-Yee-and-Grossmann-1990-1.csv'
        self.output_folder: str = f'examples/results/Four-stream-Yee-and-Grossmann-1990-1'
        self.min_dT_list: list[float] = [2, 4, 6, 8, 10, 12, 14, 16, 18, 20,]
        self.min_dqda_list: list[float] = [0.5, 0.9, 1.3, 1.7, 2.1, 2.4, 2.8, 3.2, 3.6, 4.0]
        self.stage_selection: str | list[float] = 'automated'
        self.tolerance: float = 1e-3
        self.max_parallel: int = SolveSetup.local().max_parallel
        self.best_solns_to_save: int = 10
        self.log_level: int = logging.WARNING
        
        # update options with kwargs passed in
        for k, v in kwargs.items():
            setattr(self, k, v)

class OpenHENS:
    """Facade for running a heat-exchanger-network synthesis study.

    The preferred entry point is ``OpenHENS(SynthesisStudy(...)).solve()``. The
    legacy ``OpenHENS(**options)`` path remains supported by converting options
    into the same domain objects used by the new workflow.
    """

    def __init__(self, study: SynthesisStudy | CaseStudy | None = None, **options) -> None:
        """
        - study: public SynthesisStudy entry object.
        - options: legacy keyword options for solving the problem (see OpenHensOptions).
        """
        if study is not None and options:
            raise ValueError("Pass either a SynthesisStudy or legacy OpenHENS options, not both.")

        self.study = self._coerce_study(study)
        if self.study is None:
            self.options = OpenHensOptions(**options)
        else:
            self.options = self._options_from_study(self.study)
    
        self.set_log_level(self.options.log_level)

    def _coerce_study(self, study: SynthesisStudy | CaseStudy | None) -> SynthesisStudy | None:
        """Accept the public aggregate or a bare case shell at the facade edge."""

        if study is None:
            return None
        if isinstance(study, SynthesisStudy):
            return study
        if isinstance(study, CaseStudy):
            return SynthesisStudy(case=study)
        raise TypeError("study must be a SynthesisStudy, CaseStudy, or None")

    def _options_from_study(self, study: SynthesisStudy) -> OpenHensOptions:
        """Map the DDD-style public API to the legacy option names.

        The legacy model constructors still expect ``min_dT_list`` and
        ``min_dqda_list``. Keeping that translation here prevents those names
        from leaking back into the public ``SynthesisStudy`` API.
        """

        stage_selection = study.design_space.stage_selection
        if stage_selection != "automated":
            stage_selection = list(stage_selection)

        return OpenHensOptions(
            input_folder=study.case.source,
            output_folder=study.outputs.folder,
            min_dT_list=list(study.design_space.approach_temperatures),
            min_dqda_list=list(study.design_space.derivative_thresholds),
            stage_selection=stage_selection,
            tolerance=study.solving.tolerance,
            max_parallel=study.solving.max_parallel,
            best_solns_to_save=study.outputs.best_solutions_to_save,
            log_level=study.solving.log_level,
        )
      
    def set_log_level(self, level: int) -> None:
        """Apply a facade-level log level to existing or lazily-created handlers."""

        logger.setLevel(level)

        if not logger.handlers:
            stream_handler = logging.StreamHandler(sys.stdout)
            add_handler(stream_handler, level)
        else:
            for h in logger.handlers:
                h.setLevel(level)  # <- override even fallback INFO level
        
    def solve(self) -> StudyOutcome:
        """Run the supported standard workflow and return durable study results.

        Phase one only wires the canonical PDM -> TDM -> ESM sequence with the
        default solver choices. Other ``MethodSequence`` values are valid data
        models, but execution support is intentionally deferred.
        """

        if self.study is not None and self.study.methods != MethodSequence.standard_pdm_tdm_esm():
            raise NotImplementedError(
                "Custom method sequences and solver choices will be wired into solve in a later refactor step."
            )

        self._problem_file = Path(self.options.input_folder)
        self._output_folder = Path(self.options.output_folder)
        self._output_folder.mkdir(parents=True, exist_ok=True)
        
        self.solutions = self._get_optimal_network(
            problem_file = self._problem_file, 
            min_dqda_list = self.options.min_dqda_list,
            min_dT_list = self.options.min_dT_list,
            stage_selection = self.options.stage_selection
        )

        self._best_solns = self._best_legacy_problems_by_TAC(self.solutions, self.options.best_solns_to_save)
        self._best_network_solutions = self._best_network_solutions_by_TAC(
            self.network_solutions,
            self.options.best_solns_to_save,
        )
        return self.study_outcome
    

    def display_run_metrics(self) -> None:
        """Log paths to the current run's metrics artifacts.

        Reporting now consumes the CSV artifacts written by ``solve()``. This
        method intentionally does not regenerate Excel files or plots; those are
        controlled by ``StudyOutputs`` during artifact writing.
        """

        if not hasattr(self, "study_outcome") or not hasattr(self, "_run_folder"):
            logger.warning("No study artifacts are loaded; run solve() before displaying run metrics")
            return

        manifest = self.study_outcome.manifest
        metrics_path = self._run_folder / manifest.solution_metrics_path
        summary_path = self._run_folder / manifest.run_summary_path
        if metrics_path.exists():
            logger.warning(f"Solution metrics: {metrics_path}")
        else:
            logger.warning(f"Solution metrics artifact missing: {metrics_path}")
        if summary_path.exists():
            logger.warning(f"Run summary: {summary_path}")
        else:
            logger.warning(f"Run summary artifact missing: {summary_path}")
        
    def display_best_from_run(self) -> None:
        """Render the best legacy in-memory problem from the current solve."""

        if len(self._best_solns) == 0:
            logger.warning("No solutions found, skipping display best from run")
            return
        logger.warning(f"best from current solve {self._best_solns[0].name} {self._best_solns[0].case.TAC}")
        self._best_solns[0].get_grid_diagram()
        plt.show()


    def display_n_best_from_file(self, n_best: int = 1) -> None:
        """Log the nth-best solution available in loaded durable artifacts."""

        if not hasattr(self, "study_outcome"):
            logger.warning("No study outcome is loaded; run solve() or load artifacts first")
            return
        ranked = sorted(
            (
                solution
                for solution in self.study_outcome.solutions.solutions
                if solution.total_annual_cost is not None
            ),
            key=lambda solution: solution.total_annual_cost,
        )
        if len(ranked) < n_best:
            logger.warning(f"No artifact solution ranked {n_best}")
            return
        best = ranked[n_best - 1]
        logger.warning(f"{n_best} best from artifacts {best.name} {best.total_annual_cost}")

    def _get_optimal_network(
            self, 
            problem_file,
            min_dqda_list,
            min_dT_list,
            stage_selection, 
        ) -> list[HeatExchangerNetworkProblem]:
        """
        Build and solve the standard PDM -> TDM -> ESM workflow.

        This method now delegates orchestration to ``run_synthesis_workflow`` and
        then keeps the historic ``self.solutions``/``self._best_solns`` shape for
        callers that still inspect in-memory model objects.
        """

        study = self.study or self._study_from_legacy_options(
            problem_file=problem_file,
            min_dqda_list=min_dqda_list,
            min_dT_list=min_dT_list,
            stage_selection=stage_selection,
        )
        workflow_result = run_synthesis_workflow(study, print_output=False)
        self.workflow_result = workflow_result
        self.task_outcomes = workflow_result.outcomes
        self.network_solutions = [
            outcome.solution for outcome in workflow_result.outcomes if outcome.success and outcome.solution is not None
        ]
        combined_solutions = workflow_result.successful_problems
        self.study_outcome = write_study_artifacts(
            study,
            workflow_result.outcomes,
            total_run_time_seconds=workflow_result.total_run_time,
            attempted_solver_jobs=workflow_result.attempted_solver_jobs,
            outputs=study.outputs,
        )
        self._run_folder = study.outputs.folder / self.study_outcome.manifest.run_id

        if len(combined_solutions) == 0:
            logger.warning("No solutions found")
            return []

        return combined_solutions

    def _best_network_solutions_by_TAC(
        self,
        solutions: list[NetworkSolution],
        n_best: int,
    ) -> list[NetworkSolution]:
        """Rank durable network records by total annual cost."""

        ranked = sorted(
            (solution for solution in solutions if solution.total_annual_cost is not None),
            key=lambda solution: solution.total_annual_cost,
        )
        return ranked[:n_best] if n_best > 0 else ranked

    def _best_legacy_problems_by_TAC(
        self,
        solutions: list[HeatExchangerNetworkProblem],
        n_best: int,
    ) -> list[HeatExchangerNetworkProblem]:
        """Rank legacy solved problem objects by total annual cost."""

        ranked = sorted(solutions, key=lambda solution: solution.case.TAC)
        return ranked[:n_best] if n_best > 0 else ranked

    def _study_from_legacy_options(
        self,
        problem_file,
        min_dqda_list,
        min_dT_list,
        stage_selection,
    ) -> SynthesisStudy:
        """Construct a public study aggregate from legacy facade options."""

        if stage_selection != "automated":
            stage_selection = tuple(stage_selection)

        return SynthesisStudy(
            case=CaseStudy(source=Path(problem_file)),
            design_space=DesignSpace(
                approach_temperatures=tuple(min_dT_list),
                derivative_thresholds=tuple(min_dqda_list),
                stage_selection=stage_selection,
            ),
            methods=MethodSequence.standard_pdm_tdm_esm(),
            solving=SolveSetup.local(
                tolerance=self.options.tolerance,
                max_parallel=self.options.max_parallel,
                log_level=self.options.log_level,
            ),
            outputs=StudyOutputs(folder=Path(self.options.output_folder)),
        )
