"""Poll the logger and persist the daily energy estimate."""

import logging
from datetime import timedelta
from time import monotonic
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import const
from .client import RenonFlexError, async_read_registers
from .energy import DailyEnergy

_LOGGER = logging.getLogger(__name__)


class RenonFlexCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Read the logger once per scan interval using a short-lived connection."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{const.DOMAIN}_{entry.data[const.CONF_HOST]}",
            update_interval=timedelta(seconds=const.DEFAULT_SCAN_INTERVAL),
        )
        self._connection = entry.data
        self._energy = DailyEnergy()
        self._store = Store[dict[str, Any]](hass, 1, f"{const.DOMAIN}.{entry.entry_id}")
        self._loaded = False
        self._save_pending = False

    async def _async_setup(self) -> None:
        """Restore today's estimate without counting Home Assistant downtime."""
        stored = await self._store.async_load()
        if stored and stored.get("day") == dt_util.now().date().isoformat():
            self._energy.day = stored["day"]
            self._energy.kwh = max(0.0, float(stored["kwh"]))
        self._loaded = True

    @callback
    def _energy_data(self) -> dict[str, Any]:
        """Return a fresh snapshot for storage."""
        self._save_pending = False
        return {"day": self._energy.day, "kwh": self._energy.kwh}

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            registers = await async_read_registers(self._connection)
        except RenonFlexError as err:
            self._energy.reset_sample()
            raise UpdateFailed(str(err)) from err

        data: dict[str, Any] = {
            const.STATE_KEY: const.STATE_MAP.get(
                registers[const.STATE_REGISTER_INDEX], "unknown"
            )
        }
        for reg in const.REGISTERS:
            data[reg.key] = registers[reg.index] * reg.scale
        data[const.ENERGY_KEY] = self._energy.update(
            data["power_active"], dt_util.now(), monotonic()
        )
        if not self._save_pending:
            self._save_pending = True
            self._store.async_delay_save(self._energy_data, 60)
        return data

    async def async_shutdown(self) -> None:
        """Stop polling and flush the estimate on unload or shutdown."""
        await super().async_shutdown()
        if self._loaded:
            await self._store.async_save(self._energy_data())
