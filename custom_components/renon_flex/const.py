"""RENON Flex IFL register definitions and connection settings."""

from dataclasses import dataclass

DOMAIN = "renon_flex"
MANUFACTURER = "RENON"
MODEL = "FLEX-LV-EU-6K"
LOGGER_MODEL = "Stick Logger LSW-5"
DEVICE_NAME = "RENON FLEX"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_SLAVE_ID = "slave_id"
CONF_PROTOCOL = "protocol"
CONF_SERIAL = "serial"
CONF_TIMEOUT = "timeout"
PROTOCOL_MODBUS = "modbus_tcp"
PROTOCOL_SOLARMAN = "solarman"
DEFAULT_PORT = 502
DEFAULT_SLAVE_ID = 1
DEFAULT_SCAN_INTERVAL = 10
DEFAULT_TIMEOUT = 15

# Community profile, not an official RENON protocol specification:
# https://github.com/davidrapan/ha-solarman/blob/main/custom_components/solarman/inverter_definitions/renon_ifl.yaml
# FC03, PDU addresses (no 40001 offset). Multiword values are low word first,
# as implemented by the source profile's parser. Read only known contiguous
# registers: in particular, 0x2280 is NOT included between the PV power words.
PROFILE_NAME = "RENON Flex IFL (community)"
PROFILE_SOURCE = "https://github.com/davidrapan/ha-solarman/blob/main/custom_components/solarman/inverter_definitions/renon_ifl.yaml"


@dataclass(frozen=True)
class Register:
    """A measured value from the IFL profile, with engineering units."""

    key: str
    address: int
    scale: float = 1.0
    unit: str | None = None
    device_class: str | None = None
    state_class: str = "measurement"
    count: int = 1


REGISTERS: tuple[Register, ...] = (
    Register("voltage_dc", 0x1690, 0.1, "V", "voltage"),
    Register("current_dc", 0x1691, 0.1, "A", "current"),
    Register("voltage_dc2", 0x1692, 0.1, "V", "voltage"),
    Register("current_dc2", 0x1693, 0.1, "A", "current"),
    Register("power_pv1", 0x227F, 1.0, "W", "power"),
    Register("power_pv2", 0x2281, 1.0, "W", "power"),
    Register("voltage_ac", 0x3110, 0.1, "V", "voltage"),
    Register("current_ac", 0x3111, 0.1, "A", "current"),
    Register("energy_today", 0x3153, 0.001, "kWh", "energy", "total_increasing", 2),
)
READ_BLOCKS = ((0x1690, 4), (0x227F, 1), (0x2281, 1), (0x3110, 2), (0x3153, 2))
ENERGY_KEY = "energy_today"
