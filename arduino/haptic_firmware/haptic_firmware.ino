// =====================================================
// Pulso Háptico - Firmware Arduino (mide + ejecuta, NO decide)
// Proyecto Pulso Háptico
// =====================================================
//
// Responsabilidad de este sketch (y SOLO esto):
//   1) Leer el Pulse Sensor Amped y calcular BPM, línea base (baseline)
//      y BPM suavizado.
//   2) Enviar esa telemetría cruda por Serial/USB.
//   3) Recibir por Serial un patrón háptico ya traducido (PATTERN/STEP/END)
//      y ejecutarlo sobre 6 motores vibradores.
//
// Lo que este sketch NO hace:
//   - No decide qué política aplicar según el BPM. Esa decisión (delta vs.
//     baseline -> reassure/awareness/breath/calm_down) la toma el backend
//     Django, que es quien manda el patrón correspondiente.
//
// Conexiones Pulse Sensor Amped
// -----------------------------
//   Sensor + / rojo     -> 5V
//   Sensor - / negro    -> GND
//   Sensor S / señal    -> A0
//
// Conexiones motores (cada uno con transistor BC548 o similar)
// -------------------------------------------------------------
//   Motor 0 (L1) -> D3  PWM
//   Motor 1 (R1) -> D5  PWM
//   Motor 2 (L2) -> D6  PWM
//   Motor 3 (R2) -> D9  PWM
//   Motor 4 (L3) -> D10 PWM
//   Motor 5 (R3) -> D11 PWM
//
// Protocolo serial backend -> Arduino
// ------------------------------------
//   PING
//   PATTERN,<policy_code>,<repeat_count>,<cooldown_ms>,<step_count>
//   STEP,<duration_ms>,<pwm0>,<pwm1>,<pwm2>,<pwm3>,<pwm4>,<pwm5>,<transition_code>
//   ... (step_count líneas STEP)
//   END
//   STOP
//
// policy_code (solo informativo, para logs/ACK): 1=reassure 2=awareness
//   3=breath 4=calm_down
// transition_code: 0=instant 1=ramp_up 2=hold 3=ramp_down 4=pause
// pwmN: intensidad final 0..255 YA calculada por el backend (incluye
//   calibración por motor + intensidad global). El sketch no reescala nada.
//
// Protocolo serial Arduino -> backend
// -------------------------------------
//   EVT,...   eventos (boot, pattern_done, etc.)
//   TEL,...   telemetría periódica parseable
//   ACK,...   confirmaciones
//   ERR,...   errores de protocolo
//
// =====================================================

// -----------------------------
// Configuración Pulse Sensor Amped
// -----------------------------
const int PULSE_PIN = A0;
const int LED = LED_BUILTIN;

const unsigned long PULSE_SAMPLE_PERIOD_MS = 10UL; // 100 Hz
unsigned long lastPulseSampleMs = 0;

const unsigned long SIGNAL_WINDOW_MS = 3000UL;
const int MIN_VALID_AMPLITUDE = 18;

int rawSignal = 0;
float smoothSignal = 0;
bool firstSignalSample = true;

int windowMin = 1023;
int windowMax = 0;
int signalAmplitude = 0;

float thresholdHigh = 0;
float thresholdLow = 0;
unsigned long signalWindowStartMs = 0;

bool signalOK = false;
bool aboveThreshold = false;

// -----------------------------
// Cálculo de BPM
// -----------------------------
const byte RATE_SIZE = 8;
byte rates[RATE_SIZE];
byte rateSpot = 0;
byte rateCount = 0;

unsigned long lastBeat = 0;
float beatsPerMinute = 0;
int beatAvg = 0;

const int MIN_VALID_BPM = 40;
const int MAX_VALID_BPM = 180;
const unsigned long MIN_VALID_IBI_MS = 60000UL / MAX_VALID_BPM;
const unsigned long MAX_VALID_IBI_MS = 60000UL / MIN_VALID_BPM;

// -----------------------------
// Línea base (baseline)
// -----------------------------
// Duración de medición de línea base. Bajar a 30UL*1000UL para pruebas rápidas.
const unsigned long BASELINE_DURATION_MS = 3UL * 60UL * 1000UL;
const unsigned long BASELINE_SAMPLE_PERIOD_MS = 1000UL;
const int MAX_BASELINE_SAMPLES = 320;
byte baselineSamples[MAX_BASELINE_SAMPLES];
int baselineCount = 0;

