# -*- coding: utf-8 -*-
"""
executor_py.io — IO layer subpackage.

Mirrors `hace/io/rac/` module structure.
"""

from .rac.cri.fdi import FdiExecutor, FdiMethod, FdiTransport, FDIMethodRegistry
from .rac.cri.fpi import FpiExecutor, FpiMethod, FpiTransport, FPIMethodRegistry
from .rac.cri.ffi import FfiExecutor, FfiMethod, FfiTransport, FFIMethodRegistry
from .transport import StdioTransport, HttpTransport, WsTransport

__all__ = [
    # CRI transports
    "FdiExecutor", "FdiMethod", "FdiTransport", "FDIMethodRegistry",
    "FpiExecutor", "FpiMethod", "FpiTransport", "FPIMethodRegistry",
    "FfiExecutor", "FfiMethod", "FfiTransport", "FFIMethodRegistry",
    # RION transports
    "StdioTransport", "HttpTransport", "WsTransport",
]