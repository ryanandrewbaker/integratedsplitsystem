"""ARCHITECTURE.md §4.2.1 golden table T1–T7 for the M2 controller."""

from __future__ import annotations

import pytest

from custom_components.integrated_split_system.controller import (
    ControllerState,
    Direction,
    StateMachineInput,
    compute_kitchen_climate_controller,
)


def _golden_input(**overrides: object) -> StateMachineInput:
    defaults: dict[str, object] = {
        "climate_on": True,
        "virtual_fan_only": False,
        "temperature": 22.0,
        "base_low": 21.0,
        "base_high": 24.0,
        "manual_boost": False,
        "heat_demand_active": False,
        "cool_demand_active": False,
        "fan_automatic": True,
        "current_state": ControllerState.MAINTAIN,
        "current_direction": Direction.HEAT,
    }
    defaults.update(overrides)
    return StateMachineInput(**defaults)  # type: ignore[arg-type]


def _run(
    *,
    temperature: float | None,
    current_state: ControllerState,
    heat_demand_active: bool = False,
    cool_demand_active: bool = False,
    virtual_fan_only: bool = False,
    manual_boost: bool = False,
    current_direction: Direction = Direction.HEAT,
) -> ControllerState:
    result = compute_kitchen_climate_controller(
        _golden_input(
            temperature=temperature,
            current_state=current_state,
            heat_demand_active=heat_demand_active,
            cool_demand_active=cool_demand_active,
            virtual_fan_only=virtual_fan_only,
            manual_boost=manual_boost,
            current_direction=current_direction,
        )
    )
    return result.desired_state


@pytest.mark.parametrize(
    ("case_id", "prior_state", "temperature", "heat_demand", "cool_demand", "fan_only", "expected"),
    [
        ("T1", ControllerState.MAINTAIN, 22.6, False, False, False, ControllerState.IDLE),
        ("T2", ControllerState.IDLE, 22.6, False, False, False, ControllerState.IDLE),
        ("T3", ControllerState.IDLE, 21.0, False, False, False, ControllerState.MAINTAIN),
        ("T4", ControllerState.MAINTAIN, 19.5, False, False, False, ControllerState.BOOST),
        ("T5", ControllerState.BOOST, 21.2, False, False, False, ControllerState.MAINTAIN),
        (
            "T6",
            ControllerState.MAINTAIN,
            22.0,
            True,
            False,
            False,
            ControllerState.BOOST,
        ),
        ("T7", ControllerState.BOOST, 22.0, False, False, True, ControllerState.IDLE),
    ],
)
def test_golden_state_transitions(
    case_id: str,
    prior_state: ControllerState,
    temperature: float,
    heat_demand: bool,
    cool_demand: bool,
    fan_only: bool,
    expected: ControllerState,
) -> None:
    """Golden rows T1–T7 from docs/ARCHITECTURE.md §4.2.1."""
    assert (
        _run(
            temperature=temperature,
            current_state=prior_state,
            heat_demand_active=heat_demand,
            cool_demand_active=cool_demand,
            virtual_fan_only=fan_only,
        )
        == expected
    )


def test_t7_suppresses_automatic_fan_staging() -> None:
    result = compute_kitchen_climate_controller(
        _golden_input(
            virtual_fan_only=True,
            temperature=22.0,
            current_state=ControllerState.BOOST,
        )
    )
    assert result.desired_state == ControllerState.IDLE
    assert result.apply_automatic_fan_stage is False


def test_manual_boost_shifts_heat_band_without_changing_base_inputs() -> None:
    """manualBoost uses baseLow+1 for heat; virtual band inputs stay 21/24."""
    base_low = 21.0
    base_high = 24.0
    without_boost = compute_kitchen_climate_controller(
        _golden_input(
            base_low=base_low,
            base_high=base_high,
            temperature=22.6,
            current_state=ControllerState.MAINTAIN,
        )
    )
    with_boost = compute_kitchen_climate_controller(
        _golden_input(
            base_low=base_low,
            base_high=base_high,
            manual_boost=True,
            temperature=22.6,
            current_state=ControllerState.MAINTAIN,
        )
    )
    assert without_boost.desired_state == ControllerState.IDLE
    assert with_boost.desired_state == ControllerState.MAINTAIN
    assert with_boost.desired_fan_stage == "high"


def test_manual_boost_cool_band_uses_base_high_minus_one() -> None:
    result = compute_kitchen_climate_controller(
        _golden_input(
            manual_boost=True,
            temperature=23.5,
            current_state=ControllerState.MAINTAIN,
            current_direction=Direction.COOL,
        )
    )
    assert result.desired_direction == Direction.COOL
    assert result.desired_state == ControllerState.MAINTAIN
    assert result.desired_fan_stage == "high"