unsigned long baselineStartMs = 0;
unsigned long lastBaselineSampleMs = 0;
bool baselineStarted = false;
bool baselineReady = false;
int baselineBpm = 0;

// -----------------------------
// BPM suavizado (para que el backend calcule el delta)
// -----------------------------
const byte SMOOTH_WINDOW_SECONDS = 15;
byte smoothSamples[SMOOTH_WINDOW_SECONDS];
byte smoothIndex = 0;
byte smoothCount = 0;
unsigned long lastSmoothSampleMs = 0;
int smoothBpm = 0;

// -----------------------------
// Telemetría
// -----------------------------
const unsigned long TELEMETRY_PERIOD_MS = 1000UL;
unsigned long lastTelemetryMs = 0;

// =====================================================
// CONFIGURACIÓN HÁPTICA
// =====================================================
const byte MOTOR_COUNT = 6;
const byte MOTOR_PINS[MOTOR_COUNT] = {3, 5, 6, 9, 10, 11};
const byte MAX_PATTERN_STEPS = 8;

const byte TRANSITION_INSTANT   = 0;
const byte TRANSITION_RAMP_UP   = 1;
const byte TRANSITION_HOLD      = 2;
const byte TRANSITION_RAMP_DOWN = 3;
const byte TRANSITION_PAUSE     = 4;

struct HapticStep {
  unsigned int durationMs;
  byte pwm[MOTOR_COUNT]; // pwm final ya calculado por el backend, por motor
  byte transition;
};

struct HapticPattern {
  byte policyCode;
  byte repeatCount;
  unsigned int cooldownMs;
  byte stepCount;
  HapticStep steps[MAX_PATTERN_STEPS];
};

HapticPattern incomingPattern;
HapticPattern activePattern;

bool receivingPattern = false;
byte expectedStepCount = 0;
byte incomingStepCount = 0;

bool patternLoaded = false;
bool playbackActive = false;
bool playbackInCooldown = false;
byte playbackStepIndex = 0;
byte playbackRepeatIndex = 0;
unsigned long playbackStepStartMs = 0;
unsigned long playbackCooldownStartMs = 0;

// pwm de arranque de cada canal al comenzar el step actual (para ramps)
byte stepStartPwm[MOTOR_COUNT];

const byte SERIAL_BUFFER_SIZE = 110;
char serialBuffer[SERIAL_BUFFER_SIZE];
byte serialBufferIndex = 0;

// =====================================================
// SETUP
// =====================================================
void setup() {
  Serial.begin(115200);
  pinMode(LED, OUTPUT);

  for (byte i = 0; i < MOTOR_COUNT; i++) {
    pinMode(MOTOR_PINS[i], OUTPUT);
    analogWrite(MOTOR_PINS[i], 0);
  }

  Serial.println(F("EVT,boot,device=pulso_haptico_firmware"));
  Serial.println(F("EVT,info,pulse_sensor=A0,motors=3|5|6|9|10|11,baud=115200"));
  Serial.println(F("EVT,info,place_finger_for_baseline"));

  resetRateBuffer();
}

// =====================================================
// LOOP PRINCIPAL
// =====================================================
void loop() {
  updateHeartRate();
  handleSerialInput();
  updateHapticPlayback();

  if (!baselineReady) {
    collectBaseline();
  } else {
    updateSmoothedBpm();
  }

  printAppTelemetry(false);
}

// =====================================================
// LECTURA / CÁLCULO DE BPM (Pulse Sensor Amped)
// =====================================================
void updateHeartRate() {
  unsigned long now = millis();
  if (now - lastPulseSampleMs < PULSE_SAMPLE_PERIOD_MS) {
    return;
  }
  lastPulseSampleMs = now;

  rawSignal = analogRead(PULSE_PIN);

  if (firstSignalSample) {
    smoothSignal = rawSignal;
    resetSignalWindow(rawSignal);
    firstSignalSample = false;
  }

  smoothSignal = 0.70 * smoothSignal + 0.30 * rawSignal;
  updateSignalWindow(rawSignal);

  if (now - signalWindowStartMs >= SIGNAL_WINDOW_MS) {
    signalAmplitude = windowMax - windowMin;

    if (signalAmplitude >= MIN_VALID_AMPLITUDE) {
      thresholdHigh = windowMin + signalAmplitude * 0.60;
      thresholdLow  = windowMin + signalAmplitude * 0.40;
      signalOK = true;
    } else {
      signalOK = false;
    }

    resetSignalWindow(rawSignal);
  }

  if (!signalOK) {
    return;
  }

  detectBeatFromAnalogSignal(now);
}

