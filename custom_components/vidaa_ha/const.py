"""Constants for the VIDAA TV integration."""

from __future__ import annotations

import re

DOMAIN = "vidaa_ha"
NAME = "VIDAA TV"
VERSION = "1.0.4"

CONF_HOST = "host"
CONF_NAME = "name"
CONF_PORT = "port"
CONF_MAC = "mac"
CONF_CLIENT_ID = "client_id"
CONF_CERTFILE = "certfile"
CONF_KEYFILE = "keyfile"
CONF_WOL = "wol"
CONF_KEY_DELAY = "key_delay"
CONF_INCLUDE_APPS_IN_SOURCES = "include_apps_in_sources"
CONF_CREATE_KEY_BUTTONS = "create_key_buttons"
CONF_CREATE_PICTURE_ENTITIES = "create_picture_entities"
CONF_CREATE_DIAGNOSTICS = "create_diagnostics"

DEFAULT_PORT = 36669
DEFAULT_USERNAME = "hisenseservice"
DEFAULT_PASSWORD = "multimqttservice"
DEFAULT_WOL = True
DEFAULT_KEY_DELAY = 0.2
DEFAULT_INCLUDE_APPS_IN_SOURCES = True
DEFAULT_CREATE_KEY_BUTTONS = True
DEFAULT_CREATE_PICTURE_ENTITIES = True
DEFAULT_CREATE_DIAGNOSTICS = True

MANUFACTURER = "Hisense"

APPS_DEVICE = "apps"
INPUTS_DEVICE = "inputs"
REMOTE_DEVICE = "remote"
SETTINGS_DEVICE = "settings"

SUNDEVICE_LABELS = {
    APPS_DEVICE: "Apps",
    INPUTS_DEVICE: "Inputs",
    REMOTE_DEVICE: "Remote",
    SETTINGS_DEVICE: "Settings",
}

# Sub-devices used before the five-device grouping. Their entities are moved
# to the new device during setup so upgrading does not leave empty devices.
LEGACY_SUBDEVICE_TARGETS: dict[str, str | None] = {
    "status": None,
    "system": SETTINGS_DEVICE,
    "picture": SETTINGS_DEVICE,
    "apps_streaming": APPS_DEVICE,
    "apps_live": APPS_DEVICE,
    "apps_music": APPS_DEVICE,
    "apps_games": APPS_DEVICE,
    "apps_tools": APPS_DEVICE,
    "remote_navigation": REMOTE_DEVICE,
    "remote_volume": REMOTE_DEVICE,
    "remote_playback": REMOTE_DEVICE,
    "remote_extras": REMOTE_DEVICE,
}

APP_CATEGORY_ICONS = {
    "streaming": "mdi:play-box-multiple",
    "live": "mdi:broadcast",
    "music": "mdi:music-box-multiple",
    "games": "mdi:gamepad-variant",
    "tools": "mdi:application-cog",
}

APP_NAME_CATEGORIES: dict[str, str] = {}


def _register_apps(category: str, names: str) -> None:
    for name in names.split("|"):
        APP_NAME_CATEGORIES[" ".join(name.split()).casefold()] = category


_register_apps(
    "streaming",
    "Plex|Netflix|YouTube|Apple TV|Disney+|Stan.|Britbox|DAZN|UEFA.tv|Triller TV.|NBA|"
    "HBO Max|WeTV|Paramount+|Crunchyroll|MUBI|iWant|Red Bull TV|UFC|Filmzie|Vod On Demand|"
    "V Home|tubi|Prime Video|VIDAA Kids",
)
_register_apps(
    "live",
    "Foxtel|Kayo|Binge|ABC iview|9Now|7plus|10 play|SBS ON DEMAND|"
    "Haystack TV Local + World News|CNA",
)
_register_apps("music", "DEEZER|Spotify : Music & Podcasts|Amazon Music")
_register_apps("games", "Couchplay Games|Game Center")
_register_apps("tools", "TV Browser|APP STORE|E-Manual|Deviant Art")


def clean_app_name(name: str | None) -> str:
    """Return a display-friendly app name."""
    if not name:
        return "Unknown app"
    return " ".join(str(name).split())


