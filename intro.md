# VayuMitra — A Complete Introduction (for everyone)

> *"Vayu" means air, "Mitra" means friend. VayuMitra is a personal air-quality
> friend that watches the air you breathe and warns you — and everyone around
> you — the moment it becomes dangerous.*

This document explains the **whole project** from scratch. It starts with the
dream, then explains it for a non-technical person, then walks a beginner
(someone who has never touched Arduino or hardware) through every part, and
finally explains every technical word in plain English. Read it top to bottom
and you'll understand the entire system.

---

## Part 1 — The Vision (the "why")

Millions of people have **asthma**. For them, bad air isn't just unpleasant — a
sudden spike in smoke, dust, or fumes can trigger a dangerous attack within
minutes. The problem is that:

- **Air quality is hyperlocal.** The air right next to you (a smoky kitchen, a
  dusty street corner, a room with fresh paint) can be far worse than what a
  city-wide "AQI" number says.
- **Warnings come too late.** By the time you *feel* the bad air, the attack may
  already be starting.
- **Everyone is different.** A humidity level that's fine for one person can
  trigger another person's asthma.

**Our dream:** a small, affordable "air companion" that:

1. **Senses the air right where you are**, every few seconds.
2. **Understands *your* personal risk** — not a generic number, but a score
   tuned to your asthma severity and triggers.
3. **Predicts trouble before it arrives** ("humidity will cross your danger line
   in ~25 minutes").
4. **Acts instantly and everywhere at once** when danger is real: a buzzer and
   red light on the device, a full-screen alarm on your phone with one-tap
   directions to clean air, and a flag on a shared city map.
5. **Works without the internet.** All the important thinking happens on
   devices in the room ("on the edge"), so it keeps working even if Wi-Fi or the
   cloud goes down.

This is being built for the **Qualcomm Snapdragon Multiverse Hackathon**, whose
theme is *multi-device orchestration* — making several devices cooperate to do
something no single device could do alone. VayuMitra's showpiece is exactly
that: **one air-quality event making four devices react together in under a
second.**

---

## Part 2 — How it works, explained for anyone

Imagine four teammates in a relay race:

1. **The Sensor Box** (a small board with air sensors) is like a **nose**. It
   constantly sniffs the air and shouts out numbers: "dust is 20… 22… now 300!"

2. **The Brain** (a laptop/mini-PC) listens to the nose. It does the thinking:
   "Given this person's asthma, a dust level of 300 that's *rising fast* means
   HIGH DANGER." It decides what everyone should do.

3. **The Phone** is like a **personal bodyguard** in your pocket. When the Brain
   says "danger!", the phone throws up a big red full-screen warning, tells you
   what to do, and offers one-tap directions to the nearest clean-air spot.

4. **The Cloud** (optional, a server on the internet) is like a **city map** —
   it collects danger reports from many sensor boxes and shows which
   neighbourhoods are bad right now.

They all talk to each other through a shared **"group chat"** (this is a piece of
software called a *message broker* — more on that soon). Nobody talks directly;
everybody just posts messages to the group chat, and whoever cares reads them.

**The star of the show — the "cascade":** When the air suddenly gets dangerous,
the Brain doesn't just do one thing. It fires a coordinated chain reaction:

> Buzzer sounds **+** device light turns red **+** phone screen goes full-screen
> red **+** city map flags the zone — **all at the same instant.**

And it's a closed loop: you tap **"I'm safe"** on the phone (or press a button on
the device), the buzzer stops, the lights go back to green, and everything calms
down. That whole loop — danger detected → everyone reacts → you acknowledge →
everyone relaxes — is the thing we're most proud of.

**Why is this special?** Because it's *coordination*. Any one device is dumb
alone. Together, they behave like a single, intelligent safety system.

---

## Part 3 — The four devices and the flow (still simple)