void detectBeatFromAnalogSignal(unsigned long now) {
  if (!aboveThreshold && smoothSignal >= thresholdHigh) {
    aboveThreshold = true;

    unsigned long ibi = now - lastBeat;
    if (lastBeat != 0 && ibi >= MIN_VALID_IBI_MS && ibi <= MAX_VALID_IBI_MS) {
      lastBeat = now;
      beatsPerMinute = 60000.0 / (float)ibi;

      int bpmInt = (int)round(beatsPerMinute);
      if (bpmInt >= MIN_VALID_BPM && bpmInt <= MAX_VALID_BPM) {
        rates[rateSpot++] = (byte)bpmInt;
        rateSpot %= RATE_SIZE;
        if (rateCount < RATE_SIZE) rateCount++;

        int total = 0;
        for (byte i = 0; i < rateCount; i++) total += rates[i];
        beatAvg = total / rateCount;

        digitalWrite(LED, HIGH);
      }
    } else {
      lastBeat = now;
    }
  } else if (aboveThreshold && smoothSignal <= thresholdLow) {
    aboveThreshold = false;
    digitalWrite(LED, LOW);
  }
}

void resetSignalWindow(int seedValue) {
  windowMin = seedValue;
  windowMax = seedValue;
  signalWindowStartMs = millis();
}

void updateSignalWindow(int value) {
  if (value < windowMin) windowMin = value;
  if (value > windowMax) windowMax = value;
}

void resetRateBuffer() {
  for (byte i = 0; i < RATE_SIZE; i++) rates[i] = 0;
  rateSpot = 0;
  rateCount = 0;
}

// =====================================================
// LÍNEA BASE
// =====================================================
void collectBaseline() {
  if (!signalOK || beatAvg <= 0) return;

  unsigned long now = millis();

  if (!baselineStarted) {
    baselineStarted = true;
    baselineStartMs = now;
    lastBaselineSampleMs = now;
    baselineCount = 0;
  }

  if (now - lastBaselineSampleMs >= BASELINE_SAMPLE_PERIOD_MS) {
    lastBaselineSampleMs = now;
    if (baselineCount < MAX_BASELINE_SAMPLES) {
      baselineSamples[baselineCount++] = (byte)constrain(beatAvg, 0, 255);
    }
  }

  if (now - baselineStartMs >= BASELINE_DURATION_MS && baselineCount > 0) {
    baselineBpm = medianOfByteArray(baselineSamples, baselineCount);
    baselineReady = true;
    Serial.print(F("EVT,baseline_ready,baseline_bpm="));
    Serial.println(baselineBpm);
  }
}

int medianOfByteArray(byte *values, int count) {
  byte sorted[MAX_BASELINE_SAMPLES];
  for (int i = 0; i < count; i++) sorted[i] = values[i];

  for (int i = 1; i < count; i++) {
    byte key = sorted[i];
    int j = i - 1;
    while (j >= 0 && sorted[j] > key) {
      sorted[j + 1] = sorted[j];
      j--;
    }
    sorted[j + 1] = key;
  }

  if (count % 2 == 1) return sorted[count / 2];
  return (sorted[count / 2 - 1] + sorted[count / 2]) / 2;
}

// =====================================================
// BPM SUAVIZADO (para que el backend calcule delta)
// =====================================================
void updateSmoothedBpm() {
  if (!signalOK || beatAvg <= 0) return;

  unsigned long now = millis();
  if (now - lastSmoothSampleMs < BASELINE_SAMPLE_PERIOD_MS) return;
  lastSmoothSampleMs = now;

  smoothSamples[smoothIndex] = (byte)constrain(beatAvg, 0, 255);
  smoothIndex = (smoothIndex + 1) % SMOOTH_WINDOW_SECONDS;
  if (smoothCount < SMOOTH_WINDOW_SECONDS) smoothCount++;

  smoothBpm = medianOfByteArray(smoothSamples, smoothCount);
}

