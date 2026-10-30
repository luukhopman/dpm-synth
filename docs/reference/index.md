---
description: Exact behaviour of dpm-synth - the template format, the CLI, the exit statuses, the JSON output, the Python API, the standards followed and the glossary.
---

# Reference

Exact, complete descriptions. For explanations, see the
[concepts](../concepts/index.md); for recipes, the
[how-to guides](../guides/index.md).

<div class="grid cards" markdown>

-   :lucide-badge-check:{ .lg .middle } [**Standards and conformance**](standards.md)

    ---

    The EBA filing rules, xBRL-CSV, Report Packages and DPM-XL versions the reports follow, and how that is tested.

-   :lucide-file-json:{ .lg .middle } [**Template format**](template-format.md)

    ---

    The `dpm-synth-template/1` JSON format, field by field, and how it is validated; dpm-xl's `dpm-module/1` has the same fields.

-   :lucide-terminal:{ .lg .middle } [**CLI**](cli.md)

    ---

    The `dpm-synth generate` command and every option, such as `--size`, `--fill`, `--currency` and `--fail-on`.

-   :lucide-list-ordered:{ .lg .middle } [**Exit statuses**](exit-statuses.md)

    ---

    What each exit status means, and when the package is written.

-   :lucide-braces:{ .lg .middle } [**JSON output**](json-output.md)

    ---

    The layout of `dpm-synth generate --json`, with `schema_version`.

-   :lucide-code:{ .lg .middle } [**Python API**](api.md)

    ---

    Every public name, generated from the docstrings.

-   :lucide-book-a:{ .lg .middle } [**Glossary**](glossary.md)

    ---

    The terms of EBA reporting, XBRL and the DPM, shared by the three toolkit sites.

</div>
