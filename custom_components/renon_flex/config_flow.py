"""UI configuration for the RENON FLEX integration."""

import logging
from ipaddress import ip_address
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from . import const
from .client import RenonFlexError, async_read_data

_LOGGER = logging.getLogger(__name__)


def _valid_host(host: str) -> bool:
    """Accept plain IP/hostnames; URLs and port suffixes belong in other fields."""
    try:
        ip_address(host)
    except ValueError:
        return (
            bool(host)
            and not any(char in host for char in "/:#?@")
            and not any(char.isspace() for char in host)
        )
    return True


USER_SCHEMA = vol.Schema(
    {
        vol.Required(const.CONF_HOST): vol.All(str, vol.Strip, vol.Length(min=1)),
        vol.Required(const.CONF_PROTOCOL, default=const.PROTOCOL_MODBUS): vol.In(
            {
                const.PROTOCOL_MODBUS: "Modbus TCP",
                const.PROTOCOL_SOLARMAN: "Solarman V5",
            }
        ),
        vol.Required(const.CONF_PORT, default=const.DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
        vol.Required(const.CONF_SLAVE_ID, default=const.DEFAULT_SLAVE_ID): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=247)
        ),
        vol.Optional(const.CONF_SERIAL): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=0xFFFFFFFF)
        ),
        vol.Required(const.CONF_TIMEOUT, default=const.DEFAULT_TIMEOUT): vol.All(
            vol.Coerce(int), vol.Range(min=3, max=60)
        ),
    }
)


class RenonFlexConfigFlow(ConfigFlow, domain=const.DOMAIN):
    """Validate the connection without creating a temporary coordinator."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_connection_step(user_input, "user")

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change IP, port or transport while preserving existing entities."""
        return await self._async_connection_step(user_input, "reconfigure")

    async def _async_connection_step(
        self, user_input: dict[str, Any] | None, step_id: str
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        error_detail = ""
        if user_input is not None:
            if step_id == "user" and self._async_current_entries():
                return self.async_abort(reason="single_instance_allowed")
            data = USER_SCHEMA(user_input)
            if not _valid_host(data[const.CONF_HOST]):
                errors[const.CONF_HOST] = "invalid_host"
            elif (
                data[const.CONF_PROTOCOL] == const.PROTOCOL_SOLARMAN
                and const.CONF_SERIAL not in data
            ):
                errors[const.CONF_SERIAL] = "serial_required"
            else:
                try:
                    await async_read_data(data)
                except RenonFlexError as err:
                    _LOGGER.warning(
                        "Logger validation failed (%s): %s", err.error_key, err
                    )
                    errors["base"] = err.error_key
                    error_detail = str(err)
                else:
                    if step_id == "reconfigure":
                        return self.async_update_reload_and_abort(
                            self._get_reconfigure_entry(), data=data
                        )
                    return self.async_create_entry(
                        title=f"{const.DEVICE_NAME} {data[const.CONF_HOST]}", data=data
                    )
        suggested = user_input
        if suggested is None and step_id == "reconfigure":
            suggested = dict(self._get_reconfigure_entry().data)
        schema = self.add_suggested_values_to_schema(USER_SCHEMA, suggested)
        return self.async_show_form(
            step_id=step_id,
            data_schema=schema,
            errors=errors,
            description_placeholders={"error_detail": error_detail},
        )
