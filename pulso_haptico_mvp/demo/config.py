@dataclass
class EffectivePattern:
    policy: str
    pattern_id: str
    customized: bool
    repeat_count: int
    cooldown_ms: int
    commands: List[str]
    human_steps: List[Dict[str, Any]]



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

VALID_POLICIES = ["reassure", "awareness", "breath", "calm_down"]
DEMO_STEP_DURATION_SEC = 30.0