"""Async client for the local VIDAA MQTT broker.

This module deliberately has no Home Assistant imports so it can be exercised
standalone against a TV (see ``scripts/live_test.py``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import socket
import ssl
import time
from collections.abc import Callable, Iterable
from contextlib import suppress
from typing import Any

import aiomqtt

try:  # Home Assistant imports this as a package; the live test imports it directly.
    from .const import app_category as get_app_category
    from .const import clean_app_name, resolve_key
except ImportError:  # pragma: no cover - standalone probe path
    from const import app_category as get_app_category
    from const import clean_app_name, resolve_key

_LOGGER = logging.getLogger(__name__)


class VidaaError(Exception):
    """Base error for VIDAA communication."""


class VidaaConnectionError(VidaaError):
    """Raised when the TV cannot be reached or does not answer queries."""


class VidaaCommandError(VidaaError):
    """Raised when a command cannot be sent."""


def normalize_mac(mac: str | None) -> str:
    """Normalize a MAC address to lowercase colon notation."""
    cleaned = re.sub(r"[^0-9a-fA-F]", "", mac or "").lower()
    if len(cleaned) != 12:
        raise ValueError(f"Invalid MAC address: {mac!r}")
    return ":".join(cleaned[i : i + 2] for i in range(0, 12, 2))


def client_id_for_mac(mac: str) -> str:
    """Return the topic client ID this firmware uses for unicast replies."""
    cleaned = re.sub(r"[^0-9a-fA-F]", "", mac).upper()
    return f"{cleaned}$vidaa_common"


def _extract_icon(app: dict[str, Any]) -> str | None:
    icon = str(app.get("httpIcon") or "")
    if "iconDownload" in icon:
        icon = icon.split("iconDownload", 1)[1]
    if icon.startswith("http://") or icon.startswith("https://"):
        return icon
    return None


class VidaaClient:
    """Persistent connection to a VIDAA TV's local MQTT broker."""

    def __init__(
        self,
        host: str,
        mac: str,
        *,
        port: int = 36669,
        certfile: str,
        keyfile: str,
        client_id: str | None = None,
        username: str = "hisenseservice",
        password: str = "multimqttservice",
    ) -> None:
        self.host = host
        self.port = port
        self.mac = normalize_mac(mac)
        self.client_id = client_id or client_id_for_mac(self.mac)
        self.certfile = certfile
        self.keyfile = keyfile
        self.username = username
        self.password = password

        self.data: dict[str, Any] = {
            "device_info": {},
            "tv_info": {},
            "capability": {},
            "apps": [],
            "sources": [],
            "picture_settings": [],
            "sound_settings": [],
            "state": {},
            "volume": None,
            "muted": None,
            "hotel_mode": None,
            "power": None,
            "detail": None,
            "current_app": None,
            "current_app_id": None,
            "current_app_url": None,
            "current_source": None,
            "current_source_id": None,
            "channel_name": None,
            "channel_number": None,
            "program_title": None,
            "audio_output": None,
            "hdr_mode": None,
            "audio_format": None,
            "sleep_timer": None,
            "connected": False,
            "last_update": None,
            "last_state": None,
            "last_connected": None,
            "apps_updated": None,
            "sources_updated": None,
            "picture_updated": None,
            "raw": {},
        }

        self._listeners: set[Callable[[dict[str, Any]], None]] = set()
        self._pending: dict[str, list[asyncio.Future[Any]]] = {}
        self._task: asyncio.Task[None] | None = None
        self._listen_task: asyncio.Task[None] | None = None
        self._mqtt: aiomqtt.Client | None = None
        self._stopping = False
        self._first_ready = asyncio.Event()
        self._notify_handle: asyncio.TimerHandle | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    @property
    def connected(self) -> bool:
        """Return True while the MQTT session is established."""
        return bool(self.data.get("connected"))

    @property
    def power(self) -> bool | None:
        """Return the last known power state, or None if unknown."""
        return self.data.get("power")

    @property
    def detail(self) -> str | None:
        """Return a human-readable live state."""
        return self.data.get("detail")

    def add_listener(self, listener: Callable[[dict[str, Any]], None]) -> None:
        """Register a synchronous state listener."""
        self._listeners.add(listener)

    def remove_listener(self, listener: Callable[[dict[str, Any]], None]) -> None:
        """Unregister a state listener."""
        self._listeners.discard(listener)

    async def async_start(self, startup_timeout: float = 20.0) -> None:
        """Connect and load the initial state."""
        if self._task is not None and not self._task.done():
            await asyncio.wait_for(self._first_ready.wait(), startup_timeout)
            return

        self._stopping = False
        self._first_ready.clear()
        self._task = asyncio.create_task(
            self._run(), name=f"vidaa-ha {self.host}"
        )
        try:
            await asyncio.wait_for(self._first_ready.wait(), startup_timeout)
        except TimeoutError as err:
            await self.async_stop()
            raise VidaaConnectionError(
                f"Timed out connecting to the VIDAA broker at {self.host}:{self.port}"
            ) from err

        if not self.data["device_info"] and not self.data["tv_info"]:
            await self.async_stop()
            raise VidaaConnectionError(
                "Connected to the TV broker but received no device information. "
                "Check the MAC address / client ID and client certificate."
            )

    async def async_stop(self) -> None:
        """Stop the connection and cancel background work."""
        self._stopping = True
        if self._notify_handle is not None:
            self._notify_handle.cancel()
            self._notify_handle = None
        if self._listen_task is not None:
            self._listen_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._listen_task
            self._listen_task = None
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._mqtt = None
        self.data["connected"] = False

    async def async_reconnect(self) -> None:
        """Restart the MQTT session."""
        await self.async_stop()
        await self.async_start()

    async def _run(self) -> None:
        attempt = 0
        while not self._stopping:
            try:
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                context.load_cert_chain(self.certfile, self.keyfile)
                with suppress(Exception):
                    context.set_ciphers("DEFAULT@SECLEVEL=1")

                async with aiomqtt.Client(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    identifier=self.client_id,
                    clean_session=True,
                    keepalive=60,
                    timeout=8,
                    tls_context=context,
                    tls_insecure=True,
                ) as mqtt:
                    self._mqtt = mqtt
                    attempt = 0
                    self.data["connected"] = True
                    self.data["last_connected"] = time.time()
                    await mqtt.subscribe(f"/remoteapp/mobile/{self.client_id}/#")
                    await mqtt.subscribe("/remoteapp/mobile/broadcast/#")
                    self._notify()

                    self._listen_task = asyncio.create_task(
                        self._listen(mqtt), name=f"vidaa-ha listen {self.host}"
                    )
                    await self._initial_load()
                    self._first_ready.set()
                    self._notify()
                    await self._listen_task
            except asyncio.CancelledError:
                raise
            except aiomqtt.MqttError as err:
                _LOGGER.warning(
                    "VIDAA MQTT connection to %s failed: %s", self.host, err
                )
            except Exception:  # noqa: BLE001 - keep the reconnect loop alive
                _LOGGER.exception(
                    "Unexpected error in VIDAA connection to %s", self.host
                )
            finally:
                if self._listen_task is not None:
                    self._listen_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await self._listen_task
                    self._listen_task = None
                self._mqtt = None
                self.data["connected"] = False
                self._notify()

            if self._stopping:
                break
            attempt += 1
            delay = min(30, 2 ** min(attempt, 4))
            _LOGGER.debug(
                "Reconnecting to VIDAA TV %s in %ss (attempt %s)",
                self.host,
                delay,
                attempt,
            )
            await asyncio.sleep(delay)

    async def _listen(self, mqtt: aiomqtt.Client) -> None:
        async for message in mqtt.messages:
            topic = getattr(message.topic, "value", str(message.topic))
            payload = message.payload
            if isinstance(payload, (bytes, bytearray)):
                payload_text = payload.decode("utf-8", errors="replace")
            else:
                payload_text = str(payload)
            try:
                self._handle_message(topic, payload_text)
            except Exception:  # noqa: BLE001 - never kill the listener
                _LOGGER.exception("Error handling VIDAA message on %s", topic)

    async def _initial_load(self) -> None:
        """Request all state the TV exposes without changing anything."""
        queries = [
            ("platform_service", "getdeviceinfo", "{}"),
            ("platform_service", "gettvinfo", "{}"),
            ("platform_service", "getvolume", ""),
            ("ui_service", "capability", "{}"),
            ("ui_service", "sourcelist", ""),
            ("ui_service", "applist", ""),
            (
                "platform_service",
                "picturesetting",
                json.dumps({"action": "get_menu_info"}),
            ),
        ]
        await asyncio.gather(
            *[
                self._async_query(service, action, payload, timeout=7.0)
                for service, action, payload in queries
            ],
            return_exceptions=True,
        )

    # ------------------------------------------------------------------
    # MQTT helpers
    # ------------------------------------------------------------------
    def _action_topic(self, service: str, action: str) -> str:
        return f"/remoteapp/tv/{service}/{self.client_id}/actions/{action}"

    async def _publish(self, topic: str, payload: str) -> None:
        if self._mqtt is None or not self.connected:
            raise VidaaCommandError("The TV is not connected")
        await self._mqtt.publish(topic, payload, qos=0)

    async def _async_query(
        self,
        service: str,
        action: str,
        payload: str = "",
        *,
        timeout: float = 6.0,
    ) -> Any:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self._pending.setdefault(action, []).append(future)
        try:
            await self._publish(self._action_topic(service, action), payload)
            return await asyncio.wait_for(future, timeout)
        except (TimeoutError, VidaaCommandError):
            return None
        finally:
            pending = self._pending.get(action)
            if pending is not None:
                with suppress(ValueError):
                    pending.remove(future)
                if not pending:
                    self._pending.pop(action, None)

    def _resolve_query(self, leaf: str, value: Any) -> None:
        for future in list(self._pending.get(leaf, [])):
            if not future.done():
                future.set_result(value)

    # ------------------------------------------------------------------
    # Message parsing
    # ------------------------------------------------------------------
    def _handle_message(self, topic: str, text: str) -> None:
        if not topic.startswith("/remoteapp/mobile/"):
            return

        try:
            payload: Any = json.loads(text) if text else None
        except (TypeError, ValueError):
            payload = text

        self.data["last_update"] = time.time()
        self._store_raw(topic, payload)

        if "/broadcast/" in topic:
            if topic.endswith("/state"):
                self._apply_state(payload)
            elif "volumechange" in topic:
                self._apply_volume(payload)
            elif "hotelmodechange" in topic:
                self._apply_hotel_mode(payload)
            self._resolve_query(topic.rsplit("/", 1)[-1], payload)
            self._notify()
            return

        if "/data/" not in topic:
            return

        leaf = topic.rsplit("/", 1)[-1]
        if leaf == "getdeviceinfo":
            self._apply_device_info(payload)
        elif leaf == "gettvinfo":
            self._apply_tv_info(payload)
        elif leaf == "capability":
            self._apply_capability(payload)
        elif leaf == "applist":
            self._apply_apps(payload)
        elif leaf == "sourcelist":
            self._apply_sources(payload)
        elif leaf == "picturesetting":
            self._apply_picture_settings(payload)
        elif leaf == "soundsetting":
            self._apply_sound_settings(payload)
        elif leaf == "getvolume":
            self._apply_volume(payload)
        elif leaf == "state":
            self._apply_state(payload)

        self._resolve_query(leaf, payload)
        self._notify()

    def _store_raw(self, topic: str, payload: Any) -> None:
        raw: dict[str, Any] = self.data["raw"]
        raw[topic] = payload
        if len(raw) > 120:
            for old_topic in list(raw)[:20]:
                raw.pop(old_topic, None)

    def _apply_device_info(self, payload: Any) -> None:
        if isinstance(payload, dict):
            self.data["device_info"] = payload

    def _apply_tv_info(self, payload: Any) -> None:
        if isinstance(payload, dict):
            self.data["tv_info"] = payload

    def _apply_capability(self, payload: Any) -> None:
        if isinstance(payload, dict):
            self.data["capability"] = payload

    def _apply_apps(self, payload: Any) -> None:
        raw = payload
        if isinstance(raw, dict):
            raw = raw.get("applist") or raw.get("apps") or raw.get("data")
        if not isinstance(raw, list):
            return

        apps: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            if str(item.get("isunInstalled", "")).casefold() in ("true", "1"):
                continue
            app_id = str(item.get("appId", "")).strip()
            if not app_id or app_id in seen:
                continue
            seen.add(app_id)
            app = dict(item)
            app["app_id"] = app_id
            app["display_name"] = clean_app_name(item.get("name"))
            app["category"] = get_app_category(app["display_name"])
            app["icon_url"] = _extract_icon(item)
            apps.append(app)

        if apps or not self.data["apps"]:
            self.data["apps"] = apps
            self.data["apps_updated"] = time.time()

    def _apply_sources(self, payload: Any) -> None:
        raw = payload
        if isinstance(raw, dict):
            raw = raw.get("sourcelist") or raw.get("sources") or raw.get("data")
        if not isinstance(raw, list):
            return

        sources: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            source = dict(item)
            source["source_id"] = str(
                item.get("sourceid") or item.get("source_id") or ""
            )
            source["display_name"] = clean_app_name(
                item.get("displayname")
                or item.get("sourcename")
                or item.get("sourceid")
            )
            if source["source_id"]:
                sources.append(source)

        if sources or not self.data["sources"]:
            self.data["sources"] = sources
            self.data["sources_updated"] = time.time()

    def _apply_picture_settings(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        menu_info = payload.get("menu_info")
        if isinstance(menu_info, list):
            self.data["picture_settings"] = [
                dict(item) for item in menu_info if isinstance(item, dict)
            ]
            self.data["picture_updated"] = time.time()

    def _apply_sound_settings(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        menu_info = payload.get("menu_info")
        if isinstance(menu_info, list):
            self.data["sound_settings"] = [
                dict(item) for item in menu_info if isinstance(item, dict)
            ]

    def _apply_volume(self, payload: Any) -> None:
        if isinstance(payload, (int, float)):
            self.data["volume"] = int(payload)
            return
        if not isinstance(payload, dict):
            return

        volume_type = payload.get("volume_type")
        value = payload.get("volume_value")
        if volume_type in (0, 1, "0", "1", None) and value is not None:
            try:
                self.data["volume"] = int(value)
            except (TypeError, ValueError):
                pass
        if volume_type in (2, "2") and value is not None:
            self.data["muted"] = str(value) in ("1", "True", "true")
        elif "is_mute" in payload:
            self.data["muted"] = str(payload["is_mute"]) in ("1", "True", "true")
        elif "muted" in payload:
            self.data["muted"] = bool(payload["muted"])

    def _apply_hotel_mode(self, payload: Any) -> None:
        if isinstance(payload, dict):
            value = payload.get("hotel_mode")
            if value is not None:
                self.data["hotel_mode"] = value

    def _find_app(self, name: str | None = None, app_id: str | None = None) -> dict[str, Any] | None:
        if app_id:
            for app in self.data["apps"]:
                if app.get("app_id") == str(app_id):
                    return app
        if name:
            cleaned = clean_app_name(name).casefold()
            for app in self.data["apps"]:
                if app["display_name"].casefold() == cleaned:
                    return app
        return None

    def _find_source(self, source_id: str | None = None, name: str | None = None) -> dict[str, Any] | None:
        if source_id:
            for source in self.data["sources"]:
                if source["source_id"].casefold() == str(source_id).casefold():
                    return source
        if name:
            cleaned = clean_app_name(name).casefold()
            for source in self.data["sources"]:
                if source["display_name"].casefold() == cleaned:
                    return source
                if source["source_id"].casefold() == cleaned:
                    return source
        return None

    def _apply_state(self, payload: Any) -> None:
        if not isinstance(payload, dict) or not payload:
            return

        self.data["state"] = payload
        self.data["last_state"] = time.time()
        statetype = str(payload.get("statetype") or "").casefold()

        if "is_power_on" in payload:
            self.data["power"] = str(payload["is_power_on"]) in ("1", "True", "true")
        elif statetype == "fake_sleep_0" or "off" in statetype:
            self.data["power"] = False
        elif statetype:
            self.data["power"] = True

        if statetype == "fake_sleep_0" or "off" in statetype:
            self.data["detail"] = "Off"
            self.data["current_app"] = None
            self.data["current_app_id"] = None
            self.data["current_app_url"] = None
            return

        if statetype == "screensaver" or statetype == "screen_saver":
            self.data["detail"] = "Screensaver"
        elif statetype == "remote_launcher":
            self.data["detail"] = "Home"
            self.data["current_app"] = None
            self.data["current_app_id"] = None
            self.data["current_app_url"] = None
        elif statetype == "livetv":
            self.data["detail"] = "Live TV"
            self.data["current_app"] = None
            self.data["current_app_id"] = None
            self.data["current_app_url"] = None
            if not self.data.get("current_source_id"):
                self.data["current_source_id"] = "TV"
                self.data["current_source"] = "TV"
        elif statetype == "sourceswitch":
            source_id = payload.get("sourceid") or payload.get("source_id")
            source = self._find_source(source_id=source_id)
            if source:
                self.data["current_source_id"] = source["source_id"]
                self.data["current_source"] = source["display_name"]
            elif source_id:
                self.data["current_source_id"] = str(source_id)
                self.data["current_source"] = str(source_id)
            self.data["detail"] = (
                self.data.get("current_source") or str(source_id or "Input")
            )
            self.data["current_app"] = None
            self.data["current_app_id"] = None
            self.data["current_app_url"] = None
        elif statetype == "app":
            app = self._find_app(
                name=payload.get("name") or payload.get("appname"),
                app_id=str(payload.get("appid")) if payload.get("appid") else None,
            )
            app_name = (
                app["display_name"]
                if app
                else clean_app_name(
                    payload.get("name") or payload.get("appname") or "App"
                ).title()
            )
            self.data["current_app"] = app_name
            self.data["current_app_id"] = (
                app["app_id"] if app else (
                    str(payload["appid"]) if payload.get("appid") else None
                )
            )
            self.data["current_app_url"] = (
                payload.get("url") or (app.get("url") if app else None)
            )
            self.data["detail"] = app_name
        elif statetype == "remote_setting":
            self.data["detail"] = "Settings"
        elif statetype:
            self.data["detail"] = statetype.replace("_", " ").title()

        if "sourceid" in payload:
            source = self._find_source(source_id=str(payload["sourceid"]))
            if source:
                self.data["current_source_id"] = source["source_id"]
                self.data["current_source"] = source["display_name"]
            else:
                self.data["current_source_id"] = str(payload["sourceid"])
                self.data["current_source"] = str(payload["sourceid"])
        if "sourcename" in payload:
            self.data["current_source"] = str(payload["sourcename"])
        if "channel_name" in payload:
            self.data["channel_name"] = payload["channel_name"]
        if "channel_num" in payload:
            self.data["channel_number"] = str(payload["channel_num"])
        if "program_title" in payload:
            self.data["program_title"] = payload["program_title"]
        if "audio_output" in payload:
            self.data["audio_output"] = payload["audio_output"]
        if "hdr_mode" in payload:
            self.data["hdr_mode"] = payload["hdr_mode"]
        if "audio_format" in payload:
            self.data["audio_format"] = payload["audio_format"]
        if "sleep_time" in payload:
            with suppress(TypeError, ValueError):
                self.data["sleep_timer"] = int(payload["sleep_time"])

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    async def async_send_key(self, key: str) -> None:
        """Send one raw VIDAA key code."""
        resolved = resolve_key(key)
        await self._publish(
            self._action_topic("remote_service", "sendkey"), resolved
        )
        if resolved == "KEY_POWER" and self.data["power"] is not None:
            self._set_power(not self.data["power"])
        elif resolved == "KEY_MUTE" and self.data["muted"] is not None:
            self.data["muted"] = not self.data["muted"]
        elif resolved == "KEY_HOME" and self.data["power"] is not False:
            self.data["power"] = True
            self.data["current_app"] = None
            self.data["current_app_id"] = None
            self.data["current_app_url"] = None
            self.data["detail"] = "Home"
        self._notify()

    async def async_send_keys(
        self, keys: Iterable[str], *, delay: float = 0.2
    ) -> None:
        """Send several keys in order."""
        for key in keys:
            await self.async_send_key(key)
            if delay:
                await asyncio.sleep(delay)

    async def async_launch_app(self, app: dict[str, Any]) -> None:
        """Launch an installed application."""
        payload = {
            "appId": str(app.get("appId") or app.get("app_id") or ""),
            "name": app.get("name") or app.get("display_name") or "",
            "url": app.get("url") or "",
            "storeType": app.get("storeType", 99),
        }
        await self._publish(
            self._action_topic("ui_service", "launchapp"),
            json.dumps(payload),
        )
        display = clean_app_name(app.get("display_name") or app.get("name"))
        self.data["power"] = True
        self.data["current_app"] = display
        self.data["current_app_id"] = payload["appId"]
        self.data["current_app_url"] = payload["url"]
        self.data["detail"] = display
        self._notify()

    async def async_launch_app_by_name(self, name: str) -> bool:
        """Launch an app by display name or app ID."""
        app = self._find_app(name=name, app_id=name)
        if app is None:
            return False
        await self.async_launch_app(app)
        return True

    async def async_launch_url(self, url: str, name: str = "Web") -> None:
        """Open an arbitrary URL in the TV browser."""
        payload = {
            "appId": "",
            "name": name,
            "url": url,
            "urlType": 37,
            "appName": name,
            "appUrl": url,
            "storeType": 99,
        }
        await self._publish(
            self._action_topic("ui_service", "launchapp"),
            json.dumps(payload),
        )
        self.data["power"] = True
        self.data["current_app"] = clean_app_name(name)
        self.data["current_app_id"] = None
        self.data["current_app_url"] = url
        self.data["detail"] = clean_app_name(name)
        self._notify()

    async def async_change_source(self, source: str) -> bool:
        """Switch to an input by source ID or display name."""
        found = self._find_source(source_id=source, name=source)
        source_id = found["source_id"] if found else source
        await self._publish(
            self._action_topic("ui_service", "changesource"),
            json.dumps({"sourceid": source_id}),
        )
        if found:
            self.data["current_source_id"] = found["source_id"]
            self.data["current_source"] = found["display_name"]
            self.data["detail"] = found["display_name"]
        else:
            self.data["current_source_id"] = source_id
            self.data["current_source"] = source_id
            self.data["detail"] = source_id
        self.data["current_app"] = None
        self.data["current_app_id"] = None
        self.data["current_app_url"] = None
        self._notify()
        return True

    async def async_select_source(self, name: str) -> bool:
        """Select an input or launch an app by name."""
        if self._find_source(name=name) is not None:
            return await self.async_change_source(name)
        return await self.async_launch_app_by_name(name)

    async def async_set_volume(self, volume: int) -> None:
        """Set the master volume (0-100)."""
        volume = max(0, min(100, int(volume)))
        await self._publish(
            self._action_topic("platform_service", "changevolume"), str(volume)
        )
        self.data["volume"] = volume
        self._notify()

    async def async_volume_up(self) -> None:
        """Step volume up."""
        await self.async_send_key("KEY_VOLUMEUP")

    async def async_volume_down(self) -> None:
        """Step volume down."""
        await self.async_send_key("KEY_VOLUMEDOWN")

    async def async_mute(self, mute: bool) -> None:
        """Set mute idempotently."""
        if self.data["muted"] is not None and bool(mute) == bool(
            self.data["muted"]
        ):
            return
        await self.async_send_key("KEY_MUTE")
        self.data["muted"] = bool(mute)
        self._notify()

    async def async_media_play(self) -> None:
        await self.async_send_key("KEY_PLAY")

    async def async_media_pause(self) -> None:
        await self.async_send_key("KEY_PAUSE")

    async def async_media_stop(self) -> None:
        await self.async_send_key("KEY_STOP")

    async def async_media_next(self) -> None:
        await self.async_send_key("KEY_FORWARDS")

    async def async_media_previous(self) -> None:
        await self.async_send_key("KEY_BACK")

    async def async_play_media(self, media_type: str, media_id: str) -> bool:
        """Launch an app/URL or tune to a channel number."""
        kind = str(media_type or "").casefold()
        if kind in ("url", "web") or media_id.startswith(("http://", "https://")):
            await self.async_launch_url(media_id)
            return True
        if kind in ("channel", "tvshow") and re.fullmatch(r"\d+(?:\.\d+)?", media_id):
            keys = []
            for char in media_id:
                keys.append("KEY_CHANNELDOT" if char == "." else f"KEY_{char}")
            await self.async_send_keys(keys, delay=0.15)
            return True
        if kind == "app" or kind in ("", "app_name"):
            return await self.async_launch_app_by_name(media_id)
        return await self.async_launch_app_by_name(media_id)

    async def async_set_picture_menu(self, menu_id: int, value: Any) -> None:
        """Write one picture setting menu item."""
        await self._publish(
            self._action_topic("platform_service", "picturesetting"),
            json.dumps({"menu_id": int(menu_id), "menu_value": str(value)}),
        )
        for item in self.data["picture_settings"]:
            if str(item.get("menu_id")) == str(menu_id):
                item["menu_value"] = value
                break
        self.data["picture_updated"] = time.time()
        self._notify()

    async def async_refresh_apps(self) -> list[dict[str, Any]]:
        """Re-query the installed app list."""
        await self._async_query("ui_service", "applist", "", timeout=7.0)
        return self.data["apps"]

    async def async_refresh_sources(self) -> list[dict[str, Any]]:
        """Re-query the input list."""
        await self._async_query("ui_service", "sourcelist", "", timeout=7.0)
        return self.data["sources"]

    async def async_refresh_picture_settings(self) -> list[dict[str, Any]]:
        """Re-query the picture settings menu."""
        await self._async_query(
            "platform_service",
            "picturesetting",
            json.dumps({"action": "get_menu_info"}),
            timeout=7.0,
        )
        return self.data["picture_settings"]

    async def async_turn_on(self) -> None:
        """Wake the TV with WOL and, if it is known to be off, a power key."""
        await self._send_wake_on_lan()
        if self.connected and self.data["power"] is False:
            await self.async_send_key("KEY_POWER")

    async def async_turn_off(self) -> None:
        """Put the TV in standby."""
        if self.data["power"] is False:
            return
        if not self.connected:
            raise VidaaCommandError("The TV is not connected")
        await self.async_send_keys(["KEY_POWER"])
        self._set_power(False)

    async def _send_wake_on_lan(self) -> None:
        """Send Wake-on-LAN magic packets to the TV's wired and wireless MACs."""
        loop = asyncio.get_running_loop()
        with suppress(Exception):
            await loop.run_in_executor(None, self._send_wol_sync)

    def _send_wol_sync(self) -> None:
        cleaned = re.sub(r"[^0-9a-fA-F]", "", self.mac)
        payload = b"\xff" * 6 + bytes.fromhex(cleaned) * 16
        targets = {"255.255.255.255"}
        if self.host.count(".") == 3:
            targets.add(self.host.rsplit(".", 1)[0] + ".255")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            for target in targets:
                for port in (9, 7):
                    for _ in range(2):
                        with suppress(OSError):
                            sock.sendto(payload, (target, port))

    # ------------------------------------------------------------------
    # Change notification
    # ------------------------------------------------------------------
    def _set_power(self, value: bool) -> None:
        self.data["power"] = value
        if not value:
            self.data["detail"] = "Off"
        elif not self.data.get("detail") or self.data["detail"] == "Off":
            self.data["detail"] = "On"

    def _notify(self) -> None:
        if self._notify_handle is not None:
            return
        with suppress(RuntimeError):
            loop = asyncio.get_running_loop()
            self._notify_handle = loop.call_later(0.05, self._dispatch)

    def _dispatch(self) -> None:
        self._notify_handle = None
        for listener in list(self._listeners):
            try:
                listener(self.data)
            except Exception:  # noqa: BLE001 - a listener must not stop the client
                _LOGGER.exception("VIDAA state listener failed")

