# -*- coding: utf-8 -*-
"""Fix the corrupted fdi.py by reconstructing the broken section."""

fp = 'src/executor_py/io/rac/cri/fdi.py'
with open(fp, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the start of the corruption: the 'resolve_fdi_module' section marker
start = None
for i, line in enumerate(lines):
    if '# --- Module resolution' in line:
        start = i
        break

if start is None:
    print('Could not find module resolution marker')
    exit(1)

# Find the end: the '__all__' section
end = None
for i in range(start, len(lines)):
    if '__all__' in lines[i]:
        end = i
        break

if end is None:
    print('Could not find __all__ section')
    exit(1)

# Build the correct replacement section
replacement = '''    # ─── Module resolution ───────────────────────────┍

    def resolve_fdi_module(self, module_path: str) -> Any:
        """Resolve and load a Python module from an FDI path.

        This is the autoload mechanism: given a path like
        'io/rac/cri/file', resolve to the actual module.
        """
        exec_dir = Path(__file__).resolve().parents[6]  # fdi.py -> executor_py/

        # Try as package path
        pkg_path = exec_dir / module_path.replace("/", ".")
        try:
            return importlib.import_module(f"executor_py.{module_path.replace('/', '.')}")
        except ImportError:
            pass

        # Try as file path
        py_path = exec_dir / module_path.replace("/", os.sep) / "core.py"
        if py_path.exists():
            spec = importlib.util.spec_from_file_location(module_path, py_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod

        return None

    def _capability_to_rac_uri(self, capability: str) -> str:
        """Convert an FDI capability identifier to a RAC URI.

        Per rac-uri-resolver.ail §1 — RAC URI grammar:
        rac://{rule}.{ownerspace}.{specs}/{path}
        """
        parts = capability.split(".")
        if len(parts) >= 3 and parts[0] == "fdi":
            module = parts[1]
            action = parts[2]
            path = f"{module}/{action}" if action else module
            return f"rac://cri.te.fdi/{path}"
        return f"rac://cri.te.fdi/{capability.replace('.', '/')}"

    # ─── rac:import binding (FDI facade) ───────────────────────────────────────────┍

    def import_binding(self, capability: str) -> Callable:
        """Import a capability binding via FDI (rac:import).

        Per rac-uri-resolver.ail §5: rac:import → resolve_rac_uri →
        verify_export → verify_ara/license → bind_execution_substrate.

        Resolution order:
        1. RouteResolver (canonical: discover from <artifact>/routes/*)
        2. Text-editor FDI facade (rac_fdi_in.import_binding)
        3. Local _FDI_CAPABILITY_MAP fallback

        Args:
            capability: FDI capability identifier (e.g., "fdi.str.snake")
                        or full RAC URI (e.g., "rac://cri.hace.fdi/text-editor/str/snake")

        Returns:
            Bound callable ready for direct invocation
        """
        # 1. Try RouteResolver — canonical discovery from <artifact>/routes/*
        try:
            from ...resolver import RouteResolver
            resolver = RouteResolver()
            resolver.discover_routes()
            rac_uri = capability if capability.startswith("rac://") else self._capability_to_rac_uri(capability)
            route = resolver.resolve_rac_uri(rac_uri)
            if route and route.export_enabled:
                module_path, func_name = resolver._lookup_capability(rac_uri)
                if module_path and func_name:
                    return _lazy_load_binding(module_path, func_name)
        except Exception:
            pass
        # 2. Bridge to text-editor's FDI facade
        try:
            from text_editor.io.rac.cri.fdi import rac_fdi_in
            return rac_fdi_in.import_binding(capability)
        except ImportError:
            pass
        # 3. Fallback: local capability map
        module_path, func_name = _FDI_CAPABILITY_MAP.get(capability, ("", ""))
        if module_path and func_name:
            return _lazy_load_binding(module_path, func_name)
        raise ExecuteError(
            code="FDI_IMPORT_FAILED",
            message=f"Cannot import capability: {capability}",
        )


def resolve_fdi_target(rac_uri: str) -> dict:
    """Resolve an FDI RAC URI to target dimensions.

    Mirrors resolve_target() in racor.rs.

    Example:
        rac://cri.platform.hace.fdi/hace/executor-py/io/rac/cri/file
        -> {rule: "cri", ownerspace: "platform.hace", specs: "fdi", ...}
    """
    # Strip rac://
    rest = rac_uri.replace("rac://", "")

    # Split spec_part / path
    if "/" in rest:
        spec_part, path = rest.split("/", 1)
    else:
        spec_part, path = rest, ""

    # FDI canonical: cri.{ownerspace}.{specs}
    parts = spec_part.split(".")
    rule = parts[0] if parts else ""
    specs = parts[-1] if len(parts) > 0 else ""
    ownerspace = ".".join(parts[1:-1]) if len(parts) >= 3 else ""

    return {
        "rule": rule,
        "ownerspace": ownerspace,
        "specs": specs,
        "path": path,
        "transport": "ffi",           # FDI = FFI (in-process)
        "machine": "hace-lion-machine",  # Local native machine
        "transport_kind": "Fdi",
        "is_wired": True,             # FDI = wired
        "is_autoload": True,
    }


def resolve_fdi_uri(rac_uri: str) -> dict:
    """Resolve FDI URI (alias for resolve_fdi_target)."""
    return resolve_fdi_target(rac_uri)


def create_fdi_executor(uri: str = "") -> FdiExecutor:
    """Create a new FDI executor with autoload transport."""
    transport = FdiTransport(uri=uri, method=FdiMethod.FILE)
    executor = FdiExecutor()
    executor.transport = transport
    return executor


# Register FDI in global DNA registry
'''

# Find the __all__ line to insert before it
lines = lines[:start] + [replacement] + lines[end:]
content = ''.join(lines)

with open(fp, 'w', encoding='utf-8') as f:
    f.write(content)

print('FDI fixed successfully')
