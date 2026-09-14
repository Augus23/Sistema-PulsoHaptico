# =============================================================================
# ESTRUCTURAS DE DATOS Y UTILIDADES DE PATRÓN
# =============================================================================



def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def channels_to_mask(channels: List[int]) -> int:
    mask = 0
    for i, active in enumerate(channels):
        if active:
            mask |= (1 << i)
    return mask


def load_catalog(catalog_dir: Path) -> Dict[str, Dict[str, Any]]:
    if not catalog_dir.exists():
        raise FileNotFoundError(f"No existe la carpeta de catálogo: {catalog_dir}")

    catalog: Dict[str, Dict[str, Any]] = {}
    for path in sorted(catalog_dir.glob("*.json")):
        with path.open("r", encoding="utf-8") as f:
            pattern = json.load(f)
        policy = pattern["context"]["policy"]
        catalog[policy] = pattern
    return catalog


def build_effective_pattern(pattern: Dict[str, Any]) -> EffectivePattern:
    policy = pattern["context"]["policy"]
    adjustable = pattern["adjustable_params"]
    
    base_intensity = float(adjustable["intensity_scale"]["default"])
    base_duration = float(adjustable["duration_scale"]["default"])
    repeat_count = int(pattern["playback"]["repeat_count"])
    cooldown_ms = int(pattern["playback"]["cooldown_ms"])
    policy_code = POLICY_TO_CODE[policy]

    commands: List[str] = [
        f"PATTERN,{policy_code},0,{repeat_count},{cooldown_ms},{len(pattern['steps'])}"
    ]
    human_steps: List[Dict[str, Any]] = []

    for step in pattern["steps"]:
        duration_ms = max(1, int(round(int(step["duration_ms"]) * base_duration)))
        pwm = int(round(float(step["intensity"]) * base_intensity * 255.0))
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
        customized=False,
        repeat_count=repeat_count,
        cooldown_ms=cooldown_ms,
        commands=commands,
        human_steps=human_steps
    )


def parse_telemetry_line(line: str) -> Optional[Dict[str, str]]:
    if not line.startswith("TEL,"):
        return None
    result: Dict[str, str] = {}
    for part in line[4:].split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            result[k.strip()] = v.strip()
    return result