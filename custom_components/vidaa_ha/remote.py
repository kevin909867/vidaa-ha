"""Remote entity for the VIDAA TV."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from homeassistant.components.remote import RemoteEntity, RemoteEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_KEY_DELAY,
    DEFAULT_KEY_DELAY,
    REMOTE_COMMANDS,
    REMOTE_DEVICE,
    SUNDEVICE_LABELS,
)
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
    """Set up the VIDAA remote."""
    async_add_entities([VidaaRemote(entry.runtime_data.coordinator, entry)])


class VidaaRemote(VidaaEntity, RemoteEntity):
    """A remote that can send every key the TV accepts."""

    _attr_name = "Remote"
    # Home Assistant 2026.11 removed the explicit SEND_COMMAND flag; older
    # releases still need it. The fallback must be an (empty) RemoteEntityFeature:
    # HA's state_attributes tests `RemoteEntityFeature.ACTIVITY in
    # supported_features`, which raises TypeError on a plain int.
    _attr_supported_features = getattr(
        RemoteEntityFeature, "SEND_COMMAND", RemoteEntityFeature(0)
    )
    _attr_icon = "mdi:remote"

    def __init__(self, coordinator: Any, entry: VidaaConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "remote",
            name="Remote",
            device_key=REMOTE_DEVICE,
            device_name=SUNDEVICE_LABELS[REMOTE_DEVICE],
        )

    @property
    def is_on(self) -> bool | None:
        return self._client.power

    @property
    def available(self) -> bool:
        # Call the client even if MQTT dropped so Home Assistant surfaces a
        # useful "not connected" error instead of silently skipping the call.
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = dict(super().extra_state_attributes or {})
        attrs.update(
            {
                "detail": self._client.detail,
                "commands": REMOTE_COMMANDS,
            }
        )
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        try:
            await self._client.async_turn_on()
        except VidaaCommandError as err:
            raise HomeAssistantError(str(err)) from err
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self._client.async_turn_off()
        except VidaaCommandError as err:
            raise HomeAssistantError(str(err)) from err
        self.async_write_ha_state()

    async def async_send_command(
        self, command: Iterable[str], **kwargs: Any
    ) -> None:
        repeats = int(kwargs.get("num_repeats", 1) or 1)
        hold = float(kwargs.get("hold_secs", 0) or 0)
        delay = float(
            kwargs.get("delay_secs")
            or self._entry.options.get(CONF_KEY_DELAY, DEFAULT_KEY_DELAY)
            or 0
        )
        # Home Assistant normally supplies a list, but direct calls and older
        # releases can pass a single string. Without this, list("home") would
        # send h, o, m, e instead of KEY_HOME.
        commands = [command] if isinstance(command, str) else list(command)
        if not commands:
            return
        try:
            for _ in range(max(1, repeats)):
                for single in commands:
                    await self._client.async_send_key(single)
                    if hold > 0:
                        await asyncio.sleep(hold)
                    elif delay > 0:
                        await asyncio.sleep(delay)
        except VidaaCommandError as err:
            raise HomeAssistantError(str(err)) from err
