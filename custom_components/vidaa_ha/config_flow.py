"""Config and options flow for the VIDAA TV integration."""

from __future__ import annotations

import html
import re
import ssl
from pathlib import Path
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigEntry, OptionsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_CERTFILE,
    CONF_CLIENT_ID,
    CONF_CREATE_DIAGNOSTICS,
    CONF_CREATE_KEY_BUTTONS,
    CONF_CREATE_PICTURE_ENTITIES,
    CONF_HOST,
    CONF_INCLUDE_APPS_IN_SOURCES,
    CONF_KEY_DELAY,
    CONF_KEYFILE,
    CONF_MAC,
    CONF_NAME,
    CONF_PORT,
    CONF_WOL,
    DEFAULT_CREATE_DIAGNOSTICS,
    DEFAULT_CREATE_KEY_BUTTONS,
    DEFAULT_CREATE_PICTURE_ENTITIES,
    DEFAULT_INCLUDE_APPS_IN_SOURCES,
    DEFAULT_KEY_DELAY,
    DEFAULT_PORT,
    DEFAULT_WOL,
    DOMAIN,
)
from .vidaa_client import VidaaClient, VidaaConnectionError, normalize_mac

_MAC_RE = re.compile(r"mac=([0-9a-fA-F]{12})")
_NAME_RE = re.compile(r"<friendlyName>(.*?)</friendlyName>", re.DOTALL)
_MODEL_RE = re.compile(r"<modelName>(.*?)</modelName>", re.DOTALL)


def _bundled(filename: str) -> str:
    return str(Path(__file__).parent / "certs" / filename)


async def _discover_tv(
    hass: HomeAssistant, host: str
) -> dict[str, str | None]:
    """Read identity from the TV's unauthenticated UPnP descriptor."""
    result: dict[str, str | None] = {
        "mac": None,
        "name": None,
        "model": None,
    }
    session = async_get_clientsession(hass)
    url = f"http://{host}:38400/MediaServer/rendererdevicedesc.xml"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
            if resp.status != 200:
                return result
            text = await resp.text()
    except (aiohttp.ClientError, TimeoutError, OSError):
        return result

    if match := _MAC_RE.search(text):
        result["mac"] = match.group(1)
    if match := _NAME_RE.search(text):
        result["name"] = html.unescape(match.group(1)).strip()
    if match := _MODEL_RE.search(text):
        result["model"] = html.unescape(match.group(1)).strip()
    return result


async def _validate(
    host: str,
    port: int,
    mac: str,
) -> VidaaClient:
    client = VidaaClient(
        host,
        mac,
        port=port,
        certfile=_bundled("vidaa_client.pem"),
        keyfile=_bundled("vidaa_client.key"),
    )
    await client.async_start(startup_timeout=18)
    return client


class VidaaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle adding a VIDAA TV."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))
            discovered = await _discover_tv(self.hass, host)

            raw_mac = str(user_input.get(CONF_MAC) or discovered.get("mac") or "")
            try:
                mac = normalize_mac(raw_mac)
            except ValueError:
                errors[CONF_MAC] = "invalid_mac"
                mac = ""

            if not errors and not mac:
                errors["base"] = "mac_not_found"
                description_placeholders["host"] = host

            client: VidaaClient | None = None
            if not errors:
                try:
                    client = await _validate(host, port, mac)
                except (VidaaConnectionError, OSError, ssl.SSLError):
                    errors["base"] = "cannot_connect"
                except ValueError:
                    errors[CONF_MAC] = "invalid_mac"

            if client is not None:
                try:
                    device = client.data.get("device_info", {})
                    tv = client.data.get("tv_info", {})
                    if not device:
                        errors["base"] = "cannot_connect"
                    else:
                        await self.async_set_unique_id(
                            mac.replace(":", "").upper()
                        )
                        self._abort_if_unique_id_configured()
                        title = (
                            str(user_input.get(CONF_NAME) or "").strip()
                            or str(device.get("tv_name") or "").strip()
                            or str(discovered.get("name") or "").strip()
                            or "VIDAA TV"
                        )
                        data = {
                            CONF_HOST: host,
                            CONF_PORT: port,
                            CONF_MAC: mac,
                            CONF_CLIENT_ID: client.client_id,
                            CONF_CERTFILE: _bundled("vidaa_client.pem"),
                            CONF_KEYFILE: _bundled("vidaa_client.key"),
                            "name": title,
                            "model": device.get("model_name"),
                            "sw_version": device.get("tv_version"),
                            "device_id": tv.get("deviceid"),
                            "feature_code": tv.get("featurecode"),
                            "ethernet_mac": device.get("eth0"),
                            "wifi_mac": device.get("wlan0"),
                        }
                        return self.async_create_entry(
                            title=title,
                            data=data,
                            options={
                                CONF_WOL: DEFAULT_WOL,
                                CONF_KEY_DELAY: DEFAULT_KEY_DELAY,
                                CONF_INCLUDE_APPS_IN_SOURCES: DEFAULT_INCLUDE_APPS_IN_SOURCES,
                                CONF_CREATE_KEY_BUTTONS: DEFAULT_CREATE_KEY_BUTTONS,
                                CONF_CREATE_PICTURE_ENTITIES: DEFAULT_CREATE_PICTURE_ENTITIES,
                                CONF_CREATE_DIAGNOSTICS: DEFAULT_CREATE_DIAGNOSTICS,
                            },
                        )
                finally:
                    await client.async_stop()

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_NAME): str,
                vol.Optional(CONF_MAC): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return VidaaOptionsFlow()


class VidaaOptionsFlow(OptionsFlow):
    """Options for a configured TV."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_WOL, default=options.get(CONF_WOL, DEFAULT_WOL)
                ): bool,
                vol.Optional(
                    CONF_KEY_DELAY,
                    default=options.get(CONF_KEY_DELAY, DEFAULT_KEY_DELAY),
                ): vol.All(vol.Coerce(float), vol.Range(min=0, max=2)),
                vol.Optional(
                    CONF_INCLUDE_APPS_IN_SOURCES,
                    default=options.get(
                        CONF_INCLUDE_APPS_IN_SOURCES,
                        DEFAULT_INCLUDE_APPS_IN_SOURCES,
                    ),
                ): bool,
                vol.Optional(
                    CONF_CREATE_KEY_BUTTONS,
                    default=options.get(
                        CONF_CREATE_KEY_BUTTONS, DEFAULT_CREATE_KEY_BUTTONS
                    ),
                ): bool,
                vol.Optional(
                    CONF_CREATE_PICTURE_ENTITIES,
                    default=options.get(
                        CONF_CREATE_PICTURE_ENTITIES,
                        DEFAULT_CREATE_PICTURE_ENTITIES,
                    ),
                ): bool,
                vol.Optional(
                    CONF_CREATE_DIAGNOSTICS,
                    default=options.get(
                        CONF_CREATE_DIAGNOSTICS, DEFAULT_CREATE_DIAGNOSTICS
                    ),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
