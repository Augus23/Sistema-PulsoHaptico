#include <Wire.h>
#include "MAX30105.h"
#include "heartRate.h"

MAX30105 particleSensor;

// -----------------------------
// Configuración general
// -----------------------------

const byte RATE_SIZE = 8;   // Promedio corto de BPM. 4 responde más rápido; 8 es más estable.
byte rates[RATE_SIZE];
byte rateSpot = 0;
byte rateCount = 0;

long lastBeat = 0;

float beatsPerMinute = 0;
int beatAvg = 0;

long irValue = 0;

// Umbral tentativo para detectar dedo presente.
// Hay que ajustarlo mirando valores IR sin dedo y con dedo.
const long FINGER_THRESHOLD = 50000;

// Rango fisiológico aceptado para descartar falsos positivos.
const int MIN_VALID_BPM = 40;
const int MAX_VALID_BPM = 180;

// -----------------------------
// Línea base
// -----------------------------

// Cambiar a 5UL para medir 5 minutos.
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

// -----------------------------
// Telemetría
// -----------------------------

const unsigned long TELEMETRY_PERIOD_MS = 1000UL;
unsigned long lastTelemetryMs = 0;


// =====================================================
// SETUP
// =====================================================

void setup()
{
  Serial.begin(115200);
  Serial.println("Inicializando MAX30102...");

  if (!particleSensor.begin(Wire, I2C_SPEED_FAST))
  {
    Serial.println("MAX30102/MAX30105 no encontrado. Revisar conexiones.");
    while (1);
  }

  Serial.println("Sensor encontrado.");
  Serial.println("Colocar el dedo con presion estable.");
  Serial.println("Primero se medira linea base en reposo.");

  // Configuración explícita del sensor.
  // Más claro que usar particleSensor.setup() sin parámetros.
  byte ledBrightness = 0x1F;  // Intensidad LED. Subir si la señal es débil.
  byte sampleAverage = 4;     // Promedio interno. Subir a 8 si hay mucho ruido.
  byte ledMode = 2;           // Red + IR. Adecuado para MAX30102.
  int sampleRate = 100;       // 100 muestras/s.
  int pulseWidth = 411;       // Mayor resolución.
  int adcRange = 4096;        // Subir a 8192 si hay saturación.

  particleSensor.setup(
    ledBrightness,
    sampleAverage,
    ledMode,
    sampleRate,
    pulseWidth,
    adcRange
  );

  // Para este algoritmo usamos principalmente IR.
  particleSensor.setPulseAmplitudeRed(0x0A);
  particleSensor.setPulseAmplitudeIR(0x1F);
  particleSensor.setPulseAmplitudeGreen(0);
}


// =====================================================
// LOOP PRINCIPAL
// =====================================================

void loop()
{
  updateHeartRate();

  if (!baselineReady)
  {
    collectBaseline();
  }
  else
  {
    updateSmoothedBpm();
    currentLevel = classifyStressLevel();
  }

  printTelemetry();
}


// =====================================================
// ACTUALIZACIÓN DE BPM DESDE IR
// =====================================================

void updateHeartRate()
{
  irValue = particleSensor.getIR();

  // Si no hay dedo, no intentamos actualizar BPM.
  if (irValue < FINGER_THRESHOLD)
  {
    return;
  }

  if (checkForBeat(irValue) == true)
  {
    unsigned long now = millis();

    // Evita usar el primer latido, porque no hay latido anterior.
    if (lastBeat > 0)
    {
      unsigned long delta = now - lastBeat;

      beatsPerMinute = 60.0 / (delta / 1000.0);

      if (beatsPerMinute >= MIN_VALID_BPM && beatsPerMinute <= MAX_VALID_BPM)
      {
        addRateSample((byte)beatsPerMinute);
        beatAvg = averageRates();
      }
    }

    lastBeat = now;
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


// =====================================================
// MEDICIÓN DE LÍNEA BASE
// =====================================================

void collectBaseline()
{
  unsigned long now = millis();

  bool fingerPresent = irValue >= FINGER_THRESHOLD;
  bool bpmAvailable = beatAvg > 0;

  if (!baselineStarted && fingerPresent && bpmAvailable)
  {
    baselineStarted = true;
    baselineStartMs = now;
    lastBaselineSampleMs = now;

    Serial.println("baseline_started");
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

    Serial.print("baseline_ready, baseline_bpm=");
    Serial.println(baselineBpm);

    // Limpiamos buffers de suavizado para empezar la fase de detección.
    smoothIndex = 0;
    smoothCount = 0;
    smoothBpm = 0;
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

  bool fingerPresent = irValue >= FINGER_THRESHOLD;
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
  if (irValue < FINGER_THRESHOLD)
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
// TELEMETRÍA SERIAL
// =====================================================

void printTelemetry()
{
  unsigned long now = millis();

  if (now - lastTelemetryMs < TELEMETRY_PERIOD_MS)
  {
    return;
  }

  lastTelemetryMs = now;

  if (!baselineReady)
  {
    Serial.print("phase=baseline");
    Serial.print(", ir=");
    Serial.print(irValue);
    Serial.print(", bpm=");
    Serial.print(beatsPerMinute);
    Serial.print(", beat_avg=");
    Serial.print(beatAvg);
    Serial.print(", samples=");
    Serial.print(baselineCount);

    if (baselineStarted)
    {
      Serial.print(", elapsed_s=");
      Serial.print((now - baselineStartMs) / 1000);
    }
    else
    {
      Serial.print(", waiting_for_valid_signal");
    }

    if (irValue < FINGER_THRESHOLD)
    {
      Serial.print(", no_finger");
    }

    Serial.println();
  }
  else
  {
    int delta = smoothBpm - baselineBpm;

    Serial.print("phase=run");
    Serial.print(", ir=");
    Serial.print(irValue);
    Serial.print(", bpm=");
    Serial.print(beatsPerMinute);
    Serial.print(", beat_avg=");
    Serial.print(beatAvg);
    Serial.print(", smooth_bpm=");
    Serial.print(smoothBpm);
    Serial.print(", baseline_bpm=");
    Serial.print(baselineBpm);
    Serial.print(", delta=");
    Serial.print(delta);
    Serial.print(", level=");
    Serial.print(levelName(currentLevel));
    Serial.print(", policy=");
    Serial.print(policyName(currentLevel));

    if (irValue < FINGER_THRESHOLD)
    {
      Serial.print(", no_finger");
    }

    Serial.println();
  }
}