# -*- coding: utf-8 -*-
"""
executor_py.io.rac.cri.bridge — CRI Bridge Modules

Bridge modules that connect executor-py SDK with external systems
via canonical CRI transport paths (FDI/FPI).
"""

from .ail_machine import AilMachineBridge

__all__ = [
    "AilMachineBridge",
]
