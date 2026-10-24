<p align="center">
  <a href="https://luukhopman.github.io/dpm-synth/"><img src="https://luukhopman.github.io/dpm-synth/assets/logo.svg" alt="dpm-synth" width="240"></a>
</p>

<p align="center"><em>Generate synthetic EBA reports that satisfy DPM-XL validation rules.</em></p>

Generate synthetic EBA xBRL-CSV report packages that satisfy a module's
DPM-XL validation rules. Give dpm-synth a template with a module's tables,
cells and rules; it fills every cell with a plausible value, repairs the
values until the rules pass, and writes a report package that reads and
validates like a real submission. Use it to test loaders, data warehouses
and validators for EBA reports, for any module, without real supervisory
data.

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
print(result.passed, "of", result.rules, "rules pass; failing:", result.failed)
write_xbrl_csv(result.report, "report.zip")
```

```text
2 of 2 rules pass; failing: []
```

From the command line, with an exit status of 1 if some rules still fail:

```console
$ dpm-synth generate minimal.json -o report.zip --seed 7
rules: 2, passed: 2, failed: 0, not evaluated: 0, not applicable: 0
rounds: 2 (failing rules per round: 1, 0)
wrote report.zip (3 facts)
```

The sample template `minimal.json` is in
[`docs/samples`](https://github.com/luukhopman/dpm-synth/tree/main/docs/samples);
templates for real EBA modules are exported from a DPM release by any tool
that writes the
[template format](https://luukhopman.github.io/dpm-synth/reference/template-format/).

## Features

- **Any module**: the `dpm-synth-template/1` format describes tables, open
  keys, cells, data types, allowed items and DPM-XL rules.
- **Rules satisfied**: an evaluate-and-repair loop over the rules, with
  [dpm-xl](https://luukhopman.github.io/dpm-xl/), repairs sums,
  differences, products, sign rules, `isnull`, `in` and `match`. On EBA
  DPM 4.3 COREP_OF, 999 of the 1,051 rules that apply pass, in 15 rounds;
  the result names the rest.
- **Valid packages**: written by
  [dpm-xbrl](https://luukhopman.github.io/dpm-xbrl/), with a fictional LEI,
  and read back without broken EBA filing rules other than the file name.
- **Reproducible**: the same template, seed and versions give the same
  bytes.
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
  template, build one from a DPM release, load-test, reproducible
  seeds, validate the output with dpm-xbrl and dpm-xl
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
