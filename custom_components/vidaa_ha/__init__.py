"""The VIDAA TV integration."""

from __future__ import annotations

import logging
import ssl
from dataclasses import dataclass
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_CERTFILE,
    CONF_HOST,
    CONF_KEYFILE,
    CONF_MAC,
    CONF_PORT,
    DEFAULT_PORT,
    DOMAIN,
    HOMEKIT_REMOTE_KEYS,
    LEGACY_SUBDEVICE_TARGETS,
)
from .coordinator import VidaaCoordinator
from .vidaa_client import (
    VidaaClient,
    VidaaCommandError,
    VidaaConnectionError,
)

_LOGGER = logging.getLogger(__name__)

HOMEKIT_REMOTE_EVENT = "homekit_tv_remote_key_pressed"

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
    _async_migrate_legacy_devices(hass, entry)
    _async_register_homekit_remote_keys(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VidaaConfigEntry) -> bool:
    """Unload a configured TV."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.coordinator.async_stop_client()
    return unloaded


def _async_migrate_legacy_devices(
    hass: HomeAssistant, entry: VidaaConfigEntry
) -> None:
    """Move entities from the old sub-devices and remove the empty devices."""
    devices = dr.async_get(hass)
    entities = er.async_get(hass)
    for old_key, target_key in LEGACY_SUBDEVICE_TARGETS.items():
        old_device = devices.async_get_device(
            identifiers={(DOMAIN, f"{entry.entry_id}_{old_key}")}
        )
        if old_device is None:
            continue
        target_id = (
            entry.entry_id
            if target_key is None
            else f"{entry.entry_id}_{target_key}"
        )
        target_device = devices.async_get_device(
            identifiers={(DOMAIN, target_id)}
        )
        old_entities = er.async_entries_for_device(
            entities, old_device.id, include_disabled_entities=True
        )
        if target_device is None:
            if not old_entities:
                devices.async_remove_device(old_device.id)
            continue
        for entity in old_entities:
            entities.async_update_entity(
                entity.entity_id, device_id=target_device.id
            )
        devices.async_remove_device(old_device.id)


def _async_register_homekit_remote_keys(
    hass: HomeAssistant, entry: VidaaConfigEntry
) -> None:
    """Translate HomeKit television remote presses into VIDAA keys."""

    @callback
    def _handle_homekit_key(event: Event) -> None:
        entity_id = event.data.get("entity_id")
        key_name = event.data.get("key_name")
        if not entity_id or not key_name:
            return
        entity_entry = er.async_get(hass).async_get(str(entity_id))
        if (
            entity_entry is None
            or entity_entry.config_entry_id != entry.entry_id
            or entity_entry.domain not in ("media_player", "remote")
        ):
            return
        key = HOMEKIT_REMOTE_KEYS.get(str(key_name))
        if key is None:
            return
        hass.async_create_task(
            _async_send_homekit_key(entry, key),
            f"vidaa-ha HomeKit remote key {key_name}",
        )

    entry.async_on_unload(
        hass.bus.async_listen(HOMEKIT_REMOTE_EVENT, _handle_homekit_key)
    )


async def _async_send_homekit_key(
    entry: VidaaConfigEntry, key: str
) -> None:
    """Send a key selected in Apple Home's television remote widget."""
    try:
        await entry.runtime_data.client.async_send_key(key)
    except VidaaCommandError as err:
        _LOGGER.warning("Could not send HomeKit remote key %s: %s", key, err)


async def _async_reload_entry(
    hass: HomeAssistant, entry: VidaaConfigEntry
) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
