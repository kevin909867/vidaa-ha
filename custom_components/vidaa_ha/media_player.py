"""Media player entity for a VIDAA TV."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaType,
)
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_INCLUDE_APPS_IN_SOURCES,
    DEFAULT_INCLUDE_APPS_IN_SOURCES,
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
    """Set up the VIDAA media player."""
    async_add_entities(
        [VidaaMediaPlayer(entry.runtime_data.coordinator, entry)]
    )


class VidaaMediaPlayer(VidaaEntity, MediaPlayerEntity):
    """The TV as a Home Assistant media player."""

    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.TV
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
    )

    def __init__(self, coordinator: Any, entry: VidaaConfigEntry) -> None:
        super().__init__(
            coordinator, entry, "media_player", name=None, device_key=None
        )

    @property
    def available(self) -> bool:
        """Always available so Wake-on-LAN can be attempted."""
        return True

    @property
    def assumed_state(self) -> bool:
        return self._client.power is None

    @property
    def state(self) -> str:
        if not self._client.connected:
            return STATE_OFF
        if self._client.power is None:
            return STATE_UNKNOWN
        return STATE_ON if self._client.power else STATE_OFF

    @property
    def volume_level(self) -> float | None:
        volume = self._client.data.get("volume")
        return None if volume is None else round(int(volume) / 100, 2)

    @property
    def is_volume_muted(self) -> bool | None:
        return self._client.data.get("muted")

    def _include_apps(self) -> bool:
        return bool(
            self._entry.options.get(
                CONF_INCLUDE_APPS_IN_SOURCES,
                DEFAULT_INCLUDE_APPS_IN_SOURCES,
            )
        )

    @property
    def source_list(self) -> list[str]:
        values: list[str] = []
        for source in self._client.data.get("sources", []):
            name = source.get("display_name")
            if name and name not in values:
                values.append(name)
        if self._include_apps():
            for app in self._client.data.get("apps", []):
                name = app.get("display_name")
                if name and name not in values:
                    values.append(name)
        return values

    @property
    def source(self) -> str | None:
        return self._client.data.get("current_app") or self._client.data.get(
            "current_source"
        )

    @property
    def app_name(self) -> str | None:
        return self._client.data.get("current_app")

    @property
    def media_title(self) -> str | None:
        return self._client.detail

    @property
    def media_content_type(self) -> MediaType | None:
        if self._client.data.get("current_app"):
            return MediaType.APP
        source_id = str(self._client.data.get("current_source_id") or "").upper()
        if source_id == "TV":
            return MediaType.CHANNEL
        return None

    @property
    def media_channel(self) -> str | None:
        number = self._client.data.get("channel_number")
        name = self._client.data.get("channel_name")
        if number and name:
            return f"{number} {name}"
        return number or name

    @property
    def entity_picture(self) -> str | None:
        app_id = self._client.data.get("current_app_id")
        name = self._client.data.get("current_app")
        for app in self._client.data.get("apps", []):
            if (app_id and app.get("app_id") == app_id) or (
                name and app.get("display_name") == name
            ):
                return app.get("icon_url")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = dict(super().extra_state_attributes or {})
        data = self._client.data
        state = data.get("state") or {}
        attrs.update(
            {
                "statetype": state.get("statetype"),
                "current_app": data.get("current_app"),
                "current_app_id": data.get("current_app_id"),
                "current_source": data.get("current_source"),
                "current_source_id": data.get("current_source_id"),
                "channel_name": data.get("channel_name"),
                "channel_number": data.get("channel_number"),
                "program_title": data.get("program_title"),
                "hotel_mode": data.get("hotel_mode"),
                "hdr_mode": data.get("hdr_mode"),
                "audio_format": data.get("audio_format"),
                "audio_output": data.get("audio_output"),
                "sleep_timer": data.get("sleep_timer"),
                "last_state": data.get("last_state"),
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

    async def async_set_volume_level(self, volume: float) -> None:
        # HomeKit's TelevisionSpeaker reports percentage values (0-100), while
        # Home Assistant's service normally supplies 0.0-1.0. Accept both so
        # the Apple Home volume control maps to the TV's 0-100 range.
        level = float(volume)
        if level > 1:
            level /= 100
        level = max(0.0, min(1.0, level))
        try:
            await self._client.async_set_volume(round(level * 100))
        except VidaaCommandError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_volume_up(self) -> None:
        try:
            await self._client.async_volume_up()
        except VidaaCommandError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_volume_down(self) -> None:
        try:
            await self._client.async_volume_down()
        except VidaaCommandError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_mute_volume(self, mute: bool) -> None:
        try:
            await self._client.async_mute(mute)
        except VidaaCommandError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_select_source(self, source: str) -> None:
        try:
            if not await self._client.async_select_source(source):
                raise HomeAssistantError(f"Unknown source or app: {source}")
        except VidaaCommandError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_play_media(
        self, media_type: str, media_id: str, **kwargs: Any
    ) -> None:
        try:
            found = await self._client.async_play_media(media_type, media_id)
        except VidaaCommandError as err:
            raise HomeAssistantError(str(err)) from err
        if not found:
            raise HomeAssistantError(f"Unknown app or media: {media_id}")

    async def async_media_play(self) -> None:
        try:
            await self._client.async_media_play()
        except VidaaCommandError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_media_pause(self) -> None:
        try:
            await self._client.async_media_pause()
        except VidaaCommandError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_media_stop(self) -> None:
        try:
            await self._client.async_media_stop()
        except VidaaCommandError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_media_next_track(self) -> None:
        try:
            await self._client.async_media_next()
        except VidaaCommandError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_media_previous_track(self) -> None:
        try:
            await self._client.async_media_previous()
        except VidaaCommandError as err:
            raise HomeAssistantError(str(err)) from err
