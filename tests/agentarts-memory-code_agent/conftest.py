"""Conftest for agentarts-memory-code_agent tests.

Makes the plugin's `server` package importable without installing it,
by inserting the plugin root onto sys.path.
"""

import os
import sys

_PLUGIN_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "agentarts-memory-plugins", "agentarts-memory-code_agent")
)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)
