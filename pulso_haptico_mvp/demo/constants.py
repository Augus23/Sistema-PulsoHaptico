# =============================================================================
# CONSTANTES Y PROTOCOLO
# =============================================================================
MOCK_BASELINE_BPM = 68

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
DEMO_STEP_DURATION_SEC = 5.0

BPM_CONFIG = {
    "awareness": {"bpm": 70, "amplitude": 8},
    "reassure": {"bpm": 90, "amplitude": 50},
    "breath": {"bpm": 110, "amplitude": 100},
    "calm_down": {"bpm": 130, "amplitude": 200},
}


POLICY_LABELS = {
    "awareness": "CONCIENCIA",
    "reassure": "CONTENCIÓN",
    "breath": "RESPIRACIÓN",
    "calm_down": "CALMA",
}

POLICY_COLORS = {
    "awareness": "#00ADB5",
    "reassure": "#007CB5",
    "breath": "#0054B5",
    "calm_down": "#0027B5",
}

MOCK_ECG_POLICY_LEVELS = {
    "awareness": (8.0, "CONCIENCIA - NIVEL 1"),
    "reassure": (14.0, "CONTENCIÓN - NIVEL 2"),
    "breath": (22.0, "RESPIRACIÓN - NIVEL 3"),
    "calm_down": (31.0, "CALMA - NIVEL 4"),
}

POLICY_SCENARIOS = {
    "awareness": (
        "Un cambio de actividad",
        "En una transicion cotidiana se acumulan ruido, movimiento o conversaciones. Puede ser un momento para notar las primeras señales de incomodidad.",
        "Una señal suave acompana la atencion al pulso.",
    ),
    "reassure": (
        "Un plan que cambia",
        "Una modificacion inesperada de la rutina puede generar incertidumbre o tension.",
        "Un ritmo predecible ofrece una referencia estable.",
    ),
    "breath": (
        "Un entorno muy estimulante",
        "En un lugar concurrido, el ruido y la actividad pueden hacer que la activacion siga subiendo.",
        "El patron ritmico acompaña una pausa y una respiracion mas lenta.",
    ),
    "calm_down": (
        "Necesidad de bajar estimulos",
        "Tras acumularse varios estimulos, puede ayudar hacer una pausa o buscar un lugar mas tranquilo.",
        "La secuencia acompaña la autorregulacion, respetando lo que le resulte comodo a la persona.",
    ),
}
MOTOR_POLICY_DESCRIPTIONS = {
    "awareness": "En medio de la rutina, cuando el ruido o el movimiento empiezan a generar una incomodidad leve, el dispositivo da un toque suave y rápido en el brazo, como un \"subrayado\" sutil para avisarte que tu cuerpo está empezando a notarlo, sin apurarte ni corregirte nada todavía.",
    "reassure": "Frente a un cambio inesperado en la rutina o cuando hay incertidumbre, pero querés mantener la tranquilidad, el dispositivo da un toque muy suave y repartido en el brazo, como una presencia discreta que te confirma que todo está bien y te ayuda a mantener el equilibrio",
    "breath": "En situaciones muy estimulantes o concurridas (como una exposición pública) donde la ansiedad empieza a subir, el dispositivo te acompaña con una vibración en forma de \"ola\" que sube, se mantiene un instante y baja suavemente, invitándote a regular el ritmo de tu respiración sin apurarte",
    "calm_down": "Cuando se acumulan demasiados estímulos, el nivel de estrés es alto y el cuerpo necesita hacer una pausa o buscar un lugar más tranquilo, el dispositivo te abraza con una vibración amplia que empieza firme y se va apagando progresivamente, ayudándote a bajar la intensidad de forma segura y sin sobresaltos.",
}