# vidaa-ha

A local Home Assistant integration for Hisense / VIDAA TVs, built around the
TV's own MQTT broker. No cloud, no PIN, no Android TV.

It talks to the broker on port `36669` over mutual TLS using the credentials
the official VIDAA app uses, connects with the MAC-form client ID this firmware
expects for unicast replies, and dispatches every reply by its own topic. That
last detail is why app lists, input lists, device information and state work
here when simpler integrations get empty results.

Tested against a **Hisense 85A66GAVT** on firmware `V0000.06.12X.N1212`
(MediaTek MT9900, VIDAA `transport_protocol=2152`). It should work on other
VIDAA sets that accept the same static local credentials.

## Entity organisation

Everything is grouped into five devices: the main TV, **Apps**, **Inputs**,
**Remote** and **Settings**. Live status stays on the main TV device.

| Device | What is in it |
|---|---|
| **Welter TV** (main TV) | `media_player`, power and mute sensors, detailed state, current app/input, volume, channel, hotel mode |
| **Apps** | one launch button per installed app |
| **Inputs** | source selector and one button per physical input |
| **Remote** | the full `remote` entity and every remote key button, including the number pad |
| **Settings** | picture sliders and sensors, device/MQTT diagnostics, refresh/reconnect buttons |

The app list is read from the TV at setup, so the buttons are the apps actually
installed on that set, including Foxtel, Kayo, Binge, Stan, ABC iview, 9Now,
7plus, 10 play, SBS On Demand, Netflix, Plex and the rest.

## Installation

### HACS

The `vidaa-ha` folder must be the **root** of the repository you add to HACS
(publish that folder as its own repository, or move its contents to the repo
root). HACS looks for `custom_components/` and `hacs.json` at the repository
root, not in a subfolder.

1. HACS → Integrations → ⋮ → **Custom repositories**.
2. Add the `vidaa-ha` repository as an **Integration**.
3. Install **vidaa-ha**, restart Home Assistant.
4. **Settings → Devices & services → Add integration → VIDAA TV**.
5. Enter the TV's IP address. Leave MAC empty unless discovery fails.

### Manual

Copy `custom_components/vidaa_ha` into your Home Assistant
`/config/custom_components/` directory, restart, then add the integration.

## Setup notes

- The TV's UPnP descriptor on `http://<tv>:38400/MediaServer/rendererdevicedesc.xml`
  is used to discover the MAC and friendly name. It needs no authentication.
- The integration uses the MAC-form MQTT client ID
  `<MAC-WITHOUT-COLONS>$vidaa_common`. This is the critical difference from
  other VIDAA integrations: the broker accepts many client IDs, but this
  firmware only sends unicast query replies to that one.
- The bundled client certificate/key in `custom_components/vidaa_ha/certs/`
  is the universal VIDAA app certificate. It is used only for the local TLS
  connection. mTLS is mandatory; the broker rejects connections without a
  client certificate.
- No PIN or on-screen pairing is required on this firmware. Static credentials
  are accepted directly.
- Power state is taken from the TV's `state` broadcast. When Home Assistant
  starts and the TV has not broadcast a state yet, the power entity is
  **unknown** rather than guessing. It resolves on the next app/input/power
  change.
- `turn_on` sends Wake-on-LAN to every known TV MAC and, if the TV reconnects
  still reporting `off`, sends `KEY_POWER` once the session is ready. It never
  toggles power when the state is unknown. See **Waking the TV from deep sleep**
  below.

## Waking the TV from deep sleep

`turn_on` sends a Wake-on-LAN magic packet to the configured MAC plus the TV's
`eth0` and `wlan0` MACs, to the global and subnet broadcast addresses and to
the TV's own IP on UDP ports 9 and 7. If the packet only wakes the network
stack, the integration waits for the first MQTT session and sends `KEY_POWER`
when the TV reports that the panel is still off. It does not send a power
toggle when the state is unknown, so it cannot switch off a TV that woke
straight to the launcher.

For this to work, the TV must keep at least one network interface alive in
standby:

