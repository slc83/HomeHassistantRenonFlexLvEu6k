"""Test the real pymodbus transport and the Solarman adapter."""

import asyncio
import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pysolarmanv5.pysolarmanv5 import NoSocketAvailableError
from umodbus.client.serial.redundancy_check import get_crc

from custom_components.renon_flex.client import RenonFlexError, async_read_registers

DATA = {"host": "127.0.0.1", "port": 502, "slave_id": 1}
REGISTERS = [1000, 10, 360, 230, 3, 4, 2]


async def read_test_registers(data):
    """Transport fixture: request a synthetic block independent of the IFL map."""
    return await async_read_registers(data, blocks=((0, 7),))


@pytest.mark.parametrize("error", [False, True])
async def test_real_modbus_tcp(error):
    closed = asyncio.Event()

    async def respond(reader, writer):
        try:
            header = await reader.readexactly(7)
            transaction, protocol, length, unit = struct.unpack(">HHHB", header)
            request = await reader.readexactly(length - 1)
            assert protocol == 0
            assert unit == 1
            assert request == struct.pack(">BHH", 3, 0, 7)
            payload = (
                bytes([0x83, 2]) if error else struct.pack(">BB7H", 3, 14, *REGISTERS)
            )
            writer.write(
                struct.pack(">HHHB", transaction, 0, len(payload) + 1, unit) + payload
            )
            await writer.drain()
            assert await reader.read() == b""
        finally:
            writer.close()
            await writer.wait_closed()
            closed.set()

    server = await asyncio.start_server(respond, "127.0.0.1", 0)
    async with server:
        port = server.sockets[0].getsockname()[1]
        if error:
            with pytest.raises(RenonFlexError, match="Modbus exception"):
                await read_test_registers({**DATA, "port": port})
        else:
            assert await read_test_registers({**DATA, "port": port}) == REGISTERS
        await asyncio.wait_for(closed.wait(), 2)


async def test_solarman_adapter():
    client = MagicMock()
    client.connect = AsyncMock(return_value=None)
    client.read_holding_registers = AsyncMock(return_value=REGISTERS)
    client.disconnect = AsyncMock()
    with patch(
        "custom_components.renon_flex.client.PySolarmanV5Async", return_value=client
    ) as factory:
        assert (
            await read_test_registers(
                {**DATA, "port": 8899, "protocol": "solarman", "serial": 123456789}
            )
            == REGISTERS
        )
    assert factory.call_args.args == ("127.0.0.1", 123456789)
    assert factory.call_args.kwargs["mb_slave_id"] == 1
    client.read_holding_registers.assert_awaited_once_with(register_addr=0, quantity=7)
    client.disconnect.assert_awaited_once()


@pytest.mark.parametrize("failure", ["connect", "short", "timeout", "cancel"])
async def test_failures_close_modbus_connection(failure):
    client = MagicMock()
    client.connect = AsyncMock(return_value=failure != "connect")
    response = MagicMock()
    response.isError.return_value = False
    response.registers = [0] if failure == "short" else REGISTERS
    client.read_holding_registers = AsyncMock(return_value=response)
    if failure == "timeout":
        client.read_holding_registers.side_effect = TimeoutError
    elif failure == "cancel":
        client.read_holding_registers.side_effect = asyncio.CancelledError
    with (
        patch(
            "custom_components.renon_flex.client.AsyncModbusTcpClient",
            return_value=client,
        ),
        pytest.raises(
            asyncio.CancelledError if failure == "cancel" else RenonFlexError
        ),
    ):
        await read_test_registers(DATA)
    client.close.assert_called_once()


async def test_solarman_failure_disconnects():
    client = MagicMock()
    client.connect = AsyncMock(side_effect=OSError("unreachable"))
    client.disconnect = AsyncMock()
    with (
        patch(
            "custom_components.renon_flex.client.PySolarmanV5Async", return_value=client
        ),
        pytest.raises(RenonFlexError, match="unreachable"),
    ):
        await read_test_registers({**DATA, "protocol": "solarman", "serial": 123})
    client.disconnect.assert_awaited_once()


