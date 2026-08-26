# Pulso Háptico — Backend + Firmware (Etapa 1)

Esta entrega cubre **firmware Arduino** + **backend Django**, tal como se
acordó: primero la base de datos/lógica/hardware, y en un próximo paso la
app mobile (React Native + Expo) que va a consumir esta misma API.

## Arquitectura

```
[ Pulse Sensor Amped ] --A0--> [ Arduino ] <--USB serial--> [ Django, misma PC ] <--WiFi/HTTP--> [ App mobile ]
```

- **Arduino** (`arduino/haptic_firmware/haptic_firmware.ino`): SOLO mide BPM
  (bpm, bpm suavizado, línea base) y ejecuta los patrones de vibración que
  recibe por serial. **No decide** qué política aplicar.
- **Django** (`backend/`): lee esa telemetría, decide automáticamente qué
  política corresponde según el BPM (o la que el usuario elija a mano),
  calcula la intensidad final de cada uno de los 6 motores (patrón base +
  calibración por motor + intensidad global) y se la manda al Arduino.
  Expone todo por una API REST que va a consumir la app mobile.
- **App mobile** (próxima etapa): pantalla principal con las 4 políticas +
  slider de intensidad global, y una pantalla por política con un slider
  por motor (L1/R1/L2/R2/L3/R3), igual que el mockup.

## 1) Cargar el firmware en el Arduino

1. Abrir `arduino/haptic_firmware/haptic_firmware.ino` en el IDE de Arduino.
2. Conectar el Pulse Sensor Amped a A0 (ver comentarios del sketch) y los 6
   motores (con transistor) a los pines 3, 5, 6, 9, 10, 11.
3. Subir el sketch. **Cerrar el Serial Monitor del IDE** antes de correr
   Django (el puerto serial no puede estar abierto en dos programas a la vez).

## 2) Levantar el backend Django

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

python3 manage.py migrate
python3 manage.py runserver 0.0.0.0:8000
```

`0.0.0.0:8000` (en vez de `127.0.0.1`) es importante para que el celular con
la app mobile, conectado al mismo Wi-Fi, pueda pegarle al server por la IP
local de la PC (ej. `http://192.168.0.15:8000`).

### Variables de entorno útiles

| Variable               | Default   | Para qué sirve                                                        |
|-------------------------|-----------|------------------------------------------------------------------------|
| `PULSO_SERIAL_PORT`     | (auto)    | Puerto del Arduino. Ej: `COM5`, `/dev/ttyUSB0`. Si no se define, se auto-detecta el primer puerto serial disponible. |
| `PULSO_BAUDRATE`        | `115200`  | Debe matchear el `.ino`.                                                |
| `PULSO_MOCK_ARDUINO`    | `0`       | Poner en `1` para probar el backend/app **sin** Arduino conectado: simula BPM oscilante y recorre las 4 políticas solo. |

Ejemplo para probar sin hardware:

```bash
PULSO_MOCK_ARDUINO=1 python3 manage.py runserver 0.0.0.0:8000
```

## 3) Cómo se decide la política automáticamente

En `backend/pulso_backend/settings.py`:

```python
PULSO_POLICY_THRESHOLDS = {
    "calm_down": 33,   # delta >= 33
    "breath": 19,      # 19 <= delta < 33
    "awareness": 9,    # 9 <= delta < 19
    # delta < 9 -> reassure
}
```

`delta = smooth_bpm - baseline_bpm` (ambos calculados por el Arduino y
enviados como telemetría cruda). Estos umbrales se pueden ajustar sin tocar
el firmware.

## 4) API REST expuesta (la va a consumir la app mobile)

| Método | Endpoint                              | Uso                                                                 |
|--------|----------------------------------------|----------------------------------------------------------------------|
| GET    | `/api/policies/`                       | Las 4 tarjetas de la pantalla principal (código, título, descripción). |
| GET    | `/api/policies/<code>/`                | Detalle de una política + calibración de sus 6 motores.              |
| PUT    | `/api/policies/<code>/motors/`         | Guarda los 6 sliders ("Guardar Cambios del Patrón").                  |
| POST   | `/api/policies/<code>/activate/`       | Dispara esa política manualmente, ahora mismo.                        |
| GET    | `/api/status/`                         | BPM actual, conexión Arduino, modo (auto/manual), intensidad global.  |
| PUT    | `/api/status/`                         | Cambia intensidad global y/o modo auto/manual.                        |
| POST   | `/api/stop/`                           | Apaga los motores ya.                                                 |

`<code>` es uno de: `reassure`, `awareness`, `breath`, `calm_down`.

Body de ejemplo para `PUT /api/policies/breath/motors/`:

