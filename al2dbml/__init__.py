from __future__ import annotations

from .diagram import Diagram, Generator, generate
from .grouping import GroupingConfig

__version__ = "0.6.0"

# 'Generator' is a deprecated alias for 'Diagram'; remove in 0.7.0.
__all__ = ["Diagram", "Generator", "GroupingConfig", "__version__", "generate"]
