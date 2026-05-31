"""
Pytest configuration for module tests.

Behavioral tests use inheritance from amplifier-core base classes.
See tests/test_behavioral.py for the inherited tests.

The amplifier-core pytest plugin provides fixtures automatically:
- module_path: Detected path to this module
- module_type: Detected type (provider, tool, hook, etc.)
- coordinator: MockCoordinator for mounting modules
- provider_module, tool_module, etc.: Mounted module instances
"""

import sys
from pathlib import Path

# Ensure the local package is importable when running via
# 'uv run --with amplifier-core pytest' (which can use the system Python
# rather than the project's .venv, so the editable-install .pth file is
# not on sys.path automatically).
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
