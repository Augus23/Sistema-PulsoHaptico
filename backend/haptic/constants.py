"""Constantes compartidas por todo el backend de Pulso Háptico."""

POLICY_REASSURE = "reassure"
POLICY_AWARENESS = "awareness"
POLICY_BREATH = "breath"
POLICY_CALM_DOWN = "calm_down"

VALID_POLICIES = [POLICY_REASSURE, POLICY_AWARENESS, POLICY_BREATH, POLICY_CALM_DOWN]

POLICY_CHOICES = [
    (POLICY_REASSURE, "Reassure"),
    (POLICY_AWARENESS, "Awareness"),
    (POLICY_BREATH, "Breath"),
    (POLICY_CALM_DOWN, "Calm Down"),
]

# Códigos numéricos que entiende el firmware Arduino (PATTERN,<policy_code>,...)
POLICY_TO_CODE = {
    POLICY_REASSURE: 1,
    POLICY_AWARENESS: 2,
    POLICY_BREATH: 3,
    POLICY_CALM_DOWN: 4,
}
CODE_TO_POLICY = {v: k for k, v in POLICY_TO_CODE.items()}

TRANSITION_TO_CODE = {
    "instant": 0,
    "ramp_up": 1,
    "hold": 2,
    "ramp_down": 3,
    "pause": 4,
}

MOTOR_COUNT = 6
# Etiquetas mostradas en la app, en el mismo orden que los canales 0..5
# del JSON (grilla 2x3): L1 R1 / L2 R2 / L3 R3
MOTOR_LABELS = ["L1", "R1", "L2", "R2", "L3", "R3"]

# Título/subtítulo cortos para las tarjetas de la pantalla principal.
# La descripción larga se toma directamente del JSON de cada patrón.
POLICY_TITLES = {
    POLICY_REASSURE: ("Presencia estable", "Cálido, constante"),
    POLICY_AWARENESS: ("Presencia creciente", "Nítido, enfocado"),
    POLICY_BREATH: ("Respiración cíclica", "Pulsante, lento"),
    POLICY_CALM_DOWN: ("Guía hacia la quietud", "Descendente, suave"),
}

DEFAULT_MOTOR_INTENSITY_PERCENT = 70.0
DEFAULT_GLOBAL_INTENSITY_PERCENT = 65.0

MODE_AUTO = "auto"
MODE_MANUAL = "manual"
MODE_CHOICES = [(MODE_AUTO, "Automático"), (MODE_MANUAL, "Manual")]
