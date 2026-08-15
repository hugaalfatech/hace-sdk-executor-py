# -*- coding: utf-8 -*-
"""
ROTA Test — RAC CRI Bidirectional Flow (FDI ↔ FPI)

Verifies canonical CRI flows between text-editor (FDI) and ail-machine (FPI):

1. text-editor → ail-machine: FDI import_binding with zero-payload, TTLV execution
2. ail-machine → text-editor: FPI instance lifecycle (init → running → finalize → terminated)

Per CGE Canon AUD-20260814-FPI-VS-FFI-CANON:
- FDI (File Descriptor I/O) = wired transport (NOT FFI)
- FPI (Function Process Instance) = stateful lifecycle entity (NOT wireless)
- FFI (Foreign Function Interface) = low-level C-ABI binding mechanism (under the hood)

Per cri-fpi-instance.ail §7 invariants:
- RAC URI identifies Actor, not implementation
- action.feature identifies executable capability
- process identifies FPI lifecycle
- input carries execution data
- routes contain declarations, never implementation code
- executor implementation is resolved from dist
- cross_layer_import is forbidden
"""

import pytest
import sys
from pathlib import Path

from executor_py.core import (
    ExecContext,
    ExecInput,
    ExecOutput,
    SioStatus,
    SepiProof,
    FanId,
    ExecuteError,
)


# ─── Canonical AIL content for testing FPI flows ─────────────────────────────

AIL_TEST_CONTENT = """---
schema: test
version: "1.0"
namespace: test
---
# Test Document

```yaml info=execute
action: test
```
"""


# ─── Test 1: text-editor → ail-machine via FDI ───────────────────────────────

class TestRACCRIFDITextEditorToAilMachine:
    """Test FDI import flow: ail-machine uses text-editor FDI via executor-py."""

    def test_fdi_import_str_slug_via_executor_py(self):
        """ail-machine imports text-editor str.slug capability via executor-py FdiExecutor."""
        from executor_py.io.rac.cri.fdi import FdiExecutor, FdiActorAlias

        executor = FdiExecutor()

        # rac:import — zero-payload binding returns actor alias
        text_editor = executor.import_binding("fdi.str.slug", "text_editor")

        assert isinstance(text_editor, FdiActorAlias)

        # rac:call — execute with TTLV payload
        result = text_editor.fdi.str.slug({"args": {"value": "Hello World Test"}})

        assert result["result"] == "hello-world-test"  # slug = kebab-case per text-editor

    def test_fdi_import_str_snake_via_executor_py(self):
        """ail-machine imports text-editor str.snake capability via executor-py."""
        from executor_py.io.rac.cri.fdi import FdiExecutor

        executor = FdiExecutor()

        text_editor = executor.import_binding("fdi.str.snake", "text_editor")
        result = text_editor.fdi.str.snake({"args": {"value": "Hello World Test"}})

        # snake uses underscore delimiter; verify underscores present
        assert "_" in result["result"]

    def test_fdi_import_uri_normalize_via_executor_py(self):
        """ail-machine imports text-editor uri.normalize_uri capability via executor-py."""
        from executor_py.io.rac.cri.fdi import FdiExecutor

        executor = FdiExecutor()

        text_editor = executor.import_binding("fdi.uri.normalize_uri", "text_editor")
        uri = text_editor.fdi.uri.normalize_uri({"args": {"value": "RAC://CRI.HACE.FDI/TEXT-EDITOR"}})

        assert uri["result"] == "rac://cri.hace.fdi/text-editor"

    def test_fdi_import_file_read_via_executor_py(self):
        """ail-machine imports text-editor file.read_file capability via executor-py."""
        from executor_py.io.rac.cri.fdi import FdiExecutor
        import tempfile

        executor = FdiExecutor()
        text_editor = executor.import_binding("fdi.file.read_file", "text_editor")

        # Create temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Hello AIL Machine")
            temp_path = f.name

        result = text_editor.fdi.file.read_file({"args": {"path": temp_path}})

        assert result["result"] == "Hello AIL Machine"

        # Cleanup
        Path(temp_path).unlink(missing_ok=True)

    def test_fdi_invoke_with_sio_frame(self):
        """ail-machine invokes FDI with canonical SIOFrame via executor execute."""
        from executor_py.io.rac.cri.fdi import FdiExecutor

        executor = FdiExecutor()

        ctx = ExecContext(
            workspace_root="/workspace",
            actor_target="text-editor",
        )
        exec_input = ExecInput(
            action="fdi.str.slug",
            payload={"value": "Test String"},
            headers={
                "ara": "ara:test:valid",
                "licence": "lic:test:valid",
                "visibility": "restricted",
            },
            context={"workspace_root": "/workspace", "actor_target": "text-editor"},
        )

        result = executor.execute(exec_input, ctx)

        assert result.status.value == "success"
        assert "result" in result.result
        assert result.result["result"] == "test-string"


