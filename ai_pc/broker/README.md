# Mosquitto broker (AI PC)

A single Mosquitto broker is the only thing linking the devices. It runs on the
AI PC (Snapdragon Surface); the UNO Q and the phone connect to it over the venue
Wi-Fi.

## Install (Windows ARM64)

```powershell
winget install EclipseFoundation.Mosquitto
```

## Run (verbose)

```powershell
mosquitto -c ai_pc/broker/mosquitto.conf -v
```

Leave this window open. `run_all.ps1` starts it for you.

## Let LAN devices reach it

1. **Open TCP 1883 in Windows Firewall** (one-time):
   ```powershell
   New-NetFirewallRule -DisplayName "VayuMitra MQTT 1883" -Direction Inbound `
       -Protocol TCP -LocalPort 1883 -Action Allow
   ```
2. **Find the LAN IP** of the AI PC:
   ```powershell
   ipconfig    # look for the Wi-Fi adapter's IPv4 Address, e.g. 192.168.1.42
   ```
   That IP is the value every device puts in `MQTT_HOST` (in `.env` for the
   orchestrator, in the App Lab config for the UNO Q, and in the phone app).

## Quick sanity check

```powershell
# subscribe in one terminal
mosquitto_sub -h 127.0.0.1 -t "vayumitra/#" -v
# publish in another
mosquitto_pub -h 127.0.0.1 -t "vayumitra/test" -m "hello"
```
