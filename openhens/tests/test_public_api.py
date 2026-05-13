from pathlib import Path

import pytest
from pydantic import ValidationError

from openhens import (
    CaseStudy,
    DesignSpace,
    MethodSequence,
    OpenHENS,
    SolveSetup,
    StudyOutputs,
    SynthesisStudy,
)


def test_public_study_can_construct_facade_without_solving() -> None:
    case = CaseStudy.from_csv("examples/cases/Four-stream-Yee-and-Grossmann-1990-1.csv")
    study = SynthesisStudy(case=case)

    model = OpenHENS(study)

    assert model.study == study
    assert model.options.input_folder == Path("examples/cases/Four-stream-Yee-and-Grossmann-1990-1.csv")
    assert model.options.min_dT_list == [2, 4, 6, 8, 10, 12, 14, 16, 18, 20]
    assert model.options.min_dqda_list == [0.5, 0.9, 1.3, 1.7, 2.1, 2.4, 2.8, 3.2, 3.6, 4.0]
    assert model.options.stage_selection == "automated"
    assert model.options.tolerance == 1e-3
    assert model.options.max_parallel == 10
    assert model.options.best_solns_to_save == 10


def test_case_study_shell_can_be_passed_directly_to_facade() -> None:
    model = OpenHENS(CaseStudy(source=Path("case.csv"), name="Example"))

    assert isinstance(model.study, SynthesisStudy)
    assert model.study.name == "Example"
    assert model.options.input_folder == Path("case.csv")


def test_custom_design_space_maps_to_legacy_options() -> None:
    study = SynthesisStudy(
        case=CaseStudy(source=Path("case.csv")),
        design_space=DesignSpace(
            approach_temperatures=(10,),
            derivative_thresholds=(1.0, 2.0),
            stage_selection=(2, 3),
        ),
        solving=SolveSetup(tolerance=1e-4, max_parallel=2),
        outputs=StudyOutputs(folder=Path("results"), best_solutions_to_save=3),
    )

    model = OpenHENS(study)

    assert model.options.min_dT_list == [10]
    assert model.options.min_dqda_list == [1.0, 2.0]
    assert model.options.stage_selection == [2, 3]
    assert model.options.tolerance == 1e-4
    assert model.options.max_parallel == 2
    assert model.options.output_folder == Path("results")
    assert model.options.best_solns_to_save == 3


@pytest.mark.parametrize(
    ("model", "kwargs"),
    [
        (DesignSpace, {"min_dT_values": ()}),
        (DesignSpace, {"min_dT_values": (-1,)}),
        (DesignSpace, {"min_dqda_values": (0,)}),
        (DesignSpace, {"approach_temperatures": ()}),
        (DesignSpace, {"derivative_thresholds": (0,)}),
        (DesignSpace, {"stage_selection": (1,)}),
        (DesignSpace, {"stage_selection": (1, -1)}),
        (MethodSequence, {"pdm_solver": "not-a-solver"}),
        (StudyOutputs, {"output_formats": ("xml",)}),
        (StudyOutputs, {"output_formats": ()}),
        (StudyOutputs, {"formats": ("xml",)}),
        (StudyOutputs, {"formats": ()}),
        (StudyOutputs, {"best_solutions_to_save": 0}),
        (SolveSetup, {"tolerance": 0}),
        (SolveSetup, {"max_parallel": 0}),
    ],
)
def test_public_models_reject_invalid_values(model: type, kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        model(**kwargs)


def test_facade_rejects_study_and_legacy_options_together() -> None:
    with pytest.raises(ValueError, match="either a SynthesisStudy or legacy OpenHENS options"):
        OpenHENS(SynthesisStudy(case=CaseStudy(source=Path("case.csv"))), input_folder="other.csv")


def test_public_api_names_match_refactor_plan() -> None:
    study = SynthesisStudy(
        case=CaseStudy(source=Path("case.csv")),
        design_space=DesignSpace(
            approach_temperatures=[2, 4],
            derivative_thresholds=[0.5, 1.0],
            stage_selection="automated",
        ),
        methods=MethodSequence.standard_pdm_tdm_esm(),
        solving=SolveSetup.local(tolerance=1e-3, max_parallel=10),
        outputs=StudyOutputs(
            folder=Path("results"),
            formats=["json", "csv"],
            include_excel=False,
            include_plots=False,
        ),
    )

    assert study.design_space.approach_temperatures == (2, 4)
    assert study.design_space.derivative_thresholds == (0.5, 1.0)
    assert study.solving.max_parallel == 10
    assert study.outputs.folder == Path("results")
    assert study.outputs.formats == ("json", "csv")
