p = "T:/hace/engine/hace/sdk/executor-py/src/executor_py/io/rac/cri/fdi.py"
c = open(p, encoding='utf-8').read()

old = """    def _execute_capability(self, capability: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        \"\"\"Execute a capability via the underlying executor with TTLV payload.\"\"\"
        from ....core import ExecContext, ExecInput
        
        ctx = ExecContext(
            workspace_root=self._default_context.get("workspace_root", "/workspace"),
            actor_target=self._default_context.get("actor_target", "text-editor"),
            extra=self._default_context,
        )
        
        # Merge headers: default + payload-specific
        headers = {**self._default_headers}
        if "headers" in payload:
            headers.update(payload.pop("headers", {}))
        
        # Extract TTLV payload fields
        action = capability
        args = payload.get("args", {})
        options = payload.get("options", {})
        
        exec_input = ExecInput(
            action=action,
            payload={"args": args, "options": options},
            headers=headers,
            context=self._default_context,
        )
        
        result = self._executor.execute(exec_input, ctx)
        
        return {
            "status": result.status.value,
            "result": result.result,
            "proof": result.proof,
        }"""

new = """    def _execute_capability(self, capability: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        \"\"\"Execute a capability directly via adapter/text-editor facade (canonical).

        Per CGE Canon: capabilities execute directly via adapter/facade,
        NOT through executor's transport registry.
        \"\"\"
        from ....core import ExecContext, ExecInput, ExecuteError
        
        ctx = ExecContext(
            workspace_root=self._default_context.get("workspace_root", "/workspace"),
            actor_target=self._default_context.get("actor_target", "text-editor"),
            extra=self._default_context,
        )
        
        # Merge headers: default + payload-specific
        headers = {**self._default_headers}
        if "headers" in payload:
            headers.update(payload.pop("headers", {}))
        
        # Extract TTLV payload fields
        args = payload.get("args", {})
        options = payload.get("options", {})
        
        # Try adapter first (executor-py convention)
        try:
            from .fdi_binding import get_capability_adapter
            adapter = get_capability_adapter(capability)
            if adapter is not None:
                # Adapter convention: adapter(ctx, **args) -> result
                result = adapter(ctx, **args, headers=headers, context=self._default_context, options=options)
                return {
                    "status": "SUCCESS",
                    "result": result.get("result", result),
                    "proof": None,
                }
        except ImportError:
            pass
        except Exception:
            # Adapter failed, try text-editor facade
            pass
        
        # Try text-editor facade (RBP-IN)
        try:
            from text_editor.io.rac.cri.fdi import rac_fdi_in
            # rac_fdi_in.invoke uses text-editor convention: handler(action, payload, headers, context)
            result = rac_fdi_in.invoke(capability, {"value": payload.get("args", {}).get("value", ""), **payload.get("args", {})}, headers=headers, context=self._default_context)
            if isinstance(result, dict):
                if result.get("status") == "ERROR":
                    raise ExecuteError(code="FDI_EXEC_ERROR", message=result.get("header", f"{capability} failed"))
                return {
                    "status": "SUCCESS",
                    "result": result.get("result", result),
                    "proof": None,
                }
        except ImportError:
            pass
        except Exception as e:
            raise ExecuteError(code="FDI_EXEC_ERROR", message=f"{capability} failed: {str(e)}")
        
        # Try executor's internal registry (transport methods only)
        try:
            from ....core import ExecContext, ExecInput
            exec_input = ExecInput(
                action=capability,
                payload={"args": args, "options": options},
                headers=headers,
                context=self._default_context,
            )
            result = self._executor.execute(exec_input, ctx)
            return {
                "status": result.status.value,
                "result": result.result,
                "proof": result.proof,
            }
        except Exception:
            pass
        
        raise ExecuteError(code="FDI_NO_METHOD", message=f"Capability not found: {capability}")"""

c = c.replace(old, new)
open(p, 'w', encoding='utf-8').write(c)
print('Done')