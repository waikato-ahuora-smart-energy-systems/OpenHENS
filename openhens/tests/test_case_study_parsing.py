from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from openhens import CaseStudy


FOUR_STREAM_CASE = Path("examples/cases/Four-stream-Yee-and-Grossmann-1990-1.csv")
NINE_STREAM_CASE = Path("examples/cases/Nine-stream-Linnhoff-and-Ahmad-1999-1.csv")
TEMPERATURE_CONTRIBUTION_CASE = Path("examples/cases/Fifteen-stream-Walmsley-et-al-2022-1.csv")


def test_four_stream_case_parses_to_solver_arrays() -> None:
    case = CaseStudy.from_csv(FOUR_STREAM_CASE)
    arrays = case.to_legacy_arrays(dTmin=10)

    assert len(case.hot_streams) == 2
    assert len(case.cold_streams) == 2
    assert len(case.hot_utilities) == 1
    assert len(case.cold_utilities) == 1
    np.testing.assert_allclose(arrays["T_h_in"], [650, 590])
    np.testing.assert_allclose(arrays["T_h_out"], [370, 370])
    np.testing.assert_allclose(arrays["f_h"], [10, 20])
    np.testing.assert_allclose(arrays["T_c_in"], [410, 350])
    np.testing.assert_allclose(arrays["T_c_out"], [650, 500])
    np.testing.assert_allclose(arrays["f_c"], [15, 13])
    np.testing.assert_allclose(arrays["T_hu_in"], [680])
    np.testing.assert_allclose(arrays["T_cu_out"], [320])
    np.testing.assert_allclose(arrays["unit_cost"], [5500])
    np.testing.assert_allclose(arrays["hu_unit_cost"], [5500])
    np.testing.assert_allclose(arrays["cu_unit_cost"], [5500])
    np.testing.assert_allclose(arrays["T_h_cont"], [5, 5])
    assert arrays["hot_names"].tolist() == ["Raw Milk ", "HT Flash"]


def test_nine_stream_comma_export_parses() -> None:
    case = CaseStudy.from_csv(NINE_STREAM_CASE)
    arrays = case.to_legacy_arrays(dTmin=20)

    assert len(case.hot_streams) == 4
    assert len(case.cold_streams) == 5
    np.testing.assert_allclose(arrays["T_h_in"][:2], [600.15, 493.15])
    np.testing.assert_allclose(arrays["T_c_out"][-1:], [573.15])
    np.testing.assert_allclose(arrays["hu_cost"], [60])
    np.testing.assert_allclose(arrays["cu_cost"], [6])
    np.testing.assert_allclose(arrays["A_coeff"], [70])
    np.testing.assert_allclose(arrays["T_c_cont"], [10, 10, 10, 10, 10])


def test_optional_temperature_contribution_column_is_preserved() -> None:
    case = CaseStudy.from_csv(TEMPERATURE_CONTRIBUTION_CASE)
    arrays = case.to_legacy_arrays(dTmin=20)

    assert case.hot_streams[0].temperature_contribution == 0.5
    assert case.cold_streams[0].temperature_contribution == 2.5
    np.testing.assert_allclose(arrays["T_h_cont"], [stream.temperature_contribution for stream in case.hot_streams])
    np.testing.assert_allclose(arrays["T_c_cont"], [stream.temperature_contribution for stream in case.cold_streams])


def test_all_tracked_example_cases_parse_successfully() -> None:
    for path in sorted(Path("examples/cases").glob("*.csv")):
        CaseStudy.from_csv(path)


@pytest.mark.parametrize(
    ("replacement", "match"),
    [
        ("1;Process A;Raw Milk ;Hot;650;370;not-a-number;1;0", "row 4: Flow heat capacity must be numeric"),
        ("1;Process A;Raw Milk ;Hot;650;700;10;1;0", "row 4: hot stream must cool down"),
        ("1;Utility;HPS;Hot Utility;680;680;;5;-80", "row 8: Stream cost must be non-negative"),
        ("1;Process A;Process-process HX;Exchange;5500;-150;1;;", "row 14: HX area coefficient"),
    ],
)
def test_case_study_rejects_bad_values(tmp_path: Path, replacement: str, match: str) -> None:
    source_text = FOUR_STREAM_CASE.read_text()
    original = _line_with(source_text, replacement.split(";", maxsplit=4)[3])
    path = _write_case(tmp_path, source_text.replace(original, replacement))

    with pytest.raises((ValueError, ValidationError), match=match):
        CaseStudy.from_csv(path)


def test_case_study_requires_hot_utility(tmp_path: Path) -> None:
    source_text = "\n".join(
        line for line in FOUR_STREAM_CASE.read_text().splitlines() if "Hot Utility" not in line
    )
    path = _write_case(tmp_path, source_text)

    with pytest.raises(ValueError, match="utilities section: missing required Hot Utility row"):
        CaseStudy.from_csv(path)


def test_case_study_requires_exchanger_cost_rows(tmp_path: Path) -> None:
    source_text = "\n".join(
        line for line in FOUR_STREAM_CASE.read_text().splitlines() if ";Exchange;" not in line
    )
    path = _write_case(tmp_path, source_text)

    with pytest.raises(ValueError, match="exchanger economics section: missing required Exchange row"):
        CaseStudy.from_csv(path)


def _write_case(tmp_path: Path, source_text: str) -> Path:
    path = tmp_path / "case.csv"
    path.write_text(source_text)
    return path


def _line_with(source_text: str, designation: str) -> str:
    for line in source_text.splitlines():
        if f";{designation};" in line:
            return line
    raise AssertionError(f"could not find row with designation {designation!r}")