// =====================================================
// TELEMETRÍA
// =====================================================
void printAppTelemetry(bool force) {
  unsigned long now = millis();
  if (!force && (now - lastTelemetryMs < TELEMETRY_PERIOD_MS)) return;
  lastTelemetryMs = now;

  Serial.print(F("TEL,phase="));
  if (!baselineReady) {
    Serial.print(F("baseline"));
    Serial.print(F(",signal_ok=")); Serial.print(signalOK ? 1 : 0);
    Serial.print(F(",bpm=")); Serial.print((int)round(beatsPerMinute));
    Serial.print(F(",beat_avg=")); Serial.print(beatAvg);
    Serial.print(F(",baseline_samples=")); Serial.print(baselineCount);
    Serial.print(F(",elapsed_s="));
    Serial.println(baselineStarted ? (now - baselineStartMs) / 1000UL : 0);
  } else {
    Serial.print(F("run"));
    Serial.print(F(",signal_ok=")); Serial.print(signalOK ? 1 : 0);
    Serial.print(F(",bpm=")); Serial.print((int)round(beatsPerMinute));
    Serial.print(F(",beat_avg=")); Serial.print(beatAvg);
    Serial.print(F(",smooth_bpm=")); Serial.print(smoothBpm);
    Serial.print(F(",baseline_bpm=")); Serial.print(baselineBpm);
    Serial.print(F(",playback=")); Serial.print(playbackActive ? 1 : 0);
    Serial.print(F(",active_policy_code=")); Serial.println(patternLoaded ? activePattern.policyCode : 0);
  }
}

// =====================================================
// RECEPCIÓN SERIAL DE COMANDOS (backend -> Arduino)
// =====================================================
void handleSerialInput() {
  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '\r') continue;

    if (c == '\n') {
      serialBuffer[serialBufferIndex] = '\0';
      if (serialBufferIndex > 0) {
        processSerialLine(serialBuffer);
      }
      serialBufferIndex = 0;
      continue;
    }

    if (serialBufferIndex < SERIAL_BUFFER_SIZE - 1) {
      serialBuffer[serialBufferIndex++] = c;
    } else {
      // Línea demasiado larga: se descarta y se resetea el buffer.
      serialBufferIndex = 0;
      Serial.println(F("ERR,line_too_long"));
    }
  }
}

void processSerialLine(char *line) {
  if (strcmp(line, "PING") == 0) {
    Serial.println(F("ACK,PONG"));
    return;
  }

  if (strcmp(line, "STOP") == 0) {
    stopPlayback();
    Serial.println(F("ACK,STOPPED"));
    return;
  }

  if (strncmp(line, "PATTERN,", 8) == 0) {
    parsePatternHeader(line + 8);
    return;
  }

  if (strncmp(line, "STEP,", 5) == 0) {
    parseStepLine(line + 5);
    return;
  }

  if (strcmp(line, "END") == 0) {
    finalizeIncomingPattern();
    return;
  }

  Serial.print(F("ERR,unknown_command,"));
  Serial.println(line);
}

// PATTERN,<policy_code>,<repeat_count>,<cooldown_ms>,<step_count>
void parsePatternHeader(char *args) {
  int policyCode = 0, repeatCount = 1, cooldownMs = 0, stepCount = 0;

  char *token = strtok(args, ",");
  int fieldIndex = 0;
  while (token != NULL) {
    long value = atol(token);
    switch (fieldIndex) {
      case 0: policyCode = (int)value; break;
      case 1: repeatCount = (int)value; break;
      case 2: cooldownMs = (int)value; break;
      case 3: stepCount = (int)value; break;
    }
    fieldIndex++;
    token = strtok(NULL, ",");
  }

  if (fieldIndex < 4 || stepCount < 1 || stepCount > MAX_PATTERN_STEPS) {
    Serial.println(F("ERR,bad_pattern_header"));
    receivingPattern = false;
    return;
  }

  incomingPattern.policyCode = (byte)policyCode;
  incomingPattern.repeatCount = (byte)constrain(repeatCount, 1, 8);
  incomingPattern.cooldownMs = (unsigned int)constrain(cooldownMs, 0, 10000);
  incomingPattern.stepCount = (byte)stepCount;

  expectedStepCount = (byte)stepCount;
  incomingStepCount = 0;
  receivingPattern = true;

  Serial.println(F("ACK,PATTERN_HEADER_OK"));
}

