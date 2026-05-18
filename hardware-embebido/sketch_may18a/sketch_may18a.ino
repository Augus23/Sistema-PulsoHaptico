// Código básico para encender y apagar un motor usando el pin D11
// Compatible con Arduino

const int motorPin1 = 11;
const int motorPin2 = 10;

void setup() {
    pinMode(motorPin1, OUTPUT);
    pinMode(motorPin2, OUTPUT);
    Serial.begin(115200);
}

void loop() {
    Serial.print("prendiendo");
    digitalWrite(motorPin2, HIGH);  // Enciende el motor2
    digitalWrite(motorPin1, HIGH); // Enciende el motor1
    delay(3000);                  // Espera 3 segundos
    Serial.print("apagando");
    digitalWrite(motorPin2, LOW);  // Apaga el motor2
    digitalWrite(motorPin1, LOW);  // Apaga el motor1
    delay(3000);                  // Espera 3 segundos
}