```
   THE NOSE                 THE BRAIN                     THE BODYGUARD
 ┌───────────┐   air      ┌──────────────────┐  risk +   ┌───────────┐
 │ Sensor    │  numbers   │  Laptop / PC     │  alarms   │  Phone    │
 │ Box       │ ─────────► │  (the thinking)  │ ────────► │  (Android)│
 │ (Arduino) │ ◄───────── │                  │ ◄──────── │           │
 └───────────┘  commands  └──────────────────┘   "safe"  └───────────┘
                                  │
                                  ▼
                          ┌──────────────┐
                          │  Cloud map   │  (optional, the "city view")
                          └──────────────┘
```

The one thing connecting them all is a **group chat** running on the Brain
(the laptop). Every message has a strict, agreed-upon format so no one gets
confused — like everyone in the chat agreeing to always write the date the same
way.

---

## Part 4 — The technical walkthrough, for a total beginner

Now we go one level deeper, but still in plain language. I'll introduce each
piece and explain *what it is* and *why it's there*. Don't worry if a word is
new — everything is also in the **Glossary** at the end.

### 4.1 The "group chat": MQTT and Mosquitto

The devices need a way to talk. We use a system called **MQTT**.

- **What is MQTT?** It's a simple messaging language for small devices. It works
  on a **"publish / subscribe"** idea, like a notice board:
  - A device **publishes** (posts) a message to a **topic** (a labelled slot on
    the board), e.g. the topic `telemetry/sensor-1`.
  - Other devices **subscribe** (sign up) to topics they care about, and they
    automatically receive any message posted there.
  - The publisher and subscriber never need to know about each other. This is
    what keeps the four devices **loosely coupled** (independent).

- **What is a "broker"?** The notice board itself needs to run somewhere. The
  program that hosts the board — receiving posts and delivering them to
  subscribers — is called the **broker**.

- **What is Mosquitto?** **Mosquitto** is just a popular, free, lightweight
  program that acts as that MQTT broker. When we say "run Mosquitto", we mean
  "start the notice-board program so the devices can post and read messages."
  We run it on the laptop (the Brain). *(For laptop-only testing without
  installing Mosquitto, we include a tiny Python stand-in broker called
  `dev_broker.py` that does the same job.)*

- **Why local (not internet)?** The broker runs on the local Wi-Fi network in
  the room. No message needs to leave the building. That's what "runs on the
  edge" means and why it keeps working with no internet.

> **Analogy:** MQTT is the *language*, a topic is a *chat channel*, publishing is
> *posting a message*, subscribing is *joining a channel*, and Mosquitto is the
> *chat server* everyone connects to.

### 4.2 The "shared agreement": the contract

If the sensor box posts a message and the phone reads it, they must agree on the
**exact shape** of that message — which fields exist, what they're called, what
type each is. This agreement is called the **contract**.

- We wrote the contract in one place (`packages/contract/`) so all four devices
  copy the *same* rules. This is the **only** thing the four parts of the code
  share — everything else is independent.
- It has three pieces:
  - **Topics** (the list of channel names, e.g. `telemetry/<device>`,
    `risk/<user>`, `emergency/alert`).
  - **Message shapes** (e.g. a "SensorReading" always has `pm25`, `temperature`,
    `humidity`, and a timestamp).
  - **A validator** — code that checks "is this message legal?" and rejects
    malformed ones, so a bug in one device can't poison the others.

- **What is JSON?** The messages are written in **JSON**, a simple text format
  of `"name": value` pairs that both humans and computers can read easily, e.g.
  `{"pm25": 42.0, "temperature": 28.4}`.
- **What is a JSON Schema?** It's a rulebook *for* JSON — it says "a
  SensorReading must have a number called pm25 between 0 and 500", etc. Our
  validator uses it to check every message.
- **What is pydantic?** A Python helper that turns those rules into easy-to-use
  Python objects and fills in defaults, so our code builds correct messages
  without hand-typing every field.

### 4.3 The sensors — the actual hardware (explained from zero)

The sensor box has two real sensors. Here's what they are and how they're read.

**Sensor 1 — the BME680 (or BME690).** A tiny chip that measures four things:
**temperature**, **humidity** (how much moisture is in the air),
**air pressure**, and a **gas/VOC** signal.

- **What is VOC?** *Volatile Organic Compounds* — fumes from things like alcohol,
  paint, cleaning sprays, perfume. The chip can't name the exact chemical, but
  it can tell "the air just got more chemically polluted." We turn its raw
  reading into a simple **VOC index** (0 = clean, higher = more fumes). A great
  demo: wave an alcohol wipe near it and the number jumps.
