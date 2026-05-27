// =====================================================
// Stress Detector Amped + Reproductor de patrones hápticos
// Proyecto IDI-2026 / Pulso háptico
// =====================================================
//
// Qué hace este sketch
// --------------------
// 1) Lee un Pulse Sensor Amped conectado al pin A0.
// 2) Calcula BPM, línea base y nivel relativo de activación.
// 3) Envía telemetría por USB/Serial a una aplicación en PC.
// 4) Recibe desde la PC un patrón háptico compacto, derivado de un JSON.
// 5) Ejecuta ese patrón en 6 motores vibradores conectados a pines PWM.
//
// Por qué NO recibe JSON completo
// -------------------------------
// Arduino Nano tiene poca RAM. La PC conserva el JSON como formato de catálogo,
// pero lo traduce a un protocolo serial compacto, línea por línea.
//
// Conexiones Pulse Sensor Amped
// -----------------------------
//   Sensor + / rojo     -> 5V
//   Sensor - / negro    -> GND
//   Sensor S / señal    -> A0
//
// Conexiones motores por transistor BC548 o similar
// -------------------------------------------------
//   Motor 0 -> D3  PWM
//   Motor 1 -> D5  PWM
//   Motor 2 -> D6  PWM
//   Motor 3 -> D9  PWM
//   Motor 4 -> D10 PWM
//   Motor 5 -> D11 PWM
//
// Cada motor debe estar manejado por transistor, no directamente desde el pin.
// Pin PWM -> resistencia de base -> BC548. Emisor a GND. Colector al negativo
// del motor. Positivo del motor a fuente. GND de fuente y Arduino en común.
//
// Protocolo serial PC -> Arduino
// ------------------------------
// La PC envía:
//   PING
//   PATTERN,<policy_code>,<custom>,<repeat_count>,<cooldown_ms>,<step_count>
//   STEP,<duration_ms>,<mask>,<pwm>,<transition_code>
//   STEP,...
//   END
//
// policy_code:
//   1 = reassure, 2 = awareness, 3 = breath, 4 = calm_down
// custom:
//   0 = patrón base, 1 = patrón con personalización aplicada en la PC
// mask:
//   máscara binaria de 6 bits. bit 0 = motor 0, bit 5 = motor 5.
// pwm:
//   intensidad final ya escalada, entre 0 y 255.
// transition_code:
//   0 = instant, 1 = ramp_up, 2 = hold, 3 = ramp_down, 4 = pause
//
// Protocolo serial Arduino -> PC
// ------------------------------
//   EVT,...  eventos
//   TEL,...  telemetría periódica parseable por la app
//   ACK,...  confirmaciones
//   ERR,...  errores de protocolo
//
// Uso recomendado
// ---------------
// 1) Cargar este sketch en Arduino Nano.
// 2) Cerrar el Serial Monitor del IDE.
// 3) Ejecutar la app Python en la PC con el puerto correcto.
//
// =====================================================


// -----------------------------
// Configuración Pulse Sensor Amped
// -----------------------------

const int PULSE_PIN = A0;
const int LED = LED_BUILTIN;

// Muestreo de señal analógica
const unsigned long PULSE_SAMPLE_PERIOD_MS = 10UL;   // 100 Hz
unsigned long lastPulseSampleMs = 0;

// Ventana para estimar amplitud y umbrales dinámicos
const unsigned long SIGNAL_WINDOW_MS = 3000UL;

// Amplitud mínima cruda para considerar señal confiable.
// Si es muy bajo, el sensor está mal apoyado o no hay pulso usable.
const int MIN_VALID_AMPLITUDE = 18;

// Señal cruda y filtrada
int rawSignal = 0;
float smoothSignal = 0;
bool firstSignalSample = true;

// Mínimo/máximo en ventana
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

const byte RATE_SIZE = 8;   // Promedio corto de BPM. 4 responde más rápido; 8 es más estable.
byte rates[RATE_SIZE];
byte rateSpot = 0;
byte rateCount = 0;

