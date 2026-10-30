---
description: For AI agents and their users - the essential dpm-synth API on one page, its contracts, common pitfalls, and the llms.txt files.
---

# Using dpm-synth with AI agents

This page is for coding agents that write code *using* dpm-synth, and for
people who brief them. It gives the essential API, the contracts to rely on
and the mistakes to avoid. Agents working *on* the dpm-synth repository
should read `AGENTS.md` in its root instead.

Machine-readable copies of these docs:

- [`llms.txt`](llms.txt): an index of every page with a one-line
  description ([llmstxt.org](https://llmstxt.org) format).
- [`llms-full.txt`](llms-full.txt): every page in one Markdown file,
  including the API reference.
- Each page as Markdown: replace the trailing `/` of a page URL with
  `.md`, for example
  `https://luukhopman.github.io/dpm-synth/guides/load-testing.md`
  (section index pages are `.../guides/index.md`).

The sibling packages have the same files:
[dpm-xl](https://luukhopman.github.io/dpm-xl/llms.txt) and
[dpm-xbrl](https://luukhopman.github.io/dpm-xbrl/llms.txt).

## Essentials

```python
from dpmxbrl import write_xbrl_csv
from dpmxl import evaluate_rule

from dpmsynth import TemplateError, generate, load_template, write_scaled_package

try:
    template = load_template("sample.json")  # a path, or the parsed JSON as a dict
except TemplateError as error:  # the only exception for a bad template
    raise SystemExit(f"bad template: {error}")

result = generate(template, seed=7)  # same inputs and versions, same report
result.statuses  # {"rows": "passed", ..., "history": "unsupported"}: by rule code
result.summary  # {"rules": 9, "passed": 8, "failed": 0, ...}: counts by status
result.failed  # []: codes of rules that still fail
result.messages  # {"history": "...time_shift..."}: why error or unsupported
result.report  # dpmxbrl.Report, ready to write
result.data  # SyntheticData: a dpm-xl provider over the values

write_xbrl_csv(result.report, "report.zip")
write_scaled_package(result.data, "big.zip", rows=1000)  # load testing
evaluate_rule("{tS_01.00, r0010, c0010} >= 0", result.data).status
```

| Task | Call |
| --- | --- |
| Load a template | `load_template(path_or_mapping) -> ModuleTemplate`; reads `dpm-synth-template/1` and dpm-xl's `dpm-module/1`; raises `TemplateError` |
| Get a template for a real module | `dpm-xl export-module DATABASE MODULE --release R -o module.json` ([guide](guides/from-a-dpm-release.md)) |
| Generate | `generate(template, *, seed=0, open_rows=2, max_rounds=40, entity="SYNTHETICDPMXL000002", reporting_level="CON", reference_date=None, currency=None, size="medium", fill=1.0) -> GenerationResult` |
| Write the package | `dpmxbrl.write_xbrl_csv(result.report, "report.zip")` |
| Millions of rows | `write_scaled_package(result.data, "big.zip", rows=N or {table: N}) -> dict[str, int]` |
| Rebuild the report after changing values | `build_report(result.data) -> dpmxbrl.Report` |
| Evaluate a rule on the values | `dpmxl.evaluate_rule(expression, result.data, precondition=...)` |
| Keep only some rules | `dataclasses.replace(template, rules=tuple(...))` |
| Command line | `dpm-synth generate TEMPLATE -o OUT.zip [--seed N] [--size small\|medium\|large] [--fill RATIO] [--currency CODE] [--fail-on error\|warning] [--json]`; exit 0 no rule at or above `--fail-on` fails or is `error`, 1 some do, 2 usage, 3 bad input |
| Check the package against the same file | `dpm-xl check-report module.json report.zip` (needs `dpm-xl[xbrl]`) |

## Contracts

- `load_template` raises `TemplateError` (a `ValueError`) for every
  unreadable, non-JSON or invalid template, naming the field by its path,
  such as `tables[2].cells[0].datapoint`. Unknown fields are ignored.
- `generate` raises `ValueError` only for invalid options. Rules that cannot
  be evaluated never raise: they are `error` or `unsupported`. `load_template`
  rejects rules that do not parse or select a table outside the template.
- `statuses` has every rule once, with one of `STATUSES`: dpm-xl's
  `passed`, `failed`, `not_applicable`, `error` and `unsupported`, or
  `skipped` for an inactive rule (`TemplateRule.active`). Rules of either
  `severity` are repaired.
- The same template, seed, options, output file name and versions give the
  same bytes.
- `ModuleTemplate` and its parts are frozen dataclasses; `GenerationResult`
  is frozen too, but `result.data.values` is a mutable dict.
- `--json` output is `{"schema_version": 2, "tool": "dpm-synth",
  "version", "summary": {"rules", "passed", "failed", "not_applicable",
  "error", "unsupported", "skipped", "facts"}, "output", "release",
  "module", "seed", "rounds", "history", "repairs", "results": [{"rule",
  "severity", "status", "message"}]}` ([JSON output](reference/json-output.md));
  `schema_version` changes when the layout does.
- Exit status 1 means a rule at or above `--fail-on` (default `error`)
  fails or is `error`; failing `warning` rules and `unsupported` rules
  leave it at 0 by default.
- Every generated LEI-shaped identifier starts with `SYNTH`
  (`LEI_PREFIX`) and has valid check digits; the default entity is the
  fictional `SYNTHETICDPMXL000002`. None can be a real entity's LEI.
- Nothing is fetched over the network.

## Pitfalls

- **Not every rule passes.** Real modules keep some failing rules; read
  `result.failed`, never assume it is empty. See
  [limits of the loop](concepts/limits.md).
- **Exit status 1 is not a crash.** The package is written; compare the
  failed rules in the JSON `results` with what you expect.
- **Scaled rows are not evaluated.** Rules that sum an open table fail on a
  scaled package; use the unscaled one to test validation results.
- **The entity and reporting level live in the data.** Pass `entity`,
  `reporting_level` and `reference_date` to `generate`;
  `build_report` and `write_scaled_package` take them from `result.data`.
- **The root folder is the file name.** Packages are named as dpm-xbrl
  names them: `report.zip` holds `report/...`. The EBA file-naming filing
  rule is a warning on synthetic names.
- **Rule order matters for reproducibility.** Reordering the template's
  tables, cells or rules can change the values for a seed.
- **Values are synthetic.** They satisfy rules, not economics; do not use
  them as realistic magnitudes.
- **Data types are the DPM's.** `es` is text that may be empty in the DPM
  but is never written empty (EBA filing rule 2.19); `t` is always `true`;
  an `e` cell needs `items`. See
  [data types](reference/template-format.md#data-types).
- **`time_shift` rules are `unsupported`.** A single report has no earlier
  period; they never change the exit status.

## Where to look next

- [Getting started](getting-started.md) for a guided first use.
- [Template format](reference/template-format.md) to write or check a
  template.
- [Shape a realistic report](guides/realistic-reports.md) for `size`,
  `fill`, `currency`, rule `severity` and `active`.
- [Standards and conformance](reference/standards.md) for the filing
  rules and format versions the reports follow.
- [Python API](reference/api.md) for every signature, and
  [CLI](reference/cli.md), [exit statuses](reference/exit-statuses.md) and
  [JSON output](reference/json-output.md).