- **How is it wired?** Over a connection called **I²C** (pronounced "I-squared-C"
  or "I-two-C"). Think of I²C as a tiny two-wire conversation line that lets a
  chip and the board talk. You just connect four wires (power, ground, and two
  data wires) and the board can ask the chip "what are your readings?".

**Sensor 2 — the GP2Y1010AU0F** (a Sharp optical dust sensor). This measures
**dust / smoke** in the air, which we use as a stand-in for **PM2.5**.

- **What is PM2.5?** "Particulate Matter 2.5 microns" — extremely tiny dust/soot
  particles small enough to get deep into your lungs. It's the single most
  important pollutant for asthma, so it's our **most important number**.
- **How does this sensor work?** It shines a tiny infrared LED inside a little
  chamber and measures how much light bounces off floating dust. More dust →
  more scattered light → higher reading. Because it's basically a smoke detector,
  a **wisp of incense or a just-blown-out match** near it spikes the reading fast
  and reliably (a perfect demo).
- **Why is it trickier than the BME?** It gives an **analog** signal (a
  voltage), not neat digital numbers, and it needs precise timing: you must pulse
  its LED on for a few *microseconds*, read the voltage at the exact right
  instant, then turn the LED off — 100 times a second — and average the results
  because the raw signal is noisy.
  - **What is analog vs digital?** *Digital* = clean numbers the chip hands over.
    *Analog* = a continuously varying voltage the board must *measure* itself
    with an **ADC** (Analog-to-Digital Converter — a part that turns a voltage
    into a number).
- **Why does it need an extra circuit?** Its output voltage can go slightly
  higher than the board safely accepts, so we add a couple of cheap electronic
  parts (a resistor and a capacitor, plus a "voltage divider") to keep it in a
  safe range. This is the only soldering/breadboard work in the whole project.
- **Honest limitation:** this cheap sensor gives one crude dust number, not a
  lab-grade PM2.5 in exact units. So we treat it as a **relative** indicator
  ("dust is rising fast") rather than a certified measurement. That's perfectly
  fine for detecting a dangerous *change*.

### 4.4 The sensor board — Arduino UNO Q, and the MCU vs MPU idea

The board that holds the sensors is an **Arduino UNO Q**. Arduino is a family of
beginner-friendly electronics boards. This particular board is special because it
has **two brains on one board**:

- **The MCU (Microcontroller).** A small, real-time chip that is great at precise
  physical timing (like pulsing that dust-sensor LED every 10 milliseconds
  without ever being late). It talks directly to the sensors, the buzzer, and the
  LED. Think of it as the **hands and reflexes**.
- **The MPU (Microprocessor).** A more powerful chip that runs full **Linux**
  (a proper operating system) and can do networking — like connecting to Wi-Fi
  and posting MQTT messages. Think of it as the **communicator**.

- **Why split the work?** Precise microsecond timing must happen on the MCU
  (Linux is too "busy" to be that punctual). Networking is easy on the MPU. So:
  - **The MCU** reads both sensors, computes the numbers, and drives the buzzer
    and LED.
  - **The MPU** takes those numbers and posts them to the MQTT group chat, and
    listens for commands like "sound the alarm."

- **What is the "Bridge"?** The two brains are on one board but are separate
  chips, so they need a way to hand data to each other. That internal
  hand-off channel is called the **Bridge**. The MCU puts the latest readings on
  the Bridge; the MPU picks them up. When a command like "alarm on" arrives from
  the network, the MPU calls across the Bridge to tell the MCU to buzz.
- **What is "App Lab"?** Arduino's software tool for creating and running these
  two-brain apps. You paste in the MCU code (`sketch.ino`) and the MPU code
  (`main.py`), and it flashes/runs them on the board.
- **What is a "sketch"?** Just the Arduino word for a program that runs on the
  board (the `.ino` file).

