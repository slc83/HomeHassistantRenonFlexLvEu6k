"""Test the real pymodbus transport and the Solarman adapter."""

import asyncio
import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.renon_flex.client import RenonFlexError, async_read_registers

DATA = {"host": "127.0.0.1", "port": 502, "slave_id": 1}
REGISTERS = [1000, 10, 360, 230, 3, 4, 2]


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
                await async_read_registers({**DATA, "port": port})
        else:
            assert await async_read_registers({**DATA, "port": port}) == REGISTERS
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
            await async_read_registers(
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
        await async_read_registers(DATA)
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
        await async_read_registers({**DATA, "protocol": "solarman", "serial": 123})
    client.disconnect.assert_awaited_once()
