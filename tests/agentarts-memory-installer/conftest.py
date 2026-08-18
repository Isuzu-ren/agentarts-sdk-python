"""Pytest configuration for agentarts-memory-installer tests.

Makes the installer's `agentarts_memory_installer` package importable
without installing it, by inserting the plugin root onto sys.path.
"""

import os
import sys

_PLUGIN_ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "..", "agentarts-memory-plugins", "agentarts-memory-installer"
    )
)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)
