"""Thin paho-mqtt wrapper: connect + auto-reconnect, Last-Will (LWT),
subscribe to a topic set, and hand decoded JSON payloads to a callback.

Design goals (from the plan):
  * **Never crash on connect failure** — paho's ``connect_async`` + ``loop_start``
    reconnect with backoff on their own network thread.
  * Publishing before/without a connection is safe (queued or dropped, logged).
  * Works with paho-mqtt 2.x (CallbackAPIVersion) and falls back to 1.x.

The callbacks run on paho's network thread.  ``on_message`` here just decodes
JSON and forwards ``(topic, payload_dict)`` to the user callback, which is
responsible for thread-hopping into asyncio if needed.
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Callable, Iterable, Optional

import paho.mqtt.client as mqtt

log = logging.getLogger("vayumitra.mqtt")

# Detect paho major version for the callback API.
_PAHO2 = hasattr(mqtt, "CallbackAPIVersion")


class MqttClient:
    def __init__(
        self,
        host: str,
        port: int,
        client_id: str,
        on_message: Callable[[str, dict], None],
        subscriptions: Optional[Iterable[str]] = None,
        lwt_topic: Optional[str] = None,
        lwt_payload: Optional[dict] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self._on_message = on_message
        self._subs = list(subscriptions or [])
        self._lwt_topic = lwt_topic
        self._lwt_payload = lwt_payload
        self.connected = threading.Event()

        if _PAHO2:
            self._c = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_id,
                clean_session=True,
            )
        else:  # paho 1.x
            self._c = mqtt.Client(client_id=client_id, clean_session=True)

        self._c.on_connect = self._cb_connect
        self._c.on_disconnect = self._cb_disconnect
        self._c.on_message = self._cb_message

        # Reconnect with exponential backoff (1s .. 30s).
        self._c.reconnect_delay_set(min_delay=1, max_delay=30)

        if lwt_topic is not None:
            payload = json.dumps(lwt_payload) if lwt_payload is not None else ""
            self._c.will_set(lwt_topic, payload, qos=1, retain=True)

    # --- paho callbacks (network thread) ---------------------------------- #
    def _cb_connect(self, client, userdata, flags, reason_code, properties=None):
        # reason_code is an int (1.x) or ReasonCode (2.x); 0 / Success == ok.
        ok = (getattr(reason_code, "value", reason_code) == 0)
        if ok:
            self.connected.set()
            log.info("MQTT connected to %s:%s as %s", self.host, self.port, self.client_id)
            for topic in self._subs:
                client.subscribe(topic, qos=1)
                log.info("  subscribed: %s", topic)
            # Announce ourselves online (retained), overriding the LWT.
            if self._lwt_topic and self._lwt_payload is not None:
                online = dict(self._lwt_payload)
                online["online"] = True
                self.publish(self._lwt_topic, online, retain=True)
        else:
            log.warning("MQTT connect failed rc=%s (will retry)", reason_code)

    def _cb_disconnect(self, client, userdata, *args):
        self.connected.clear()
        log.warning("MQTT disconnected (will auto-reconnect)")

    def _cb_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            log.warning("dropping non-JSON message on %s: %s", msg.topic, e)
            return
        try:
            self._on_message(msg.topic, payload)
        except Exception:  # never let a handler kill the network thread
            log.exception("on_message handler raised for topic %s", msg.topic)

    # --- public API ------------------------------------------------------- #
    def start(self) -> None:
        """Connect asynchronously and spin the network loop on its own thread."""
        try:
            self._c.connect_async(self.host, self.port, keepalive=30)
        except Exception as e:  # DNS etc. — loop_start still retries
            log.warning("initial connect_async failed (%s); loop will retry", e)
        self._c.loop_start()

    def publish(self, topic: str, payload: dict, qos: int = 1, retain: bool = False) -> None:
        try:
            data = json.dumps(payload)
        except (TypeError, ValueError) as e:
            log.error("refusing to publish non-serializable payload on %s: %s", topic, e)
            return
        info = self._c.publish(topic, data, qos=qos, retain=retain)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            log.debug("publish rc=%s on %s (not yet connected?)", info.rc, topic)

    def subscribe(self, topic: str) -> None:
        if topic not in self._subs:
            self._subs.append(topic)
        if self.connected.is_set():
            self._c.subscribe(topic, qos=1)

    def stop(self) -> None:
        try:
            self._c.loop_stop()
            self._c.disconnect()
        except Exception:
            pass
