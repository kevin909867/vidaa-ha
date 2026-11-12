"""The VIDAA TV integration."""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_CERTFILE,
    CONF_HOST,
    CONF_KEYFILE,
    CONF_MAC,
    CONF_PORT,
    DEFAULT_PORT,
)
from .coordinator import VidaaCoordinator
from .vidaa_client import VidaaClient, VidaaConnectionError

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.REMOTE,
    Platform.SELECT,
    Platform.SENSOR,
]


@dataclass
class VidaaRuntimeData:
    """Runtime objects for a configured TV."""

    client: VidaaClient
    coordinator: VidaaCoordinator


VidaaConfigEntry = ConfigEntry[VidaaRuntimeData]


def _bundled(filename: str) -> str:
    return str(Path(__file__).parent / "certs" / filename)


async def async_setup_entry(hass: HomeAssistant, entry: VidaaConfigEntry) -> bool:
    """Set up a VIDAA TV from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    mac = entry.data[CONF_MAC]
    certfile = entry.data.get(CONF_CERTFILE) or _bundled("vidaa_client.pem")
    keyfile = entry.data.get(CONF_KEYFILE) or _bundled("vidaa_client.key")

    client = VidaaClient(
        host,
        mac,
        port=port,
        certfile=certfile,
        keyfile=keyfile,
    )
    try:
        await client.async_start(startup_timeout=20)
    except (VidaaConnectionError, OSError, ssl.SSLError, ValueError) as err:
        raise ConfigEntryNotReady(
            f"Could not connect to the VIDAA TV at {host}: {err}"
        ) from err

    coordinator = VidaaCoordinator(hass, entry, client)
    coordinator.async_set_updated_data(client.data)
    entry.runtime_data = VidaaRuntimeData(client=client, coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VidaaConfigEntry) -> bool:
    """Unload a configured TV."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.coordinator.async_stop_client()
    return unloaded


async def _async_reload_entry(
    hass: HomeAssistant, entry: VidaaConfigEntry
) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
