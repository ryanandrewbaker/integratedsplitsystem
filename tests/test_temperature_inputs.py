"""M2 temperature input manager."""

from __future__ import annotations

from homeassistant.const import UnitOfTemperature
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from custom_components.integrated_split_system.temperature import (
    TemperatureInputManager,
    TemperatureSourceConfig,
    parse_temperature_sources,
)

from .conftest import build_config_entry_data, setup_config_entry, track_climate_service_calls


async def test_equal_weight_average(hass, physical_climate_factory) -> None:
    s1 = "sensor.kitchen_temp_a"
    s2 = "sensor.kitchen_temp_b"
    hass.states.async_set(s1, "20", {})
    hass.states.async_set(s2, "24", {})
    await hass.async_block_till_done()

    mgr = TemperatureInputManager(
        hass,
        [
            TemperatureSourceConfig(s1),
            TemperatureSourceConfig(s2),
        ],
    )
    snap = mgr.recalculate()
    assert snap.control_temperature_c == 22.0
    assert snap.method == "average"
    assert snap.valid_source_count == 2


async def test_single_valid_source_fallback(hass) -> None:
    hass.states.async_set("sensor.only_one", "21.5", {})
    await hass.async_block_till_done()
    mgr = TemperatureInputManager(hass, [TemperatureSourceConfig("sensor.only_one")])
    snap = mgr.recalculate()
    assert snap.control_temperature_c == 21.5
    assert snap.method == "single"


async def test_unavailable_sources_degraded(hass) -> None:
    mgr = TemperatureInputManager(
        hass,
        [TemperatureSourceConfig("sensor.missing")],
    )
    snap = mgr.recalculate()
    assert snap.degraded is True
    assert snap.control_temperature_c is None


async def test_fahrenheit_hass_unit_implicit_physical(hass, physical_climate_factory) -> None:
    hass.config.units = US_CUSTOMARY_SYSTEM
    physical = await physical_climate_factory(
        "climate.us_room_ac",
        unique_id="us_room_ac",
        attributes={"current_temperature": 68.0},
    )
    mgr = TemperatureInputManager(
        hass,
        [TemperatureSourceConfig(physical, "current_temperature")],
    )
    snap = mgr.recalculate()
    assert snap.control_temperature_c == 20.0


def test_parse_temperature_sources_from_entry_data() -> None:
    raw = [{"entity_id": "sensor.a"}, {"entity_id": "climate.x", "attribute": "current_temperature"}]
    parsed = parse_temperature_sources(raw)
    assert len(parsed) == 2
    assert parsed[1].attribute == "current_temperature"


async def test_integration_uses_physical_fallback_without_sources(
    hass, kitchen_physical_climate: str
) -> None:
    with track_climate_service_calls(hass) as calls:
        entry = await setup_config_entry(
            hass,
            build_config_entry_data(
                physical_climate_entity_id=kitchen_physical_climate,
                room_name="Kitchen",
            ),
            entry_id="temp_fallback",
        )
        await hass.async_block_till_done()

    coord = entry.runtime_data.coordinator
    snap = coord._temperature_manager.snapshot if coord._temperature_manager else None
    assert snap is not None
    assert snap.control_temperature_c == 22.0
    assert not any(c[2].get("entity_id") == kitchen_physical_climate for c in calls)
