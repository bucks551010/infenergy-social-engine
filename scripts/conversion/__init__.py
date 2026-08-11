"""Conversion Logic Social Engine — decision-logic layer.

Implements Sections 2-11, 19, 23-25, 27-28, 42, 44 of the Conversion Logic spec.
Sits ABOVE existing generation phases in scripts/generate_posts.py:
Phase 0 produces a StrategicBrief which downstream phases must respect.
"""

from .briefs import StrategicBrief, PersuasionBlock, CopyBlock, DesignBlock, QualityBlock, ExperimentBlock
from .engine import ConversionLogicEngine, build_strategic_brief
from . import performance_memory

__all__ = [
    "StrategicBrief",
    "PersuasionBlock",
    "CopyBlock",
    "DesignBlock",
    "QualityBlock",
    "ExperimentBlock",
    "ConversionLogicEngine",
    "build_strategic_brief",
    "performance_memory",
]
