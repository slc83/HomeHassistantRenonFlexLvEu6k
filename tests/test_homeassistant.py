"""Exercise UI flows, entry setup, sensor registration and restart on Core."""

from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.renon_flex.client import RenonFlexError
from custom_components.renon_flex.diagnostics import async_get_config_entry_diagnostics

REGISTERS = {
    "power_active": 1000.0,
    "power_pv1": 600.0,
    "power_pv2": 400.0,
    "voltage_dc": 360.0,
    "current_dc": 3.0,
    "voltage_dc2": 350.0,
    "current_dc2": 2.0,
    "voltage_ac": 230.0,
    "current_ac": 4.0,
    "energy_today": 12.345,
    "battery_soc": 78.5,
    "battery_power": -1234.0,
    "battery_charge_today": 6.0,
    "battery_discharge_today": 7.0,
    "load_energy_today": 12.345,
}
FLOW_READ = "custom_components.renon_flex.config_flow.async_read_data"
POLL_READ = "custom_components.renon_flex.coordinator.async_read_data"


async def test_form_renders(hass):
    result = await hass.config_entries.flow.async_init(
        "renon_flex", context={"source": "user"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["data_schema"] is not None


async def test_flow_handles_failed_read(hass):
    with patch(FLOW_READ, side_effect=RenonFlexError("offline")):
        result = await hass.config_entries.flow.async_init(
            "renon_flex", context={"source": "user"}, data={"host": "127.0.0.1"}
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_solarman_requires_logger_serial(hass):
    with patch(FLOW_READ) as read:
        result = await hass.config_entries.flow.async_init(
            "renon_flex",
            context={"source": "user"},
            data={"host": "127.0.0.1", "port": 8899, "protocol": "solarman"},
        )
    assert result["errors"] == {"serial": "serial_required"}
    read.assert_not_called()


async def test_flow_creates_entry(hass):
    with (
        patch(FLOW_READ, return_value=REGISTERS),
        patch(POLL_READ, return_value=REGISTERS),
    ):
        result = await hass.config_entries.flow.async_init(
            "renon_flex", context={"source": "user"}, data={"host": "127.0.0.1"}
        )
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["port"] == 502
    assert result["result"].state == ConfigEntryState.LOADED


async def test_setup_sensors_unavailability_recovery_and_unload(hass, entry):
    with patch(POLL_READ, return_value=REGISTERS):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()
    assert entry.state == ConfigEntryState.LOADED
    registry = er.async_get(hass)
    entities = {
        item.unique_id.removeprefix(f"{entry.entry_id}-"): item.entity_id
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert len(entities) == 29
    power = hass.states.get(entities["power_active"])
    assert power.state == "1000.0"
    assert (
        power.name == "RENON FLEX Potenza FV totale"
        or power.name == "RENON FLEX Total PV power"
    )
    assert power.attributes["unit_of_measurement"] == "W"
    energy = hass.states.get(entities["energy_today"])
    assert energy.attributes["unit_of_measurement"] == "kWh"
    assert energy.attributes["state_class"] == "total_increasing"
    assert energy.state == "12.345"
    assert "state" not in entities
    assert "power_reactive" not in entities
    battery = hass.states.get(entities["battery_soc"])
    assert battery.state == "78.5"
    assert battery.attributes["unit_of_measurement"] == "%"
    assert battery.attributes["device_class"] == "battery"
    assert hass.states.get(entities["battery_power"]).state == "-1234.0"
    for key in ("battery_charge_today", "battery_discharge_today", "load_energy_today"):
        measured = hass.states.get(entities[key])
        assert measured.attributes["unit_of_measurement"] == "kWh"
        assert measured.attributes["state_class"] == "total_increasing"

    with patch(POLL_READ, side_effect=RenonFlexError("offline")):
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
    assert hass.states.get(entities["power_active"]).state == "unavailable"
    with patch(POLL_READ, return_value=REGISTERS):
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
    assert hass.states.get(entities["power_active"]).state == "1000.0"
    coordinator = entry.runtime_data
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state == ConfigEntryState.NOT_LOADED
    assert coordinator._shutdown_requested


async def test_first_refresh_retries_when_offline(hass, entry):
    with patch(POLL_READ, side_effect=RenonFlexError("offline")):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()
    assert entry.state == ConfigEntryState.SETUP_RETRY


async def test_energy_is_read_from_inverter_after_reload(hass, entry):
    with patch(POLL_READ, return_value=REGISTERS):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()
    assert entry.runtime_data.data["energy_today"] == 12.345
    with patch(POLL_READ, return_value={**REGISTERS, "energy_today": 12.678}):
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.runtime_data.data["energy_today"] == 12.678


async def test_duplicate_entry_aborts(hass, entry):
    with patch(POLL_READ, return_value=REGISTERS):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()
    with patch(FLOW_READ) as read:
        result = await hass.config_entries.flow.async_init(
            "renon_flex", context={"source": "user"}, data={"host": "127.0.0.2"}
        )
    assert result["type"] == FlowResultType.ABORT
    read.assert_not_called()


async def test_reconfigure_preserves_entry(hass, entry):
    with patch(POLL_READ, return_value=REGISTERS):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()
    result = await hass.config_entries.flow.async_init(
        "renon_flex",
        context={"source": "reconfigure", "entry_id": entry.entry_id},
    )
    assert result["step_id"] == "reconfigure"
    with (
        patch(FLOW_READ, return_value=REGISTERS),
        patch(POLL_READ, return_value=REGISTERS),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "127.0.0.2",
                "port": 8899,
                "protocol": "solarman",
                "serial": 123456789,
            },
        )
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["host"] == "127.0.0.2"
    assert entry.data["protocol"] == "solarman"
    assert entry.data["serial"] == 123456789
    assert entry.state == ConfigEntryState.LOADED


async def test_failed_reconfigure_keeps_existing_connection(hass, entry):
    with patch(POLL_READ, return_value=REGISTERS):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()
    with patch(FLOW_READ, side_effect=RenonFlexError("offline")):
        result = await hass.config_entries.flow.async_init(
            "renon_flex",
            context={"source": "reconfigure", "entry_id": entry.entry_id},
            data={"host": "127.0.0.2"},
        )
    assert result["errors"] == {"base": "cannot_connect"}
    assert entry.data["host"] == "127.0.0.1"
    assert entry.state == ConfigEntryState.LOADED


@pytest.mark.parametrize(
    "host", ["http://192.168.1.12", "192.168.1.12:8899", "192.168.1.12/path"]
)
async def test_invalid_host_never_opens_connection(hass, host):
    with patch(FLOW_READ) as read:
        result = await hass.config_entries.flow.async_init(
            "renon_flex", context={"source": "user"}, data={"host": host}
        )
    assert result["errors"] == {"host": "invalid_host"}
    read.assert_not_called()


@pytest.mark.parametrize("key", ["invalid_registers", "read_timeout", "protocol_error"])
async def test_flow_displays_actual_failure(hass, key, caplog):
    detail = "Solarman V5 192.168.1.12:8899: test diagnostic detail"
    with patch(FLOW_READ, side_effect=RenonFlexError(detail, error_key=key)):
        result = await hass.config_entries.flow.async_init(
            "renon_flex", context={"source": "user"}, data={"host": "192.168.1.12"}
        )
    assert result["errors"] == {"base": key}
    assert result["description_placeholders"]["error_detail"] == detail
    assert detail in caplog.text


async def test_partial_profile_can_be_configured(hass):
    partial = {**REGISTERS, "power_pv1": None, "power_active": None}
    with patch(FLOW_READ, return_value=partial), patch(POLL_READ, return_value=partial):
        result = await hass.config_entries.flow.async_init(
            "renon_flex", context={"source": "user"}, data={"host": "127.0.0.1"}
        )
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.state == ConfigEntryState.LOADED
    registry = er.async_get(hass)
    entities = {
        item.unique_id.removeprefix(f"{entry.entry_id}-"): item.entity_id
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert hass.states.get(entities["power_pv1"]).state == "unavailable"
    assert hass.states.get(entities["power_active"]).state == "unavailable"
    assert hass.states.get(entities["power_pv2"]).state == "400.0"
    assert hass.states.get(entities["voltage_dc"]).state == "360.0"
    estimated_id = entities["power_pv1_estimated"]
    estimated = hass.states.get(estimated_id)
    assert estimated.state == "1080.0"
    assert estimated.attributes["unit_of_measurement"] == "W"
    assert estimated.attributes["device_class"] == "power"
    assert estimated.attributes["state_class"] == "measurement"

    entry.runtime_data.async_set_updated_data({**partial, "current_dc": 0.0})
    await hass.async_block_till_done()
    assert hass.states.get(estimated_id).state == "0.0"
    entry.runtime_data.async_set_updated_data({**partial, "voltage_dc": None})
    await hass.async_block_till_done()
    assert hass.states.get(estimated_id).state == "unavailable"
    entry.runtime_data.async_set_updated_data({**partial, "current_dc": None})
    await hass.async_block_till_done()
    assert hass.states.get(estimated_id).state == "unavailable"
    entry.runtime_data.async_set_updated_data(partial)
    await hass.async_block_till_done()
    assert hass.states.get(estimated_id).state == "1080.0"
    assert hass.states.get(entities["energy_today"]).state == "12.345"

    entry.runtime_data.unsupported_blocks.add((0x227F, 1))
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["unsupported_blocks"] == [{"address": "0x227F", "count": 1}]
    assert "power_pv1" in diagnostics["unavailable_measurements"]
    assert "voltage_dc" in diagnostics["available_measurements"]
    assert "host" not in diagnostics
    assert "serial" not in diagnostics
