#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pulso háptico - maqueta CLI para PC
===================================

Qué hace esta aplicación
------------------------
1) Abre una conexión serial USB con Arduino Nano.
2) Recibe telemetría del sketch stressDetectorAmpedHapticMVP.ino.
3) Muestra en pantalla los datos recibidos: BPM, BPM suavizado, línea base,
   delta y política sugerida.
4) Decide qué política aplicar.
5) Lee el patrón base de esa política desde archivos JSON del catálogo.
6) Aplica personalizaciones simples sobre adjustable_params:
   - intensity_scale
   - duration_scale
   - repeat_count, si el patrón lo permite
7) Traduce el JSON a un protocolo serial compacto para Arduino Nano.
8) Envía el patrón y muestra exactamente qué datos envió.

Por qué la app no manda JSON completo al Arduino
------------------------------------------------
Arduino Nano tiene RAM limitada. El JSON queda como formato de catálogo en la PC.
La PC lo convierte a líneas compactas:

    PATTERN,<policy_code>,<custom>,<repeat_count>,<cooldown_ms>,<step_count>
    STEP,<duration_ms>,<mask>,<pwm>,<transition_code>
    ...
    END

Instalación
-----------
    pip install -r requirements.txt

Uso típico
----------
Windows:
    python pc_haptic_app.py --port COM5 --catalog patterns

Linux:
    python pc_haptic_app.py --port /dev/ttyUSB0 --catalog patterns

macOS:
    python pc_haptic_app.py --port /dev/tty.usbserial-XXXX --catalog patterns

Personalización de una política
-------------------------------
Ejemplo: awareness un poco más intensa y breath más lenta.

    python pc_haptic_app.py --port COM5 --catalog patterns \
        --intensity-scale awareness=1.15 \
        --duration-scale breath=1.25

Ejemplo: repetir calm_down 3 veces, si el JSON lo permite.

    python pc_haptic_app.py --port COM5 --catalog patterns \
        --repeat-count calm_down=3

Comandos durante la ejecución
-----------------------------
La app es una maqueta de línea de comandos. Para detenerla: Ctrl+C.
Para frenar los motores desde la PC, cerrar con Ctrl+C envía STOP al Arduino.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover
    print("ERROR: falta instalar pyserial. Ejecutá: pip install pyserial", file=sys.stderr)
    sys.exit(1)


POLICY_TO_CODE = {
    "reassure": 1,
    "awareness": 2,
    "breath": 3,
    "calm_down": 4,
}

CODE_TO_POLICY = {v: k for k, v in POLICY_TO_CODE.items()}

TRANSITION_TO_CODE = {
    "instant": 0,
    "ramp_up": 1,
    "hold": 2,
    "ramp_down": 3,
    "pause": 4,
}

VALID_POLICIES = set(POLICY_TO_CODE.keys())


@dataclass
class EffectivePattern:
    """Patrón ya traducido a lo que entiende Arduino."""

    policy: str
    pattern_id: str
    customized: bool
    repeat_count: int
    cooldown_ms: int
    commands: List[str]
    human_steps: List[Dict[str, Any]]
    intensity_scale: float
    duration_scale: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Maqueta CLI PC-Arduino para compañero háptico con políticas vibrotáctiles."
    )
    parser.add_argument("--port", help="Puerto serial. Ej.: COM5, /dev/ttyUSB0, /dev/tty.usbserial-XXXX")
    parser.add_argument("--baud", type=int, default=115200, help="Baudios. Debe coincidir con el sketch Arduino.")
    parser.add_argument("--catalog", default="patterns", help="Carpeta con archivos JSON de patrones.")
    parser.add_argument("--reset-wait", type=float, default=2.0, help="Segundos de espera luego de abrir el puerto, porque Arduino se resetea.")
    parser.add_argument("--policy-mode", choices=["arduino", "pc"], default="arduino",
                        help="arduino usa la política enviada por el sketch; pc reclasifica con baseline/smooth_bpm si puede.")
    parser.add_argument("--intensity-scale", action="append", default=[], metavar="POLICY=VALUE",
                        help="Escala de intensidad por política. Ej.: awareness=1.15. Puede repetirse.")
    parser.add_argument("--duration-scale", action="append", default=[], metavar="POLICY=VALUE",
                        help="Escala de duración por política. Ej.: breath=1.25. Puede repetirse.")
    parser.add_argument("--repeat-count", action="append", default=[], metavar="POLICY=VALUE",
                        help="Repeticiones por política, si el JSON permite override. Ej.: calm_down=3.")
    parser.add_argument("--resend-after", type=float, default=0.0,
                        help="Reenvía la misma política luego de N segundos. 0 desactiva reenvío.")
    parser.add_argument("--dry-run", action="store_true",
                        help="No abre puerto serial: muestra carga de catálogo y ejemplos de comandos.")
    return parser.parse_args()