// STEP,<duration_ms>,<pwm0>,<pwm1>,<pwm2>,<pwm3>,<pwm4>,<pwm5>,<transition_code>
void parseStepLine(char *args) {
  if (!receivingPattern || incomingStepCount >= MAX_PATTERN_STEPS) {
    Serial.println(F("ERR,step_without_pattern"));
    return;
  }

  long values[8];
  int fieldIndex = 0;

  char *token = strtok(args, ",");
  while (token != NULL && fieldIndex < 8) {
    values[fieldIndex++] = atol(token);
    token = strtok(NULL, ",");
  }

  if (fieldIndex != 8) {
    Serial.println(F("ERR,bad_step_line"));
    return;
  }

  HapticStep *step = &incomingPattern.steps[incomingStepCount];
  step->durationMs = (unsigned int)constrain(values[0], 1, 60000);
  for (byte i = 0; i < MOTOR_COUNT; i++) {
    step->pwm[i] = (byte)constrain(values[1 + i], 0, 255);
  }
  step->transition = (byte)constrain(values[7], 0, 4);

  incomingStepCount++;
}

void finalizeIncomingPattern() {
  if (!receivingPattern || incomingStepCount != expectedStepCount) {
    Serial.println(F("ERR,incomplete_pattern"));
    receivingPattern = false;
    return;
  }

  activePattern = incomingPattern;
  patternLoaded = true;
  receivingPattern = false;

  startPlayback();

  Serial.print(F("ACK,PATTERN_LOADED,policy_code="));
  Serial.println(activePattern.policyCode);
}

// =====================================================
// REPRODUCCIÓN HÁPTICA
// =====================================================
void startPlayback() {
  playbackActive = true;
  playbackInCooldown = false;
  playbackStepIndex = 0;
  playbackRepeatIndex = 0;
  playbackStepStartMs = millis();

  for (byte i = 0; i < MOTOR_COUNT; i++) stepStartPwm[i] = 0;

  Serial.println(F("EVT,pattern_start"));
}

void stopPlayback() {
  playbackActive = false;
  playbackInCooldown = false;
  patternLoaded = false;
  for (byte i = 0; i < MOTOR_COUNT; i++) {
    analogWrite(MOTOR_PINS[i], 0);
  }
}

void updateHapticPlayback() {
  if (!playbackActive || !patternLoaded) return;

  unsigned long now = millis();

  if (playbackInCooldown) {
    if (now - playbackCooldownStartMs >= activePattern.cooldownMs) {
      playbackInCooldown = false;
      playbackStepIndex = 0;
      playbackStepStartMs = now;
      for (byte i = 0; i < MOTOR_COUNT; i++) stepStartPwm[i] = 0;
    } else {
      return;
    }
  }

  HapticStep *step = &activePattern.steps[playbackStepIndex];
  unsigned long elapsed = now - playbackStepStartMs;
  float progress = (float)elapsed / (float)step->durationMs;
  if (progress > 1.0) progress = 1.0;

  for (byte i = 0; i < MOTOR_COUNT; i++) {
    byte output = computeChannelOutput(step, i, progress);
    analogWrite(MOTOR_PINS[i], output);
  }

  if (elapsed >= step->durationMs) {
    playbackStepIndex++;

    if (playbackStepIndex >= activePattern.stepCount) {
      playbackRepeatIndex++;

      if (playbackRepeatIndex >= activePattern.repeatCount) {
        stopPlayback();
        Serial.println(F("EVT,pattern_done"));
        return;
      }

      playbackInCooldown = true;
      playbackCooldownStartMs = now;
      for (byte i = 0; i < MOTOR_COUNT; i++) analogWrite(MOTOR_PINS[i], 0);
      return;
    }

    playbackStepStartMs = now;
    for (byte i = 0; i < MOTOR_COUNT; i++) {
      stepStartPwm[i] = computeChannelOutput(step, i, 1.0);
    }
  }
}

byte computeChannelOutput(HapticStep *step, byte channel, float progress) {
  byte target = step->pwm[channel];

  switch (step->transition) {
    case TRANSITION_RAMP_UP:
      return (byte)(stepStartPwm[channel] + (target - (int)stepStartPwm[channel]) * progress);
    case TRANSITION_RAMP_DOWN:
      return (byte)(stepStartPwm[channel] * (1.0 - progress));
    case TRANSITION_PAUSE:
      return 0;
    case TRANSITION_HOLD:
    case TRANSITION_INSTANT:
    default:
      return target;
  }
}
