const int MOTOR = A2;

// PULSE MOCK
float pulse;
float timeStep = 0;
int currentBPM;

// THRESHOLDS AND LEVELS
int activationThresholds[] = {90, 110, 130}; 
int deactivationThresholds[] = {80, 100, 120}; // Histéresis
int state = 0;
String stateMessage[] = {"Normalidad", "Estas bien", "Con Cuidado", "Alerta"};

// INTERVALS OF CAPTURING
unsigned long currentTime = 0;
unsigned long lastTime = 0;
unsigned long interval = 1000;


int getPulseMock(){
 pulse = 80 + (35 * sin(timeStep));
 timeStep += 0.05; 
 return  currentBPM = (int)pulse + random(-2, 2);
}

void startPattern(int state){
  switch(state){
   	case 1:
	  // Patrón constante con vibración baja
      Serial.println("Reproduciendo patron 1");
      for(int i = 0; i < 10; i++){
        analogWrite(MOTOR, 40);
        delay(5);
      }
      break;
    case 2:	
      // Patrón alternado con vibración media
      Serial.println("Reproduciendo patron 2");
      for(int i = 0; i < 10; i++){
      	analogWrite(MOTOR, 80);
        delay(500);
        analogWrite(MOTOR, 0);
        delay(500);
      }
      break;
    case 3:
      // Patrón ascendente y descendente
	  Serial.println("Reproduciendo patron 3");
      for(int i = 0; i < 10; i++){
        for(int j = 0; j<255; j++){
          analogWrite(MOTOR, j);
          delay(10);
        }
        for(int j = 255; j > 0; j--){
          analogWrite(MOTOR, j);
          delay(10);
        }
      }
      break;
    default:
      Serial.println("Motor apagado");
      analogWrite(MOTOR, 0);
      break;
    
  }
}

void setup(){
  Serial.begin(9600);
  pinMode(MOTOR, OUTPUT);
}

void loop(){
  
  currentTime = millis();
  if(currentTime - lastTime >= interval){
    lastTime = currentTime;
      
    currentBPM = getPulseMock();

    Serial.print("PULSO: ");
    Serial.print(currentBPM);
    Serial.println(" BPM");

    
    // CAMBIAR NIVEL
    if(state < 3 && currentBPM > activationThresholds[state]){
      // Si se superó el umbral
      state++;
      Serial.println(stateMessage[state]);
      startPattern(state);
      	
    }
    
    // REDUCIR NIVEL (Histéresis)
    if(state > 0 && currentBPM < deactivationThresholds[state-1]){
      // Si el umbral es menor
      state--;
      Serial.println(stateMessage[state]);
      startPattern(state);
  	}
    
  }
}