# ─── Test 2: executor-py delegates to text-editor via adapter registry ────────

class TestRACCRIFDITextEditorFacade:
    """Test FDI flow: executor-py delegates to text-editor capabilities via adapters.

    Per CGE Canon: executor-py does NOT import text-editor directly at module level.
    All text-editor access is via lazy bootstrap + adapter delegation.
    """

    def _bootstrap_text_editor(self):
        """Bootstrap text-editor as a proper package with __path__."""
        import importlib.util as _ilu
        if "text_editor" not in sys.modules:
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
        return sys.modules["text_editor"]

    def test_text_editor_fdi_import_via_executor_py(self):
        """text-editor FDI capabilities accessible via executor-py FdiExecutor adapter."""
        from executor_py.io.rac.cri.fdi import FdiExecutor, FdiActorAlias

        executor = FdiExecutor()
        handler = executor.import_binding("fdi.str.slug", "text_editor")

        # Verify it returns an actor alias, not raw callable
        assert isinstance(handler, FdiActorAlias)

        result = handler.fdi.str.slug({"args": {"value": "Text Editor Slug"}})
        assert "result" in result
        assert result["result"] == "text-editor-slug"  # kebab-case per text-editor

    def test_text_editor_fdi_invoke_via_executor_py(self):
        """text-editor fdi capabilities invoke through executor-py FdiExecutor.execute."""
        from executor_py.io.rac.cri.fdi import FdiExecutor

        executor = FdiExecutor()
        ctx = ExecContext(workspace_root="/workspace", actor_target="text-editor")
        exec_input = ExecInput(
            action="fdi.str.camel",
            payload={"value": "hello world"},
        )

        result = executor.execute(exec_input, ctx)
        assert result.result["result"] == "helloWorld"

    def test_text_editor_fdi_resolve_rac_uri(self):
        """Resolve text-editor FDI routes via RouteResolver."""
        from executor_py.io.rac.resolver import RouteResolver

        resolver = RouteResolver()
        resolver.discover_routes()

        route = resolver.resolve_rac_uri("rac://cri.hace.fdi/text-editor/str/slug")

        assert route is not None
        assert route.specs == "fdi"
        assert route.export_enabled is True


# ─── Test 3: ail-machine → text-editor via FPI ────────────────────────────────

