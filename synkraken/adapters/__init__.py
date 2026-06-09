from .base import BaseAdapter
from .claude import ClaudeAdapter
from .crush import CrushAdapter
from .goose import GooseAdapter
from .hermes import HermesAdapter
from .openclaw import OpenClawAdapter
from .antigravity import AntigravityAdapter
from .odysseus import OdysseusAdapter
from .ollama import OllamaAdapter

ADAPTER_TYPES = {
    "claude": ClaudeAdapter,
    "crush": CrushAdapter,
    "goose": GooseAdapter,
    "hermes": HermesAdapter,
    "openclaw": OpenClawAdapter,
    "google_antigravity": AntigravityAdapter,
    "odysseus": OdysseusAdapter,
    "ollama": OllamaAdapter,
}


def build_adapter(adapter_id: str, config: dict) -> BaseAdapter:
    adapter_type = config.get("type")
    if adapter_type not in ADAPTER_TYPES:
        raise ValueError(f"Unsupported adapter type: {adapter_type}")
    return ADAPTER_TYPES[adapter_type](adapter_id=adapter_id, config=config)
