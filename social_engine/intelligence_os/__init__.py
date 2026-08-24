"""Infenergy Intelligence OS.

The package is an additive operating layer over the existing Social Engine.
It owns governance, durable execution, world state, and the master session;
existing production subsystems remain behind registered semantic capabilities.
"""

from .foundation import bootstrap

__all__ = ["bootstrap"]