**Important for you (no hardware yet):** we built a **"mock"** version
(`mock_hw.py`) that *pretends* to be the sensor board. It invents realistic
sensor numbers (including fake pollution spikes) and prints "BUZZER ON",
"LED red" instead of touching real hardware. This means **you can run and test
the entire system on a plain laptop today**, with no Arduino at all. When the
real board arrives, you swap the mock for the real board — nothing else changes.

### 4.5 The Brain — the "orchestrator"

The most important software is the **orchestrator** (in `ai_pc/orchestrator/`).
It runs on the laptop/PC, listens to sensor messages, thinks, and reacts. Here
are its parts, in the order data flows through them:

**(a) It receives readings.** It subscribes to the sensor topics on the broker.
Every new reading gets processed.

**(b) `features.py` — building the "clues".** A single snapshot ("dust is 300")
isn't enough; *trend* matters. This part keeps the last ~10 minutes of readings
and computes extra clues like **rate of change** ("dust is rising 30 units per
minute"). It bundles everything into a fixed list of 11 numbers called the
**feature vector** — the standard input the rest of the system expects.

**(c) `heuristic.py` — the built-in scorer.** A **heuristic** is a sensible
hand-written formula (rules of thumb). Ours turns those 11 numbers into a
**risk score from 0 to 100**, weighting PM2.5 the most, then humidity extremes,
fumes, rapid temperature drops, etc., and scaling by *your* asthma severity and
sensitivity. It also explains itself, returning the top 2–3 reasons ("high
PM2.5", "rapid PM2.5 rise"). This formula always works and needs no AI, so the
system is never helpless.

**(d) `inference.py` — the smarter AI model (with safe fallbacks).** We also
train a small **neural network** (an AI model that learns patterns from data) to
predict the same score. On the hackathon's special hardware it runs on the
**NPU** for speed and low power.
- **What is a neural network / model?** Software that has "learned" from many
  examples to map inputs (the 11 numbers) to an output (a risk score).
- **What is the NPU?** *Neural Processing Unit* — a chip designed specifically
  to run AI models very fast and efficiently, separate from the regular CPU. The
  Snapdragon laptop has one (its "Hexagon" NPU). Running our model there is a
  key hackathon goal.
- **What is ONNX?** A standard file format for saving a trained AI model so
  different programs/hardware can run it. We export our model as an ONNX file.
- **What is quantization / INT8?** A trick to shrink an AI model so it runs
  faster on the NPU: instead of high-precision decimal numbers, it uses small
  8-bit integers (**INT8**). Slightly less precise, much faster and lighter.
- **The safety net:** the code tries the **NPU** first; if that's unavailable it
  falls back to the ordinary **CPU**; if even the model file is missing it falls
  back to the **heuristic** formula. So it *always* produces a score, on any
  machine. (On your laptop today, it uses the heuristic — and that's fine.)

**(e) `forecast.py` — predicting the near future.** Using the recent trend, it
projects the next 30 minutes ("PM2.5 will keep rising and cross your danger line
in ~12 minutes; a safe window opens around minute 20"). It uses a classic,
lightweight prediction method called **Holt's smoothing** (a way to extend a
trend line forward).

**(f) `advisory.py` — the one-sentence advice.** It turns the situation into a
single helpful sentence ("Air is hazardous now — move indoors and keep your
inhaler ready"). Ideally a small **on-device language model** writes it; if that
isn't available, we use pre-written **templates**. Either way you get clear
advice instantly.
- **What is Foundry Local?** Microsoft's tool for running a small AI **language
  model** (the kind that writes text, like a mini-ChatGPT) *locally* on the
  laptop's NPU — no internet. We use it for the advice sentence, with templates
  as backup.

**(g) `cascade.py` — THE HERO: the emergency state machine.** This decides when
to raise and lower the alarm, and coordinates all four devices. It's built as a
**state machine**: at any moment the system is in one of four states —
`NORMAL → WATCH → EMERGENCY → ACKED` — and it moves between them by clear rules.
- **What is a state machine?** A model where something is always in exactly one
  "state," and specific events move it to another state. (Like a traffic light:
  green → amber → red, by fixed rules.)
- **Why not just "if score > 75, alarm"?** Because raw sensor data is jumpy; a
  single flicker over the line shouldn't blast the alarm, and one dip shouldn't
  cancel a real emergency. So we use two safeguards:
  - **Dwell:** the score must stay high for *several readings in a row* before
    escalating (no false alarms from a one-off blip).
  - **Hysteresis:** the level to *turn on* the alarm is higher than the level to
    *turn it off*, so it can't rapidly flip on-off-on ("flapping"). *(Hysteresis
    just means "different thresholds for going up vs coming down.")*
- **What "firing the cascade" does (all at once):** it creates one shared
  **alert ID**, then publishes an **EmergencyAlert** (phone + cloud), a
  **DeviceCommand** to sound the buzzer + turn the LED red, and records the exact
  time so we can measure how fast every device reacted.
- **The ack loop:** *ack* = acknowledge. When you tap "I'm safe" (or press the
  device button), an **EmergencyAck** message comes back, the buzzer stops, and
  after the air clears the system returns to green and sends a "clear" command.
  If nobody acks within 20 seconds, it re-alerts (so a real emergency isn't
  ignored).

**(h) `metrics.py` — the stopwatch.** It timestamps every hop and reports
latencies ("sensor→risk took 3 ms", "alert→ack took 900 ms"), shown on the
dashboard. This proves the coordination is genuinely fast.

**(i) `main.py` — the conductor.** Wires all the above together, runs everything
concurrently, and also opens a tiny web control panel (a few web addresses like
`/state` and `/trigger_spike`) so the dashboard can peek at the internal state
and manually fire a demo spike.
- **What is FastAPI / an "API endpoint"?** FastAPI is a Python tool for making
  small web addresses your other programs can call. An **endpoint** is one such
  address (e.g. `/trigger_spike` = "please simulate a pollution spike now").
- **What is a "simulator"?** Built-in fake sensor data so the whole system can
  run and demo with **no hardware** (the `--sim` mode). Insurance for the stage.

### 4.6 The dashboard — the big screen

`ai_pc/dashboard/app.py` is a **dashboard**: a live web page (opened in a
browser) showing everything at a glance — the risk gauge coloured by level, live
charts of PM2.5/VOC/temperature/humidity, the cascade state (a big green/amber/
red box mirroring the device LED), the latency stopwatch, the forecast, and a
**"Trigger demo spike"** button as a stage backup.
- **What is Streamlit?** A Python tool that turns a simple script into a nice
  interactive web dashboard without writing website code. That's what powers
  this screen.

### 4.7 The phone app — Android (Kotlin / Jetpack Compose)

`mobile/` is a full **Android app**. It:
- Lets you set your **profile** (asthma severity, triggers, sensitivity, meds),
  which personalises your risk.
- Shows your **live risk** and sensor readings.
- Flips to a **full-screen red emergency** when danger fires, with your
  personalised advice, a **"Navigate"** button (one tap opens Google Maps to the
  nearest clean-air spot), and an **"I'm safe"** button that sends the ack.
- Runs its **own copy of the model on the phone**, so if Wi-Fi drops it *still*
  shows a risk value (offline capability).

Terms:
- **Kotlin** — the modern programming language for Android apps.
- **Jetpack Compose** — the modern toolkit for building Android screens by
  describing what they should look like.
- **LiteRT / TFLite (TensorFlow Lite)** — a way to run a small AI model *on the
  phone* efficiently. If the model file isn't present, the app falls back to the
  same heuristic formula, so it's never blank.
- **HiveMQ client** — the phone's library for talking MQTT to the same broker.

### 4.8 The cloud — the city map (optional / future)

`cloud/` collects danger reports from many sensor boxes, groups them by
geographic area into **zones**, and publishes a city-wide view plus a rough
1–2 day outlook. It's optional: if a real cloud AI service isn't connected, it
produces a simple template forecast so the demo still shows a map. This is
mostly **future work**.
- **What is "the cloud"?** Simply "someone else's computer on the internet" —
  a server you send data to for large-scale processing. Everything *else* in
  VayuMitra runs locally; the cloud is the one optional online piece.

### 4.9 The "glue" — scripts and tests

- **`infra/scripts/`** — one-command helpers: `setup.ps1` (install everything),
  `run_all.ps1` (start broker + brain + dashboard together), `stop_all.ps1`
  (stop them), plus `dev_broker.py` and `demo_cascade.py` for laptop-only
  testing.
  - **What is PowerShell / a `.ps1` file?** PowerShell is the Windows command-
    line/scripting tool; a `.ps1` file is a script it runs (like a recipe of
    commands).
- **`tests/`** — automatic checks that prove the important logic is correct
  (the contract, the scoring formula, and especially the cascade). Run with
  `pytest`. **All 21 tests currently pass.**
  - **What is pytest / a "test"?** A test is a small piece of code that checks
    "given this input, do we get the expected output?". pytest runs them all and
    reports pass/fail, so we catch mistakes automatically.

---

## Part 5 — Follow one pollution spike through the whole system

Let's trace exactly what happens, end to end, when smoke hits the sensor:

1. **Smoke drifts near the dust sensor.** The MCU's dust reading jumps from ~20
   to ~350. The MCU also reads temperature/humidity/fumes from the BME.
2. **MCU → Bridge → MPU.** The MPU grabs these numbers and **publishes** a
   `SensorReading` message to the topic `telemetry/unoq-01` on the broker.
3. **The broker delivers** that message to everyone subscribed — including the
   orchestrator (Brain) and the dashboard.
4. **The Brain builds features** (adds "dust is rising fast") and computes a
   **risk score** — say **96 / 100, "critical"** — and publishes a
   `RiskAssessment` to `risk/demo-user`. The phone and dashboard show it.
5. **The cascade reacts.** Score stays critical for two readings (dwell) →
   state goes `WATCH → EMERGENCY` → it **fires the cascade**:
   - `EmergencyAlert` → phone (full-screen) + cloud (flag the zone),
   - `DeviceCommand{alarm_on, led red}` → the MPU → across the Bridge → the MCU
     sounds the buzzer and turns the LED red.
   - All sharing one alert ID, all timestamped.
6. **You respond.** The phone shows "Navigate to Shivaji Park (640 m)" and
   "I'm safe". You tap **I'm safe** (or press the device button) → an
   `EmergencyAck` goes back to the Brain.
7. **De-escalation.** The Brain moves to `ACKED`, silences the buzzer, turns the
   LED amber; once the air clears for a few readings it returns to `NORMAL`,
   sends a `clear` command, and the LED goes green. **Loop closed.**

The dashboard's stopwatch shows the whole "danger → all devices reacting"
happened in well under a second. **That is the multi-device orchestration we're
being judged on.**

---

## Part 6 — Glossary (every term, in one place)

| Term | Plain-English meaning |
|---|---|
| **Edge / on the edge** | Doing the computing on local devices in the room, not on the internet. Keeps working offline; more private; faster. |
| **MQTT** | A simple messaging system for devices, based on posting to and reading from named channels ("topics"). |
| **Topic** | A named channel on the message board (e.g. `risk/demo-user`). |
| **Publish / Subscribe** | Publish = post a message to a topic. Subscribe = sign up to receive messages from a topic. |
| **Broker** | The server program that hosts the topics and delivers messages between devices. |
| **Mosquitto** | A popular free program that acts as the MQTT broker. We run it on the laptop. |
| **`dev_broker.py`** | Our tiny Python stand-in broker, so you can test on a laptop without installing Mosquitto. |
| **LWT (Last Will & Testament)** | A message the broker sends on your behalf if you disconnect unexpectedly — so others know a device went offline. |
| **QoS (Quality of Service)** | How hard MQTT tries to deliver a message. We use level 1 = "deliver at least once." |
| **Retained message** | The broker remembers the *last* message on a topic and gives it to anyone who joins later (so a new subscriber isn't blank). |
| **Contract** | The shared agreement on message formats + topic names that all devices follow. The only thing they share. |
| **JSON** | A simple text format of `"name": value` pairs for data. |
| **JSON Schema** | A rulebook that defines what a valid JSON message looks like. |
| **Validate** | To check a message against the schema and reject it if it's malformed. |
| **pydantic** | A Python library that turns the message rules into convenient objects. |
| **Sensor** | A component that measures something physical (dust, temperature, etc.). |
| **BME680 / BME690** | A chip measuring temperature, humidity, pressure, and gas/VOC. |
| **GP2Y1010AU0F** | A cheap optical dust sensor we use as a PM2.5 (fine-dust) indicator. |
| **PM2.5** | Very fine dust/soot particles that harm the lungs — the top pollutant for asthma. |
| **VOC** | Volatile Organic Compounds — airborne fumes (alcohol, paint, sprays). We report a 0–500 "VOC index." |
| **I²C** | A two-wire connection standard letting the board talk to chips like the BME. |
| **Analog / Digital** | Analog = a varying voltage the board must measure. Digital = ready-made numbers. |
| **ADC** | Analog-to-Digital Converter — the part that turns a voltage into a number. |
| **Arduino** | A family of beginner-friendly electronics boards + software. |
| **UNO Q** | The specific Arduino board we use — it has both an MCU and an MPU. |
| **MCU (Microcontroller)** | The small real-time chip; handles precise timing, sensors, buzzer, LED. |
| **MPU (Microprocessor)** | The bigger chip running Linux; handles Wi-Fi and MQTT. |
| **Bridge** | The internal channel the MCU and MPU use to pass data on the same board. |
| **App Lab** | Arduino's tool to build and run these two-chip apps. |
| **Sketch** | An Arduino program (the `.ino` file) that runs on the board. |
| **Mock / mock_hw.py** | Fake hardware in software, so we can run everything with no real board. |
| **Simulator / `--sim`** | Built-in fake sensor data (with spikes) so the whole system demos with no hardware. |
| **Orchestrator** | The main "Brain" program on the laptop that thinks and coordinates. |
| **Feature vector** | The fixed list of 11 numbers (readings + trends + profile) fed to the scorer. |
| **Heuristic** | A sensible hand-written formula (rules of thumb) that computes the risk score without AI. |
| **Neural network / model** | AI software that learned to map inputs to an output (here, a risk score). |
| **CPU** | The general-purpose processor in any computer. |
| **NPU** | Neural Processing Unit — a chip specialised for running AI fast and efficiently. |
| **Hexagon** | The name of Qualcomm Snapdragon's NPU. |
| **ONNX** | A standard file format for saving a trained AI model. |
| **Quantization / INT8** | Shrinking a model to small 8-bit integers so it runs faster on the NPU. |
| **onnxruntime / onnxruntime-qnn** | Software that runs ONNX models; the "-qnn" version runs them on the Snapdragon NPU. |
| **Inference** | The act of running a trained model to get a prediction. |
| **Forecast / Holt's smoothing** | Predicting the near future by extending the recent trend forward. |
| **Advisory** | The single helpful sentence of advice shown to the user. |
| **Foundry Local** | Microsoft's tool to run a small text-writing AI model locally on the NPU. |
| **Template (fallback)** | A pre-written sentence used when the AI text model isn't available. |
| **Cascade** | Our hero feature: one event triggering coordinated actions across all devices at once. |
| **State machine** | A system that's always in one state and moves between states by rules. |
| **Dwell** | Requiring the condition to persist for several readings before acting (prevents false alarms). |
| **Hysteresis** | Using a higher threshold to turn on than to turn off, to prevent rapid flip-flopping. |
| **Ack (acknowledge)** | The "I'm safe" confirmation that silences the alarm and closes the loop. |
| **Alert ID** | A shared code tying together all messages/actions of a single emergency. |
| **Latency / metrics** | How long each step takes; we measure and display it to prove speed. |
| **FastAPI** | A Python tool for making small web addresses (APIs) other programs can call. |
| **API endpoint** | One such web address (e.g. `/trigger_spike`). |
| **Dashboard / Streamlit** | The live web page showing everything; Streamlit is the tool that builds it. |
| **Android / Kotlin / Jetpack Compose** | Android = the phone OS; Kotlin = the app language; Compose = the UI toolkit. |
| **LiteRT / TFLite** | A way to run a small AI model directly on the phone. |
| **HiveMQ client** | The phone's library for speaking MQTT to the broker. |
| **Haversine** | A formula for the distance between two GPS points (used to find the nearest clean-air zone). |
| **Cloud** | An internet server used for large-scale processing; here, optional/future. |
| **Zone** | A geographic area the cloud groups sensor reports into, for the city map. |
| **PowerShell / `.ps1`** | Windows' command-line scripting tool and its script files. |
| **pytest / test** | Automatic checks that verify the code behaves correctly. |
| **venv (virtual environment)** | An isolated Python setup for this project so its libraries don't clash with others. |

---

## Part 7 — What is done and what is tested today

**Fully built and verified on a plain laptop (no hardware):**
- ✅ The **contract** (shared message rules) — installs and validates.
- ✅ The **orchestrator / Brain** — features, heuristic scoring, forecast,
  advisory (templates), and the full **cascade** — running end to end.
- ✅ The **emergency cascade over a real message broker**: a simulated spike
  drives `NORMAL → WATCH → EMERGENCY → alert (with nearest safe zone) →
  buzzer + red LED → ack → alarm off → back to normal`. Verified with a
  one-command demo (`infra/scripts/demo_cascade.py`).
- ✅ The **live dashboard** (browser).
- ✅ The **sensor board's software in "mock" mode** — produces valid readings and
  reacts to commands, with zero hardware.
- ✅ The **cloud aggregator** (basic zones/outlook).
- ✅ **21 automatic tests pass.**
- ✅ All required Python libraries install on this machine.

**Written to specification but only fully runnable on the real gear
(hackathon PC + hardware):**
- ⏳ **Real sensors** (BME680/690 + GP2Y1010) and **buzzer/LED/button** on the
  Arduino UNO Q — needs the board, Arduino App Lab, and the small dust-sensor
  circuit (a resistor, a capacitor, and a voltage divider).
- ⏳ **AI model on the NPU** (`onnxruntime-qnn`) + the **NPU-vs-CPU speed
  benchmark** — needs the Snapdragon X Elite laptop. (On other machines it
  correctly falls back to CPU, then to the heuristic.)
- ⏳ **On-device advice model** (Foundry Local) — needs that tool installed;
  otherwise templates are used.
- ⏳ **Phone app on a device/emulator** — needs Android Studio to build and run.

**Roughly ~80% of the software is testable on a normal laptop today; ~20%
(real NPU numbers, the language model, and physical sensing/actuation) needs the
hackathon hardware.** Importantly, the scored hero — the multi-device cascade —
is 100% demoable on a laptop right now.

---

## Part 8 — What's not finished, and where we're headed

**Not yet done / to finish at the hackathon:**
1. **Physical hardware bring-up.** Wire and calibrate the two real sensors on the
   UNO Q, confirm the buzzer/LED/button work, and adapt the board's internal
   "Bridge" calls to the exact version installed on the hackathon machine.
2. **Train and quantize the real AI model**, then run it on the Snapdragon NPU
   and record the speed/energy benchmark vs the CPU.
3. **Turn on the on-device language model** (Foundry Local) for smarter,
   personalised advice sentences.
4. **Build and side-load the phone app**, connect it to the broker, and rehearse
   the full-screen alert + Maps navigation + "I'm safe" loop.
5. **Fine-tune the alarm thresholds** on real sensor data (the numbers that
   decide "warning" vs "critical") so live demos are crisp.

**Future vision (beyond the hackathon):**
- **A real cloud city-map** with a proper 24–48 hour air-quality outlook powered
  by cloud AI, aggregating many devices across a city.
- **Multiple users and multiple sensor boxes** — a household or a whole clinic.
- **Better, calibrated sensors** for true PM2.5 in exact units, and a
  medically-reviewed, personalised risk model trained on real patient data
  (today's model is trained on *synthetic* data — an honest, disclosed choice
  that lets us ship without a labelled medical dataset).
- **Integrations**: smart-home purifiers/ACs that turn on automatically, and
  caregiver/doctor notifications during an emergency.
- **More trigger types and predictive warnings** tuned to each person over time.

---

*In one line: VayuMitra senses the air on a tiny board, thinks about your
personal asthma risk on the edge, and makes four devices act as one to protect
you — instantly, and even offline.*
