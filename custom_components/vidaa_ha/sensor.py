"""Sensors for the VIDAA TV, including the full picture-settings tree."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_CREATE_DIAGNOSTICS,
    CONF_CREATE_PICTURE_ENTITIES,
    DEFAULT_CREATE_DIAGNOSTICS,
    DEFAULT_CREATE_PICTURE_ENTITIES,
    DIAGNOSTIC_SENSORS,
    SETTINGS_DEVICE,
    SUNDEVICE_LABELS,
)
from .entity import VidaaEntity
from .vidaa_client import normalize_mac

if TYPE_CHECKING:
    from . import VidaaConfigEntry

PARALLEL_UPDATES = 0


def _pretty_menu_name(name: str) -> str:
    name = str(name or "").strip()
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    for token in ("HDMI", "HDR", "RGB", "UHD", "MPEG", "OLED", "4K", "3D"):
        name = name.replace(token.title(), token)
    name = name.replace("3d", "3D").replace("Hdmi", "HDMI")
    return " ".join(name.split())


def _app_icon(client: Any) -> str | None:
    app_id = client.data.get("current_app_id")
    name = client.data.get("current_app")
    for app in client.data.get("apps", []):
        if (app_id and app.get("app_id") == app_id) or (
            name and app.get("display_name") == name
        ):
            return app.get("icon_url")
    return None


class VidaaStateSensor(VidaaEntity, SensorEntity):
    """A detailed live state such as the current app, input or Home."""

    _attr_name = "State"
    _attr_icon = "mdi:television"

    def __init__(self, coordinator: Any, entry: VidaaConfigEntry) -> None:
        super().__init__(
            coordinator, entry, "tv_state", name="State", device_key=None
        )

    @property
    def native_value(self) -> str | None:
        return self._client.detail

    @property
    def entity_picture(self) -> str | None:
        return _app_icon(self._client)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = dict(super().extra_state_attributes or {})
        data = self._client.data
        state = data.get("state") or {}
        attrs.update(
            {
                "statetype": state.get("statetype"),
                "power": data.get("power"),
                "current_app": data.get("current_app"),
                "current_app_id": data.get("current_app_id"),
                "current_app_url": data.get("current_app_url"),
                "current_source": data.get("current_source"),
                "current_source_id": data.get("current_source_id"),
                "channel_name": data.get("channel_name"),
                "channel_number": data.get("channel_number"),
                "program_title": data.get("program_title"),
                "volume": data.get("volume"),
                "muted": data.get("muted"),
                "hotel_mode": data.get("hotel_mode"),
                "hdr_mode": data.get("hdr_mode"),
                "audio_format": data.get("audio_format"),
                "audio_output": data.get("audio_output"),
                "sleep_timer": data.get("sleep_timer"),
                "last_state": data.get("last_state"),
                "raw_state": state,
            }
        )
        return attrs


class VidaaCurrentAppSensor(VidaaEntity, SensorEntity):
    """Currently running app."""

    _attr_name = "Current App"
    _attr_icon = "mdi:application"

    def __init__(self, coordinator: Any, entry: VidaaConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "current_app",
            name="Current App",
        )

    @property
    def native_value(self) -> str | None:
        return self._client.data.get("current_app")

    @property
    def entity_picture(self) -> str | None:
        return _app_icon(self._client)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = dict(super().extra_state_attributes or {})
        attrs.update(
            {
                "app_id": self._client.data.get("current_app_id"),
                "app_url": self._client.data.get("current_app_url"),
            }
        )
        return attrs


class VidaaCurrentSourceSensor(VidaaEntity, SensorEntity):
    """Currently selected physical input."""

    _attr_name = "Current Source"
    _attr_icon = "mdi:video-input-hdmi"

    def __init__(self, coordinator: Any, entry: VidaaConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "current_source",
            name="Current Source",
        )

    @property
    def native_value(self) -> str | None:
        return self._client.data.get("current_source")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = dict(super().extra_state_attributes or {})
        source_id = self._client.data.get("current_source_id")
        for source in self._client.data.get("sources", []):
            if source.get("source_id") == source_id:
                attrs.update(
                    {
                        "source_id": source.get("source_id"),
                        "is_signal": source.get("is_signal"),
                        "has_signal": source.get("has_signal"),
                        "is_lock": source.get("is_lock"),
                        "hotel_mode": source.get("hotel_mode"),
                    }
                )
                break
        return attrs


class VidaaVolumeSensor(VidaaEntity, SensorEntity):
    """Master volume."""

    _attr_name = "Volume"
    _attr_icon = "mdi:volume-high"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: Any, entry: VidaaConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "volume",
            name="Volume",
        )

    @property
    def native_value(self) -> int | None:
        return self._client.data.get("volume")


class VidaaChannelSensor(VidaaEntity, SensorEntity):
    """Current TV channel, when the TV reports one."""

    _attr_name = "Channel"
    _attr_icon = "mdi:television-guide"

    def __init__(self, coordinator: Any, entry: VidaaConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "channel",
            name="Channel",
        )

    @property
    def native_value(self) -> str | None:
        number = self._client.data.get("channel_number")
        name = self._client.data.get("channel_name")
        if number and name:
            return f"{number} {name}"
        return number or name

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = dict(super().extra_state_attributes or {})
        attrs.update(
            {
                "channel_number": self._client.data.get("channel_number"),
                "channel_name": self._client.data.get("channel_name"),
                "program_title": self._client.data.get("program_title"),
            }
        )
        return attrs


class VidaaHotelModeSensor(VidaaEntity, SensorEntity):
    """Hotel mode flag from the TV broadcast."""

    _attr_name = "Hotel Mode"
    _attr_icon = "mdi:office-building"

    def __init__(self, coordinator: Any, entry: VidaaConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "hotel_mode",
            name="Hotel Mode",
        )

    @property
    def native_value(self) -> str | None:
        value = self._client.data.get("hotel_mode")
        return None if value is None else str(value)


class VidaaDiagnosticSensor(VidaaEntity, SensorEntity):
    """One raw telemetry value reported by the TV."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: Any,
        entry: VidaaConfigEntry,
        spec: tuple[str, str, str, str, str],
    ) -> None:
        self._key, name, self._group, self._field, icon = spec
        super().__init__(
            coordinator,
            entry,
            f"diag_{self._key}",
            name=name,
            device_key=SETTINGS_DEVICE,
            device_name=SUNDEVICE_LABELS[SETTINGS_DEVICE],
        )
        self._attr_icon = icon

    @property
    def native_value(self) -> Any:
        value = self._client.data.get(self._group, {}).get(self._field)
        if value is None:
            return None
        if self._field in ("eth0", "wlan0"):
            try:
                return normalize_mac(str(value))
            except ValueError:
                return str(value)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = dict(super().extra_state_attributes or {})
        attrs["source_group"] = self._group
        attrs["source_field"] = self._field
        return attrs


