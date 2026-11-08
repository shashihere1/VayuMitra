/*
 * VayuMitra — UNO Q MCU sketch (STM32 side).  ALL sensing + actuation.
 *
 *   - BME680/690 over I2C           -> temperature, humidity, pressure, gas
 *   - Sharp GP2Y1010AU0F (analog)   -> pm25 (dust proxy) via LED pulse + ADC
 *   - Modulino Buzzer               -> emergency alarm (driven by MPU command)
 *   - onboard RGB LED               -> cascade state (green/amber/red/off)
 *   - Modulino Knob button (opt.)   -> physical EmergencyAck
 *
 * The MCU bridges all values to Linux; the MPU (python/main.py) reads the
 * Bridge and publishes MQTT.  The sketch does NO networking and does NOT use
 * Serial1 (claimed by the Router).  The microsecond-precise GP2Y pulse is
 * exactly why this sensor lives on the MCU, not Linux.
 *
 * Bridge API note: `Bridge.provide()` / `Bridge.notify()` / RPC registration
 * names below follow plan.md; MATCH them to YOUR installed Arduino App Lab
 * Bridge example's exact API if it differs.
 */

#include <Wire.h>

// --- BME680 (default). For BME690 use the Bosch BME690_SensorAPI / BSEC 3.x
//     instead; wiring is identical. See uno_q/README.md. ----------------------
#include <Adafruit_Sensor.h>
#include <Adafruit_BME680.h>

// --- Modulino (Buzzer + Knob) over Qwiic/I2C --------------------------------
#include <Modulino.h>

// --- App Lab Bridge (MCU <-> Linux) -----------------------------------------
#include <Bridge.h>   // provided by the Arduino UNO Q App Lab runtime

// ---------------------------------------------------------------------------
// Pin / constant config (mirror of .env; these live authoritatively HERE).
// ---------------------------------------------------------------------------
#define BME_I2C_ADDR      0x76      // 0x76 or 0x77
static const int   DUST_LED_PIN  = 2;      // GP2Y1010 LED-pulse control GPIO
static const int   DUST_ADC_PIN  = A0;     // GP2Y1010 Vo through divider (<=3.3V)
static const float ADC_MAX       = 4095.0; // 12-bit ADC on the UNO Q
static const float VREF          = 3.3;    // ADC reference (volts)
static const float DUST_DIVIDER  = 1.5;    // Vo divider ratio (reconstruction)
static const float DUST_VOC_OFFSET = 0.6;  // clean-air Voc (V) — calibrate per unit

// GP2Y pulse timing (classic Sharp datasheet values); LED LOW = LED on.
static const int   DUST_SAMPLES  = 100;    // median/average window (~1 s)
static const unsigned long DUST_CYCLE_US = 10000; // 10 ms per sample

// ---------------------------------------------------------------------------
Adafruit_BME680 bme;                // uses the default Wire; see setup()
Modulino         modulino;
ModulinoBuzzer   buzzer;
ModulinoKnob     knob;

// Shared sensor values (published to the Bridge each loop).
float g_pm25 = 0.0f;
float g_temperature = 0.0f;
float g_humidity = 0.0f;
float g_pressure = 0.0f;
float g_voc_index = 0.0f;

// VOC baseline (rolling max of gas resistance in clean air).
float g_gas_baseline = 1.0f;

// Alarm/LED state.
bool  g_alarm = false;

// ---------------------------------------------------------------------------
// RGB LED helper.  Replace with the correct onboard-LED API for your board
// (many UNO Q variants expose LEDR/LEDG/LEDB or an RGB helper).
// ---------------------------------------------------------------------------
void setLed(const char *color) {
#if defined(LEDR) && defined(LEDG) && defined(LEDB)
  auto on = [](int pin, bool v){ pinMode(pin, OUTPUT); digitalWrite(pin, v ? LOW : HIGH); }; // active-low
  bool r=false,g=false,b=false;
  if      (!strcmp(color,"green")) g=true;
  else if (!strcmp(color,"amber")) { r=true; g=true; }
  else if (!strcmp(color,"red"))   r=true;
  // "off" -> all false
  on(LEDR,r); on(LEDG,g); on(LEDB,b);
#else
  (void)color;   // no-op if the board LED macros aren't available
#endif
}

// ---------------------------------------------------------------------------
// Bridge-callable actuation (invoked by the MPU via python/main.py).
// ---------------------------------------------------------------------------
void set_alarm(bool on) {
  g_alarm = on;
  if (on) {
    buzzer.tone(880, 500);   // 880 Hz for 500 ms — repeated by the loop while on
  } else {
    buzzer.tone(0, 1);       // silence
  }
}

