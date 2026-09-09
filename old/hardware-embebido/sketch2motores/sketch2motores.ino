const int motorPin1 = 11;
const int buttonPin = 12;
const int motorPin2 = 10;

bool motorActivo = false;
bool ultimoEstadoBoton = HIGH;


void setup() {
  pinMode(motorPin1, OUTPUT);
  pinMode(motorPin2, OUTPUT);
  pinMode(buttonPin, INPUT_PULLUP); // botón a GND

  digitalWrite(motorPin1, LOW);
  digitalWrite(motorPin2, LOW);
}

void loop() {
  bool estadoBoton = digitalRead(buttonPin);

  // detectar pulsación (flanco)
  if (ultimoEstadoBoton == HIGH && estadoBoton == LOW) {
    motorActivo = !motorActivo; // cambia estado

    delay(50); // anti-rebote básico
  }

  ultimoEstadoBoton = estadoBoton;

  if (motorActivo) {
    analogWrite(motorPin1, 20); // intensidad de vibración (0–255)
    analogWrite(motorPin2, 70);
  } else {
    analogWrite(motorPin1, 0);
    analogWrite(motorPin2, 0);
  }

}