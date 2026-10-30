---
description: Task-oriented recipes for dpm-synth - write a template, get one from a DPM release, shape a realistic report, load-test, reproduce reports and validate the output.
---

# How-to guides

Recipes for specific tasks. Each assumes you have dpm-synth installed and
have generated a first report; the [getting started](../getting-started.md)
tutorial covers the basics. Every example runs against the templates in
[`docs/samples`](https://github.com/luukhopman/dpm-synth/tree/main/docs/samples).

<div class="grid cards" markdown>

-   :lucide-pencil-line:{ .lg .middle } [**Write a template by hand**](write-a-template.md)

    ---

    Describe your own tables, keys, data types and rules, and check the template.

-   :lucide-database:{ .lg .middle } [**Get a template from a DPM release**](from-a-dpm-release.md)

    ---

    Export a real module with dpm-xl, and what each field holds.

-   :lucide-sliders-horizontal:{ .lg .middle } [**Shape a realistic report**](realistic-reports.md)

    ---

    Amounts for an institution size, sparse reports, currencies, warnings and inactive rules.

-   :lucide-gauge:{ .lg .middle } [**Load-test with scaled packages**](load-testing.md)

    ---

    Write packages with millions of open-table rows, and know which rules still hold.

-   :lucide-repeat:{ .lg .middle } [**Reproduce a report with seeds**](reproducible-seeds.md)

    ---

    Get the same bytes again, or different reports on purpose.

-   :lucide-circle-check:{ .lg .middle } [**Validate the output with dpm-xbrl and dpm-xl**](validate-output.md)

    ---

    Check a package independently, as a downstream consumer would.

</div>
