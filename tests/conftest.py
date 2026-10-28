"""Run against real Home Assistant Core, without substituting its modules."""

from pathlib import Path

import pytest
from homeassistant import config_entries, loader
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry, device_registry, entity_registry, frame
from homeassistant.util import dt as dt_util


@pytest.fixture
async def hass(tmp_path):
    (tmp_path / "custom_components").symlink_to(
        Path(__file__).resolve().parents[1] / "custom_components"
    )
    instance = HomeAssistant(str(tmp_path))
    instance.config.skip_pip = True
    await instance.config.async_set_time_zone("Europe/Rome")
    loader.async_setup(instance)
    frame.async_setup(instance)
    instance.config_entries = config_entries.ConfigEntries(instance, {})
    await instance.config_entries.async_initialize()
    await area_registry.async_load(instance)
    device_registry.async_setup(instance)
    await device_registry.async_load(instance)
    await entity_registry.async_load(instance)
    yield instance
    await instance.async_stop(force=True)
    await instance.async_block_till_done()
    dt_util.set_default_time_zone(dt_util.UTC)


@pytest.fixture
def entry():
    return config_entries.ConfigEntry(
        domain="renon_flex",
        data={"host": "127.0.0.1", "port": 502, "slave_id": 1},
        title="RENON FLEX",
        source="user",
        version=1,
        minor_version=1,
        options={},
        unique_id=None,
        discovery_keys={},
        subentries_data=[],
    )
