"""Report profile compatibility without exporting host or logger serial."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import const


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Describe rejected blocks and the measurements currently available."""
    coordinator = entry.runtime_data
    return {
        "profile": const.PROFILE_NAME,
        "profile_source": const.PROFILE_SOURCE,
        "unsupported_blocks": [
            {"address": f"0x{address:04X}", "count": count}
            for address, count in sorted(coordinator.unsupported_blocks)
        ],
        "available_measurements": [
            key for key, value in coordinator.data.items() if value is not None
        ],
        "unavailable_measurements": [
            key for key, value in coordinator.data.items() if value is None
        ],
        "last_update_success": coordinator.last_update_success,
    }
