# 🚀 Guía de Demostración y Arquitectura del Sistema - Pulso Háptico

Este documento contiene las instrucciones paso a paso para ejecutar el entorno de demostración de la aplicación **Pulso Háptico**, así como la explicación detallada de la arquitectura modular del sistema y su flujo de comunicación interno.

---

## 📋 Requisitos Previos

* **Python 3.8** o superior instalado en el sistema.
* Puerto USB disponible y microcontrolador cargado con el firmware (en caso de realizar pruebas con hardware real).

---

## 🛠️ Instalación y Configuración del Entorno Virtual

Sigue estos pasos desde la terminal en la raíz del proyecto para aislar las dependencias:

### 1. Crear el entorno virtual
* **Linux / macOS:**
  ```bash
  python3 -m venv venv

* **Windows:**
```cmd
python -m venv venv

```



### 2. Activar el entorno virtual

* **Linux / macOS:**
```bash
source venv/bin/activate

```


* **Windows (CMD):**
```cmd
venv\Scripts\activate.bat

```


* **Windows (PowerShell):**
```powershell
venv\Scripts\Activate.ps1

```



### 3. Instalar dependencias

Con el entorno virtual activado, instala las librerías necesarias ejecutando:

```bash
pip install -r requirements.txt

```

---

## 💻 Pasos para Ejecutar la Demostración

### Opción A: Ejecución en MODO MOCK (Sin Hardware)

Ideal para desarrollo, pruebas de la interfaz gráfica o demostraciones donde no se cuenta con el Arduino Nano o el sensor de pulso conectado.

```bash
python main.py --mock --catalog patterns

```

* **¿Qué sucede?** Se inicia un simulador serial interno (`MockArduinoSerial`) que genera valores fluctuantes de BPM y responde a los comandos del protocolo como si fuera la placa física.

---

### Opción B: Ejecución con HARDWARE REAL

Para pruebas con el sensor de pulso y la matriz de motores hápticos conectados por USB.

1. **Conectar el Arduino Nano** a la PC mediante el cable USB.
2. **Ejecutar indicando el puerto serial:**
* **Windows:**
```cmd
python main.py --port COM5 --catalog patterns

```


* **Linux / macOS:**
```bash
python main.py --port /dev/ttyUSB0 --catalog patterns

```




*(Nota: Si no especificas el argumento `--port`, el programa abrirá un menú interactivo en la consola para seleccionar el puerto disponible).*

---

## 🏗️ Arquitectura del Sistema

La aplicación sigue una arquitectura modular desacoplada basada en el patrón **Modelo-Vista-Controlador (MVC)** para permitir el trabajo en paralelo de múltiples desarrolladores.

```text
pulso_haptic_mvp/
│
├── patterns/                   # Archivos JSON del catálogo de políticas
│   ├── reassure_base.json
│   ├── awareness_base.json
│   ├── breath_base.json
│   └── calm_down_base.json
│
├── demo/                        # Módulos del sistema
│   ├── __init__.py
│   ├── config.py               # Constantes y estructuras de datos (Modelos)
│   ├── protocol.py             # Parser de JSON y generador de tramas seriales
│   ├── hardware.py             # Abstracción Serial (Driver USB + Mock Simulator)
│   └── ui.py                   # Frontend (Tkinter) y Orquestador de Tiempos
│
├── main.py                     # Punto de entrada y CLI parser
└── DEMO.md                     # Documentación de demostración

```

### Descripción de Módulos

* **`demo/config.py`**: Almacena las estructuras de datos (`EffectivePattern`), diccionarios globales de mapeo de políticas (`POLICY_TO_CODE`) y códigos de transición háptica.
* **`demo/protocol.py`**: Encargado de cargar los archivos JSON del catálogo, validar sus duraciones/intensidades y compactarlos en comandos de texto ligero (`PATTERN`, `STEP`, `END`) compatibles con la RAM del microcontrolador.
* **`demo/hardware.py`**: Contiene la lógica de comunicación bidireccional mediante `SerialWorkerThread` (hilo desacoplado) y la clase `MockArduinoSerial` para simular lecturas analógicas y comandos `ACK`.
* **`demo/ui.py`**: Alberga la interfaz de usuario `HapticDemoApp` (construida en Tkinter) y el hilo `DemoOrchestrator`, encargado de automatizar la rotación de políticas cada 30 segundos en el modo demo.
* **`demo.py`**: Punto de entrada de la aplicación. Parsea argumentos de consola, instancia los hilos y arranca el ciclo de eventos visuales (`mainloop`).

---

## 🔄 Flujo de Datos y Comunicación entre Módulos

El flujo de información se organiza mediante **mensajería asíncrona no bloqueante** apoyada en hilos (`threads`) y funciones de callback:

```
┌─────────────────┐       (1) Lee JSON       ┌──────────────────┐
│  patterns/*.json│ ───────────────────────► │  demo/protocol.py│
└─────────────────┘                          └─────────┬────────┘
                                                       │ (2) Genera trama compacta
                                                       ▼
┌─────────────────┐       (4) Eventos UI     ┌──────────────────┐
│    demo/ui.py   │ ◄─────────────────────── │ demo/hardware.py │
│  (Tkinter App / │                          │  (Worker/Mock)   │
│  Orchestrator)  │ ───────────────────────► └─────────┬────────┘
└─────────────────┘     (3) Solicitud Política         │
                                                       │ (5) Tx/Rx Protocolo Serial
                                                       ▼
                                             ┌──────────────────┐
                                             │   Arduino Nano   │
                                             └──────────────────┘

```

### Detalle del Flujo de Comunicación:

1. **Carga Inicial:** `main.py` solicita a `demo/protocol.py` cargar el catálogo de archivos JSON desde la carpeta `patterns/`.
2. **Recepción de Telemetría (Hardware/Mock ➔ UI):**
* El hilo `SerialWorkerThread` en `demo/hardware.py` lee continuamente la línea Serial.
* Al recibir una línea de telemetría (`TEL,...`), la parsea y dispara el callback registrado en `demo/ui.py`.
* La interfaz gráfica actualiza las etiquetas de **BPM**, **Smooth BPM** y **Delta** mediante llamadas seguras al hilo principal de Tkinter (`self.after()`).


3. **Envío de Política Háptica (UI ➔ Hardware ➔ Microcontrolador):**
* El usuario pulsa un botón manual en la UI o el `DemoOrchestrator` conmuta de política (cada 30s).
* Se invoca a `demo/protocol.py` para construir un objeto `EffectivePattern` adaptado a esa política.
* `demo/hardware.py` transmite la ráfaga de comandos por serial:
```text
PATTERN,policy_code,custom,repeat_count,cooldown_ms,step_count
STEP,duration_ms,mask,pwm,transition_code
...
END

```


4. **Respuesta y Confirmación (Hardware ➔ UI):**
* El Arduino (o el simulador Mock) responde con tramas de confirmación (`ACK,PATTERN_LOADED` o `EVT,playback_started`).
* `demo/hardware.py` redirige estos mensajes a la consola visual de logs dentro del frontend.