class VidaaCountSensor(VidaaEntity, SensorEntity):
    """A count of discovered apps or inputs."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:counter"

    def __init__(
        self,
        coordinator: Any,
        entry: VidaaConfigEntry,
        key: str,
        name: str,
        data_key: str,
    ) -> None:
        self._data_key = data_key
        super().__init__(
            coordinator,
            entry,
            key,
            name=name,
            device_key=SETTINGS_DEVICE,
            device_name=SUNDEVICE_LABELS[SETTINGS_DEVICE],
        )

    @property
    def native_value(self) -> int:
        return len(self._client.data.get(self._data_key, []))


class VidaaLastUpdateSensor(VidaaEntity, SensorEntity):
    """Last time any MQTT message was received."""

    _attr_name = "Last Update"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Any, entry: VidaaConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "last_update",
            name="Last Update",
            device_key=SETTINGS_DEVICE,
            device_name=SUNDEVICE_LABELS[SETTINGS_DEVICE],
        )

    @property
    def native_value(self) -> datetime | None:
        value = self._client.data.get("last_update")
        if value is None:
            return None
        return datetime.fromtimestamp(float(value), tz=UTC)


class VidaaClientIdSensor(VidaaEntity, SensorEntity):
    """The MQTT/topic client ID used for this TV."""

    _attr_name = "MQTT Client ID"
    _attr_icon = "mdi:identifier"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Any, entry: VidaaConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "client_id",
            name="MQTT Client ID",
            device_key=SETTINGS_DEVICE,
            device_name=SUNDEVICE_LABELS[SETTINGS_DEVICE],
        )

    @property
    def native_value(self) -> str:
        return self._client.client_id


class VidaaBrokerSensor(VidaaEntity, SensorEntity):
    """Broker endpoint."""

    _attr_name = "Broker Endpoint"
    _attr_icon = "mdi:server-network"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Any, entry: VidaaConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "broker",
            name="Broker Endpoint",
            device_key=SETTINGS_DEVICE,
            device_name=SUNDEVICE_LABELS[SETTINGS_DEVICE],
        )

    @property
    def native_value(self) -> str:
        return f"{self._client.host}:{self._client.port}"


class VidaaPictureSensor(VidaaEntity, SensorEntity):
    """One read-only item from the TV's picture menu tree."""

    _attr_icon = "mdi:tune-variant"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: Any,
        entry: VidaaConfigEntry,
        item: dict[str, Any],
        name: str,
    ) -> None:
        self._menu_id = int(item["menu_id"])
        super().__init__(
            coordinator,
            entry,
            f"picture_{self._menu_id}",
            name=name,
            device_key=SETTINGS_DEVICE,
            device_name=SUNDEVICE_LABELS[SETTINGS_DEVICE],
        )

    def _item(self) -> dict[str, Any] | None:
        for item in self._client.data.get("picture_settings", []):
            if str(item.get("menu_id")) == str(self._menu_id):
                return item
        return None

    @property
    def native_value(self) -> Any:
        item = self._item()
        return None if item is None else item.get("menu_value")

    @property
    def available(self) -> bool:
        return self._client.connected and self._item() is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = dict(super().extra_state_attributes or {})
        item = self._item() or {}
        attrs.update(
            {
                "menu_id": item.get("menu_id"),
                "menu_value_type": item.get("menu_value_type"),
                "menu_biz_id": item.get("menu_biz_id"),
            }
        )
        return attrs


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VidaaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VIDAA sensors."""
    coordinator = entry.runtime_data.coordinator
    client = entry.runtime_data.client
    entities: list[SensorEntity] = [
        VidaaStateSensor(coordinator, entry),
        VidaaCurrentAppSensor(coordinator, entry),
        VidaaCurrentSourceSensor(coordinator, entry),
        VidaaVolumeSensor(coordinator, entry),
        VidaaChannelSensor(coordinator, entry),
        VidaaHotelModeSensor(coordinator, entry),
    ]

    if entry.options.get(
        CONF_CREATE_DIAGNOSTICS, DEFAULT_CREATE_DIAGNOSTICS
    ):
        entities.extend(
            VidaaDiagnosticSensor(coordinator, entry, spec)
            for spec in DIAGNOSTIC_SENSORS
        )
        entities.extend(
            [
                VidaaCountSensor(
                    coordinator, entry, "app_count", "Installed Apps", "apps"
                ),
                VidaaCountSensor(
                    coordinator, entry, "source_count", "Inputs", "sources"
                ),
                VidaaLastUpdateSensor(coordinator, entry),
                VidaaClientIdSensor(coordinator, entry),
                VidaaBrokerSensor(coordinator, entry),
            ]
        )

    if entry.options.get(
        CONF_CREATE_PICTURE_ENTITIES, DEFAULT_CREATE_PICTURE_ENTITIES
    ):
        items = [
            item
            for item in client.data.get("picture_settings", [])
            if item.get("menu_value") is not None
            and str(item.get("menu_value_type", "")).casefold()
            not in ("error", "action")
        ]
        name_counts: dict[str, int] = defaultdict(int)
        base_names: list[str] = []
        for item in items:
            base = _pretty_menu_name(
                item.get("menu_name") or f"Menu {item.get('menu_id')}"
            )
            base_names.append(base)
            name_counts[base] += 1
        seen: dict[str, int] = defaultdict(int)
        for item, base in zip(items, base_names):
            if name_counts[base] > 1:
                seen[base] += 1
                name = f"{base} ({seen[base]})"
            else:
                name = base
            entities.append(VidaaPictureSensor(coordinator, entry, item, name))

    async_add_entities(entities)
