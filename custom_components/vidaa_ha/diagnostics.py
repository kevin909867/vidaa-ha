"""Diagnostics support for the VIDAA TV integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostic data without certificate contents or state history."""
    client = entry.runtime_data.client
    data = client.data

    apps = []
    for app in data.get("apps", []):
        apps.append(
            {
                key: value
                for key, value in app.items()
                if key not in ("httpIcon", "icon_url")
            }
        )

    return {
        "entry": {
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "client": {
            "host": client.host,
            "port": client.port,
            "client_id": client.client_id,
            "connected": client.connected,
            "power": data.get("power"),
            "detail": data.get("detail"),
            "volume": data.get("volume"),
            "muted": data.get("muted"),
            "hotel_mode": data.get("hotel_mode"),
            "last_update": data.get("last_update"),
            "last_connected": data.get("last_connected"),
        },
        "device_info": data.get("device_info"),
        "tv_info": data.get("tv_info"),
        "capability": data.get("capability"),
        "state": data.get("state"),
        "apps": apps,
        "sources": data.get("sources"),
        "picture_settings": data.get("picture_settings"),
        "raw_topics": sorted(data.get("raw", {})),
    }
