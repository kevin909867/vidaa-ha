#!/usr/bin/env python3
"""Read-only live check of the VIDAA client against a real TV.

Usage:
    .venv/bin/python vidaa-ha/scripts/live_test.py --host 10.1.1.56 \
        --mac e4:3b:c9:4c:aa:8d

This queries identity, apps, inputs, state and picture settings. It never
sends a key, changes an input, or launches anything.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "vidaa_ha"
sys.path.insert(0, str(COMPONENT))

from vidaa_client import VidaaClient  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="10.1.1.56")
    parser.add_argument("--port", type=int, default=36669)
    parser.add_argument("--mac", default="e4:3b:c9:4c:aa:8d")
    parser.add_argument(
        "--cert", default=str(COMPONENT / "certs" / "vidaa_client.pem")
    )
    parser.add_argument(
        "--key", default=str(COMPONENT / "certs" / "vidaa_client.key")
    )
    args = parser.parse_args()

    client = VidaaClient(
        args.host,
        args.mac,
        port=args.port,
        certfile=args.cert,
        keyfile=args.key,
    )
    try:
        await client.async_start()
    except Exception as err:  # noqa: BLE001
        print(f"CONNECT FAILED: {err!r}")
        return 1

    try:
        print("CONNECTED")
        print("client_id:", client.client_id)
        print("connected:", client.connected)
        print("device_info:", json.dumps(client.data["device_info"], indent=2))
        print("tv_info:", json.dumps(client.data["tv_info"], indent=2))
        print("capability:", json.dumps(client.data["capability"], indent=2))
        print(
            "power:", client.data["power"],
            "| detail:", client.data["detail"],
            "| volume:", client.data["volume"],
            "| muted:", client.data["muted"],
        )
        print("apps:", len(client.data["apps"]))
        for app in client.data["apps"]:
            print(
                f"  {app['app_id']:>5}  {app['display_name']:<32} "
                f"[{app['category']}]"
            )
        print("sources:", len(client.data["sources"]))
        for source in client.data["sources"]:
            print(
                f"  {source['source_id']:<8} {source['display_name']:<28} "
                f"signal={source.get('is_signal')}"
            )
        print("picture settings:", len(client.data["picture_settings"]))
        if client.data["picture_settings"]:
            print(
                "  first:",
                client.data["picture_settings"][0],
                "last:",
                client.data["picture_settings"][-1],
            )
        print("raw topics:", len(client.data["raw"]))

        failures = []
        if not client.data["device_info"]:
            failures.append("no device_info")
        if len(client.data["apps"]) < 1:
            failures.append("no apps")
        if len(client.data["sources"]) < 1:
            failures.append("no sources")
        if not client.data["picture_settings"]:
            failures.append("no picture settings")
        if failures:
            print("FAILED:", ", ".join(failures))
            return 1
        print("OK: all read-only queries returned data")
        return 0
    finally:
        await client.async_stop()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
