// =====================================================
// SIMULACIÓN DE PULSO + CONTROL DE MOTOR
// =====================================================

const int[] motors = {A0, A1, A2, A3, A6, A7}; // A4 y A5 reservados para sensor
const int motorsNumber = 1;

// -----------------------------
// SIMULADOR DE PULSO
// -----------------------------
float simulatedBPM = 75.0;
unsigned long lastSimulatedBeat = 0;

// -----------------------------
// BPM Y PROMEDIO
// -----------------------------
const byte RATE_SIZE = 8;
byte rates[RATE_SIZE];
byte rateSpot = 0;
byte rateCount = 0;

long lastBeat = 0;

float beatsPerMinute = 0;
int beatAvg = 0;

long irValue = 0;

const long FINGER_THRESHOLD = 50000;

const int MIN_VALID_BPM = 40;
const int MAX_VALID_BPM = 180;

// -----------------------------
// LÍNEA BASE
// -----------------------------
const unsigned long BASELINE_DURATION_MS = 1UL * 60UL * 1000UL;
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
// SUAVIZADO
// -----------------------------
const byte SMOOTH_WINDOW_SECONDS = 15;

byte smoothSamples[SMOOTH_WINDOW_SECONDS];
byte smoothIndex = 0;
byte smoothCount = 0;

unsigned long lastSmoothSampleMs = 0;
int smoothBpm = 0;

// -----------------------------
// CLASIFICACIÓN
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
// TELEMETRÍA
// -----------------------------
const unsigned long TELEMETRY_PERIOD_MS = 1000UL;
unsigned long lastTelemetryMs = 0;

// =====================================================
// SETUP
// =====================================================
void setup()
{
  Serial.begin(115200);
  Serial.println("Simulador de pulso iniciado");

  for(int i = 0; i<motorsNumber; i++){
    pinMode(motors[i], OUTPUT);
  }

  randomSeed(analogRead(0));
}

// =====================================================
// LOOP
// =====================================================
void loop()
{
  updateHeartRate();

  simulateDynamicBPM();

  if (!baselineReady)
  {
    collectBaseline();
  }
  else
  {
    updateSmoothedBpm();
    currentLevel = classifyStressLevel();
    runPattern(currentLevel);
  }

  printTelemetry();
}

// =====================================================
// SIMULACIÓN DINÁMICA
// =====================================================
void simulateDynamicBPM()
{
  static unsigned long lastChange = 0;

  if (millis() - lastChange > 10000)
  {
    lastChange = millis();

    int mode = random(0, 4);

    switch (mode)
    {
      case 0: simulatedBPM = 70; break;
      case 1: simulatedBPM = 85; break;
      case 2: simulatedBPM = 100; break;
      case 3: simulatedBPM = 120; break;
    }

    Serial.print("Simulated BPM changed to: ");
    Serial.println(simulatedBPM);
  }
}

// =====================================================
// GENERADOR DE LATIDOS
// =====================================================
void updateHeartRate()
{
  unsigned long now = millis();

  irValue = FINGER_THRESHOLD + 10000;

  unsigned long interval = (unsigned long)(60000.0 / simulatedBPM);

  if (now - lastSimulatedBeat >= interval)
  {
    lastSimulatedBeat = now;

    float noise = random(-3, 4);
    beatsPerMinute = simulatedBPM + noise;

    if (beatsPerMinute >= MIN_VALID_BPM && beatsPerMinute <= MAX_VALID_BPM)
    {
      addRateSample((byte)beatsPerMinute);
      beatAvg = averageRates();
    }
  }
}

// =====================================================
// PROMEDIO BPM
// =====================================================
void addRateSample(byte bpm)
{
  rates[rateSpot] = bpm;
  rateSpot = (rateSpot + 1) % RATE_SIZE;

  if (rateCount < RATE_SIZE)
    rateCount++;
}

int averageRates()
{
  if (rateCount == 0) return 0;

  int sum = 0;
  for (byte i = 0; i < rateCount; i++)
    sum += rates[i];

  return sum / rateCount;
}

