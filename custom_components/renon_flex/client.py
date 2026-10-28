"""Read-only transport adapters for Modbus TCP and Solarman V5."""

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

from pymodbus.client import AsyncModbusTcpClient
from pysolarmanv5 import PySolarmanV5Async

from . import const

_LOGGER = logging.getLogger(__name__)
CONNECT_TIMEOUT = 5


class RenonFlexError(Exception):
    """Communication with the logger failed."""


async def async_read_registers(data: Mapping[str, Any]) -> list[int]:
    """Open one connection, read the configured block and always close it."""
    host = data[const.CONF_HOST]
    port = int(data[const.CONF_PORT])
    slave = int(data[const.CONF_SLAVE_ID])
    solarman = data.get(const.CONF_PROTOCOL) == const.PROTOCOL_SOLARMAN
    if solarman:
        client = PySolarmanV5Async(
            host,
            int(data[const.CONF_SERIAL]),
            port=port,
            mb_slave_id=slave,
            socket_timeout=CONNECT_TIMEOUT,
            auto_reconnect=False,
            logger=_LOGGER,
        )
    else:
        client = AsyncModbusTcpClient(
            host, port=port, timeout=CONNECT_TIMEOUT, retries=0
        )
    try:
        async with asyncio.timeout(CONNECT_TIMEOUT * 2):
            if solarman:
                await client.connect()
                registers = await client.read_holding_registers(
                    register_addr=const.FIRST_REGISTER, quantity=const.REGISTER_COUNT
                )
            else:
                if not await client.connect():
                    raise RenonFlexError(f"Could not connect to {host}:{port}")
                response = await client.read_holding_registers(
                    address=const.FIRST_REGISTER,
                    count=const.REGISTER_COUNT,
                    device_id=slave,
                )
                if response.isError():
                    raise RenonFlexError(f"Modbus exception: {response}")
                registers = response.registers
        if len(registers) != const.REGISTER_COUNT:
            raise RenonFlexError(f"Unexpected register count: {len(registers)}")
        return list(registers)
    except RenonFlexError:
        raise
    except Exception as err:
        raise RenonFlexError(f"Communication error with {host}:{port}: {err}") from err
    finally:
        try:
            if solarman:
                async with asyncio.timeout(CONNECT_TIMEOUT):
                    await client.disconnect()
            else:
                client.close()  # pymodbus close() is synchronous, also for async clients.
        except Exception:
            _LOGGER.debug("Error closing logger connection", exc_info=True)
