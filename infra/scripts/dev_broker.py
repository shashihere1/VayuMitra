"""Laptop-only dev MQTT broker (pure Python, no install of Mosquitto needed).

For local testing when you don't want to install Mosquitto. At the hackathon /
in the real demo, use Mosquitto instead (see ai_pc/broker/README.md) — it's the
production broker and the phone + UNO Q expect it. This script just lets you
exercise the full software cascade on a bare laptop.

    pip install amqtt          # one-time
    python infra/scripts/dev_broker.py

Listens on 0.0.0.0:1883, anonymous, same as mosquitto.conf.
"""
from __future__ import annotations

import asyncio
import logging

logging.basicConfig(level=logging.WARNING)

try:
    from amqtt.broker import Broker
except Exception:
    raise SystemExit("amqtt not installed. Run:  pip install amqtt")

CONFIG = {
    "listeners": {"default": {"type": "tcp", "bind": "0.0.0.0:1883"}},
    "sys_interval": 0,  # disable the $SYS stats task (avoids a noisy plugin path)
    "auth": {"allow-anonymous": True, "plugins": ["auth_anonymous"]},
}


async def main() -> None:
    broker = Broker(CONFIG)
    await broker.start()
    print("dev broker listening on 0.0.0.0:1883 (Ctrl+C to stop)", flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\ndev broker stopped")