```json
{
  "motors": [
    {"motor_index": 0, "intensity_percent": 45},
    {"motor_index": 1, "intensity_percent": 45},
    {"motor_index": 2, "intensity_percent": 82},
    {"motor_index": 3, "intensity_percent": 82},
    {"motor_index": 4, "intensity_percent": 20},
    {"motor_index": 5, "intensity_percent": 20}
  ]
}
```

`motor_index` 0..5 corresponde a L1, R1, L2, R2, L3, R3 (misma grilla 2x3
del mockup).

## 5) De dónde sale cada cosa que muestra la pantalla

- **Descripción de cada política**: viene directo del catálogo JSON
  (`backend/haptic/patterns/*.json`, campo `description`), igual a los
  textos del mockup.
- **Intensidad final de cada motor** = intensidad del step del JSON (fija,
  define la "forma" del patrón: sube, sostiene, baja) × calibración de ese
  motor en esa política (slider L1..R3, guardado en la base) × intensidad
  global (slider de la pantalla principal).

## 6) App mobile (React Native + Expo)

Está en `mobile/`. Usa Expo Router (navegación por archivos) y consume
exactamente la API de arriba con `fetch` (sin librerías externas de red).

### Instalar y correr

```bash
cd mobile
npm install
npx expo start
```

Escaneá el QR con la app Expo Go (Android/iOS), o `npx expo start --android`
/ `--ios` con un emulador. **El celular tiene que estar en la misma red
Wi-Fi que la PC** donde corre Django.

### Configurar la conexión al backend

La primera vez, andá a la pestaña **Ajustes** y cargá la IP local de la PC
donde corre Django, por ejemplo:

```
http://192.168.0.15:8000
```

(no `127.0.0.1`/`localhost`, porque eso apuntaría al propio celular). Podés
buscar la IP de la PC con `ipconfig` (Windows) o `ip addr` / `ifconfig`
(Linux/macOS). Tocá "Probar conexión" para confirmar. Se guarda en el
celular (AsyncStorage), no hace falta configurarlo de nuevo.

### Estructura

```
mobile/
  app/
    _layout.tsx           Providers globales (tema + servidor) y stack raíz
    (tabs)/
      _layout.tsx          Tab bar: Inicio / Patrones / Ajustes
      index.tsx            Inicio: estado en vivo + intensidad global + grilla de políticas
      patterns.tsx          Patrones: lista completa con descripción
      settings.tsx          Ajustes: IP del servidor, modo auto/manual, modo oscuro, stop
    policy/[code].tsx       Edición de una política: 6 sliders por motor + guardar + probar
  src/
    api/                   Tipos + cliente fetch de la API Django
    components/            Piezas reutilizables (sliders, tarjetas, botones, barra superior)
    context/ServerContext.tsx   URL del backend (persistida) + polling de /api/status/
    theme/                 Colores + contexto de modo oscuro
```

### Pantallas y qué hacen

- **Inicio**: banner de conexión/BPM en vivo (poll cada 2s), slider de
  intensidad global (pega a `PUT /api/status/`), grilla de las 4 políticas
  (pega a `GET /api/policies/`). Tocar una tarjeta navega a su edición.
- **Patrones**: la misma lista de políticas en formato de filas con
  descripción completa, para llegar directo a editar cualquiera.
- **Ajustes**: IP del backend + botón de prueba, selector Automático/Manual
  (pega a `PUT /api/status/`), modo oscuro (sólo visual, local), y botón de
  emergencia "Detener motores ahora" (`POST /api/stop/`).
- **Editar política** (`policy/[code]`): trae `GET /api/policies/<code>/`,
  muestra descripción + 6 sliders (L1..R3) editables localmente, y dos
  acciones: "Guardar Cambios del Patrón" (`PUT /api/policies/<code>/motors/`,
  sólo habilitado si hay cambios sin guardar) y "Probar patrón ahora"
  (`POST /api/policies/<code>/activate/`, dispara el patrón ya mismo para
  poder sentirlo mientras calibrás).

### Qué quedó fuera de esta primera versión

Para no inflar el alcance sin necesidad, no se implementaron: perfiles de
usuario, modo daltonismo, paleta de colores personalizada ni notificaciones
push (estaban en el mockup pero no tienen contraparte funcional en el
backend actual). El modo oscuro sí quedó, porque es puramente visual y no
necesita nada del backend.

### Verificación hecha

- Backend: probado end-to-end con `PULSO_MOCK_ARDUINO=1` (sin hardware) —
  listar políticas, editar motores, cambiar intensidad global/modo, activar
  manualmente y detener, todo respondió como se esperaba.
- Mobile: `npx tsc --noEmit` sin errores y los íconos usados verificados
  contra el set real de Feather. No se corrió en un simulador/dispositivo
  real (no disponible en este entorno), así que probalo con Expo Go y
  contame si algo no se ve bien.
