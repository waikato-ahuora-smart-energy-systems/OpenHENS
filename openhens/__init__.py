from .domain import (
    CaseStudy,
    ColdStream,
    ColdUtility,
    DesignSpace,
    ExchangerEconomics,
    HotStream,
    HotUtility,
    MethodSequence,
    NetworkSolution,
    SolutionPortfolio,
    SolveSetup,
    SolverRun,
    SynthesisTask,
    TaskOutcome,
    StudyManifest,
    StudyOutcome,
    StudyOutputs,
    TaskNumericalSettings,
    TaskRestrictions,
    SynthesisStudy,
)

__all__ = [
    "OpenHENS",
    "SynthesisStudy",
    "CaseStudy",
    "HotStream",
    "ColdStream",
    "HotUtility",
    "ColdUtility",
    "ExchangerEconomics",
    "DesignSpace",
    "MethodSequence",
    "SolveSetup",
    "StudyOutputs",
    "SynthesisTask",
    "TaskOutcome",
    "SolverRun",
    "TaskNumericalSettings",
    "TaskRestrictions",
    "StudyOutcome",
    "SolutionPortfolio",
    "NetworkSolution",
    "StudyManifest",
]


def __getattr__(name: str):
    if name == "OpenHENS":
        from .main import OpenHENS

        return OpenHENS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
