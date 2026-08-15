# HACE SDK — Python Executor (NEP-PY)

> **CONA://executor.py.v1** — Python NEP Executor

## Concept

Python Executor = **NEP-PY** — Python substrate for inference execution via llama-cpp-python / hace-llm-machine.

> Bridges Runinfer ME Core to Python NEP. Implements `MactorBackend` trait via PyO3.

## Dual Implementation

### 1. Python Package (`src/executor_py/`)
```bash
# Install
pip install -e sdk/executor-py

# Test
python -m pytest tests/
```

### 2. Rust PyO3 Bridge
```bash
cargo build -p hace-sdk-executor-py
cargo test -p hace-sdk-executor-py
```

## FES DNA (from pyproject.toml)
- actor: `text-ractor`
- executor: `executor-py`
- fes_model: `IPO`
- ipo_processor: `true`
- rac_router_role: `MCV_Controller`
- transports: `[fdi, fpi, ffi, http, ws]`

## Python Package Structure (src/executor_py/)
- Core: `ExecuteParticle`, `ExecContext`, `ExecInput`, `ExecOutput`, `SepiProof`
- SIO: `SioEnvelope`, `SioResult`, `SioMetadata`, `TransportConfig`, `RetryPolicy`
- FES DNA: `EnginePart`, `ExecutorDNA`, `ActorExecutorMapping`, `FesLayer`
- Subpackages: `actor`, `executor`, `module`, `ipo`, `capor`, `racor`, `evidence`, `adapter`, `payload`, `io.rac.cri.{fdi,ffi,fpi}`, `io.transport`

## Status
- **Complete**: Both Python package + Rust PyO3 bridge