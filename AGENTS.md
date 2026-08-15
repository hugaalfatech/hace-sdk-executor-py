# HACE SDK — Python Executor Agents Guide

> For Cogninfer working on `sdk/executor-py`.

## Dual Implementation

### 1. Python Package (src/executor_py/)
- **Build**: hatchling, `pip install -e .`
- **Deps**: aiohttp, websockets
- **Tests**: pytest-asyncio, mypy, ruff
- **Scripts**: check, test, crystallize, seal (PowerShell)

### 2. Rust PyO3 Bridge (src/lib.rs)
- **Crate**: `hace-sdk-executor-py`
- **Deps**: `hace-sdk-me-core`, `hace-sdk-runinfer`, `pyo3 0.22 (extension-module)`
- **Implements**: `MactorBackend` trait using llama-cpp-python via PyO3
- **Hooks**: `PythonExecutorHook` binding to FEM lifecycle (init/health/stop)

## FES DNA (tool.executor-py)
```toml
actor = "text-ractor"
executor = "executor-py"
fes_model = "IPO"
ipo_processor = true
rac_router_role = "MCV_Controller"
fes_layer = "executor"
transports = ["fdi", "fpi", "ffi", "http", "ws"]
```

## Invariant
- MactorBackend trait conformance
- IPO processor as MCV_Controller
- Evidence required (ALR/FEH)
- RAC URI v4, SIO-FPI-JSON-v1