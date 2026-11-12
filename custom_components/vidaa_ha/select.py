"""Input source selection for the VIDAA TV."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import INPUTS_DEVICE, SUNDEVICE_LABELS
from .entity import VidaaEntity
from .vidaa_client import VidaaCommandError

if TYPE_CHECKING:
    from . import VidaaConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VidaaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the source selector if the TV reported inputs."""
    if not entry.runtime_data.client.data.get("sources"):
        return
    async_add_entities(
        [VidaaSourceSelect(entry.runtime_data.coordinator, entry)]
    )


class VidaaSourceSelect(VidaaEntity, SelectEntity):
    """Choose a physical input on the TV."""

    _attr_name = "Source"
    _attr_icon = "mdi:video-input-hdmi"

    def __init__(self, coordinator: Any, entry: VidaaConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "source_select",
            name="Source",
            device_key=INPUTS_DEVICE,
            device_name=SUNDEVICE_LABELS[INPUTS_DEVICE],
        )

    @property
    def options(self) -> list[str]:
        return [
            source["display_name"]
            for source in self._client.data.get("sources", [])
            if source.get("display_name")
        ]

    @property
    def current_option(self) -> str | None:
        current_id = self._client.data.get("current_source_id")
        current_name = self._client.data.get("current_source")
        for source in self._client.data.get("sources", []):
            if current_id and source.get("source_id") == current_id:
                return source.get("display_name")
            if current_name and source.get("display_name") == current_name:
                return source.get("display_name")
        return current_name

    async def async_select_option(self, option: str) -> None:
        try:
            if not await self._client.async_change_source(option):
                raise HomeAssistantError(f"Unknown input: {option}")
        except VidaaCommandError as err:
            raise HomeAssistantError(str(err)) from err