def app_category(name: str | None) -> str:
    """Return the UI category for an installed app."""
    cleaned = clean_app_name(name)
    category = APP_NAME_CATEGORIES.get(cleaned.casefold())
    if category:
        return category
    lowered = cleaned.casefold()
    if any(token in lowered for token in ("music", "spotify", "deezer", "radio", "podcast")):
        return "music"
    if any(token in lowered for token in ("game", "play", "casino")):
        return "games"
    if any(token in lowered for token in ("browser", "store", "manual", "art")):
        return "tools"
    if any(token in lowered for token in ("tv", "live", "news", "catch", "now", "sport")):
        return "live"
    return "streaming"


def slugify(value: str) -> str:
    """Create a stable slug for a unique ID."""
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


# Full key namespace that the local broker accepts. Grouped for the entity UI.
REMOTE_GROUPS: list[dict] = [
    {
        "key": "remote_navigation",
        "name": "Remote · Navigation",
        "icon": "mdi:gamepad-round-outline",
        "buttons": [
            ("Power", "KEY_POWER", "mdi:power"),
            ("Home", "KEY_HOME", "mdi:home"),
            ("Back", "KEY_BACK", "mdi:arrow-left"),
            ("Return", "KEY_RETURNS", "mdi:keyboard-return"),
            ("Menu", "KEY_MENU", "mdi:menu"),
            ("Exit", "KEY_EXIT", "mdi:exit-to-app"),
            ("Info", "KEY_INFO", "mdi:information-outline"),
            ("Up", "KEY_UP", "mdi:chevron-up"),
            ("Down", "KEY_DOWN", "mdi:chevron-down"),
            ("Left", "KEY_LEFT", "mdi:chevron-left"),
            ("Right", "KEY_RIGHT", "mdi:chevron-right"),
            ("OK", "KEY_OK", "mdi:check-circle-outline"),
            ("OK (long press)", "KEY_OK_LONG_PRESS", "mdi:check-circle"),
        ],
    },
    {
        "key": "remote_volume",
        "name": "Remote · Volume & Channels",
        "icon": "mdi:volume-high",
        "buttons": [
            ("Volume Up", "KEY_VOLUMEUP", "mdi:volume-plus"),
            ("Volume Down", "KEY_VOLUMEDOWN", "mdi:volume-minus"),
            ("Mute", "KEY_MUTE", "mdi:volume-mute"),
            ("Mute (long press)", "KEY_MUTE_LONG_PRESS", "mdi:volume-off"),
            ("Channel Up", "KEY_CHANNELUP", "mdi:arrow-up-bold"),
            ("Channel Down", "KEY_CHANNELDOWN", "mdi:arrow-down-bold"),
            ("Channel List", "KEY_CHLIST", "mdi:format-list-numbered"),
            ("Guide", "KEY_EPG", "mdi:television-guide"),
            ("Channel Dot", "KEY_CHANNELDOT", "mdi:period"),
            ("0", "KEY_0", "mdi:numeric-0"),
            ("1", "KEY_1", "mdi:numeric-1"),
            ("2", "KEY_2", "mdi:numeric-2"),
            ("3", "KEY_3", "mdi:numeric-3"),
            ("4", "KEY_4", "mdi:numeric-4"),
            ("5", "KEY_5", "mdi:numeric-5"),
            ("6", "KEY_6", "mdi:numeric-6"),
            ("7", "KEY_7", "mdi:numeric-7"),
            ("8", "KEY_8", "mdi:numeric-8"),
            ("9", "KEY_9", "mdi:numeric-9"),
        ],
    },
    {
        "key": "remote_playback",
        "name": "Remote · Playback & Apps",
        "icon": "mdi:play-circle-outline",
        "buttons": [
            ("Play", "KEY_PLAY", "mdi:play"),
            ("Pause", "KEY_PAUSE", "mdi:pause"),
            ("Stop", "KEY_STOP", "mdi:stop"),
            ("Rewind", "KEY_BACK", "mdi:rewind"),
            ("Fast Forward", "KEY_FORWARDS", "mdi:fast-forward"),
            ("Subtitle", "KEY_SUBTITLE", "mdi:subtitles-outline"),
            ("Teletext", "KEY_TEXT", "mdi:text-box-outline"),
            ("Audio", "KEY_AUDIO", "mdi:audio"),
            ("Media", "KEY_MEDIA", "mdi:usb"),
            ("Live TV", "KEY_LIVETV", "mdi:television-classic"),
            ("Apps", "KEY_APPS", "mdi:apps"),
            ("Netflix Key", "KEY_NETFLIX", "mdi:netflix"),
            ("YouTube Key", "KEY_YOUTUBE", "mdi:youtube"),
            ("Prime Video Key", "KEY_PRIME", "mdi:amazon"),
        ],
    },
    {
        "key": "remote_extras",
        "name": "Remote · Colour & Extras",
        "icon": "mdi:remote",
        "buttons": [
            ("Red", "KEY_RED", "mdi:circle"),
            ("Green", "KEY_GREEN", "mdi:circle"),
            ("Yellow", "KEY_YELLOW", "mdi:circle"),
            ("Blue", "KEY_BLUE", "mdi:circle"),
            ("Voice Up", "KEY_VOICEUP", "mdi:microphone-plus"),
            ("Voice Down", "KEY_VOICEDOWN", "mdi:microphone-minus"),
            ("Mouse Click", "KEY_LEFTMOUSEKEYS", "mdi:cursor-default-click"),
            ("Mouse Up", "KEY_UDULEFTMOUSEKEYS", "mdi:cursor-move"),
            ("Mouse Down", "KEY_UDDLEFTMOUSEKEYS", "mdi:cursor-move"),
            ("Zoom In", "KEY_ZOOMIN", "mdi:magnify-plus"),
            ("Zoom Out", "KEY_ZOOMOUT", "mdi:magnify-minus"),
            ("Audio Only", "KEY_AUDIO", "mdi:monitor-off"),
            ("Audio Only (dedicated)", "KEY_AUDIO_ONLY", "mdi:monitor-off"),
            ("Sound Output", "KEY_SOUND", "mdi:volume-high"),
            ("Headphone Output", "KEY_HEADPHONE", "mdi:headphones"),
        ],
    },
]