unsigned long lastBeat = 0;

float beatsPerMinute = 0;
int beatAvg = 0;

// Rango fisiológico aceptado para descartar falsos positivos.
const int MIN_VALID_BPM = 40;
const int MAX_VALID_BPM = 180;

// Derivados para evitar doble conteo de picos.
const unsigned long MIN_VALID_IBI_MS = 60000UL / MAX_VALID_BPM;
const unsigned long MAX_VALID_IBI_MS = 60000UL / MIN_VALID_BPM;


// -----------------------------
// Línea base
// -----------------------------

// Cambiar a 5UL para medir 5 minutos.
// Para pruebas rápidas podés bajar temporalmente a 30UL * 1000UL.
const unsigned long BASELINE_DURATION_MS = 3UL * 60UL * 1000UL;

const unsigned long BASELINE_SAMPLE_PERIOD_MS = 1000UL;

// 5 minutos a 1 muestra por segundo = 300 muestras.
// Dejamos margen.
const int MAX_BASELINE_SAMPLES = 320;
byte baselineSamples[MAX_BASELINE_SAMPLES];
int baselineCount = 0;

unsigned long baselineStartMs = 0;
unsigned long lastBaselineSampleMs = 0;

bool baselineStarted = false;
bool baselineReady = false;

int baselineBpm = 0;


// -----------------------------
// Suavizado para clasificación
// -----------------------------

// Ventana temporal de suavizado.
// Puede probarse entre 10 y 20 segundos.
const byte SMOOTH_WINDOW_SECONDS = 15;

byte smoothSamples[SMOOTH_WINDOW_SECONDS];
byte smoothIndex = 0;
byte smoothCount = 0;

unsigned long lastSmoothSampleMs = 0;
int smoothBpm = 0;


// -----------------------------
// Clasificación de estado
// -----------------------------

enum StressLevel {
  LEVEL_NO_SIGNAL,
  LEVEL_REASSURE,
  LEVEL_AWARENESS,
  LEVEL_BREATH,
  LEVEL_CALM_DOWN
};

StressLevel currentLevel = LEVEL_NO_SIGNAL;
StressLevel lastEventLevel = LEVEL_NO_SIGNAL;


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

// Códigos de transición recibidos desde la app Python.
const byte TRANSITION_INSTANT   = 0;
const byte TRANSITION_RAMP_UP   = 1;
const byte TRANSITION_HOLD      = 2;
const byte TRANSITION_RAMP_DOWN = 3;
const byte TRANSITION_PAUSE     = 4;

struct HapticStep {
  unsigned int durationMs;   // duración del paso
  byte mask;                 // bits de motores activos
  byte pwm;                  // intensidad 0..255 ya escalada por la PC
  byte transition;           // código de transición
};

