---
description: A first synthetic report end to end - install, a template, generate from the command line and from Python, read the package back, and next steps.
---

# Getting started

This tutorial generates a synthetic report for a small template, reads the
package back with dpm-xbrl and checks the rules with dpm-xl. It takes about
ten minutes.

## Install

```text
pip install dpm-synth
```

dpm-synth needs Python 3.11 or newer. It installs [dpm-xl], which evaluates
DPM-XL rules, and [dpm-xbrl], which reads and writes EBA reports.

## The template

A template describes one module: its tables, the cells of each table, and
the rules a report must satisfy. It is a JSON document in the
`dpm-synth-template/1` format. This is
[`minimal.json`](samples/minimal.json):

```json
--8<-- "docs/samples/minimal.json"
```

- Table `T_01.00` has three monetary cells (`data_type` `m`) in rows 0010 to
  0030 of column 0010. Each cell names the `datapoint` that carries its
  value in the package.
- Rule `v1` says row 0010 is the sum of rows 0020 and 0030; rule `v2` says
  both components are zero or more.

For real modules you do not write templates by hand: any tool that reads a
DPM release can export them; see
[build a template from a DPM release](guides/from-a-dpm-release.md).
To write your own, see [write a template by hand](guides/write-a-template.md).

## Generate from the command line

```console
$ dpm-synth generate minimal.json -o report.zip --seed 7
rules: 2, passed: 2, failed: 0
rounds: 2 (failing rules per round: 1, 0)
wrote report.zip (3 facts)
$ echo $?
0
```

The first round found one failing rule (the random total did not match its
components), repaired it, and the second round found none. Exit status 0
means every rule that could be evaluated passes; 1 would mean some still
fail. The package is written either way.

## Read the package back

`report.zip` is an EBA xBRL-CSV report package. Read it with dpm-xbrl:

```python
from dpmxbrl import read_report

report = read_report("report.zip")
print(report.entity_id, report.reference_date, report.filing_indicators)
for fact in report.facts:
    print(fact.template, fact.datapoint, fact.value)
print([finding.code for finding in report.filing])
```

```text
SYNTHETICDPMXL000002.CON 2026-12-31 {'T_01.00': True}
t_01.00 dp1001 1126000
t_01.00 dp1002 971000
t_01.00 dp1003 155000
['invalidFileName']
```

The entity is the fictional LEI `SYNTHETICDPMXL000002` at the consolidated
level. The only EBA filing rule the package breaks is the file name, which
for a real submission encodes the entity, module and dates; name the output
accordingly if that matters to you.

## Generate from Python

The same from Python, with the result of the repair loop:

```python
from dpmxbrl import write_xbrl_csv

from dpmsynth import generate, load_template

template = load_template("minimal.json")
result = generate(template, seed=7)
print(f"{result.summary['passed']} passed, failed: {result.failed}")
print(f"rounds: {result.rounds}, failing per round: {result.history}")
write_xbrl_csv(result.report, "report.zip")
```

```text
2 passed, failed: []
rounds: 2, failing per round: [1, 0]
```

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

## A bigger template

[`sample.json`](samples/sample.json) has a closed table with row and column
totals, a ratio and an enumerated cell, an open table keyed by an
enumerated property, an open table keyed by LEIs, and a `time_shift` rule
that needs last year's report:

```console
$ dpm-synth generate sample.json -o sample.zip --seed 7
rules: 9, passed: 8, failed: 0, unsupported: 1
rounds: 5 (failing rules per round: 5, 3, 1, 1, 0)
history: unsupported: The rule compares with the previous reporting period (time_shift), which a single report does not include
wrote sample.zip (20 facts)
```

The `time_shift` rule is `unsupported`: a single report has no previous
period, and the summary says so. [The evaluate-and-repair loop](concepts/repair-loop.md) explains the
rounds.

## Next steps

- [Validate the output](guides/validate-output.md) independently with
  dpm-xbrl and dpm-xl.
- [Load-test](guides/load-testing.md) with millions of open-table rows.
- Read [the limits of the loop](concepts/limits.md) before relying on a
  module's every rule passing.
