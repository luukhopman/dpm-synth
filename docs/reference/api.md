---
description: API reference for the dpmsynth package - load_template, generate, GenerationResult, SyntheticData, build_report, write_scaled_package and the template classes.
---

# Python API

The public API is the names in `dpmsynth.__all__`, all on this page and
covered by the [stability policy](../project/stability.md). They are
defined in `dpmsynth.template`, `dpmsynth.generator` and `dpmsynth.scale`;
import them from `dpmsynth`. Names that start with an underscore, such as
the private methods of `SyntheticData`, are internal.

```python
from dpmxbrl import write_xbrl_csv

from dpmsynth import generate, load_template, write_scaled_package

result = generate(load_template("sample.json"), seed=7)
write_xbrl_csv(result.report, "report.zip")
written = write_scaled_package(result.data, "big.zip", rows=10_000)
print(result.summary["passed"], result.failed, written)
```

```text
8 [] {'S_01.00': 14, 'S_02.00.a': 4, 'S_03.00': 10000}
```

## Thread safety

[`generate`][dpmsynth.generate] keeps no shared state, so several
templates may be generated in parallel threads; it is CPU-bound, so
processes run faster. A `SyntheticData` is changed while it is generated
and is safe to read from several threads afterwards; templates are
immutable.

## Templates

::: dpmsynth.load_template

::: dpmsynth.ModuleTemplate

::: dpmsynth.TemplateTable

::: dpmsynth.OpenKey

::: dpmsynth.TemplateCell

::: dpmsynth.TemplateRule

::: dpmsynth.TemplateError

::: dpmsynth.TEMPLATE_FORMAT

## Generating

::: dpmsynth.generate

::: dpmsynth.GenerationResult

::: dpmsynth.STATUSES

::: dpmsynth.SyntheticData

::: dpmsynth.DEFAULT_ENTITY

::: dpmsynth.DEFAULT_REFERENCE_DATE

::: dpmsynth.LEI_PREFIX

::: dpmsynth.MAX_OPEN_ROWS

## Writing

::: dpmsynth.build_report

::: dpmsynth.write_scaled_package

## Version

::: dpmsynth.__version__