class TestRACCRIFPIAilMachineToTextEditor:
    """Test FPI flow: text-editor calls ail-machine FPI instance via executor-py"""

    def test_fpi_instance_open_ail_machine(self):
        """text-editor opens FPI instance to ail-machine via executor-py"""
        from executor_py.io.rac.cri.fpi import FpiExecutor

        executor = FpiExecutor()
        instance = executor.instance("fpi.ail.machine", endpoint="fpi://ail-machine")

        assert instance is not None
        assert instance.is_open
        assert instance.capability == "fpi.ail.machine"

    def test_fpi_instance_execute_ail_parse(self):
        """text-editor executes ail.parse on ail-machine FPI instance"""
        from executor_py.io.rac.cri.fpi import FpiExecutor

        executor = FpiExecutor()
        instance = executor.instance("fpi.ail.machine", endpoint="fpi://ail-machine")

        result = instance.execute("ail.parse", {"raw_text": AIL_TEST_CONTENT})

        assert "result" in result
        assert result["result"]["status"] == "success"

    def test_fpi_instance_execute_ail_validate(self):
        """text-editor executes ail.validate on ail-machine FPI instance"""
        from executor_py.io.rac.cri.fpi import FpiExecutor

        executor = FpiExecutor()
        instance = executor.instance("fpi.ail.machine", endpoint="fpi://ail-machine")

        result = instance.execute("ail.validate", {"raw_text": AIL_TEST_CONTENT})

        assert "result" in result
        assert result["result"]["status"] == "success"

    def test_fpi_instance_execute_ail_slugify(self):
        """text-editor executes ail.slugify on ail-machine FPI instance"""
        from executor_py.io.rac.cri.fpi import FpiExecutor

        executor = FpiExecutor()
        instance = executor.instance("fpi.ail.machine", endpoint="fpi://ail-machine")

        result = instance.execute("ail.slugify", {"raw_text": "My Schema Name"})

        assert "result" in result
        assert result["result"]["status"] == "success"

    def test_fpi_instance_execute_ail_format_e164(self):
        """text-editor executes ail.format_e164 on ail-machine FPI instance"""
        from executor_py.io.rac.cri.fpi import FpiExecutor

        executor = FpiExecutor()
        instance = executor.instance("fpi.ail.machine", endpoint="fpi://ail-machine")

        result = instance.execute("ail.format_e164", {"raw_text": "0909123456"})

        assert "result" in result
        assert result["result"]["status"] == "success"

    def test_fpi_instance_close(self):
        """text-editor closes ail-machine FPI instance"""
        from executor_py.io.rac.cri.fpi import FpiExecutor

        executor = FpiExecutor()
        instance = executor.instance("fpi.ail.machine", endpoint="fpi://ail-machine")

        assert instance.is_open

        result = instance.close()
        assert result["closed"] is True
        assert not instance.is_open


# ─── Test 4: Integration — full bidirectional roundtrip ────────────────────────

class TestRACCRIBidirectionalIntegration:
    """Test full bidirectional FDI ↔ FPI roundtrip"""

    def test_ail_machine_uses_text_editor_fdi(self):
        """ail-machine uses text-editor FDI capabilities via executor-py"""
        from executor_py.io.rac.cri.fdi import FdiExecutor

        executor = FdiExecutor()

        # AIL machine needs to slugify schema names
        text_editor = executor.import_binding("fdi.str.slug", "text_editor")
        slug = text_editor.fdi.str.slug({"args": {"value": "My Test Schema"}})
        assert slug["result"] == "my-test-schema"  # kebab-case per text-editor

        # AIL machine needs to normalize URIs
        text_editor = executor.import_binding("fdi.uri.normalize_uri", "text_editor")
        uri = text_editor.fdi.uri.normalize_uri({"args": {"value": "RAC://CRI.HACE.FDI/TEXT-EDITOR"}})
        assert uri["result"] == "rac://cri.hace.fdi/text-editor"

    def test_text_editor_uses_ail_machine_fpi(self):
        """text-editor uses ail-machine FPI instance via executor-py"""
        from executor_py.io.rac.cri.fpi import FpiExecutor
        from executor_py.io.rac.cri.fdi import FdiExecutor

        # Text editor opens AIL machine instance
        fpi_executor = FpiExecutor()
        ail_instance = fpi_executor.instance("fpi.ail.machine", endpoint="fpi://ail-machine")

        assert ail_instance.is_open

        # Text editor parses AIL document
        parse_result = ail_instance.execute("ail.parse", {"raw_text": AIL_TEST_CONTENT})
        assert parse_result["result"]["status"] == "success"

        # Text editor validates AIL document
        validate_result = ail_instance.execute("ail.validate", {"raw_text": AIL_TEST_CONTENT})
        assert validate_result["result"]["status"] == "success"

        # Text editor gets summary
        summary_result = ail_instance.execute("ail.summary", {"raw_text": AIL_TEST_CONTENT})
        assert summary_result["result"]["status"] == "success"

        # Close instance
        close_result = ail_instance.close()
        assert close_result["closed"] is True

    def test_full_roundtrip_fdi_fpi(self):
        """Full roundtrip: text-editor FDI -> ail-machine FPI -> text-editor FDI"""
        from executor_py.io.rac.cri.fdi import FdiExecutor
        from executor_py.io.rac.cri.fpi import FpiExecutor

        fdi_executor = FdiExecutor()
        fpi_executor = FpiExecutor()

        # 1. Text editor uses FDI to slugify
        text_editor = fdi_executor.import_binding("fdi.str.slug", "text_editor")
        slug_result = text_editor.fdi.str.slug({"args": {"value": "User Profile Schema"}})
        assert slug_result["result"] == "user-profile-schema"  # kebab-case per text-editor

        # 2. Text editor opens AIL machine instance
        ail_instance = fpi_executor.instance("fpi.ail.machine")

        # 3. AIL machine parses document
        ail_content = f"""---
schema: {slug_result["result"]}
version: "1.0"
namespace: test
---
# Test
"""
        parse_result = ail_instance.execute("ail.parse", {"raw_text": ail_content})
        assert parse_result["result"]["status"] == "success"

        # 4. AIL machine validates
        validate_result = ail_instance.execute("ail.validate", {"raw_text": ail_content})
        assert validate_result["result"]["status"] == "success"

        # 5. Text editor uses FDI again for slugify
        snake_result = text_editor.fdi.str.snake({"args": {"value": "User Profile Schema"}})
        # snake uses underscore delimiter per text-editor
        assert "_" in snake_result["result"]
        assert snake_result["result"].replace(" ", "") == snake_result["result"].replace(" ", "").lower()

        # 6. Close instance
        ail_instance.close()


