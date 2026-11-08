# VayuMitra demo script (~4 min)

**Setup before you start:** broker + orchestrator + dashboard up
(`./infra/scripts/run_all.ps1`), phone app connected, UNO Q online (or
`python uno_q/python/main.py --mock`). Dashboard on the big screen.

1. **Setup (15 s).** Dashboard green, phone low risk, LED green.
   > "Four devices, one Wi-Fi, no cloud in the loop."

2. **Real data (20 s).** Breathe on the BME → humidity/temp move live on the
   dashboard + phone.
   > "Genuine hyperlocal sensing, sub-minute, on the edge."

3. **The spike (40 s).** "Pollution rises nearby." Trigger a **real spike**:
   - **PM2.5:** a wisp of **incense** / a **just-blown-out match** near the
     GP2Y1010 intake (smoke-detector part → fast + reliable), **or**
   - **VOC:** **hand sanitizer / an alcohol wipe** near the BME (instant,
     smoke-free).

   Risk climbs green→amber (LED amber) → **crosses critical** → **all four fire
   at once:** buzzer + red LED, phone full-screen alert with the personalized
   advisory, dashboard cascade red, cloud zone flagged. Call out the
   **cross-device latency** on the HUD.

4. **Personalized + predictive (30 s).** Show the on-device-LLM advisory
   sentence + the forecast ("indoor advised in ~25 min; safe window 6-7 pm"),
   tailored to this user's profile.

5. **Act & resolve (25 s).** Tap **Navigate** → Maps routes to the nearest
   clean-air zone; tap **I'm safe** (or press the Knob button) → buzzer stops,
   everything de-escalates to green. Closed loop.

6. **Edge proof (25 s).** **Turn Wi-Fi off** on the phone → the on-device model
   still shows a risk value. Then show the **NPU-vs-CPU benchmark** slide
   (`ai_pc/ml/benchmark.md`).
   > "Risk inference runs on the Hexagon NPU."

7. **Close.**
   > "Sensing on the microcontroller, intelligence on the NPU, action on the
   > phone, scale in the cloud — impossible on one device."

## Backup if a live spike is slow

Run `./infra/scripts/run_all.ps1 -Sim` and click the dashboard
**"🚨 Trigger demo spike"** button (calls the orchestrator `/trigger_spike`
endpoint). This reproduces steps 3-5 with zero peripherals.
