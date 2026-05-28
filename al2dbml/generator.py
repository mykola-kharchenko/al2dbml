"""Deprecated module path; use :mod:`al2dbml.diagram` instead.

This shim exists so that code written against 0.5.x and earlier — which
imported ``Generator`` from ``al2dbml.generator`` — continues to work
through one minor release. It will be removed in 0.7.0.

New code should use::

    from al2dbml import Diagram

or equivalently::

    from al2dbml.diagram import Diagram
"""

from __future__ import annotations

from .diagram import Diagram, Generator, generate

__all__ = ["Diagram", "Generator", "generate"]
