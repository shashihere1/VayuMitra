"""VayuMitra live dashboard (Streamlit).

Run:
    streamlit run ai_pc/dashboard/app.py

Subscribes to the MQTT broker in a background thread for live telemetry / risk /
forecast / emergency, and polls the orchestrator's ``/state`` endpoint for the
inference engine badge, cascade state and latency HUD.  Designed to be legible
from across the room.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
from collections import defaultdict, deque
from pathlib import Path

# make the repo importable when launched via `streamlit run`
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except Exception:
    pass

import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
API_PORT = int(os.getenv("API_PORT", "8000"))
PREFIX = "vayumitra"
MAXLEN = 240  # ~8 min at 2s cadence

LEVEL_COLOR = {"low": "#16a34a", "moderate": "#eab308",
               "high": "#f97316", "critical": "#dc2626"}
LED_COLOR = {"green": "#16a34a", "amber": "#eab308", "red": "#dc2626", "off": "#6b7280"}


class Store:
    """Thread-safe latest-state store fed by a background MQTT subscriber."""

    def __init__(self, host: str, port: int) -> None:
        self.lock = threading.Lock()
        self.telemetry_hist = defaultdict(lambda: deque(maxlen=MAXLEN))
        self.latest_reading = {}
        self.latest_risk = {}
        self.latest_forecast = {}
        self.last_alert = None
        self.connected = False

        if hasattr(mqtt, "CallbackAPIVersion"):
            self._c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id="vayumitra-dashboard")
        else:
            self._c = mqtt.Client(client_id="vayumitra-dashboard")
        self._c.on_connect = self._on_connect
        self._c.on_message = self._on_message
        self._c.reconnect_delay_set(1, 15)
        try:
            self._c.connect_async(host, port, keepalive=30)
        except Exception:
            pass
        self._c.loop_start()

    def _on_connect(self, *args):
        self.connected = True
        self._c.subscribe(f"{PREFIX}/#", qos=1)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return
        mt = payload.get("msg_type")
        with self.lock:
            if mt == "SensorReading":
                did = payload.get("device_id", "?")
                self.latest_reading[did] = payload
                self.telemetry_hist[did].append((time.time(), payload))
            elif mt == "RiskAssessment":
                self.latest_risk[payload.get("user_id", "?")] = payload
            elif mt == "ForecastUpdate":
                self.latest_forecast[payload.get("user_id", "?")] = payload
            elif mt == "EmergencyAlert":
                self.last_alert = payload

    def telemetry_df(self, device_id: str) -> pd.DataFrame:
        with self.lock:
            rows = list(self.telemetry_hist.get(device_id, []))
        if not rows:
            return pd.DataFrame()
        data = [{
            "time": pd.to_datetime(ts, unit="s"),
            "PM2.5": r.get("pm25"),
            "VOC": r.get("voc_index"),
            "Temp": r.get("temperature"),
            "Humidity": r.get("humidity"),
        } for ts, r in rows]
        return pd.DataFrame(data).set_index("time")


@st.cache_resource
def get_store(host: str, port: int) -> Store:
    return Store(host, port)


def fetch_orch_state() -> dict:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{API_PORT}/state", timeout=1.5) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return {}


def trigger_spike() -> bool:
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{API_PORT}/trigger_spike", method="POST")
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


# --------------------------------------------------------------------------- #
def main() -> None:
    st.set_page_config(page_title="VayuMitra", page_icon="🌬️", layout="wide")
    store = get_store(MQTT_HOST, MQTT_PORT)
    state = fetch_orch_state()

    st.markdown("## 🌬️ VayuMitra — live air-quality & asthma-risk dashboard")

    # top bar: connection + engine + spike button
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    c1.metric("Broker", "connected" if store.connected else "…", MQTT_HOST)
    c2.metric("Inference engine", (state.get("engine") or "—").upper())
    c3.metric("Advisory", (state.get("advisory_source") or "—"))
    if c4.button("🚨 Trigger demo spike", use_container_width=True):
        st.toast("Spike triggered" if trigger_spike() else "Spike endpoint unreachable")

    user_id = os.getenv("USER_ID", "demo-user")
    device_id = os.getenv("DEVICE_ID", "unoq-01")
    risk = store.latest_risk.get(user_id, {})
    reading = store.latest_reading.get(device_id, {})

    left, right = st.columns([2, 1])

    # --- left: charts + readings ---
    with left:
        st.markdown("#### Live sensors")
        m = st.columns(4)
        m[0].metric("PM2.5 (µg/m³-eq)", _fmt(reading.get("pm25")))
        m[1].metric("VOC index", _fmt(reading.get("voc_index")))
        m[2].metric("Temp (°C)", _fmt(reading.get("temperature")))
        m[3].metric("Humidity (%)", _fmt(reading.get("humidity")))

        df = store.telemetry_df(device_id)
        if not df.empty:
            st.line_chart(df[["PM2.5", "VOC"]], height=220)
            st.line_chart(df[["Temp", "Humidity"]], height=180)
        else:
            st.info("Waiting for telemetry… start the orchestrator (or --sim) and the UNO Q.")

    # --- right: risk gauge + cascade + advisory ---
    with right:
        level = risk.get("risk_level", "low")
        score = risk.get("risk_score", 0)
        color = LEVEL_COLOR.get(level, "#6b7280")
        st.markdown("#### Asthma risk")
        st.markdown(
            f"<div style='background:{color};border-radius:16px;padding:18px;"
            f"text-align:center;color:white'>"
            f"<div style='font-size:64px;font-weight:800;line-height:1'>{score:.0f}</div>"
            f"<div style='font-size:22px;text-transform:uppercase;letter-spacing:2px'>{level}</div>"
            f"<div style='font-size:12px;opacity:.85'>engine: {risk.get('engine','—')} · "
            f"{_fmt(risk.get('inference_ms'))} ms</div></div>",
            unsafe_allow_html=True,
        )
        if risk.get("top_factors"):
            st.caption("Top factors: " + ", ".join(risk["top_factors"]))
        if risk.get("advisory"):
            st.info(f"💬 {risk['advisory']}  \n*(source: {risk.get('advisory_source','—')})*")

        # cascade panel
        st.markdown("#### Emergency cascade")
        cascade = next((c for c in state.get("cascades", []) if c.get("user_id") == user_id), {})
        cstate = cascade.get("state", "NORMAL")
        led = {"NORMAL": "green", "WATCH": "amber", "EMERGENCY": "red", "ACKED": "amber"}.get(cstate, "off")
        st.markdown(
            f"<div style='background:{LED_COLOR[led]};border-radius:12px;padding:14px;"
            f"text-align:center;color:white;font-size:26px;font-weight:700'>{cstate}</div>",
            unsafe_allow_html=True,
        )
        if cascade.get("alert_id"):
            st.caption(f"alert_id: {cascade['alert_id']}")
        if store.last_alert:
            sz = store.last_alert.get("safe_zone") or {}
            st.caption(f"Last alert reason: {store.last_alert.get('reason','')} · "
                       f"nearest safe zone: {sz.get('name','—')}")

    # --- latency HUD + forecast ---
    st.markdown("---")
    h1, h2 = st.columns([1, 1])
    with h1:
        st.markdown("#### ⏱️ Latency HUD")
        metrics = state.get("metrics", {})
        hud = st.columns(3)
        hud[0].metric("ingest→risk (p50)", f"{_metric(metrics,'ingest_to_risk_ms','p50_ms')} ms")
        hud[1].metric("cascade→ack (last)", f"{_metric(metrics,'cascade_to_ack_ms','last_ms')} ms")
        hud[2].metric("inference (p50)", f"{_metric(metrics,'inference_ms','p50_ms')} ms")
    with h2:
        st.markdown("#### 🔮 Forecast (30 min)")
        f = store.latest_forecast.get(user_id, {})
        if f:
            breach = f.get("threshold_breach_min")
            st.write(f"PM2.5 threshold breach in: **{breach} min**" if breach
                     else "No PM2.5 threshold breach predicted 👍")
            windows = f.get("safe_windows", [])
            if windows:
                st.caption("Safe windows (min from now): " +
                           ", ".join(f"{w['start_min']:.0f}–{w['end_min']:.0f}" for w in windows[:4]))
            preds = f.get("predictions", {})
            if preds.get("pm25"):
                st.line_chart(pd.DataFrame({"PM2.5 forecast": preds["pm25"]}), height=140)
        else:
            st.caption("Forecast appears after ~30 s of telemetry.")

    # auto-refresh
    time.sleep(1.5)
    st.rerun()


def _fmt(v, nd=1):
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return "—"


def _metric(metrics: dict, series: str, field: str) -> str:
    try:
        return f"{metrics[series][field]:.1f}"
    except Exception:
        return "—"


# Streamlit executes the module top-to-bottom on every rerun.
main()
