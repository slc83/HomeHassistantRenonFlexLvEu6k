"""Exercise UI flows, entry setup, sensor registration and restart on Core."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.renon_flex.client import RenonFlexError
from custom_components.renon_flex.coordinator import RenonFlexCoordinator

REGISTERS = [1000, 10, 360, 230, 3, 4, 2]
FLOW_READ = "custom_components.renon_flex.config_flow.async_read_registers"
POLL_READ = "custom_components.renon_flex.coordinator.async_read_registers"


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
    assert len(entities) == 8
    power = hass.states.get(entities["power_active"])
    assert power.state == "1000.0"
    assert (
        power.name == "RENON FLEX Potenza attiva"
        or power.name == "RENON FLEX Active power"
    )
    assert power.attributes["unit_of_measurement"] == "W"
    energy = hass.states.get(entities["energy_today"])
    assert energy.attributes["unit_of_measurement"] == "kWh"
    assert energy.attributes["state_class"] == "total_increasing"
    assert hass.states.get(entities["state"]).state == "working"

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


@pytest.mark.parametrize("today", [True, False])
async def test_energy_storage_restore(hass, entry, today):
    coordinator = RenonFlexCoordinator(hass, entry)
    day = dt_util.now().date().isoformat() if today else "2000-01-01"
    await coordinator._store.async_save({"day": day, "kwh": 1.25})
    await coordinator._async_setup()
    with patch(POLL_READ, return_value=REGISTERS):
        data = await coordinator._async_update_data()
    assert data["energy_today"] == (1.25 if today else 0)
    await coordinator.async_shutdown()
    snapshot = json.loads(Path(coordinator._store.path).read_text())
    assert snapshot["data"]["kwh"] == data["energy_today"]


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