def parse_policy_value_overrides(items: Iterable[str], value_type: type) -> Dict[str, Any]:
    """Parsea argumentos tipo awareness=1.15 o calm_down=3."""
    result: Dict[str, Any] = {}
    for raw in items:
        if "=" not in raw:
            raise ValueError(f"Override inválido: {raw}. Usar POLICY=VALUE")
        policy, value = raw.split("=", 1)
        policy = policy.strip()
        if policy not in VALID_POLICIES:
            raise ValueError(f"Política inválida en override: {policy}")
        try:
            result[policy] = value_type(value)
        except ValueError as exc:
            raise ValueError(f"Valor inválido en override {raw}") from exc
    return result


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def load_catalog(catalog_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Carga todos los JSON de la carpeta y los indexa por context.policy."""
    if not catalog_dir.exists():
        raise FileNotFoundError(f"No existe la carpeta de catálogo: {catalog_dir}")

    catalog: Dict[str, Dict[str, Any]] = {}
    for path in sorted(catalog_dir.glob("*.json")):
        with path.open("r", encoding="utf-8") as f:
            pattern = json.load(f)
        validate_pattern_minimally(pattern, source=path)
        policy = pattern["context"]["policy"]
        catalog[policy] = pattern

    missing = sorted(VALID_POLICIES - set(catalog.keys()))
    if missing:
        print(f"ATENCIÓN: faltan políticas en el catálogo: {', '.join(missing)}")

    return catalog


def validate_pattern_minimally(pattern: Dict[str, Any], source: Path) -> None:
    """Validación estructural liviana para no sumar dependencia jsonschema.

    No reemplaza una validación formal contra estructuraPoliticaBase.json, pero detecta
    errores que romperían la traducción a Arduino.
    """
    required = [
        "pattern_id", "context", "device", "playback", "adjustable_params", "steps"
    ]
    for key in required:
        if key not in pattern:
            raise ValueError(f"{source}: falta clave requerida {key}")

    policy = pattern["context"].get("policy")
    if policy not in VALID_POLICIES:
        raise ValueError(f"{source}: política inválida: {policy}")

    if pattern["device"].get("channels") != 6:
        raise ValueError(f"{source}: device.channels debe ser 6")

    steps = pattern.get("steps", [])
    if not (1 <= len(steps) <= 8):
        raise ValueError(f"{source}: el sketch acepta entre 1 y 8 steps")

    for i, step in enumerate(steps, start=1):
        channels = step.get("channels")
        if not isinstance(channels, list) or len(channels) != 6 or any(c not in (0, 1) for c in channels):
            raise ValueError(f"{source}: step {i} debe tener 6 canales binarios")
        if step.get("transition") not in TRANSITION_TO_CODE:
            raise ValueError(f"{source}: transición inválida en step {i}: {step.get('transition')}")


def build_effective_pattern(
    pattern: Dict[str, Any],
    intensity_overrides: Dict[str, float],
    duration_overrides: Dict[str, float],
    repeat_overrides: Dict[str, int],
) -> EffectivePattern:
    """Convierte un JSON de catálogo en comandos compactos para Arduino."""
    policy = pattern["context"]["policy"]
    adjustable = pattern["adjustable_params"]

    intensity_spec = adjustable["intensity_scale"]
    duration_spec = adjustable["duration_scale"]

    base_intensity = float(intensity_spec["default"])
    base_duration = float(duration_spec["default"])

    intensity_scale = float(intensity_overrides.get(policy, base_intensity))
    duration_scale = float(duration_overrides.get(policy, base_duration))

    intensity_scale = clamp(intensity_scale, float(intensity_spec["min"]), float(intensity_spec["max"]))
    duration_scale = clamp(duration_scale, float(duration_spec["min"]), float(duration_spec["max"]))

    base_repeat = int(pattern["playback"]["repeat_count"])
    repeat_count = base_repeat
    if policy in repeat_overrides:
        if adjustable.get("allow_repeat_override", False):
            repeat_count = int(clamp(repeat_overrides[policy], 1, 8))
        else:
            print(f"ATENCIÓN: {policy} no permite override de repeat_count; se usa {base_repeat}")

    cooldown_ms = int(pattern["playback"]["cooldown_ms"])
    policy_code = POLICY_TO_CODE[policy]

    customized = (
        abs(intensity_scale - base_intensity) > 1e-6
        or abs(duration_scale - base_duration) > 1e-6
        or repeat_count != base_repeat
    )

    commands: List[str] = [
        f"PATTERN,{policy_code},{1 if customized else 0},{repeat_count},{cooldown_ms},{len(pattern['steps'])}"
    ]
    human_steps: List[Dict[str, Any]] = []

    for step in pattern["steps"]:
        duration_ms = max(1, int(round(int(step["duration_ms"]) * duration_scale)))
        pwm = int(round(float(step["intensity"]) * intensity_scale * 255.0))
        pwm = int(clamp(pwm, 0, 255))
        mask = channels_to_mask(step["channels"])
        transition_code = TRANSITION_TO_CODE[step["transition"]]
        commands.append(f"STEP,{duration_ms},{mask},{pwm},{transition_code}")
        human_steps.append({
            "duration_ms": duration_ms,
            "mask": mask,
            "pwm": pwm,
            "transition": step["transition"],
            "channels": step["channels"],
        })

    commands.append("END")

    return EffectivePattern(
        policy=policy,
        pattern_id=pattern["pattern_id"],
        customized=customized,
        repeat_count=repeat_count,
        cooldown_ms=cooldown_ms,
        commands=commands,
        human_steps=human_steps,
        intensity_scale=intensity_scale,
        duration_scale=duration_scale,
    )


def channels_to_mask(channels: List[int]) -> int:
    """Convierte [1,0,0,0,0,1] en máscara de bits: motor 0 y motor 5 activos."""
    mask = 0
    for i, active in enumerate(channels):
        if active:
            mask |= (1 << i)
    return mask


def parse_telemetry_line(line: str) -> Optional[Dict[str, str]]:
    """Parsea líneas TEL,key=value,key=value generadas por el sketch."""
    if not line.startswith("TEL,"):
        return None
    result: Dict[str, str] = {}
    for part in line[4:].split(","):
        if "=" in part:
            key, value = part.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def decide_policy(telemetry: Dict[str, str], mode: str) -> Optional[str]:
    """Decide política a aplicar.

    mode='arduino': toma la política calculada por el sketch.
    mode='pc': intenta reclasificar con smooth_bpm - baseline_bpm; si no puede,
               vuelve a la política recibida desde Arduino.
    """
    if telemetry.get("phase") != "run":
        return None

    if telemetry.get("signal_ok") == "0":
        return None

    arduino_policy = telemetry.get("policy")
    if arduino_policy == "no_signal":
        arduino_policy = None

    if mode == "arduino":
        return arduino_policy if arduino_policy in VALID_POLICIES else None

    # Clasificación local usando la misma regla relativa que el sketch.
    try:
        smooth_bpm = int(float(telemetry["smooth_bpm"]))
        baseline_bpm = int(float(telemetry["baseline_bpm"]))
    except (KeyError, ValueError):
        return arduino_policy if arduino_policy in VALID_POLICIES else None

    delta = smooth_bpm - baseline_bpm
    if delta >= 33:
        return "calm_down"
    if delta >= 19:
        return "breath"
    if delta >= 9:
        return "awareness"
    return "reassure"


def display_received_telemetry(telemetry: Dict[str, str]) -> None:
    """Muestra en consola sólo lo importante para la maqueta."""
    phase = telemetry.get("phase", "?")
    if phase == "baseline":
        print(
            "[BPM] fase=baseline "
            f"signal_ok={telemetry.get('signal_ok')} "
            f"bpm={telemetry.get('bpm')} "
            f"beat_avg={telemetry.get('beat_avg')} "
            f"muestras={telemetry.get('baseline_samples')} "
            f"elapsed_s={telemetry.get('elapsed_s', '-')}"
        )
    elif phase == "run":
        print(
            "[BPM] fase=run "
            f"bpm={telemetry.get('bpm')} "
            f"beat_avg={telemetry.get('beat_avg')} "
            f"smooth_bpm={telemetry.get('smooth_bpm')} "
            f"baseline={telemetry.get('baseline_bpm')} "
            f"delta={telemetry.get('delta')} "
            f"policy_rx={telemetry.get('policy')} "
            f"playback={telemetry.get('playback')}"
        )


def send_effective_pattern(ser: serial.Serial, effective: EffectivePattern) -> None:
    """Envía a Arduino el patrón ya compactado, con una pequeña pausa por línea."""
    print("\n[TX] política decidida:", effective.policy)
    print("[TX] pattern_id:", effective.pattern_id)
    print("[TX] tipo:", "PERSONALIZADA" if effective.customized else "BASE")
    print(
        f"[TX] intensity_scale={effective.intensity_scale:.2f}, "
        f"duration_scale={effective.duration_scale:.2f}, "
        f"repeat_count={effective.repeat_count}, cooldown_ms={effective.cooldown_ms}"
    )
    print("[TX] pasos traducidos:")
    for i, step in enumerate(effective.human_steps, start=1):
        print(
            f"     {i:02d}. duration={step['duration_ms']}ms "
            f"channels={step['channels']} mask={step['mask']} "
            f"pwm={step['pwm']} transition={step['transition']}"
        )

    for command in effective.commands:
        ser.write((command + "\n").encode("ascii"))
        ser.flush()
        time.sleep(0.015)


def choose_port_interactively() -> Optional[str]:
    """Lista puertos disponibles si el usuario no pasó --port."""
    ports = list(list_ports.comports())
    if not ports:
        print("No encontré puertos seriales. Conectá Arduino y volvé a ejecutar.")
        return None

    print("Puertos seriales detectados:")
    for i, port in enumerate(ports, start=1):
        print(f"  {i}. {port.device}  {port.description}")

    if len(ports) == 1:
        print(f"Uso automáticamente: {ports[0].device}")
        return ports[0].device

    choice = input("Elegí número de puerto: ").strip()
    try:
        index = int(choice) - 1
        if 0 <= index < len(ports):
            return ports[index].device
    except ValueError:
        pass
    print("Selección inválida.")
    return None


def run_dry(catalog: Dict[str, Dict[str, Any]], intensity_overrides: Dict[str, float],
            duration_overrides: Dict[str, float], repeat_overrides: Dict[str, int]) -> None:
    """Modo de prueba sin Arduino: muestra cómo se traducirían los patrones."""
    print("Modo dry-run: no se abre puerto serial.\n")
    for policy in ["reassure", "awareness", "breath", "calm_down"]:
        if policy not in catalog:
            continue
        effective = build_effective_pattern(catalog[policy], intensity_overrides, duration_overrides, repeat_overrides)
        print("=" * 70)
        print(f"Política: {policy} / patrón: {effective.pattern_id}")
        print("Tipo:", "PERSONALIZADA" if effective.customized else "BASE")
        for command in effective.commands:
            print(command)
    print("=" * 70)


def main() -> int:
    args = parse_args()

    try:
        intensity_overrides = parse_policy_value_overrides(args.intensity_scale, float)
        duration_overrides = parse_policy_value_overrides(args.duration_scale, float)
        repeat_overrides = parse_policy_value_overrides(args.repeat_count, int)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        catalog = load_catalog(Path(args.catalog))
    except Exception as exc:
        print(f"ERROR cargando catálogo: {exc}", file=sys.stderr)
        return 2

    print("Catálogo cargado:")
    for policy, pattern in sorted(catalog.items()):
        print(f"  - {policy}: {pattern['pattern_id']} ({pattern.get('name', 'sin nombre')})")
    print()

    if args.dry_run:
        run_dry(catalog, intensity_overrides, duration_overrides, repeat_overrides)
        return 0

    port = args.port or choose_port_interactively()
    if not port:
        return 2

    try:
        ser = serial.Serial(port=port, baudrate=args.baud, timeout=1.0, write_timeout=1.0)
    except serial.SerialException as exc:
        print(f"ERROR: no pude abrir {port}: {exc}", file=sys.stderr)
        return 1

    print(f"Conexión serial abierta en {port} a {args.baud} baudios.")
    print("Esperando reset inicial de Arduino...")
    time.sleep(args.reset_wait)
    ser.reset_input_buffer()

    # Ping liviano: si el sketch responde, aparecerá ACK,PONG en consola.
    ser.write(b"PING\n")
    ser.flush()
    print("Conexión establecida. Leyendo telemetría. Ctrl+C para salir.\n")

    last_sent_policy: Optional[str] = None
    last_sent_time = 0.0

    try:
        while True:
            raw = ser.readline()
            #print(raw)
            if not raw:
                continue

            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            # Siempre mostramos líneas de eventos, ACK y errores.
            if line.startswith(("EVT,", "ACK,", "ERR,")):
                print(f"[RX] {line}")
                continue

            telemetry = parse_telemetry_line(line)
            if telemetry is None:
                # Mensajes no parseables; útiles durante depuración.
                print(f"[RX?] {line}")
                continue

            display_received_telemetry(telemetry)
            policy = decide_policy(telemetry, args.policy_mode)
            if policy is None:
                continue

            print(f"[DECISION] política a aplicar: {policy}")

            if policy not in catalog:
                print(f"[DECISION] no hay patrón JSON para {policy}; no se envía nada.")
                continue

            now = time.time()
            should_send = policy != last_sent_policy
            if not should_send and args.resend_after > 0:
                should_send = (now - last_sent_time) >= args.resend_after

            if should_send:
                effective = build_effective_pattern(
                    catalog[policy],
                    intensity_overrides=intensity_overrides,
                    duration_overrides=duration_overrides,
                    repeat_overrides=repeat_overrides,
                )
                send_effective_pattern(ser, effective)
                last_sent_policy = policy
                last_sent_time = now

    except KeyboardInterrupt:
        print("\nCerrando. Envío STOP para apagar motores.")
        try:
            ser.write(b"STOP\n")
            ser.flush()
            time.sleep(0.1)
        except serial.SerialException:
            pass
    finally:
        ser.close()
        print("Puerto serial cerrado.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
