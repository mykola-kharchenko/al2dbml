"""Build phases for the Generator pipeline.

Each module here owns one phase of the AL -> DBML pipeline (enums,
tables, extensions, filters, references, groups). The :class:`BuildContext`
in :mod:`al2dbml._build.context` carries the mutable state across phases;
:class:`BuildConfig` holds the immutable knobs.

This is an internal package — the leading underscore signals that the
sub-builder API is not part of the public surface and may change between
minor versions without notice. The public entry point is
:class:`al2dbml.generator.Generator` (renamed to ``Diagram`` in 0.6.0).
"""
