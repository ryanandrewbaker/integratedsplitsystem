"""Kitchen climate controller state machine (ported from kitchen-climate-state-machine.ts)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class ControllerState(StrEnum):
    """High-level controller operating state."""

    OFF = "off"
    BOOST = "boost"
    MAINTAIN = "maintain"
    IDLE = "idle"


class Direction(StrEnum):
    """Active heating or cooling direction."""

    HEAT = "heat"
    COOL = "cool"


FanStage = Literal["off", "high", "medium", "low"]


@dataclass(frozen=True, slots=True)
class StateMachineInput:
    """Inputs for one controller evaluation step."""

    climate_on: bool
    virtual_fan_only: bool
    temperature: float | None
    base_low: float
    base_high: float
    manual_boost: bool
    heat_demand_active: bool
    cool_demand_active: bool
    fan_automatic: bool
    current_state: ControllerState
    current_direction: Direction


@dataclass(frozen=True, slots=True)
class StateMachineOutput:
    """Outputs from one controller evaluation step."""

    desired_direction: Direction
    desired_state: ControllerState
    desired_fan_stage: FanStage
    apply_automatic_fan_stage: bool


def _midpoint(low: float, high: float) -> float:
    return low + (high - low) / 2


def compute_kitchen_climate_controller(
    input: StateMachineInput,
) -> StateMachineOutput:
    """Compute desired direction, state, and fan staging from current conditions."""
    if input.virtual_fan_only and input.climate_on:
        direction = (
            input.current_direction
            if input.current_direction in (Direction.HEAT, Direction.COOL)
            else Direction.HEAT
        )
        return StateMachineOutput(
            desired_direction=direction,
            desired_state=ControllerState.IDLE,
            desired_fan_stage="off",
            apply_automatic_fan_stage=False,
        )

    t = input.temperature
    base_low = input.base_low
    base_high = input.base_high
    manual_boost = input.manual_boost
    current_state = input.current_state

    if input.heat_demand_active:
        desired_direction = Direction.HEAT
    elif input.cool_demand_active:
        desired_direction = Direction.COOL
    elif input.current_direction in (Direction.HEAT, Direction.COOL):
        desired_direction = input.current_direction
    elif t is not None and t <= _midpoint(base_low, base_high):
        desired_direction = Direction.HEAT
    else:
        desired_direction = Direction.COOL

    low = base_low + 1.0 if manual_boost and desired_direction == Direction.HEAT else base_low
    high = (
        base_high - 1.0 if manual_boost and desired_direction == Direction.COOL else base_high
    )

    if not input.climate_on or t is None:
        desired_state = ControllerState.OFF
    elif input.heat_demand_active or input.cool_demand_active:
        desired_state = ControllerState.BOOST
    elif desired_direction == Direction.HEAT:
        if current_state == ControllerState.IDLE:
            desired_state = ControllerState.MAINTAIN if t <= low else ControllerState.IDLE
        elif t >= low + 1.5:
            desired_state = ControllerState.IDLE
        elif t <= low - 1.0:
            desired_state = ControllerState.BOOST
        else:
            desired_state = ControllerState.MAINTAIN
    else:
        if current_state == ControllerState.IDLE:
            desired_state = ControllerState.MAINTAIN if t >= high else ControllerState.IDLE
        elif t <= high - 1.5:
            desired_state = ControllerState.IDLE
        elif t >= high + 1.0:
            desired_state = ControllerState.BOOST
        else:
            desired_state = ControllerState.MAINTAIN

    desired_fan_stage: FanStage = "off"
    if manual_boost and desired_state in (ControllerState.BOOST, ControllerState.MAINTAIN):
        desired_fan_stage = "high"
    elif desired_state == ControllerState.BOOST:
        desired_fan_stage = "high"
    elif desired_state == ControllerState.MAINTAIN and desired_direction == Direction.HEAT:
        desired_fan_stage = "low" if t is not None and t >= low + 1.0 else "medium"
    elif desired_state == ControllerState.MAINTAIN and desired_direction == Direction.COOL:
        desired_fan_stage = "low" if t is not None and t <= high - 1.0 else "medium"

    apply_automatic_fan_stage = input.fan_automatic or (
        manual_boost and desired_fan_stage == "high"
    )

    return StateMachineOutput(
        desired_direction=desired_direction,
        desired_state=desired_state,
        desired_fan_stage=desired_fan_stage,
        apply_automatic_fan_stage=apply_automatic_fan_stage,
    )


_FAN_PREFS: dict[str, list[str]] = {
    "strong": ["strong", "high", "auto", "medium", "low", "quiet"],
    "high": ["high", "strong", "auto", "medium", "low", "quiet"],
    "medium": ["medium", "auto", "high", "low", "quiet"],
    "low": ["low", "quiet", "medium", "auto", "high"],
    "quiet": ["quiet", "low", "medium", "auto", "high"],
    "auto": ["auto", "high", "medium", "low", "quiet"],
}


def map_selected_fan_to_sensibo(selected_fan: str, available_modes: list[str]) -> str:
    """Map a UI fan stage to the best available Sensibo fan mode."""
    candidates = _FAN_PREFS.get(selected_fan.lower(), _FAN_PREFS["high"])
    normalized = [m.lower() for m in available_modes]
    for candidate in candidates:
        index = normalized.index(candidate) if candidate in normalized else -1
        if index != -1:
            return available_modes[index]
    return ""


def seconds_since_power_transition(
    now_epoch_sec: float, last_transition_iso: str | None
) -> float | None:
    """Seconds since an ISO-ish HA timestamp, or None when unknown."""
    if not last_transition_iso:
        return None
    parsed = last_transition_iso.replace(" ", "T")
    from datetime import datetime

    try:
        dt = datetime.fromisoformat(parsed)
    except ValueError:
        return None
    epoch_ms = dt.timestamp() * 1000
    if not (epoch_ms == epoch_ms):  # NaN guard
        return None
    return now_epoch_sec - epoch_ms / 1000


def should_defer_physical_shutdown(
    seconds_since_power_on: float | None, min_cycle_seconds: float
) -> bool:
    """Return True when compressor min-cycle should defer shutdown."""
    if seconds_since_power_on is None:
        return False
    return 0 <= seconds_since_power_on < min_cycle_seconds
