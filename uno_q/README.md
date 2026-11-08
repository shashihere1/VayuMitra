# UNO Q — firmware (sensing + actuation)

The MCU sketch reads **BME680/690 (I2C)** and the **GP2Y1010AU0F (analog + LED
pulse)**, drives the **buzzer + LED**, and bridges everything to Linux. The MPU
`python/main.py` reads the Bridge and publishes MQTT. It also runs **off
hardware** via a mock — the guaranteed demo fallback.

## Laptop path (no board) — guaranteed fallback

```bash
# with the broker running (see ai_pc/broker/README.md):
pip install -r uno_q/python/requirements.txt
python uno_q/python/main.py --mock
```
The mock emits synthetic BME + a periodic `pm25`/`voc` spike and prints the
buzzer/LED actions it receives. Publishes valid `SensorReading`s to
`vayumitra/telemetry/<DEVICE_ID>`.

## Hardware wiring

### BME680 / BME690 (I2C)
`VCC→3V3`, `GND→GND`, `SDA→SDA`, `SCL→SCL` (or the Qwiic connector). Address
**0x76** or **0x77**. UNO Q I/O is 3.3 V.

> **Wire/Wire1 gotcha:** the Qwiic/I2C bus may be `Wire` or `Wire1` on the UNO Q.
> If the BME isn't found on `Wire`, use the commented `Wire1` fallback in
> `sketch.ino`.

### GP2Y1010AU0F (analog optical dust sensor) — **external circuit required**
It won't work without these parts:
- **150 Ω** resistor in series on **V-LED**, with a **220 µF** cap from V-LED to GND.
- A **resistor divider on `Vo`** to keep it **≤ 3.3 V** (A0/A1 are *not* 5 V-tolerant).
  Record the exact ratio as `DUST_DIVIDER` in `sketch.ino`.

6-pin wiring:

| Pin | Signal | Connect to |
|---|---|---|
| 1 | V-LED | 5 V **via 150 Ω** (+ 220 µF to GND) |
| 2 | LED-GND | GND |
| 3 | LED | `DUST_LED_PIN` (GPIO 2) — pulse control |
| 4 | S-GND | GND |
| 5 | Vo | `DUST_ADC_PIN` (A0) **through the divider**, ≤ 3.3 V |
| 6 | Vcc | 5 V |

5 V from the UNO Q 5 V pin / USB hub; LED-control + ADC logic stay ≤ 3.3 V.

### Calibration
Measure the clean-air `Vo` (~0.6 V) and set `DUST_VOC_OFFSET`. Treat `pm25` as a
**relative** proxy (not calibrated µg/m³). `pm10`/`pm1_0` are published null; the
orchestrator derives `pm10 ≈ pm25 × 1.4`.

## Build & run in App Lab

1. Create the app in **Arduino App Lab**; paste in `sketch/sketch.ino` and
   `python/main.py`.
2. Install sketch libraries (see `sketch/sketch.yaml`): Adafruit BME680, Adafruit
   Unified Sensor, Modulino. (BME690 → Bosch BME690_SensorAPI / BSEC 3.x.)
3. Set Wi-Fi and `MQTT_HOST` (the AI PC's LAN IP), `DEVICE_ID`, `USER_ID`.
4. Flash the MCU, then start the app:
   ```bash
   arduino-app-cli app start ~/ArduinoApps/vayumitra
   arduino-app-cli app logs  ~/ArduinoApps/vayumitra
   ```

## Bridge API

`sketch.ino` uses `Bridge.provide()/expose()/notify()` and `main.py` reads the
Bridge on the Python side. **Match these names to your installed App Lab Bridge
example's exact API** — they vary by runtime version. `main.py` looks for a
`bridge_hw.RealBridge`; provide that thin adapter around your Bridge, or run
`--mock`.

## Demo spikes

- **PM2.5:** a wisp of **incense** or a **just-blown-out match** near the
  GP2Y1010 intake (it's a smoke-detector part — fast + reliable).
- **VOC:** **hand sanitizer / an alcohol wipe** near the BME (instant, smoke-free).
