"""Generate synthetic EBA reports that satisfy DPM-XL validation rules."""

from .generator import GenerationResult, SyntheticData, build_report, generate
from .template import (
    TEMPLATE_FORMAT,
    ModuleTemplate,
    OpenKey,
    TemplateCell,
    TemplateError,
    TemplateRule,
    TemplateTable,
    load_template,
)

__all__ = [
    "TEMPLATE_FORMAT",
    "GenerationResult",
    "ModuleTemplate",
    "OpenKey",
    "SyntheticData",
    "TemplateCell",
    "TemplateError",
    "TemplateRule",
    "TemplateTable",
    "build_report",
    "generate",
    "load_template",
]
