"""Read-only transport adapters for Modbus TCP and Solarman V5."""

import asyncio
import logging
import socket
from collections.abc import Mapping
from typing import Any

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusIOException
from pysolarmanv5 import PySolarmanV5Async
from pysolarmanv5.pysolarmanv5 import V5FrameError
from umodbus.exceptions import ModbusError

from . import const

_LOGGER = logging.getLogger(__name__)
CLOSE_TIMEOUT = 5


class RenonFlexError(Exception):
    """Communication with the logger failed."""

    def __init__(
        self,
        message: str,
        *,
        error_key: str = "cannot_connect",
        modbus_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.error_key = error_key
        self.modbus_code = modbus_code


def _modbus_error(code: int | None, context: str) -> RenonFlexError:
    """Keep device exceptions distinct from network connection failures."""
    key = {1: "unsupported_function", 2: "invalid_registers"}.get(code, "modbus_error")
    return RenonFlexError(
        f"{context}: Modbus exception code {code}",
        error_key=key,
        modbus_code=code,
    )


async def _async_read_block(
    client: AsyncModbusTcpClient | PySolarmanV5Async,
    solarman: bool,
    address: int,
    count: int,
    slave: int,
    context: str,
) -> list[int]:
    """Normalize device exceptions from the two transport libraries."""
    try:
        if solarman:
            return await client.read_holding_registers(
                register_addr=address, quantity=count
            )
        response = await client.read_holding_registers(
            address=address, count=count, device_id=slave
        )
        if isinstance(response, ModbusIOException):
            raise response
        if response.isError():
            raise _modbus_error(response.exception_code, context)
        return response.registers
    except ModbusError as err:
        raise _modbus_error(getattr(err, "error_code", None), context) from err


async def async_read_registers(
    data: Mapping[str, Any],
    *,
    blocks: tuple[tuple[int, int], ...] = const.READ_BLOCKS,
    allow_unsupported: bool = False,
    unsupported_blocks: set[tuple[int, int]] | None = None,
) -> list[int | None]:
    """Read ordered blocks sequentially over one connection; always close it."""
    host = data[const.CONF_HOST]
    port = int(data[const.CONF_PORT])
    slave = int(data[const.CONF_SLAVE_ID])
    timeout = float(data.get(const.CONF_TIMEOUT, const.DEFAULT_TIMEOUT))
    solarman = data.get(const.CONF_PROTOCOL) == const.PROTOCOL_SOLARMAN
    protocol = "Solarman V5" if solarman else "Modbus TCP"
    connection_context = f"{protocol} {host}:{port}, unit={slave}"
    context = connection_context
    if solarman:
        client = PySolarmanV5Async(
            host,
            int(data[const.CONF_SERIAL]),
            port=port,
            mb_slave_id=slave,
            socket_timeout=timeout,
            auto_reconnect=False,
            logger=_LOGGER,
        )
    else:
        client = AsyncModbusTcpClient(host, port=port, timeout=timeout, retries=0)
    phase = "connect"
    try:
        async with asyncio.timeout(timeout):
            if solarman:
                await client.connect()
            elif not await client.connect():
                raise RenonFlexError(
                    f"{context}: TCP connection failed; check whether this port is open"
                )
        phase = "read"
        values: list[int | None] = []
        for address, count in blocks:
            if (
                allow_unsupported
                and unsupported_blocks is not None
                and (address, count) in unsupported_blocks
            ):
                values.extend([None] * count)
                continue
            context = (
                f"{connection_context}: FC03 address=0x{address:04X} ({address}), "
                f"count={count}"
            )
            try:
                async with asyncio.timeout(timeout):
                    registers = await _async_read_block(
                        client, solarman, address, count, slave, context
                    )
            except RenonFlexError as err:
                if not allow_unsupported or err.modbus_code != 2:
                    raise
                _LOGGER.warning("Unsupported register block skipped: %s", err)
                if unsupported_blocks is not None:
                    unsupported_blocks.add((address, count))
                values.extend([None] * count)
                continue
            if len(registers) != count:
                raise RenonFlexError(
                    f"{context}: Unexpected register count: {len(registers)} "
                    f"(expected {count})",
                    error_key="invalid_response",
                )
            values.extend(registers)
        return values
    except RenonFlexError:
        raise
    except (TimeoutError, ModbusIOException) as err:
        raise RenonFlexError(
            f"{context}: {phase} timeout after {timeout:g}s; "
            f"{type(err).__name__}: {str(err).strip() or 'no response'}",
            error_key=f"{phase}_timeout",
        ) from err
    except ModbusError as err:
        raise _modbus_error(getattr(err, "error_code", None), context) from err
    except V5FrameError as err:
        raise RenonFlexError(
            f"{context}: invalid Solarman V5 response: {err}",
            error_key="protocol_error",
        ) from err
    except socket.gaierror as err:
        raise RenonFlexError(
            f"{context}: name resolution failed: {err}", error_key="invalid_host"
        ) from err
    except Exception as err:
        cause = err.__cause__ or err
        key = "cannot_connect" if phase == "connect" else "read_error"
        if isinstance(cause, socket.gaierror):
            key = "invalid_host"
        elif isinstance(cause, TimeoutError):
            key = f"{phase}_timeout"
        raise RenonFlexError(
            f"{context}: {phase} failed: {type(cause).__name__}: "
            f"{str(cause).strip() or 'no details'}",
            error_key=key,
        ) from err
    finally:
        try:
            if solarman:
                async with asyncio.timeout(CLOSE_TIMEOUT):
                    await client.disconnect()
            else:
                client.close()  # pymodbus close() is synchronous, also for async clients.
        except Exception:
            _LOGGER.debug("Error closing logger connection", exc_info=True)


async def async_read_data(
    data: Mapping[str, Any], *, unsupported_blocks: set[tuple[int, int]] | None = None
) -> dict[str, float | None]:
    """Decode supported IFL measurements, leaving rejected registers unavailable."""
    values = await async_read_registers(
        data, allow_unsupported=True, unsupported_blocks=unsupported_blocks
    )
    addresses = [
        address + i for address, count in const.READ_BLOCKS for i in range(count)
    ]
    raw = dict(zip(addresses, values, strict=True))
    result: dict[str, float | None] = {}
    for register in const.REGISTERS:
        if any(raw[register.address + i] is None for i in range(register.count)):
            result[register.key] = None
            continue
        words = [raw[register.address + i] for i in range(register.count)]
        if register.high_word_first:
            words.reverse()
        value = sum(word << (16 * i) for i, word in enumerate(words))
        bits = 16 * register.count
        if register.signed and value & (1 << (bits - 1)):
            value -= 1 << bits
        measured = round(value * register.scale, 6)
        if (register.min_value is not None and measured < register.min_value) or (
            register.max_value is not None and measured > register.max_value
        ):
            _LOGGER.debug("Out-of-range %s value ignored: %s", register.key, measured)
            result[register.key] = None
        else:
            result[register.key] = measured
    if all(value is None for value in result.values()):
        raise RenonFlexError(
            "The device rejected every block of the RENON Flex IFL profile; "
            "no measurements could be read.",
            error_key="invalid_registers",
        )
    pv1, pv2 = result["power_pv1"], result["power_pv2"]
    result["power_active"] = pv1 + pv2 if pv1 is not None and pv2 is not None else None
    return result
