# -*- coding: utf-8 -*-
"""
executor_py.io.rac.cri — Core RPC Interface transport bindings.

CRI = Core RPC Interface — canonical rule for host_call/stdio transports.

Per RAC-URI-MAP.ail v4:
    rac://cri.{ownerspace}.{specs}/{path}
    specs: fdi | ffi | fpi | wasm | ...

Transport Motifs (per CGE Canon AUD-20260814-FPI-VS-FFI-CANON):
    FDI (File Descriptor I/O)   — wired/autoload, USB/cable metaphor
    FFI (Foreign Function Interface) — native bridge, zero-copy ABI boundary
    FPI (Function Process Instance) — stateful lifecycle entity (init → running → finalize → terminated)

Key distinction:
    - FFI = low-level stateless C-ABI binding mechanism (ctypes, extern "C")
    - FPI = high-level stateful runtime entity with lifecycle management
    - FDI = wired transport motif (file/pipe/fd/shm autoload)

FFI and FPI are DISTINCT: FFI is the mechanism, FPI is the entity that uses
FFI as its underlying transport substrate.

Mirrors:
    - io/rac/src/resolver.rs (RACOR resolution)
    - io/rac/src/uri.rs (URI classification)
    - text-editor/io/rac/cri/fdi.py (existing FDI facade)
"""

from .fdi import (
    FdiMethod,
    FdiTransport,
    FDIMethodRegistry,
    FdiExecutor,
    FdiActorAlias,
    resolve_fdi_target,
    create_fdi_executor,
    _lazy_load_binding,
)
from .fpi import (
    FpiMethod,
    FpiTransport,
    FPIMethodRegistry,
    FpiExecutor,
    FpiInstance,
    FpiLifecycleState,
    resolve_fpi_target,
    create_fpi_executor,
)

# FFI module is a separate transport (native bridge) — lazy import to avoid
# ImportError if the ffi module has not been implemented yet.
try:
    from .ffi import (
        FfiMethod,
        FfiTransport,
        FFIMethodRegistry,
        FfiExecutor,
        resolve_ffi_target,
        create_ffi_executor,
    )
except ImportError:
    FfiMethod = None
    FfiTransport = None
    FFIMethodRegistry = None
    FfiExecutor = None
    resolve_ffi_target = None
    create_ffi_executor = None


__all__ = [
    # FDI — wired transport (USB/cable/autoload)
    "FdiMethod", "FdiTransport", "FDIMethodRegistry", "FdiExecutor",
    "FdiActorAlias", "resolve_fdi_target", "create_fdi_executor",
    "_lazy_load_binding",
    # FFI — native bridge transport (zero-copy ABI boundary)
    "FfiMethod", "FfiTransport", "FFIMethodRegistry", "FfiExecutor",
    "resolve_ffi_target", "create_ffi_executor",
    # FPI — Function Process Instance (stateful lifecycle entity)
    "FpiMethod", "FpiTransport", "FPIMethodRegistry", "FpiExecutor",
    "FpiInstance", "FpiLifecycleState", "resolve_fpi_target", "create_fpi_executor",
]
