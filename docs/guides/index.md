---
description: Task-oriented recipes for dpm-synth - write a template, generate from a DPM export, load-test, reproduce reports and validate the output.
---

# How-to guides

Recipes for specific tasks. Each assumes you have dpm-synth installed and
have generated a first report; the [getting started](../getting-started.md)
tutorial covers the basics. Every example runs against the templates in
[`docs/samples`](https://github.com/luukhopman/dpm-synth/tree/main/docs/samples).

| Guide | Use it to |
| --- | --- |
| [Write a template by hand](write-a-template.md) | Describe your own tables, keys, data types and rules, and check the template. |
| [Generate from a DPM export](dpm-export.md) | Generate a report for a real EBA module, choose its rules and read the results. |
| [Load-test with scaled packages](load-testing.md) | Write packages with millions of open-table rows, and know which rules still hold. |
| [Reproduce a report with seeds](reproducible-seeds.md) | Get the same bytes again, or different reports on purpose. |
| [Validate the output with dpm-xbrl and dpm-xl](validate-output.md) | Check a package independently, as a downstream consumer would. |
