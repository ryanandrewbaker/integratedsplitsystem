"""Boost band shift and non-compounding virtual setpoints (D01 / ARCHITECTURE §4.5)."""

from __future__ import annotations

from custom_components.integrated_split_system.controller import (
    ControllerState,
    Direction,
    StateMachineInput,
    compute_kitchen_climate_controller,
    map_selected_fan_to_sensibo,
)


def _boost_input(**overrides: object) -> StateMachineInput:
    defaults: dict[str, object] = {
        "climate_on": True,
        "virtual_fan_only": False,
        "base_low": 20.0,
        "base_high": 24.5,
        "manual_boost": False,
        "heat_demand_active": False,
        "cool_demand_active": False,
        "fan_automatic": True,
        "current_state": ControllerState.MAINTAIN,
        "current_direction": Direction.HEAT,
        "temperature": 21.5,
    }
    defaults.update(overrides)
    return StateMachineInput(**defaults)  # type: ignore[arg-type]


def test_boost_start_does_not_compound_virtual_band_inputs() -> None:
    """B1: boost uses ±1°C effective bands; base_low/base_high inputs unchanged."""
    virtual_low = 20.0
    virtual_high = 24.5
    result = compute_kitchen_climate_controller(
        _boost_input(
            base_low=virtual_low,
            base_high=virtual_high,
            manual_boost=True,
            temperature=21.5,
        )
    )
    assert result.desired_state == ControllerState.MAINTAIN
    assert result.desired_fan_stage == "high"


def test_extend_boost_reuses_same_base_targets() -> None:
    """B2: repeated evaluation with same virtual targets does not widen bands."""
    virtual_low = 20.0
    virtual_high = 24.5
    first = compute_kitchen_climate_controller(
        _boost_input(
            base_low=virtual_low,
            base_high=virtual_high,
            manual_boost=True,
            temperature=19.0,
        )
    )
    second = compute_kitchen_climate_controller(
        _boost_input(
            base_low=virtual_low,
            base_high=virtual_high,
            manual_boost=True,
            temperature=19.0,
            current_state=first.desired_state,
        )
    )
    assert first.desired_state == ControllerState.BOOST
    assert second.desired_state == ControllerState.BOOST


def test_cancel_boost_restores_unshifted_heat_hysteresis() -> None:
    """B3: manual_boost off returns effective low to base_low (20.0)."""
    virtual_low = 20.0
    virtual_high = 24.5
    boosted = compute_kitchen_climate_controller(
        _boost_input(
            base_low=virtual_low,
            base_high=virtual_high,
            manual_boost=True,
            temperature=20.5,
            current_state=ControllerState.IDLE,
        )
    )
    cancelled = compute_kitchen_climate_controller(
        _boost_input(
            base_low=virtual_low,
            base_high=virtual_high,
            manual_boost=False,
            temperature=20.5,
            current_state=ControllerState.IDLE,
        )
    )
    assert boosted.desired_state == ControllerState.MAINTAIN
    assert cancelled.desired_state == ControllerState.IDLE


def test_cool_boost_effective_high_is_base_high_minus_one() -> None:
    """B6: cool manual boost tightens high band to 23.5 when base_high is 24.5."""
    result = compute_kitchen_climate_controller(
        _boost_input(
            manual_boost=True,
            temperature=24.0,
            current_direction=Direction.COOL,
        )
    )
    assert result.desired_direction == Direction.COOL
    assert result.desired_state == ControllerState.MAINTAIN
    assert result.desired_fan_stage == "high"


def test_manual_boost_high_fan_when_automatic_fan_disabled() -> None:
    result = compute_kitchen_climate_controller(
        _boost_input(
            base_low=21.0,
            base_high=24.0,
            manual_boost=True,
            fan_automatic=False,
            temperature=21.5,
        )
    )
    assert result.desired_fan_stage == "high"
    assert result.apply_automatic_fan_stage is True


def test_map_selected_fan_to_sensibo_preserves_casing() -> None:
    assert map_selected_fan_to_sensibo("medium", ["Auto", "Medium", "High"]) == "Medium"


def test_map_selected_fan_to_sensibo_empty_when_no_match() -> None:
    assert map_selected_fan_to_sensibo("high", []) == ""