# ─── Test 5: Route Resolution ─────────────────────────────────────────────────

class TestRACCRIRouteResolution:
    """Test RAC URI resolution for both directions"""

    def test_fdi_route_resolution_text_editor(self):
        """Resolve text-editor FDI routes"""
        from executor_py.io.rac.resolver import RouteResolver

        resolver = RouteResolver()
        resolver.discover_routes()

        route = resolver.resolve_rac_uri("rac://cri.hace.fdi/text-editor")
        assert route is not None
        assert route.specs == "fdi"
        assert route.export_enabled is True

    def test_fpi_route_resolution_ail_machine(self):
        """Resolve ail-machine FPI routes"""
        from executor_py.io.rac.resolver import RouteResolver

        resolver = RouteResolver()
        resolver.discover_routes()

        route = resolver.resolve_rac_uri("rac://cri.hace.fpi/ail-machine")
        assert route is not None
        assert route.specs == "fpi"
        assert route.export_enabled is True

    def test_text_editor_route_resolution(self):
        """Resolve text-editor routes via RouteResolver"""
        from executor_py.io.rac.resolver import RouteResolver

        resolver = RouteResolver()
        resolver.discover_routes()

        route = resolver.resolve_rac_uri("rac://cri.hace.fdi/text-editor/str/slug")
        assert route is not None
        assert route.specs == "fdi"
        assert route.capability == "text-editor"  # parent capability
        # Feature resolved via raw capabilities list
        raw_caps = route.raw.get("capabilities", [])
        assert any("str.slug" in c for c in raw_caps)


# ─── Test 6: SIO Frame Compliance ─────────────────────────────────────────────

class TestRACCRISIOFrameCompliance:
    """Test SIO-CRI-FPI-V2 frame compliance"""

    def test_fdi_sio_frame_structure(self):
        """FDI invoke uses canonical SIOFrame"""
        from executor_py.io.rac.cri.fdi import FdiExecutor
        from executor_py.io.rac.resolver import SIOFrame

        executor = FdiExecutor()

        ctx = ExecContext(
            workspace_root="/workspace",
            actor_target="text-editor",
        )
        exec_input = ExecInput(
            action="fdi.str.slug",
            payload={"value": "Test"},
            headers={
                "ara": "ara:test:valid",
                "licence": "lic:test:valid",
                "visibility": "restricted",
            },
            context={"workspace_root": "/workspace", "actor_target": "text-editor"},
        )

        result = executor.execute(exec_input, ctx)

        assert result.status.value == "success"
        assert result.proof is not None
        assert result.proof.fan_id == "hace-io-rac-cri-fdi"

    def test_fpi_sio_frame_structure(self):
        """FPI instance execute uses canonical SIOFrame"""
        from executor_py.io.rac.cri.fpi import FpiExecutor

        executor = FpiExecutor()
        instance = executor.instance("fpi.ail.machine", endpoint="fpi://ail-machine")

        result = instance.execute("ail.parse", {"raw_text": AIL_TEST_CONTENT})

        assert "result" in result
        assert result["action"] == "ail.parse"
        assert result["state"] == "running"
