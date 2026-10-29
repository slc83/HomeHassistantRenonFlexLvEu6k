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
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_TIMEOUT = 15

# Community profile, not an official RENON protocol specification:
# https://github.com/davidrapan/ha-solarman/blob/main/custom_components/solarman/inverter_definitions/renon_ifl.yaml
# FC03, PDU addresses (no 40001 offset). Multiword values default to low word
# first; grid/load power explicitly use high word first in the source profile.
# Read only known contiguous
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
    signed: bool = False
    high_word_first: bool = False
    min_value: float | None = None
    max_value: float | None = None


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
    Register("battery_voltage", 0x3140, 0.1, "V", "voltage"),
    Register("battery_current", 0x3141, 0.01, "A", "current", signed=True),
    Register("battery_power", 0x314A, 1.0, "W", "power", signed=True),
    Register("battery_soc", 0x3145, 0.1, "%", "battery", min_value=0, max_value=100),
    Register("battery_temperature", 0x3146, 0.1, "°C", "temperature", signed=True),
    Register("grid_frequency", 0x3119, 0.01, "Hz", "frequency"),
    Register(
        "grid_power",
        0x2284,
        1.0,
        "W",
        "power",
        count=2,
        signed=True,
        high_word_first=True,
    ),
    Register("load_power", 0x2288, 1.0, "W", "power", count=2, high_word_first=True),
    Register(
        "load_energy_today",
        0x3157,
        0.001,
        "kWh",
        "energy",
        "total_increasing",
        2,
        signed=True,
        min_value=0,
    ),
    Register("energy_total", 0x3165, 0.001, "kWh", "energy", "total_increasing", 2),
    Register(
        "grid_import_today", 0x316B, 0.001, "kWh", "energy", "total_increasing", 2
    ),
    Register(
        "grid_export_today", 0x3155, 0.001, "kWh", "energy", "total_increasing", 2
    ),
    Register(
        "grid_import_total", 0x317D, 0.001, "kWh", "energy", "total_increasing", 2
    ),
    Register(
        "grid_export_total", 0x3167, 0.001, "kWh", "energy", "total_increasing", 2
    ),
    Register(
        "battery_charge_today", 0x316D, 0.001, "kWh", "energy", "total_increasing", 2
    ),
    Register(
        "battery_discharge_today", 0x316F, 0.001, "kWh", "energy", "total_increasing", 2
    ),
    Register(
        "battery_charge_total", 0x317F, 0.001, "kWh", "energy", "total_increasing", 2
    ),
    Register(
        "battery_discharge_total", 0x3181, 0.001, "kWh", "energy", "total_increasing", 2
    ),
)
# Preserve the original block boundaries. Probe each additional measurement
# independently so a rejected temperature register cannot hide battery SOC.
READ_BLOCKS = (
    (0x1690, 4),
    (0x227F, 1),
    (0x2281, 1),
    (0x3110, 2),
    (0x3153, 2),
    *((register.address, register.count) for register in REGISTERS[9:]),
)
ENERGY_KEY = "energy_today"