REMOTE_COMMANDS: list[str] = sorted(
    {button[1] for group in REMOTE_GROUPS for button in group["buttons"]}
)

# Friendly command aliases accepted by remote.send_command.
KEY_ALIASES: dict[str, str] = {
    "power": "KEY_POWER",
    "power_off": "KEY_POWER",
    "standby": "KEY_POWER",
    "up": "KEY_UP",
    "down": "KEY_DOWN",
    "left": "KEY_LEFT",
    "right": "KEY_RIGHT",
    "ok": "KEY_OK",
    "enter": "KEY_OK",
    "select": "KEY_OK",
    "ok_long": "KEY_OK_LONG_PRESS",
    "back": "KEY_BACK",
    "return": "KEY_RETURNS",
    "home": "KEY_HOME",
    "menu": "KEY_MENU",
    "settings": "KEY_MENU",
    "exit": "KEY_EXIT",
    "info": "KEY_INFO",
    "volume_up": "KEY_VOLUMEUP",
    "volumeup": "KEY_VOLUMEUP",
    "vol_up": "KEY_VOLUMEUP",
    "volume_down": "KEY_VOLUMEDOWN",
    "volumedown": "KEY_VOLUMEDOWN",
    "vol_down": "KEY_VOLUMEDOWN",
    "mute": "KEY_MUTE",
    "unmute": "KEY_MUTE",
    "channel_up": "KEY_CHANNELUP",
    "channelup": "KEY_CHANNELUP",
    "ch_up": "KEY_CHANNELUP",
    "channel_down": "KEY_CHANNELDOWN",
    "channeldown": "KEY_CHANNELDOWN",
    "ch_down": "KEY_CHANNELDOWN",
    "channel_dot": "KEY_CHANNELDOT",
    "dot": "KEY_CHANNELDOT",
    "play": "KEY_PLAY",
    "pause": "KEY_PAUSE",
    "stop": "KEY_STOP",
    "fast_forward": "KEY_FORWARDS",
    "forward": "KEY_FORWARDS",
    "ff": "KEY_FORWARDS",
    "rewind": "KEY_BACK",
    "rw": "KEY_BACK",
    "subtitle": "KEY_SUBTITLE",
    "subtitles": "KEY_SUBTITLE",
    "guide": "KEY_EPG",
    "epg": "KEY_EPG",
    "chlist": "KEY_CHLIST",
    "channel_list": "KEY_CHLIST",
    "text": "KEY_TEXT",
    "teletext": "KEY_TEXT",
    "red": "KEY_RED",
    "green": "KEY_GREEN",
    "yellow": "KEY_YELLOW",
    "blue": "KEY_BLUE",
    "livetv": "KEY_LIVETV",
    "live_tv": "KEY_LIVETV",
    "tv": "KEY_LIVETV",
    "media": "KEY_MEDIA",
    "apps": "KEY_APPS",
    "audio": "KEY_AUDIO",
    "mouse": "KEY_LEFTMOUSEKEYS",
    "zoom_in": "KEY_ZOOMIN",
    "zoom_out": "KEY_ZOOMOUT",
    "netflix": "KEY_NETFLIX",
    "youtube": "KEY_YOUTUBE",
    "prime": "KEY_PRIME",
    "prime_video": "KEY_PRIME",
}

