# =============================================================================
# CONSTANTES Y PROTOCOLO
# =============================================================================
POLICY_TO_CODE = {
    "reassure": 1,
    "awareness": 2,
    "breath": 3,
    "calm_down": 4,
}

TRANSITION_TO_CODE = {
    "instant": 0,
    "ramp_up": 1,
    "hold": 2,
    "ramp_down": 3,
    "pause": 4,
}

# The automatic demo intentionally starts with awareness and then reassure.
SEQUENTIAL_POLICIES = ["awareness", "reassure", "breath", "calm_down"]
VALID_POLICIES = SEQUENTIAL_POLICIES.copy()
DEMO_STEP_DURATION_SEC = 15.0

BPM_CONFIG = {
    "awareness": {"bpm": 70, "amplitude": 8},
    "reassure": {"bpm": 90, "amplitude": 50},
    "breath": {"bpm": 110, "amplitude": 100},
    "calm_down": {"bpm": 130, "amplitude": 200},
}


POLICY_LABELS = {
    "awareness": "SER CONSCIENTE",
    "reassure": "ACOMPAÑAR",
    "breath": "RESPIRAR",
    "calm_down": "CALMARSE",
}

BUTTON_COLOR = "#007CB5"

MOCK_ECG_POLICY_LEVELS = {
    "awareness": (8.0, f"{POLICY_LABELS['awareness']} - NIVEL 1"),
    "reassure": (14.0, f"{POLICY_LABELS['reassure']} - NIVEL 2"),
    "breath": (22.0, f"{POLICY_LABELS['breath']} - NIVEL 3"),
    "calm_down": (31.0, f"{POLICY_LABELS['calm_down']} - NIVEL 4"),
}

POLICY_SCENARIOS = {
    "awareness": (
        "Activación: Incremento leve de la frecuencia cardíaca. Propuesta: Señal suave que permite tomar una pausa y llevar la atención al cuerpo."
    ),
    "reassure": (
        "Activación: Fluctuaciones contínuas de la frecuencia cardíaca. Propuesta: Toque suave y contínuo que proporciona estabilidad y compañía"
    ),
    "breath": (
        "Activación: Ritmo cardíaco moderado. Propuesta: Marca compás pausado que acompaña al ritmo de la respiración"
    ),
    "calm_down": (
        "Activación: Incremento considerable del pulso cardíaco. Propuesta: Emisión de patrón suave para reducir sobreestimulación"
    ),
}