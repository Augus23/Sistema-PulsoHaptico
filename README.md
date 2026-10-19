# Compañero Háptico

Proyecto LIFIA 2026: sistema de acompañamiento háptico con Arduino Nano, sensor de pulso, motores de vibración y aplicación de escritorio.


## Estructura del proyecto

```text
.
├── app/
│   ├── arduino/
│   │   └── stressDetectorAmpedHapticMVP/
│   │       └── stressDetectorAmpedHapticMVP.ino
│   ├── patterns/                       # Catálogo de patrones JSON
│   ├── src/
│   │   ├── static/                     # Recursos visuales de la interfaz
│   │   ├── config.py                   # Estructuras de datos
│   │   ├── constants.py                # Políticas, códigos y parámetros
│   │   ├── hardware.py                 # Comunicación serial y simulador
│   │   ├── protocol.py                 # Catálogo y tramas del protocolo
│   │   └── ui.py                       # Interfaz y secuencia automática
│   ├── tests/                          # Pruebas de la aplicación Python
│   ├── demo.py                         # Entrada de la demo gráfica
│   ├── pc_haptic_app.py                # Aplicación Python alternativa
│   ├── pc_haptic_app_manual_policy.py  # Variante de selección manual
│   └── requirements.txt                # Dependencias Python
├── docs/
│   └── especificacion_pruebas_politicas_hapticas.docx
├── hardware_tests/                     # Pruebas de hardware Arduino
│   └── test_motores/
│       └── test_motores.ino
├── legacy/                             # Código y documentación históricos
└── README.md
```

## Requisitos

- Python 3.8 o superior.
- Entorno gráfico de escritorio para ejecutar la interfaz Tkinter/CustomTkinter.

## Preparación

Desde la raíz del repositorio, crea y activa un entorno virtual dentro de `app/`, e instala sus dependencias:

```powershell
cd app
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

En Linux o macOS, activa el entorno con:

```bash
source .venv/bin/activate
```

## Ejecución prevista

Desde `app/`, la demo gráfica puede ejecutarse sin hardware con el simulador serial:

```bash
python demo.py --mock --catalog patterns
```

Para conectarse a un Arduino, cierra antes el Monitor Serial del IDE y especifica el puerto:

```powershell
python demo.py --port COM5 --catalog patterns
```

En Linux, el puerto puede tener un nombre como `/dev/ttyUSB0`:

```bash
python demo.py --port /dev/ttyUSB0 --catalog patterns
```

La opción `--baud` permite cambiar la velocidad serial; el valor predeterminado es `115200`. Si se omite `--port`, la aplicación intenta ofrecer una selección interactiva de los puertos disponibles.

## Funcionamiento

1. `demo.py` carga los patrones JSON de `patterns/` y configura el simulador o el puerto serial.
2. `protocol.py` convierte el patrón seleccionado en comandos compactos `PATTERN`, `STEP` y `END`. El JSON permanece en la PC; el Arduino no necesita interpretarlo.
3. `hardware.py` gestiona la comunicación en un hilo independiente. Recibe telemetría `TEL`, confirmaciones `ACK`, eventos `EVT` y errores `ERR`, y transmite los comandos del patrón.
4. `ui.py` presenta la telemetría y permite seleccionar políticas manualmente o activar una secuencia automática. El modo mock permite probar la interfaz sin Arduino.
5. El sketch en `app/arduino/stressDetectorAmpedHapticMVP/` lee el sensor en A0, calcula BPM y línea base, envía telemetría y controla seis motores PWM.

El protocolo PC → Arduino usa una cabecera `PATTERN`, una línea `STEP` por paso y `END` para finalizar la carga. Arduino responde mediante líneas seriales de telemetría, eventos, confirmaciones o errores.

## Hardware

El Pulse Sensor Amped se conecta con `+` a `5V`, `-` a `GND` y señal a `A0`. Los seis motores usan los pines PWM D3, D5, D6, D9, D10 y D11, respectivamente. Cada motor debe controlarse mediante un transistor; no debe conectarse directamente a un pin del Arduino. La fuente de los motores y el Arduino deben compartir GND.

## Código histórico y pruebas

`hardware_tests/` contiene sketches para probar componentes físicos. `legacy/` conserva versiones y notas anteriores, no es la ruta de ejecución principal. Las pruebas de Python de la aplicación están en `app/tests/`.
