"""AgentArts Memory Provider plugin for Hermes Agent."""

try:
    from .provider import AgentArtsMemoryProvider, register
except ImportError:  # imported as a top-level module (no parent package)
    from provider import AgentArtsMemoryProvider, register

__version__ = "1.0.0"

__all__ = ["AgentArtsMemoryProvider", "register"]
