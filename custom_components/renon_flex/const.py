"""Constants for the RENON FLEX Stick Logger integration."""

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
PROTOCOL_MODBUS = "modbus_tcp"
PROTOCOL_SOLARMAN = "solarman"

DEFAULT_PORT = 502
DEFAULT_SLAVE_ID = 1
DEFAULT_SCAN_INTERVAL = 10  # seconds


@dataclass(frozen=True)
class Register:
    """A single holding register exposed by the Stick Logger.

    index:
        Position of the register inside the contiguous block read in a
        single Modbus request (0-based).
    scale:
        Multiplier applied to the raw 16-bit value to obtain the
        engineering value (e.g. 0.1 if the logger reports deciwatts).
    device_class / state_class:
        Home Assistant sensor class names (mapped to the matching enums
        in sensor.py).
    """

    key: str
    index: int
    scale: float = 1.0
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = None


# ---------------------------------------------------------------------------
# Modbus holding register map.
#
# pymodbus uses 0-based PDU addresses, so register "40001" in a classic
# Modbus map is address 0 here. This is the original project's assumed
# seven-register layout, NOT a manufacturer-verified RENON register map.
# Confirm addresses, data types, scales and states against the inverter's
# protocol documentation before relying on the readings. The logger is a
# transport; it does not define the inverter's register map.
# ---------------------------------------------------------------------------
FIRST_REGISTER = 0
REGISTER_COUNT = 7

REGISTERS: tuple[Register, ...] = (
    Register(
        key="power_active",
        index=0,
        unit="W",
        device_class="power",
        state_class="measurement",
    ),
    Register(key="power_reactive", index=1, unit="var", state_class="measurement"),
    Register(
        key="voltage_dc",
        index=2,
        unit="V",
        device_class="voltage",
        state_class="measurement",
    ),
    Register(
        key="voltage_ac",
        index=3,
        unit="V",
        device_class="voltage",
        state_class="measurement",
    ),
    Register(
        key="current_dc",
        index=4,
        unit="A",
        device_class="current",
        state_class="measurement",
    ),
    Register(
        key="current_ac",
        index=5,
        unit="A",
        device_class="current",
        state_class="measurement",
    ),
)

# Position of the inverter state register inside the block.
STATE_REGISTER_INDEX = 6

# Raw state register value -> human readable state.
# Adjust to match the state table in the logger manual.
STATE_MAP: dict[int, str] = {
    0: "off",
    1: "standby",
    2: "working",
    3: "fault",
}

# Keys used in the coordinator data dict.
STATE_KEY = "state"
ENERGY_KEY = "energy_today"
