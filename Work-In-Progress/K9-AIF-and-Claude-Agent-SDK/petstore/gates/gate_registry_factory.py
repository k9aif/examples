"""Static factory for BaseGateRegistry providers — mirrors K9-AIF's Provider Adapter Pattern."""

from __future__ import annotations

import logging
from threading import Lock
from typing import Any, Dict, Optional, Type

log = logging.getLogger("GateRegistryFactory")


class GateRegistryFactory:
    _registry: Dict[str, Type[Any]] = {}
    _lock = Lock()
    _bootstrapped = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("GateRegistryFactory is static")

    @staticmethod
    def _ensure_defaults() -> None:
        if GateRegistryFactory._bootstrapped:
            return
        with GateRegistryFactory._lock:
            if GateRegistryFactory._bootstrapped:
                return
            from petstore.gates.simple_gate_registry import SimpleGateRegistry

            GateRegistryFactory._registry.update({"simple": SimpleGateRegistry})
            GateRegistryFactory._bootstrapped = True

    @staticmethod
    def register(name: str, cls: Type[Any]) -> None:
        GateRegistryFactory._ensure_defaults()
        with GateRegistryFactory._lock:
            GateRegistryFactory._registry[name.lower()] = cls

    @staticmethod
    def get(name: str, config: Optional[Dict[str, Any]] = None) -> Any:
        GateRegistryFactory._ensure_defaults()
        cls = GateRegistryFactory._registry.get(name.lower())
        if not cls:
            raise ValueError(f"Unknown gate registry provider: {name}")
        return cls(config=config or {})

    @staticmethod
    def create(config: Optional[Dict[str, Any]] = None) -> Any:
        GateRegistryFactory._ensure_defaults()
        provider = (config or {}).get("gates", {}).get("provider", "simple").lower()
        log.info("[GateRegistryFactory] Creating gate registry provider: %s", provider)
        return GateRegistryFactory.get(provider, config=config)
