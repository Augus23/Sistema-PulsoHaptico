/*
  Test de 6 motores ERM con Arduino Nano
  Controlados por transistor BC548 / 2N2222 / similar

  Conexiones:
  Motor 0 -> D3  PWM
  Motor 1 -> D5  PWM
  Motor 2 -> D6  PWM
  Motor 3 -> D9  PWM
  Motor 4 -> D10 PWM
  Motor 5 -> D11 PWM

  Circuito típico con BC548:
  - Pin PWM Arduino -> resistencia 1k -> base del transistor
  - Emisor -> GND
  - Colector -> negativo del motor
  - Positivo del motor -> +V motores, por ejemplo 3V o 5V
  - GND fuente motores unido a GND Arduino
  - Diodo flyback en paralelo con el motor:
      cátodo a +V motor
      ánodo al lado del transistor / negativo del motor
*/

const int motorPins[] = {3, 5, 6, 9, 10, 11};
const int motorCount = 6;

// Ajustes generales
const int intensidadTest = 200;   // 0-255. Bajarlo si vibra demasiado fuerte.
const int intensidadMax  = 255;
const int duracionPulso  = 300;   // ms
const int pausaEntre     = 400;   // ms

void setup() {
  Serial.begin(9600);

  for (int i = 0; i < motorCount; i++) {
    pinMode(motorPins[i], OUTPUT);
    analogWrite(motorPins[i], 0);
  }

  Serial.println("Test de motores iniciado");
  Serial.println("Motores en pines: D3, D5, D6, D9, D10, D11");
}

void loop() {
  testUnoPorUno();
  delay(1000);

  testRampaUnoPorUno();
  delay(1000);

  testTodosJuntos();
  delay(2000);
}

void testUnoPorUno() {
  Serial.println("Test 1: pulsos individuales");

  for (int i = 0; i < motorCount; i++) {
    Serial.print("Motor ");
    Serial.print(i);
    Serial.print(" en pin D");
    Serial.println(motorPins[i]);

    analogWrite(motorPins[i], intensidadTest);
    delay(duracionPulso);

    analogWrite(motorPins[i], 0);
    delay(pausaEntre);
  }
}

void testRampaUnoPorUno() {
  Serial.println("Test 2: rampa suave individual");

  for (int i = 0; i < motorCount; i++) {
    Serial.print("Rampa motor ");
    Serial.println(i);

    // Sube intensidad
    for (int val = 0; val <= intensidadMax; val += 5) {
      analogWrite(motorPins[i], val);
      delay(10);
    }

    delay(200);

    // Baja intensidad
    for (int val = intensidadMax; val >= 0; val -= 5) {
      analogWrite(motorPins[i], val);
      delay(10);
    }

    analogWrite(motorPins[i], 0);
    delay(pausaEntre);
  }
}

void testTodosJuntos() {
  Serial.println("Test 3: todos juntos");

  for (int i = 0; i < motorCount; i++) {
    analogWrite(motorPins[i], intensidadTest);
  }

  delay(500);

  for (int i = 0; i < motorCount; i++) {
    analogWrite(motorPins[i], 0);
  }

  delay(500);

  // Tres impulsos cortos
  for (int pulso = 0; pulso < 3; pulso++) {
    for (int i = 0; i < motorCount; i++) {
      analogWrite(motorPins[i], intensidadMax);
    }

    delay(120);

    for (int i = 0; i < motorCount; i++) {
      analogWrite(motorPins[i], 0);
    }

    delay(180);
  }
}