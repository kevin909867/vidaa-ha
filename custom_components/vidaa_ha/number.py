"""Writable picture-setting sliders for the VIDAA TV."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_CREATE_PICTURE_ENTITIES,
    DEFAULT_CREATE_PICTURE_ENTITIES,
    PICTURE_DEVICE,
    PICTURE_NUMBER_CONTROLS,
    SUNDEVICE_LABELS,
)
from .entity import VidaaEntity
from .vidaa_client import VidaaCommandError

if TYPE_CHECKING:
    from . import VidaaConfigEntry

PARALLEL_UPDATES = 0


def _find_menu(client: Any, menu_id: int) -> dict[str, Any] | None:
    for item in client.data.get("picture_settings", []):
        if str(item.get("menu_id")) == str(menu_id):
            return item
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VidaaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up known writable picture sliders."""
    if not entry.options.get(
        CONF_CREATE_PICTURE_ENTITIES, DEFAULT_CREATE_PICTURE_ENTITIES
    ):
        return
    client = entry.runtime_data.client
    entities = []
    for control in PICTURE_NUMBER_CONTROLS:
        if _find_menu(client, control["menu_id"]) is not None:
            entities.append(
                VidaaPictureNumber(
                    entry.runtime_data.coordinator, entry, control
                )
            )
    if entities:
        async_add_entities(entities)


class VidaaPictureNumber(VidaaEntity, NumberEntity):
    """One numeric picture setting."""

    _attr_mode = NumberMode.SLIDER
    _attr_native_step = 1

    def __init__(
        self,
        coordinator: Any,
        entry: VidaaConfigEntry,
        control: dict[str, Any],
    ) -> None:
        self._menu_id = int(control["menu_id"])
        super().__init__(
            coordinator,
            entry,
            f"picture_number_{self._menu_id}",
            name=control["name"],
            device_key=PICTURE_DEVICE,
            device_name=SUNDEVICE_LABELS[PICTURE_DEVICE],
        )
        self._attr_icon = control.get("icon")
        self._attr_native_min_value = control.get("min", 0)
        self._attr_native_max_value = control.get("max", 100)

    def _menu(self) -> dict[str, Any] | None:
        return _find_menu(self._client, self._menu_id)

    @property
    def native_value(self) -> float | None:
        item = self._menu()
        if item is None:
            return None
        try:
            return float(item.get("menu_value"))
        except (TypeError, ValueError):
            return None

    @property
    def available(self) -> bool:
        return self._client.connected and self._menu() is not None

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self._client.async_set_picture_menu(
                self._menu_id, round(value)
            )
        except VidaaCommandError as err:
            raise HomeAssistantError(str(err)) from err
