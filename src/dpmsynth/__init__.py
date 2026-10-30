"""Generate synthetic EBA xBRL-CSV reports that satisfy DPM-XL validation rules.

Typical use::

    from dpmxbrl import write_xbrl_csv

    from dpmsynth import generate, load_template

    result = generate(load_template("template.json"), seed=7)
    write_xbrl_csv(result.report, "report.zip")
    print(result.summary, result.failed)

Everything in ``__all__`` is the public API; import it from ``dpmsynth``.
"""

from ._version import __version__
from .generator import (
    DEFAULT_ENTITY,
    DEFAULT_REFERENCE_DATE,
    LEI_PREFIX,
    MAX_OPEN_ROWS,
    SIZES,
    STATUSES,
    GenerationResult,
    SyntheticData,
    build_report,
    generate,
)
from .scale import write_scaled_package
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
    "DEFAULT_ENTITY",
    "DEFAULT_REFERENCE_DATE",
    "LEI_PREFIX",
    "MAX_OPEN_ROWS",
    "SIZES",
    "STATUSES",
    "TEMPLATE_FORMAT",
    "GenerationResult",
    "ModuleTemplate",
    "OpenKey",
    "SyntheticData",
    "TemplateCell",
    "TemplateError",
    "TemplateRule",
    "TemplateTable",
    "__version__",
    "build_report",
    "generate",
    "load_template",
    "write_scaled_package",
]
