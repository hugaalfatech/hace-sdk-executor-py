# -*- coding: utf-8 -*-
"""
executor_py.io.rac — RAC operation routing (HOW/WHERE).

Mirrors `hace/io/rac/` (RAC transport/resolver layer).
"""

from .cri.fdi import FdiExecutor, FdiMethod, FdiTransport, FDIMethodRegistry
from .cri.fpi import FpiExecutor, FpiMethod, FpiTransport, FPIMethodRegistry
from .cri.fpi import FpiInstance
from .cri.ffi import FfiExecutor, FfiMethod, FfiTransport, FFIMethodRegistry
from .resolver import (
    RouteResolver,
    RouteIndex,
    NormalizedRoute,
    SIOFrame,
    create_resolver,
    resolve_rac_uri,
)
from .contracts import (
    RacMethodName,
    RacMethodContract,
    RAC_METHOD_CONTRACTS,
    RacMethodDispatcher,
    DefaultRacMethodDispatcher,
    resolve_rac_target,
)

__all__ = [
    # CRI transports
    "FdiExecutor", "FdiMethod", "FdiTransport", "FDIMethodRegistry",
    "FpiExecutor", "FpiMethod", "FpiTransport", "FPIMethodRegistry", "FpiInstance",
    "FfiExecutor", "FfiMethod", "FfiTransport", "FFIMethodRegistry",
    # Route Resolver (CGE/CRD CANON-20260814)
    "RouteResolver", "RouteIndex", "NormalizedRoute", "SIOFrame",
    "create_resolver", "resolve_rac_uri",
    # RAC Method Contracts
    "RacMethodName", "RacMethodContract", "RAC_METHOD_CONTRACTS",
    "RacMethodDispatcher", "DefaultRacMethodDispatcher",
    "resolve_rac_target",
]
