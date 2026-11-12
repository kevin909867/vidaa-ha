"""Coordinator wiring the VIDAA client into Home Assistant."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .vidaa_client import VidaaClient

_LOGGER = logging.getLogger(__name__)


class VidaaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Push-based coordinator for one VIDAA TV."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: VidaaClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=None,
        )
        self.client = client
        self.entry = entry
        client.add_listener(self._handle_client_data)

    @callback
    def _handle_client_data(self, data: dict[str, Any]) -> None:
        self.async_set_updated_data(data)

    async def _async_update_data(self) -> dict[str, Any]:
        return self.client.data

    async def async_stop_client(self) -> None:
        """Detach the listener and stop the MQTT client."""
        self.client.remove_listener(self._handle_client_data)
        await self.client.async_stop()
