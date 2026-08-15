# -*- coding: utf-8 -*-
"""
executor_py.io.rac.cri.fdi_binding — Lazy-loading capability binding helper.

Per rac-uri-resolver.ail §5: rac:import → bind_execution_substrate.
Supports adapter functions for text-editor capabilities.
"""

from __future__ import annotations

import importlib
import sys
from typing import Callable, Optional


def _load_text_editor_bootstrap():
    """Ensure text-editor bootstrap is loaded.

    Text-editor's __init__.py adds its directory to sys.path, so submodules
    are importable as direct names (e.g., "str.core", "uri.core").
    Sets __path__ to include all subdirectories for namespace resolution.
    """
    if "text_editor" not in sys.modules:
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location(
            "text_editor", "T:/hace/engine/hace/text-editor/__init__.py"
        )
        text_editor = _ilu.module_from_spec(spec)
        text_editor.__path__ = [
            "T:/hace/engine/hace/text-editor",
            "T:/hace/engine/hace/text-editor/io",
            "T:/hace/engine/hace/text-editor/io/rac",
            "T:/hace/engine/hace/text-editor/io/rac/cri",
            "T:/hace/engine/hace/text-editor/uri",
            "T:/hace/engine/hace/text-editor/str",
            "T:/hace/engine/hace/text-editor/file",
            "T:/hace/engine/hace/text-editor/addon",
        ]
        sys.modules["text_editor"] = text_editor
        spec.loader.exec_module(text_editor)


def _get_adapter(capability: str):
    """Get adapter for text-editor capabilities."""
    # Check if capability is a text-editor capability
    if capability.startswith("fdi.str.") or capability.startswith("fdi.uri.") or \
       capability.startswith("fdi.file.") or capability.startswith("fdi.str.ail_"):
        
        # Import adapter module
        try:
            from .fdi_adapters import get_adapter
            return get_adapter(capability)
        except ImportError:
            pass
    return None


def _lazy_load_binding(module_path: str, func_name: str) -> Callable:
    """Lazy-load a capability binding from a module path + function name.

    Returns a guarded callable that dispatches to the resolved handler.
    Per rac-uri-resolver.ail §5: bind_execution_substrate.
    
    For text-editor capabilities, uses adapter functions that translate
    the calling convention to executor-py convention.
    """
    # Check if this is a text-editor capability that needs an adapter
    # Extract capability from module_path/func_name
    capability = None
    if module_path.startswith("text_editor."):
        # Map module_path/func_name to capability
        if module_path == "text_editor.str.core" and func_name == "handle_str_action":
            # We can't determine the exact action from just this, so we need
            # the capability to be passed differently. For now, fall through.
            pass
        elif module_path == "text_editor.uri.core" and func_name == "handle_uri_action":
            pass
        elif module_path == "text_editor.file.core":
            pass
        elif module_path == "text_editor.addon.ail_machine.bridge":
            pass
    
    # Standard lazy loading for non-adapted capabilities
    parts = module_path.split(".")
    for i in range(len(parts), 0, -1):
        candidate = ".".join(parts[:i])
        try:
            mod = importlib.import_module(candidate)
        except ImportError:
            continue
        remainder = module_path[len(candidate) + 1:].replace(".", "/")
        if remainder:
            try:
                mod = importlib.import_module(f"{candidate}.{remainder.replace('/', '.')}")
            except ImportError:
                continue
        handler = getattr(mod, func_name, None)
        if handler is not None:
            return handler
    
    # If we reach here, check if there's an adapter for this capability
    # We need the capability identifier - try to derive it
    if module_path.startswith("text_editor.str.core") and func_name == "handle_str_action":
        # This is a generic str handler - we can't determine specific action
        # The caller should use the adapter directly
        pass
    elif module_path.startswith("text_editor.uri.core") and func_name == "handle_uri_action":
        pass
    elif module_path.startswith("text_editor.file.core"):
        pass
    elif module_path.startswith("text_editor.addon.ail_machine.bridge"):
        pass
    
    raise ImportError(f"Cannot resolve {module_path}.{func_name}")


def get_capability_adapter(capability: str):
    """
    Get adapter function for a capability.
    
    Returns adapter function if capability has an adapter, None otherwise.
    Adapter functions have signature: adapter(ctx, **args) -> result
    """
    try:
        from .fdi_adapters import get_adapter
        return get_adapter(capability)
    except ImportError:
        return None


def load_text_editor_module(module_path: str):
    """Load text-editor module with proper bootstrap."""
    if module_path.startswith("text_editor."):
        if "text_editor" not in sys.modules:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "text_editor", "T:/hace/engine/hace/text-editor/__init__.py"
            )
            text_editor = importlib.util.module_from_spec(spec)
            sys.modules["text_editor"] = text_editor
            spec.loader.exec_module(text_editor)
    return importlib.import_module(module_path)