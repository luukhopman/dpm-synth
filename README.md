<p align="center">
  <a href="https://luukhopman.github.io/dpm-synth/"><img src="https://luukhopman.github.io/dpm-synth/assets/logo.svg" alt="dpm-synth logo" width="240"></a>
</p>

<p align="center"><em>Generate synthetic EBA reports that satisfy DPM-XL validation rules.</em></p>

dpm-synth generates synthetic test data for European Banking Authority
(EBA) reporting: xBRL-CSV report packages, such as COREP or FINREP reports,
whose values are made up but pass the module's DPM-XL validation rules.
Give it a template file with a module's tables, cells and rules, such as
the module file `dpm-xl export-module` writes from an EBA Data Point Model
(DPM 2.0) release; it fills every cell with a plausible value, repairs the
values until the rules pass, and writes a report package that reads and
validates like a real XBRL submission. Use it to test loaders, data
warehouses and validators for EBA reports, for any module, without real
supervisory data. It builds on its sibling packages
[dpm-xl](https://pypi.org/project/dpm-xl/), which evaluates the rules, and
[dpm-xbrl](https://pypi.org/project/dpm-xbrl/), which writes the package.

dpm-synth is an independent project, not affiliated with or endorsed by the
European Banking Authority.

## Installation

```text
pip install dpm-synth   # Python 3.11+; installs dpm-xl and dpm-xbrl
```

## Quickstart

```python
from dpmxbrl import write_xbrl_csv

from dpmsynth import generate, load_template

template = load_template("minimal.json")  # a module's tables, cells and rules
result = generate(template, seed=7)
summary = result.summary  # rules counted by status
print(summary["passed"], "of", summary["rules"], "rules pass; failing:", result.failed)
write_xbrl_csv(result.report, "report.zip")
```

```text
2 of 2 rules pass; failing: []
```

From the command line, with an exit status of 1 if some rules still fail:

```console
$ dpm-synth generate minimal.json -o report.zip --seed 7
rules: 2, passed: 2, failed: 0
rounds: 1 (failing rules per round: 0)
wrote report.zip (3 facts)
```

The sample template `minimal.json` is in
[`docs/samples`](https://github.com/luukhopman/dpm-synth/tree/main/docs/samples);
templates for real EBA modules are exported from a DPM release with
[`dpm-xl export-module`](https://luukhopman.github.io/dpm-xl/guides/from-a-dpm-release/),
whose module file dpm-synth reads as it is (see
[get a template from a DPM release](https://luukhopman.github.io/dpm-synth/guides/from-a-dpm-release/)).

## Features

- **Any module**: dpm-synth reads the module file (`dpm-module/1`) that
  `dpm-xl export-module` writes from an EBA DPM release, or a file you
  write with a module's tables, open keys, cells, data types, allowed
  items and DPM-XL rules.
- **Every DPM data type**: `es` cells get non-empty text (EBA filing rule
  2.19), `t` cells are always `true`, and dates, URIs and ordinals have
  their own forms.
- **Rules satisfied**: an evaluate-and-repair loop over the rules, with
  [dpm-xl](https://luukhopman.github.io/dpm-xl/), repairs sums,
  differences, products, sign rules, `isnull`, `in` and `match`, after a
  joint solve of the linear rules. The result names the rules that still
  fail; [limits](https://luukhopman.github.io/dpm-synth/concepts/limits/)
  has the figures for a real module.
- **Realistic shape**: `--size small|medium|large` for the amounts,
  `--fill` for sparse reports and `--currency` for the reporting currency.
- **Severities and inactive rules**: failing `warning` rules exit with
  status 1 only with `--fail-on warning`; rules with `"active": false` are
  skipped.
- **Valid packages**: written by
  [dpm-xbrl](https://luukhopman.github.io/dpm-xbrl/), with a fictional LEI,
  and read back without broken EBA filing rules other than the file name.
- **Reproducible**: a seed reproduces a report byte for byte
  ([what else it depends on](https://luukhopman.github.io/dpm-synth/guides/reproducible-seeds/)).
- **Large**: scaled packages stream open tables with millions of rows.

## Toolkit

**Part of the dpm toolkit**, three Python packages that work together:

| Package | What it does |
| :-- | :-- |
| <a href="https://luukhopman.github.io/dpm-xl/"><img src="https://luukhopman.github.io/dpm-xl/assets/logo.svg" alt="dpm-xl" height="32"></a> | Parse and evaluate DPM-XL validation rules |
| <a href="https://luukhopman.github.io/dpm-xbrl/"><img src="https://luukhopman.github.io/dpm-xbrl/assets/logo.svg" alt="dpm-xbrl" height="32"></a> | Read, write and check xBRL-CSV and XBRL-XML reports |
| <a href="https://luukhopman.github.io/dpm-synth/"><img src="https://luukhopman.github.io/dpm-synth/assets/logo.svg" alt="dpm-synth" height="32"></a> | Generate test reports that satisfy DPM-XL rules **(this package)** |

The [toolkit tour](https://luukhopman.github.io/dpm-xl/guides/toolkit-tour/)
takes one report through all three: generated with dpm-synth, read with
dpm-xbrl, then evaluated and explained with dpm-xl.

## Documentation

**Documentation: <https://luukhopman.github.io/dpm-synth/>**

- [Getting started](https://luukhopman.github.io/dpm-synth/getting-started/)
- [How-to guides](https://luukhopman.github.io/dpm-synth/guides/): write a
  template, get one from a DPM release, shape a realistic report,
  load-test, reproducible seeds, validate the output with dpm-xbrl and dpm-xl
- [Concepts](https://luukhopman.github.io/dpm-synth/concepts/): the
  evaluate-and-repair loop and its limits
- [Reference](https://luukhopman.github.io/dpm-synth/reference/): the
  [template format](https://luukhopman.github.io/dpm-synth/reference/template-format/),
  the [CLI](https://luukhopman.github.io/dpm-synth/reference/cli/) and the
  [Python API](https://luukhopman.github.io/dpm-synth/reference/api/)
- For AI agents: [llms.txt](https://luukhopman.github.io/dpm-synth/llms.txt)
  and [llms-full.txt](https://luukhopman.github.io/dpm-synth/llms-full.txt)
- [Changelog](https://github.com/luukhopman/dpm-synth/blob/main/CHANGELOG.md),
  [stability policy](https://luukhopman.github.io/dpm-synth/project/stability/)
  and [security policy](https://luukhopman.github.io/dpm-synth/project/security/)

## Development

```text
uv sync
uv run pytest
uv run ruff check
uv run ruff format --check
uv run ty check
uv run python scripts/build_docs.py
```

See [contributing](https://luukhopman.github.io/dpm-synth/project/contributing/).

## Licence

MIT. See [LICENSE](https://github.com/luukhopman/dpm-synth/blob/main/LICENSE).
