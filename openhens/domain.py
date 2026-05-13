"""Public domain entry objects for OpenHENS studies."""

from __future__ import annotations

import csv
import logging
import math
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


SolverName = Literal["couenne", "ipopt-pyomo", "apopt", "ipopt-GEKKO"]
MethodName = Literal["PDM", "TDM", "ESM"]
OutputFormat = Literal["json", "csv", "xlsx", "png", "html"]
StageSelection = Literal["automated"] | tuple[int, int]
ExchangerKind = Literal["exchange", "heating", "cooling"]
TaskObjective = Literal["hot utility", "variable total cost"]


class OpenHENSModel(BaseModel):
    """Shared Pydantic configuration for public OpenHENS models."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class HotStream(OpenHENSModel):
    """Validated hot process stream.

    CSV units follow the workbook export columns: temperatures in K, heat
    capacity flow rate in kW/K, film coefficient in kW/m2-K, and stream cost in
    $/kW-y. ``temperature_contribution`` is optional and defaults in the legacy
    adapter to ``dTmin / 2`` when absent.
    """

    source_row: int = Field(ge=1)
    number: str
    subsystem: str
    name: str
    supply_temperature: float
    target_temperature: float
    heat_capacity_flowrate: float
    heat_transfer_coefficient: float
    cost: float
    temperature_contribution: float | None = None

    @model_validator(mode="after")
    def validate_hot_stream(self) -> "HotStream":
        _validate_finite_fields(
            self,
            "supply_temperature",
            "target_temperature",
            "heat_capacity_flowrate",
            "heat_transfer_coefficient",
            "cost",
            "temperature_contribution",
        )
        if self.supply_temperature <= self.target_temperature:
            raise ValueError(
                f"process streams row {self.source_row}: hot stream must cool down "
                "(Supply Temp must be greater than Target Temp)"
            )
        if self.heat_capacity_flowrate <= 0:
            raise ValueError(f"process streams row {self.source_row}: Flow heat capacity must be positive")
        if self.heat_transfer_coefficient <= 0:
            raise ValueError(f"process streams row {self.source_row}: HTC must be positive")
        if self.cost < 0:
            raise ValueError(f"process streams row {self.source_row}: Stream cost must be non-negative")
        if self.temperature_contribution is not None and self.temperature_contribution < 0:
            raise ValueError(f"process streams row {self.source_row}: T cont must be non-negative")
        return self


class ColdStream(OpenHENSModel):
    """Validated cold process stream with the same units as :class:`HotStream`."""

    source_row: int = Field(ge=1)
    number: str
    subsystem: str
    name: str
    supply_temperature: float
    target_temperature: float
    heat_capacity_flowrate: float
    heat_transfer_coefficient: float
    cost: float
    temperature_contribution: float | None = None

    @model_validator(mode="after")
    def validate_cold_stream(self) -> "ColdStream":
        _validate_finite_fields(
            self,
            "supply_temperature",
            "target_temperature",
            "heat_capacity_flowrate",
            "heat_transfer_coefficient",
            "cost",
            "temperature_contribution",
        )
        if self.target_temperature <= self.supply_temperature:
            raise ValueError(
                f"process streams row {self.source_row}: cold stream must heat up "
                "(Target Temp must be greater than Supply Temp)"
            )
        if self.heat_capacity_flowrate <= 0:
            raise ValueError(f"process streams row {self.source_row}: Flow heat capacity must be positive")
        if self.heat_transfer_coefficient <= 0:
            raise ValueError(f"process streams row {self.source_row}: HTC must be positive")
        if self.cost < 0:
            raise ValueError(f"process streams row {self.source_row}: Stream cost must be non-negative")
        if self.temperature_contribution is not None and self.temperature_contribution < 0:
            raise ValueError(f"process streams row {self.source_row}: T cont must be non-negative")
        return self


class HotUtility(OpenHENSModel):
    """Validated hot utility stream.

    Temperatures are in K, HTC is kW/m2-K, and cost is $/kW-y.
    """

    source_row: int = Field(ge=1)
    number: str
    subsystem: str
    name: str
    supply_temperature: float
    target_temperature: float
    heat_transfer_coefficient: float
    cost: float

    @model_validator(mode="after")
    def validate_hot_utility(self) -> "HotUtility":
        _validate_finite_fields(
            self,
            "supply_temperature",
            "target_temperature",
            "heat_transfer_coefficient",
            "cost",
        )
        if self.supply_temperature < self.target_temperature:
            raise ValueError(
                f"utilities row {self.source_row}: hot utility Supply Temp must be greater than "
                "or equal to Target Temp"
            )
        if self.heat_transfer_coefficient <= 0:
            raise ValueError(f"utilities row {self.source_row}: HTC must be positive")
        if self.cost < 0:
            raise ValueError(f"utilities row {self.source_row}: Stream cost must be non-negative")
        return self


class ColdUtility(OpenHENSModel):
    """Validated cold utility stream with the same units as :class:`HotUtility`."""

    source_row: int = Field(ge=1)
    number: str
    subsystem: str
    name: str
    supply_temperature: float
    target_temperature: float
    heat_transfer_coefficient: float
    cost: float

    @model_validator(mode="after")
    def validate_cold_utility(self) -> "ColdUtility":
        _validate_finite_fields(
            self,
            "supply_temperature",
            "target_temperature",
            "heat_transfer_coefficient",
            "cost",
        )
        if self.target_temperature < self.supply_temperature:
            raise ValueError(
                f"utilities row {self.source_row}: cold utility Target Temp must be greater than "
                "or equal to Supply Temp"
            )
        if self.heat_transfer_coefficient <= 0:
            raise ValueError(f"utilities row {self.source_row}: HTC must be positive")
        if self.cost < 0:
            raise ValueError(f"utilities row {self.source_row}: Stream cost must be non-negative")
        return self


class ExchangerEconomics(OpenHENSModel):
    """Validated exchanger area-cost row.

    Fixed unit cost is in $/y, area coefficient is in $/m2-y, and the area
    exponent is dimensionless.
    """

    source_row: int = Field(ge=1)
    kind: ExchangerKind
    number: str
    subsystem: str
    name: str
    unit_cost: float
    area_coefficient: float
    area_exponent: float

    @model_validator(mode="after")
    def validate_economics(self) -> "ExchangerEconomics":
        _validate_finite_fields(self, "unit_cost", "area_coefficient", "area_exponent")
        if self.unit_cost < 0:
            raise ValueError(f"exchanger economics row {self.source_row}: HX unit cost must be non-negative")
        if self.area_coefficient < 0:
            raise ValueError(
                f"exchanger economics row {self.source_row}: HX area coefficient must be non-negative"
            )
        if self.area_exponent < 0:
            raise ValueError(f"exchanger economics row {self.source_row}: HX area exponent must be non-negative")
        return self


class CaseStudy(OpenHENSModel):
    """Case-study input shell, optionally populated with validated CSV rows.

    Use ``CaseStudy.from_csv(...)`` when code needs row-level validation or the
    typed stream/utility/economics models. ``CaseStudy(source=...)`` is also
    accepted as a path-only compatibility shell for solve paths that still let
    the legacy model loader read the CSV directly.
    """

    source: Path
    name: str | None = None
    hot_streams: tuple[HotStream, ...] = ()
    cold_streams: tuple[ColdStream, ...] = ()
    hot_utilities: tuple[HotUtility, ...] = ()
    cold_utilities: tuple[ColdUtility, ...] = ()
    exchanger_economics: tuple[ExchangerEconomics, ...] = ()

    @classmethod
    def from_csv(cls, source: str | Path, *, name: str | None = None) -> "CaseStudy":
        """Load a workbook-export CSV with delimiter autodetection and row validation."""

        path = Path(source)
        rows = _read_case_csv(path)
        return cls(source=path, name=name, **_parse_case_rows(rows))

    @property
    def exchange_economics(self) -> ExchangerEconomics:
        """Return the process-process exchanger cost row required by the legacy model."""

        return _single_economics(self.exchanger_economics, "exchange")

    @property
    def heating_economics(self) -> ExchangerEconomics:
        """Return the hot-utility exchanger cost row required by the legacy model."""

        return _single_economics(self.exchanger_economics, "heating")

    @property
    def cooling_economics(self) -> ExchangerEconomics:
        """Return the cold-utility exchanger cost row required by the legacy model."""

        return _single_economics(self.exchanger_economics, "cooling")

    def to_legacy_arrays(self, dTmin: float) -> dict[str, np.ndarray]:
        """Return the array names and shapes expected by the current solver stack.

        Missing temperature contributions intentionally fall back to ``dTmin / 2``
        so older CSV exports still reproduce the historical preprocessing logic.
        """

        default_temperature_contribution = dTmin / 2
        exchange = self.exchange_economics
        heating = self.heating_economics
        cooling = self.cooling_economics

        return {
            "T_h_in": _float_array(stream.supply_temperature for stream in self.hot_streams),
            "T_h_out": _float_array(stream.target_temperature for stream in self.hot_streams),
            "f_h": _float_array(stream.heat_capacity_flowrate for stream in self.hot_streams),
            "htc_h": _float_array(stream.heat_transfer_coefficient for stream in self.hot_streams),
            "h_cost": _float_array(stream.cost for stream in self.hot_streams),
            "hot_names": _str_array(stream.name for stream in self.hot_streams),
            "T_h_cont": _float_array(
                stream.temperature_contribution
                if stream.temperature_contribution is not None
                else default_temperature_contribution
                for stream in self.hot_streams
            ),
            "T_c_in": _float_array(stream.supply_temperature for stream in self.cold_streams),
            "T_c_out": _float_array(stream.target_temperature for stream in self.cold_streams),
            "f_c": _float_array(stream.heat_capacity_flowrate for stream in self.cold_streams),
            "htc_c": _float_array(stream.heat_transfer_coefficient for stream in self.cold_streams),
            "c_cost": _float_array(stream.cost for stream in self.cold_streams),
            "cold_names": _str_array(stream.name for stream in self.cold_streams),
            "T_c_cont": _float_array(
                stream.temperature_contribution
                if stream.temperature_contribution is not None
                else default_temperature_contribution
                for stream in self.cold_streams
            ),
            "hu_cost": _float_array(utility.cost for utility in self.hot_utilities),
            "hu_unit_cost": _float_array([heating.unit_cost]),
            "hu_coeff": _float_array([heating.area_coefficient]),
            "T_hu_in": _float_array(utility.supply_temperature for utility in self.hot_utilities),
            "T_hu_out": _float_array(utility.target_temperature for utility in self.hot_utilities),
            "htc_hu": _float_array(utility.heat_transfer_coefficient for utility in self.hot_utilities),
            "hu_exp": _float_array([heating.area_exponent]),
            "cu_cost": _float_array(utility.cost for utility in self.cold_utilities),
            "cu_unit_cost": _float_array([cooling.unit_cost]),
            "cu_coeff": _float_array([cooling.area_coefficient]),
            "T_cu_in": _float_array(utility.supply_temperature for utility in self.cold_utilities),
            "T_cu_out": _float_array(utility.target_temperature for utility in self.cold_utilities),
            "htc_cu": _float_array(utility.heat_transfer_coefficient for utility in self.cold_utilities),
            "cu_exp": _float_array([cooling.area_exponent]),
            "unit_cost": _float_array([exchange.unit_cost]),
            "A_coeff": _float_array([exchange.area_coefficient]),
            "A_exp": _float_array([exchange.area_exponent]),
        }

    def apply_to_legacy_model(self, model: object, dTmin: float) -> None:
        """Populate a mutable legacy model instance with the expected solver arrays."""

        for name, values in self.to_legacy_arrays(dTmin).items():
            setattr(model, name, values)


def _read_case_csv(path: Path) -> list[tuple[int, list[str]]]:
    """Read a workbook-export CSV while preserving row numbers for error messages."""

    if not path.exists():
        raise FileNotFoundError(f"Case CSV not found: {path}")

    text = path.read_text(encoding="utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,")
    except csv.Error:
        dialect = csv.excel()
        dialect.delimiter = ";" if text.count(";") >= text.count(",") else ","

    reader = csv.reader(text.splitlines(), dialect)
    return [(index, row) for index, row in enumerate(reader, start=1)]


def _parse_case_rows(rows: list[tuple[int, list[str]]]) -> dict[str, tuple[OpenHENSModel, ...]]:
    """Split a workbook export into typed sections using the shared designation column."""

    process_header = _find_header_row(rows, ("number", "subsystem", "description", "designation", "supply temp"))
    _find_header_row(rows, ("number", "subsystem", "description", "designation", "hx unit cost"))
    temperature_contribution_column = _temperature_contribution_column(process_header)

    hot_streams: list[HotStream] = []
    cold_streams: list[ColdStream] = []
    hot_utilities: list[HotUtility] = []
    cold_utilities: list[ColdUtility] = []
    exchanger_economics: list[ExchangerEconomics] = []

    for row_number, row in rows:
        designation = _normalise(_cell(row, 3))
        if not designation or designation == "designation":
            continue

        if designation == "hot":
            hot_streams.append(_parse_hot_stream(row_number, row, temperature_contribution_column))
        elif designation == "cold":
            cold_streams.append(_parse_cold_stream(row_number, row, temperature_contribution_column))
        elif designation == "hot utility":
            hot_utilities.append(_parse_hot_utility(row_number, row))
        elif designation == "cold utility":
            cold_utilities.append(_parse_cold_utility(row_number, row))
        elif designation in {"exchange", "heating", "cooling"}:
            exchanger_economics.append(_parse_exchanger_economics(row_number, row, designation))
        elif designation == "electricity":
            # The workbook can carry electricity rows, but the legacy solver API
            # has never exposed matching arrays for them.
            continue
        else:
            raise ValueError(f"row {row_number}: unknown Designation {designation!r}")

    _require_rows("process streams", "Hot", hot_streams)
    _require_rows("process streams", "Cold", cold_streams)
    _require_rows("utilities", "Hot Utility", hot_utilities)
    _require_rows("utilities", "Cold Utility", cold_utilities)
    for kind in ("exchange", "heating", "cooling"):
        if not any(economics.kind == kind for economics in exchanger_economics):
            raise ValueError(f"exchanger economics section: missing required {kind.title()} row")

    return {
        "hot_streams": tuple(hot_streams),
        "cold_streams": tuple(cold_streams),
        "hot_utilities": tuple(hot_utilities),
        "cold_utilities": tuple(cold_utilities),
        "exchanger_economics": tuple(exchanger_economics),
    }


def _parse_hot_stream(row_number: int, row: list[str], t_cont_column: int | None) -> HotStream:
    return HotStream(
        source_row=row_number,
        number=_cell(row, 0),
        subsystem=_cell(row, 1),
        name=_raw_cell(row, 2),
        supply_temperature=_numeric(row_number, row, 4, "Supply Temp", "process streams"),
        target_temperature=_numeric(row_number, row, 5, "Target Temp", "process streams"),
        heat_capacity_flowrate=_numeric(row_number, row, 6, "Flow heat capacity", "process streams"),
        heat_transfer_coefficient=_numeric(row_number, row, 7, "HTC", "process streams"),
        cost=_numeric(row_number, row, 8, "Stream cost", "process streams"),
        temperature_contribution=_optional_numeric(
            row_number,
            row,
            t_cont_column,
            "T cont",
            "process streams",
        ),
    )


def _parse_cold_stream(row_number: int, row: list[str], t_cont_column: int | None) -> ColdStream:
    return ColdStream(
        source_row=row_number,
        number=_cell(row, 0),
        subsystem=_cell(row, 1),
        name=_raw_cell(row, 2),
        supply_temperature=_numeric(row_number, row, 4, "Supply Temp", "process streams"),
        target_temperature=_numeric(row_number, row, 5, "Target Temp", "process streams"),
        heat_capacity_flowrate=_numeric(row_number, row, 6, "Flow heat capacity", "process streams"),
        heat_transfer_coefficient=_numeric(row_number, row, 7, "HTC", "process streams"),
        cost=_numeric(row_number, row, 8, "Stream cost", "process streams"),
        temperature_contribution=_optional_numeric(
            row_number,
            row,
            t_cont_column,
            "T cont",
            "process streams",
        ),
    )


def _parse_hot_utility(row_number: int, row: list[str]) -> HotUtility:
    return HotUtility(
        source_row=row_number,
        number=_cell(row, 0),
        subsystem=_cell(row, 1),
        name=_raw_cell(row, 2),
        supply_temperature=_numeric(row_number, row, 4, "Supply Temp", "utilities"),
        target_temperature=_numeric(row_number, row, 5, "Target Temp", "utilities"),
        heat_transfer_coefficient=_numeric(row_number, row, 7, "HTC", "utilities"),
        cost=_numeric(row_number, row, 8, "Stream cost", "utilities"),
    )


def _parse_cold_utility(row_number: int, row: list[str]) -> ColdUtility:
    return ColdUtility(
        source_row=row_number,
        number=_cell(row, 0),
        subsystem=_cell(row, 1),
        name=_raw_cell(row, 2),
        supply_temperature=_numeric(row_number, row, 4, "Supply Temp", "utilities"),
        target_temperature=_numeric(row_number, row, 5, "Target Temp", "utilities"),
        heat_transfer_coefficient=_numeric(row_number, row, 7, "HTC", "utilities"),
        cost=_numeric(row_number, row, 8, "Stream cost", "utilities"),
    )


def _parse_exchanger_economics(row_number: int, row: list[str], kind: ExchangerKind) -> ExchangerEconomics:
    return ExchangerEconomics(
        source_row=row_number,
        kind=kind,
        number=_cell(row, 0),
        subsystem=_cell(row, 1),
        name=_raw_cell(row, 2),
        unit_cost=_numeric(row_number, row, 4, "HX unit cost", "exchanger economics"),
        area_coefficient=_numeric(row_number, row, 5, "HX area coefficient", "exchanger economics"),
        area_exponent=_numeric(row_number, row, 6, "HX area exponent", "exchanger economics"),
    )


def _cell(row: list[str], index: int) -> str:
    if index >= len(row):
        return ""
    return row[index].strip()


def _raw_cell(row: list[str], index: int) -> str:
    """Return the cell verbatim for fields where workbook spacing is user-visible."""

    if index >= len(row):
        return ""
    return row[index]


def _numeric(row_number: int, row: list[str], index: int, field_name: str, section: str) -> float:
    raw_value = _cell(row, index)
    if raw_value == "":
        raise ValueError(f"{section} row {row_number}: {field_name} is required")
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{section} row {row_number}: {field_name} must be numeric; got {raw_value!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"{section} row {row_number}: {field_name} must be finite")
    return value


def _optional_numeric(
    row_number: int,
    row: list[str],
    index: int | None,
    field_name: str,
    section: str,
) -> float | None:
    """Parse an optional numeric field, treating blank or absent columns as missing."""

    if index is None or _cell(row, index) == "":
        return None
    return _numeric(row_number, row, index, field_name, section)


def _normalise(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _normalise_header(value: str) -> str:
    return _normalise(value).replace("_", " ")


def _find_header_row(rows: list[tuple[int, list[str]]], required_prefix: tuple[str, ...]) -> list[str]:
    """Find a section header even when workbook exports include title rows above it."""

    required = tuple(_normalise_header(value) for value in required_prefix)
    for _, row in rows:
        normalised = tuple(_normalise_header(cell) for cell in row[: len(required)])
        if normalised == required:
            return row
    raise ValueError(f"CSV does not match the expected workbook-export schema; missing header {required_prefix!r}")


def _temperature_contribution_column(process_header: list[str]) -> int | None:
    """Locate the optional process-stream temperature contribution column.

    Older case-study exports omit this column entirely, so downstream parsing
    must gracefully fall back to the historical ``dTmin / 2`` default.
    """

    for index, label in enumerate(process_header):
        normalised = _normalise_header(label)
        if normalised in {"t cont", "t contribution", "temperature contribution"}:
            return index
    return None


def _require_rows(section: str, designation: str, rows: list[OpenHENSModel]) -> None:
    if not rows:
        raise ValueError(f"{section} section: missing required {designation} row")


def _single_economics(rows: tuple[ExchangerEconomics, ...], kind: ExchangerKind) -> ExchangerEconomics:
    """Return the first matching economics row, mirroring the legacy single-row contract."""

    matches = tuple(row for row in rows if row.kind == kind)
    if not matches:
        raise ValueError(f"exchanger economics section: missing required {kind.title()} row")
    return matches[0]


def _validate_finite_fields(model: OpenHENSModel, *field_names: str) -> None:
    """Centralize finite-number checks so row models report consistent errors."""

    for field_name in field_names:
        value = getattr(model, field_name)
        if value is not None and not math.isfinite(value):
            raise ValueError(f"row {model.source_row}: {field_name} must be finite")


def _float_array(values) -> np.ndarray:
    """Materialize solver-facing numeric arrays with the dtype expected downstream."""

    return np.array(list(values), dtype=float)


def _str_array(values) -> np.ndarray:
    """Materialize solver-facing string arrays without normalizing workbook text."""

    return np.array(list(values), dtype=str)


class DesignSpace(OpenHENSModel):
    """Design grid and stage-selection inputs for a synthesis study.

    ``validation_alias`` keeps the public names aligned with the refactor plan
    while still accepting the historical option keys used by existing callers.
    """

    approach_temperatures: tuple[float, ...] = Field(
        default=(2, 4, 6, 8, 10, 12, 14, 16, 18, 20),
        validation_alias=AliasChoices("approach_temperatures", "min_dT_values"),
    )
    derivative_thresholds: tuple[float, ...] = Field(
        default=(0.5, 0.9, 1.3, 1.7, 2.1, 2.4, 2.8, 3.2, 3.6, 4.0),
        validation_alias=AliasChoices("derivative_thresholds", "min_dqda_values"),
    )
    stage_selection: StageSelection = "automated"

    @field_validator("approach_temperatures", "derivative_thresholds")
    @classmethod
    def validate_design_grid(cls, values: tuple[float, ...]) -> tuple[float, ...]:
        if not values:
            raise ValueError("design grids must contain at least one value")
        if any(not math.isfinite(value) or value <= 0 for value in values):
            raise ValueError("design grid values must be finite and positive")
        return values

    @field_validator("stage_selection", mode="before")
    @classmethod
    def validate_stage_selection(cls, value: object) -> object:
        if value == "automated":
            return value
        if not isinstance(value, (list, tuple)):
            raise ValueError("stage_selection must be 'automated' or two positive stage counts")
        if len(value) != 2:
            raise ValueError("manual stage_selection must contain exactly two stage counts")
        # ``type(...) is int`` rejects bools, which would otherwise sneak
        # through because ``bool`` is a subclass of ``int``.
        if any(type(stage) is not int or stage <= 0 for stage in value):
            raise ValueError("manual stage_selection stage counts must be positive integers")
        return tuple(value)


class MethodSequence(OpenHENSModel):
    """Method and solver sequence for a synthesis study.

    The default order and solver choices match the long-standing public OpenHENS
    workflow so callers can opt in incrementally without changing results. In
    this phase, ``OpenHENS.solve()`` only executes the canonical
    ``PDM -> TDM -> ESM`` sequence with the default solver choices; custom
    method orders or solver choices validate here but raise ``NotImplementedError``
    at the facade until those execution paths are wired.
    """

    methods: tuple[MethodName, ...] = ("PDM", "TDM", "ESM")
    pdm_solver: SolverName = "couenne"
    tdm_solver: SolverName = "couenne"
    esm_solver: SolverName = "ipopt-pyomo"

    @classmethod
    def standard_pdm_tdm_esm(cls) -> "MethodSequence":
        """Return the canonical public workflow ordering used by legacy entry points."""

        return cls()

    @field_validator("methods")
    @classmethod
    def validate_methods(cls, methods: tuple[MethodName, ...]) -> tuple[MethodName, ...]:
        if not methods:
            raise ValueError("method sequence must contain at least one method")
        return methods


class SolveSetup(OpenHENSModel):
    """Local solve controls matching the current OpenHENS defaults."""

    tolerance: float = 1e-3
    max_parallel: int = 10
    log_level: int = logging.WARNING

    @classmethod
    def local(cls, **kwargs) -> "SolveSetup":
        """Compatibility constructor mirroring the existing local workflow defaults."""

        return cls(**kwargs)

    @field_validator("tolerance")
    @classmethod
    def validate_tolerance(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("tolerance must be finite and positive")
        return value

    @field_validator("max_parallel")
    @classmethod
    def validate_max_parallel(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("max_parallel must be positive")
        return value


class StudyOutputs(OpenHENSModel):
    """Study artifact preferences for the public API.

    Field aliases keep older option dictionaries working while the public names
    settle on the refactored study vocabulary. JSON and CSV are currently the
    mandatory durable outputs regardless of ``formats``; the field records the
    requested public contract for future output negotiation. Legacy workbook and
    plot exports are controlled by ``include_excel`` and ``include_plots``.
    """

    folder: Path = Field(
        default=Path("examples/results/Four-stream-Yee-and-Grossmann-1990-1"),
        validation_alias=AliasChoices("folder", "output_folder"),
    )
    formats: tuple[OutputFormat, ...] = Field(
        default=("json", "csv"),
        validation_alias=AliasChoices("formats", "output_formats"),
    )
    include_excel: bool = Field(default=False, validation_alias=AliasChoices("include_excel", "excel_enabled"))
    include_plots: bool = Field(default=False, validation_alias=AliasChoices("include_plots", "plots_enabled"))
    run_id: str | None = None
    best_solutions_to_save: int = 10

    @field_validator("formats")
    @classmethod
    def validate_output_formats(cls, formats: tuple[OutputFormat, ...]) -> tuple[OutputFormat, ...]:
        if not formats:
            raise ValueError("output_formats must contain at least one format")
        return formats

    @field_validator("best_solutions_to_save")
    @classmethod
    def validate_best_solutions_to_save(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("best_solutions_to_save must be positive")
        return value

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("run_id must be non-empty when provided")
        if Path(value).name != value:
            raise ValueError("run_id must be a single folder name")
        return value


class SynthesisStudy(OpenHENSModel):
    """Top-level public entry object for an OpenHENS synthesis study.

    This is the stable input shell consumed by the modern facade, with
    backcompat aliases only where the older options object leaked into user
    code.
    """

    case: CaseStudy
    name: str | None = None
    design_space: DesignSpace = Field(default_factory=DesignSpace)
    methods: MethodSequence = Field(default_factory=MethodSequence.standard_pdm_tdm_esm)
    solving: SolveSetup = Field(
        default_factory=SolveSetup.local,
        validation_alias=AliasChoices("solving", "solve_setup"),
    )
    outputs: StudyOutputs = Field(default_factory=StudyOutputs)

    @model_validator(mode="after")
    def set_default_name(self) -> "SynthesisStudy":
        if self.name is None and self.case.name is not None:
            self.name = self.case.name
        return self


class TaskNumericalSettings(OpenHENSModel):
    """Numerical controls for one generated synthesis task."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tolerance: float

    @field_validator("tolerance")
    @classmethod
    def validate_tolerance(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("task tolerance must be finite and positive")
        return value


class TaskRestrictions(OpenHENSModel):
    """Serializable topology/restriction data passed between workflow stages."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    recovery_heat_duties: tuple[tuple[tuple[float, ...], ...], ...] | None = None
    hot_utility_duties: tuple[float, ...] | None = None
    cold_utility_duties: tuple[float, ...] | None = None

    def to_legacy_z_restriction(self) -> list:
        """Return the legacy ``[z, z_hu, z_cu]`` restriction shape.

        The nested single-value lists are intentional: they preserve the exact
        shape consumed by older solver routines and their tests.
        """

        recovery = None
        if self.recovery_heat_duties is not None:
            recovery = [
                [
                    [[float(value)] for value in cold_stream]
                    for cold_stream in hot_stream
                ]
                for hot_stream in self.recovery_heat_duties
            ]
        return [recovery, self.hot_utility_duties, self.cold_utility_duties]


class SynthesisTask(OpenHENSModel):
    """Immutable, serializable description of one PDM, TDM, or ESM solve.

    Tasks are designed to survive queueing, JSON round-trips, and cross-process
    handoff without carrying solver runtime objects.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    method: MethodName
    parent_task_ids: tuple[str, ...] = ()
    case_reference: Path
    stage_selection: StageSelection = "automated"
    solver: SolverName
    objective: TaskObjective
    restrictions: TaskRestrictions = Field(default_factory=TaskRestrictions)
    numerical_settings: TaskNumericalSettings
    dTmin: float
    min_dqda: float = 0
    approach_temperature: float | None = None
    derivative_threshold: float | None = None
    stages: int | None = None
    legacy_name: str
    non_isothermal_model: bool
    integers: bool
    evolution_enabled: bool = False

    @field_validator("task_id", "legacy_name")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value:
            raise ValueError("task identifiers and names must be non-empty")
        return value

    @field_validator("dTmin")
    @classmethod
    def validate_dTmin(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("task dTmin must be finite and positive")
        return value

    @field_validator("min_dqda")
    @classmethod
    def validate_min_dqda(cls, value: float) -> float:
        if not math.isfinite(value) or value < 0:
            raise ValueError("task min_dqda must be finite and non-negative")
        return value

    @field_validator("approach_temperature", "derivative_threshold")
    @classmethod
    def validate_optional_positive(cls, value: float | None) -> float | None:
        if value is not None and (not math.isfinite(value) or value <= 0):
            raise ValueError("task design coordinates must be finite and positive")
        return value

    @field_validator("stages")
    @classmethod
    def validate_stages(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("task stages must be positive when provided")
        return value


class SolverRun(OpenHENSModel):
    """JSON-compatible metadata captured from one solver invocation.

    This is intentionally narrow so durable results can be written without
    depending on solver-specific classes or enums. ``status`` is the raw GEKKO
    or Pyomo status value when available, ``objective_value`` is the model
    objective in solver units, and ``solve_time`` is elapsed wall-clock seconds.
    """

    name: str
    extension: str | int | None = None
    status: str | int | None = None
    objective_value: float | None = None
    solve_time: float | None = Field(default=None, ge=0)
    failure_reason: str | None = None


class NetworkSolution(OpenHENSModel):
    """Stable public record for a solved heat-exchanger network.

    Only durable, JSON-friendly values belong here; solver internals stay on
    transient workflow objects so persisted results remain easy to reload.

    Units follow the legacy model arrays: temperatures in K, heat duties in kW,
    exchanger areas in m2, and total annual cost/objective values in $/y.
    Recovery-shaped fields use ``[hot_stream][cold_stream][stage]`` ordering;
    stream-temperature fields use ``[stream][stage]`` ordering. ``unit_counts``
    uses ``total``, ``recovery``, ``hot_utility``, and ``cold_utility`` keys
    when those values were available from post-processing.
    """

    name: str
    task_id: str | None = None
    method: str | None = None
    solver: SolverRun | None = None
    parent_task_ids: tuple[str, ...] = ()
    dTmin: float | None = None
    min_dqda: float | None = None
    approach_temperature: float | None = None
    derivative_threshold: float | None = None
    stages: int | None = None
    recovery_heat_duties: tuple[tuple[tuple[float | None, ...], ...], ...] | None = None
    hot_utility_duties: tuple[float | None, ...] | None = None
    cold_utility_duties: tuple[float | None, ...] | None = None
    hot_stream_temperatures: tuple[tuple[float | None, ...], ...] | None = None
    cold_stream_temperatures: tuple[tuple[float | None, ...], ...] | None = None
    hot_recovery_outlet_temperatures: tuple[tuple[tuple[float | None, ...], ...], ...] | None = None
    cold_recovery_outlet_temperatures: tuple[tuple[tuple[float | None, ...], ...], ...] | None = None
    recovery_areas: tuple[tuple[tuple[float | None, ...], ...], ...] | None = None
    hot_utility_areas: tuple[float | None, ...] | None = None
    cold_utility_areas: tuple[float | None, ...] | None = None
    dqda: tuple[tuple[tuple[float | None, ...], ...], ...] | None = None
    utility_loads: dict[str, float | None] = Field(default_factory=dict)
    unit_counts: dict[str, int | None] = Field(default_factory=dict)
    total_annual_cost: float | None = None
    model_objective_value: float | None = None
    method_lineage: tuple[dict[str, str | int | float | bool | None], ...] = ()
    verification_failures: tuple[str, ...] = ()


class TaskOutcome(OpenHENSModel):
    """Stable result for one synthesis task.

    ``problem`` and ``topology`` are transient compatibility fields used by the
    current local workflow. They are deliberately excluded from serialized
    output so durable results never require GEKKO or pickle loading.
    """

    task: SynthesisTask
    success: bool
    solver: SolverRun | None = None
    solution: NetworkSolution | None = None
    failure_reason: str | None = None
    verification_failures: tuple[str, ...] = ()
    error: str | None = Field(default=None, exclude=True)
    problem: Any | None = Field(default=None, exclude=True, repr=False)
    topology: Any | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="before")
    @classmethod
    def sync_legacy_error(cls, data):
        if isinstance(data, dict):
            # Older workflow code populated ``error``; the durable public field
            # is ``failure_reason``. Keep both synchronized on input.
            if data.get("failure_reason") is None and data.get("error") is not None:
                data = data | {"failure_reason": data["error"]}
            elif data.get("error") is None and data.get("failure_reason") is not None:
                data = data | {"error": data["failure_reason"]}
        return data

    @property
    def task_id(self) -> str:
        return self.task.task_id


class SolutionPortfolio(OpenHENSModel):
    """Stable public shell for ranked study solutions.

    The wrapper gives persisted study outputs a durable top-level shape even as
    ranking metadata evolves around the individual solutions.
    """

    solutions: tuple[NetworkSolution, ...] = ()

    def best_by_total_annual_cost(self) -> NetworkSolution | None:
        """Return the finite lowest-TAC solution while preserving tie order."""

        ranked = [
            solution
            for solution in self.solutions
            if solution.total_annual_cost is not None and math.isfinite(solution.total_annual_cost)
        ]
        if not ranked:
            return None
        return min(ranked, key=lambda solution: solution.total_annual_cost)


class StudyManifest(OpenHENSModel):
    """Stable public shell for study artifact metadata.

    This manifest points at durable outputs on disk and records the study-level
    bookkeeping needed to reload a run without solver state. Artifact paths are
    normally relative to the run folder containing ``manifest.json``; pass a
    manifest path or run-folder path to ``StudyOutcome.from_artifacts`` so those
    relative paths resolve correctly.

    ``attempted_solver_jobs`` and run summaries preserve the historical ESM
    weighting where one ESM task represents eleven attempted cases.
    """

    run_id: str | None = None
    study_name: str | None = None
    study: SynthesisStudy | None = None
    case_hash: str | None = None
    package_version: str | None = None
    solver_metadata: tuple[dict[str, Any], ...] = ()
    created_at: str | None = None
    completed_at: str | None = None
    total_run_time_seconds: float | None = None
    attempted_solver_jobs: int = 0
    manifest_path: Path = Path("manifest.json")
    result_paths: tuple[Path, ...] = ()
    solution_metrics_path: Path | None = Path("metrics/solution_metrics.csv")
    run_summary_path: Path | None = Path("metrics/run_summary.csv")
    excel_paths: tuple[Path, ...] = ()
    plot_paths: tuple[Path, ...] = ()
    artifacts: tuple[Path, ...] = ()


class StudyOutcome(OpenHENSModel):
    """Stable public shell for a completed synthesis study.

    ``portfolio`` remains accepted as an input alias so previously persisted
    outputs can be read back after the public field settled on ``solutions``.
    """

    study: SynthesisStudy
    solutions: SolutionPortfolio = Field(
        default_factory=SolutionPortfolio,
        validation_alias=AliasChoices("solutions", "portfolio"),
    )
    manifest: StudyManifest = Field(default_factory=StudyManifest)
    task_outcomes: tuple[TaskOutcome, ...] = ()
    total_run_time_seconds: float | None = None
    attempted_solver_jobs: int = 0

    @classmethod
    def from_artifacts(cls, manifest: str | Path | StudyManifest) -> "StudyOutcome":
        """Reload a completed study from a saved manifest path or run folder.

        Passing a ``StudyManifest`` object only works when its result paths are
        absolute or relative to the current working directory. Prefer a path for
        normal run-folder reloads because it preserves the artifact base folder.
        """

        from .artifacts import load_study_outcome

        return load_study_outcome(manifest)
