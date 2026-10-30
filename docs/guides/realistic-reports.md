---
description: Shape a synthetic report - amounts for a small, medium or large institution, sparse reports, the reporting currency and currencies of denomination, and rules graded by severity or switched off.
icon: lucide/sliders-horizontal
---

# Shape a realistic report

By default dpm-synth fills every cell, draws amounts for a medium-sized
institution and reports in euro. Four options bring a report closer to the
one you need to test with: `--size`, `--fill`, `--currency`, and the
`severity` and `active` fields of the template's rules. Each has the same
name in Python, as an argument of [`generate`][dpmsynth.generate] or a field
of the [template](../reference/template-format.md).

| To | Command line | Python or template |
| --- | --- | --- |
| Draw amounts for a smaller or larger institution | `--size small\|medium\|large` | `generate(..., size="large")` |
| Leave cells out, as real reports do | `--fill RATIO` | `generate(..., fill=0.5)` |
| Report in another currency | `--currency CODE` | `generate(..., currency="SEK")`, or `"currency"` in the template |
| Report a cell in its currency of denomination | | `"unit": true` on the cell |
| Make a rule a warning | `--fail-on error\|warning` sets what fails the run | `"severity": "warning"` on the rule |
| Switch a rule off | | `"active": false` on the rule |

The values still satisfy the rules, not economics: see
[limits of the loop](../concepts/limits.md).

## Institution size

`--size` sets the range that monetary amounts start in, over three orders of
magnitude: 1,000 to 1,000,000 for `small`, 100,000 to 100,000,000 for
`medium` (the default) and 10,000,000 to 10,000,000,000 for `large`. The
repairs then move them as the rules ask:

```python
from dpmsynth import generate, load_template

template = load_template("minimal.json")
for size in ("small", "medium", "large"):
    result = generate(template, seed=7, size=size)  # (1)!
    print(size, [fact.value for fact in result.report.facts])
```

1. The same seed draws the same relative values; only their scale changes.

```text
small ['93000', '3000', '90000']
medium ['9253000', '283000', '8970000']
large ['925373000', '28350000', '897023000']
```

## Sparse reports

Real reports leave most cells empty. `--fill` is the share of cells that
start with a value; the others are left out of the report unless a rule
needs a value, and every table keeps at least one fact:

```console
$ dpm-synth generate sample.json -o sparse.zip --seed 7 --fill 0.5
rules: 9, passed: 8, failed: 0, unsupported: 1
rounds: 2 (failing rules per round: 3, 0)
history: unsupported: The rule compares with the previous reporting period (time_shift), which a single report does not include
wrote sparse.zip (13 facts)
```

The full report has 20 facts. Three of the 13 were left out at first and
got a value because a rule needed one, such as the total of a row.

## Currencies

Monetary facts are reported in one reporting currency, as EBA filing rule
3.1 asks: the template's `currency`, or `--currency`, or else EUR. A cell
with `"unit": true` is reported in its currency of denomination instead,
the currency of its row's `CUS` or `CUA` key.
[`currencies.json`](../samples/currencies.json) has both:

```console
$ dpm-synth generate currencies.json -o currencies.zip --seed 7 --currency NOK
rules: 2, passed: 2, failed: 0
rounds: 1 (failing rules per round: 0)
wrote currencies.zip (7 facts)
```

Read back with dpm-xbrl, the report's base currency is NOK, and the `unit`
column follows each row's `CUS` key:

```python
from dpmxbrl import read_report

report = read_report("currencies.zip")
print(report.base_currency)
for fact in report.facts:
    print(fact.template, fact.datapoint, fact.value, dict(fact.keys))  # (1)!
```

1. `eba_CU:x1` stands for the reporting currency; `eba_CU:USD` names one.
   The percentage in `dp3` has no unit.

```text
iso4217:NOK
k_01.00 dp1 6961500 {'CUS': 'eba_CU:x1', 'unit': 'iso4217:NOK'}
k_01.00 dp2 2944500 {'CUS': 'eba_CU:x1', 'unit': 'iso4217:NOK'}
k_01.00 dp3 0.6900 {'CUS': 'eba_CU:x1', 'unit': ''}
k_01.00 dp1 283000 {'CUS': 'eba_CU:USD', 'unit': 'iso4217:USD'}
k_01.00 dp2 165000 {'CUS': 'eba_CU:USD', 'unit': 'iso4217:USD'}
k_01.00 dp3 0.1300 {'CUS': 'eba_CU:USD', 'unit': ''}
k_02.00 dp4 1250000 {}
```

## Warnings and inactive rules

The EBA marks some validation rules as blocking errors and others as
warnings, and deactivates rules over time. A template carries both:

- `"severity": "warning"` marks a rule that does not fail the run by
  default. Warnings are repaired like errors; the severity only changes the
  output and the exit status.
- `"active": false` switches a rule off: it is neither repaired nor
  evaluated, and is reported as `skipped`. It is not parsed either, so it
  may select a table the template does not have.

This template adds a text cell to `minimal.json`, a warning that its value
is three capital letters, which the loop does not repair (see
[regular expressions](../concepts/limits.md#regular-expressions)), and an
inactive rule:

```python
import json
from pathlib import Path

template = json.loads(Path("minimal.json").read_text(encoding="utf-8"))
template["tables"][0]["cells"].append(
    {"id": "T_01.00/r0040", "row": "0040", "column": "0010", "datapoint": "dp1004"}
)
template["rules"] += [
    {
        "code": "w1",
        "expression": 'match({tT_01.00, r0040, c0010}, "^[A-Z]{3}$")',
        "severity": "warning",
    },
    {"code": "old", "expression": "{tX_99.00, r0010, c0010} > 0", "active": False},
]
Path("graded.json").write_text(json.dumps(template, indent=1), encoding="utf-8")
```

The failing warning is named with `(warning)`, and by default the run
still succeeds; `--fail-on warning` makes it fail:

```console
$ dpm-synth generate graded.json -o graded.zip --seed 7
rules: 4, passed: 2, failed: 1, skipped: 1
rounds: 2 (failing rules per round: 1, 1)
still failing: w1 (warning)
wrote graded.zip (4 facts)
$ echo $?
0
$ dpm-synth generate graded.json -o graded.zip --seed 7 --fail-on warning
rules: 4, passed: 2, failed: 1, skipped: 1
rounds: 2 (failing rules per round: 1, 1)
still failing: w1 (warning)
wrote graded.zip (4 facts)
$ echo $?
1
```

The [JSON output](../reference/json-output.md) gives each rule's
`severity` and `status`, and [exit statuses](../reference/exit-statuses.md)
lists when the run fails.
