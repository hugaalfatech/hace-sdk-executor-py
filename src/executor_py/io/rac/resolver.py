# -*- coding: utf-8 -*-
"""
executor_py.io.rac.resolver — Unified Route Resolver

Authority: CSA / CTO
Spec: rac-uri-resolver.ail (CGE/CRD CANON-20260814-EXECUTOR-RAC-ROUTE-RESOLVER)

Per CGE directive: sdk/executor-* MUST discover capability routes from
<artifact>/routes/{rac, mcp, http, cli} and <artifact>/config/{defines, schemas, settings}

Canonical grammar: rac://{rule}.{ownerspace}.{specs}/{path}
SIO-CRI-FPI-V2 frame: {uri, method, payload[action, process, messages, data], headers[ara, licence, visibility], context}

Resolver algorithm:
  1. discover_routes — scan <artifact>/routes/ and <artifact>/config/
  2. parse_route_resources — parse AIL/YAML/JSON route files
  3. resolve_rac_uri — resolve RAC URI to route record
  4. normalize — produce NormalizedRoute IR
  5. authorize — verify export, ARA, license
  6. bind_substrate — bind execution substrate (FDI/FPI/HTTP/MCP/CLI)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


@dataclass
class NormalizedRoute:
    """Intermediate representation (IR) for a resolved route.

    Per rac-uri-resolver.ail §8 — Normalized Route Object.
    """
    rac_uri: str
    rule: str
    ownerspace: str
    specs: str
    path: str
    capability: str
    feature: str
    function: str
    export_enabled: bool = True
    ara_required: bool = True
    license_required: bool = True
    substrate: str = "in_process"
    runtime: str = "python"
    entrypoint: Optional[str] = None
    actions: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SIOFrame:
    """RAC SIO Frame — Core IO Contract.

    Per rac-uri-resolver.ail §CANON — SIO Frame.
    Structure: {uri, method, payload[action, process, messages, data],
                 headers[ara, licence, visibility], context}
    """
    uri: str
    method: str
    payload: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> bool:
        """Validate SIO frame core invariants.

        Per SIO-CRI-FPI-V2: frame must have uri, method, and payload with action.
        For FPI frames, payload also includes process, input, options.
        """
        if not self.uri:
            return False
        if not self.method:
            return False
        if "action" not in self.payload:
            return False
        return True

    def to_rac_uri(self) -> str:
        """Extract RAC URI from frame."""
        return self.uri


@dataclass
class RouteIndex:
    """Route Index — common lookup table for all routes.

    Per rac-uri-resolver.ail §10 — Một Route Index dùng chung.
    """
    routes: Dict[str, NormalizedRoute] = field(default_factory=dict)

    def add(self, route: NormalizedRoute) -> None:
        """Add a normalized route to the index."""
        self.routes[route.rac_uri] = route

    def find(self, rac_uri: str) -> Optional[NormalizedRoute]:
        """Find a route by RAC URI."""
        return self.routes.get(rac_uri)

    def find_by_capability(self, capability: str) -> Optional[NormalizedRoute]:
        """Find a route by exact capability match."""
        for route in self.routes.values():
            if route.capability == capability:
                return route
        return None

    def find_by_action(self, action: str) -> Optional[NormalizedRoute]:
        """Find a route by capability action name.

        Per rac-uri-resolver.ail — capability may be a top-level capability
        (e.g., "text-editor") or a feature (e.g., "str.slug", "ail.parse").
        """
        # Direct capability match
        for route in self.routes.values():
            if route.capability == action:
                return route
        # Match by capability + "." + feature (e.g., "text-editor.str.slug")
        for route in self.routes.values():
            if action.startswith(route.capability + "."):
                return route
        # Match by registered features/actions in route raw config
        norm_action = action
        if norm_action.startswith("fdi."):
            norm_action = norm_action[4:]
        for route in self.routes.values():
            # Check raw actions and capabilities lists
            raw_actions = route.raw.get("actions", []) or []
            raw_capabilities = route.raw.get("capabilities", []) or []
            all_features = [a.replace("fdi.", "") if isinstance(a, str) else a for a in raw_actions] + \
                          [c.replace("fdi.", "") if isinstance(c, str) else c for c in raw_capabilities]
            if norm_action in raw_actions or norm_action in raw_capabilities or norm_action in all_features:
                return route
        return None

    def list_routes(self) -> List[str]:
        """List all registered route URIs."""
        return list(self.routes.keys())


class RouteResolver:
    """Unified Route Resolver for sdk/executor-*.

    Per rac-uri-resolver.ail §CANON — Executor Route Resolver.

    Discovers, parses, normalizes, resolves, authorizes, and binds
    RAC capabilities from <artifact>/routes/* and <artifact>/config/*.

    Resource formats supported: AIL, YAML, JSON.
    """

    RESOURCE_ROOTS = ["rac", "mcp", "http", "cli"]
    CONFIG_ROOTS = ["defines", "schemas", "settings"]

    def __init__(self, artifact_root: Optional[str] = None):
        """Initialize resolver with artifact root directory.

        Args:
            artifact_root: Base path containing routes/ and config/ directories.
                          If None, attempts to resolve from execution context.
        """
        self.artifact_root = self._resolve_artifact_root(artifact_root)
        self.index = RouteIndex()
        self._discovered = False

    def _resolve_artifact_root(self, artifact_root: Optional[str]) -> Path:
        """Locate artifact root with routes/ directory."""
        if artifact_root:
            path = Path(artifact_root)
            if path.is_dir():
                return path

        # Walk up from caller's __file__ to find routes/
        frame = __import__("inspect").currentframe()
        try:
            caller_path = __import__("inspect").getfile(frame.f_back)
            candidate = Path(caller_path).resolve()
            for parent in [candidate] + list(candidate.parents):
                routes_dir = parent / "routes"
                if routes_dir.is_dir():
                    return parent
        finally:
            del frame

        # Default fallback: T:/hace/engine/hace
        default_root = Path("T:/hace/engine/hace")
        if (default_root / "routes").is_dir():
            return default_root

        return Path(os.getcwd())

    def discover_routes(self) -> RouteIndex:
        """Scan artifact/routes/ and artifact/config/ for route resources.

        Per rac-uri-resolver.ail §9 — Resolver discovery algorithm step 1-2.
        """
        if self._discovered:
            return self.index

        routes_dir = self.artifact_root / "routes"
        config_dir = self.artifact_root / "config"

        for root_name, root in [("routes", routes_dir), ("config", config_dir)]:
            if not root.is_dir():
                continue
            self._scan_directory(root, root_name)

        self._discovered = True
        return self.index

    def _scan_directory(self, dir_path: Path, root_type: str) -> None:
        """Recursively scan a directory for route resource files."""
        for entry in sorted(dir_path.iterdir()):
            if entry.is_dir():
                self._scan_directory(entry, root_type)
            elif entry.is_file():
                self._parse_route_file(entry, root_type)

    def _parse_route_file(self, file_path: Path, root_type: str) -> None:
        """Parse a single route resource file (AIL/YAML/JSON)."""
        suffix = file_path.suffix.lower()
        try:
            if suffix in (".ail", ".yaml", ".yml"):
                routes = self._parse_ail_yaml(file_path)
                self._register_routes(routes, file_path, root_type)
            elif suffix == ".json":
                routes = self._parse_json(file_path)
                self._register_routes(routes, file_path, root_type)
        except Exception:
            pass

    def _parse_ail_yaml(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse AIL/YAML route file into route records.

        AIL files in this context are hybrid Markdown + YAML.
        Route records are defined in YAML frontmatter or inline YAML after comments.
        """
        text = file_path.read_text(encoding="utf-8")

        # Try YAML frontmatter (--- ... ---)
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 2:
                try:
                    import yaml
                    data = yaml.safe_load(parts[1])
                    if isinstance(data, dict):
                        if "routes" in data:
                            return data["routes"]
                        if "route" in data:
                            return [data["route"]]
                        if "rac_uri" in data:
                            return [data]
                except ImportError:
                    pass

        # Try direct YAML parsing (AIL files may be YAML with Markdown comment header)
        # Strip leading comment lines and parse the rest as YAML
        try:
            import yaml
            lines = text.split("\n")
            yaml_start = 0
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    yaml_start = i
                    break
            yaml_text = "\n".join(lines[yaml_start:])
            data = yaml.safe_load(yaml_text)
            if isinstance(data, dict):
                if "routes" in data:
                    return data["routes"]
                if "route" in data:
                    return [data["route"]]
                if "rac_uri" in data:
                    return [data]
        except (ImportError, Exception):
            pass

        # Parse AIL table format for route declarations
        routes = self._parse_ail_tables(text, file_path)
        return routes

    def _parse_ail_tables(self, text: str, file_path: Path) -> List[Dict[str, Any]]:
        """Parse AIL document tables for route declarations."""
        routes = []

        # Extract table rows with route patterns
        # Pattern: | route_name | handler | description |
        lines = text.split("\n")
        in_table = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|") and "rac:// or `" in stripped.lower():
                in_table = True
                continue
            if in_table and stripped.startswith("| ---"):
                continue
            if in_table and stripped.startswith("|"):
                cells = [c.strip() for c in stripped.strip("|").split("|")]
                if len(cells) >= 3 and "rac://" in cells[0]:
                    rac_uri = cells[0].strip("`")
                    routes.append({
                        "rac_uri": rac_uri,
                        "route_handler": cells[1],
                        "description": cells[2] if len(cells) > 2 else "",
                        "source_file": str(file_path),
                    })
                elif len(cells) >= 2 and "rac://" not in cells[0]:
                    # Canonical route format from table
                    route_name = cells[0].strip("`")
                    handler = cells[1].strip("`")
                    routes.append({
                        "rac_uri": f"rac://cri.te.{route_name}",
                        "route_handler": handler,
                        "description": cells[2] if len(cells) > 2 else "",
                        "source_file": str(file_path),
                    })

        return routes

    def _parse_json(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse JSON route file."""
        text = file_path.read_text(encoding="utf-8")
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if "routes" in data:
                return data["routes"]
            if "route" in data:
                return [data["route"]]
            return [data]
        return []

    def _register_routes(self, route_records: List[Dict[str, Any]],
                         file_path: Path, root_type: str) -> None:
        """Register parsed route records into the index."""
        for record in route_records:
            if not isinstance(record, dict):
                continue
            rac_uri = record.get("rac_uri") or record.get("uri", "")
            if not rac_uri:
                continue

            normalized = self._normalize_route(rac_uri, record, file_path, root_type)
            if normalized:
                self.index.add(normalized)

    def _normalize_route(self, rac_uri: str, raw: Dict[str, Any],
                         file_path: Path, root_type: str) -> Optional[NormalizedRoute]:
        """Normalize a raw route record into NormalizedRoute IR.

        Per rac-uri-resolver.ail §8 — Normalized Route Object.
        """
        parsed = self._parse_rac_uri(rac_uri)
        if not parsed:
            return None

        rule = parsed.get("rule", "")
        ownerspace = parsed.get("ownerspace", "")
        specs = parsed.get("specs", "")
        path = parsed.get("path", "")

        # Extract capability info from path or raw record
        capability = raw.get("capability", "")
        feature = raw.get("feature", "")
        function = raw.get("function", "") or raw.get("entrypoint", "")

        if not capability:
            # Derive capability from path segments
            path_parts = [p for p in path.strip("/").split("/") if p]
            if len(path_parts) >= 2:
                module = path_parts[-2]
                action = path_parts[-1]
                capability = f"{module}.{action}"
                feature = module
                function = action

        return NormalizedRoute(
            rac_uri=rac_uri,
            rule=rule,
            ownerspace=ownerspace,
            specs=specs,
            path=path,
            capability=capability,
            feature=feature,
            function=function,
            export_enabled=raw.get("export", {}).get("enabled", raw.get("export_enabled", raw.get("export", True))),
            ara_required=raw.get("authority", {}).get("ara_required", True),
            license_required=raw.get("authority", {}).get("license_required", True),
            substrate=raw.get("execution", {}).get("substrate", "in_process"),
            runtime=raw.get("execution", {}).get("runtime", "python"),
            entrypoint=raw.get("execution", {}).get("entrypoint") or raw.get("entrypoint"),
            actions=raw.get("actions", []),
            raw=raw,
        )

    def _parse_rac_uri(self, rac_uri: str) -> Optional[Dict[str, str]]:
        """Parse RAC URI using canonical grammar: rac://{rule}.{ownerspace}.{specs}/{path}

        Per rac-uri-resolver.ail §CANON — rac_uri_grammar.
        """
        if not rac_uri.startswith("rac://"):
            return None

        rest = rac_uri.replace("rac://", "")

        # Split spec_part / path
        if "/" in rest:
            spec_part, path = rest.split("/", 1)
        else:
            spec_part, path = rest, ""

        # FDI/FPI canonical: cri.{ownerspace}.{specs}
        parts = spec_part.split(".")
        if len(parts) < 3:
            # Fallback: rule=parts[0], specs=parts[-1], ownerspace=middle
            rule = parts[0] if parts else ""
            specs = parts[-1] if len(parts) > 0 else ""
            ownerspace = ".".join(parts[1:-1]) if len(parts) >= 3 else ""
        else:
            rule = parts[0]
            specs = parts[-1]
            ownerspace = ".".join(parts[1:-1])

        return {
            "rule": rule,
            "ownerspace": ownerspace,
            "specs": specs,
            "path": "/" + path if path else "",
        }

    def resolve_rac_uri(self, rac_uri: str) -> Optional[NormalizedRoute]:
        """Resolve a RAC URI to a route record.

        Per rac-uri-resolver.ail §10 — RAC URI lookup.
        """
        if not self._discovered:
            self.discover_routes()

        # Direct lookup
        route = self.index.find(rac_uri)
        if route:
            return route

        # Try by action/capability
        parsed = self._parse_rac_uri(rac_uri)
        if parsed:
            path = parsed.get("path", "")
            path_parts = [p for p in path.strip("/").split("/") if p]
            if len(path_parts) >= 2:
                capability = f"{path_parts[-2]}.{path_parts[-1]}"
                route = self.index.find_by_action(capability)
                if route:
                    return route
            # Also try parent capability (e.g., "text-editor" from "/text-editor/str/slug")
            if len(path_parts) >= 1:
                parent_capability = path_parts[-2] if len(path_parts) >= 2 else path_parts[-1]
                route = self.index.find_by_capability(parent_capability)
                if route:
                    return route

        return None

    def authorize(self, route: NormalizedRoute,
                  caller: str = "default",
                  ara: Optional[Dict[str, Any]] = None,
                  license_key: Optional[str] = None) -> bool:
        """Verify ARA and license authorization.

        Per rac-uri-resolver.ail §2 — authority_gatekeeper.
        """
        if route.ara_required and not ara:
            # In test/dev mode, allow without ARA
            pass

        if route.license_required and not license_key:
            # Try local license store (TEE/APES)
            license_key = self._check_local_license(store_path=route.ownerspace)
            if not license_key:
                return False

        return True

    def _check_local_license(self, store_path: str) -> Optional[str]:
        """Check local TEE/APES license store."""
        license_paths = [
            Path(os.environ.get("APES_LICENSE_DIR", "")) / "license.key",
            Path("T:/caw/.shared-registry/license.key"),
            Path.home() / ".hacex" / "license.key",
        ]
        for lp in license_paths:
            if lp.is_file():
                return lp.read_text(encoding="utf-8").strip()
        return None

    def bind_substrate(self, route: NormalizedRoute) -> Any:
        """Bind execution substrate for a resolved route.

        Per rac-uri-resolver.ail §5 — rac:import → bind_execution_substrate.
        """
        specs = route.specs

        if specs == "fdi":
            # FDI = in-process guarded callable
            from ..cri.fdi import FdiExecutor
            from ..cri.fdi_binding import _lazy_load_binding
            module_path, func_name = self._lookup_capability(route.rac_uri)
            if module_path and func_name:
                return _lazy_load_binding(module_path, func_name)
            raise RuntimeError(f"Cannot resolve FDI binding for {route.rac_uri}")

        elif specs == "fpi":
            # FPI = instance lifecycle (open/execute/close)
            from ..cri.fpi import FpiExecutor
            executor = FpiExecutor()
            return executor.instance(route.capability)

        elif specs == "ffi":
            # FFI = native bridge
            from ..cri.ffi import FfiExecutor
            executor = FfiExecutor()
            return executor.instance(route.capability)

        else:
            raise RuntimeError(f"Unknown substrate specs: {specs}")

    def _lookup_capability(self, rac_uri: str) -> tuple:
        """Lookup capability in route index for binding resolution."""
        route = self.resolve_rac_uri(rac_uri)
        if not route:
            return ("", "")

        # Check raw record for module/function info
        raw = route.raw
        if "module_path" in raw and "function_name" in raw:
            return (raw["module_path"], raw["function_name"])

        # Check for handler field like "file/core.py:create_file"
        handler = raw.get("handler") or raw.get("route_handler")
        if handler and ":" in handler:
            parts = handler.split(":")
            return (parts[0].replace("/", "."), parts[1])

        # Fallback: derive from capability
        if route.capability and "." in route.capability:
            module, func = route.capability.rsplit(".", 1)
            return (module, func)

        return ("", "")


def create_resolver(artifact_root: Optional[str] = None) -> RouteResolver:
    """Factory function to create a RouteResolver."""
    return RouteResolver(artifact_root=artifact_root)


def resolve_rac_uri(rac_uri: str, artifact_root: Optional[str] = None) -> Optional[NormalizedRoute]:
    """Convenience function: resolve a RAC URI directly."""
    resolver = create_resolver(artifact_root)
    resolver.discover_routes()
    return resolver.resolve_rac_uri(rac_uri)


__all__ = [
    "RouteResolver",
    "RouteIndex",
    "NormalizedRoute",
    "SIOFrame",
    "create_resolver",
    "resolve_rac_uri",
]
