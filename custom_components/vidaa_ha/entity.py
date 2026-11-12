"""Shared entities and device hierarchy for the VIDAA integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_MAC,
    DOMAIN,
    MANUFACTURER,
)
from .coordinator import VidaaCoordinator
from .vidaa_client import VidaaClient, normalize_mac


def _main_device_info(entry: ConfigEntry, client: VidaaClient) -> DeviceInfo:
    data = client.data
    device = data.get("device_info", {})
    tv = data.get("tv_info", {})
    capability = data.get("capability", {})
    model = device.get("model_name") or entry.data.get("model") or "VIDAA TV"
    info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title or "VIDAA TV",
        manufacturer=MANUFACTURER,
        model=model,
        sw_version=device.get("tv_version") or entry.data.get("sw_version"),
        hw_version=capability.get("chipplatform"),
        serial_number=tv.get("deviceid") or entry.data.get("device_id"),
        configuration_url=(
            f"http://{entry.data.get('host')}:38400/"
            "MediaServer/rendererdevicedesc.xml"
        ),
    )
    mac = device.get("eth0") or entry.data.get(CONF_MAC)
    if mac:
        try:
            info["connections"] = {(CONNECTION_NETWORK_MAC, normalize_mac(mac))}
        except ValueError:
            pass
    return info


def _sub_device_info(
    entry: ConfigEntry,
    client: VidaaClient,
    key: str,
    name: str,
) -> DeviceInfo:
    device = client.data.get("device_info", {})
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{key}")},
        name=name,
        manufacturer=MANUFACTURER,
        model=device.get("model_name") or "VIDAA TV",
        sw_version=device.get("tv_version"),
        via_device=(DOMAIN, entry.entry_id),
    )


class VidaaEntity(CoordinatorEntity[VidaaCoordinator]):
    """Base entity for the TV and all of its logical sub-devices."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: VidaaCoordinator,
        entry: ConfigEntry,
        unique_id: str,
        *,
        name: str | None = None,
        device_key: str | None = None,
        device_name: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._client = coordinator.client
        self._attr_unique_id = f"{entry.entry_id}_{unique_id}"
        if name is not None:
            self._attr_name = name
        if device_key is None:
            self._attr_device_info = _main_device_info(entry, self._client)
        else:
            self._attr_device_info = _sub_device_info(
                entry,
                self._client,
                device_key,
                device_name or device_key.replace("_", " ").title(),
            )

    @property
    def available(self) -> bool:
        """Return whether the TV broker is connected."""
        return self._client.connected

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the connection details on every entity."""
        return {
            "vidaa_host": self._client.host,
            "vidaa_connected": self._client.connected,
        }
