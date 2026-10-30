---
description: Tutorial - install dpm-synth, read a template file, generate a first synthetic report, look inside the package, read it back with dpm-xbrl and check a rule with dpm-xl.
icon: lucide/graduation-cap
---

# Getting started

This tutorial generates a synthetic report from a small template file,
looks at the files inside it, reads it back with dpm-xbrl and checks a rule
with dpm-xl. It takes about ten minutes.

You need Python 3.11 or newer and a terminal. No knowledge of XBRL or
DPM-XL is assumed: each step says what the output means, and terms with a
dotted underline, such as datapoint, show a definition when you point at
them. The [glossary](reference/glossary.md) lists them all.

You will:

1. install dpm-synth;
2. read a template file;
3. generate a report on the command line;
4. look inside the package;
5. read the package back;
6. generate from Python;
7. evaluate a rule on the generated values;
8. try a bigger template file.

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

## 2. Read a template file

dpm-synth's input is a *template file*: a JSON document that describes one
module, with its tables, the cells of each table, and the rules a report
must satisfy. In EBA reporting, a *template* is a reporting form such as
`C_07.00`, made of one or more *tables* such as `C_07.00.a`; the template
file lists tables, and rules and reports name them.

This is [`minimal.json`](samples/minimal.json); save it in an empty folder
to follow along:

```json
--8<-- "docs/samples/minimal.json"
```

- Table `T_01.00` has three monetary cells (`data_type` `m`) in rows 0010 to
  0030 of column 0010. Each cell names the `datapoint` that carries its
  value in the package.
- Rule `v1` says row 0010 is the sum of rows 0020 and 0030; rule `v2` says
  both components are zero or more.

For a real module the template file has thousands of cells and rules. It
is the module file that `dpm-xl export-module` writes from an EBA DPM
release; see [get a template from a DPM release](guides/from-a-dpm-release.md).
To write your own, see [write a template by hand](guides/write-a-template.md).

## 3. Generate on the command line

```console
$ dpm-synth generate minimal.json -o report.zip --seed 7  # (1)!
rules: 2, passed: 2, failed: 0
rounds: 1 (failing rules per round: 0)
wrote report.zip (3 facts)
$ echo $?
0
```

1. `-o` names the report package (a ZIP) to write; `--seed` picks the
   random values, so the same seed gives the same report.

`rules` counts the checks the report must pass; both pass. `rounds` is how
many fix-up passes dpm-synth made, with the number of rules failing at the
start of each; you can ignore it unless rules still fail
([how it works](concepts/repair-loop.md)). Exit status 0 means nothing
failed; the [exit statuses](reference/exit-statuses.md) list the others.

## 4. Look inside the package

`report.zip` is an EBA xBRL-CSV report package: a ZIP of a few JSON and
CSV files.

```console
$ unzip -Z1 report.zip
report/META-INF/reportPackage.json
report/reports/report.json
report/reports/parameters.csv
report/reports/FilingIndicators.csv
report/reports/t_01.00.csv
```

- `reportPackage.json` marks the ZIP as a report package.
- `report.json` names the module's taxonomy entry point.
- `parameters.csv` holds the entity, the reference date, the currency and
  the decimals the values are reported with.
- `FilingIndicators.csv` says which templates the report includes.
- Each other CSV file is one table, named by its code in lower case. It
  has one row per fact:

```console
$ unzip -p report.zip report/reports/t_01.00.csv
datapoint,factValue
dp1001,9253000
dp1002,283000
dp1003,8970000
```

A datapoint code identifies a cell of the table, here rows 0010 to 0030;
the template file maps each code to its row and column.

## 5. Read the package back

Read the package with dpm-xbrl, as a consumer of the report would:

```python
from dpmxbrl import read_report

report = read_report("report.zip")
print(report.entity_id, report.reference_date, report.filing_indicators)
for fact in report.facts:
    print(fact.datapoint, fact.value)
print([finding.code for finding in report.filing])  # (1)!
```

1. The EBA filing rules the file breaks, as dpm-xbrl records them.

```text
SYNTHETICDPMXL000002.CON 2026-12-31 {'T_01.00': True}
dp1001 9253000
dp1002 283000
dp1003 8970000
['invalidFileName']
```

The entity is the fictional LEI `SYNTHETICDPMXL000002` at the consolidated
level. `{'T_01.00': True}` is the filing indicator: the report declares that
it includes template `T_01.00`. The only EBA filing rule the package breaks
is the file name, which for a real submission encodes the entity, module
and dates; name the output accordingly if that matters to you. [Standards and
conformance](reference/standards.md) lists the filing rules the reports
follow.

## 6. Generate from Python

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

## 7. Evaluate a rule on the values

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

## 8. Try a bigger template file

[`sample.json`](samples/sample.json) has a closed table with row and column
totals, a ratio and an enumerated cell, an open table keyed by an
enumerated property, an open table keyed by LEIs, and a `time_shift` rule
that needs last year's report:

```console
$ dpm-synth generate sample.json -o sample.zip --seed 7
rules: 9, passed: 8, failed: 0, unsupported: 1
rounds: 2 (failing rules per round: 3, 0)
rule prior-period (unsupported): The rule compares with the previous reporting period (time_shift), which a single report does not include
wrote sample.zip (20 facts)
```

Three rules failed at the start of the first pass and none at the start
of the second. Rule `prior-period` compares with last year's report, which
a single report does not have, so it is `unsupported`; the line starting
with `rule prior-period` gives the reason. An `unsupported` rule does not
change the exit status.

## What you learned

- A template file lists a module's tables, cells and rules.
- The package is a ZIP with one CSV file per table.
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