# Keys emitted by HomeKit's Television remote. Keeping the mapping here also
# lets remote.send_command accept the same names directly.
HOMEKIT_REMOTE_KEYS: dict[str, str] = {
    "arrow_up": "KEY_UP",
    "arrow_down": "KEY_DOWN",
    "arrow_left": "KEY_LEFT",
    "arrow_right": "KEY_RIGHT",
    "select": "KEY_OK",
    "back": "KEY_BACK",
    "exit": "KEY_EXIT",
    "information": "KEY_INFO",
    "play_pause": "KEY_PLAY",
    "rewind": "KEY_BACK",
    "fast_forward": "KEY_FORWARDS",
    "next_track": "KEY_FORWARDS",
    "previous_track": "KEY_BACK",
}
KEY_ALIASES.update(HOMEKIT_REMOTE_KEYS)


def resolve_key(command: str) -> str:
    """Resolve a friendly key name or raw key code to a VIDAA key code."""
    cleaned = command.strip()
    if not cleaned:
        return cleaned
    lowered = cleaned.casefold()
    if lowered in KEY_ALIASES:
        return KEY_ALIASES[lowered]
    if lowered.startswith("key_"):
        return cleaned.upper()
    digits = {
        "0": "KEY_0",
        "1": "KEY_1",
        "2": "KEY_2",
        "3": "KEY_3",
        "4": "KEY_4",
        "5": "KEY_5",
        "6": "KEY_6",
        "7": "KEY_7",
        "8": "KEY_8",
        "9": "KEY_9",
    }
    return digits.get(cleaned, cleaned.upper())


# Picture menu IDs exposed as writable sliders. These match the TV's
# picturesetting menu payload and are read back after every change.
PICTURE_NUMBER_CONTROLS: list[dict] = [
    {
        "menu_id": 3,
        "name": "Brightness",
        "icon": "mdi:brightness-6",
        "min": 0,
        "max": 100,
    },
    {
        "menu_id": 4,
        "name": "Contrast",
        "icon": "mdi:contrast-circle",
        "min": 0,
        "max": 100,
    },
    {
        "menu_id": 5,
        "name": "Colour Intensity",
        "icon": "mdi:palette",
        "min": 0,
        "max": 100,
    },
    {
        "menu_id": 8,
        "name": "Backlight",
        "icon": "mdi:brightness-7",
        "min": 0,
        "max": 100,
    },
    {
        "menu_id": 20,
        "name": "Tint",
        "icon": "mdi:invert-colors",
        "min": 0,
        "max": 100,
    },
    {
        "menu_id": 21,
        "name": "Sharpness",
        "icon": "mdi:image-filter-center-focus",
        "min": 0,
        "max": 100,
    },
]

