"""Carga el catálogo de patrones (JSON) y los traduce al protocolo serial
compacto que entiende el firmware Arduino.

A diferencia de la maqueta CLI original, acá la intensidad final de cada
STEP se calcula por MOTOR individual (no un único valor de intensidad para
todo el patrón), combinando:

    pwm_motor_i = intensity_json_del_step (0..1)
                * (calibracion_motor_i_de_la_politica / 100)
                * (intensidad_global / 100)
                * 255

Esto es lo que permite que la pantalla de cada política tenga un slider
independiente por motor (L1, R1, L2, R2, L3, R3), y que la pantalla
principal tenga además un slider de "Intensidad Global" que multiplica a
todos los motores de todas las políticas por igual.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from .. import constants

PATTERNS_DIR = Path(__file__).resolve().parent.parent / "patterns"


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def load_catalog() -> Dict[str, dict]:
    """Carga todos los JSON de /haptic/patterns y los indexa por política."""
    catalog: Dict[str, dict] = {}
    for path in sorted(PATTERNS_DIR.glob("*.json")):
        with path.open("r", encoding="utf-8") as f:
            pattern = json.load(f)
        policy = pattern["context"]["policy"]
        catalog[policy] = pattern
    return catalog


# Catálogo cargado una sola vez al importar el módulo (los JSON son estáticos).
CATALOG: Dict[str, dict] = load_catalog()


def get_policy_description(policy: str) -> str:
    pattern = CATALOG.get(policy)
    if not pattern:
        return ""
    return pattern.get("description", "")


def build_serial_commands(
    policy: str,
    motor_intensity_percent: List[float],
    global_intensity_percent: float,
) -> List[str]:
    """Traduce el patrón JSON de `policy` a líneas PATTERN/STEP/END.

    motor_intensity_percent: lista de 6 valores 0..100, uno por motor
        (L1, R1, L2, R2, L3, R3), específicos de esta política.
    global_intensity_percent: 0..100, viene del slider de la pantalla
        principal y afecta a todas las políticas por igual.
    """
    if policy not in CATALOG:
        raise ValueError(f"Política desconocida o sin patrón cargado: {policy}")
    if len(motor_intensity_percent) != constants.MOTOR_COUNT:
        raise ValueError("motor_intensity_percent debe tener 6 valores")

    pattern = CATALOG[policy]
    policy_code = constants.POLICY_TO_CODE[policy]
    repeat_count = int(pattern["playback"]["repeat_count"])
    cooldown_ms = int(pattern["playback"]["cooldown_ms"])
    steps = pattern["steps"]

    global_factor = _clamp(global_intensity_percent, 0, 100) / 100.0
    motor_factors = [_clamp(v, 0, 100) / 100.0 for v in motor_intensity_percent]

    lines: List[str] = [
        f"PATTERN,{policy_code},{repeat_count},{cooldown_ms},{len(steps)}"
    ]

    for step in steps:
        channels = step["channels"]
        base_intensity = float(step["intensity"])  # 0..1, definido por el JSON
        transition_code = constants.TRANSITION_TO_CODE[step["transition"]]

        pwm_values = []
        for i in range(constants.MOTOR_COUNT):
            if channels[i]:
                pwm = base_intensity * motor_factors[i] * global_factor * 255.0
            else:
                pwm = 0.0
            pwm_values.append(int(round(_clamp(pwm, 0, 255))))

        duration_ms = int(step["duration_ms"])
        pwm_csv = ",".join(str(v) for v in pwm_values)
        lines.append(f"STEP,{duration_ms},{pwm_csv},{transition_code}")

    lines.append("END")
    return lines


def decide_policy_from_delta(delta: float) -> str:
    """Mapea delta (smooth_bpm - baseline_bpm) a una política.

    Esta es LA lógica de decisión del sistema: vive acá, en el backend,
    no en el firmware Arduino.
    """
    from django.conf import settings

    thresholds = settings.PULSO_POLICY_THRESHOLDS
    if delta >= thresholds["calm_down"]:
        return constants.POLICY_CALM_DOWN
    if delta >= thresholds["breath"]:
        return constants.POLICY_BREATH
    if delta >= thresholds["awareness"]:
        return constants.POLICY_AWARENESS
    return constants.POLICY_REASSURE