struct HapticPattern {
  byte policyCode;
  bool customized;
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

// Buffer de recepción serial. Cada línea del protocolo es corta.
const byte SERIAL_BUFFER_SIZE = 96;
char serialBuffer[SERIAL_BUFFER_SIZE];
byte serialBufferIndex = 0;


// =====================================================
// SETUP
// =====================================================

void setup()
{
  Serial.begin(115200);

  pinMode(LED, OUTPUT);

  for (byte i = 0; i < MOTOR_COUNT; i++)
  {
    pinMode(MOTOR_PINS[i], OUTPUT);
    analogWrite(MOTOR_PINS[i], 0);
  }

  Serial.println(F("EVT,boot,device=stress_detector_amped_haptic_mvp"));
  Serial.println(F("EVT,info,pulse_sensor=A0,motors=3|5|6|9|10|11,baud=115200"));
  Serial.println(F("EVT,info,place_finger_for_baseline"));

  resetRateBuffer();
}


// =====================================================
// LOOP PRINCIPAL
// =====================================================

void loop()
{
  // Mantener estas funciones no bloqueantes permite medir pulso,
  // recibir comandos y ejecutar vibraciones al mismo tiempo.
  updateHeartRate();
  handleSerialInput();
  updateHapticPlayback();

  if (!baselineReady)
  {
    collectBaseline();
  }
  else
  {
    updateSmoothedBpm();
    currentLevel = classifyStressLevel();

    // Evento inmediato cuando cambia el nivel/política.
    if (currentLevel != lastEventLevel)
    {
      lastEventLevel = currentLevel;
      printPolicyChangeEvent();
      printAppTelemetry(true);
    }
  }

  // Telemetría periódica para la app.
  printAppTelemetry(false);
}


// =====================================================
// ACTUALIZACIÓN DE BPM DESDE PULSE SENSOR AMPED
// =====================================================

void updateHeartRate()
{
  unsigned long now = millis();

  if (now - lastPulseSampleMs < PULSE_SAMPLE_PERIOD_MS)
  {
    return;
  }

  lastPulseSampleMs = now;

  rawSignal = analogRead(PULSE_PIN);

  if (firstSignalSample)
  {
    smoothSignal = rawSignal;
    resetSignalWindow(rawSignal);
    firstSignalSample = false;
  }

  // Filtro exponencial simple.
  // Suficiente para reducir ruido sin borrar demasiado el pulso.
  smoothSignal = 0.70 * smoothSignal + 0.30 * rawSignal;

  updateSignalWindow(rawSignal);

  // Cada SIGNAL_WINDOW_MS recalculamos amplitud y umbrales.
  if (now - signalWindowStartMs >= SIGNAL_WINDOW_MS)
  {
    signalAmplitude = windowMax - windowMin;

    if (signalAmplitude >= MIN_VALID_AMPLITUDE)
    {
      thresholdHigh = windowMin + signalAmplitude * 0.60;
      thresholdLow  = windowMin + signalAmplitude * 0.40;
      signalOK = true;
    }
    else
    {
      signalOK = false;
      aboveThreshold = false;
      digitalWrite(LED, LOW);

      // Si no hay señal usable, evitamos seguir arrastrando BPM viejo.
      resetRateBuffer();
    }

    resetSignalWindow(rawSignal);
  }

  // Si todavía no tenemos señal confiable, no detectamos latidos.
  if (!signalOK)
  {
    return;
  }

  detectBeatFromAnalogSignal(now);
}


void updateSignalWindow(int value)
{
  if (value < windowMin) windowMin = value;
  if (value > windowMax) windowMax = value;
}

// resetea la ventana al valor por parametro y guarda cuando la actualizó
void resetSignalWindow(int value)
{
  windowMin = value;
  windowMax = value;
  signalWindowStartMs = millis();
}


void detectBeatFromAnalogSignal(unsigned long now)
{
  // Cruce ascendente del umbral alto.
  // La histéresis se completa esperando luego que baje de thresholdLow.
  if (!aboveThreshold && smoothSignal > thresholdHigh)
  {
    aboveThreshold = true;

    if (lastBeat == 0)
    {
      lastBeat = now;
      return;
    }

    unsigned long ibi = now - lastBeat;

    // Evita doble conteo de picos demasiado cercanos.
    if (ibi < MIN_VALID_IBI_MS)
    {
      return;
    }

    // Si pasó demasiado tiempo, reiniciamos referencia pero no calculamos BPM.
    if (ibi > MAX_VALID_IBI_MS)
    {
      lastBeat = now;
      return;
    }

    beatsPerMinute = 60000.0 / ibi;

    if (beatsPerMinute >= MIN_VALID_BPM && beatsPerMinute <= MAX_VALID_BPM)
    {
      addRateSample((byte)beatsPerMinute);
      beatAvg = averageRates();

      digitalWrite(LED, HIGH);
      lastBeat = now;
    }
  }

  // Cruce descendente del umbral bajo.
  // Recién ahí habilitamos detectar un nuevo latido.
  if (aboveThreshold && smoothSignal < thresholdLow)
  {
    aboveThreshold = false;
    digitalWrite(LED, LOW);
  }
}


void addRateSample(byte bpm)
{
  rates[rateSpot] = bpm;
  rateSpot = (rateSpot + 1) % RATE_SIZE;

  if (rateCount < RATE_SIZE)
  {
    rateCount++;
  }
}


int averageRates()
{
  if (rateCount == 0) return 0;

  int sum = 0;

  for (byte i = 0; i < rateCount; i++)
  {
    sum += rates[i];
  }

  return sum / rateCount;
}


void resetRateBuffer()
{
  rateSpot = 0;
  rateCount = 0;
  lastBeat = 0;
  beatsPerMinute = 0;
  beatAvg = 0;

  for (byte i = 0; i < RATE_SIZE; i++)
  {
    rates[i] = 0;
  }
}


// =====================================================
// MEDICIÓN DE LÍNEA BASE
// =====================================================

void collectBaseline()
{
  unsigned long now = millis();

  bool fingerPresent = signalOK;
  bool bpmAvailable = beatAvg > 0;

  if (!baselineStarted && fingerPresent && bpmAvailable)
  {
    baselineStarted = true;
    baselineStartMs = now;
    lastBaselineSampleMs = now;

    Serial.println(F("EVT,baseline_started"));
  }

  if (!baselineStarted)
  {
    return;
  }

  // Guardamos una muestra por segundo del BPM promedio corto.
  if (fingerPresent && bpmAvailable && now - lastBaselineSampleMs >= BASELINE_SAMPLE_PERIOD_MS)
  {
    lastBaselineSampleMs = now;

    if (baselineCount < MAX_BASELINE_SAMPLES)
    {
      baselineSamples[baselineCount] = (byte)beatAvg;
      baselineCount++;
    }
  }

  bool timeCompleted = (now - baselineStartMs >= BASELINE_DURATION_MS);
  bool enoughSamples = (baselineCount >= 60); // mínimo razonable

  if ((timeCompleted && enoughSamples) || baselineCount >= MAX_BASELINE_SAMPLES)
  {
    baselineBpm = medianBaseline();
    baselineReady = true;

    Serial.print(F("EVT,baseline_ready,baseline_bpm="));
    Serial.println(baselineBpm);

    // Limpiamos buffers de suavizado para empezar la fase de detección.
    smoothIndex = 0;
    smoothCount = 0;
    smoothBpm = 0;
    lastSmoothSampleMs = millis();
  }
}


// Calcula la mediana de la línea base.
// Ordena el arreglo baselineSamples en el lugar.
// No importa perder el orden original porque ya no lo necesitamos.
int medianBaseline()
{
  sortByteArray(baselineSamples, baselineCount);

  if (baselineCount == 0) return 0;

  if (baselineCount % 2 == 1)
  {
    return baselineSamples[baselineCount / 2];
  }
  else
  {
    int a = baselineSamples[(baselineCount / 2) - 1];
    int b = baselineSamples[baselineCount / 2];
    return (a + b) / 2;
  }
}


// =====================================================
// BPM SUAVIZADO PARA CLASIFICACIÓN
// =====================================================

void updateSmoothedBpm()
{
  unsigned long now = millis();

  bool fingerPresent = signalOK;
  bool bpmAvailable = beatAvg > 0;

  if (!fingerPresent || !bpmAvailable)
  {
    return;
  }

  // Tomamos una muestra por segundo de beatAvg.
  if (now - lastSmoothSampleMs >= 1000UL)
  {
    lastSmoothSampleMs = now;

    smoothSamples[smoothIndex] = (byte)beatAvg;
    smoothIndex = (smoothIndex + 1) % SMOOTH_WINDOW_SECONDS;

    if (smoothCount < SMOOTH_WINDOW_SECONDS)
    {
      smoothCount++;
    }

    smoothBpm = medianSmooth();
  }
}


int medianSmooth()
{
  if (smoothCount == 0) return 0;

  byte temp[SMOOTH_WINDOW_SECONDS];

  for (byte i = 0; i < smoothCount; i++)
  {
    temp[i] = smoothSamples[i];
  }

  sortByteArray(temp, smoothCount);

  if (smoothCount % 2 == 1)
  {
    return temp[smoothCount / 2];
  }
  else
  {
    int a = temp[(smoothCount / 2) - 1];
    int b = temp[smoothCount / 2];
    return (a + b) / 2;
  }
}


// =====================================================
// CLASIFICACIÓN POR BPM RELATIVO
// =====================================================

StressLevel classifyStressLevel()
{
  if (!signalOK)
  {
    return LEVEL_NO_SIGNAL;
  }

  // Hasta que no haya al menos algunos segundos de ventana,
  // evitamos clasificar agresivamente.
  if (smoothCount < 5 || smoothBpm == 0 || baselineBpm == 0)
  {
    return LEVEL_NO_SIGNAL;
  }

  int delta = smoothBpm - baselineBpm;

  if (delta >= 33)
  {
    return LEVEL_CALM_DOWN;
  }
  else if (delta >= 19)
  {
    return LEVEL_BREATH;
  }
  else if (delta >= 9)
  {
    return LEVEL_AWARENESS;
  }
  else
  {
    // Incluye baseline - 5 a baseline + 8,
    // y también valores más bajos que la línea base.
    // Para el proyecto, eso no requiere intervención fuerte.
    return LEVEL_REASSURE;
  }
}


const char* policyName(StressLevel level)
{
  switch (level)
  {
    case LEVEL_REASSURE:
      return "reassure";

    case LEVEL_AWARENESS:
      return "awareness";

    case LEVEL_BREATH:
      return "breath";

    case LEVEL_CALM_DOWN:
      return "calm_down";

    default:
      return "no_signal";
  }
}


byte policyCode(StressLevel level)
{
  switch (level)
  {
    case LEVEL_REASSURE:
      return 1;
    case LEVEL_AWARENESS:
      return 2;
    case LEVEL_BREATH:
      return 3;
    case LEVEL_CALM_DOWN:
      return 4;
    default:
      return 0;
  }
}


const char* levelName(StressLevel level)
{
  switch (level)
  {
    case LEVEL_REASSURE:
      return "regulacion_estable";

    case LEVEL_AWARENESS:
      return "activacion_leve";

    case LEVEL_BREATH:
      return "activacion_moderada";

    case LEVEL_CALM_DOWN:
      return "activacion_alta";

    default:
      return "sin_senal";
  }
}


// =====================================================
// UTILIDAD: ORDENAMIENTO SIMPLE
// =====================================================

void sortByteArray(byte arr[], int n)
{
  for (int i = 1; i < n; i++)
  {
    byte key = arr[i];
    int j = i - 1;

    while (j >= 0 && arr[j] > key)
    {
      arr[j + 1] = arr[j];
      j--;
    }

    arr[j + 1] = key;
  }
}


// =====================================================
// TELEMETRÍA SERIAL PARA LA APP
// =====================================================

void printAppTelemetry(bool force)
{
  unsigned long now = millis();

  if (!force && now - lastTelemetryMs < TELEMETRY_PERIOD_MS)
  {
    return;
  }

  lastTelemetryMs = now;

  if (!baselineReady)
  {
    Serial.print(F("TEL,phase=baseline"));
    Serial.print(F(",raw="));
    Serial.print(rawSignal);
    Serial.print(F(",smooth_signal="));
    Serial.print(smoothSignal, 1);
    Serial.print(F(",amp="));
    Serial.print(signalAmplitude);
    Serial.print(F(",signal_ok="));
    Serial.print(signalOK ? 1 : 0);
    Serial.print(F(",bpm="));
    Serial.print(beatsPerMinute, 1);
    Serial.print(F(",beat_avg="));
    Serial.print(beatAvg);
    Serial.print(F(",baseline_samples="));
    Serial.print(baselineCount);

    if (baselineStarted)
    {
      Serial.print(F(",elapsed_s="));
      Serial.print((now - baselineStartMs) / 1000);
    }
    else
    {
      Serial.print(F(",waiting_for_valid_signal=1"));
    }

    Serial.println();
  }
  else
  {
    int delta = smoothBpm - baselineBpm;

    Serial.print(F("TEL,phase=run"));
    Serial.print(F(",raw="));
    Serial.print(rawSignal);
    Serial.print(F(",smooth_signal="));
    Serial.print(smoothSignal, 1);
    Serial.print(F(",amp="));
    Serial.print(signalAmplitude);
    Serial.print(F(",signal_ok="));
    Serial.print(signalOK ? 1 : 0);
    Serial.print(F(",bpm="));
    Serial.print(beatsPerMinute, 1);
    Serial.print(F(",beat_avg="));
    Serial.print(beatAvg);
    Serial.print(F(",smooth_bpm="));
    Serial.print(smoothBpm);
    Serial.print(F(",baseline_bpm="));
    Serial.print(baselineBpm);
    Serial.print(F(",delta="));
    Serial.print(delta);
    Serial.print(F(",level="));
    Serial.print(levelName(currentLevel));
    Serial.print(F(",policy="));
    Serial.print(policyName(currentLevel));
    Serial.print(F(",policy_code="));
    Serial.print(policyCode(currentLevel));
    Serial.print(F(",playback="));
    Serial.print(playbackActive ? 1 : 0);
    Serial.println();
  }
}


void printPolicyChangeEvent()
{
  Serial.print(F("EVT,policy_change,level="));
  Serial.print(levelName(currentLevel));
  Serial.print(F(",policy="));
  Serial.print(policyName(currentLevel));
  Serial.print(F(",policy_code="));
  Serial.println(policyCode(currentLevel));
}


// =====================================================
// RECEPCIÓN SERIAL DE PATRONES
// =====================================================

void handleSerialInput()
{
  while (Serial.available() > 0)
  {
    char c = (char)Serial.read();

    if (c == '\r')
    {
      continue;
    }

    if (c == '\n')
    {
      serialBuffer[serialBufferIndex] = '\0';

      if (serialBufferIndex > 0)
      {
        parseSerialLine(serialBuffer);
      }

      serialBufferIndex = 0;
    }
    else
    {
      if (serialBufferIndex < SERIAL_BUFFER_SIZE - 1)
      {
        serialBuffer[serialBufferIndex] = c;
        serialBufferIndex++;
      }
      else
      {
        // Línea demasiado larga: descartamos para no desbordar memoria.
        serialBufferIndex = 0;
        Serial.println(F("ERR,line_too_long"));
      }
    }
  }
}


void parseSerialLine(char* line)
{
  if (strcmp(line, "PING") == 0)
  {
    Serial.println(F("ACK,PONG"));
    return;
  }

  if (strcmp(line, "STOP") == 0)
  {
    stopHapticPlayback(true);
    Serial.println(F("ACK,STOPPED"));
    return;
  }

  if (startsWith(line, "PATTERN,"))
  {
    parsePatternHeader(line);
    return;
  }

  if (startsWith(line, "STEP,"))
  {
    parsePatternStep(line);
    return;
  }

  if (strcmp(line, "END") == 0)
  {
    finishIncomingPattern();
    return;
  }

  Serial.print(F("ERR,unknown_command,line="));
  Serial.println(line);
}


bool startsWith(const char* text, const char* prefix)
{
  while (*prefix)
  {
    if (*text != *prefix)
    {
      return false;
    }
    text++;
    prefix++;
  }
  return true;
}


void parsePatternHeader(char* line)
{
  // Formato: PATTERN,<policy_code>,<custom>,<repeat_count>,<cooldown_ms>,<step_count>
  char* token = strtok(line, ","); // PATTERN
  token = strtok(NULL, ",");
  if (token == NULL) { Serial.println(F("ERR,bad_pattern_header")); return; }
  byte pCode = constrain(atoi(token), 1, 4);

  token = strtok(NULL, ",");
  if (token == NULL) { Serial.println(F("ERR,bad_pattern_header")); return; }
  bool custom = atoi(token) != 0;

  token = strtok(NULL, ",");
  if (token == NULL) { Serial.println(F("ERR,bad_pattern_header")); return; }
  byte repeats = constrain(atoi(token), 1, 8);

  token = strtok(NULL, ",");
  if (token == NULL) { Serial.println(F("ERR,bad_pattern_header")); return; }
  unsigned int cooldown = constrain(atoi(token), 0, 10000);

  token = strtok(NULL, ",");
  if (token == NULL) { Serial.println(F("ERR,bad_pattern_header")); return; }
  byte steps = constrain(atoi(token), 1, MAX_PATTERN_STEPS);

  incomingPattern.policyCode = pCode;
  incomingPattern.customized = custom;
  incomingPattern.repeatCount = repeats;
  incomingPattern.cooldownMs = cooldown;
  incomingPattern.stepCount = steps;

  expectedStepCount = steps;
  incomingStepCount = 0;
  receivingPattern = true;

  Serial.print(F("ACK,PATTERN_HEADER,policy_code="));
  Serial.print(pCode);
  Serial.print(F(",custom="));
  Serial.print(custom ? 1 : 0);
  Serial.print(F(",steps="));
  Serial.println(steps);
}


void parsePatternStep(char* line)
{
  // Formato: STEP,<duration_ms>,<mask>,<pwm>,<transition_code>
  if (!receivingPattern)
  {
    Serial.println(F("ERR,step_without_pattern"));
    return;
  }

  if (incomingStepCount >= expectedStepCount || incomingStepCount >= MAX_PATTERN_STEPS)
  {
    Serial.println(F("ERR,too_many_steps"));
    return;
  }

  char* token = strtok(line, ","); // STEP
  token = strtok(NULL, ",");
  if (token == NULL) { Serial.println(F("ERR,bad_step")); return; }
  unsigned int duration = constrain(atoi(token), 1, 10000);

  token = strtok(NULL, ",");
  if (token == NULL) { Serial.println(F("ERR,bad_step")); return; }
  byte mask = constrain(atoi(token), 0, 63);

  token = strtok(NULL, ",");
  if (token == NULL) { Serial.println(F("ERR,bad_step")); return; }
  byte pwm = constrain(atoi(token), 0, 255);

  token = strtok(NULL, ",");
  if (token == NULL) { Serial.println(F("ERR,bad_step")); return; }
  byte transition = constrain(atoi(token), 0, 4);

  incomingPattern.steps[incomingStepCount].durationMs = duration;
  incomingPattern.steps[incomingStepCount].mask = mask;
  incomingPattern.steps[incomingStepCount].pwm = pwm;
  incomingPattern.steps[incomingStepCount].transition = transition;

  incomingStepCount++;

  Serial.print(F("ACK,STEP,"));
  Serial.println(incomingStepCount);
}


void finishIncomingPattern()
{
  if (!receivingPattern)
  {
    Serial.println(F("ERR,end_without_pattern"));
    return;
  }

  if (incomingStepCount != expectedStepCount)
  {
    Serial.print(F("ERR,step_count_mismatch,expected="));
    Serial.print(expectedStepCount);
    Serial.print(F(",received="));
    Serial.println(incomingStepCount);
    receivingPattern = false;
    return;
  }

  activePattern = incomingPattern;
  patternLoaded = true;
  receivingPattern = false;

  startHapticPlayback();

  Serial.print(F("ACK,PATTERN_LOADED,policy_code="));
  Serial.print(activePattern.policyCode);
  Serial.print(F(",custom="));
  Serial.print(activePattern.customized ? 1 : 0);
  Serial.print(F(",steps="));
  Serial.print(activePattern.stepCount);
  Serial.print(F(",repeat_count="));
  Serial.println(activePattern.repeatCount);
}


// =====================================================
// REPRODUCCIÓN HÁPTICA NO BLOQUEANTE
// =====================================================

void startHapticPlayback()
{
  if (!patternLoaded || activePattern.stepCount == 0)
  {
    Serial.println(F("ERR,no_pattern_to_play"));
    return;
  }

  playbackActive = true;
  playbackInCooldown = false;
  playbackStepIndex = 0;
  playbackRepeatIndex = 0;
  playbackStepStartMs = millis();

  Serial.print(F("EVT,playback_started,policy_code="));
  Serial.print(activePattern.policyCode);
  Serial.print(F(",custom="));
  Serial.println(activePattern.customized ? 1 : 0);
}


void stopHapticPlayback(bool manualStop)
{
  stopAllMotors();
  playbackActive = false;
  playbackInCooldown = false;
  playbackStepIndex = 0;
  playbackRepeatIndex = 0;

  if (manualStop)
  {
    Serial.println(F("EVT,playback_stopped_manual"));
  }
}


// ejecuta los pasos del patron que recibe el arduino
void updateHapticPlayback()
{
  if (!playbackActive)
  {
    return;
  }

  unsigned long now = millis();

  if (playbackInCooldown)
  {
    if (now - playbackCooldownStartMs >= activePattern.cooldownMs)
    {
      playbackInCooldown = false;
      playbackStepIndex = 0;
      playbackStepStartMs = now;
    }
    else
    {
      return;
    }
  }

  if (playbackStepIndex >= activePattern.stepCount)
  {
    playbackRepeatIndex++;

    if (playbackRepeatIndex >= activePattern.repeatCount)
    {
      stopAllMotors();
      playbackActive = false;
      Serial.println(F("EVT,playback_finished"));
      return;
    }

    stopAllMotors();
    playbackInCooldown = true;
    playbackCooldownStartMs = now;
    return;
  }

  HapticStep step = activePattern.steps[playbackStepIndex];
  unsigned long elapsed = now - playbackStepStartMs;

  if (elapsed >= step.durationMs)
  {
    playbackStepIndex++;
    playbackStepStartMs = now;
    return;
  }

  byte currentPwm = computeStepPwm(step, elapsed);
  applyMotorMask(step.mask, currentPwm);
}


byte computeStepPwm(HapticStep step, unsigned long elapsed)
{
  if (step.transition == TRANSITION_PAUSE || step.pwm == 0 || step.mask == 0)
  {
    return 0;
  }

  if (step.durationMs == 0)
  {
    return step.pwm;
  }

  if (step.transition == TRANSITION_RAMP_UP)
  {
    unsigned long value = ((unsigned long)step.pwm * elapsed) / step.durationMs;
    if (value > step.pwm) value = step.pwm;
    return (byte)value;
  }

  if (step.transition == TRANSITION_RAMP_DOWN)
  {
    unsigned long value = ((unsigned long)step.pwm * elapsed) / step.durationMs;
    if (value > step.pwm) value = step.pwm;
    return (byte)(step.pwm - value);
  }

  // TRANSITION_INSTANT y TRANSITION_HOLD se tratan igual en la reproducción.
  return step.pwm;
}


void applyMotorMask(byte mask, byte pwm)
{
  for (byte i = 0; i < MOTOR_COUNT; i++)
  {
    bool active = (mask & (1 << i)) != 0;
    analogWrite(MOTOR_PINS[i], active ? pwm : 0);
  }
}


void stopAllMotors()
{
  for (byte i = 0; i < MOTOR_COUNT; i++)
  {
    analogWrite(MOTOR_PINS[i], 0);
  }
}
