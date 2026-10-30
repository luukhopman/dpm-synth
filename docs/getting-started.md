---
description: Tutorial - install dpm-synth, read a template, generate a first synthetic report from the command line and from Python, read the package back and check its rules.
icon: lucide/graduation-cap
---

# Getting started

This tutorial generates a synthetic report for a small template, reads the
package back with dpm-xbrl and checks the rules with dpm-xl. It takes about
ten minutes.

!!! info "Before you start"

    You need Python 3.11 or newer and a terminal. No knowledge of XBRL or
    DPM-XL is assumed: each step says what the output means, and terms
    with a dotted underline, such as datapoint, show a definition when you
    point at them. The [glossary](reference/glossary.md) lists them all.

You will:

1. install dpm-synth;
2. read a template;
3. generate a report on the command line;
4. read the package back;
5. generate from Python;
6. evaluate a rule on the generated values;
7. try a bigger template.

## 1. Install

=== "pip"

    ```text
    pip install dpm-synth
    ```

=== "uv"

    ```text
    uv add dpm-synth
    ```

This also installs [dpm-xl], which evaluates DPM-XL rules, and [dpm-xbrl],
which reads and writes EBA reports. Check the installation; it prints the
installed version:

```bash
dpm-synth --version
```

## 2. Read a template

A template describes one module: its tables, the cells of each table, and
the rules a report must satisfy. It is a JSON document in the
`dpm-synth-template/1` format. This is
[`minimal.json`](samples/minimal.json); save it in an empty folder to
follow along:

```json
--8<-- "docs/samples/minimal.json"
```

- Table `T_01.00` has three monetary cells (`data_type` `m`) in rows 0010 to
  0030 of column 0010. Each cell names the `datapoint` that carries its
  value in the package.
- Rule `v1` says row 0010 is the sum of rows 0020 and 0030; rule `v2` says
  both components are zero or more.

For a real module the template has thousands of cells and rules and is
exported from a DPM release; see
[get a template from a DPM release](guides/from-a-dpm-release.md). To write
your own, see [write a template by hand](guides/write-a-template.md).

## 3. Generate on the command line

```console
$ dpm-synth generate minimal.json -o report.zip --seed 7  # (1)!
rules: 2, passed: 2, failed: 0
rounds: 1 (failing rules per round: 0)
wrote report.zip (3 facts)
$ echo $?
0
```

1. `-o` names the report package to write; `--seed` picks the random
   values, so the same seed gives the same report.

The summary counts the rules by status. `rounds` lists how many rules
failed at the start of each evaluate-and-repair round: here none, because
the joint solve of the linear rules had already settled them. Exit status
0 means no rule fails; 1 would mean some still fail, and the package is
written either way.

## 4. Read the package back

`report.zip` is an EBA xBRL-CSV report package. Read it with dpm-xbrl:

```python
from dpmxbrl import read_report

report = read_report("report.zip")
print(report.entity_id, report.reference_date, report.filing_indicators)
for fact in report.facts:
    print(fact.template, fact.datapoint, fact.value)
print([finding.code for finding in report.filing])  # (1)!
```

1. The EBA filing rules the file breaks, as dpm-xbrl records them.

```text
SYNTHETICDPMXL000002.CON 2026-12-31 {'T_01.00': True}
t_01.00 dp1001 9253000
t_01.00 dp1002 283000
t_01.00 dp1003 8970000
['invalidFileName']
```

The entity is the fictional LEI `SYNTHETICDPMXL000002` at the consolidated
level. The only EBA filing rule the package breaks is the file name, which
for a real submission encodes the entity, module and dates; name the output
accordingly if that matters to you. [Standards and
conformance](reference/standards.md) lists the filing rules the reports
follow.

## 5. Generate from Python

The same from Python, with the result of the repair loop:

```python
from dpmxbrl import write_xbrl_csv

from dpmsynth import generate, load_template

template = load_template("minimal.json")  # (1)!
result = generate(template, seed=7)
print(f"{result.summary['passed']} passed, failed: {result.failed}")  # (2)!
print(f"rounds: {result.rounds}, failing per round: {result.history}")
write_xbrl_csv(result.report, "report.zip")
```

1. Raises `TemplateError`, naming the field, if the template is not valid.
2. `summary` counts the rules by status; `failed` lists the codes of the
   rules that still fail.

```text
2 passed, failed: []
rounds: 1, failing per round: [0]
```

## 6. Evaluate a rule on the values

`result.report` is a `dpmxbrl.Report`; `result.data` holds the generated
values and is a dpm-xl data provider, so you can evaluate any rule on it:

```python
from dpmxl import evaluate_rule

rule = "with {tT_01.00, c0010}: {r0010} >= {r0020}"
print(evaluate_rule(rule, result.data).status)
```

```text
passed
```

## 7. Try a bigger template

[`sample.json`](samples/sample.json) has a closed table with row and column
totals, a ratio and an enumerated cell, an open table keyed by an
enumerated property, an open table keyed by LEIs, and a `time_shift` rule
that needs last year's report:

```console
$ dpm-synth generate sample.json -o sample.zip --seed 7
rules: 9, passed: 8, failed: 0, unsupported: 1
rounds: 2 (failing rules per round: 3, 0)
history: unsupported: The rule compares with the previous reporting period (time_shift), which a single report does not include
wrote sample.zip (20 facts)
```

Three rules failed at the start of the first round and none at the start
of the second. The `time_shift` rule is `unsupported`: a single report has
no previous period, and the summary says so. It does not change the exit
status.

## What you learned

- A template lists a module's tables, cells and rules.
- `dpm-synth generate` and [`generate`][dpmsynth.generate] fill every
  cell, repair the values until the rules pass, and report each rule's
  status.
- The package is an ordinary EBA xBRL-CSV report package that dpm-xbrl
  reads back and dpm-xl can check.

## Next steps

- [Shape a realistic report](guides/realistic-reports.md): institution
  size, sparse reports, currencies, warnings and inactive rules.
- [Validate the output](guides/validate-output.md) independently with
  dpm-xbrl and dpm-xl.
- [Load-test](guides/load-testing.md) with millions of open-table rows.
- Read [the limits of the loop](concepts/limits.md) before relying on a
  module's every rule passing.
