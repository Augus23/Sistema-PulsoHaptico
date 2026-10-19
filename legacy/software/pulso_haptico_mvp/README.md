# Pulso háptico MVP — PC + Arduino Nano

Esta carpeta contiene una maqueta funcional de línea de comandos para conectar el circuito Arduino con una app de PC.

## Archivos

- `stressDetectorAmpedHapticMVP.ino`: sketch Arduino Nano. Conserva la lógica de sensor, BPM, línea base y clasificación; agrega telemetría serial, recepción de patrones y control no bloqueante de 6 motores PWM.
- `pc_haptic_app.py`: aplicación CLI en Python. Abre el puerto, recibe BPM, decide política, lee el patrón JSON, aplica personalización y manda un protocolo compacto al Nano.
- `patterns/`: catálogo inicial de 4 políticas en JSON.
- `requirements.txt`: dependencia Python mínima.

## Conexiones esperadas

### Pulse Sensor Amped

- `+` / rojo -> `5V`
- `-` / negro -> `GND`
- `S` / señal -> `A0`

### Motores vibrotáctiles

Cada motor debe conectarse vía transistor, no directamente al pin Arduino.

- Motor 0 -> D3
- Motor 1 -> D5
- Motor 2 -> D6
- Motor 3 -> D9
- Motor 4 -> D10
- Motor 5 -> D11

## Instalación Python

```bash
pip install -r requirements.txt
```

## Uso básico

1. Cargar `stressDetectorAmpedHapticMVP.ino` en Arduino Nano.
2. Cerrar el Monitor Serial del IDE Arduino.
3. Ejecutar la app:

```bash
python pc_haptic_app.py --port COM9 --catalog patterns
```

En Linux puede ser:

```bash
python pc_haptic_app.py --port /dev/ttyUSB0 --catalog patterns
```

Si no se indica `--port`, la app lista los puertos disponibles.

## Personalización desde CLI

```bash
python pc_haptic_app.py --port COM9 --catalog patterns   --intensity-scale awareness=1.15   --duration-scale breath=1.25   --repeat-count calm_down=3
```

La app indica si envía patrón `BASE` o `PERSONALIZADA`.

## Prueba sin Arduino

```bash
python pc_haptic_app.py --catalog patterns --dry-run
```

Esto muestra cómo se traducen los JSON a comandos compactos.

## Protocolo serial resumido

PC -> Arduino:

```text
PATTERN,<policy_code>,<custom>,<repeat_count>,<cooldown_ms>,<step_count>
STEP,<duration_ms>,<mask>,<pwm>,<transition_code>
...
END
```

Arduino -> PC:

```text
TEL,phase=run,bpm=...,smooth_bpm=...,baseline_bpm=...,delta=...,policy=...
EVT,policy_change,...
ACK,PATTERN_LOADED,...
ERR,...
```

## Nota de diseño

El JSON se conserva como formato expresivo de catálogo en la PC. El Nano sólo recibe una versión compacta porque tiene poca RAM y no conviene cargar un parser JSON en esta etapa.