- **Fast Power On / Quick Start: ON** — Settings → System → Advanced Settings.
  This keeps the MQTT broker running in shallow standby, so Home Assistant can
  send `KEY_POWER` without Wake-on-LAN. This is the most reliable option.
- **Wake on LAN: ON** — Settings → Network, for wired Ethernet.
- **Wake on Wireless Network: ON** — Settings → Network, for Wi-Fi.
- **Auto Standby with No Signal** and **Auto Sleep** — turn both off so the TV
  does not drop into regulatory deep sleep while idle.

Some VIDAA models (notably 2020–2022 A6/A7-class sets) remove power from the
Ethernet PHY and Wi-Fi radio in deep sleep. No magic packet can reach a TV in
that state. Use an IR blaster, HDMI-CEC, or the physical remote for a true cold
boot; Wake-on-LAN is a hardware capability, not something the integration can
add.

## Using the entities

### Apps

Every installed app gets a button. Pressing it sends the same `launchapp`
payload the TV uses. The media player also includes apps in its source list
(configurable in options).

### Full remote

`remote.<tv>_remote` accepts raw VIDAA key codes or friendly aliases:

```yaml
action: remote.send_command
target:
  entity_id: remote.welter_tv_remote
data:
  command:
    - home
    - delay: 0
    - down
    - ok
```

Supported raw keys include `KEY_POWER`, `KEY_HOME`, `KEY_BACK`,
`KEY_RETURNS`, `KEY_UP/DOWN/LEFT/RIGHT`, `KEY_OK`, `KEY_MENU`, `KEY_EXIT`,
`KEY_INFO`, `KEY_VOLUMEUP/DOWN`, `KEY_MUTE`, `KEY_CHANNELUP/DOWN`,
`KEY_CHLIST`, `KEY_EPG`, `KEY_PLAY/PAUSE/STOP`, `KEY_FORWARDS`,
`KEY_SUBTITLE`, `KEY_TEXT`, `KEY_RED/GREEN/YELLOW/BLUE`, `KEY_0`–`KEY_9`,
`KEY_CHANNELDOT`, `KEY_LIVETV`, `KEY_MEDIA`, `KEY_APPS`, `KEY_AUDIO`,
`KEY_VOICEUP/DOWN`, `KEY_ZOOMIN/OUT`, `KEY_LEFTMOUSEKEYS`, and more.

The `Remote` entity's attributes list every command. The remote-key buttons
give you the same commands without writing YAML. All of them, including
`0`–`9`, are on the single **Remote** device.

### Apple Home / HomeKit

Expose `media_player.<tv>` to HomeKit in **accessory mode**. Home Assistant
requires accessory mode for a media player with device class `tv`; bridge mode
does not create the television remote controls.