@pytest.mark.parametrize("reply", ["valid", "address_error", "wrong_serial", "silent"])
async def test_real_solarman_v5(reply):
    """Use the real V5 client against a TCP server with independent framing."""
    closed = asyncio.Event()
    serial = 123456789

    async def respond(reader, writer):
        try:
            header = await reader.readexactly(11)
            length = struct.unpack("<H", header[1:3])[0]
            body = await reader.readexactly(length + 2)
            assert header[0] == 0xA5
            assert header[3:5] == b"\x10\x45"
            assert struct.unpack("<I", header[7:11])[0] == serial
            assert body[15:-2][:6] == struct.pack(">BBHH", 1, 3, 0, 7)
            if reply != "silent":
                rtu = (
                    b"\x01\x83\x02"
                    if reply == "address_error"
                    else struct.pack(">BBB7H", 1, 3, 14, *REGISTERS)
                )
                rtu += get_crc(rtu)
                payload = b"\x02" + bytes(13) + rtu
                response = (
                    b"\xa5"
                    + struct.pack("<H", len(payload))
                    + b"\x10\x15"
                    + header[5:7]
                    + struct.pack("<I", serial + (reply == "wrong_serial"))
                    + payload
                )
                response += bytes([sum(response[1:]) & 255, 0x15])
                writer.write(response)
                await writer.drain()
            await reader.read()
        finally:
            writer.close()
            await writer.wait_closed()
            closed.set()

    server = await asyncio.start_server(respond, "127.0.0.1", 0)
    async with server:
        data = {
            **DATA,
            "port": server.sockets[0].getsockname()[1],
            "protocol": "solarman",
            "serial": serial,
            "timeout": 0.5,
        }
        if reply == "valid":
            assert await read_test_registers(data) == REGISTERS
        else:
            with pytest.raises(RenonFlexError) as error:
                await read_test_registers(data)
            assert (
                error.value.error_key
                == {
                    "address_error": "invalid_registers",
                    "wrong_serial": "protocol_error",
                    "silent": "read_timeout",
                }[reply]
            )
        await asyncio.wait_for(closed.wait(), 2)


async def test_solarman_connect_failure_preserves_dns_cause():
    import socket

    client = MagicMock()
    cause = socket.gaierror(-2, "Name does not resolve")
    error = NoSocketAvailableError("Cannot open connection")
    error.__cause__ = cause
    client.connect = AsyncMock(side_effect=error)
    client.disconnect = AsyncMock()
    with (
        patch(
            "custom_components.renon_flex.client.PySolarmanV5Async", return_value=client
        ),
        pytest.raises(RenonFlexError) as result,
    ):
        await read_test_registers({**DATA, "protocol": "solarman", "serial": 123})
    assert result.value.error_key == "invalid_host"
    assert "Name does not resolve" in str(result.value)


async def test_rejected_blocks_are_cached_until_reload():
    client = MagicMock()
    client.connect = AsyncMock(return_value=True)
    response = MagicMock()
    response.isError.return_value = True
    response.exception_code = 2
    client.read_holding_registers = AsyncMock(return_value=response)
    unsupported = set()
    with patch(
        "custom_components.renon_flex.client.AsyncModbusTcpClient", return_value=client
    ):
        for _ in range(2):
            assert await async_read_registers(
                DATA,
                blocks=((0x227F, 1),),
                allow_unsupported=True,
                unsupported_blocks=unsupported,
            ) == [None]
    assert unsupported == {(0x227F, 1)}
    client.read_holding_registers.assert_awaited_once()


@pytest.mark.parametrize("code", [1, 4, 6, 11])
async def test_other_modbus_exceptions_are_not_ignored(code):
    client = MagicMock()
    client.connect = AsyncMock(return_value=True)
    response = MagicMock()
    response.isError.return_value = True
    response.exception_code = code
    client.read_holding_registers = AsyncMock(return_value=response)
    unsupported = set()
    with (
        patch(
            "custom_components.renon_flex.client.AsyncModbusTcpClient",
            return_value=client,
        ),
        pytest.raises(RenonFlexError) as error,
    ):
        await async_read_registers(
            DATA,
            blocks=((0x227F, 1),),
            allow_unsupported=True,
            unsupported_blocks=unsupported,
        )
    assert error.value.modbus_code == code
    assert not unsupported
