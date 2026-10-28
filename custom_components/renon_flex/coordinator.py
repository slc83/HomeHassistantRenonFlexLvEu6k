"""Read the measured values from the RENON Flex IFL profile."""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import const
from .client import RenonFlexError, async_read_data

_LOGGER = logging.getLogger(__name__)


class RenonFlexCoordinator(DataUpdateCoordinator[dict[str, float | None]]):
    """Read all known blocks in one short-lived logger connection."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{const.DOMAIN}_{entry.data[const.CONF_HOST]}",
            update_interval=timedelta(seconds=const.DEFAULT_SCAN_INTERVAL),
        )
        self._connection = entry.data
        self.unsupported_blocks: set[tuple[int, int]] = set()

    async def _async_update_data(self) -> dict[str, float | None]:
        try:
            return await async_read_data(
                self._connection, unsupported_blocks=self.unsupported_blocks
            )
        except RenonFlexError as err:
            raise UpdateFailed(str(err)) from err
