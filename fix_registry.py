p = r'T:/hace/engine/hace/sdk/executor-py/src/executor_py/io/rac/cri/fdi_adapters.py'
c = open(p, encoding='utf-8').read()

# Add persistent registry function at the top after imports
import_marker = """from __future__ import annotations

from typing import Any, Callable, Dict, Optional
import importlib
import sys"""

c = c.replace(import_marker, import_marker + """

# Persistent registry (survives module reload)
def _get_registry():
    if not hasattr(_get_registry, '_registry'):
        _get_registry._registry = {}
    return _get_registry._registry""")

# Update _register_adapters to use persistent registry
old_register = """def _register_adapters():
    \"\"\"Register all adapters for text-editor capabilities.\"\"\"
    
    # Str actions
    str_actions = ["""

new_register = """def _register_adapters():
    \"\"\"Register all adapters for text-editor capabilities.\"\"\"
    registry = _get_registry()
    if registry:
        return  # Already registered
    
    # Str actions
    str_actions = ["""

c = c.replace(old_register, new_register)

# Update get_adapter
old_get = """def get_adapter(capability: str) -> Optional[Callable]:
    \"\"\"Get adapter for a capability, creating it if needed.\"\"\"
    if not _ADAPTER_REGISTRY:
        _register_adapters()
    return _ADAPTER_REGISTRY.get(capability)"""

new_get = """def get_adapter(capability: str) -> Optional[Callable]:
    \"\"\"Get adapter for a capability, creating it if needed.\"\"\"
    registry = _get_registry()
    if not registry:
        _register_adapters()
    return registry.get(capability)"""

c = c.replace(old_get, new_get)

# Update list_adapters
old_list = """def list_adapters() -> list[str]:
    \"\"\"List all registered adapter capabilities.\"\"\"
    if not _ADAPTER_REGISTRY:
        _register_adapters()
    return list(_ADAPTER_REGISTRY.keys())"""

new_list = """def list_adapters() -> list[str]:
    \"\"\"List all registered adapter capabilities.\"\"\"
    registry = _get_registry()
    if not registry:
        _register_adapters()
    return list(registry.keys())"""

c = c.replace(old_list, new_list)

# Remove the global _ADAPTER_REGISTRY variable
c = c.replace("""_ADAPTER_REGISTRY: Dict[str, Callable] = {}

def _register_adapters():""", """def _register_adapters():""")

open(p, 'w', encoding='utf-8').write(c)
print('Done')