The integration handles HomeKit's `homekit_tv_remote_key_pressed` events for
this TV, so the D-pad, select, back, exit and information buttons in the Apple
Remote widget send the matching VIDAA keys. The HomeKit **Back** button sends
`KEY_RETURNS` (the TV's menu/return key); media rewind stays on `KEY_BACK`.

Apple's HomeKit television remote has **no Home button**, and the Home app does
not let an integration add one. The remote's **Info** button is therefore
mapped to `KEY_HOME`: tap it to return to the VIDAA launcher, then pick an app.
The TV's own information panel remains available as the `info` command, for
example `remote.send_command` with `command: info`.

HomeKit volume up/down calls the media player's volume step actions, which use
the TV's absolute `changevolume` command.

Apple's television remote protocol has no numeric keypad, so `0`–`9` cannot
appear in the HomeKit remote itself. They remain available as **Remote**
buttons in Home Assistant and as `remote.send_command` commands.

If app switching works but volume does not, use the volume buttons in the
Apple Remote widget or Control Center while the TV remote is selected. The
Home app tile does not expose every media-player feature.

### Media player

- Standard on/off, volume, mute and source selection.
- `play_media` can launch an app by name, open a URL in the TV browser, or tune
  a channel number:

```yaml
action: media_player.play_media
target:
  entity_id: media_player.welter_tv
data:
  media_content_type: app
  media_content_id: Netflix
```

```yaml
action: media_player.play_media
target:
  entity_id: media_player.welter_tv
data:
  media_content_type: url
  media_content_id: https://example.com
```

### Detailed state

`sensor.<tv>_state` shows the human-readable state (`Plex`, `Home`,
`PlayStation 4 Pro`, `Live TV`, `Off`, …) and exposes the raw `statetype`, app
ID/URL, source ID, channel, program, HDR/audio format, hotel mode and more as
attributes.

The separate status entities now live on the main TV device, alongside
`binary_sensor.<tv>_power`: `binary_sensor.<tv>_muted`,
`sensor.<tv>_current_app`, `sensor.<tv>_current_source`,
`sensor.<tv>_volume` and `sensor.<tv>_channel`. Home Assistant may keep their
old entity IDs when upgrading, but they are grouped under the main device.

## Picture settings

The TV exposes its full picture menu over MQTT (118 items on the test set).
The integration reads all of them and creates:

- read-only sensors for each usable menu item, grouped under **Settings**;
- writable sliders for Brightness, Contrast, Colour Intensity, Backlight, Tint
  and Sharpness.

Sound settings are **not** exposed by this firmware; the `soundsetting` action
returns no reply. The integration does not invent controls for it.

## Options

- **Wake-on-LAN** (default on): send magic packets to the TV's Ethernet MAC.
- **Delay between remote keys** (default `0.2` s).
- **Include apps in media player sources** (default on).
- **Create buttons for every remote key** (default on).
- **Create picture settings entities** (default on).
- **Create diagnostic sensors** (default on).

Turning off app/key/picture/diagnostic creation only affects entity creation;
the underlying client still reads everything.

## Troubleshooting

- **Cannot connect**: confirm the TV IP, that port `36669` is reachable, and
  that the TV is on the LAN. The broker is TLS-only; a plain MQTT client will
  not work.
- **Entities unavailable after the TV has been off**: the TV shuts down its
  broker in deep standby. The integration retries in the background and asks
  for the power state again when the TV returns, so entities recover without
  reloading the integration. If they do not, check the log for
  `Restarting the VIDAA connection` or `VIDAA MQTT connection` warnings.
- **No apps/sources**: check that the integration is using the MAC-form client
  ID. It does this automatically from the configured MAC. If the MAC was
  entered incorrectly, remove and re-add the integration.
- **Power unknown**: the integration sends `gettvstate` after connecting and
  the TV broadcasts state changes, but some firmware only sends broadcasts.
  Wait for a state change, or press Home on the remote.
- **Wake-on-LAN doesn't work**: enable **Fast Power On** and **Wake on LAN /
  Wake on Wireless Network** on the TV, and keep the TV on wired Ethernet if
  possible. Some models cut power to their network hardware in deep sleep and
  cannot be woken by any packet; use IR, HDMI-CEC, or the physical remote.
- **Entity names**: Home Assistant derives entity IDs from the main TV device
  name. If your TV is named "Welter TV", expect `media_player.welter_tv`,
  `binary_sensor.welter_tv_power`, and so on.

## Read-only protocol test

The client can be exercised without Home Assistant:

```bash
python -m venv .venv
.venv/bin/pip install aiomqtt
.venv/bin/python vidaa-ha/scripts/live_test.py \
  --host 10.1.1.56 --mac e4:3b:c9:4c:aa:8d
```

It only queries identity, apps, inputs, state and picture settings. It never
sends a key, changes an input, or launches anything.

## Protocol summary

```text
host       <tv>:36669
TLS        client certificate (bundled), server verification disabled
username   hisenseservice
password   multimqttservice
client_id  <MAC-NO-COLONS-UPPERCASE>$vidaa_common

subscribe  /remoteapp/mobile/<client_id>/#
           /remoteapp/mobile/broadcast/#
publish    /remoteapp/tv/ui_service/<client_id>/actions/<action>
           /remoteapp/tv/platform_service/<client_id>/actions/<action>
           /remoteapp/tv/remote_service/<client_id>/actions/sendkey
```

Queries are matched by the reply topic leaf, never by a shared "last message"
slot. That avoids the broadcast-vs-reply race that breaks app/source lookups in
other implementations.
