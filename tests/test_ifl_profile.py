"""Exercise IFL addresses and conversions over real TCP/V5 transports."""

import asyncio
import struct
from unittest.mock import patch

import pytest
from umodbus.client.serial.redundancy_check import get_crc

from custom_components.renon_flex import const
from custom_components.renon_flex.client import RenonFlexError, async_read_data

WORDS = {
    0x1690: 3600,
    0x1691: 43,
    0x1692: 3550,
    0x1693: 21,
    0x227F: 1000,
    0x2281: 500,
    0x3110: 2305,
    0x3111: 65,
    0x3153: 0x2345,
    0x3154: 1,
    0x3140: 512,
    0x3141: 0xFF85,
    0x314A: 0xFB2E,
    0x3145: 785,
    0x3146: 0xFFC9,
    0x3119: 5002,
    0x2284: 0xFFFE,
    0x2285: 0xEE90,
    0x2288: 1,
    0x2289: 0x1170,
    0x3157: 12345,
    0x3158: 0,
    0x3165: 1000,
    0x3166: 2,
    0x316B: 2000,
    0x316C: 0,
    0x3155: 3000,
    0x3156: 0,
    0x317D: 4000,
    0x317E: 2,
    0x3167: 5000,
    0x3168: 2,
    0x316D: 6000,
    0x316E: 0,
    0x316F: 7000,
    0x3170: 0,
    0x317F: 8000,
    0x3180: 2,
    0x3181: 9000,
    0x3182: 2,
}


@pytest.mark.parametrize("solarman", [False, True])
@pytest.mark.parametrize(
    "rejected", [None, 0x1690, 0x227F, 0x2281, 0x3145, 0x316D, "all"]
)
async def test_ifl_real_transports(solarman, rejected):
    done = asyncio.Event()
    requests = []
    connections = []
    server_errors = []

    async def respond(reader, writer):
        connections.append(writer)
        try:
            while True:
                try:
                    header = await reader.readexactly(11 if solarman else 7)
                except asyncio.IncompleteReadError:
                    break
                if solarman:
                    length = struct.unpack("<H", header[1:3])[0]
                    body = await reader.readexactly(length + 2)
                    unit, function, address, count = struct.unpack(">BBHH", body[15:21])
                    assert header[3:5] == b"\x10\x45"
                else:
                    length = struct.unpack(">H", header[4:6])[0]
                    body = await reader.readexactly(length - 1)
                    unit = header[6]
                    function, address, count = struct.unpack(">BHH", body)
                assert function == 3
                assert unit == 1
                assert (address, count) in const.READ_BLOCKS
                requests.append((address, count))
                if address == rejected or rejected == "all":
                    pdu = bytes([0x83, 2])
                else:
                    values = [WORDS[address + i] for i in range(count)]
                    pdu = bytes([3, 2 * count]) + struct.pack(f">{count}H", *values)
                if solarman:
                    rtu = bytes([unit]) + pdu
                    payload = b"\x02" + bytes(13) + rtu + get_crc(rtu)
                    frame = (
                        b"\xa5"
                        + struct.pack("<H", len(payload))
                        + b"\x10\x15"
                        + header[5:11]
                        + payload
                    )
                    frame += bytes([sum(frame[1:]) & 255, 0x15])
                else:
                    frame = header[:4] + struct.pack(">HB", len(pdu) + 1, unit) + pdu
                writer.write(frame)
                await writer.drain()
        except (
            AssertionError,
            KeyError,
            ValueError,
            OSError,
            asyncio.IncompleteReadError,
        ) as err:
            server_errors.append(err)
        finally:
            writer.close()
            await writer.wait_closed()
            done.set()

    server = await asyncio.start_server(respond, "127.0.0.1", 0)
    async with server:
        data = {
            "host": "127.0.0.1",
            "port": server.sockets[0].getsockname()[1],
            "slave_id": 1,
            "serial": 123456789,
            "protocol": "solarman" if solarman else "modbus_tcp",
            "timeout": 1,
        }
        if rejected == "all":
            with pytest.raises(RenonFlexError) as error:
                await async_read_data(data)
            assert error.value.error_key == "invalid_registers"
            assert "every block" in str(error.value)
        else:
            result = await async_read_data(data)
            expected = {
                "voltage_dc": 360.0,
                "current_dc": 4.3,
                "voltage_dc2": 355.0,
                "current_dc2": 2.1,
                "power_pv1": 1000.0,
                "power_pv2": 500.0,
                "power_active": 1500.0,
                "voltage_ac": 230.5,
                "current_ac": 6.5,
                "energy_today": 74.565,
                "battery_voltage": 51.2,
                "battery_current": -1.23,
                "battery_power": -1234.0,
                "battery_soc": 78.5,
                "battery_temperature": -5.5,
                "grid_frequency": 50.02,
                "grid_power": -70000.0,
                "load_power": 70000.0,
                "load_energy_today": 12.345,
                "energy_total": 132.072,
                "grid_import_today": 2.0,
                "grid_export_today": 3.0,
                "grid_import_total": 135.072,
                "grid_export_total": 136.072,
                "battery_charge_today": 6.0,
                "battery_discharge_today": 7.0,
                "battery_charge_total": 139.072,
                "battery_discharge_total": 140.072,
            }
            if rejected is not None:
                address, count = next(
                    block for block in const.READ_BLOCKS if block[0] == rejected
                )
                for register in const.REGISTERS:
                    if address <= register.address < address + count:
                        expected[register.key] = None
                if rejected in (0x227F, 0x2281):
                    expected["power_active"] = None
            assert result == expected
        assert requests == list(const.READ_BLOCKS)
        await asyncio.wait_for(done.wait(), 2)
    assert len(connections) == 1
    assert not server_errors
    assert all(address > 0 for address, _ in requests)


def test_profile_blocks_cover_only_defined_words():
    defined = {reg.address + i for reg in const.REGISTERS for i in range(reg.count)}
    requested = {
        address + i for address, count in const.READ_BLOCKS for i in range(count)
    }
    assert defined == requested
    assert 0x2280 not in requested


@pytest.mark.parametrize("soc", [1001, 0xFFFF])
async def test_invalid_battery_percentage_is_unavailable(soc):
    words = {**WORDS, 0x3145: soc}
    raw_values = [
        words[address + i] for address, count in const.READ_BLOCKS for i in range(count)
    ]
    with patch(
        "custom_components.renon_flex.client.async_read_registers",
        return_value=raw_values,
    ):
        result = await async_read_data({})
    assert result["battery_soc"] is None
    assert result["battery_power"] == -1234.0
