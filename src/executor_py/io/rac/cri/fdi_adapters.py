# -*- coding: utf-8 -*-
"""
executor_py.io.rac.cri.fdi_adapters — FDI Handler Adapters for text-editor

Adapts text-editor FDI handlers to executor-py calling convention.

Text-editor handlers: handle_str_action(action, payload, headers, context) -> dict
Executor-py convention: handler(ctx, **args) -> result
Text-editor direct binding: handler(payload_dict) -> result

This module provides adapter functions that bridge the calling conventions.
Supports both calling conventions:
- Executor-py: handler(ctx, **args)
- Text-editor direct: handler(payload_dict)
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional
import importlib
import sys
from pathlib import Path


# ─── Module Loading (at module level to avoid closure scoping issues) ──────────

def _load_text_editor_module(module_path: str):
    """Load text-editor module with proper bootstrap.

    Text-editor's __init__.py adds its directory to sys.path, so submodules
    are importable as direct names (e.g., "str.core", "uri.core").

    Sets __path__ to include all subdirectories for namespace package resolution
    """
    if module_path.startswith("text_editor."):
        # Ensure text-editor is bootstrapped
        if "text_editor" not in sys.modules:
            import importlib.util as _importlib_util
            spec = _importlib_util.spec_from_file_location(
                "text_editor", "T:/hace/engine/hace/text-editor/__init__.py"
            )
            text_editor = _importlib_util.module_from_spec(spec)
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

        # Text-editor submodules are importable directly since __init__.py
        # added the directory to sys.path. But some submodules (like addon.*)
        # have __init__.py that trigger hard imports that may fail.
        # Try direct submodule import first, then fall back to importlib.util
        submodule = module_path.replace("text_editor.", "")
        try:
            return importlib.import_module(submodule)
        except ImportError:
            pass

        # Fallback: try via text_editor package (if __path__ is set)
        try:
            return importlib.import_module(module_path)
        except (ImportError, Exception):
            pass

        # Last resort: load module directly via importlib.util
        # This bypasses __init__.py chain for submodules like addon.ail_machine.bridge
        try:
            import importlib.util as _ilu
            file_path = "T:/hace/engine/hace/text-editor/" + submodule.replace(".", "/") + ".py"
            _path = Path(file_path)
            if _path.is_file():
                _spec = _ilu.spec_from_file_location(module_path, file_path)
                _mod = _ilu.module_from_spec(_spec)
                sys.modules[module_path] = _mod
                _spec.loader.exec_module(_mod)
                return _mod
        except Exception:
            pass

    return importlib.import_module(module_path)


# Pre-load text-editor handler modules at import time to avoid closure scoping issues
_STR_HANDLER = None
_URI_HANDLER = None
_FILE_HANDLERS = {}
_AIL_HANDLERS = {}


def _ensure_str_handler():
    global _STR_HANDLER
    if _STR_HANDLER is None:
        module = _load_text_editor_module("text_editor.str.core")
        _STR_HANDLER = getattr(module, "handle_str_action", None)
        if _STR_HANDLER is None:
            raise RuntimeError("text_editor.str.core.handle_str_action not found")
    return _STR_HANDLER


def _ensure_uri_handler():
    global _URI_HANDLER
    if _URI_HANDLER is None:
        module = _load_text_editor_module("text_editor.uri.core")
        _URI_HANDLER = getattr(module, "handle_uri_action", None)
        if _URI_HANDLER is None:
            raise RuntimeError("text_editor.uri.core.handle_uri_action not found")
    return _URI_HANDLER


def _ensure_file_handler(func_name: str):
    if func_name not in _FILE_HANDLERS:
        module = _load_text_editor_module("text_editor.file.core")
        _FILE_HANDLERS[func_name] = getattr(module, func_name, None)
        if _FILE_HANDLERS[func_name] is None:
            raise RuntimeError(f"text_editor.file.core.{func_name} not found")
    return _FILE_HANDLERS[func_name]


def _ensure_ail_handler(func_name: str):
    """Lazy-load AIL machine bridge handler.

    Loads text-editor/addon/ail-machine/bridge.py directly via importlib.util
    to bypass broken __init__.py chains in addon/ (ThrottlingPlugin import failure).
    """
    if func_name not in _AIL_HANDLERS:
        # Load bridge.py directly — directory is ail-machine (hyphen, not underscore)
        import importlib.util as _ilu
        bridge_path = "T:/hace/engine/hace/text-editor/addon/ail-machine/bridge.py"
        _module = None
        if Path(bridge_path).is_file():
            _spec = _ilu.spec_from_file_location("ail_machine_bridge", bridge_path)
            _module = _ilu.module_from_spec(_spec)
            sys.modules["ail_machine_bridge"] = _module
            _spec.loader.exec_module(_module)
        else:
            # Fallback: try through text_editor package
            try:
                _module = _load_text_editor_module("text_editor.addon.ail_machine.bridge")
            except Exception:
                _module = _load_text_editor_module("text_editor.addon.ail-machine.bridge")

        _AIL_HANDLERS[func_name] = getattr(_module, func_name, None) if _module else None
        if _AIL_HANDLERS[func_name] is None:
            raise RuntimeError(f"AIL machine bridge.{func_name} not found")
    return _AIL_HANDLERS[func_name]


# ─── Context Detection ────────────────────────────────────────────────────────

def _is_exec_context(obj) -> bool:
    """Check if object is an ExecContext instance."""
    return hasattr(obj, 'workspace_root') and hasattr(obj, 'actor_target')


# ─── Adapter Factories (no closures over importlib) ───────────────────────────

def _make_str_action_adapter(action: str) -> Callable:
    """Create adapter for text-editor str.* actions."""
    handler = _ensure_str_handler()
    action_name = action.split(".")[-1]  # e.g., "slug"
    
    def adapter(ctx_or_payload, **args) -> Dict[str, Any]:
        # Detect calling convention
        if _is_exec_context(ctx_or_payload):
            ctx = ctx_or_payload
            args_dict = args
        else:
            ctx = None
            args_dict = ctx_or_payload if isinstance(ctx_or_payload, dict) else {}
        
        payload = {
            "value": args_dict.get("value", ""),
            "separator": args_dict.get("separator", "-"),
            "delimiter": args_dict.get("delimiter", "_"),
            "limit": args_dict.get("limit", 100),
            "end": args_dict.get("end", "..."),
            "words": args_dict.get("words", 100),
            "needles": args_dict.get("needles", []),
            "ignore_case": args_dict.get("ignore_case", False),
            "search": args_dict.get("search", ""),
            "from_str": args_dict.get("from_str", ""),
            "to_str": args_dict.get("to_str", ""),
            "length": args_dict.get("length", 0),
            "pad": args_dict.get("pad", " "),
            "options": args_dict.get("options", {}),
        }
        
        # Call text-editor handler with its convention
        result = handler(
            action=f"str.{action_name}",
            payload=payload,
            headers=args_dict.get("headers"),
            context=args_dict.get("context"),
        )
        
        # Convert text-editor result format to executor-py format
        if isinstance(result, dict):
            if result.get("status") == "ERROR":
                from executor_py.core import ExecuteError
                raise ExecuteError(
                    code="FDI_EXEC_ERROR",
                    message=result.get("header", f"str.{action} failed"),
                )
            return {"result": result.get("result", result)}
        return {"result": result}
    
    adapter.__name__ = f"adapt_str_{action.replace('.', '_')}"
    adapter.__doc__ = f"Adapter for text-editor {action}"
    return adapter


def _make_uri_action_adapter(action: str) -> Callable:
    """Create adapter for text-editor uri.* actions."""
    handler = _ensure_uri_handler()
    action_name = action.split(".")[-1]
    
    def adapter(ctx_or_payload, **args) -> Dict[str, Any]:
        # Detect calling convention
        if _is_exec_context(ctx_or_payload):
            ctx = ctx_or_payload
            args_dict = args
        else:
            ctx = None
            args_dict = ctx_or_payload if isinstance(ctx_or_payload, dict) else {}
        
        payload = {
            "value": args_dict.get("value", ""),
            "encoding": args_dict.get("encoding", "utf-8"),
            "options": args_dict.get("options", {}),
        }
        
        # Workaround for text-editor URI handler bug (misroutes all actions to uri_to_path)
        # Use parse_uri with uri key to get parsed URI, then normalize
        action_name = action.split(".")[-1]
        uri_value = payload.get("value", "") or payload.get("uri", "")
        
        if action_name in ("normalize_uri", "parse_uri", "uri_to_path") and uri_value:
            # Use parse_uri to get parsed URI components
            result = handler(
                action="parse_uri",
                payload={"uri": uri_value},
                headers=args_dict.get("headers"),
                context=args_dict.get("context"),
            )
            
            # Extract URI from response (even if status is ERROR)
            if isinstance(result, dict) and result.get("uri"):
                normalized = result["uri"]
                # For normalize_uri, ensure lowercase canonical form
                if action_name == "normalize_uri":
                    normalized = normalized.lower()
                return {"result": normalized}
        
        # Fallback: call original action
        result = handler(
            action=action_name,
            payload=payload,
            headers=args_dict.get("headers"),
            context=args_dict.get("context"),
        )
        
        if isinstance(result, dict):
            if result.get("status") == "ERROR":
                from executor_py.core import ExecuteError
                raise ExecuteError(
                    code="FDI_EXEC_ERROR",
                    message=result.get("header", f"uri.{action} failed"),
                )
            return {"result": result.get("result", result)}
        return {"result": result}
    
    adapter.__name__ = f"adapt_uri_{action.replace('.', '_')}"
    adapter.__doc__ = f"Adapter for text-editor {action}"
    return adapter


def _make_file_action_adapter(action: str) -> Callable:
    """Create adapter for text-editor file.* actions."""
    func_name = action.split(".")[-1]
    handler = _ensure_file_handler(func_name)
    
    def adapter(ctx_or_payload, **args) -> Dict[str, Any]:
        if _is_exec_context(ctx_or_payload):
            ctx = ctx_or_payload
            args_dict = args
        else:
            ctx = None
            args_dict = ctx_or_payload if isinstance(ctx_or_payload, dict) else {}
        
        if action == "fdi.file.create_file":
            result = handler(
                path=args_dict.get("path", ""),
                content=args_dict.get("content", ""),
                mode=args_dict.get("mode", "replace"),
            )
        elif action == "fdi.file.read_file":
            result = handler(
                path=args_dict.get("path", ""),
                encoding=args_dict.get("encoding", "utf-8"),
            )
        elif action == "fdi.file.append_file":
            result = handler(
                path=args_dict.get("path", ""),
                content=args_dict.get("content", ""),
            )
        elif action == "fdi.file.delete_file":
            result = handler(path=args_dict.get("path", ""))
        elif action == "fdi.file.ensure_dir":
            result = handler(path=args_dict.get("path", ""))
        else:
            raise RuntimeError(f"Unhandled file action: {action}")
        
        if isinstance(result, dict) and result.get("status") == "ERROR":
            from executor_py.core import ExecuteError
            raise ExecuteError(
                code="FDI_EXEC_ERROR",
                message=result.get("header", f"file.{action} failed"),
            )

        # Handle FileResult objects — extract content string
        # FileResult may not have .content attribute (only path/telemetry)
        # So for read_file, we need to re-read if content not present
        if hasattr(result, 'content'):
            return {"result": result.content}
        elif hasattr(result, 'path') and action == "fdi.file.read_file":
            # FileResult doesn't store content — re-read the file
            try:
                from pathlib import Path
                filepath = getattr(result, 'path', args_dict.get("path", ""))
                if filepath:
                    content = Path(filepath).read_text(encoding="utf-8", errors="ignore")
                    return {"result": content}
            except Exception:
                pass
            # Fallback: return the str representation
            return {"result": str(result)}

        return {"result": result}
    
    adapter.__name__ = f"adapt_file_{action.replace('.', '_')}"
    adapter.__doc__ = f"Adapter for text-editor {action}"
    return adapter


def _make_ail_action_adapter(action: str) -> Callable:
    """Create adapter for AIL machine bridge actions.

    Maps actions to text-editor/addon/ail_machine/bridge.py functions:
    - ail.parse → ail_parse(raw_text)
    - ail.validate → ail_validate(raw_text)
    - ail.format_e164 → ail_format_e164(raw_text)
    - ail.slugify → ail_slugify(raw_text, separator)
    - ail.split_uri → ail_split_uri(raw_text)
    - ail.summary → ail_summary(raw_text)
    - ail.detect → ail_detect(raw_text)
    - ail.render → ail_render(raw_text)
    """
    # Extract function name: fdi.ail.parse -> ail_parse
    parts = action.split(".")
    if parts[-2] == "ail" and parts[-1] in ("parse", "validate", "render", "detect",
        "format_e164", "slugify", "split_uri", "summary"):
        func_name = f"ail_{parts[-1]}"
    else:
        func_name = parts[-1]

    handler = _ensure_ail_handler(func_name)

    def adapter(ctx_or_payload, **args) -> Dict[str, Any]:
        if _is_exec_context(ctx_or_payload):
            ctx = ctx_or_payload
            args_dict = args
        else:
            ctx = None
            args_dict = ctx_or_payload if isinstance(ctx_or_payload, dict) else {}

        value = args_dict.get("value", args_dict.get("raw_text", ""))

        if func_name == "ail_format_e164":
            result = handler(raw_text=value)
        elif func_name == "ail_slugify":
            result = handler(raw_text=value, separator=args_dict.get("separator", "-"))
        elif func_name in ("ail_split_uri", "ail_summary", "ail_detect",
                           "ail_parse", "ail_validate"):
            result = handler(raw_text=value)
        elif func_name == "ail_render":
            result = handler(pipeline=None, raw_text=value)
        else:
            raise RuntimeError(f"Unhandled AIL action: {action}")

        # Unwrap result — some handlers return dicts, some return strings
        if isinstance(result, dict) and "result" in result:
            return {"result": result}
        return {"result": result}

    adapter.__name__ = f"adapt_ail_{action.replace('.', '_')}"
    adapter.__doc__ = f"Adapter for text-editor AIL bridge {action}"
    return adapter


# ─── Registry ────────────────────────────────────────────────────────────────

# Persistent registry (survives module reload)
def _get_registry():
    if not hasattr(_get_registry, '_registry'):
        _get_registry._registry = {}
    return _get_registry._registry


def _register_adapters():
    """Register all adapters for text-editor capabilities."""
    registry = _get_registry()
    if registry:
        return  # Already registered
    
    # Str actions
    str_actions = [
        "fdi.str.headline", "fdi.str.slug", "fdi.str.snake", "fdi.str.kebab",
        "fdi.str.camel", "fdi.str.studly", "fdi.str.limit", "fdi.str.words",
        "fdi.str.squish", "fdi.str.contains", "fdi.str.starts_with",
        "fdi.str.ends_with", "fdi.str.before", "fdi.str.after",
        "fdi.str.between", "fdi.str.pad_left", "fdi.str.pad_right",
    ]
    for action in str_actions:
        registry[action] = _make_str_action_adapter(action)
    
    # URI actions
    uri_actions = [
        "fdi.uri.normalize_uri", "fdi.uri.parse_uri", "fdi.uri.uri_to_path",
        "fdi.uri.path_to_uri", "fdi.uri.is_safe_uri", "fdi.uri.resolve_uri",
    ]
    for action in uri_actions:
        registry[action] = _make_uri_action_adapter(action)
    
    # File actions
    file_actions = [
        "fdi.file.create_file", "fdi.file.read_file", "fdi.file.append_file",
        "fdi.file.delete_file", "fdi.file.ensure_dir",
    ]
    for action in file_actions:
        registry[action] = _make_file_action_adapter(action)
    
    # AIL actions (bridge from text-editor/addon/ail_machine/bridge.py)
    ail_actions = [
        "fdi.str.ail_format_e164", "fdi.str.ail_slugify",
        "fdi.str.ail_split_uri", "fdi.str.ail_summary",
        "fdi.ail.parse", "fdi.ail.validate", "fdi.ail.render", "fdi.ail.detect",
        "fdi.ail.format_e164", "fdi.ail.slugify",
        "fdi.ail.split_uri", "fdi.ail.summary",
    ]
    for action in ail_actions:
        registry[action] = _make_ail_action_adapter(action)


def get_adapter(capability: str) -> Optional[Callable]:
    """Get adapter for a capability, creating it if needed."""
    registry = _get_registry()
    if not registry:
        _register_adapters()
    return registry.get(capability)


def list_adapters() -> list[str]:
    """List all registered adapter capabilities."""
    registry = _get_registry()
    if not registry:
        _register_adapters()
    return list(registry.keys())


__all__ = [
    "get_adapter",
    "list_adapters",
]