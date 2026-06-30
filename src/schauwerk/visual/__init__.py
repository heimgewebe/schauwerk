"""Visual grammar primitives and DSL helpers for Schauwerk renderers."""

from .grammar import (
    MIRO_VISUAL_PRIMITIVES,
    TemplateSpec,
    VisualPrimitive,
    learning_template,
    primitive_by_name,
    primitive_catalog,
    primitive_names,
)
from .miro_dsl import bullets, doc, line, table

__all__ = [
    "MIRO_VISUAL_PRIMITIVES",
    "TemplateSpec",
    "VisualPrimitive",
    "bullets",
    "doc",
    "learning_template",
    "line",
    "primitive_by_name",
    "primitive_catalog",
    "primitive_names",
    "table",
]