void set_led(const char *color) {
  setLed(color);
}

// ---------------------------------------------------------------------------
// GP2Y1010AU0F read: pulse LED, sample ADC, average, reconstruct Vo -> pm25.
// ---------------------------------------------------------------------------
float readDustPM25() {
  long acc = 0;
  for (int i = 0; i < DUST_SAMPLES; i++) {
    unsigned long t0 = micros();
    digitalWrite(DUST_LED_PIN, LOW);      // LED on
    delayMicroseconds(280);               // settle, then sample
    int adc = analogRead(DUST_ADC_PIN);
    delayMicroseconds(40);
    digitalWrite(DUST_LED_PIN, HIGH);     // LED off (on-time ~320 us)
    acc += adc;
    // idle the rest of the 10 ms cycle without blocking too hard
    while (micros() - t0 < DUST_CYCLE_US) { /* spin briefly */ }
  }
  float adcAvg = (float)acc / DUST_SAMPLES;

  // reconstruct Vo (volts) through the divider
  float v = adcAvg / ADC_MAX * VREF * DUST_DIVIDER;
  v -= DUST_VOC_OFFSET;                    // subtract measured clean-air offset
  if (v < 0) v = 0;

  float dust_mg_m3 = 0.17f * v - 0.1f;     // common GP2Y approximation
  if (dust_mg_m3 < 0) dust_mg_m3 = 0;
  float pm25 = dust_mg_m3 * 1000.0f;       // ug/m3-equivalent
  if (pm25 > 500.0f) pm25 = 500.0f;
  return pm25;
}

// ---------------------------------------------------------------------------
void readBME() {
  if (!bme.performReading()) return;
  g_temperature = bme.temperature;                 // C
  g_humidity    = bme.humidity;                    // %
  g_pressure    = bme.pressure / 100.0f;           // hPa
  float gas     = (float)bme.gas_resistance;       // ohms

  // relative VOC index vs a rolling clean-air baseline (resistance high = clean)
  if (gas > g_gas_baseline) g_gas_baseline = gas;  // track the max seen
  float ratio = (g_gas_baseline > 0) ? (gas / g_gas_baseline) : 1.0f;
  float voc = 500.0f * (1.0f - ratio);
  if (voc < 0) voc = 0; if (voc > 500) voc = 500;
  g_voc_index = voc;
}

// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);

  pinMode(DUST_LED_PIN, OUTPUT);
  digitalWrite(DUST_LED_PIN, HIGH);   // LED off initially
  analogReadResolution(12);           // 12-bit ADC

  // I2C — the UNO Q Qwiic/I2C bus may be `Wire` or `Wire1`; adjust if the BME
  // isn't found (see the Wire/Wire1 gotcha in the README).
  Wire.begin();
  if (!bme.begin(BME_I2C_ADDR)) {
    Serial.println("BME680 not found at 0x76 — try 0x77 or Wire1");
    // raw-Wire fallback (uncomment to force a specific bus):
    // Wire1.begin(); bme.begin(BME_I2C_ADDR, &Wire1);
  } else {
    bme.setTemperatureOversampling(BME680_OS_8X);
    bme.setHumidityOversampling(BME680_OS_2X);
    bme.setPressureOversampling(BME680_OS_4X);
    bme.setIIRFilterSize(BME680_FILTER_SIZE_3);
    bme.setGasHeater(320, 150);       // 320 C for 150 ms
  }

  modulino.begin();
  buzzer.begin();
  knob.begin();
  setLed("green");

  // Expose values + functions to the Linux MPU over the Bridge.
  // (Match these to your App Lab Bridge example's exact API.)
  Bridge.begin();
  Bridge.provide("pm25",        &g_pm25);
  Bridge.provide("temperature", &g_temperature);
  Bridge.provide("humidity",    &g_humidity);
  Bridge.provide("pressure",    &g_pressure);
  Bridge.provide("voc_index",   &g_voc_index);
  Bridge.expose("set_alarm",    set_alarm);   // RPC: MPU -> MCU
  Bridge.expose("set_led",      set_led);
}

// ---------------------------------------------------------------------------
unsigned long lastBME = 0;
void loop() {
  // BME is slow; read it ~every 2 s. Dust is sampled every loop.
  if (millis() - lastBME > 2000) {
    readBME();
    lastBME = millis();
  }
  g_pm25 = readDustPM25();

  // keep the buzzer sounding while alarmed
  if (g_alarm) buzzer.tone(880, 300);

  // physical ack via the knob button -> notify the MPU
  if (knob.isPressed()) {
    Bridge.notify("knob_pressed");
  }

  Bridge.update();   // push provided values to Linux
}
