from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class EffectivePattern:
    policy: str
    pattern_id: str
    customized: bool
    repeat_count: int
    cooldown_ms: int
    commands: List[str]
    human_steps: List[Dict[str, Any]]

