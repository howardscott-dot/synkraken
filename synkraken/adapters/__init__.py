from .base import BaseAdapter
from .claude import ClaudeAdapter
from .goose import GooseAdapter
from .hermes import HermesAdapter
from .openclaw import OpenClawAdapter

ADAPTER_TYPES = {
    "claude": ClaudeAdapter,
    "goose": GooseAdapter,
    "hermes": HermesAdapter,
    "openclaw": OpenClawAdapter,
}


def build_adapter(adapter_id: str, config: dict) -> BaseAdapter:
    adapter_type = config.get("type")
    if adapter_type not in ADAPTER_TYPES:
        raise ValueError(f"Unsupported adapter type: {adapter_type}")
    return ADAPTER_TYPES[adapter_type](adapter_id=adapter_id, config=config)