// =====================================================
// BASELINE
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

  if (!baselineStarted) return;

  if (now - lastBaselineSampleMs >= BASELINE_SAMPLE_PERIOD_MS)
  {
    lastBaselineSampleMs = now;

    if (baselineCount < MAX_BASELINE_SAMPLES)
    {
      baselineSamples[baselineCount] = (byte)beatAvg;
      baselineCount++;
    }
  }

  if ((now - baselineStartMs >= BASELINE_DURATION_MS) && baselineCount >= 60)
  {
    baselineBpm = medianBaseline();
    baselineReady = true;

    Serial.print("baseline_ready: ");
    Serial.println(baselineBpm);
  }
}

int medianBaseline()
{
  sortByteArray(baselineSamples, baselineCount);

  if (baselineCount % 2 == 1)
    return baselineSamples[baselineCount / 2];
  else
    return (baselineSamples[baselineCount / 2 - 1] +
            baselineSamples[baselineCount / 2]) / 2;
}

// =====================================================
// SUAVIZADO
// =====================================================
void updateSmoothedBpm()
{
  if (millis() - lastSmoothSampleMs >= 1000)
  {
    lastSmoothSampleMs = millis();

    smoothSamples[smoothIndex] = (byte)beatAvg;
    smoothIndex = (smoothIndex + 1) % SMOOTH_WINDOW_SECONDS;

    if (smoothCount < SMOOTH_WINDOW_SECONDS)
      smoothCount++;

    smoothBpm = medianSmooth();
  }
}

int medianSmooth()
{
  byte temp[SMOOTH_WINDOW_SECONDS];

  for (byte i = 0; i < smoothCount; i++)
    temp[i] = smoothSamples[i];

  sortByteArray(temp, smoothCount);

  if (smoothCount % 2 == 1)
    return temp[smoothCount / 2];
  else
    return (temp[smoothCount / 2 - 1] +
            temp[smoothCount / 2]) / 2;
}

// =====================================================
// CLASIFICACIÓN
// =====================================================
StressLevel classifyStressLevel()
{
  if (smoothCount < 5) return LEVEL_NO_SIGNAL;

  int delta = smoothBpm - baselineBpm;

  if (delta >= 33) return LEVEL_CALM_DOWN;
  if (delta >= 19) return LEVEL_BREATH;
  if (delta >= 9)  return LEVEL_AWARENESS;

  return LEVEL_REASSURE;
}

// =====================================================
// MOTOR
// =====================================================
void runPattern(StressLevel level)
{
  switch (level)
  {
    case LEVEL_REASSURE:
      
      break;

    case LEVEL_AWARENESS:
      // Prende cada motor un segundo
      Serial.println("Iniciando patron AWARENESS");
      for(int i = 0; i<motorsNumber; i++){
        analogWrite(motors[i], 50);
        delay(1000);
        analogWrite(motors[i], 0);
      }
      break;

    case LEVEL_BREATH:
      // prende todos los motores una vez ascendentemente
      Serial.println("Iniciando patron BREATH");
      for(int i=0; i<motorsNumber; i++){
        for(int j=0; j<255; j++){
          analogWrite(motors[i], j);
          delay(10);
        }
        analogWrite(motors[i], 0);
      }
      break;

    case LEVEL_CALM_DOWN:
      // prende todos los motores un segundo 3 veces
      Serial.println("Iniciando patron CALM DOWN");
      for(int i=0; i<3; i++){
        for(int j = 0; j<motorsNumber; j++){
          analogWrite(motors[j], 50);
          delay(50);
        }
        break;
        delay(1000);
        for(int j = 0; j<motorsNumber; j++){
          analogWrite(motors[j], 0);
        }
      }

    default:
      for(int i=0; i<motorsNumber; i++){
        analogWrite(motors[i], 0);
      }
      break;
  }
}

// =====================================================
// UTILIDAD
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
// SERIAL
// =====================================================
void printTelemetry()
{
  if (millis() - lastTelemetryMs < TELEMETRY_PERIOD_MS)
    return;

  lastTelemetryMs = millis();

  Serial.print("BPM=");
  Serial.print(beatAvg);
  Serial.print(" | Smooth=");
  Serial.print(smoothBpm);
  Serial.print(" | Baseline=");
  Serial.print(baselineBpm);
  Serial.print(" | Level=");
  Serial.println(currentLevel);
}