# Diagnostic telemetry. Each entry is (key, name, group, field, icon).
DIAGNOSTIC_SENSORS: list[tuple[str, str, str, str, str]] = [
    ("device_name", "Device Name", "device_info", "tv_name", "mdi:television"),
    ("model", "Model", "device_info", "model_name", "mdi:television-box"),
    ("firmware", "Firmware", "device_info", "tv_version", "mdi:package-up"),
    ("ip_address", "IP Address", "device_info", "ip", "mdi:ip-network"),
    ("ethernet_mac", "Ethernet MAC", "device_info", "eth0", "mdi:ethernet"),
    ("wifi_mac", "Wi-Fi MAC", "device_info", "wlan0", "mdi:wifi"),
    ("transport_protocol", "Transport Protocol", "device_info", "transport_protocol", "mdi:swap-horizontal"),
    ("region", "Region", "device_info", "region", "mdi:map-marker"),
    ("country", "Country", "device_info", "country", "mdi:flag"),
    ("language", "Language", "device_info", "language", "mdi:translate"),
    ("voice", "Voice Support", "device_info", "voice", "mdi:microphone"),
    ("platform", "Platform", "device_info", "platform", "mdi:chip"),
    ("vidaa_support", "VIDAA Support", "device_info", "vidaa_support", "mdi:check-decagram"),
    ("brand", "Brand", "tv_info", "brand", "mdi:tag"),
    ("feature_code", "Feature Code", "tv_info", "featurecode", "mdi:barcode"),
    ("device_id", "Device ID", "tv_info", "deviceid", "mdi:identifier"),
    ("capability_stamp", "Capability Stamp", "tv_info", "capability", "mdi:file-certificate"),
    ("tuner_count", "Tuner Count", "tv_info", "tuner_num", "mdi:radio-tower"),
    ("fake_sleep", "Fake Sleep", "tv_info", "fake_sleep", "mdi:sleep"),
    ("fake_sleep_state", "Fake Sleep State", "tv_info", "fake_sleep_state", "mdi:sleep-off"),
    ("screen_capture_supported", "Screen Capture Supported", "tv_info", "screen_capture_supported", "mdi:monitor-screenshot"),
    ("audio_capture_supported", "Audio Capture Supported", "tv_info", "audio_capture_supported", "mdi:microphone-outline"),
    ("audio_capture_version", "Audio Capture Version", "tv_info", "audio_capture_version", "mdi:microphone-settings"),
    ("base_ui", "Base UI", "capability", "baseUIVersion", "mdi:layers"),
    ("chipset", "Chipset", "capability", "chipplatform", "mdi:chip"),
    ("resolution", "Resolution", "capability", "resolution", "mdi:monitor"),
    ("player_family", "Player Family", "capability", "playerFamilyName", "mdi:movie-open"),
    ("player_version", "Player Family Version", "capability", "playerFamilyVersion", "mdi:movie-open-check"),
    ("produce_date", "Produce Date", "capability", "produceDate", "mdi:calendar"),
    ("software_version", "Software Version (capability)", "capability", "softwareVersion", "mdi:package"),
    ("vendor_brand", "Vendor Brand", "capability", "vendorBrand", "mdi:tag-outline"),
    ("device_type", "Device Type", "capability", "deviceType", "mdi:devices"),
    ("tv_mode", "TV Mode", "capability", "tvmode", "mdi:television-classic"),
    ("zone", "Zone", "capability", "zone", "mdi:map-clock"),
    ("tv_browser", "TV Browser Engine", "capability", "tvBrowser", "mdi:web"),
    ("app_edit", "App Editing", "capability", "app_edit", "mdi:pencil"),
    ("rename", "Rename Support", "capability", "rename", "mdi:rename-box"),
    ("search_now", "Search Now", "capability", "searchnow", "mdi:magnify"),
    ("e_manual", "E-Manual", "capability", "emanual", "mdi:book-open-variant"),
    ("device_message", "Device Message", "capability", "devicemsg", "mdi:message-text"),
]
