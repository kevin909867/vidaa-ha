"""Binary sensors for the VIDAA TV."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    SETTINGS_DEVICE,
    SUNDEVICE_LABELS,
)
from .entity import VidaaEntity

if TYPE_CHECKING:
    from . import VidaaConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VidaaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VIDAA binary sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            VidaaPowerBinarySensor(coordinator, entry),
            VidaaMutedBinarySensor(coordinator, entry),
            VidaaConnectedBinarySensor(coordinator, entry),
        ]
    )


class VidaaPowerBinarySensor(VidaaEntity, BinarySensorEntity):
    """On/off state of the TV."""

    _attr_name = "Power"
    _attr_device_class = BinarySensorDeviceClass.POWER

    def __init__(self, coordinator: Any, entry: VidaaConfigEntry) -> None:
        super().__init__(coordinator, entry, "power", name="Power", device_key=None)

    @property
    def is_on(self) -> bool | None:
        return self._client.power

    @property
    def available(self) -> bool:
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = dict(super().extra_state_attributes or {})
        state = self._client.data.get("state") or {}
        attrs.update(
            {
                "statetype": state.get("statetype"),
                "detail": self._client.detail,
                "power_source": "mqtt_state"
                if self._client.data.get("last_state")
                else "unknown",
            }
        )
        return attrs


class VidaaMutedBinarySensor(VidaaEntity, BinarySensorEntity):
    """Mute state reported by the TV."""

    _attr_name = "Muted"
    _attr_device_class = BinarySensorDeviceClass.SOUND

    def __init__(self, coordinator: Any, entry: VidaaConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "muted",
            name="Muted",
        )

    @property
    def is_on(self) -> bool | None:
        return self._client.data.get("muted")

    @property
    def available(self) -> bool:
        return self._client.connected and self._client.data.get("muted") is not None


class VidaaConnectedBinarySensor(VidaaEntity, BinarySensorEntity):
    """Whether the local MQTT session is connected."""

    _attr_name = "MQTT Connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Any, entry: VidaaConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "mqtt_connected",
            name="MQTT Connected",
            device_key=SETTINGS_DEVICE,
            device_name=SUNDEVICE_LABELS[SETTINGS_DEVICE],
        )

    @property
    def is_on(self) -> bool:
        return self._client.connected

    @property
    def available(self) -> bool:
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = dict(super().extra_state_attributes or {})
        attrs["client_id"] = self._client.client_id
        attrs["broker"] = f"{self._client.host}:{self._client.port}"
        return attrs
