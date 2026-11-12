"""Buttons for apps, every remote key, inputs and maintenance actions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    APP_CATEGORY_ICONS,
    APP_CATEGORY_LABELS,
    CONF_CREATE_DIAGNOSTICS,
    CONF_CREATE_KEY_BUTTONS,
    DEFAULT_CREATE_DIAGNOSTICS,
    DEFAULT_CREATE_KEY_BUTTONS,
    INPUTS_DEVICE,
    REMOTE_GROUPS,
    SUNDEVICE_LABELS,
    SYSTEM_DEVICE,
    app_category,
    slugify,
)
from .entity import VidaaEntity
from .vidaa_client import VidaaCommandError, VidaaError

if TYPE_CHECKING:
    from . import VidaaConfigEntry

PARALLEL_UPDATES = 0


def _input_icon(source_id: str) -> str:
    upper = source_id.upper()
    if upper == "TV":
        return "mdi:television-classic"
    if upper.startswith("HDMI"):
        return "mdi:hdmi-port"
    if upper.startswith("AV"):
        return "mdi:video-input-component"
    return "mdi:video-input"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VidaaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up app, key, input and maintenance buttons."""
    coordinator = entry.runtime_data.coordinator
    client = entry.runtime_data.client
    entities: list[ButtonEntity] = []

    for app in client.data.get("apps", []):
        entities.append(VidaaAppButton(coordinator, entry, app))

    if entry.options.get(CONF_CREATE_KEY_BUTTONS, DEFAULT_CREATE_KEY_BUTTONS):
        for group in REMOTE_GROUPS:
            for name, key, icon in group["buttons"]:
                entities.append(
                    VidaaKeyButton(coordinator, entry, group, name, key, icon)
                )

    for source in client.data.get("sources", []):
        entities.append(VidaaSourceButton(coordinator, entry, source))

    if entry.options.get(
        CONF_CREATE_DIAGNOSTICS, DEFAULT_CREATE_DIAGNOSTICS
    ):
        entities.extend(
            [
                VidaaRefreshAppsButton(coordinator, entry),
                VidaaRefreshPictureButton(coordinator, entry),
                VidaaReconnectButton(coordinator, entry),
            ]
        )

    async_add_entities(entities)


class VidaaAppButton(VidaaEntity, ButtonEntity):
    """Launch one installed application."""

    def __init__(
        self,
        coordinator: Any,
        entry: VidaaConfigEntry,
        app: dict[str, Any],
    ) -> None:
        self._app = app
        self._app_id = str(app.get("app_id") or app.get("appId") or "")
        category = app_category(app.get("display_name") or app.get("name"))
        super().__init__(
            coordinator,
            entry,
            f"app_{self._app_id}",
            name=app.get("display_name") or app.get("name") or "App",
            device_key=f"apps_{category}",
            device_name=APP_CATEGORY_LABELS[category],
        )
        self._attr_icon = APP_CATEGORY_ICONS[category]
        if app.get("icon_url"):
            self._attr_entity_picture = app["icon_url"]

    async def async_press(self) -> None:
        try:
            await self._client.async_launch_app(self._app)
        except VidaaCommandError as err:
            raise HomeAssistantError(str(err)) from err


class VidaaKeyButton(VidaaEntity, ButtonEntity):
    """One physical remote key."""

    def __init__(
        self,
        coordinator: Any,
        entry: VidaaConfigEntry,
        group: dict[str, Any],
        name: str,
        key: str,
        icon: str,
    ) -> None:
        self._key = key
        super().__init__(
            coordinator,
            entry,
            f"key_{slugify(name)}_{slugify(key)}",
            name=name,
            device_key=group["key"],
            device_name=group["name"],
        )
        self._attr_icon = icon

    async def async_press(self) -> None:
        try:
            await self._client.async_send_key(self._key)
        except VidaaCommandError as err:
            raise HomeAssistantError(str(err)) from err


class VidaaSourceButton(VidaaEntity, ButtonEntity):
    """Switch to one physical input."""

    def __init__(
        self,
        coordinator: Any,
        entry: VidaaConfigEntry,
        source: dict[str, Any],
    ) -> None:
        self._source_id = source.get("source_id")
        super().__init__(
            coordinator,
            entry,
            f"source_{source['source_id']}",
            name=source.get("display_name") or source.get("source_id"),
            device_key=INPUTS_DEVICE,
            device_name=SUNDEVICE_LABELS[INPUTS_DEVICE],
        )
        self._attr_icon = _input_icon(str(self._source_id))

    async def async_press(self) -> None:
        try:
            await self._client.async_change_source(str(self._source_id))
        except VidaaCommandError as err:
            raise HomeAssistantError(str(err)) from err


class _VidaaSystemButton(VidaaEntity, ButtonEntity):
    """Base class for maintenance buttons."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: Any,
        entry: VidaaConfigEntry,
        key: str,
        name: str,
        icon: str,
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            key,
            name=name,
            device_key=SYSTEM_DEVICE,
            device_name=SUNDEVICE_LABELS[SYSTEM_DEVICE],
        )
        self._attr_icon = icon

    @property
    def available(self) -> bool:
        return True


class VidaaRefreshAppsButton(_VidaaSystemButton):
    """Re-query installed apps and reload entities if the list changed."""

    def __init__(self, coordinator: Any, entry: VidaaConfigEntry) -> None:
        super().__init__(
            coordinator, entry, "refresh_apps", "Refresh Apps", "mdi:refresh"
        )

    async def async_press(self) -> None:
        before = {app.get("app_id") for app in self._client.data.get("apps", [])}
        try:
            apps = await self._client.async_refresh_apps()
        except VidaaCommandError as err:
            raise HomeAssistantError(str(err)) from err
        after = {app.get("app_id") for app in apps}
        if before != after:
            await self.hass.config_entries.async_reload(self._entry.entry_id)


class VidaaRefreshPictureButton(_VidaaSystemButton):
    """Re-query the picture menu tree."""

    def __init__(self, coordinator: Any, entry: VidaaConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "refresh_picture",
            "Refresh Picture Settings",
            "mdi:tune-variant",
        )

    async def async_press(self) -> None:
        try:
            await self._client.async_refresh_picture_settings()
        except VidaaCommandError as err:
            raise HomeAssistantError(str(err)) from err


class VidaaReconnectButton(_VidaaSystemButton):
    """Restart the MQTT session."""

    def __init__(self, coordinator: Any, entry: VidaaConfigEntry) -> None:
        super().__init__(
            coordinator, entry, "reconnect", "Reconnect", "mdi:lan-connect"
        )

    async def async_press(self) -> None:
        try:
            await self._client.async_reconnect()
        except VidaaError as err:
            raise HomeAssistantError(str(err)) from err
