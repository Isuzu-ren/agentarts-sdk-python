"""AgentArts Memory Provider plugin for Hermes Agent."""

try:
    # When imported as a package (e.g. `import agentarts_memory_hermes`).
    from .provider import AgentArtsMemoryProvider, register
except ImportError:  # pragma: no cover - fallback for sys.path-style import
    # When the plugin dir is on sys.path and imported as top-level modules
    # (e.g. `import __init__`), where relative imports are unavailable.
    from provider import AgentArtsMemoryProvider, register

__version__ = "1.0.0"

__all__ = ["AgentArtsMemoryProvider", "register"]
